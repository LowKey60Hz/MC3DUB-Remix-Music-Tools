"""Read-only source/layout/budget verification for the three supported originals."""
import hashlib
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root.parent / 'UI Custom Gameplay Music Tools/supporting_tools'))
import vip_capacity as capacity
import MC3_ISO_Builder_VIP as vip
import MC3_ISO_Builder_Retail as retail
from MC3_ISO_Builder_V11A import INFO

references = {
    'vip': ('Midnight Club 3 VIP v1.0-C.iso', vip, vip.PROFILES['VIP Expansion']['archives']),
    'vip-v11a': ('Midnight Club 3 VIP v1.1-A.iso', vip, INFO),
    'retail': ('Midnight Club 3 - DUB Edition Remix (USA).iso', retail, retail.PROFILES['Retail USA']['archives']),
}
results = {}
for profile, (filename, engine, archives) in references.items():
    source = root.parent / "Base ISO's" / filename
    print('Verifying ' + capacity.CAPACITY_PROFILES[profile]['label'] + ' original...', flush=True)
    value = hashlib.sha256()
    with source.open('rb') as stream:
        for data in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            value.update(data)
    if value.hexdigest() != capacity.CAPACITY_PROFILES[profile]['sha256']:
        raise ValueError('Original source fingerprint mismatch: ' + filename)
    with source.open('rb') as stream:
        records, root_size = engine.inspect_base(stream, archives)
        directory = engine.read_exact(stream, 261 * 2048, root_size)
        elf_record = records.get('SLUS_213.55;1')
        elf_sha = None
        if elf_record is not None:
            sector = engine.u32(directory, elf_record + 2)
            length = engine.u32(directory, elf_record + 10)
            elf_sha = engine.hash_region(stream, sector * 2048, length)
    sizes = {row[0]: row[2] for row in archives}
    report = capacity.assess(sizes['ASSETS.DAT'], sizes['STREAMS.DAT'], value.hexdigest(), layout_profile=profile)
    results[profile] = dict(source=str(source), sha256=value.hexdigest(), source_layout_verified=True,
                            executable_sha256=elf_sha, capacity=report)
    print(json.dumps({'profile':profile, 'shared_budget_bytes':report['shared_layout_capacity_bytes'],
                      'original_unused_budget_bytes':report['remaining_bytes'], 'source_layout_verified':True}), flush=True)
path = root / 'All_Profile_Capacity_Verification.json'
with path.open('x', encoding='utf-8') as stream:
    stream.write(json.dumps(results, indent=2) + '\n')
print('All three source hashes and layouts verified; no ISOs or workspaces changed.', flush=True)
