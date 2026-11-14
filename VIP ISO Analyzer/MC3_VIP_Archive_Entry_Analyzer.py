#!/usr/bin/env python3
"""Read-only DAVE/Dave archive entry analyzer. Python 3.8+."""
import argparse
import collections
import json
import os
from pathlib import Path
import struct

CHARS = "\x00 #$()-./?0123456789_abcdefghijklmnopqrstuvwxyz~\x7f"


def read_exact(f, n):
    data = f.read(n)
    if len(data) != n:
        raise ValueError('Unexpected end of archive')
    return data


def decode_name(f, magic, offset, previous):
    f.seek(offset)
    if magic == b'DAVE':
        data = bytearray()
        while True:
            b = read_exact(f, 1)[0]
            if b == 0:
                break
            if len(data) >= 65536:
                raise ValueError('Unterminated filename')
            data.append(b)
        return data.decode('ascii')
    def bits():
        value = int.from_bytes(read_exact(f, 3), 'little')
        return [(value >> (i * 6)) & 63 for i in range(4)]
    name_bits = bits()
    name = ''
    if name_bits[0] >= 0x38:
        dedup = (name_bits.pop(1) - 0x20) * 8 + name_bits.pop(0) - 0x38
        if dedup < 0 or dedup > len(previous):
            raise ValueError('Invalid compressed-name prefix')
        name = previous[:dedup]
    for _ in range(65536):
        if not name_bits:
            name_bits = bits()
        if name_bits[0] == 0:
            return name
        idx = name_bits.pop(0)
        if idx >= len(CHARS):
            raise ValueError('Invalid compressed-name character index')
        name += CHARS[idx]
    raise ValueError('Compressed filename too long')


def analyze(archive, extracted, sample_limit):
    archive = Path(archive).resolve()
    extracted = Path(extracted).resolve() if extracted else None
    size = archive.stat().st_size
    entries = []
    with archive.open('rb') as f:
        magic, count, info_size, names_size = struct.unpack('<4sIII', read_exact(f, 16))
        if magic not in (b'DAVE', b'Dave'):
            raise ValueError('Not a DAVE/Dave archive')
        if count > 5_000_000 or 0x800 + count * 16 > size or info_size < count * 16:
            raise ValueError('Invalid archive entry table')
        name_start = 0x800 + info_size
        if name_start + names_size > size:
            raise ValueError('Filename table exceeds archive size')
        previous = ''
        for i in range(count):
            f.seek(0x800 + i * 16)
            noff, doff, full, stored = struct.unpack('<IIII', read_exact(f, 16))
            if noff >= names_size:
                raise ValueError('Invalid filename offset for entry {}'.format(i))
            name = decode_name(f, magic, name_start + noff, previous)
            previous = name
            if not name or name.startswith('/') or '\\' in name or any(p in ('.', '..') for p in name.split('/')):
                raise ValueError('Unsafe or invalid entry name at {}: {!r}'.format(i, name))
            if doff + stored > size:
                raise ValueError('Entry {} extends beyond archive'.format(i))
            entries.append({'index': i, 'name': name, 'data_offset': doff,
                            'full_size': full, 'stored_size': stored,
                            'directory_record': name.endswith('/'),
                            'compressed': full != stored})

    names = collections.defaultdict(list)
    offsets = collections.defaultdict(list)
    for e in entries:
        names[e['name']].append(e['index'])
        offsets[e['data_offset']].append(e['index'])
    duplicate_names = {n: ids for n, ids in names.items() if len(ids) > 1}
    repeated_offsets = {str(off): ids for off, ids in offsets.items() if len(ids) > 1}
    directory_entries = [e for e in entries if e['directory_record']]
    file_entries = [e for e in entries if not e['directory_record']]
    zero_entries = [e for e in entries if e['full_size'] == 0 and e['stored_size'] == 0]
    files_missing = []
    dirs_missing = []
    mismatched_sizes = []
    if extracted:
        if not extracted.is_dir():
            raise ValueError('Extracted folder does not exist: {}'.format(extracted))
        for e in entries:
            target = extracted.joinpath(*e['name'].rstrip('/').split('/'))
            if e['directory_record']:
                if not target.is_dir():
                    dirs_missing.append(e['name'])
            else:
                if not target.is_file():
                    files_missing.append(e['name'])
                elif target.stat().st_size != e['full_size']:
                    mismatched_sizes.append({'name': e['name'], 'archive_size': e['full_size'], 'disk_size': target.stat().st_size})
        disk_files = sum(len(fs) for _, _, fs in os.walk(extracted))
        disk_dirs = sum(len(ds) for _, ds, _ in os.walk(extracted))
    else:
        disk_files = disk_dirs = None
    sample = lambda values: list(values)[:sample_limit]
    report = {
        'archive': str(archive), 'archive_bytes': size, 'format': magic.decode('ascii'),
        'total_entries': count, 'directory_records': len(directory_entries),
        'file_records': len(file_entries), 'zero_byte_records': len(zero_entries),
        'compressed_file_records': sum(e['compressed'] for e in file_entries),
        'stored_file_bytes': sum(e['stored_size'] for e in file_entries),
        'unique_names': len(names), 'duplicate_name_groups': len(duplicate_names),
        'extra_duplicate_name_records': sum(len(v)-1 for v in duplicate_names.values()),
        'repeated_offset_groups': len(repeated_offsets),
        'extra_repeated_offset_records': sum(len(v)-1 for v in repeated_offsets.values()),
        'directory_records_with_nonzero_size': sum(bool(e['full_size'] or e['stored_size']) for e in directory_entries),
        'extracted_directory': str(extracted) if extracted else None,
        'disk_files': disk_files, 'disk_directories': disk_dirs,
        'missing_file_record_count': len(files_missing), 'missing_directory_record_count': len(dirs_missing),
        'file_size_mismatch_count': len(mismatched_sizes),
        'duplicate_name_examples': [{'name': n, 'entry_indices': ids[:20], 'count': len(ids)} for n, ids in sample(duplicate_names.items())],
        'shared_offset_examples': [{'offset': off, 'entry_indices': ids[:20], 'count': len(ids),
                                    'names': [entries[i]['name'] for i in ids[:10]]}
                                   for off, ids in sample(repeated_offsets.items())],
        'missing_file_examples': sample(files_missing),
        'missing_directory_examples': sample(dirs_missing),
        'file_size_mismatch_examples': sample(mismatched_sizes),
        'directory_record_examples': [e['name'] for e in directory_entries[:sample_limit]],
        'zero_byte_record_examples': [e['name'] for e in zero_entries[:sample_limit]],
        'all_entries': entries,
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', help='Original ASSETS.DAT')
    parser.add_argument('--extracted', help='Previously decompiled ASSETS directory')
    parser.add_argument('--output', default='VIP_v11A_Archive_Entry_Report.json')
    parser.add_argument('--sample-limit', type=int, default=20)
    args = parser.parse_args()
    if args.sample_limit < 1 or args.sample_limit > 1000:
        parser.error('--sample-limit must be between 1 and 1000')
    report = analyze(args.archive, args.extracted, args.sample_limit)
    out = Path(args.output).resolve()
    if out == Path(args.archive).resolve() or (args.extracted and out.is_relative_to(Path(args.extracted).resolve())):
        parser.error('Output report must not overwrite archive or extracted files')
    if out.exists():
        parser.error('Output report already exists: {}'.format(out))
    with out.open('x', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print('MC3 VIP Archive Entry Analyzer — READ ONLY')
    for key in ('format','total_entries','directory_records','file_records','zero_byte_records',
                'compressed_file_records','unique_names','duplicate_name_groups',
                'extra_duplicate_name_records','repeated_offset_groups','extra_repeated_offset_records',
                'disk_files','disk_directories','missing_file_record_count',
                'missing_directory_record_count','file_size_mismatch_count'):
        print('{:<34} {}'.format(key + ':', report[key]))
    print('Report:', out)
    print('Original archive and extracted files unchanged.')

if __name__ == '__main__':
    main()
