"""Isolated ABA/ABB Win playlist tests; retain the authenticated swapped audio."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
import zlib

import build_two_win_skip2_test as common
from build_two_win_swapped_test import hash_extent
from MC3_ISO_Extractor import inspect
from MC3_VIP_Archive_Entry_Analyzer import analyze

CHUNK = 8*1024**2
A = r'music\Win_Lose\win1'
B = r'music\Win_Lose\win3'


def contents(path):
    result = {}
    entries = analyze(path, None, 1)['all_entries']
    with path.open('rb') as stream:
        for entry in entries:
            if entry['directory_record']:
                continue
            stream.seek(entry['data_offset'])
            stored = stream.read(entry['stored_size'])
            raw = zlib.decompress(stored, -15) if entry['compressed'] else stored
            if len(raw) != entry['full_size']:
                raise ValueError('Invalid decoded size')
            result[entry['index']] = (entry['name'], hashlib.sha256(raw).hexdigest(),
                                     raw if entry['name'].endswith('_raceover_music.play') else None)
    return entries, result


def playlist(raw, entries):
    newline = '\r\n' if b'\r\n' in raw else '\n'
    bom = b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b''
    return bom + (newline.join(['num_songs: 3']+entries)+newline).encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test-dir', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    source = args.test_dir.resolve(strict=True)
    output = args.output_dir.resolve()
    project = common.PROJECT.resolve()
    if (output == source or output.is_relative_to(source) or source.is_relative_to(output)
            or output == project or output.is_relative_to(project)):
        raise ValueError('Output must be separate from source and production')
    if output.exists():
        raise FileExistsError('Refusing to overwrite prior three-entry evidence')
    if shutil.disk_usage(source).free < 28*1024**3:
        raise ValueError('Need at least 28 GiB free')
    report = json.loads((source/'swapped_result.json').read_text())
    image = source/'MC3_Retail_Two_Win_1_and_3_SWAPPED.iso'
    print('Authenticating swapped control...', flush=True)
    if common.digest(image) != report['iso_sha256']:
        raise ValueError('Swapped control fingerprint mismatch')
    if report['playlist_entries'] != [A, B] or report['num_songs'] != 2:
        raise ValueError('Unexpected control playlist')
    production = common.digest(common.TOOLS/'sync_winlose_folders.py')
    if production != '31d8a9dcfb253d744bf7af0c8c9710e2e869e7d63aa44e212d689f5584de5751':
        raise ValueError('Production differs from investigation baseline')
    output.mkdir()
    reference = output/'reference'
    reference.mkdir()
    with image.open('rb') as stream:
        layout = inspect(stream)
        for name in ('ASSETS.DAT', 'STREAMS.DAT'):
            sector, size = layout[name]
            stream.seek(sector*2048)
            with (reference/name).open('xb') as saved:
                remaining = size
                while remaining:
                    block = stream.read(min(CHUNK, remaining))
                    if not block:
                        raise ValueError('Truncated source ISO')
                    saved.write(block)
                    remaining -= len(block)
    print('Checking compiler round-trip of repeated playlist references...', flush=True)
    probe = output/'compiler_probe'
    probe.mkdir()
    samples = {'aba.play': playlist(b'\n', [A, B, A]), 'abb.play': playlist(b'\n', [A, B, B])}
    for name, raw in samples.items():
        (probe/name).write_bytes(raw)
    common.TEST = output
    common.run([sys.executable, '-u', str(common.TOOLS/'dave.py'), 'B', '-ca', '-cn', '-cf', '-fc', '1',
                str(probe), str(output/'compiler_probe.dat')], output/'compiler_probe.log')
    probe_entries = analyze(output/'compiler_probe.dat', None, 1)['all_entries']
    with (output/'compiler_probe.dat').open('rb') as stream:
        found = set()
        for entry in probe_entries:
            if entry['directory_record']:
                continue
            stream.seek(entry['data_offset'])
            stored = stream.read(entry['stored_size'])
            raw = zlib.decompress(stored, -15) if entry['compressed'] else stored
            if raw != samples[entry['name']]:
                raise ValueError('Compiler altered repeated references')
            found.add(entry['name'])
        if found != set(samples):
            raise ValueError('Compiler probe file-set mismatch')
    print('Compiler preserves ABA and ABB exactly.', flush=True)
    entries, before = contents(reference/'ASSETS.DAT')
    targets = [e for e in entries if not e['directory_record'] and
               Path(e['name']).match('tune/audio/playlist/city/*/music/*_raceover_music.play')]
    if len(targets) != 24 or len({e['name'] for e in targets}) != 24:
        raise ValueError('Expected exactly 24 distinct Win playlists')
    for entry in targets:
        if before[entry['index']][2].decode('utf-8-sig').splitlines() != ['num_songs: 2', A, B]:
            raise ValueError('Unexpected source Win playlist')
    streams_hash = common.digest(reference/'STREAMS.DAT')
    summaries = []
    for label, order in [('ABA', [A, B, A]), ('ABB', [A, B, B])]:
        print('Preparing '+label+' with all other archive bytes preserved...', flush=True)
        folder = output/label
        folder.mkdir()
        workspace = folder/'ISO_FILES'
        workspace.mkdir()
        assets = workspace/'ASSETS.DAT'
        shutil.copyfile(reference/'ASSETS.DAT', assets)
        # Append explicit uncompressed payloads; change only each target record's
        # offset/full-size/stored-size fields. Preserve all old payload bytes.
        patches = []
        appended = bytearray()
        original_size = assets.stat().st_size
        for entry in targets:
            raw = playlist(before[entry['index']][2], order)
            patches.append((0x800+entry['index']*16+4,
                            struct.pack('<III', original_size+len(appended), len(raw), len(raw))))
            appended.extend(raw)
        appended.extend(b'\0'*(-(original_size+len(appended)) % 2048))
        with assets.open('r+b') as stream:
            stream.seek(0, 2)
            stream.write(appended)
            for offset, raw in patches:
                stream.seek(offset)
                stream.write(raw)
        # Authenticate every byte, including unused original payloads and padding.
        with (reference/'ASSETS.DAT').open('rb') as control, assets.open('rb') as changed:
            position = 0
            while block := control.read(CHUNK):
                wanted = bytearray(block)
                for offset, raw in patches:
                    low, high = max(position, offset), min(position+len(block), offset+len(raw))
                    if low < high:
                        wanted[low-position:high-position] = raw[low-offset:high-offset]
                if changed.read(len(block)) != wanted:
                    raise ValueError('Unexpected binary ASSETS difference')
                position += len(block)
            if changed.read() != appended:
                raise ValueError('Appended payload mismatch')
        rebuilt_entries, after = contents(assets)
        if len(rebuilt_entries) != len(entries) or after.keys() != before.keys():
            raise ValueError('Archive record set changed')
        wanted_indices = {e['index'] for e in targets}
        for index, previous in before.items():
            if index in wanted_indices:
                raw = playlist(previous[2], order)
                if after[index] != (previous[0], hashlib.sha256(raw).hexdigest(), raw):
                    raise ValueError('Three-entry payload mismatch')
            elif after[index] != previous:
                raise ValueError('Unrelated decoded ASSETS changed')
        shutil.copyfile(reference/'STREAMS.DAT', workspace/'STREAMS.DAT')
        if common.digest(workspace/'STREAMS.DAT') != streams_hash:
            raise ValueError('STREAMS copy differs from authenticated control')
        shutil.copyfile(source/'ISO_FILES/STREAMS.LST', workspace/'STREAMS.LST')
        original_iso = Path((source/'ISO_FILES/MC3_SOURCE_ISO.txt').read_text().strip())
        result_image = folder/('MC3_Retail_Three_Win_'+label+'.iso')
        common.TEST = folder
        common.run([sys.executable, '-u', str(common.TOOLS/'MC3_ISO_Builder_Retail.py'),
                    '--profile', 'retail', '--relocate-archives', '--source', str(original_iso),
                    '--replacement-dir', str(workspace), '--manifest', str(workspace/'STREAMS.LST'),
                    '--output', str(result_image), '--yes'], folder/'build.log')
        with result_image.open('rb') as stream:
            result_layout = inspect(stream)
            for name in ('STREAMS.DAT', 'ASSETS.DAT'):
                sector, size = result_layout[name]
                local = workspace/name
                if size != local.stat().st_size or hash_extent(stream, sector*2048, size) != common.digest(local):
                    raise ValueError('Output archive mismatch: '+name)
        if common.digest(common.TOOLS/'sync_winlose_folders.py') != production:
            raise ValueError('Production engine changed')
        result = dict(iso=str(result_image), iso_sha256=common.digest(result_image),
                      source_iso=str(image), source_sha256=report['iso_sha256'],
                      mapping=report['mapping'], pattern=label, num_songs=3, playlist_entries=order,
                      win_playlist_count=24, compiler_preserves_duplicate_references=True,
                      all_other_decoded_assets_unchanged=True, lose_unchanged=True,
                      streams_identical_to_swapped=True, streams_sha256=streams_hash,
                      archive_method='Append uncompressed playlists; patch only 24 existing record offset/size triples',
                      all_other_original_assets_bytes_preserved=True, every_decoded_record_verified=True,
                      iso_archives_and_protected_bytes_verified=True, production_engine_unchanged=True,
                      production_engine_sha256=production, source_and_active_workspaces_not_written=True,
                      runtime_status='NOT TESTED')
        (folder/'result.json').write_text(json.dumps(result, indent=2)+'\n')
        summaries.append(result)
        print(label+' verified: '+result['iso_sha256'], flush=True)
    if common.digest(image) != report['iso_sha256']:
        raise ValueError('Source control changed during build')
    (output/'comparison_results.json').write_text(json.dumps(summaries, indent=2)+'\n')
    print('Both three-entry comparison images are verified. Runtime testing remains.', flush=True)


if __name__ == '__main__':
    main()
