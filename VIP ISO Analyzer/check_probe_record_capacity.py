"""Reproduce record-aware capacity checks on existing research archives only."""
import hashlib
import json
from pathlib import Path
import importlib.util
import argparse

root = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('vip_capacity', root.parent / 'UI Custom Gameplay Music Tools/supporting_tools/vip_capacity.py')
capacity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capacity)
source = root.parent / "Base ISO's/Midnight Club 3 VIP v1.1-A.iso"
value = hashlib.sha256()
with source.open('rb') as stream:
    for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
        value.update(block)
streams = root / 'VIP_v11A_STREAMS_Test.dat'
paths = {'successful_baseline': root / 'VIP_v11A_ASSETS_v5_Test.dat',
         'below_control': root / 'Boundary_Probes/ASSETS_below_2GiB.dat',
         'failed_high_offset': root / 'Boundary_Probes/ASSETS_above_2GiB.dat',
         'successful_size_only': root / 'Boundary_Probes/ASSETS_above_2GiB_size_only.dat'}
results = {label: capacity.assess_archives(path, streams, value.hexdigest()) for label, path in paths.items()}
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--report', type=Path, default=root / 'Boundary_Probes/Record_Aware_Capacity_Results.json')
report = parser.parse_args().report
with report.open('x', encoding='utf-8') as stream:
    stream.write(json.dumps(results, indent=2) + '\n')
for label, result in results.items():
    print(json.dumps({'case': label, 'status': result['status'],
                      'passes_size_policy': result['passes_size_policy'],
                      'assets_bytes': result['assets_payload_bytes'],
                      'max_live_end_exclusive': result['assets_index']['max_live_end_exclusive'],
                      'risky_records': result['assets_index']['records_past_conservative_offset_ceiling'],
                      'streams_live_records': result['streams_index']['live_record_count']}))
expected = {'successful_baseline': True, 'below_control': True,
            'failed_high_offset': False, 'successful_size_only': True}
if any(results[label]['passes_size_policy'] != expected[label] for label in expected):
    raise SystemExit('Checker does not match the expected probe classification')
