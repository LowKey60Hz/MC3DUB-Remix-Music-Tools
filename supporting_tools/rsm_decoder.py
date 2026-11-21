#!/usr/bin/env python3
"""Experimental MC3 Rockstar RSTM PSX ADPCM decoder.

Unlike v1, stereo channels alternate every 16-byte ADPCM frame.
This is a test implementation; compare against vgmstream before production use.
"""
import argparse
import struct
import wave
from pathlib import Path

COEFFICIENTS = ((0, 0), (60, 0), (115, -52), (98, -55), (122, -60))
HEADER_SIZE = 0x800
FRAME_BYTES = 16
SAMPLES_PER_FRAME = 28


def decode_frame(frame, history):
    predictor = frame[0] >> 4
    shift = frame[0] & 0x0F
    if predictor >= len(COEFFICIENTS) or shift > 12:
        raise ValueError(f'Invalid PSX ADPCM frame: predictor={predictor}, shift={shift}')
    c1, c2 = COEFFICIENTS[predictor]
    prev1, prev2 = history
    samples = []
    for byte in frame[2:]:
        for nibble in (byte & 0x0F, byte >> 4):
            if nibble >= 8:
                nibble -= 16
            sample = (nibble << 12) >> shift
            sample += (prev1 * c1 + prev2 * c2 + 32) >> 6
            sample = max(-32768, min(32767, sample))
            prev2, prev1 = prev1, sample
            samples.append(sample)
    history[0], history[1] = prev1, prev2
    return samples


def convert(source, output, seconds=20):
    data = Path(source).read_bytes()
    if len(data) < HEADER_SIZE or data[:4] != b'RSTM':
        raise ValueError('Invalid or truncated RSTM file')
    rate, channels = struct.unpack_from('<II', data, 8)
    declared_size = struct.unpack_from('<I', data, 0x18)[0]
    if not (8000 <= rate <= 48000 and channels in (1, 2)):
        raise ValueError(f'Unsupported audio properties: {rate} Hz, {channels} channels')
    if declared_size > len(data) - HEADER_SIZE:
        raise ValueError('Truncated RSTM audio payload')
    payload = memoryview(data)[HEADER_SIZE:HEADER_SIZE + declared_size]
    group_bytes = FRAME_BYTES * channels
    if len(payload) % group_bytes:
        raise ValueError('RSTM audio length is not aligned to complete channel groups')
    groups = len(payload) // group_bytes
    if seconds is not None:
        if seconds <= 0:
            raise ValueError('Preview seconds must be positive')
        groups = min(groups, int(seconds * rate / SAMPLES_PER_FRAME + 0.999999))
    histories = [[0, 0] for _ in range(channels)]
    with wave.open(str(output), 'wb') as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        for group in range(groups):
            pos = group * group_bytes
            decoded = []
            for ch in range(channels):
                frame = payload[pos + ch * FRAME_BYTES:pos + (ch + 1) * FRAME_BYTES]
                decoded.append(decode_frame(frame, histories[ch]))
            pcm = [sample for frame_samples in zip(*decoded) for sample in frame_samples]
            wav.writeframesraw(struct.pack('<' + 'h' * len(pcm), *pcm))
    print(f'Created: {output}\nRate: {rate} Hz; channels: {channels}; duration: {groups * SAMPLES_PER_FRAME / rate:.2f}s')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--seconds', type=float, default=20)
    parser.add_argument('--full', action='store_true')
    args = parser.parse_args()
    convert(args.source, args.output, None if args.full else args.seconds)
