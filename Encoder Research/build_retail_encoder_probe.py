"""Put the prototype RSM into the original Retail main-menu slot only.

All archive offsets, other payloads, metadata and both-layer image size remain
unchanged. No active workspace files or conversion tools are modified.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys

ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parent/'UI Custom Gameplay Music Tools'
sys.path.insert(0,str(PROJECT/'supporting_tools'))
from hash_build import get_hash_func
from MC3_ISO_Extractor import TRUSTED_RETAIL_SHA256
CHUNK=8*1024*1024


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT.parent/"Base ISO's/Midnight Club 3 - DUB Edition Remix (USA).iso")
    parser.add_argument('--rsm',type=Path,default=ROOT/'artifacts/brazilian_phonk_10s/prototype.rsm')
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/MC3_Retail_Python_Encoder_Menu_Test.iso')
    args=parser.parse_args()
    source,rsm,output=(p.resolve() for p in (args.source,args.rsm,args.output))
    partial=output.with_suffix('.iso.partial'); report=output.with_suffix('.json')
    if source==output or source.stat().st_size!=8539963392:
        raise ValueError('Expected original Retail source and a separate output')
    if any(p.exists() for p in (output,partial,report)):
        raise FileExistsError('Refusing to overwrite an existing probe')
    if shutil.disk_usage(output.parent).free<source.stat().st_size+128*1024*1024:
        raise ValueError('Insufficient space for one separate ISO')
    payload=rsm.read_bytes()
    assert payload[:4]==b'RSTM' and len(payload)>2048
    rate,channels=struct.unpack_from('<II',payload,8)
    audio_bytes=struct.unpack_from('<I',payload,0x18)[0]
    assert 8000<=rate<=48000 and channels in (1,2) and audio_bytes==len(payload)-2048
    assert audio_bytes%(16*channels)==0
    target='Music/HipHop/MFresh_FrontEnd.rsm'
    target_hash=get_hash_func('MClub')(target)
    with source.open('rb') as inp:
        inp.seek(16*2048); pvd=inp.read(2048)
        assert pvd[:6]==b'\x01CD001'
        root_sector=struct.unpack_from('<I',pvd,158)[0]; root_size=struct.unpack_from('<I',pvd,166)[0]
        assert 0<root_size<=2048
        inp.seek(root_sector*2048); directory=inp.read(root_size)
        position=0; archive=None
        while position<len(directory) and directory[position]:
            length=directory[position]; assert length>=34 and position+length<=len(directory)
            name=directory[position+33:position+33+directory[position+32]]
            if name==b'STREAMS.DAT;1':
                archive=(struct.unpack_from('<I',directory,position+2)[0]*2048,struct.unpack_from('<I',directory,position+10)[0])
            position+=length
        assert archive is not None
        base,allocation=archive
        inp.seek(base); magic,count=struct.unpack('<4sI',inp.read(8))
        assert magic==b'Hash' and 0<count<100000
        table=inp.read(count*12)
        records=[struct.unpack_from('<III',table,index*12) for index in range(count)]
        matches=[(index,row) for index,row in enumerate(records) if row[0]==target_hash]
        assert len(matches)==1
        index,(_,offset,stored)=matches[0]
        assert offset>=8+count*12 and offset+stored<=allocation and len(payload)<=stored
        for other,(_,start,size) in enumerate(records):
            assert not size or other==index or start+size<=offset or start>=offset+stored, 'Shared target payload needs separate handling'
        inp.seek(base+offset); assert inp.read(4)==b'RSTM'
    patches=sorted([(base+offset,payload),(base+8+index*12+8,struct.pack('<I',len(payload)))])
    print('Copying and fingerprinting original Retail ISO...',flush=True)
    source_hash=hashlib.sha256()
    with source.open('rb') as inp,partial.open('xb') as out:
        while block:=inp.read(CHUNK): source_hash.update(block); out.write(block)
    if source_hash.hexdigest()!=TRUSTED_RETAIL_SHA256:
        raise ValueError('Source is not the trusted original Retail ISO; partial output is unusable')
    with partial.open('r+b') as out:
        for start,data in patches: out.seek(start); out.write(data)
    print('Verifying every ISO byte against the original plus exact menu-audio patches...',flush=True)
    output_hash=hashlib.sha256(); position=0
    with source.open('rb') as inp,partial.open('rb') as out:
        while original:=inp.read(CHUNK):
            expected=bytearray(original)
            for start,data in patches:
                low=max(position,start); high=min(position+len(original),start+len(data))
                if low<high: expected[low-position:high-position]=data[low-start:high-start]
            actual=out.read(len(original)); assert actual==expected
            output_hash.update(actual); position+=len(original)
        assert not out.read(1)
        out.seek(base+offset); assert out.read(len(payload))==payload
        out.seek(base+8+index*12)
        assert struct.unpack('<III',out.read(12))==(target_hash,offset,len(payload))
    partial.rename(output)
    result={'iso':str(output),'iso_sha256':output_hash.hexdigest(),'source_sha256':source_hash.hexdigest(),
            'prototype_rsm':str(rsm),'prototype_rsm_sha256':hashlib.sha256(payload).hexdigest(),
            'target':target,'replacement_bytes':len(payload),'old_slot_bytes':stored,
            'audio_seconds':audio_bytes//(16*channels)*28/rate,'all_archive_offsets_unchanged':True,
            'all_bytes_outside_target_payload_and_one_size_field_identical':True,
            'active_workspace_and_production_tools_not_written':True,'legacy_encoder_executed':False,
            'security_settings_changed':False,'runtime_status':'NOT TESTED',
            'test':'Cold boot exact ISO without emulator save state; reach main menu and listen for the Brazilian phonk excerpt. Check distortion, channels, clipping, transitions, and repeated menu visits.'}
    report.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':
    main()
