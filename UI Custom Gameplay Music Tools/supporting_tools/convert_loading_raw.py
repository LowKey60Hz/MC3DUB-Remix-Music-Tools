#!/usr/bin/env python3
"""Standalone MC3 loading-screen PCM converter; no ffmpeg executable required."""
import argparse
import math
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

SAMPLE_RATE = 24000
MAX_BYTES = 455680  # 445 KiB: Retail-tested policy applied to all supported versions.


def treble_shelf(samples, sample_rate, frequency=4000.0, gain_db=3.0):
    """RBJ high-shelf biquad approximation of FFmpeg's treble filter."""
    A = 10 ** (gain_db / 40)
    w0 = 2 * math.pi * frequency / sample_rate
    cs, sn = math.cos(w0), math.sin(w0)
    alpha = sn / 2 * math.sqrt(2)  # shelf slope S=1
    root = math.sqrt(A)
    b0 = A * ((A+1) + (A-1)*cs + 2*root*alpha)
    b1 = -2*A * ((A-1) + (A+1)*cs)
    b2 = A * ((A+1) + (A-1)*cs - 2*root*alpha)
    a0 = (A+1) - (A-1)*cs + 2*root*alpha
    a1 = 2*((A-1) - (A+1)*cs)
    a2 = (A+1) - (A-1)*cs - 2*root*alpha
    return signal.lfilter([b0/a0,b1/a0,b2/a0],[1,a1/a0,a2/a0],samples)


def convert(src, dst):
    if not src.is_file():
        raise ValueError(f'Input file not found: {src}')
    if src.resolve() == dst.resolve():
        raise ValueError('Input and output paths must be different.')
    audio, sr = sf.read(str(src), dtype='float64', always_2d=True)
    if audio.shape[0] == 0:
        raise ValueError('Input audio is empty.')
    if sr <= 0:
        raise ValueError('Invalid input sample rate.')
    # Downmix channels; this matches the usual mono downmix for stereo input.
    mono = audio.mean(axis=1)
    from math import gcd
    divisor = gcd(int(sr), SAMPLE_RATE)
    mono = signal.resample_poly(mono, SAMPLE_RATE // divisor, int(sr) // divisor)
    mono = treble_shelf(mono, SAMPLE_RATE)
    mono *= 10 ** (3.0 / 20.0)
    # Match signed 16-bit output; hard clipping if boost exceeds full scale.
    pcm = np.rint(np.clip(mono, -1.0, 32767 / 32768) * 32768).astype('<i2')
    byte_count = pcm.nbytes
    duration = len(pcm) / SAMPLE_RATE
    print(f'[INFO] Source: {src.name} ({sr:,} Hz, {audio.shape[1]} channel(s))')
    print(f'[INFO] Output: 24,000 Hz, mono, signed 16-bit little-endian RAW')
    print(f'[INFO] Duration: {duration:.3f} seconds')
    print(f'[INFO] RAW size: {byte_count:,} bytes (limit {MAX_BYTES:,})')
    if not (0 < byte_count <= MAX_BYTES):
        raise ValueError('Output exceeds the loading-screen RAW limit of 445 KiB (455,680 bytes) or is empty. Shorten the audio to approximately 9.493 seconds or less; the converted byte count determines acceptance. No output was written.')
    dst.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temporary sibling and atomically replace the requested output.
    tmp = dst.with_name(dst.name + '.tmp')
    try:
        tmp.write_bytes(pcm.tobytes())
        tmp.replace(dst)
    finally:
        if tmp.exists():
            tmp.unlink()
    print(f'[SUCCESS] Wrote {dst}')


def main():
    parser = argparse.ArgumentParser(description='Convert MP3/WAV to MC3 24k mono PCM RAW (445 KiB / 455,680-byte output limit, approximately 9.493 seconds; Retail-tested policy applied to all supported versions).')
    parser.add_argument('input', type=Path, help='Source MP3 or WAV')
    parser.add_argument('-o', '--output', type=Path, required=True, help='Output .raw path')
    args = parser.parse_args()
    try:
        convert(args.input, args.output)
    except (OSError, RuntimeError, ValueError, sf.LibsndfileError) as exc:
        print(f'[ERROR] {exc}', file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
