"""Read existing v5 output independently; never write game archives or images."""
import hashlib
import json
from pathlib import Path
import struct
import zlib
import argparse


def validate(root, source=None):
    report = json.loads((root / 'VIP_v11A_Archive_Entry_Report.json').read_text())
    archive = root / 'VIP_v11A_ASSETS_v5_Test.dat'
    source = source or root / 'VIP_v11A_ASSETS_Decompiled'
    original = root / 'VIP_v11A_Extraction_Test/ASSETS.DAT'
    entries = report['all_entries']
    mismatches, changed, ranges = [], [], []
    verified = 0
    with archive.open('rb') as rebuilt, original.open('rb') as baseline:
        header = rebuilt.read(16)
        magic, count, table_bytes, names_bytes = struct.unpack('<4sIII', header)
        if magic != b'Dave' or count != len(entries) or baseline.read(16) != header:
            raise ValueError('Header mismatch')
        table_end = 0x800 + table_bytes + names_bytes
        rebuilt.seek(0x800 + table_bytes)
        baseline.seek(0x800 + table_bytes)
        if rebuilt.read(names_bytes) != baseline.read(names_bytes):
            raise ValueError('Filename table changed')
        for entry in entries:
            rebuilt.seek(0x800 + entry['index'] * 16)
            name_ref, offset, full, stored = struct.unpack('<IIII', rebuilt.read(16))
            baseline.seek(0x800 + entry['index'] * 16)
            old_name_ref = struct.unpack('<I', baseline.read(4))[0]
            if name_ref != old_name_ref:
                raise ValueError('Filename reference changed')
            if entry['directory_record']:
                if full or stored:
                    raise ValueError('Nonempty directory record')
                continue
            if offset < table_end or offset + stored > archive.stat().st_size:
                raise ValueError('Payload outside archive')
            ranges.append((offset, offset + stored, entry['index']))
            rebuilt.seek(offset)
            payload = rebuilt.read(stored)
            raw = zlib.decompress(payload, -15) if stored < full else payload
            if len(raw) != full:
                raise ValueError('Decoded size mismatch')
            name = entry['name']
            target = source.joinpath(*name.split('/')).resolve()
            if not target.is_relative_to(source.resolve()):
                raise ValueError('Unsafe source path')
            if hashlib.sha256(raw).digest() != hashlib.sha256(target.read_bytes()).digest():
                mismatches.append(name)
            baseline.seek(entry['data_offset'])
            old_payload = baseline.read(entry['stored_size'])
            old_raw = zlib.decompress(old_payload, -15) if entry['compressed'] else old_payload
            if raw != old_raw:
                changed.append({'name': name, 'original_bytes': len(old_raw), 'rebuilt_bytes': full})
            verified += 1
            if verified % 2000 == 0:
                print(f'Checked {verified} records', flush=True)
    ranges.sort()
    overlaps = sum(a[1] > b[0] for a, b in zip(ranges, ranges[1:]))
    return {'archive': str(archive), 'source': str(source.resolve()), 'bytes': archive.stat().st_size,
            'allocation_bytes': 1808326656, 'spare_bytes': 1808326656 - archive.stat().st_size,
            'verified_records': verified, 'source_mismatches': mismatches,
            'overlapping_payloads': overlaps, 'changed_records': changed,
            'passed': not mismatches and not overlaps,
            'game_compatibility': 'Not established by archive verification'}


if __name__ == '__main__':
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--report', type=Path, default=root / 'V5_Independent_Validation.json')
    args = parser.parse_args()
    if args.report.resolve().exists():
        raise FileExistsError('Refusing to overwrite existing diagnostic report')
    result = validate(root, args.source)
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'changed_records'}, indent=2))
    if not result['passed']:
        raise SystemExit(1)
