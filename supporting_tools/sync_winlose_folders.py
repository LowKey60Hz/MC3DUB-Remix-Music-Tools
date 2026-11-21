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
import time
from contextlib import nullcontext
import add_gameplay_songs as audio_batch
from remove_race_soundtracks import PLACEHOLDERS, slot_entries, digest as rsm_digest

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


def encode(song, output, tools, scratch, log=None):
    wav = scratch / 'source.wav'
    wav.unlink(missing_ok=True)
    output.unlink(missing_ok=True)
    kwargs = {'stdout': log, 'stderr': subprocess.STDOUT} if log is not None else {}
    cmd = [sys.executable, str(tools / 'audio_processor.py'), str(song), '-o', str(wav)]
    if subprocess.run(cmd, **kwargs).returncode or not wav.is_file():
        raise RuntimeError(f'Python WAV conversion failed for {song.name}')
    cmd = [sys.executable, str(tools / 'rstm_build.py'), str(wav), '-o', str(output)]
    if subprocess.run(cmd, cwd=tools, **kwargs).returncode or not output.is_file() or output.stat().st_size < 2048:
        raise RuntimeError(f'RSM encoding failed for {song.name}')
    wav.unlink(missing_ok=True)


def convert_track(job, folder, tools, index, total, stopped, capture):
    song, stem, _, kind = job
    folder.mkdir()
    output = folder/'output.rsm'
    log = folder/'conversion.log' if capture else None
    if stopped.is_set():
        return output, f'Conversion stopped for {song.name} after another track failed.', None
    started = time.perf_counter()
    print(f'[{index}/{total}] Converting {kind}: {song.name} -> {stem}.rsm', flush=True)
    try:
        with (log.open('w', encoding='utf-8') if log else nullcontext(None)) as stream:
            encode(song, output, tools, folder, stream)
    except (RuntimeError, OSError) as exc:
        stopped.set()
        return output, str(exc), log
    print(f'[{index}/{total}] Converted {kind}: {song.name} in {time.perf_counter()-started:.1f}s', flush=True)
    return output, None, log


def convert_plan(staged_plan, scratch, tools, serial=False):
    """Prepare every Win/Lose RSM before the existing installation transaction."""
    jobs = [(song, stem, digest, kind) for kind, plan in staged_plan.items()
            for song, stem, digest in plan]
    started = time.perf_counter()
    index = 0
    previous_width = None
    while index < len(jobs):
        width = audio_batch.batch_width(jobs[index:], serial=serial)
        if width != previous_width:
            print(f'[INFO] Converting up to {width} Win/Lose song(s) at a time (adaptive CPU/RAM budget).', flush=True)
            previous_width = width
        batch = jobs[index:index+width]
        results = audio_batch.convert_batch(batch, scratch, tools, index+1, len(jobs), converter=convert_track)
        for job, (output, error, _) in zip(batch, results):
            if error:
                raise RuntimeError(error)
            output.replace(scratch/(job[1]+'.rsm'))
            completed_folder = output.parent.resolve()
            completed_folder.relative_to(scratch.resolve())
            shutil.rmtree(completed_folder)
        index += len(batch)
    print(f'[INFO] Win/Lose conversion batch completed in {time.perf_counter()-started:.1f}s.', flush=True)


def main():
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
    mode = sys.argv[2].lower() if len(sys.argv) > 2 else ''
    if mode not in ('replace', 'add'):
        return fail('Usage: sync_winlose_folders.py ROOT replace|add [--serial]')
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
    if not (tools / 'ps_adpcm_encoder.py').is_file():
        return fail('Missing supporting_tools/ps_adpcm_encoder.py.')
    # A small history prevents re-adding the same source audio on later Add runs.
    history_path = root / 'support_logs' / 'winlose_add_history.json'
    try:
        history = json.loads(history_path.read_text(encoding='utf-8')) if history_path.exists() else {}
        if not isinstance(history, dict) or any(not isinstance(value, dict) for value in history.values()):
            raise ValueError('Invalid add history format')
    except (ValueError, OSError):
        return fail('Cannot read Win/Lose add history. Repair or remove it before continuing.')
    staged_plan = {}
    history_upgraded = False
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
            referenced = {entry.rsplit('\\', 1)[-1].casefold()
                          for entry in next(iter(info['data'].values()))[1]}
            plan = []
            for song in info['songs']:
                digest = hashlib.sha256(song.read_bytes()).hexdigest()
                record = previous.get(digest)
                recorded_slot = record.get('slot') if isinstance(record, dict) else record
                if (isinstance(recorded_slot, str) and re.fullmatch(prefix+r'\d+', recorded_slot, re.I)
                        and recorded_slot.casefold() in referenced
                        and (music/(recorded_slot+'.rsm')).is_file()):
                    installed = music/(recorded_slot+'.rsm')
                    installed_hash = rsm_digest(installed)
                    expected_hash = record.get('rsm_sha256') if isinstance(record, dict) else None
                    if not expected_hash:
                        # Old history recorded only a slot name, which can refer to
                        # original/restored audio after extraction. Verify the source.
                        print(f'[VERIFY] Checking unverified add history: {song.name}', flush=True)
                        try:
                            with tempfile.TemporaryDirectory(prefix='mc3_winlose_verify_') as temporary:
                                scratch = Path(temporary)
                                candidate = scratch/'candidate.rsm'
                                encode(song, candidate, tools, scratch)
                                expected_hash = rsm_digest(candidate)
                        except (OSError, RuntimeError) as exc:
                            return fail(f'Cannot verify previous installation of {song.name}: {exc}; game files unchanged.')
                    if expected_hash == installed_hash:
                        previous[digest] = {'slot': recorded_slot, 'rsm_sha256': installed_hash}
                        history[kind] = previous
                        history_upgraded = True
                        print(f'[SKIP] Already added (audio verified): {song.name} -> {recorded_slot}.rsm')
                        continue
                if record is not None:
                    print(f'[STALE HISTORY] {song.name}: previous audio is missing, different, or unreferenced; adding it again.')
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
        if history_upgraded:
            history_path.parent.mkdir(exist_ok=True)
            history_path.write_text(json.dumps(history, indent=2)+'\n', encoding='utf-8')
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
            convert_plan(staged_plan, scratch, tools, serial='--serial' in sys.argv[3:])
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
                            previous[digest] = {'slot': stem, 'rsm_sha256': rsm_digest(music/(stem+'.rsm'))}
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
