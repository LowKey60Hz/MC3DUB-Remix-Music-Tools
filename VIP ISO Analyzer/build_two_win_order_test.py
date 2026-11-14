"""Build an isolated playlist-order comparison from a verified local swapped test."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zlib

import build_two_win_skip2_test as baseline
from MC3_VIP_Archive_Entry_Analyzer import analyze
from MC3_ISO_Extractor import inspect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test-dir', type=Path, required=True, help='Completed baseline/swapped test folder')
    parser.add_argument('--output-dir', type=Path, required=True, help='Fresh separate output folder')
    args = parser.parse_args()
    source = args.test_dir.resolve(strict=True)
    output = args.output_dir.resolve()
    project = baseline.PROJECT.resolve()
    if (output == source or output.is_relative_to(source) or source.is_relative_to(output)
            or output == project or output.is_relative_to(project)):
        raise ValueError('Output must be separate from source and active project')
    if output.exists():
        raise FileExistsError('Refusing to overwrite an order test')
    original = json.loads((source/'result.json').read_text())
    swapped = json.loads((source/'swapped_result.json').read_text())
    image = source/'MC3_Retail_Two_Win_1_and_3_SWAPPED.iso'
    if original['playlist_entries'] != [r'music\Win_Lose\win1', r'music\Win_Lose\win3']:
        raise ValueError('Unexpected baseline playlist order')
    if swapped['source_sha256'] != original['iso_sha256'] or not swapped['playlists_unchanged']:
        raise ValueError('Swapped report provenance mismatch')
    print('Authenticating swapped ISO...', flush=True)
    if baseline.digest(image) != swapped['iso_sha256']:
        raise ValueError('Swapped ISO fingerprint mismatch')
    if shutil.disk_usage(source).free < image.stat().st_size + 4*sum(
            p.stat().st_size for p in (source/'ASSETS').rglob('*') if p.is_file()) + 2*1024**3:
        raise ValueError('Insufficient free space for isolated order comparison')
    production = baseline.digest(baseline.TOOLS/'sync_winlose_folders.py')
    print('Recording source and active workspace hashes...', flush=True)
    active_before = baseline.snapshot(project)
    source_before = baseline.snapshot(source)
    # Authenticate source ASSETS against every decoded record in the swapped ISO.
    with image.open('rb') as stream:
        layout = inspect(stream)
    output.mkdir()
    baseline.TEST = output
    workspace = output/'ISO_FILES'
    workspace.mkdir()
    print('Extracting authenticated swapped archives...', flush=True)
    with image.open('rb') as stream:
        for name in ('ASSETS.DAT', 'STREAMS.DAT'):
            sector, size = layout[name]
            stream.seek(sector*2048)
            with (workspace/name).open('xb') as saved:
                remaining = size
                while remaining:
                    block = stream.read(min(8*1024**2, remaining))
                    if not block:
                        raise ValueError('Truncated swapped archive')
                    saved.write(block)
                    remaining -= len(block)
    original_assets = workspace/'ASSETS.DAT'
    records = analyze(original_assets, None, 1)['all_entries']
    print('Comparing every decoded ASSETS record with the baseline workspace...', flush=True)
    files = [e for e in records if not e['directory_record']]
    expected_names = {k.removeprefix('ASSETS/') for k in source_before if k.startswith('ASSETS/')}
    if {e['name'] for e in files} != expected_names:
        raise ValueError('Source ASSETS file set differs from swapped image')
    with original_assets.open('rb') as stream:
        for entry in files:
            stream.seek(entry['data_offset'])
            stored = stream.read(entry['stored_size'])
            raw = zlib.decompress(stored, -15) if entry['compressed'] else stored
            if len(raw) != entry['full_size'] or hashlib.sha256(raw).hexdigest() != source_before['ASSETS/'+entry['name']]:
                raise ValueError('Source ASSETS differs from swapped ISO: '+entry['name'])
    original_assets.rename(workspace/'ASSETS_SWAPPED_REFERENCE.dat')
    print('Copying ASSETS and reversing only the 24 Win playlists...', flush=True)
    shutil.copytree(source/'ASSETS', output/'ASSETS')
    order = [r'music\Win_Lose\win3', r'music\Win_Lose\win1']
    playlists = sorted((output/'ASSETS/tune/audio/playlist').glob('city/*/music/*_raceover_music.play'))
    if len(playlists) != 24:
        raise ValueError('Expected 24 Win playlists')
    for path in playlists:
        raw = path.read_bytes()
        lines = raw.decode('utf-8-sig').splitlines()
        if lines != ['num_songs: 2'] + original['playlist_entries']:
            raise ValueError('Unexpected baseline playlist: '+str(path))
        newline = '\r\n' if b'\r\n' in raw else '\n'
        path.write_bytes((b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b'')
                         + (newline.join(['num_songs: 2']+order)+newline).encode())
    after = baseline.snapshot(output)
    print('Verifying that only the 24 playlist files changed...', flush=True)
    changed = {k for k in source_before if k.startswith('ASSETS/') and source_before[k] != after.get(k)}
    if changed != {p.relative_to(output).as_posix() for p in playlists}:
        raise ValueError('Unexpected decoded ASSETS changes')
    shutil.copy2(source/'ISO_FILES/STREAMS.LST', workspace/'STREAMS.LST')
    for path in (source/'ISO_FILES').glob('MC3_*.txt'):
        shutil.copy2(path, workspace/path.name)
    tools = baseline.TOOLS
    log = output/'build.log'
    baseline.run([sys.executable, '-u', str(tools/'dave.py'), 'B', '-ca', '-cn', '-cf', '-fc', '1',
                  str(output/'ASSETS'), str(workspace/'ASSETS.DAT')], log)
    built = [e for e in analyze(workspace/'ASSETS.DAT', None, 1)['all_entries'] if not e['directory_record']]
    print('Verifying every compiled ASSETS record...', flush=True)
    if {e['name'] for e in built} != expected_names:
        raise ValueError('Compiled ASSETS names mismatch')
    with (workspace/'ASSETS.DAT').open('rb') as stream:
        for entry in built:
            stream.seek(entry['data_offset'])
            stored = stream.read(entry['stored_size'])
            raw = zlib.decompress(stored, -15) if entry['compressed'] else stored
            if len(raw) != entry['full_size'] or hashlib.sha256(raw).hexdigest() != after['ASSETS/'+entry['name']]:
                raise ValueError('Compiled ASSETS mismatch: '+entry['name'])
    # The reference copy is evidence, not a builder replacement.
    base_iso = Path((workspace/'MC3_SOURCE_ISO.txt').read_text().strip())
    result_image = output/'MC3_Retail_Two_Win_SWAPPED_REVERSED.iso'
    baseline.run([sys.executable, '-u', str(tools/'MC3_ISO_Builder_Retail.py'), '--profile', 'retail',
                  '--relocate-archives', '--source', str(base_iso), '--replacement-dir', str(workspace),
                  '--manifest', str(workspace/'STREAMS.LST'), '--output', str(result_image), '--yes'], log)
    streams_hash = baseline.digest(workspace/'STREAMS.DAT')
    with result_image.open('rb') as stream:
        sector, size = inspect(stream)['STREAMS.DAT']
        from build_two_win_swapped_test import hash_extent
        if size != (workspace/'STREAMS.DAT').stat().st_size or hash_extent(stream, sector*2048, size) != streams_hash:
            raise ValueError('Output STREAMS differs from swapped image')
    print('Checking source workspace and production preservation...', flush=True)
    if baseline.snapshot(source) != source_before or baseline.snapshot(project) != active_before:
        raise ValueError('Source or active workspace changed')
    if baseline.digest(baseline.TOOLS/'sync_winlose_folders.py') != production:
        raise ValueError('Production engine changed')
    report = dict(iso=str(result_image), iso_sha256=baseline.digest(result_image),
                  source_iso=str(image), source_sha256=swapped['iso_sha256'], mapping=swapped['mapping'],
                  num_songs=2, playlist_entries=order, win_playlist_count=24,
                  changed_decoded_assets=sorted(changed), all_other_decoded_assets_unchanged=True,
                  streams_identical_to_swapped=True, streams_sha256=streams_hash,
                  source_and_active_workspaces_unchanged=True, production_engine_unchanged=True,
                  compiled_assets_verified=True, runtime_status='NOT TESTED')
    (output/'order_result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
