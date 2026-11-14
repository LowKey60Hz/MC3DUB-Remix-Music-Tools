#!/usr/bin/env python3
"""Read-only alignment diagnostics for the VIP v1.1-A archive-entry JSON report."""
import argparse
import json
from collections import Counter
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('report', nargs='?', default='VIP_v11A_Archive_Entry_Report.json')
    args = p.parse_args()
    report = json.loads(Path(args.report).read_text(encoding='utf-8'))
    entries = [e for e in report['all_entries'] if not e['directory_record']]
    print('VIP v1.1-A alignment diagnostics — READ ONLY')
    print('File records:', len(entries))
    print('Unique file offsets:', len({e['data_offset'] for e in entries}))
    print('\nOffset divisibility (counts overlap):')
    for n in (16, 32, 64, 128, 256, 512, 1024, 2048, 4096):
        count = sum(e['data_offset'] % n == 0 for e in entries)
        print(f'  {n:>4} bytes: {count:>6,} / {len(entries):,} ({count/len(entries):6.2%})')
    print('\nSmallest power-of-two alignment bucket (maximum tested):')
    buckets = Counter()
    for e in entries:
        align = 1
        for n in (16, 32, 64, 128, 256, 512, 1024, 2048, 4096):
            if e['data_offset'] % n == 0:
                align = n
        buckets[align] += 1
    for align, count in sorted(buckets.items()):
        print(f'  {align:>4} bytes: {count:>6,}')
    print('\nCompression flag vs 2048-byte alignment:')
    for compressed in (True, False):
        subset = [e for e in entries if bool(e['compressed']) == compressed]
        aligned = sum(e['data_offset'] % 2048 == 0 for e in subset)
        print(f'  compressed={str(compressed):5}: {aligned:,} / {len(subset):,} aligned')
    print('\nFirst 12 file records:')
    print(f"{'Index':>6} {'Offset':>13} {'Stored':>11} {'mod 2048':>9}  Name")
    for e in entries[:12]:
        print(f"{e['index']:>6} {e['data_offset']:>13,} {e['stored_size']:>11,} {e['data_offset']%2048:>9}  {e['name']}")
    print('\nNote: Offset divisibility does not prove the builder\'s alignment rule.')
    print('Original archives may have out-of-order entries and intentional gaps.')
    print('No files were modified.')

if __name__ == '__main__':
    main()
