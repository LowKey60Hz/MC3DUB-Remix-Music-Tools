"""Re-verify and finalize a completed order-test staging ISO after link denial."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import zlib

import build_two_win_skip2_test as common
from build_two_win_swapped_test import hash_extent
import MC3_ISO_Builder_Retail as builder
from MC3_ISO_Extractor import classify, inspect
from MC3_VIP_Archive_Entry_Analyzer import analyze


def decoded(path):
    entries = [e for e in analyze(path, None, 1)['all_entries'] if not e['directory_record']]
    values = {}
    with path.open('rb') as stream:
        for entry in entries:
            stream.seek(entry['data_offset'])
            stored = stream.read(entry['stored_size'])
            raw = zlib.decompress(stored, -15) if entry['compressed'] else stored
            if len(raw) != entry['full_size']:
                raise ValueError('Decoded size mismatch')
            digest = hashlib.sha256(raw).hexdigest()
            if entry['name'] in values and values[entry['name']][0] != digest:
                raise ValueError('Conflicting duplicate ASSETS records')
            values[entry['name']] = (digest, raw if entry['name'].endswith('_raceover_music.play') else None)
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test-dir', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    source = args.test_dir.resolve(strict=True)
    output = args.output_dir.resolve(strict=True)
    if output == source or output.is_relative_to(source) or output.is_relative_to(common.PROJECT.resolve()):
        raise ValueError('Unsafe output folder')
    image = output/'MC3_Retail_Two_Win_SWAPPED_REVERSED.iso'
    staging = image.with_name(image.name+'.building.tmp')
    report = output/'order_result.json'
    if image.exists() or report.exists() or not staging.is_file():
        raise ValueError('Requires an unfinalized staging image and no existing output/report')
    swapped = json.loads((source/'swapped_result.json').read_text())
    swapped_iso = source/'MC3_Retail_Two_Win_1_and_3_SWAPPED.iso'
    print('Authenticating swapped control and original Retail ISO...', flush=True)
    if common.digest(swapped_iso) != swapped['iso_sha256']:
        raise ValueError('Swapped control hash mismatch')
    workspace = output/'ISO_FILES'
    original_iso = Path((workspace/'MC3_SOURCE_ISO.txt').read_text().strip())
    if classify(original_iso)[0] != 'VERIFIED_RETAIL_REFERENCE':
        raise ValueError('Unverified Retail source')
    with swapped_iso.open('rb') as stream:
        layout = inspect(stream)
        for name, local in [('STREAMS.DAT', workspace/'STREAMS.DAT'),
                            ('ASSETS.DAT', workspace/'ASSETS_SWAPPED_REFERENCE.dat')]:
            sector, size = layout[name]
            if local.stat().st_size != size or common.digest(local) != hash_extent(stream, sector*2048, size):
                raise ValueError('Local archive differs from swapped control: '+name)
    print('Verifying all decoded ASSETS changes...', flush=True)
    before = decoded(workspace/'ASSETS_SWAPPED_REFERENCE.dat')
    after = decoded(workspace/'ASSETS.DAT')
    if before.keys() != after.keys():
        raise ValueError('ASSETS file set changed')
    changed = [name for name in before if before[name][0] != after[name][0]]
    expected = [name for name in before if Path(name).match('tune/audio/playlist/city/*/music/*_raceover_music.play')]
    if len(expected) != 24 or set(changed) != set(expected):
        raise ValueError('Changes are not exactly the 24 Win playlists')
    for name in expected:
        old, new = before[name][1], after[name][1]
        if old.decode('utf-8-sig').splitlines() != ['num_songs: 2', r'music\Win_Lose\win1', r'music\Win_Lose\win3']:
            raise ValueError('Unexpected control playlist')
        lines = old.decode('utf-8-sig').splitlines(keepends=True)
        wanted = (b'\xef\xbb\xbf' if old.startswith(b'\xef\xbb\xbf') else b'') + ''.join([lines[0], lines[2], lines[1]]).encode()
        if new != wanted:
            raise ValueError('Playlist change exceeds reversal: '+name)
    print('Re-verifying staging ISO layout, archives and all protected bytes...', flush=True)
    archives = builder.PROFILES['Retail USA']['archives']
    with original_iso.open('rb') as stream:
        _, root_size = builder.inspect_base(stream, archives)
    rows = builder.plan(common.PROJECT, archives, workspace, relocate_archives=True)
    builder.verify(original_iso, staging, rows, root_size)
    package = builder.check_manifest_preflight(original_iso, rows, workspace/'STREAMS.LST')
    with staging.open('rb') as stream:
        stream.seek(builder.MANIFEST_SECTOR*2048)
        if stream.read(len(package)) != package:
            raise ValueError('Manifest readback mismatch')
        if any(stream.read(builder.MANIFEST_CAPACITY-len(package))):
            raise ValueError('Unexpected manifest-region tail')
    production_hash = common.digest(common.TOOLS/'sync_winlose_folders.py')
    if production_hash != '31d8a9dcfb253d744bf7af0c8c9710e2e869e7d63aa44e212d689f5584de5751':
        raise ValueError('Production engine differs from preflight')
    result = dict(iso=str(image), iso_sha256=common.digest(staging),
                  source_iso=str(swapped_iso), source_sha256=swapped['iso_sha256'], mapping=swapped['mapping'],
                  num_songs=2, playlist_entries=[r'music\Win_Lose\win3', r'music\Win_Lose\win1'],
                  win_playlist_count=24, changed_decoded_assets=sorted(changed),
                  all_other_decoded_assets_unchanged=True, streams_identical_to_swapped=True,
                  streams_sha256=common.digest(workspace/'STREAMS.DAT'),
                  compiled_assets_verified=True, iso_protected_bytes_verified=True,
                  source_and_active_workspaces_not_written=True, production_engine_unchanged=True,
                  production_engine_sha256=production_hash, runtime_status='NOT TESTED')
    os.link(staging, image)
    staging.unlink()
    with report.open('x', encoding='utf-8') as saved:
        saved.write(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
