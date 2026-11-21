#!/usr/bin/env python3
"""Loading-screen slot editor, integrated with the existing ASSETS workflow.
PCM settings and assignment semantics follow the finalized loading-screen batch tool.
"""
import random
import shutil
import sys
import tempfile
from pathlib import Path

from convert_loading_raw import convert
from preview_raw import preview_raw

SLOT_COUNT = 18
MAX_RAW_BYTES = 455680  # 445 KiB, matching the GUI and converter policy.


def ask(prompt, valid):
    while True:
        answer = input(prompt).strip().upper()
        if answer in valid:
            return answer
        print('[INVALID INPUT] Choose ' + ', '.join(valid))


def main():
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
    music_dir = root / 'Loading Music'
    target = root / 'ASSETS' / 'audio' / 'loadscreen'
    if not target.is_dir() or any(not (target / f'{i}.raw').is_file() for i in range(1, SLOT_COUNT + 1)):
        print('[ERROR] Expected all 18 ASSETS/audio/loadscreen slots. Decompile ASSETS.DAT first.')
        return 1
    music_dir.mkdir(exist_ok=True)
    tracks = sorted((p for p in music_dir.iterdir() if p.is_file() and p.suffix.lower() in ('.mp3', '.wav')), key=lambda p: p.name.casefold())
    print('\n===================================================')
    print('  Ultimate Music Tools - Loading Screen Music')
    print('===================================================')
    print(f'Found {len(tracks)} MP3/WAV file(s) in Loading Music.')
    if not tracks:
        print('No tracks found. Nothing changed.')
        return 0
    if len(tracks) > SLOT_COUNT:
        print('[ERROR] Maximum 18 source tracks. Nothing changed.')
        return 1
    print('[M] Manual Selection - choose, preview and replace slots')
    print('[A] Automatic Randomized - unique random slot for each track')
    print('[E] Evenly Distributed - fill all 18 slots across tracks')
    print('[R] Return to Main Menu')
    mode = ask('Enter M, A, E or R, then press Enter: ', {'M', 'A', 'E', 'R'})
    if mode == 'R':
        return 0
    # Prepare all converted tracks and validate size BEFORE changing any game files.
    with tempfile.TemporaryDirectory(prefix='MC3_Loading_', dir=root) as work:
        prepared = []
        for i, src in enumerate(tracks, 1):
            raw = Path(work) / f'{i}.raw'
            print(f'[{i}/{len(tracks)}] Converting {src.name} ...')
            try:
                convert(src, raw)
            except (OSError, RuntimeError, ValueError) as exc:
                print(f'[ERROR] Python conversion failed for {src.name}: {exc}')
                print('No game slots were changed.')
                return 1
            if not raw.is_file():
                print(f'[ERROR] Python converter did not produce {raw.name}. No game slots were changed.')
                return 1
            size = raw.stat().st_size
            if size > MAX_RAW_BYTES or size == 0:
                print(f'[ERROR] {src.name}: RAW size {size:,} bytes; allowed 1-{MAX_RAW_BYTES:,} bytes.')
                print('Shorten the source audio and retry. No game slots were changed.')
                return 1
            prepared.append((src, raw))
        assignments = []
        if mode == 'E':
            for i, (src, raw) in enumerate(prepared):
                start = i * SLOT_COUNT // len(prepared) + 1
                end = (i + 1) * SLOT_COUNT // len(prepared)
                assignments.extend((slot, src, raw) for slot in range(start, end + 1))
                print(f'[EVEN] {src.name} -> slots {start}-{end}')
        elif mode == 'A':
            slots = random.sample(range(1, SLOT_COUNT + 1), len(prepared))
            assignments = [(slot, src, raw) for slot, (src, raw) in zip(slots, prepared)]
            for slot, src, _ in assignments:
                print(f'[RANDOM] {src.name} -> slot {slot}')
        else:
            for src, raw in prepared:
                while True:
                    slot_input = input(f'Choose slot 1-18 for {src.name} (or S to skip): ').strip().upper()
                    if slot_input == 'S':
                        print('[SKIPPED] ' + src.name)
                        break
                    if not slot_input.isdecimal() or not 1 <= int(slot_input) <= SLOT_COUNT:
                        print('[INVALID INPUT] Enter a slot number 1-18 or S.')
                        continue
                    slot = int(slot_input)
                    dest = target / f'{slot}.raw'
                    print(f'Source: {src.name}\nTarget: {dest}')
                    print('[R] Replace  [P] Preview target  [T] Try another  [S] Skip')
                    action = ask('Enter R, P, T or S, then press Enter: ', {'R', 'P', 'T', 'S'})
                    if action == 'P':
                        try:
                            preview_raw(dest, loops=4)
                        except (OSError, RuntimeError, ValueError) as exc:
                            print(f'[WARNING] Preview failed: {exc}')
                    elif action == 'R':
                        assignments.append((slot, src, raw))
                        break
                    elif action == 'S':
                        break
        if not assignments:
            print('No slots selected. Nothing changed.')
            return 0
        if mode != 'M' and ask(f'Apply {len(assignments)} slot replacement(s)? (Y/N): ', {'Y', 'N'}) != 'Y':
            print('Canceled. No slots changed.')
            return 0
        # Back up target bytes in temporary workspace, restore on any write failure.
        backups = {}
        try:
            for slot, src, raw in assignments:
                dest = target / f'{slot}.raw'
                if slot not in backups:
                    backup = Path(work) / f'backup_{slot}.raw'
                    shutil.copyfile(dest, backup)
                    backups[slot] = backup
                shutil.copyfile(raw, dest)
                print(f'[UPDATED] Slot {slot} <- {src.name}')
        except OSError as exc:
            print(f'[ERROR] Slot update failed: {exc}. Attempting to restore original slots.')
            for slot, backup in backups.items():
                try:
                    shutil.copyfile(backup, target / f'{slot}.raw')
                except OSError as restore_exc:
                    print(f'[CRITICAL] Could not restore slot {slot}: {restore_exc}')
            return 1
    print('[DONE] Loading-screen slots updated in ASSETS. Build ISO when ready.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (KeyboardInterrupt, EOFError) as exc:
        print(f'\n[CANCELLED] {exc}')
        sys.exit(1)
