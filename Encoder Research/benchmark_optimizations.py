"""Isolated A/B benchmarks; production and installed music are never written."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import statistics
import struct
import time
import wave
import numpy as np
import soundfile as sf

import reference_ps_adpcm_encoder_v1 as reference
import optimized_candidate as candidate


def verify_blocks():
    rng=random.Random(754)
    cases=[[0]*28,[32767,-32768]*14,[1000]*28]
    cases += [[rng.randint(-32768,32767) for _ in range(28)] for _ in range(300)]
    for history in ([0,0],[32767,-32768],[-2000,1800]):
        a=list(history); b=list(history)
        for samples in cases:
            if reference.encode_block(samples,a)!=candidate.encode_block(samples,b) or a!=b:
                raise ValueError('Block or history differs from reference')
    return len(cases)*3


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=int,default=12)
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    output=args.output.resolve(); output.mkdir(parents=True,exist_ok=False)
    root=Path(__file__).resolve().parent.parent
    source=root/'UI Custom Gameplay Music Tools/Custom Music/1_Dancehall/alex-productions - brazilian phonk.mp3'
    with sf.SoundFile(source) as audio:
        assert audio.samplerate==44100 and audio.channels==2
        samples=audio.read(frames=args.seconds*44100,dtype='float64',always_2d=True)
    pcm=np.rint(np.clip(samples,-1,32767/32768)*32768).astype('<i2')
    wav=output/'input.wav'
    with wave.open(str(wav),'wb') as audio:
        audio.setparams((2,2,44100,0,'NONE','not compressed')); audio.writeframes(pcm.tobytes())
    comparisons=verify_blocks()
    times={'reference':[],'optimized_serial':[],'optimized_parallel':[]}
    expected=None
    # Rotate order to reduce bias from filesystem warmth and other active tasks.
    for repeat in range(args.repeats):
        order=['reference','optimized_serial','optimized_parallel']
        order=order[repeat%3:]+order[:repeat%3]
        for mode in order:
            path=output/f'{mode}_{repeat}.rsm'
            start=time.perf_counter()
            if mode=='reference': reference.encode_wav(wav,path)
            else: candidate.encode_wav(wav,path,workers=2 if mode=='optimized_parallel' else 1)
            elapsed=time.perf_counter()-start
            data=path.read_bytes()
            digest=hashlib.sha256(data).hexdigest()
            if expected is None: expected=digest
            if digest!=expected:raise ValueError('Whole RSM bytes differ in '+mode)
            times[mode].append(elapsed)
            print(f'{mode}: {elapsed:.3f}s; byte-identical',flush=True)
    medians={key:statistics.median(values) for key,values in times.items()}
    result={'audio_seconds':len(pcm)/44100,'runs':times,'median_seconds':medians,
            'serial_speedup':medians['reference']/medians['optimized_serial'],
            'parallel_speedup':medians['reference']/medians['optimized_parallel'],
            'block_history_comparisons':comparisons,'all_rsm_bytes_identical':True,'sha256':expected,
            'scope':'Real stereo excerpt; other user conversions may be active. No production or installed music written.'}
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
