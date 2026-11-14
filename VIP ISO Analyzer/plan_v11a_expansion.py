"""Calculate a VIP v1.1-A expansion proposal. Never create or modify an ISO."""
import importlib.util
import json
from pathlib import Path
import struct

SECTOR = 2048


def align(size):
    return (size + SECTOR - 1) // SECTOR * SECTOR


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def streams_projection(folder, hash_module):
    """Mirror hash_build's name order, collision checks and sector padding, without payload writes."""
    calc_hash = hash_module.get_hash_func('mclub')
    records, hashes = [], {}
    for path in folder.rglob('*'):
        if not path.is_file():
            continue
        if path.is_symlink():
            raise ValueError('Source symlink requires explicit review')
        name = path.relative_to(folder).as_posix()
        if any(part.startswith('.') for part in path.relative_to(folder).parts):
            # glob.iglob in hash_build does not include hidden dot paths.
            continue
        hashed = name.startswith(hash_module.HASHED)
        value = int(path.stem, 16) if hashed else calc_hash(name.strip())
        if not 0 <= value <= 0xffffffff or value in hashes:
            raise ValueError(f'Invalid or duplicate STREAMS hash: {name}')
        hashes[value] = name
        records.append((name, path.stat().st_size, hashed))
    if not records:
        raise ValueError('No STREAMS source files')
    records.sort(key=lambda item: item[0].upper())
    position = 8 + len(records) * 12
    for name, size, _ in records:
        position = align(position)
        if position > 0xffffffff or size > 0xffffffff:
            raise ValueError(f'STREAMS 32-bit field overflow: {name}')
        position += size
    return {'files': len(records), 'projected_bytes': align(position),
            'payload_bytes': sum(x[1] for x in records),
            'manifest_names': sum(not x[2] for x in records),
            'note': 'Size projection only; payload identity and playback are not verified.'}


def main():
    root = Path(__file__).resolve().parent
    project = root.parent / 'UI Custom Gameplay Music Tools'
    iso = root.parent / "Base ISO's/Midnight Club 3 VIP v1.1-A.iso"
    old_iso = root.parent / "Base ISO's/Midnight Club 3 VIP v1.0-C.iso"
    scanner = load_module('mc3_scan', root / 'MC3_VIP_ISO_Analyzer_v0_2.py')
    current = scanner.scan_iso(iso, False)
    if current['warnings'] or not current['iso9660']['detected']:
        raise ValueError('Incomplete ISO9660 scan')
    udf = load_module('mc3_udf', root / 'map_udf_allocations.py').scan(iso)
    projection = streams_projection(project / 'STREAMS', load_module('mc3_hash', project / 'supporting_tools/hash_build.py'))
    validation = json.loads((root / 'V5_Active_GUI_Validation.json').read_text())
    assets = root / 'VIP_v11A_ASSETS_v5_Test.dat'
    if not validation['passed'] or validation['bytes'] != assets.stat().st_size:
        raise ValueError('Missing successful v5 validation snapshot')
    names = ('TEXTURE.DAT', 'STREAMS.DAT', 'BANKS.DAT', 'ASSETS.DAT')
    original = current['files']
    first = original['/TEXTURE.DAT']['sector']
    original_end = original['/ASSETS.DAT']['sector'] + align(original['/ASSETS.DAT']['bytes']) // SECTOR
    sizes = {name: original['/' + name]['bytes'] for name in names}
    sizes['STREAMS.DAT'] = projection['projected_bytes']
    sizes['ASSETS.DAT'] = assets.stat().st_size
    position, rows = first, []
    for name in names:
        stop = position + align(sizes[name]) // SECTOR
        rows.append({'name': name, 'start_sector': position, 'end_exclusive_sector': stop,
                     'payload_bytes': sizes[name], 'allocated_bytes': align(sizes[name]),
                     'original_start_sector': original['/' + name]['sector']})
        position = stop
    overlaps = []
    # Exclude original archive locations: the proposal replaces/relocates those archives.
    for entry in udf['files'] + udf['directories']:
        if entry['path'].upper() in {'/' + name for name in names}:
            continue
        for extent in entry['extents']:
            lo = extent['sector']
            hi = lo + align(extent['bytes']) // SECTOR
            for row in rows:
                if row['start_sector'] < hi and row['end_exclusive_sector'] > lo:
                    overlaps.append({'archive': row['name'], 'protected_file': entry['path']})
    layer = json.loads((root / 'Layer2_And_Region_Diagnostic.json').read_text())
    with iso.open('rb') as stream:
        for video in layer['files']:
            lo = video['physical_sector']
            hi = lo + align(video['bytes']) // SECTOR
            stream.seek(lo * SECTOR)
            if stream.read(4) != bytes.fromhex('000001ba'):
                raise ValueError('Cinematic signature changed')
            for row in rows:
                if row['start_sector'] < hi and row['end_exclusive_sector'] > lo:
                    overlaps.append({'archive': row['name'], 'protected_file': video['path']})
        manifest_start, manifest_size = 2074717, 1048576
        stream.seek(manifest_start * SECTOR)
        manifest = stream.read(manifest_size)
        if len(manifest) != manifest_size:
            raise ValueError('Truncated manifest region')
    # Compare the unexplained region against the older reference: equality can
    # identify carried-over bytes, but cannot establish permission to reuse them.
    compared, different_chunks = 0, 0
    with iso.open('rb') as new, old_iso.open('rb') as old:
        new.seek(original_end * SECTOR)
        old.seek(original_end * SECTOR)
        remaining = (manifest_start - original_end) * SECTOR
        while remaining:
            count = min(8 * 1024 * 1024, remaining)
            a, b = new.read(count), old.read(count)
            if len(a) != count or len(b) != count:
                raise ValueError('Truncated comparison input')
            different_chunks += a != b
            compared += count
            remaining -= count
    overrun = max(0, position - original_end) * SECTOR
    blockers = []
    if overrun:
        blockers.append('Proposal extends into unidentified nonzero data beyond the original ASSETS allocation.')
    if overlaps:
        blockers.append('Proposal overlaps mapped protected allocations.')
    if position > layer['base_sector']:
        blockers.append('Proposal crosses the second-layer boundary.')
    if position > manifest_start:
        blockers.append('Proposal reaches the legacy manifest reservation.')
    if any(manifest):
        blockers.append('Legacy 1 MiB manifest reservation is nonzero in v1.1-A; existing manifest writer would reject it.')
    blockers.append('Production builder has no v1.1-A expansion profile; relocation and UDF extent encoding require implementation and game testing.')
    result = {'mode': 'PROPOSAL ONLY — NOT APPROVED FOR WRITING',
              'streams': projection, 'assets_bytes': sizes['ASSETS.DAT'],
              'original_archive_end_exclusive_sector': original_end,
              'proposed_archive_end_exclusive_sector': position,
              'extra_bytes_beyond_original_archive_region': overrun,
              'remaining_bytes_inside_original_region': max(0, original_end - position) * SECTOR,
              'proposed_layout': rows, 'protected_allocation_overlaps': overlaps,
              'cinematics_checked': len(layer['files']),
              'legacy_manifest_region_all_zero': not any(manifest),
              'post_assets_comparison': {'bytes': compared, 'different_chunks': different_chunks,
                                         'all_equal_to_v10c': different_chunks == 0,
                                         'note': 'Equality is provenance evidence, not proof of free space.'},
              'udf_warnings': udf['warnings'], 'blockers': blockers,
              'validation_limit': 'Uses prior v5 content validation snapshot; no ISO hash, new archive build, or PCSX2 test performed.'}
    (root / 'V11A_Expansion_Plan.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
