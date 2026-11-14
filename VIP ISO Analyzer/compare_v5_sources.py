"""Compare the v5 mismatch paths against research and active GUI sources."""
import hashlib
import json
from pathlib import Path
import struct
import zlib

root = Path(__file__).resolve().parent
prior = json.loads((root / 'V5_Independent_Validation.json').read_text())
names = set(prior['source_mismatches'])
entries = json.loads((root / 'VIP_v11A_Archive_Entry_Report.json').read_text())['all_entries']
folders = {'research': root / 'VIP_v11A_ASSETS_Decompiled',
           'active_gui': root.parent / 'UI Custom Gameplay Music Tools/ASSETS',
           'v4_extracted': root / 'VIP_v11A_ASSETS_Optimized_v4_Extracted'}
results = []
seen = set()
with (root / 'VIP_v11A_ASSETS_v5_Test.dat').open('rb') as archive:
    for entry in entries:
        name = entry['name']
        if entry['directory_record'] or name not in names or name in seen:
            continue
        seen.add(name)
        archive.seek(0x800 + entry['index'] * 16 + 4)
        offset, full, stored = struct.unpack('<III', archive.read(12))
        archive.seek(offset)
        payload = archive.read(stored)
        raw = zlib.decompress(payload, -15) if stored < full else payload
        digest = hashlib.sha256(raw).hexdigest()
        item = {'name': name, 'v5_bytes': full, 'v5_sha256': digest, 'sources': {}}
        for label, folder in folders.items():
            path = folder.joinpath(*name.split('/')).resolve()
            if not path.is_relative_to(folder.resolve()):
                raise ValueError('Unsafe source name')
            if path.is_file():
                data = path.read_bytes()
                sha = hashlib.sha256(data).hexdigest()
                item['sources'][label] = {'bytes': len(data), 'sha256': sha, 'matches_v5': sha == digest}
            else:
                item['sources'][label] = {'missing': True}
        results.append(item)
summary = {label: {'matching_v5': sum(x['sources'][label].get('matches_v5', False) for x in results),
                   'missing': sum(x['sources'][label].get('missing', False) for x in results)}
           for label in folders}
output = {'unique_paths': len(results), 'summary': summary, 'files': results}
(root / 'V5_Source_Reconciliation.json').write_text(json.dumps(output, indent=2) + '\n')
print(json.dumps({'unique_paths': len(results), 'summary': summary}, indent=2))
expected = {e['name'].lower() for e in entries if not e['directory_record']}
active = folders['active_gui']
actual = {p.relative_to(active).as_posix().lower() for p in active.rglob('*') if p.is_file()}
coverage = {'unique_archive_paths': len(expected), 'active_source_files': len(actual),
            'extra_files': sorted(actual - expected), 'missing_files': sorted(expected - actual)}
(root / 'V5_Source_Coverage.json').write_text(json.dumps(coverage, indent=2) + '\n')
print(json.dumps(coverage, indent=2))
