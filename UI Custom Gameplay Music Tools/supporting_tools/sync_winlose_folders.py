#!/usr/bin/env python3
"""Folder-driven Win/Lose replacement or addition. Empty folders never change game data."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from remove_race_soundtracks import PLACEHOLDERS, slot_entries

CONFIG = {
    'Win': ('2_Win', 'win', '*_raceover_music.play'),
    'Lose': ('2_Lose', 'loose', '*_raceover_lose_music.play'),
}


def fail(message):
    print('[ERROR]', message)
    return 1


def playlist_data(path, prefix):
    raw = path.read_bytes()
    try:
        lines = raw.decode('utf-8-sig').splitlines()
    except UnicodeError as exc:
        raise ValueError(f'Invalid encoding: {path}') from exc
    if not lines or not re.fullmatch(r'num_songs:\s*\d+', lines[0].strip()):
        raise ValueError(f'Invalid playlist header: {path}')
    entries = [x.strip() for x in lines[1:] if x.strip()]
    if len(entries) != int(lines[0].split(':', 1)[1]):
        raise ValueError(f'Playlist count mismatch: {path}')
    expected = re.compile(r'music\\Win_Lose\\' + prefix + r'\d+', re.I)
    placeholder = PLACEHOLDERS['Win' if prefix == 'win' else 'Lose']
    if any(not expected.fullmatch(x) and x.casefold() != placeholder.casefold() for x in entries):
        raise ValueError(f'Unexpected playlist entry: {path}')
    return raw, entries


def encode(song, output, tools, scratch):
    wav = scratch / 'source.wav'
    wav.unlink(missing_ok=True)
    output.unlink(missing_ok=True)
    cmd = [sys.executable, str(tools / 'audio_processor.py'), str(song), '-o', str(wav)]
    if subprocess.run(cmd).returncode or not wav.is_file():
        raise RuntimeError(f'Python WAV conversion failed for {song.name}')
    cmd = [sys.executable, str(tools / 'rstm_build.py'), str(wav), '-o', str(output)]
    if subprocess.run(cmd, cwd=tools).returncode or not output.is_file() or output.stat().st_size < 2048:
        raise RuntimeError(f'RSM encoding failed for {song.name}')
    wav.unlink(missing_ok=True)


def main():
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
    mode = sys.argv[2].lower() if len(sys.argv) > 2 else ''
    if mode not in ('replace', 'add'):
        return fail('Usage: sync_winlose_folders.py ROOT replace|add')
    tools = root / 'supporting_tools'
    music = root / 'STREAMS' / 'Music' / 'Win_Lose'
    playlist_root = root / 'ASSETS' / 'tune' / 'audio' / 'playlist'
    if not music.is_dir() or not playlist_root.is_dir():
        return fail('Extract and decompile ASSETS and STREAMS first.')
    groups = {}
    for kind, (folder, prefix, pattern) in CONFIG.items():
        source = root / 'Custom Music' / folder
        songs = sorted((p for p in source.iterdir() if p.is_file() and p.suffix.lower() in ('.mp3', '.wav')),
                       key=lambda p: (p.name.casefold(), p.name)) if source.is_dir() else []
        if not songs:
            print(f'[SKIP] {folder}: no MP3/WAV files; {kind} files and playlists unchanged.')
            continue
        paths = sorted(playlist_root.glob('city/*/music/' + pattern))
        if len(paths) != 24:
            return fail(f'Expected 24 {kind} playlists, found {len(paths)}.')
        try:
            data = {p: playlist_data(p, prefix) for p in paths}
        except (ValueError, OSError) as exc:
            return fail(str(exc))
        entries = next(iter(data.values()))[1]
        if any(item[1] != entries for item in data.values()):
            return fail(f'{kind} playlists are not synchronized; no changes made.')
        real = []
        seen_audio = set()
        for entry in entries:
            if entry.casefold() == PLACEHOLDERS[kind].casefold():
                continue
            installed = music/(entry.rsplit('\\', 1)[-1]+'.rsm')
            if not installed.is_file():
                return fail('Referenced race audio is missing: '+str(installed))
            identity = hashlib.sha256(installed.read_bytes()).digest()
            if identity not in seen_audio:
                real.append(entry)
                seen_audio.add(identity)
        groups[kind] = {'songs': songs, 'prefix': prefix, 'data': data, 'entries': real}
    if not groups:
        print('[INFO] Both folders empty. No changes made.')
        return 0
    if not (tools / 'audio_processor.py').is_file() or not (tools / 'rstm_build.py').is_file():
        return fail('Missing supporting_tools/audio_processor.py or rstm_build.py.')
    if not ((tools / 'ps2str.exe').is_file() or (tools / 'MFAudio.exe').is_file()):
        return fail('Missing PS2 audio encoder.')
    # A small history prevents re-adding the same source audio on later Add runs.
    history_path = root / 'support_logs' / 'winlose_add_history.json'
    try:
        history = json.loads(history_path.read_text(encoding='utf-8')) if history_path.exists() else {}
    except (ValueError, OSError):
        return fail('Cannot read Win/Lose add history. Repair or remove it before continuing.')
    staged_plan = {}
    for kind, info in groups.items():
        prefix = info['prefix']
        existing = sorted((p for p in music.iterdir() if p.is_file() and re.fullmatch(prefix + r'\d+\.rsm', p.name, re.I)), key=lambda p: p.name.casefold())
        info['existing'] = existing
        if mode == 'replace':
            numbers = list(range(1, len(info['songs']) + 1))
            if len(numbers) == 2:
                numbers = [1, 3]
            plan = [(song, f'{prefix}{n}', None) for song, n in zip(info['songs'], numbers)]
            info['entries_new'] = slot_entries(kind, [stem for _, stem, _ in plan])
        else:
            used = {p.stem.casefold() for p in existing}
            used.update(x.rsplit('\\', 1)[-1].casefold() for x in info['entries'])
            previous = history.get(kind, {})
            plan = []
            for song in info['songs']:
                digest = hashlib.sha256(song.read_bytes()).hexdigest()
                record = previous.get(digest)
                if record and record in used and (music / (record + '.rsm')).is_file():
                    print(f'[SKIP] Already added: {song.name} -> {record}.rsm')
                    continue
                i = 1
                while f'{prefix}{i}' in used:
                    i += 1
                if kind == 'Win' and len(info['entries']) == 1 and len(info['songs']) == 1 and i == 2:
                    i = 3
                    while f'{prefix}{i}' in used:
                        i += 1
                stem = f'{prefix}{i}'
                used.add(stem)
                plan.append((song, stem, digest))
            info['entries_new'] = info['entries'] + [f'music\\Win_Lose\\{stem}' for _, stem, _ in plan]
            info['entries_new'] = slot_entries(kind, [entry.rsplit('\\', 1)[-1] for entry in info['entries_new']])
        staged_plan[kind] = plan
        print(f'[{kind.upper()}] {len(info["songs"])} source file(s), {len(plan)} to convert ({mode}).')
        for song, stem, _ in plan:
            print(f'  {song.name} -> {stem}.rsm')
    if not any(staged_plan.values()):
        print('[INFO] No new songs to install. No changes made.')
        return 0
    print('[NOTE] No permanent RSM backups are created. You can restore from the original ISO.')
    print('[NOTE] The game engine song limit is unknown.')
    if input(f'Proceed with {mode.upper()} for nonempty folders? (Y/N): ').strip().lower() != 'y':
        print('[CANCELED] No changes made.')
        return 0
    with tempfile.TemporaryDirectory(prefix='mc3_winlose_') as temp:
        scratch = Path(temp)
        try:
            for kind, plan in staged_plan.items():
                for song, stem, _ in plan:
                    print(f'[CONVERT] {kind}: {song.name} -> {stem}.rsm')
                    encode(song, scratch / (stem + '.rsm'), tools, scratch)
        except (RuntimeError, OSError) as exc:
            return fail(f'{exc}; existing game files unchanged.')
        # Rollback copies are temporary and deleted on success; no permanent backups.
        changed = {p: raw for info in groups.values() for p, (raw, _) in info['data'].items() if staged_plan[('Win' if info['prefix']=='win' else 'Lose')]}
        old_audio = {}
        destinations = set()
        for kind, plan in staged_plan.items():
            if not plan:
                continue
            if mode == 'replace':
                for p in groups[kind]['existing']:
                    old_audio[p] = p.read_bytes()
                    destinations.add(p)
            for _, stem, _ in plan:
                dest = music / (stem + '.rsm')
                if mode == 'add' and dest.exists():
                    return fail(f'Destination already exists: {dest}')
                destinations.add(dest)
        old_history = history_path.read_bytes() if history_path.exists() else None
        try:
            if mode == 'replace':
                for p in old_audio:
                    p.unlink()
            for kind, plan in staged_plan.items():
                for _, stem, _ in plan:
                    dest = music / (stem + '.rsm')
                    with dest.open('xb') as out, (scratch / (stem + '.rsm')).open('rb') as src:
                        shutil.copyfileobj(src, out)
                if not plan:
                    continue
                for p, (raw, _) in groups[kind]['data'].items():
                    newline = '\r\n' if b'\r\n' in raw else '\n'
                    entries = groups[kind]['entries_new']
                    body = newline.join([f'num_songs: {len(entries)}', *entries]) + newline
                    p.write_bytes((b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b'') + body.encode('utf-8'))
                if mode == 'add':
                    previous = history.setdefault(kind, {})
                    for _, stem, digest in plan:
                        if digest is not None:
                            previous[digest] = stem
            if mode == 'add':
                history_path.parent.mkdir(exist_ok=True)
                history_path.write_text(json.dumps(history, indent=2) + '\n', encoding='utf-8')
            else:
                # Replacing tracks invalidates prior add-history for those categories.
                for kind in groups:
                    history.pop(kind, None)
                if history_path.exists():
                    history_path.write_text(json.dumps(history, indent=2) + '\n', encoding='utf-8')
        except Exception as exc:
            print('[ERROR] Installation failed:', exc)
            try:
                for p in destinations:
                    p.unlink(missing_ok=True)
                for p, raw in old_audio.items():
                    p.write_bytes(raw)
                for p, raw in changed.items():
                    p.write_bytes(raw)
                if old_history is None:
                    history_path.unlink(missing_ok=True)
                else:
                    history_path.write_bytes(old_history)
                print('[ROLLBACK] Previous files restored.')
            except Exception as recovery:
                print('[CRITICAL] Rollback failed:', recovery)
            return 1
    print('[OK] Win/Lose customization complete. Select Option 6 to build the ISO.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
