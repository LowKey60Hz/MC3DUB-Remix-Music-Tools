"""Prepare an isolated music excerpt, encode, decode and measure the prototype."""
import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import wave

import numpy as np
from python_rsm_encoder import encode_wav
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'UI Custom Gameplay Music Tools/supporting_tools'))
from audio_processor import convert as prepare_audio
from rsm_decoder import convert as decode


def digest(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''): value.update(block)
    return value.hexdigest()


def measure(source,output,seconds):
    source=Path(source).resolve(); output=Path(output).resolve()
    before=digest(source)
    output.mkdir(parents=True,exist_ok=False)
    pcm=output/'reference.wav'; rsm=output/'prototype.rsm'; restored=output/'decoded.wav'
    with tempfile.TemporaryDirectory(prefix='prepare_',dir=output) as temp:
        full=Path(temp)/'prepared.wav'
        prepare_audio(source,full)
        with wave.open(str(full),'rb') as audio:
            params=audio.getparams()
            data=audio.readframes(min(audio.getnframes(),round(seconds*audio.getframerate())))
        with wave.open(str(pcm),'wb') as out:
            out.setparams(params); out.writeframes(data)
    report=encode_wav(pcm,rsm)
    with contextlib.redirect_stdout(io.StringIO()): decode(rsm,restored,None)
    with wave.open(str(restored),'rb') as audio:
        actual=np.frombuffer(audio.readframes(audio.getnframes()),dtype='<i2').reshape(-1,audio.getnchannels())
    expected=np.frombuffer(data,dtype='<i2').reshape(-1,report['channels'])
    comparison=actual[:len(expected)].astype(np.float64)
    original=expected.astype(np.float64)
    error=comparison-original
    qualities=[]
    for channel in range(report['channels']):
        power=float(np.sum(original[:,channel]**2)); noise=float(np.sum(error[:,channel]**2))
        qualities.append({'channel':channel,'snr_db':10*np.log10(power/noise) if power and noise else None,
                         'correlation':float(np.corrcoef(original[:,channel],comparison[:,channel])[0,1]) if power else None,
                         'mean_error_pcm':float(np.mean(error[:,channel])),
                         'max_absolute_error_pcm':float(np.max(np.abs(error[:,channel])))})
    assert digest(source)==before
    report.update(source=str(source),source_sha256=before,source_unchanged=True,
                  encoded_rsm_sha256=digest(rsm),quality=qualities,
                  reference_wav=str(pcm),decoded_wav=str(restored),rsm=str(rsm),
                  decoder='Existing project Python decoder; independent decoder and game playback still required',
                  production_converter_changed=False,security_settings_changed=False)
    (output/'measurements.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seconds',type=float,default=10)
    args=parser.parse_args()
    if not 0 < args.seconds <= 300: parser.error('Excerpt must be between 0 and 300 seconds')
    measure(args.source,args.output,args.seconds)
