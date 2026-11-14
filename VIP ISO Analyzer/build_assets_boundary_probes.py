"""Build isolated, real-resource ASSETS probes below/above 2 GiB.

Starts from the exact user-tested expanded ISO. All loading tracks are relocated
in ASSETS; no names, payloads, compression flags or source images are changed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import zlib
from build_v11a_expansion_test import module, digest, verify_unchanged

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent / 'UI Custom Gameplay Music Tools'
S = 2048
TESTED_SHA = '3cef6559a5b2e8797b1eed4ed774f3c0ee4afec9b159f1c4defe4d835f0b34e3'


def align(size):
    return (size + S - 1) // S * S


def relocation_plan(records, base_size, kind, capacity):
    selected = [x for x in records if x['name'].startswith('audio/loadscreen/') and x['name'].endswith('.raw')]
    if not selected:
        raise ValueError('No loading music records selected')
    total = sum(align(x['stored']) for x in selected)
    start = 2**31 - S - total if kind == 'below' else 2**31 + S
    if kind not in ('below', 'above') or start < align(base_size):
        raise ValueError('Invalid boundary plan or insufficient tail room')
    rows, position = [], start
    for item in selected:
        if not 0 <= item['stored'] <= 0xffffffff or item['stored'] == 0:
            raise ValueError('Invalid record length')
        rows.append({**item, 'new_offset': position})
        position += align(item['stored'])
    if position > capacity or position > 0xffffffff:
        raise ValueError('Probe exceeds calculated shared capacity or size fields')
    return {'kind': kind, 'start_offset': start, 'archive_bytes': position, 'records': rows}


def hash_extent(stream, start, size):
    stream.seek(start)
    value = hashlib.sha256()
    while size:
        data = stream.read(min(size, 8 * 1024 * 1024))
        if not data:
            raise ValueError('Truncated input')
        value.update(data)
        size -= len(data)
    return value.hexdigest()


def make_archive(source, output, plan):
    partial = output.with_suffix('.dat.partial')
    if output.exists() or partial.exists():
        raise FileExistsError(output)
    with source.open('rb') as inp, partial.open('xb') as out:
        shutil.copyfileobj(inp, out, 8 * 1024 * 1024)
        for row in plan['records']:
            inp.seek(row['offset'])
            payload = inp.read(row['stored'])
            if len(payload) != row['stored']:
                raise ValueError('Truncated source payload')
            out.seek(row['new_offset'])
            out.write(payload)
            out.seek(0x800 + row['index'] * 16 + 4)
            out.write(struct.pack('<I', row['new_offset']))
        out.truncate(plan['archive_bytes'])
    # Independent checks: the complete old archive is unchanged except the
    # exact offset fields, and every relocated payload is byte-identical.
    with source.open('rb') as inp, partial.open('rb') as out:
        cursor = 0
        for row in sorted(plan['records'], key=lambda x: x['index']):
            field = 0x800 + row['index'] * 16 + 4
            if hash_extent(inp, cursor, field - cursor) != hash_extent(out, cursor, field - cursor):
                raise ValueError('Unexpected change to baseline archive')
            out.seek(field)
            actual = struct.unpack('<III', out.read(12))
            if actual != (row['new_offset'], row['full'], row['stored']):
                raise ValueError('Relocated record metadata mismatch')
            if hash_extent(inp, row['offset'], row['stored']) != hash_extent(out, row['new_offset'], row['stored']):
                raise ValueError('Relocated payload mismatch')
            cursor = field + 4
        if hash_extent(inp, cursor, source.stat().st_size - cursor) != hash_extent(out, cursor, source.stat().st_size - cursor):
            raise ValueError('Baseline payload area changed')
    partial.rename(output)


def make_iso(source, archive, output, tools, record, root_size):
    partial = output.with_suffix('.iso.partial')
    if output.exists() or partial.exists():
        raise FileExistsError(output)
    row = dict(name='ASSETS.DAT', sector=954583, size=archive.stat().st_size, fe_sector=347)
    if row['sector'] + row['size'] // S > tools.MANIFEST_SECTOR:
        raise ValueError('Probe reaches manifest')
    with source.open('rb') as inp, partial.open('xb') as out:
        shutil.copyfileobj(inp, out, 8 * 1024 * 1024)
    with archive.open('rb') as inp, partial.open('r+b') as out:
        out.seek(row['sector'] * S)
        tools.copy_archive(inp, out, row['size'])
        tools.patch_metadata(out, record, [row], root_size)
    with source.open('rb') as inp, partial.open('rb') as out:
        tools.inspect_output(out, [row], root_size)
        if hash_extent(out, row['sector'] * S, row['size']) != digest(archive):
            raise ValueError('ISO archive read-back mismatch')
        verify_unchanged(inp, out, source.stat().st_size,
                         [(261 * S, 262 * S), (347 * S, 348 * S),
                          (row['sector'] * S, row['sector'] * S + row['size'])], tools.hash_region)
    partial.rename(output)
    return digest(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', action='store_true')
    args = parser.parse_args()
    source = ROOT / 'MC3_VIP_v11A_Expansion_Experimental.iso'
    baseline = ROOT / 'VIP_v11A_ASSETS_v5_Test.dat'
    destination = ROOT / 'Boundary_Probes'
    if destination.exists():
        raise FileExistsError('Probe directory exists; refusing to mix runs')
    tools = module('probe_vip_tools', PROJECT / 'supporting_tools/MC3_ISO_Builder_VIP.py')
    capacity = module('probe_capacity', PROJECT / 'supporting_tools/vip_capacity.py').assess(baseline.stat().st_size, 1087309824)['max_assets_allocated_with_these_streams']
    entries = json.loads((ROOT / 'VIP_v11A_Archive_Entry_Report.json').read_text())['all_entries']
    records = []
    with baseline.open('rb') as inp:
        magic, count = struct.unpack('<4sI', inp.read(8))
        if magic != b'Dave' or count != len(entries):
            raise ValueError('Baseline archive/report mismatch')
        for entry in entries:
            if entry['directory_record']:
                continue
            inp.seek(0x800 + entry['index'] * 16 + 4)
            offset, full, stored = struct.unpack('<III', inp.read(12))
            records.append({'index': entry['index'], 'name': entry['name'], 'offset': offset, 'full': full, 'stored': stored})
    plans = [relocation_plan(records, baseline.stat().st_size, kind, capacity) for kind in ('below', 'above')]
    print(json.dumps([{'kind': p['kind'], 'archive_bytes': p['archive_bytes'], 'first_track_offset': p['start_offset'], 'relocated_records': len(p['records'])} for p in plans], indent=2), flush=True)
    print('Verifying exact user-tested source ISO...', flush=True)
    if digest(source) != TESTED_SHA:
        raise ValueError('User-tested source ISO changed')
    with source.open('rb') as inp:
        if hash_extent(inp, 954583 * S, baseline.stat().st_size) != digest(baseline):
            raise ValueError('Baseline archive differs from user-tested image')
        pvd = tools.read_exact(inp, 16 * S, S)
        root_size = tools.u32(pvd, 166)
        if tools.u32(pvd, 158) != 261:
            raise ValueError('Unexpected root directory')
        # Existing output inspector returns archive positions in the root record.
        directory = tools.read_exact(inp, 261 * S, root_size)
        pos, record = 0, {}
        while pos < len(directory) and directory[pos]:
            size = directory[pos]
            if size < 34 or pos + size > len(directory):
                raise ValueError('Malformed root record')
            name = directory[pos + 33:pos + 33 + directory[pos + 32]].decode('ascii', 'replace')
            record[name] = pos
            pos += size
        if 'ASSETS.DAT;1' not in record:
            raise ValueError('Missing ASSETS record')
    # Validate the real resources against the active files before moving them.
    with baseline.open('rb') as inp:
        for row in plans[0]['records']:
            inp.seek(row['offset'])
            data = inp.read(row['stored'])
            raw = zlib.decompress(data, -15) if row['stored'] < row['full'] else data
            target = PROJECT / 'ASSETS' / row['name']
            if len(raw) != row['full'] or hashlib.sha256(raw).hexdigest() != digest(target):
                raise ValueError('Loading track differs from active source')
    if not args.build:
        print('PREFLIGHT PASSED. Add --build to create two isolated probe archives and images.')
        return
    required = sum(p['archive_bytes'] + source.stat().st_size for p in plans)
    if shutil.disk_usage(ROOT).free < required + 64 * 1024 * 1024:
        raise ValueError('Insufficient space for both probes')
    destination.mkdir()
    results = []
    for plan in plans:
        print(f'Building and checking {plan["kind"]}-2GiB probe...', flush=True)
        archive = destination / f'ASSETS_{plan["kind"]}_2GiB.dat'
        output = destination / f'MC3_ASSETS_{plan["kind"]}_2GiB.iso'
        make_archive(baseline, archive, plan)
        sha = make_iso(source, archive, output, tools, record, root_size)
        results.append({**plan, 'iso': str(output), 'iso_sha256': sha, 'automated_checks_passed': True,
                        'runtime_status': 'NOT TESTED',
                        'test': 'Boot, enter gameplay and trigger loading-screen music; all 18 loading tracks have relocated records.'})
        (destination / f'{plan["kind"]}_2GiB_result.json').write_text(json.dumps(results[-1], indent=2) + '\n')
    (destination / 'Probe_Results.json').write_text(json.dumps(results, indent=2) + '\n')
    print('Both probes built and verified. Test BELOW first, then ABOVE; do not infer runtime support from padding or boot alone.', flush=True)


if __name__ == '__main__':
    main()
