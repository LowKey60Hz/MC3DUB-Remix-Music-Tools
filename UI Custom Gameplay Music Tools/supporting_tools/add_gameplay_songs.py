#!/usr/bin/env python3
"""Phase 4B: safely add new RSM files; playlists and metadata are NOT modified."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

MIB = 1024 * 1024


def available_resources():
    """Return usable CPUs and currently available RAM; unknown means serial."""
    try:
        cpus = os.cpu_count() or 1
        if hasattr(os, 'sched_getaffinity'):
            cpus = min(cpus, len(os.sched_getaffinity(0)))
        if os.name == 'nt':
            import ctypes
            class MemoryStatus(ctypes.Structure):
                _fields_ = [('length', ctypes.c_uint32), ('load', ctypes.c_uint32)] + [
                    (name, ctypes.c_uint64) for name in
                    ('total', 'available', 'total_page', 'available_page',
                     'total_virtual', 'available_virtual', 'extended')]
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            process_mask, system_mask = ctypes.c_size_t(), ctypes.c_size_t()
            kernel.GetCurrentProcess.restype = ctypes.c_void_p
            kernel.GetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
            if not kernel.GetProcessAffinityMask(kernel.GetCurrentProcess(),
                                                ctypes.byref(process_mask), ctypes.byref(system_mask)):
                return 1, None
            cpus = min(cpus, process_mask.value.bit_count())
            memory = MemoryStatus()
            memory.length = ctypes.sizeof(memory)
            if not kernel.GlobalMemoryStatusEx(ctypes.byref(memory)):
                return cpus, None
            return cpus, memory.available
        # Linux reports available RAM, including reclaimable caches.
        meminfo = Path('/proc/meminfo')
        if meminfo.is_file():
            for line in meminfo.read_text().splitlines():
                if line.startswith('MemAvailable:'):
                    return cpus, int(line.split()[1])*1024
        return cpus, None
    except (OSError, ValueError, AttributeError):
        return 1, None


def estimated_conversion_memory(source):
    """Conservative working-set estimate, including full-file PCM preparation."""
    try:
        import soundfile as sf
        info = sf.info(str(source))
        if info.frames <= 0 or info.samplerate <= 0 or info.channels not in (1, 2):
            return None
        target_frames = (info.frames*44100 + info.samplerate-1)//info.samplerate
        # Allow for float64 decoding/resampling/rounding temporaries, Python
        # runtimes and channel workers. This is a budget, not a RAM guarantee.
        return 256*MIB + max(info.frames*info.channels, target_frames*2)*48
    except (OSError, ValueError, RuntimeError, ImportError):
        return None


def batch_width(jobs, serial=False):
    if serial or len(jobs) < 2:
        return 1
    cpus, memory = available_resources()
    # Each stereo conversion already uses two encoder workers. Leave two
    # logical CPUs and at least 1 GiB / half of available RAM for other work.
    maximum = min(3, len(jobs), max(1, (cpus-2)//2))
    if maximum < 2 or memory is None:
        return 1
    budget = min(memory//2, max(0, memory-1024*MIB))
    used = 0
    width = 0
    for job in jobs[:maximum]:
        estimate = estimated_conversion_memory(job[0])
        if estimate is None or used+estimate > budget:
            break
        used += estimate
        width += 1
    return max(1, width)


def convert_track(job, folder, tools, index, total, stopped, capture):
    """Workers only write their private scratch directory, never game files."""
    src = job[0]
    folder.mkdir()
    wav, rsm = folder/'input.wav', folder/'output.rsm'
    log = folder/'conversion.log'
    started = time.perf_counter()
    with log.open('w', encoding='utf-8') as output:
        for stage, command in (
            ('audio preparation', [sys.executable, str(tools/'audio_processor.py'), str(src), '-o', str(wav)]),
            ('RSM encoding', [sys.executable, 'rstm_build.py', str(wav), '-o', str(rsm)]),
        ):
            if stopped.is_set():
                return rsm, 'Conversion stopped after another track failed.', log
            print(f'[{index}/{total}] {stage}: {src.name}', flush=True)
            kwargs = {'stdout': output, 'stderr': subprocess.STDOUT} if capture else {}
            result = subprocess.run(command, cwd=tools, **kwargs)
            expected = wav if stage == 'audio preparation' else rsm
            if result.returncode or not expected.is_file() or (expected == rsm and rsm.stat().st_size < 2048):
                stopped.set()
                return rsm, f'{stage} failed for {src.name} (exit code {result.returncode}).', log
    print(f'[{index}/{total}] Converted {src.name} in {time.perf_counter()-started:.1f}s', flush=True)
    return rsm, None, log


def convert_batch(jobs, scratch, tools, first, total, converter=None):
    converter = converter or convert_track
    stopped = threading.Event()
    if len(jobs) == 1:
        return [converter(jobs[0], scratch/str(first), tools, first, total, stopped, False)]
    results = [None]*len(jobs)
    pool = ThreadPoolExecutor(max_workers=len(jobs))
    try:
        futures = {pool.submit(converter, job, scratch/str(first+i), tools,
                               first+i, total, stopped, True): i for i,job in enumerate(jobs)}
        for future in as_completed(futures):
            i = futures[future]
            try:
                results[i] = future.result()
            except Exception as exc:
                stopped.set()
                results[i] = (None, f'Conversion failed for {jobs[i][0].name}: {exc}', None)
            log = results[i][2]
            if log:
                for line in log.read_text(encoding='utf-8', errors='replace').splitlines():
                    print(f'[{first+i}/{total}] {line}', flush=True)
            if results[i][1]:
                print(f'[ERROR] {results[i][1]}', flush=True)
    finally:
        # Drain active subprocesses before scratch cleanup, even on Ctrl+C.
        stopped.set()
        pool.shutdown(wait=True, cancel_futures=True)
    return results

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
    if not (tools / 'ps_adpcm_encoder.py').is_file():
        print('[ERROR] Missing supporting_tools/ps_adpcm_encoder.py')
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
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='Music_Add_Temp_', dir=root) as tmp:
        index = 0
        previous_width = None
        while index < len(jobs):
            # Recheck resources between bounded batches; never queue all songs.
            width = batch_width(jobs[index:], serial='--serial' in sys.argv[2:])
            if width != previous_width:
                print(f'[INFO] Converting up to {width} song(s) at a time (adaptive CPU/RAM budget).', flush=True)
                previous_width = width
            batch = jobs[index:index+width]
            results = convert_batch(batch, Path(tmp), tools, index+1, len(jobs))
            # Only this thread publishes, in the original job order. A failure
            # stops publication of later tracks, playlists and metadata.
            for job, (rsm, error, _) in zip(batch, results):
                src, dest, artist, title, genre, record_key, digest, mode = job
                if error:
                    print(f'[ERROR] {error} Previously added RSMs are retained.')
                    return 1
                try:
                    if mode == 'ADD':
                        created = False
                        try:
                            with dest.open('xb') as output:
                                created = True
                                with rsm.open('rb') as source:
                                    shutil.copyfileobj(source, output)
                        except BaseException:
                            if created:
                                dest.unlink(missing_ok=True)
                            raise
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
                print(f'[OK] {"Replaced" if mode == "UPDATE" else "Added"} {dest.relative_to(root)}', flush=True)
                # Bound temporary disk use to the current batch.
                completed_folder = rsm.parent.resolve()
                completed_folder.relative_to(Path(tmp).resolve())
                shutil.rmtree(completed_folder)
            index += len(batch)
    save_history(history_path, history)
    print(f'\n[DONE] {len(added)} added, {len(updated)} updated, {unchanged} unchanged/baselined.')
    print(f'[INFO] Conversion batch completed in {time.perf_counter()-started:.1f}s.')
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
