"""Isolated Retail PCM probe: retain all file offsets and filesystem metadata.

Synthetic compressed probes must fit each original stored extent. Every output
byte is compared with the original plus the exact authorized patch set.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import zlib

ROOT = Path(__file__).resolve().parent
CHUNK = 8 * 1024 * 1024


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bytes', type=int, required=True, choices=(432000,446400,453600,455400,455624,455680,455682,455686,455694,455708,455736,455850,456300,457200,460800,460802,480000,576000))
    parser.add_argument('--slot', type=int, choices=range(1,19), help='Omit to replace all 18 slots (aggregate-memory test).')
    args = parser.parse_args()
    survey = json.loads((ROOT/'Retail_Original_Loading_Audio.json').read_text())
    source = Path(survey['source'])
    raw_path = ROOT/'Loading_Audio_Probes'/f'loading_{args.bytes}_bytes.raw'
    raw = raw_path.read_bytes()
    manifest = json.loads((raw_path.parent/'manifest.json').read_text())
    row = next(p for p in manifest['probes'] if p['bytes']==args.bytes)
    assert len(raw)==args.bytes and hashlib.sha256(raw).hexdigest()==row['sha256']
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    stored = compressor.compress(raw)+compressor.flush()
    assert zlib.decompress(stored,-15)==raw and len(stored)<len(raw)
    label = f'slot{args.slot}' if args.slot else 'all18'
    output = raw_path.parent/f'MC3_Retail_Loading_{args.bytes}_{label}.iso'
    partial = output.with_suffix('.iso.partial')
    report = output.with_suffix('.json')
    for path in (output,partial,report):
        if path.exists():
            raise FileExistsError(path)
    if shutil.disk_usage(ROOT).free < source.stat().st_size+128*1024*1024:
        raise ValueError('Insufficient space for one isolated ISO')
    base = survey['assets_sector']*2048
    selected = [r for r in survey['records'] if args.slot is None or r['slot']==args.slot]
    patches = []
    with source.open('rb') as inp:
        inp.seek(base)
        magic,count,table_bytes,names_bytes = struct.unpack('<4sIII',inp.read(16))
        assert magic==b'Dave'
        inp.seek(base+2048)
        table=inp.read(count*16)
        extents=[]
        for index in range(count):
            _,offset,full,size=struct.unpack_from('<IIII',table,index*16)
            if size:
                assert offset>=2048+table_bytes+names_bytes
                assert offset+size<=survey['assets_allocation']
                extents.append((offset,offset+size,index))
        for r in selected:
            index=r['index']
            _,offset,full,size=struct.unpack_from('<IIII',table,index*16)
            assert (offset,full,size)==(r['data_offset'],r['decoded_bytes'],r['stored_bytes'])
            assert len(stored)<=size, 'Probe does not fit original stored extent'
            assert all(other==index or end<=offset or start>=offset+size for start,end,other in extents), 'Shared/overlapping extent requires separate analysis'
            inp.seek(base+offset)
            old=inp.read(size)
            assert hashlib.sha256(zlib.decompress(old,-15)).hexdigest()==r['decoded_sha256']
            patches.extend(((base+offset,stored),(base+2048+index*16+8,struct.pack('<II',len(raw),len(stored)))))
    patches.sort()
    assert all(a+len(b)<=c for (a,b),(c,d) in zip(patches,patches[1:]))
    print(f'Copying trusted Retail source; {len(selected)} records; {len(raw):,} decoded bytes; {len(stored):,} compressed bytes.',flush=True)
    source_hash=hashlib.sha256()
    with source.open('rb') as inp,partial.open('xb') as out:
        while block:=inp.read(CHUNK):
            source_hash.update(block)
            out.write(block)
    if source_hash.hexdigest()!=survey['source_sha256']:
        raise ValueError('Untrusted source; partial output is not usable')
    with partial.open('r+b') as out:
        for offset,payload in patches:
            out.seek(offset)
            out.write(payload)
    print('Verifying every output byte against source plus exact patch ranges...',flush=True)
    output_hash=hashlib.sha256()
    position=0
    with source.open('rb') as inp,partial.open('rb') as out:
        while original:=inp.read(CHUNK):
            expected=bytearray(original)
            for offset,payload in patches:
                low=max(position,offset)
                high=min(position+len(original),offset+len(payload))
                if low<high:
                    expected[low-position:high-position]=payload[low-offset:high-offset]
            actual=out.read(len(original))
            if actual!=expected:
                raise ValueError(f'Unexpected output bytes at chunk {position}')
            output_hash.update(actual)
            position+=len(original)
        assert not out.read(1)
        for r in selected:
            out.seek(base+2048+r['index']*16)
            _,offset,full,size=struct.unpack('<IIII',out.read(16))
            assert (offset,full,size)==(r['data_offset'],len(raw),len(stored))
            out.seek(base+offset)
            assert zlib.decompress(out.read(size),-15)==raw
    partial.rename(output)
    result=dict(iso=str(output),iso_sha256=output_hash.hexdigest(),source_sha256=source_hash.hexdigest(),
                raw_bytes=len(raw),raw_seconds=len(raw)/48000,stored_bytes=len(stored),raw_sha256=row['sha256'],
                slots=sorted({r['slot'] for r in selected}),records=len(selected),all_offsets_preserved=True,
                filesystem_metadata_unchanged=True,every_byte_verified=True,production_files_unchanged=True,
                runtime_status='NOT TESTED',
                caveat='All-18 tests include aggregate-memory effects. Highly compressible synthetic PCM does not test arbitrary compressed sizes or music content.')
    report.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':
    main()
