#!/usr/bin/env python3
"""MC3 experimental audio preparation: decode common audio to 44.1kHz stereo PCM16 WAV.

Does not change the game's RSM encoder or loading-screen RAW workflow.
Requires: numpy, scipy, soundfile. Decoder format availability depends on libsndfile.
"""
import argparse
import math
import os
import sys
import tempfile
import wave
from pathlib import Path


def convert(source: Path, destination: Path) -> None:
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly

    if not source.is_file():
        raise FileNotFoundError(f"Input file not found: {source}")
    if source.resolve() == destination.resolve():
        raise ValueError("Input and output must be different files")
    samples, sample_rate = sf.read(str(source), dtype='float64', always_2d=True)
    if samples.shape[0] == 0 or sample_rate <= 0:
        raise ValueError("Input audio is empty or has an invalid sample rate")
    if not np.isfinite(samples).all():
        raise ValueError("Input audio contains non-finite samples")
    if samples.shape[1] == 1:
        samples = np.repeat(samples, 2, axis=1)
    elif samples.shape[1] > 2:
        raise ValueError("Multichannel audio is not yet supported; use mono or stereo")
    if sample_rate != 44100:
        common = math.gcd(int(sample_rate), 44100)
        samples = resample_poly(samples, 44100 // common, int(sample_rate) // common, axis=0)
    # PCM signed 16-bit: clip to representable interval and round to nearest integer.
    samples = np.clip(samples, -1.0, 32767 / 32768)
    pcm = np.rint(samples * 32768).astype('<i2')
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.mc3_audio_', suffix='.wav', dir=str(destination.parent))
    os.close(fd)
    try:
        with wave.open(temporary, 'wb') as out:
            out.setnchannels(2)
            out.setsampwidth(2)
            out.setframerate(44100)
            out.writeframes(pcm.tobytes())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    parser = argparse.ArgumentParser(description='Prepare stereo 44.1 kHz PCM16 WAV without FFmpeg')
    parser.add_argument('input', type=Path)
    parser.add_argument('-o', '--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        convert(args.input, args.output)
    except Exception as exc:
        print(f'[ERROR] Python audio conversion failed: {exc}', file=sys.stderr)
        return 1
    print(f'[OK] WAV created: {args.output}')
    return 0

if __name__ == '__main__':
    sys.exit(main())
