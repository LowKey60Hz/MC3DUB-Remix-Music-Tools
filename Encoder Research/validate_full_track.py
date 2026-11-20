"""Run the normal Add Tracks conversion stage on one full song in isolation."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time
import soundfile as sf

ROOT=Path(__file__).resolve().parent
TOOLS=ROOT.parent/'UI Custom Gameplay Music Tools/supporting_tools'


def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--verify-existing',action='store_true',help='Recheck an existing isolated conversion without encoding it again')
    args=parser.parse_args()
    source=args.source.resolve(); root=args.output.resolve()
    before=digest(source); info=sf.info(source)
    # MP3 duration metadata may not equal libsndfile's returned PCM length.
    decoded,decoded_rate=sf.read(source,dtype='int16',always_2d=True)
    source_frames=len(decoded)
    del decoded
    if not args.verify_existing:
        root.mkdir(parents=True,exist_ok=False)
    elif not root.is_dir() or (root/'result.json').exists():
        raise ValueError('Expected an unfinished isolated validation directory')
    tools=root/'supporting_tools'
    music=root/'STREAMS/Music/Dancehall'
    started=time.perf_counter()
    if not args.verify_existing:
        tools.mkdir()
        for name in ('audio_processor.py','rstm_build.py','ps_adpcm_encoder.py','add_gameplay_songs.py'):
            shutil.copy2(TOOLS/name,tools/name)
        staging=root/'Custom Music/1_Dancehall'; staging.mkdir(parents=True)
        shutil.copy2(source,staging/source.name)
        music.mkdir(parents=True)
        print('Converting full track with the normal Add Tracks backend in a Python-only fixture...',flush=True)
        with (root/'conversion.log').open('w',encoding='utf-8') as log:
            result=subprocess.run([sys.executable,'-u',str(tools/'add_gameplay_songs.py'),str(root),'--yes'],stdout=log,stderr=subprocess.STDOUT)
        if result.returncode:raise RuntimeError('Conversion failed; inspect '+str(root/'conversion.log'))
    else:
        assert digest(root/'Custom Music/1_Dancehall'/source.name)==before
    files=list(music.glob('*.rsm')); assert len(files)==1
    output=files[0]; data=output.read_bytes(); assert data[:4]==b'RSTM'
    rate,channels=struct.unpack_from('<II',data,8)
    payload,start,end=struct.unpack_from('<III',data,0x18)
    assert (rate,channels)==(44100,2) and payload==len(data)-2048
    assert start==0 and end==payload and payload%32==0
    encoded_samples=payload//32*28
    expected=(source_frames*44100+decoded_rate-1)//decoded_rate
    assert 0<=encoded_samples-expected<28
    raw=data[2048:]
    assert all(value==0 for value in raw[1::16])
    assert all(value>>4<5 and value&15<=12 for value in raw[::16])
    assert not list(tools.glob('*.exe')) and not list(tools.glob('*.dll'))
    assert not list(root.glob('Music_Add_Temp_*'))
    assert digest(source)==before
    report={'source':str(source),'source_unchanged':True,'source_sha256':before,
            'source_seconds':source_frames/decoded_rate,'source_metadata_seconds':info.duration,
            'rsm':str(output),'rsm_sha256':digest(output),
            'rsm_bytes':len(data),'encoding_and_preparation_seconds':None if args.verify_existing else time.perf_counter()-started,
            'sample_rate':rate,'channels':channels,'decoded_samples_per_channel':encoded_samples,
            'expected_pcm_samples_per_channel':expected,'padding_samples_per_channel':encoded_samples-expected,
            'rsm_structure_checks_passed':True,'legacy_exe_dll_absent_from_fixture':True,
            'conversion_temporary_files_cleaned':True,'active_workspace_not_used_as_output':True,
            'runtime_status':'FULL-LENGTH RSM NOT YET TESTED IN GAME'}
    (root/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
