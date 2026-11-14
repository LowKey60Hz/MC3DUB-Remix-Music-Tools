#!/usr/bin/env python3
"""Install one title theme song and synchronize all four frontend playlists."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

CITIES = ('atlanta', 'detroit', 'sd', 'tokyo')
ORIGINAL = r'music\HipHop\MFresh_FrontEnd'
MAX_STEM = 37

def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def identifier(text):
    return re.sub(r'[^A-Za-z0-9._()-]', '', text)

def parse_playlist(raw, path):
    try:
        value = raw.decode('ascii')
    except UnicodeDecodeError:
        raise ValueError(f'{path}: playlist is not ASCII')
    lines = value.splitlines()
    if len(lines) < 2 or lines[0].strip() != 'num_songs: 1':
        raise ValueError(f'{path}: expected a one-song frontend playlist')
    ref = lines[1].strip()
    if not re.fullmatch(r'music\\[A-Za-z0-9_() .-]+\\[A-Za-z0-9_().-]+', ref, re.I):
        raise ValueError(f'{path}: invalid song reference: {ref!r}')
    return ref

def playlist_bytes(old, ref):
    # Preserve newline convention, trailing empty lines, and other playlist content.
    newline = b'\r\n' if b'\r\n' in old else b'\n'
    parts = old.split(newline)
    parts[1] = ref.encode('ascii')
    return newline.join(parts)

def safe_write(path, content):
    tmp = path.with_name(path.name + '.theme-new')
    try:
        tmp.write_bytes(content)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)

def main():
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
    sources = root / 'Custom Music' / '3_Theme Song'
    if not sources.is_dir():
        print('[SKIP TITLE THEME] 3_Theme Song folder does not exist.')
        return 0
    songs = sorted((p for p in sources.iterdir() if p.is_file() and p.suffix.lower() in ('.mp3', '.wav')),
                   key=lambda p: p.name.casefold())
    if not songs:
        print('[SKIP TITLE THEME] No MP3/WAV file in 3_Theme Song.')
        return 0
    if len(songs) != 1:
        print('[ERROR] 3_Theme Song must contain exactly one MP3 or WAV. Nothing changed.')
        return 1
    source = songs[0]
    # The frontend does not display artist/title metadata. Preserve the source
    # basename where possible, while enforcing the engine's playlist stem limit.
    stem = identifier(source.stem.strip())[:MAX_STEM]
    if not stem or stem in ('.', '..'):
        print('[ERROR] Theme filename has no usable RSM identifier after sanitization.')
        return 1
    if len(identifier(source.stem.strip())) > MAX_STEM:
        print(f'[TITLE THEME] Shortened RSM identifier to {MAX_STEM} characters: {stem}')
    ref = 'music\\HipHop\\' + stem
    dest = root / 'STREAMS' / 'Music' / 'HipHop' / (stem + '.rsm')
    if not dest.parent.is_dir():
        print('[ERROR] STREAMS\\Music\\HipHop is missing.')
        return 1
    playlist_root = root / 'ASSETS' / 'tune' / 'audio' / 'playlist' / 'city'
    playlists = [playlist_root / city / 'music' / 'frontend.play' for city in CITIES]
    old_data = {}
    refs = []
    try:
        for p in playlists:
            raw = p.read_bytes()
            old_data[p] = raw
            refs.append(parse_playlist(raw, p))
    except (OSError, ValueError) as exc:
        print(f'[ERROR] Cannot validate all four frontend playlists: {exc}. Nothing changed.')
        return 1
    if len(set(refs)) != 1:
        print('[ERROR] Frontend playlists disagree on current theme. Nothing changed.')
        return 1
    previous_ref = refs[0]
    history_file = root / 'support_logs' / 'title_theme_history.json'
    legacy_history_file = root / 'support_logs' / 'cinematic_theme_history.json'
    history_source = history_file if history_file.exists() else legacy_history_file
    try:
        history = json.loads(history_source.read_text(encoding='utf-8')) if history_source.exists() else {}
        if not isinstance(history, dict):
            raise ValueError('Invalid theme history')
    except (ValueError, OSError) as exc:
        print(f'[ERROR] Cannot read theme history: {exc}')
        return 1
    digest = sha256(source)
    if previous_ref.casefold() == ref.casefold() and dest.is_file() and history.get('sha256') == digest and history.get('reference', '').casefold() == ref.casefold():
        print(f'[SKIP UNCHANGED TITLE THEME] {source.name}')
        if not history_file.exists() and legacy_history_file.exists():
            history_file.parent.mkdir(parents=True, exist_ok=True)
            safe_write(history_file, legacy_history_file.read_bytes())
        return 0
    # Existing untracked RSMs must not be silently overwritten.
    if dest.is_file() and previous_ref.casefold() != ref.casefold() and history.get('reference', '').casefold() != ref.casefold():
        print(f'[ERROR] Target RSM already exists and is not managed by theme history: {dest.name}')
        return 1
    tools = root / 'supporting_tools'
    processor = tools / 'audio_processor.py'
    builder = tools / 'rstm_build.py'
    if not processor.is_file() or not builder.is_file():
        print('[ERROR] supporting_tools\\audio_processor.py or rstm_build.py is missing.')
        return 1
    print(f'[TITLE THEME] Converting {source.name} -> {dest.name}')
    with tempfile.TemporaryDirectory(prefix='Title_Theme_Convert_', dir=root) as work:
        wav = Path(work) / 'theme.wav'
        rsm = Path(work) / 'theme.rsm'
        result = subprocess.run([sys.executable, str(processor), str(source), '-o', str(wav)])
        if result.returncode or not wav.is_file():
            print('[ERROR] Theme Python audio conversion failed; previous theme preserved.')
            return 1
        result = subprocess.run([sys.executable, 'rstm_build.py', str(wav), '-o', str(rsm)], cwd=tools)
        if result.returncode or not rsm.is_file() or rsm.stat().st_size < 2048:
            print('[ERROR] Theme RSM encoding failed; previous theme preserved.')
            return 1
        # Preserve previous target bytes for rollback in case any playlist write fails.
        old_target = dest.read_bytes() if dest.exists() else None
        changed = []
        try:
            safe_write(dest, rsm.read_bytes())
            for p in playlists:
                safe_write(p, playlist_bytes(old_data[p], ref))
                changed.append(p)
            history_file.parent.mkdir(parents=True, exist_ok=True)
            safe_write(history_file, (json.dumps({'version': 1, 'sha256': digest, 'reference': ref, 'source': source.name}, indent=2) + '\n').encode('utf-8'))
        except OSError as exc:
            print(f'[ERROR] Theme install failed: {exc}. Attempting rollback.')
            for p in changed:
                try:
                    safe_write(p, old_data[p])
                except OSError as rollback_exc:
                    print(f'[CRITICAL] Playlist rollback failed: {p}: {rollback_exc}')
            try:
                if old_target is None:
                    dest.unlink(missing_ok=True)
                else:
                    safe_write(dest, old_target)
            except OSError as rollback_exc:
                print(f'[CRITICAL] RSM rollback failed: {rollback_exc}')
            return 1
    print('[OK] All four frontend playlists now reference:', ref)
    # Delete only the previous toolkit-managed custom theme, never the original or any
    # music referenced elsewhere in the extracted ASSETS playlists.
    if previous_ref.casefold() != ref.casefold() and previous_ref.casefold() != ORIGINAL.casefold():
        managed = history.get('reference', '')
        if managed.casefold() == previous_ref.casefold():
            rel = previous_ref.split('\\')
            old_file = root / 'STREAMS' / 'Music' / rel[1] / (rel[2] + '.rsm')
            still_used = False
            for playlist in (root / 'ASSETS' / 'tune' / 'audio' / 'playlist').rglob('*.play'):
                try:
                    if previous_ref.casefold() in playlist.read_text(encoding='ascii').casefold():
                        still_used = True
                        break
                except (OSError, UnicodeError):
                    still_used = True  # Conservative: don't delete if references cannot be checked.
                    break
            if not still_used and old_file.is_file() and old_file.resolve() != dest.resolve():
                try:
                    old_file.unlink()
                    print('[CLEANUP] Deleted previous toolkit-managed theme:', old_file.name)
                except OSError as exc:
                    print(f'[WARNING] Could not remove previous theme: {exc}')
            else:
                print('[PRESERVED] Previous theme RSM is referenced elsewhere or could not be safely verified.')
        else:
            print('[PRESERVED] Previous theme is not tracked as toolkit-managed; no automatic deletion.')
    print('[DONE] Title theme song updated. Select Option 6 to compile DAT archives and build the ISO.')
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, KeyboardInterrupt) as exc:
        print(f'[ERROR] {exc}')
        sys.exit(1)
