#!/usr/bin/env python3
"""Read-only comparison of original DAVE stored sizes with raw-DEFLATE trials.
No archive, extracted file, or report is modified.
"""
import argparse
import json
import zlib
from pathlib import Path

MiB = 1024 * 1024

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report', default='VIP_v11A_Archive_Entry_Report.json')
    p.add_argument('--extracted', default='VIP_v11A_ASSETS_Decompiled')
    p.add_argument('--archive', default='VIP_v11A_Extraction_Test/ASSETS.DAT')
    args = p.parse_args()
    report = json.loads(Path(args.report).read_text(encoding='utf-8'))
    root = Path(args.extracted).resolve()
    archive = Path(args.archive)
    if not archive.is_file():
        p.error('Archive not found: ' + str(archive))
    by_name = {}
    for entry in report['all_entries']:
        if not entry['directory_record']:
            by_name[entry['name']] = entry
    candidates = [e for e in by_name.values() if e['compressed'] and e['name'].lower().endswith('.pck') and e['full_size'] <= 16 * MiB]
    picks = []
    for prefix in ('resources/prop/', 'resources/city/'):
        matching = sorted((e for e in candidates if e['name'].lower().startswith(prefix)), key=lambda e: e['full_size'])
        if matching:
            for e in (matching[0], matching[len(matching)//2], matching[-1]):
                if e['name'] not in [x['name'] for x in picks]:
                    picks.append(e)
    exception = by_name.get('resources/city/tokyo_clear_none.pck')
    if exception:
        picks.append(exception)
    if not picks:
        p.error('No suitable PCK files found in report')
    print('READ-ONLY compression test (raw DEFLATE, levels 1/6/9)')
    print('Files sampled:', len(picks))
    print('NOTE: Recompression need not match original byte-for-byte.')
    print()
    with archive.open('rb') as source:
        for e in picks:
            name = e['name']
            path = (root / Path(*name.split('/'))).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                print('MISSING:', name)
                continue
            data = path.read_bytes()
            if len(data) != e['full_size']:
                print('SIZE MISMATCH:', name, len(data), 'expected', e['full_size'])
                continue
            source.seek(e['data_offset'])
            stored = source.read(e['stored_size'])
            if len(stored) != e['stored_size']:
                print('ARCHIVE SHORT READ:', name)
                continue
            try:
                original_data = zlib.decompress(stored, -15) if e['compressed'] else stored
            except zlib.error as ex:
                print('ORIGINAL DECOMPRESSION FAILED:', name, ex)
                continue
            if original_data != data:
                print('CONTENT MISMATCH:', name, '(duplicate or extraction issue)')
                continue
            sizes = {}
            for level in (1, 6, 9):
                obj = zlib.compressobj(level=level, wbits=-15)
                sizes[level] = len(obj.compress(data) + obj.flush())
            print(name)
            print(f"  full={len(data):,} original_stored={e['stored_size']:,} original_compressed={e['compressed']}")
            print('  trial raw-DEFLATE bytes: ' + '  '.join(f'level {k}={v:,} ({v-e["stored_size"]:+,})' for k,v in sizes.items()))
            print()
    print('Finished. No files were changed.')

if __name__ == '__main__':
    main()
