#!/usr/bin/env python3
"""Phase 4C: register converted RSMs in verified city genre playlists."""
from pathlib import Path
import random
import re
import sys
from gameplay_placeholders import is_placeholder

GENRE_PLAYLISTS = {
    'Dancehall': ('Dancehall', ('sd.play', 'dance_hall_race_music.play')),
    'Drum_N_Bass': ('Drum_N_Bass', ('sd.play', 'drums_bass_race_music.play')),
    'Garage': ('Instrumental', ('garage.play',)),
    'HipHop': ('HipHop', ('sd.play', 'rap_race_music.play')),
    'Rock': ('Rock', ('sd.play', 'pop_race_music.play')),
    'Techno': ('Techno', ('sd.play', 'techno_race_music.play')),
}
MAX_RSM_STEM_LENGTH = 37  # Garage Shop playback tested: 37 works; 38 fails.


def load_playlist(path):
    data = path.read_bytes()
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        raise ValueError(f'Unsupported UTF-16 playlist: {path}')
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValueError(f'Cannot decode playlist {path}: {exc}') from exc
    newline = '\r\n' if b'\r\n' in data else '\n'
    lines = text.splitlines()
    if not lines or not re.fullmatch(r'num_songs:\s*\d+', lines[0].strip(), re.I):
        raise ValueError(f'Invalid num_songs header: {path}')
    entries = [line.strip() for line in lines[1:] if line.strip()]
    count = int(lines[0].split(':', 1)[1].strip())
    if count != len(entries):
        raise ValueError(f'Playlist count mismatch in {path.name}: header {count}, actual {len(entries)}')
    if len(set(x.casefold() for x in entries)) != len(entries):
        raise ValueError(f'Existing duplicate entries in {path.name}; refusing to modify')
    return data, newline, entries


def main():
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent
    city_dir = root / 'ASSETS' / 'tune' / 'audio' / 'playlist' / 'city'
    print('PHASE 4C - MULTI-GENRE PLAYLIST REGISTRATION')
    print('No audio conversion, metadata editing, DAT compilation, or ISO building.')
    requested = {}  # playlist Path -> entries to add
    errors = 0
    for source_genre, (game_genre, playlist_names) in GENRE_PLAYLISTS.items():
        music = root / 'Custom Music' / ('1_The_Garage_Shop' if source_genre == 'Garage' else '1_' + source_genre)
        files = sorted((p for p in music.iterdir() if p.is_file() and p.suffix.lower() in ('.mp3', '.wav')),
                       key=lambda p: p.name.casefold()) if music.is_dir() else []
        if not files:
            print(f'[SKIPPED] {source_genre}: no MP3/WAV source files')
            continue
        rsm_dir = root / 'STREAMS' / 'Music' / game_genre
        if not rsm_dir.is_dir():
            print(f'[ERROR] Missing RSM directory: {rsm_dir}')
            errors += 1
            continue
        existing_rsms = {p.name.casefold(): p for p in rsm_dir.iterdir()
                         if p.is_file() and p.suffix.lower() == '.rsm'}
        seen = set()
        print(f'[GENRE] {source_genre} -> Music/{game_genre}: {len(files)} source file(s)')
        for source in files:
            parts = source.stem.split('-', 1)
            if len(parts) != 2 or not all(p.strip() for p in parts):
                print(f'[ERROR] Invalid Artist - Title filename: {source.name}')
                errors += 1
                continue
            artist, title = (p.strip() for p in parts)
            clean = lambda value: re.sub(r'[^A-Za-z0-9._()-]', '', value)
            if not clean(artist) or not clean(title):
                print(f'[ERROR] Invalid identifier: {source.name}')
                errors += 1
                continue
            full_stem = clean(artist) + '-' + clean(title)
            stem = full_stem[:MAX_RSM_STEM_LENGTH]
            if source_genre == 'Garage':
                alternate = (clean(artist) + '_' + clean(title))[:MAX_RSM_STEM_LENGTH]
                if ((stem + '.rsm').casefold() not in existing_rsms and
                        (alternate + '.rsm').casefold() in existing_rsms):
                    print(f'[RSM NAME] {stem} -> {alternate}')
                    stem = alternate
            if len(full_stem) > MAX_RSM_STEM_LENGTH:
                print(f'[SHORTEN] {full_stem} -> {stem}')
            entry = 'music\\' + game_genre + '\\' + stem
            if entry.casefold() in seen:
                print(f'[ERROR] Duplicate source identifier: {entry}')
                errors += 1
                continue
            seen.add(entry.casefold())
            actual = existing_rsms.get((stem + '.rsm').casefold())
            if actual is None or actual.stat().st_size < 2048:
                print(f'[ERROR] Missing or invalid RSM for {source.name}: {stem}.rsm')
                errors += 1
                continue
            for name in playlist_names:
                cities = ('atlanta', 'detroit', 'sd', 'tokyo') if source_genre == 'Garage' else ('sd',)
                for city in cities:
                    path = city_dir / city / 'music' / name
                    requested.setdefault(path, []).append(entry)
            print(f'[FOUND RSM] {entry}')
    if errors:
        print(f'[STOP] {errors} issue(s); no playlists modified.')
        return 1
    if not requested:
        print('[DONE] No source songs found. Nothing changed.')
        return 0
    # A Race Editor placeholder also needs replacing when a city receives real songs.
    for path, additions in list(requested.items()):
        if path.name.casefold() == 'sd.play':
            editor = path.with_name('raceeditor.play')
            if editor.is_file():
                _, _, editor_entries = load_playlist(editor)
                if any(is_placeholder(x) for x in editor_entries):
                    requested.setdefault(editor, []).extend(additions)
    changes = {}
    try:
        for path, additions_requested in requested.items():
            if not path.is_file():
                raise ValueError(f'Missing playlist: {path}')
            original, newline, entries = load_playlist(path)
            existing = {entry.casefold() for entry in entries}
            additions = [entry for entry in additions_requested if entry.casefold() not in existing]
            # Only clear a placeholder after at least one real song is registered.
            if additions or any(not is_placeholder(x) for x in entries):
                retained = [x for x in entries if not is_placeholder(x)]
            else:
                retained = entries
            print(f'[PLAYLIST] {path.parent.parent.name}/{path.name}: {len(entries)} existing, {len(additions)} to add')
            if additions or retained != entries:
                updated = [*retained, *additions]
                # Shuffle only the general city playlist when new songs are added.
                # Genre-specific, Garage Shop, and Race Editor playlists retain their order.
                if path.name.casefold() == 'sd.play' and additions:
                    random.shuffle(updated)
                    print(f'[SHUFFLED] {path.parent.parent.name}/{path.name}: {len(updated)} songs')
                output = ('num_songs: ' + str(len(updated)) + newline +
                          newline.join(updated) + newline).encode('utf-8')
                changes[path] = (original, output)
    except (OSError, ValueError) as exc:
        print(f'[ERROR] {exc}. No playlists modified.')
        return 1
    if not changes:
        print('[DONE] All matching songs already registered. Nothing changed.')
        return 0
    print('\nPlanned modifications (only these files):')
    for path in changes:
        print(' ', path)
    if '--yes' not in sys.argv[2:] and input('Update playlists? (Y/N), then press Enter: ').strip().upper() != 'Y':
        print('Canceled. Nothing changed.')
        return 0
    modified = []
    try:
        for path, (_, output) in changes.items():
            temp = path.with_name(path.name + '.phase4c.tmp')
            try:
                with temp.open('xb') as f:
                    f.write(output)
                temp.replace(path)
            finally:
                temp.unlink(missing_ok=True)
            modified.append(path)
            print(f'[UPDATED] {path.parent.parent.name}/{path.name}')
    except OSError as exc:
        print(f'[ERROR] Write failed: {exc}')
        for path in reversed(modified):
            try:
                path.write_bytes(changes[path][0])
                print(f'[RESTORED] {path.parent.parent.name}/{path.name}')
            except OSError as restore_exc:
                print(f'[CRITICAL] Could not restore {path.name}: {restore_exc}')
        return 1
    print(f'[DONE] Updated {len(modified)} playlist(s).')
    print('Song metadata will be registered automatically in the next stage.')
    return 0

if __name__ == '__main__':
    sys.exit(main())
