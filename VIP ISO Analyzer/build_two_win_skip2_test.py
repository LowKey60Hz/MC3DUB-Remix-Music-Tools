"""Isolated Retail runtime test of two distinct songs in win1/win3.

Does not alter the production Win/Lose engine or active extracted workspace.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zlib

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent/'UI Custom Gameplay Music Tools'
TOOLS = PROJECT/'supporting_tools'
TEST = ROOT/'Two_Win_Skip2_Test'
sys.path.insert(0,str(TOOLS))
sys.path.insert(0,str(PROJECT/'gui'))
from sync_winlose_folders import encode
from race_playlist import read_race_tracks
from MC3_ISO_Builder_V11A import verify_streams
from MC3_VIP_Archive_Entry_Analyzer import analyze


def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):
            value.update(block)
    return value.hexdigest()


def snapshot(root):
    return {p.relative_to(root).as_posix():digest(p)
            for folder in ('ASSETS','STREAMS') for p in (root/folder).rglob('*') if p.is_file()}


def run(command,log):
    print('Running '+Path(command[2] if command[1]=='-u' else command[1]).name,flush=True)
    with log.open('a',encoding='utf-8') as saved:
        saved.write('\nCOMMAND '+repr(command)+'\n'); saved.flush()
        result=subprocess.run(command,stdout=saved,stderr=subprocess.STDOUT,cwd=TEST)
    if result.returncode:
        raise RuntimeError(f'Command failed ({result.returncode}); see {log}')


def main():
    global TEST
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test-dir',type=Path,default=TEST,help='New isolated output folder; existing completed tests are never overwritten')
    parser.add_argument('--resume',action='store_true',help='Resume interrupted preparation before compilation only')
    parser.add_argument('--source-workspace',type=Path,default=PROJECT,help='Read-only extracted Retail source, separate from the tools project')
    args=parser.parse_args()
    TEST=args.test_dir.resolve()
    source_workspace=args.source_workspace.resolve(strict=True)
    # Output must not be in any active workspace directory.
    if TEST==PROJECT.resolve() or TEST.is_relative_to(PROJECT.resolve()):
        raise ValueError('Test output must be outside the active tools project')
    if (TEST==source_workspace or TEST.is_relative_to(source_workspace)
            or source_workspace.is_relative_to(TEST)):
        raise ValueError('Test output and source workspace must not overlap')
    if any(not (source_workspace/name).is_dir() for name in ('ASSETS','STREAMS','ISO_FILES')):
        raise ValueError('Source workspace needs ASSETS, STREAMS and ISO_FILES')
    resume=args.resume
    if TEST.exists() and not resume:
        raise FileExistsError('Refusing to overwrite existing test workspace')
    if resume and (not (TEST/'active_before.json').is_file() or (TEST/'result.json').exists()
                   or (TEST/'ISO_FILES').exists()):
        raise ValueError('Resume is restricted to an interrupted preparation before compilation')
    if (source_workspace/'ISO_FILES/MC3_PROFILE.txt').read_text().strip()!='retail':
        raise ValueError('This isolated test is Retail only')
    source=Path((source_workspace/'ISO_FILES/MC3_SOURCE_ISO.txt').read_text().strip())
    songs=sorted((p for p in (PROJECT/'Custom Music/2_Win').iterdir()
                  if p.is_file() and p.suffix.lower() in ('.mp3','.wav')),key=lambda p:(p.name.casefold(),p.name))[:2]
    if len(songs)!=2 or digest(songs[0])==digest(songs[1]):
        raise ValueError('Need two distinct staged Win sources')
    total=sum(p.stat().st_size for name in ('ASSETS','STREAMS') for p in (source_workspace/name).rglob('*') if p.is_file())
    needed = source.stat().st_size + (total if resume else 2*total) + 512*1024*1024
    if shutil.disk_usage(ROOT).free < needed:
        raise ValueError('Not enough free space for isolated sources, compiled archives and one ISO')
    if not resume:
        TEST.mkdir()
    log=TEST/'build.log'
    production_engine_hash=digest(TOOLS/'sync_winlose_folders.py')
    active_before=snapshot(PROJECT)
    if resume:
        before=json.loads((TEST/'active_before.json').read_text())
        print('Resuming isolated preparation; final checks will verify all unchanged files.',flush=True)
    else:
        print('Recording active workspace hashes...',flush=True)
        before=snapshot(source_workspace)
        (TEST/'active_before.json').write_text(json.dumps(before,indent=2))
        print('Copying ASSETS and STREAMS into isolated workspace...',flush=True)
        for folder in ('ASSETS','STREAMS'):
            shutil.copytree(source_workspace/folder,TEST/folder)
        if snapshot(TEST)!=before:
            raise ValueError('Isolated copy differs from active snapshot')
    isolated_tools=TEST/'supporting_tools'
    isolated_tools.mkdir(exist_ok=True)
    for name in ('audio_processor.py','rstm_build.py','ps2str.exe','MFAudio.exe','encvag.dll'):
        if (TOOLS/name).is_file(): shutil.copy2(TOOLS/name,isolated_tools/name)
    # Only isolated custom Win files are replaced; Lose is never edited.
    folder=TEST/'STREAMS/Music/Win_Lose'
    for path in folder.iterdir():
        if path.is_file() and re.fullmatch(r'win\d+\.rsm',path.name,re.I):
            path.unlink()
    mapping=[]
    with tempfile.TemporaryDirectory(prefix='encode_',dir=TEST) as temp:
        scratch=Path(temp)
        for song,stem in zip(songs,('win1','win3')):
            print(f'Encoding {song.name} -> {stem}.rsm',flush=True)
            output=folder/(stem+'.rsm')
            encode(song,output,isolated_tools,scratch)
            mapping.append(dict(source=song.name,source_sha256=digest(song),slot=stem,rsm_sha256=digest(output)))
    if mapping[0]['rsm_sha256']==mapping[1]['rsm_sha256']:
        raise ValueError('The two encoded songs are identical')
    playlists=sorted((TEST/'ASSETS/tune/audio/playlist').glob('city/*/music/*_raceover_music.play'))
    if len(playlists)!=24:
        raise ValueError(f'Expected 24 Win playlists, found {len(playlists)}')
    for path in playlists:
        raw=path.read_bytes()
        newline='\r\n' if b'\r\n' in raw else '\n'
        content=newline.join(['num_songs: 2',r'music\Win_Lose\win1',r'music\Win_Lose\win3'])+newline
        path.write_bytes((b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b'')+content.encode())
    assert read_race_tracks(TEST,'Win')==[r'music\Win_Lose\win1',r'music\Win_Lose\win3']
    assert read_race_tracks(TEST,'Lose')==read_race_tracks(source_workspace,'Lose')
    after=snapshot(TEST)
    allowed={p.relative_to(TEST).as_posix() for p in playlists}
    for name in set(before)|set(after):
        is_win=re.fullmatch(r'STREAMS/Music/Win_Lose/win\d+\.rsm',name,re.I)
        if before.get(name)!=after.get(name) and name not in allowed and not is_win:
            raise ValueError('Unexpected isolated workspace change: '+name)
    workspace=TEST/'ISO_FILES'; workspace.mkdir()
    for path in (source_workspace/'ISO_FILES').glob('MC3_*.txt'):
        shutil.copy2(path,workspace/path.name)
    run([sys.executable,'-u',str(TOOLS/'dave.py'),'B','-ca','-cn','-cf','-fc','1',str(TEST/'ASSETS'),str(workspace/'ASSETS.DAT')],log)
    run([sys.executable,'-u',str(TOOLS/'hash_build.py'),'B',str(TEST/'STREAMS'),str(workspace/'STREAMS.DAT'),'-a','MClub'],log)
    print('Verifying compiled ASSETS and STREAMS against isolated sources...',flush=True)
    entries=analyze(workspace/'ASSETS.DAT',None,1)['all_entries']
    files=[entry for entry in entries if not entry['directory_record']]
    assert {e['name'] for e in files}=={p.relative_to(TEST/'ASSETS').as_posix() for p in (TEST/'ASSETS').rglob('*') if p.is_file()}
    with (workspace/'ASSETS.DAT').open('rb') as stream:
        for entry in files:
            stream.seek(entry['data_offset']); payload=stream.read(entry['stored_size'])
            raw=zlib.decompress(payload,-15) if entry['compressed'] else payload
            assert len(raw)==entry['full_size']
            assert hashlib.sha256(raw).hexdigest()==after['ASSETS/'+entry['name']]
    verify_streams(workspace/'STREAMS.DAT',TEST/'STREAMS',workspace/'STREAMS.LST')
    output=TEST/'MC3_Retail_Two_Win_1_and_3.iso'
    run([sys.executable,'-u',str(TOOLS/'MC3_ISO_Builder_Retail.py'),'--profile','retail','--relocate-archives','--source',str(source),'--replacement-dir',str(workspace),'--manifest',str(workspace/'STREAMS.LST'),'--output',str(output),'--yes'],log)
    print('Confirming active workspace and production engine remain unchanged...',flush=True)
    assert snapshot(source_workspace)==before
    assert snapshot(PROJECT)==active_before
    assert digest(TOOLS/'sync_winlose_folders.py')==production_engine_hash
    result=dict(iso=str(output),iso_sha256=digest(output),mapping=mapping,win_playlist_count=24,
                playlist_entries=[r'music\Win_Lose\win1',r'music\Win_Lose\win3'],num_songs=2,
                win2_present=False,lose_and_other_assets_unchanged=True,active_workspace_unchanged=True,
                production_engine_unchanged=True,compiled_archives_verified=True,runtime_status='NOT TESTED')
    result.update(source_workspace=str(source_workspace),source_workspace_unchanged=True)
    (TEST/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':
    main()
