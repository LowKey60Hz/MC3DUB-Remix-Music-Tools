"""Read-only provenance checks for the proposed expansion's overwrite range."""
import hashlib
import json
import mmap
from pathlib import Path
import struct
from collections import Counter


def main():
    root = Path(__file__).resolve().parent
    plan = json.loads((root / 'V11A_Expansion_Plan.json').read_text())
    start = plan['original_archive_end_exclusive_sector'] * 2048
    end = plan['proposed_archive_end_exclusive_sector'] * 2048
    if end <= start:
        raise ValueError('No extension to characterize')
    iso = root.parent / "Base ISO's/Midnight Club 3 VIP v1.1-A.iso"
    previous = root.parent / "Base ISO's/Midnight Club 3 VIP v1.0-C.iso"
    samples = []
    digest = hashlib.sha256()
    counts = Counter()
    with iso.open('rb') as stream, previous.open('rb') as old:
        stream.seek(start)
        data = stream.read(end - start)
        old.seek(start)
        old_data = old.read(end - start)
        if len(data) != end - start or len(old_data) != len(data):
            raise ValueError('Truncated comparison')
        digest.update(data)
        counts.update(data)
        for position in (0, (len(data) // 2 // 2048) * 2048, len(data) - 2048):
            sample = data[position:position + 128]
            samples.append({'sector': (start + position) // 2048, 'hex': sample.hex(), 'matches': []})
    # A match identifies byte provenance, not whether the original disc region
    # is read by the game. Search complete source files, never change them.
    source = root.parent / 'UI Custom Gameplay Music Tools/ASSETS'
    checked = 0
    for path in source.rglob('*'):
        if not path.is_file() or path.stat().st_size < 128:
            continue
        with path.open('rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as view:
            for sample in samples:
                offset = view.find(bytes.fromhex(sample['hex']))
                if offset >= 0:
                    sample['matches'].append({'file': path.relative_to(source).as_posix(), 'offset': offset})
        checked += 1
        if checked % 2000 == 0:
            print(f'Searched {checked} asset files', flush=True)
    # Report raw executable constant occurrences as leads only. Absence does
    # not exclude computed, relative, encoded or table-driven sector accesses.
    executable = b''
    with iso.open('rb') as stream:
        layout = json.loads((root / 'Current_v11A_Layout.json').read_text())
        elf = layout['files']['/SLUS_213.55']
        stream.seek(elf['sector'] * 2048)
        executable = stream.read(elf['bytes'])
    references = {}
    for value in (928161, start // 2048, end // 2048, 2074717):
        needle = struct.pack('<I', value)
        matches, position = [], 0
        while True:
            position = executable.find(needle, position)
            if position < 0:
                break
            matches.append(position)
            position += 1
        references[str(value)] = matches
    result = {'start_sector': start // 2048, 'end_exclusive_sector': end // 2048,
              'bytes': len(data), 'sha256': digest.hexdigest(),
              'identical_to_v10c': data == old_data, 'nonzero_bytes': len(data) - counts[0],
              'source_files_searched': checked, 'samples': samples,
              'executable_raw_le32_constant_offsets': references,
              'retail_reference_geometry': {'assets_start_sector': 1369534,
                                            'assets_bytes': 1444214784,
                                            'assets_end_exclusive_sector': 1369534 + 1444214784 // 2048,
                                            'provenance': 'Existing production builder Retail USA profile, not a retail ISO comparison'},
              'conclusion': 'No runtime safety conclusion. Sample matches identify content only; constant searches are not code analysis.'}
    (root / 'Extension_Characterization.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({**{k: v for k, v in result.items() if k != 'samples'},
                      'sample_match_counts': [len(x['matches']) for x in samples]}, indent=2))


if __name__ == '__main__':
    main()
