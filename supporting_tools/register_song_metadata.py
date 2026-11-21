#!/usr/bin/env python3
"""Phase 4D: register metadata for six genres, including Garage -> Instrumental.

Validates every source and playlist before touching either live string table.
"""
import copy
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from gameplay_placeholders import placeholder_refs, stage_metadata, install_metadata

MAX_RSM_STEM_LENGTH = 37  # Garage Shop playback tested: 37 works; 38 fails.
GENRES = {
    'Dancehall': ('Dancehall', 'dance_hall_race_music.play'),
    'Drum_N_Bass': ('Drum_N_Bass', 'drums_bass_race_music.play'),
    'Garage': ('Instrumental', 'garage.play'),
    'HipHop': ('HipHop', 'rap_race_music.play'),
    'Rock': ('Rock', 'pop_race_music.play'),
    'Techno': ('Techno', 'techno_race_music.play'),
}

def playlist_entries(path):
    data = path.read_bytes()
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        raise ValueError(f'Unsupported UTF-16 playlist: {path}')
    lines = data.decode('utf-8-sig').splitlines()
    if not lines or not re.fullmatch(r'num_songs:\s*\d+', lines[0].strip(), re.I):
        raise ValueError(f'Invalid playlist header: {path}')
    entries = [line.strip() for line in lines[1:] if line.strip()]
    if int(lines[0].split(':', 1)[1]) != len(entries):
        raise ValueError(f'Playlist count mismatch: {path}')
    if len({entry.casefold() for entry in entries}) != len(entries):
        raise ValueError(f'Duplicate entries in playlist: {path}')
    return {entry.casefold() for entry in entries}

def clean(value):
    return re.sub(r'[^A-Za-z0-9._()-]', '', value)

def register_main():
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent
    tables = [root / 'ASSETS' / 'fonts' / f'{name}.strtbl' for name in ('mcstrings02', 'mcstrings08')]
    playlist_dir = root / 'ASSETS' / 'tune' / 'audio' / 'playlist' / 'city' / 'sd' / 'music'
    codec = root / 'supporting_tools' / 'strtbl.py'
    if not codec.is_file():
        codec = root / 'strtbl.py'
    print('PHASE 4D - MULTI-GENRE METADATA REGISTRATION (SAN DIEGO)')
    print('No audio conversion, playlist editing, DAT compilation, or ISO building.')
    for label, path in [(p.name, p) for p in tables] + [('strtbl.py', codec)]:
        if not path.is_file():
            print(f'[ERROR] Missing {label}: {path}')
            return 1
    if any(p.stat().st_size < 1024 for p in tables):
        print('[ERROR] String table unexpectedly small.')
        return 1

    songs = {}
    errors = 0
    for folder_name, (internal, playlist_name) in GENRES.items():
        source_dir = root / 'Custom Music' / ('1_The_Garage_Shop' if folder_name == 'Garage' else '1_' + folder_name)
        files = sorted((p for p in source_dir.iterdir() if p.is_file() and p.suffix.lower() in ('.mp3', '.wav')),
                       key=lambda p: p.name.casefold()) if source_dir.is_dir() else []
        if not files:
            print(f'[SKIPPED] {folder_name}: no MP3/WAV source files')
            continue
        print(f'[GENRE] {folder_name} -> Music/{internal}: {len(files)} source file(s)')
        path = playlist_dir / playlist_name
        try:
            entries = playlist_entries(path)
        except (OSError, UnicodeError, ValueError) as exc:
            print(f'[ERROR] {exc}')
            errors += 1
            continue
        rsm_dir = root / 'STREAMS' / 'Music' / internal
        if not rsm_dir.is_dir():
            print(f'[ERROR] Missing RSM directory: {rsm_dir}')
            errors += 1
            continue
        existing_rsms = {p.name.casefold(): p for p in rsm_dir.iterdir() if p.is_file() and p.suffix.lower() == '.rsm'}
        for source in files:
            parts = source.stem.split('-', 1)
            if len(parts) != 2 or not all(part.strip() and clean(part.strip()) for part in parts):
                print(f'[ERROR] Invalid Artist - Title filename: {source.name}')
                errors += 1
                continue
            artist, title = (part.strip() for part in parts)
            full_stem = clean(artist) + '-' + clean(title)
            stem = full_stem[:MAX_RSM_STEM_LENGTH]
            # Support manually renamed Garage RSMs without changing normal naming.
            if folder_name == 'Garage':
                alternate = (clean(artist) + '_' + clean(title))[:MAX_RSM_STEM_LENGTH]
                if (stem + '.rsm').casefold() not in existing_rsms and (alternate + '.rsm').casefold() in existing_rsms:
                    stem = alternate
            if stem != full_stem:
                print(f'[SHORTEN] {full_stem} -> {stem}')
            key = f'music_{internal}_{stem}'
            if key.casefold() in {k.casefold() for k in songs}:
                print(f'[ERROR] Duplicate metadata identifier: {key}')
                errors += 1
                continue
            rsm = existing_rsms.get((stem + '.rsm').casefold())
            if rsm is None or rsm.stat().st_size < 2048:
                print(f'[ERROR] Missing or invalid RSM: {internal}/{stem}.rsm')
                errors += 1
                continue
            if (f'music\\{internal}\\{stem}').casefold() not in entries:
                print(f'[ERROR] Not registered in {playlist_name}: {stem}')
                errors += 1
                continue
            songs[key] = (internal, f'"{title}"\nby {artist}')
            print(f'[FOUND] {key}: {title} / {artist}')
    if errors:
        print(f'[STOP] {errors} validation issue(s). Nothing modified.')
        return 1
    if not songs:
        print('[SKIPPED] No source songs found. Nothing changed.')
        return 0

    with tempfile.TemporaryDirectory(prefix='mc3_metadata_') as temp:
        tmp = Path(temp)
        planned = []
        # Stage and round-trip-verify both outputs before changing either live file.
        for table in tables:
            work = tmp / table.stem
            work.mkdir()
            original = work / table.name
            shutil.copy2(table, original)
            decoded = subprocess.run([sys.executable, str(codec), 'dec', str(original)], capture_output=True, text=True)
            if decoded.returncode:
                print(f'[ERROR] Decoding failed for {table.name}:', decoded.stdout, decoded.stderr)
                return 1
            original_json = work / (table.stem + '.json')
            data = json.loads(original_json.read_text(encoding='utf-8'))
            if data.get('config', {}).get('version') != {'hash': 1, 'table': 2}:
                print(f'[ERROR] Unexpected table version: {table.name}')
                return 1
            entries = data['data']
            templates = {}
            for internal in {item[0] for item in GENRES.values()}:
                options = [v for k, v in entries.items() if k.startswith(f'music_{internal}_') and isinstance(v, dict)]
                if not options:
                    print(f'[ERROR] No metadata template for {internal} in {table.name}.')
                    return 1
                template = max(options, key=len)
                if len(template) != 6 or not all(isinstance(v, dict) and 'text' in v and 'font' in v for v in template.values()):
                    print(f'[ERROR] Invalid six-language template for {internal} in {table.name}.')
                    return 1
                templates[internal] = template
            changes = {}
            existing_folded = {key.casefold(): key for key in entries}
            for key, (internal, value) in songs.items():
                matching = existing_folded.get(key.casefold())
                if matching is not None:
                    existing = entries[matching]
                    template = templates[internal]
                    if len(existing) == 6 and all(lang in existing and existing[lang].get('text') == value for lang in template):
                        print(f'[SKIPPED] {table.name}: {key}')
                        continue
                    print(f'[ERROR] Existing metadata differs in {table.name}: {matching}')
                    return 1
                new_entry = copy.deepcopy(templates[internal])
                for lang in new_entry:
                    new_entry[lang]['text'] = value
                changes[key] = new_entry
                print(f'[ADD] {table.name}: {key} ({len(new_entry)} languages)')
            if not changes:
                continue
            entries.update(changes)
            original_json.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding='utf-8')
            original.unlink()  # Only temporary copy; prevents codec overwrite prompt.
            encoded = subprocess.run([sys.executable, str(codec), 'enc', str(original_json)], capture_output=True, text=True)
            if encoded.returncode:
                print(f'[ERROR] Encoding failed for {table.name}:', encoded.stdout, encoded.stderr)
                return 1
            candidate = work / table.name
            if not candidate.is_file() or candidate.stat().st_size < 1024:
                print(f'[ERROR] Encoded output missing: {table.name}')
                return 1
            verify_dir = work / 'verify'
            verify_dir.mkdir()
            verify_file = verify_dir / table.name
            shutil.copy2(candidate, verify_file)
            check = subprocess.run([sys.executable, str(codec), 'dec', str(verify_file)], capture_output=True, text=True)
            if check.returncode:
                print(f'[ERROR] Verification decode failed for {table.name}:', check.stdout, check.stderr)
                return 1
            verified = json.loads((verify_dir / (table.stem + '.json')).read_text(encoding='utf-8'))
            if verified != data:
                print(f'[ERROR] Round-trip mismatch for {table.name}. Nothing changed.')
                return 1
            planned.append((table, candidate, len(changes)))
        if not planned:
            print('[DONE] All metadata already registered in both tables. Nothing changed.')
            return 0
        print('\nPlanned updates:')
        for table, _, count in planned:
            print(f'  {table.name}: {count} new key(s)')
        if '--yes' not in sys.argv[2:] and input('Update metadata? (Y/N), then press Enter: ').strip().upper() != 'Y':
            print('[CANCELLED] Nothing changed.')
            return 0
        # Keep original copies only in the automatically removed temporary workspace.
        originals = {}
        for table, _, _ in planned:
            rollback_copy = tmp / ('rollback_' + table.name)
            shutil.copy2(table, rollback_copy)
            originals[table] = rollback_copy
        installed = []
        try:
            for table, candidate, _ in planned:
                staged = table.with_name(table.name + '.phase4d.tmp')
                try:
                    with staged.open('xb') as output, candidate.open('rb') as source:
                        shutil.copyfileobj(source, output)
                    staged.replace(table)
                finally:
                    staged.unlink(missing_ok=True)
                installed.append(table)
                print(f'[UPDATED] {table.name}')
        except OSError:
            for table in installed:
                shutil.copy2(originals[table], table)
            raise
        print(f'[DONE] Registered {sum(count for _, _, count in planned)} table entries.')
        return 0

def cleanup_unused_placeholders(root):
    """Remove dot metadata only when no playlist anywhere references the placeholder."""
    used = set()
    for path in (root / 'ASSETS').rglob('*.play'):
        for line in path.read_bytes().decode('utf-8-sig').splitlines()[1:]:
            used.add(line.strip().replace('/', '\\').casefold())
    unused = {ref for ref in placeholder_refs() if ref.casefold() not in used}
    if not unused:
        return
    temp, planned = stage_metadata(root, {}, unused)
    with temp:
        if planned:
            # Snapshot live tables for rollback if a write fails.
            original = {p: p.read_bytes() for p, _ in planned}
            try:
                install_metadata(planned)
            except Exception:
                for p, data in original.items():
                    p.write_bytes(data)
                raise
    print('[PLACEHOLDER] Unreferenced dot metadata cleaned up.')


def main():
    result = register_main()
    if result != 0:
        return result
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent
    cleanup_unused_placeholders(root)
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, UnicodeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f'[ERROR] {exc}')
        sys.exit(1)
