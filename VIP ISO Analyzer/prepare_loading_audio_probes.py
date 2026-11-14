"""Create isolated exact-size PCM calibration clips; never touches game files."""
import hashlib
import json
import math
from pathlib import Path
import struct
import wave

RATE = 24000
SIZES = (432000, 460800, 460802, 480000, 576000)
ROOT = Path(__file__).resolve().parent / 'Loading_Audio_Probes'


def prepare():
    # Fail closed rather than overwrite prior clips or their manifest.
    ROOT.mkdir(exist_ok=False)
    rows = []
    # Identical prefixes: quiet repeating notes with a higher marker each second.
    master = bytearray()
    for sample in range(max(SIZES) // 2):
        t = sample / RATE
        phase = t % 1.0
        frequency = 880 if phase < .12 else 440
        envelope = min(1, phase / .005, (1-phase) / .005)
        value = round(4096 * envelope * math.sin(2 * math.pi * frequency * t))
        master.extend(struct.pack('<h', value))
    for size in SIZES:
        stem = f'loading_{size}_bytes'
        raw = bytes(master[:size])
        raw_path = ROOT / (stem + '.raw')
        wav_path = ROOT / (stem + '.wav')
        raw_path.write_bytes(raw)
        with wave.open(str(wav_path), 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(RATE)
            audio.writeframes(raw)
        assert raw_path.stat().st_size == size
        with wave.open(str(wav_path), 'rb') as audio:
            assert audio.readframes(audio.getnframes()) == raw
        rows.append(dict(raw=raw_path.name, preview_wav=wav_path.name,
                         bytes=size, samples=size//2, seconds=size/48000,
                         sha256=hashlib.sha256(raw).hexdigest(),
                         exceeds_production_cap=size>460800))
    report = dict(format='s16le', sample_rate=RATE, channels=1,
                  purpose='Exact-size synthetic runtime probes, not converted music. WAVs are previews; RAWs are archive payloads.',
                  status='Prepared only; not inserted into an archive or tested in PCSX2.',
                  production_code_modified=False, probes=rows)
    (ROOT / 'manifest.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    prepare()
