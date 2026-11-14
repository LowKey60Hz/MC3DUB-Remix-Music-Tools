"""Isolate >2-GiB outer ASSETS size while preserving all successful resource offsets."""
import json
from pathlib import Path
import shutil
import struct
from build_assets_boundary_probes import ROOT, PROJECT, S, TESTED_SHA, hash_extent, make_archive, make_iso
from build_v11a_expansion_test import module, digest


def main():
    folder = ROOT / 'Boundary_Probes'
    archive = folder / 'ASSETS_above_2GiB_size_only.dat'
    output = folder / 'MC3_ASSETS_above_2GiB_size_only.iso'
    report_path = folder / 'size_only_2GiB_result.json'
    for path in (archive, archive.with_suffix('.dat.partial'), output, output.with_suffix('.iso.partial'), report_path):
        if path.exists():
            raise FileExistsError('Refusing to overwrite: ' + str(path))
    baseline = ROOT / 'VIP_v11A_ASSETS_v5_Test.dat'
    source = ROOT / 'MC3_VIP_v11A_Expansion_Experimental.iso'
    above = json.loads((folder / 'above_2GiB_result.json').read_text())
    failed_iso = folder / 'MC3_ASSETS_above_2GiB.iso'
    target_size = above['archive_bytes']
    if target_size != 2154035200:
        raise ValueError('Unexpected failed-probe size')
    tools = module('size_only_vip', PROJECT / 'supporting_tools/MC3_ISO_Builder_VIP.py')
    if 954583 + target_size // S >= tools.MANIFEST_SECTOR:
        raise ValueError('Probe exceeds inspected region')
    if shutil.disk_usage(ROOT).free < target_size + source.stat().st_size + 64 * 1024 * 1024:
        raise ValueError('Insufficient free space')
    print('Verifying successful source and failed high-offset probe hashes...', flush=True)
    if digest(source) != TESTED_SHA or digest(failed_iso) != above['iso_sha256']:
        raise ValueError('Source/probe fingerprint mismatch')
    max_payload_end = 0
    with source.open('rb') as inp:
        if hash_extent(inp, 954583 * S, baseline.stat().st_size) != digest(baseline):
            raise ValueError('Baseline differs from successful image')
        pvd = tools.read_exact(inp, 16 * S, S)
        root_size = tools.u32(pvd, 166)
        if tools.u32(pvd, 158) != 261:
            raise ValueError('Unexpected root sector')
        directory = tools.read_exact(inp, 261 * S, root_size)
        pos, record = 0, {}
        while pos < len(directory) and directory[pos]:
            length = directory[pos]
            if length < 34 or pos + length > len(directory):
                raise ValueError('Malformed root record')
            name = directory[pos + 33:pos + 33 + directory[pos + 32]].decode('ascii', 'replace')
            record[name] = pos
            pos += length
    with baseline.open('rb') as inp:
        magic, count = struct.unpack('<4sI', inp.read(8))
        if magic != b'Dave' or count != 19328:
            raise ValueError('Unexpected baseline archive')
        inp.seek(0x800)
        table = inp.read(count * 16)
        for index in range(count):
            _, offset, full, stored = struct.unpack_from('<IIII', table, index * 16)
            if stored:
                if offset + stored > baseline.stat().st_size:
                    raise ValueError('Baseline record exceeds archive')
                max_payload_end = max(max_payload_end, offset + stored)
    if max_payload_end >= 2**31:
        raise ValueError('Baseline already has high-offset payloads')
    print('Copying unchanged baseline archive and adding zero padding only...', flush=True)
    make_archive(baseline, archive, {'records': [], 'archive_bytes': target_size})
    with archive.open('rb') as inp:
        inp.seek(baseline.stat().st_size)
        remaining = target_size - baseline.stat().st_size
        while remaining:
            data = inp.read(min(8 * 1024 * 1024, remaining))
            if not data or any(data):
                raise ValueError('Archive extension is not zero-filled')
            remaining -= len(data)
    print('Building isolated size-only ISO and verifying protected bytes...', flush=True)
    output_sha = make_iso(source, archive, output, tools, record, root_size)
    with failed_iso.open('rb') as failed, output.open('rb') as size_only:
        for sector in (261, 347):
            if tools.read_exact(failed, sector * S, S) != tools.read_exact(size_only, sector * S, S):
                raise ValueError('Outer ASSETS metadata differs from failed high-offset probe')
    result = {'kind': 'above_2GiB_size_only', 'iso': str(output), 'iso_sha256': output_sha,
              'archive_bytes': target_size, 'baseline_archive_bytes': baseline.stat().st_size,
              'all_baseline_bytes_and_resource_records_unchanged': True,
              'zero_padding_verified': True, 'max_live_payload_end': max_payload_end,
              'outer_assets_metadata_identical_to_failed_probe': True,
              'automated_checks_passed': True, 'runtime_status': 'NOT TESTED',
              'test': 'Fresh boot; continue career; enter free roam/garage and confirm loading music. No save states.',
              'interpretation': 'A pass strengthens the high-offset-read hypothesis; a failure points toward outer archive size/metadata or overwrite-region behavior. Neither proves an exact engine limit.'}
    with report_path.open('x', encoding='utf-8') as report:
        report.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
