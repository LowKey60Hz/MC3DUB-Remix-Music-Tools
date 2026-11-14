#!/usr/bin/env python3
"""Experimental Dave archive rebuild. No production files are overwritten.

Uses the original archive's complete header/filename table, entry ordering,
compression flags, and original physical payload ordering. This is a research
prototype, NOT an ISO-ready or game-validated builder.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

ORIGINAL_ALLOCATION = 1_808_326_656
ALIGN_SMALL = 32
ALIGN_LARGE = 2048


def align_up(x, a):
    return (x + a - 1) // a * a


def safe_path(root, name):
    if '\\' in name or name.startswith('/') or '..' in name.split('/'):
        raise ValueError('Unsafe archive path: ' + name)
    path = root.joinpath(*name.split('/'))
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Path escapes source folder: ' + name)
    return path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report', type=Path, default=Path('VIP_v11A_Archive_Entry_Report.json'))
    p.add_argument('--archive', type=Path, default=Path('VIP_v11A_Extraction_Test/ASSETS.DAT'))
    p.add_argument('--source', type=Path, default=Path('VIP_v11A_ASSETS_Decompiled'))
    p.add_argument('--output', type=Path, default=Path('VIP_v11A_ASSETS_Experimental.dat'))
    p.add_argument('--build', action='store_true', help='Actually build new archive (default: preflight only)')
    p.add_argument('--verify', action='store_true', help='After build, verify all file records against source files')
    args = p.parse_args()
    report = json.loads(args.report.read_text(encoding='utf-8'))
    entries = report['all_entries']
    archive = args.archive.resolve()
    source = args.source.resolve()
    output = args.output.resolve()
    if output == archive or output == args.report.resolve():
        raise ValueError('Output must not overwrite the source archive or report')
    if output.exists():
        raise FileExistsError('Refusing to overwrite existing output: ' + str(output))
    if not source.is_dir():
        raise FileNotFoundError(source)
    with archive.open('rb') as f:
        magic, count, entry_block_size, name_block_size = struct.unpack('<4sIII', f.read(16))
        if magic != b'Dave' or count != len(entries):
            raise ValueError('Archive magic/count mismatch with report')
        first_payload = min(e['data_offset'] for e in entries if not e['directory_record'])
        table_end = 0x800 + entry_block_size + name_block_size
        if table_end > first_payload:
            raise ValueError('Original header overlaps file payloads')
        f.seek(0)
        prefix = f.read(first_payload)
    files = [e for e in entries if not e['directory_record']]
    paths = {}
    for e in files:
        if e['name'] not in paths:
            path = safe_path(source, e['name'])
            if not path.is_file():
                raise FileNotFoundError(path)
            if path.stat().st_size != e['full_size']:
                raise ValueError('Source size differs from report: ' + e['name'])
            paths[e['name']] = path
    print('EXPERIMENTAL VIP v1.1-A Dave builder')
    print('Entries:', len(entries), '| File records:', len(files), '| Unique source files:', len(paths))
    print('Original first payload:', first_payload)
    print('Original archive bytes:', archive.stat().st_size)
    print('Output:', output)
    print('Original archive remains unchanged.')
    if not args.build:
        print('PREFLIGHT PASSED. Add --build to create a new archive.')
        return

    # Preserve the original physical order, not the logical filename-table order.
    physical = sorted(files, key=lambda e: e['data_offset'])
    offsets = {}
    sizes = {}
    inefficient_count = 0
    inefficient_examples = []
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open('xb') as dst:
            dst.write(prefix)
            pos = first_payload
            for n, e in enumerate(physical, 1):
                # Preserve a conservative per-record alignment category. This is
                # an approximation, not proof of the original builder's rules.
                boundary = ALIGN_LARGE if e['data_offset'] % ALIGN_LARGE == 0 else ALIGN_SMALL
                pos = align_up(pos, boundary)
                if pos > 0xFFFFFFFF:
                    raise ValueError('Offset exceeds Dave 32-bit field')
                path = paths[e['name']]
                data = path.read_bytes()
                if e['compressed']:
                    obj = zlib.compressobj(9, zlib.DEFLATED, -15)
                    stored = obj.compress(data) + obj.flush()
                    # A compressed archive record can legitimately store more
                    # bytes than its uncompressed source. Preserve its flag.
                    if zlib.decompress(stored, -15) != data:
                        raise ValueError('Compression round-trip failed: ' + e['name'])
                    if len(stored) >= len(data):
                        inefficient_count += 1
                        if len(inefficient_examples) < 12:
                            inefficient_examples.append((e['name'], len(data), len(stored)))
                else:
                    stored = data
                dst.seek(pos)
                dst.write(stored)
                offsets[e['index']] = pos
                sizes[e['index']] = len(stored)
                pos += len(stored)
                if n % 1000 == 0:
                    print(f'Written {n:,}/{len(physical):,} records; {pos:,} bytes')
            # Directory entries have zero sizes. Set their pointers to the next
            # logical file record (or final end if none). Their offset semantics
            # require independent game validation.
            next_offset = pos
            for e in reversed(entries):
                if e['directory_record']:
                    offsets[e['index']] = next_offset
                    sizes[e['index']] = 0
                else:
                    next_offset = offsets[e['index']]
            for e in entries:
                idx = e['index']
                if idx < 0 or idx >= count:
                    raise ValueError('Invalid entry index')
                dst.seek(0x800 + idx * 16 + 4)
                dst.write(struct.pack('<III', offsets[idx], e['full_size'], sizes[idx]))
            dst.truncate(pos)
        print('Compressed records not smaller than source:', inefficient_count)
        for name, raw_size, compressed_size in inefficient_examples:
            print(f'  Compression overhead: {name} ({raw_size:,} -> {compressed_size:,} bytes)')
        print('Built archive:', output)
        print('Output bytes:', output.stat().st_size)
        print('Allocation limit:', ORIGINAL_ALLOCATION)
        print('Difference:', output.stat().st_size - ORIGINAL_ALLOCATION)
        print('Fits allocation:', output.stat().st_size <= ORIGINAL_ALLOCATION)
        if args.verify:
            print('Verifying every archive record...')
            with output.open('rb') as f:
                for n, e in enumerate(files, 1):
                    idx = e['index']
                    f.seek(offsets[idx]); payload = f.read(sizes[idx])
                    if len(payload) != sizes[idx]:
                        raise ValueError('Truncated payload: ' + e['name'])
                    raw = zlib.decompress(payload, -15) if e['compressed'] else payload
                    if len(raw) != e['full_size'] or hashlib.sha256(raw).digest() != hashlib.sha256(paths[e['name']].read_bytes()).digest():
                        raise ValueError('Content mismatch: ' + e['name'])
                    if n % 2000 == 0:
                        print(f'Verified {n:,}/{len(files):,}')
            print('ALL FILE RECORDS VERIFIED')
        print('WARNING: Archive has not been game-tested. Do not inject into a production ISO.')
    except Exception:
        if output.exists():
            print('Partial output may exist and should be deleted:', output)
        raise


if __name__ == '__main__':
    main()
