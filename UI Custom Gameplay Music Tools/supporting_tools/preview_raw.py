#!/usr/bin/env python3
"""Preview MC3 loading-screen RAW PCM audio a fixed number of times."""
import argparse
from pathlib import Path
import threading
import os

if os.name == "nt":
    import msvcrt

import numpy as np
import sounddevice as sd


def main():
    parser = argparse.ArgumentParser(description='Preview 24 kHz mono 16-bit PCM RAW audio.')
    parser.add_argument('file', type=Path, help='Path to the loading-screen .raw file')
    parser.add_argument('--loops', type=int, default=4, help='Number of complete plays (default: 4)')
    args = parser.parse_args()
    return preview_raw(args.file, args.loops)


def preview_raw(file_path, loops=4):
    file_path = Path(file_path)
    if loops < 1:
        raise ValueError('loops must be at least 1')
    try:
        data = file_path.read_bytes()
    except OSError as exc:
        raise RuntimeError(str(exc)) from exc
    if not data or len(data) % 2:
        raise ValueError('RAW file must contain a nonempty, even number of bytes (16-bit PCM)')
    audio = np.frombuffer(data, dtype='<i2')
    length = len(audio)
    total_frames = length * loops
    position = 0
    completed = threading.Event()
    stop_requested = threading.Event()

    def callback(outdata, frames, time_info, status):
        nonlocal position
        if stop_requested.is_set():
            outdata.fill(0)
            raise sd.CallbackStop()
        if status:
            print(f'Audio warning: {status}', flush=True)
        outdata.fill(0)
        remaining = total_frames - position
        n = min(frames, remaining)
        filled = 0
        while filled < n:
            offset = position % length
            chunk = min(n - filled, length - offset)
            outdata[filled:filled + chunk, 0] = audio[offset:offset + chunk]
            position += chunk
            filled += chunk
        if position >= total_frames:
            raise sd.CallbackStop()

    print(f'Playing {file_path.name} up to {loops} time(s) at 24000 Hz.')
    print('Press Q to stop preview early and return to the selection menu.')
    stopped_early = False
    try:
        with sd.OutputStream(samplerate=24000, channels=1, dtype='int16', callback=callback,
                             finished_callback=completed.set):
            while not completed.wait(timeout=0.05):
                if os.name == 'nt' and msvcrt.kbhit():
                    key = msvcrt.getwch()
                    if key in ('\x00', '\xe0'):
                        msvcrt.getwch()  # Consume special-key scan code.
                    elif key.lower() == 'q':
                        stopped_early = True
                        stop_requested.set()
                        completed.wait(timeout=1.0)
                        break
    except KeyboardInterrupt:
        stop_requested.set()
        print('\nPlayback interrupted.')
        return
    except sd.PortAudioError as exc:
        print(f'[ERROR] Audio device: {exc}')
        raise RuntimeError(f'Audio device: {exc}') from exc
    print('Playback stopped. Returning to selection menu.' if stopped_early else 'Playback finished.')


if __name__ == '__main__':
    main()
