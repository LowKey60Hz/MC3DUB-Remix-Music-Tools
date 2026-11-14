#!/usr/bin/env python3
"""Read-only physical payload gap diagnostics for VIP v1.1-A ASSETS.DAT."""
import argparse
import json
from collections import Counter
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', nargs='?', default='VIP_v11A_Archive_Entry_Report.json')
    args = parser.parse_args()
    report = json.loads(Path(args.report).read_text(encoding='utf-8'))
    records = sorted((e for e in report['all_entries'] if not e['directory_record']),
                     key=lambda e: (int(e['data_offset']), int(e['index'])))
    if not records:
        raise SystemExit('No file records found.')
    gaps = []
    overlaps = []
    for previous, current in zip(records, records[1:]):
        end = int(previous['data_offset']) + int(previous['stored_size'])
        gap = int(current['data_offset']) - end
        item = (gap, previous, current)
        if gap < 0:
            overlaps.append(item)
        else:
            gaps.append(item)

    print('VIP v1.1-A physical payload gap analysis — READ ONLY')
    print(f'File records: {len(records):,}')
    print(f'Unique offsets: {len(set(int(e["data_offset"]) for e in records)):,}')
    print(f'Non-overlapping consecutive pairs: {len(gaps):,}')
    print(f'Overlapping consecutive pairs: {len(overlaps):,}')
    print(f'First payload offset: {int(records[0]["data_offset"]):,}')
    print(f'Last payload end: {max(int(e["data_offset"]) + int(e["stored_size"]) for e in records):,}')
    if gaps:
        print(f'Total positive gaps: {sum(g for g, _, _ in gaps if g > 0):,} bytes')
        print(f'Median nonnegative gap: {sorted(g for g, _, _ in gaps)[len(gaps)//2]:,} bytes')
        print('\nGap size bands:')
        bands = Counter()
        for gap, _, _ in gaps:
            label = ('0' if gap == 0 else '1–31' if gap < 32 else
                     '32–127' if gap < 128 else '128–2047' if gap < 2048 else
                     '2048–65535' if gap < 65536 else '65536+')
            bands[label] += 1
        for label in ('0', '1–31', '32–127', '128–2047', '2048–65535', '65536+'):
            print(f'  {label:>11}: {bands[label]:>6,}')
        print('\nCommon exact gap sizes:')
        for gap, count in Counter(g for g, _, _ in gaps).most_common(15):
            print(f'  {gap:>10,} bytes: {count:>6,}')
        print('\nGap equals minimum padding needed for next file alignment:')
        for alignment in (32, 64, 128, 2048):
            matches = sum(g == (- (int(prev['data_offset']) + int(prev['stored_size']))) % alignment
                          for g, prev, _ in gaps)
            print(f'  {alignment:>4} bytes: {matches:>6,} / {len(gaps):,} ({matches / len(gaps):.2%})')
        print('\nLargest positive gaps (may reflect layout regions, not padding):')
        for gap, previous, current in sorted(gaps, key=lambda x: x[0], reverse=True)[:10]:
            print(f'  {gap:>12,}  after {previous["name"][:52]}')
            print(f'                 before {current["name"][:52]}')
    if overlaps:
        print('\nFirst overlapping pairs (requires investigation):')
        for gap, previous, current in overlaps[:10]:
            print(f'  overlap {-gap:,} bytes: {previous["name"]} -> {current["name"]}')
    print('\nNo archive, extracted file, or ISO was modified.')


if __name__ == '__main__':
    main()
