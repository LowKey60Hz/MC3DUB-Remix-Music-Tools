#!/usr/bin/env python3
"""Phase 4B: safely add new RSM files; playlists and metadata are NOT modified."""
from pathlib import Path
import re
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

GENRES = ('Dancehall', 'Drum_N_Bass', 'Garage', 'HipHop', 'Rock', 'Techno')
# Source folder name -> original game's STREAMS/Music directory name.
GAME_GENRE = {'Garage': 'Instrumental'}
MAX_RSM_STEM_LENGTH = 37  # Garage Shop playback tested: 37 works; 38 fails.

def ident(s):
    return re.sub(r'[^A-Za-z0-9._()-]', '', s)

def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def save_history(path, entries):
    path.parent.mkdir(exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('w', encoding='utf-8') as output:
        json.dump({'version': 1, 'tracks': entries}, output, indent=2, sort_keys=True)
        output.write('\n')
    os.replace(tmp, path)


def main():
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent
    tools = root / 'supporting_tools'
    music = root / 'Custom Music'
    target = root / 'STREAMS' / 'Music'
    processor = tools / 'audio_processor.py'
    rstm = tools / 'rstm_build.py'
    if not processor.is_file():
        print(f'[ERROR] Missing Python audio processor: {processor}')
        return 1
    if not rstm.is_file():
        print(f'[ERROR] Missing RSM builder: {rstm}')
        return 1
    print(f'[OK] Python audio processor: {processor}')
    print(f'[OK] RSM builder: {rstm}')
    if not ((tools / 'ps2str.exe').is_file() or (tools / 'MFAudio.exe').is_file()):
        print('[ERROR] Missing ps2str.exe or MFAudio.exe')
        return 1
    if not target.is_dir():
        print('[ERROR] STREAMS/Music is missing. Decompile STREAMS.DAT first.')
        return 1
    history_path = root / 'support_logs' / 'music_conversion_history.json'
    if history_path.exists():
        try:
            history_data = json.loads(history_path.read_text(encoding='utf-8'))
            if history_data.get('version') != 1 or not isinstance(history_data.get('tracks'), dict):
                raise ValueError('Unsupported conversion history format')
            history = history_data['tracks']
        except (OSError, ValueError, TypeError) as exc:
            print(f'[ERROR] Cannot read conversion history: {exc}. No files changed.')
            return 1
    else:
        history = {}
    jobs, seen, errors, unchanged = [], set(), 0, 0
    print('\nADD NEW GAMEPLAY SONGS - CONVERSION ONLY')
    print('No playlist, string table, DAT archive, or ISO will be changed.')
    for genre in GENRES:
        stream_genre = GAME_GENRE.get(genre, genre)
        folder = music / ('1_The_Garage_Shop' if genre == 'Garage' else '1_' + genre)
        files = sorted((f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in ('.mp3', '.wav')),
                       key=lambda f: f.name.casefold()) if folder.is_dir() else []
        if not files:
            print(f'[SKIPPED] {genre}: no MP3/WAV files')
            continue
        print(f'[FOUND] {genre}: {len(files)} file(s)')
        if not (target / stream_genre).is_dir():
            print(f'[ERROR] Missing STREAMS/Music/{stream_genre}')
            errors += 1
            continue
        existing = {f.name.casefold() for f in (target / stream_genre).iterdir() if f.is_file()}
        for src in files:
            parts = src.stem.split('-', 1)
            if len(parts) != 2 or not all(p.strip() for p in parts) or not all(ident(p.strip()) for p in parts):
                print(f'  [ERROR] Invalid artist - title filename: {src.name}')
                errors += 1
                continue
            artist, title = (p.strip() for p in parts)
            full_stem = ident(artist) + '-' + ident(title)
            stem = full_stem[:MAX_RSM_STEM_LENGTH]
            if stem != full_stem:
                print(f'  [SHORTEN] {full_stem}.rsm -> {stem}.rsm ({MAX_RSM_STEM_LENGTH}-character limit)')
            dest = target / stream_genre / (stem + '.rsm')
            key = (stream_genre.casefold(), dest.name.casefold())
            if key in seen:
                print(f'  [ERROR] Duplicate output in input files: {src.name} -> {dest.name}')
                errors += 1
            else:
                record_key = str(src.relative_to(root)).replace('\\', '/').casefold()
                digest = file_hash(src)
                recorded = history.get(record_key)
                exists = dest.name.casefold() in existing
                if exists and not recorded:
                    # Existing RSM from before tracking: safely baseline source without overwriting.
                    history[record_key] = {'sha256': digest, 'destination': str(dest.relative_to(root)).replace('\\', '/')}
                    print(f'  [BASELINE EXISTING] {src.name} -> {dest.name} (no overwrite)')
                    unchanged += 1
                elif exists and recorded and recorded.get('sha256') == digest and recorded.get('destination', '').casefold() == str(dest.relative_to(root)).replace('\\', '/').casefold():
                    print(f'  [SKIP UNCHANGED] {src.name} -> {dest.name}')
                    unchanged += 1
                elif exists and recorded and recorded.get('destination', '').casefold() != str(dest.relative_to(root)).replace('\\', '/').casefold():
                    print(f'  [ERROR] History destination mismatch: {src.name}')
                    errors += 1
                else:
                    mode = 'UPDATE' if exists else 'ADD'
                    jobs.append((src, dest, artist, title, genre, record_key, digest, mode))
                    print(f'  [{mode}] {src.name} -> {dest.name}')
            seen.add(key)
    if errors:
        print(f'\n[STOP] {errors} input error(s). Nothing converted or modified.')
        return 1
    if not jobs:
        save_history(history_path, history)
        print(f'\nNo new or modified tracks to convert. {unchanged} unchanged/baselined.')
        return 0
    print(f'\nReady to convert {len(jobs)} new or modified RSM file(s).')
    if '--yes' not in sys.argv[2:] and input('Proceed? (Y/N), then press Enter: ').strip().upper() != 'Y':
        print('Canceled. Nothing changed.')
        return 0
    added, updated = [], []
    with tempfile.TemporaryDirectory(prefix='Music_Add_Temp_', dir=root) as tmp:
        wav = Path(tmp) / 'input.wav'
        rsm = Path(tmp) / 'output.rsm'
        for index, (src, dest, artist, title, genre, record_key, digest, mode) in enumerate(jobs, 1):
            print(f'\n[{index}/{len(jobs)}] Converting {src.name}')
            wav.unlink(missing_ok=True)
            rsm.unlink(missing_ok=True)
            converted = subprocess.run([sys.executable, str(processor), str(src), '-o', str(wav)])
            if converted.returncode or not wav.is_file():
                print('[ERROR] Python audio conversion failed. Previously added RSMs are retained.')
                return 1
            encoded = subprocess.run([sys.executable, 'rstm_build.py', str(wav), '-o', str(rsm)], cwd=tools)
            if encoded.returncode or not rsm.is_file() or rsm.stat().st_size < 2048:
                print('[ERROR] RSM encoder failed. Previously added RSMs are retained.')
                return 1
            # Complete conversion first; atomically replace the RSM only after success.
            try:
                if mode == 'ADD':
                    with dest.open('xb') as output, rsm.open('rb') as source:
                        shutil.copyfileobj(source, output)
                    added.append(dest)
                else:
                    staged = dest.with_name(dest.name + '.new')
                    try:
                        shutil.copyfile(rsm, staged)
                        os.replace(staged, dest)
                    finally:
                        staged.unlink(missing_ok=True)
                    updated.append(dest)
            except OSError as exc:
                print(f'[ERROR] Could not save {dest.name}: {exc}')
                return 1
            history[record_key] = {'sha256': digest, 'destination': str(dest.relative_to(root)).replace('\\', '/')}
            save_history(history_path, history)
            print(f'[OK] {"Replaced" if mode == "UPDATE" else "Added"} {dest.relative_to(root)}')
    save_history(history_path, history)
    print(f'\n[DONE] {len(added)} added, {len(updated)} updated, {unchanged} unchanged/baselined.')
    print('IMPORTANT: They will not be selectable in-game until playlists and mcstrings02.strtbl are updated.')
    print('Use the exact generated RSM identifier in both playlists and metadata keys.')
    print('Other registration scripts must use the same 37-character shortening rule.')
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, KeyboardInterrupt) as exc:
        print(f'\n[ERROR] {exc}')
        sys.exit(1)
