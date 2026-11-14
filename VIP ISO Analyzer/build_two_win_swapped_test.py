"""Swap only win1/win3 payload references in the verified two-song test ISO."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys

ROOT = Path(__file__).resolve().parent
TEST = ROOT/'Two_Win_Skip2_Test'
sys.path.insert(0,str(ROOT.parent/'UI Custom Gameplay Music Tools/supporting_tools'))
from hash_build import get_hash_func
CHUNK=8*1024*1024


def hash_extent(stream,offset,size):
    stream.seek(offset)
    value=hashlib.sha256()
    while size:
        block=stream.read(min(size,CHUNK))
        if not block: raise ValueError('Truncated input')
        value.update(block); size-=len(block)
    return value.hexdigest()


def main():
    global TEST
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test-dir',type=Path,default=TEST,help='Folder containing the first test ISO and result.json')
    TEST=parser.parse_args().test_dir.resolve()
    original=json.loads((TEST/'result.json').read_text())
    # Resolve beside this script's test folder after cloning on another PC.
    source=TEST/'MC3_Retail_Two_Win_1_and_3.iso'
    output=TEST/'MC3_Retail_Two_Win_1_and_3_SWAPPED.iso'
    partial=output.with_suffix('.iso.partial')
    report=TEST/'swapped_result.json'
    if any(p.exists() for p in (output,partial,report)):
        raise FileExistsError('Refusing to overwrite a previous swapped test')
    if shutil.disk_usage(TEST).free<source.stat().st_size+128*1024*1024:
        raise ValueError('Insufficient space for a separate test ISO')
    hashes=get_hash_func('MClub')
    wanted={hashes(f'Music/Win_Lose/{stem}.rsm'):stem for stem in ('win1','win3')}
    mappings={entry['slot']:entry for entry in original['mapping']}
    with source.open('rb') as inp:
        inp.seek(16*2048); pvd=inp.read(2048)
        assert pvd[:6]==b'\x01CD001'
        root_sector=struct.unpack_from('<I',pvd,158)[0]
        root_size=struct.unpack_from('<I',pvd,166)[0]
        assert 0<root_size<=2048
        inp.seek(root_sector*2048); directory=inp.read(root_size)
        pos=0; archive=None
        while pos<len(directory) and directory[pos]:
            length=directory[pos]; assert length>=34 and pos+length<=len(directory)
            name=directory[pos+33:pos+33+directory[pos+32]]
            if name==b'STREAMS.DAT;1':
                archive=(struct.unpack_from('<I',directory,pos+2)[0]*2048,struct.unpack_from('<I',directory,pos+10)[0])
            pos+=length
        assert archive is not None
        base,size=archive
        inp.seek(base); magic,count=struct.unpack('<4sI',inp.read(8))
        assert magic==b'Hash' and 0<count<100000 and 8+count*12<size
        table=inp.read(count*12); entries={}
        for index in range(count):
            key,offset,length=struct.unpack_from('<III',table,index*12)
            assert offset+length<=size
            if key in wanted:
                stem=wanted[key]; assert stem not in entries
                assert length>=2048 and offset>=8+count*12
                assert hash_extent(inp,base+offset,length)==mappings[stem]['rsm_sha256']
                entries[stem]=(index,offset,length)
        assert set(entries)=={'win1','win3'}
        # Keep filename hashes in place; exchange the offset/length pairs only.
        patches=[]
        for target,other in (('win1','win3'),('win3','win1')):
            index,_,_=entries[target]
            _,offset,length=entries[other]
            patches.append((base+8+index*12+4,struct.pack('<II',offset,length)))
    patches.sort()
    print('Copying and authenticating first test ISO; swapping two record references only...',flush=True)
    source_hash=hashlib.sha256()
    with source.open('rb') as inp,partial.open('xb') as out:
        while block:=inp.read(CHUNK):
            source_hash.update(block); out.write(block)
    if source_hash.hexdigest()!=original['iso_sha256']:
        raise ValueError('Original test ISO fingerprint mismatch; partial is not usable')
    with partial.open('r+b') as out:
        for offset,payload in patches:
            out.seek(offset); out.write(payload)
    print('Comparing every byte with the first ISO plus the two exact record patches...',flush=True)
    output_hash=hashlib.sha256(); position=0
    with source.open('rb') as inp,partial.open('rb') as out:
        while block:=inp.read(CHUNK):
            expected=bytearray(block)
            for offset,payload in patches:
                low=max(position,offset); high=min(position+len(block),offset+len(payload))
                if low<high: expected[low-position:high-position]=payload[low-offset:high-offset]
            actual=out.read(len(block)); assert actual==expected
            output_hash.update(actual); position+=len(block)
        assert not out.read(1)
        for target,other in (('win1','win3'),('win3','win1')):
            index,_,_=entries[target]
            out.seek(base+8+index*12)
            key,offset,length=struct.unpack('<III',out.read(12))
            assert key==hashes(f'Music/Win_Lose/{target}.rsm')
            assert hash_extent(out,base+offset,length)==mappings[other]['rsm_sha256']
    partial.rename(output)
    mapping=[dict(mappings[other],slot=target) for target,other in (('win1','win3'),('win3','win1'))]
    result=dict(iso=str(output),iso_sha256=output_hash.hexdigest(),source_iso=str(source),
                source_sha256=source_hash.hexdigest(),mapping=mapping,
                only_two_streams_offset_size_pairs_changed=True,all_other_bytes_identical=True,
                audio_payloads_not_reencoded=True,playlists_unchanged=True,num_songs=2,
                playlist_entries=original['playlist_entries'],lose_unchanged=True,
                active_workspace_and_production_code_not_written=True,runtime_status='NOT TESTED')
    report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':
    main()
