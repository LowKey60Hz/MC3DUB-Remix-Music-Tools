"""Measure isolated preparation + RSM throughput; never installs game music."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    tools = root/'UI Custom Gameplay Music Tools/supporting_tools'
    source = root/'UI Custom Gameplay Music Tools/Custom Music/1_Dancehall/alex-productions - brazilian phonk.mp3'
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)

    def convert(job):
        mode, index = job
        folder = output/f'{mode}_{index}'
        folder.mkdir()
        timings = {}
        for stage, command in (
            ('prepare', [sys.executable, str(tools/'audio_processor.py'), str(source), '-o', str(folder/'input.wav')]),
            ('encode', [sys.executable, str(tools/'rstm_build.py'), str(folder/'input.wav'), '-o', str(folder/'output.rsm')]),
        ):
            started = time.perf_counter()
            result = subprocess.run(command, capture_output=True, text=True)
            (folder/f'{stage}.log').write_text(result.stdout+result.stderr, encoding='utf-8')
            if result.returncode:
                raise RuntimeError(f'{stage} failed; see {folder}')
            timings[stage] = time.perf_counter()-started
        timings['sha256'] = hashlib.sha256((folder/'output.rsm').read_bytes()).hexdigest()
        return timings

    results = {}
    for concurrency in (1, 3):
        mode = f'concurrency_{concurrency}'
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            tracks = list(pool.map(convert, [(mode,i) for i in range(3)]))
        results[mode] = {'batch_seconds':time.perf_counter()-started, 'tracks':tracks}
        print(json.dumps({mode:results[mode]}), flush=True)
    digests = {track['sha256'] for mode in results.values() for track in mode['tracks']}
    if len(digests) != 1:
        raise ValueError('Batch outputs differ')
    results['byte_identical'] = True
    results['speedup'] = results['concurrency_1']['batch_seconds']/results['concurrency_3']['batch_seconds']
    results['scope'] = 'Three copies of one 92.34-second stereo song; includes fresh Python preparation/encoder process startup. No game data writes.'
    (output/'result.json').write_text(json.dumps(results, indent=2)+'\n', encoding='utf-8')
    print(f'All RSM files identical; batch speedup {results["speedup"]:.2f}x', flush=True)


if __name__ == '__main__':
    main()
