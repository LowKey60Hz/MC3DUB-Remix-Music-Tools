"""Read-only Retail prefix-space/allocation verification for a relocation proposal."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from map_udf_allocations import scan

root=Path(__file__).resolve().parent
sys.path.insert(0,str(root.parent/'UI Custom Gameplay Music Tools/supporting_tools'))
from MC3_ISO_Extractor import TRUSTED_RETAIL_SHA256, sha256_file
source=root.parent/"Base ISO's/Midnight Club 3 - DUB Edition Remix (USA).iso"
if sha256_file(source)!=TRUSTED_RETAIL_SHA256:
    raise ValueError('Retail original fingerprint mismatch')
spec=importlib.util.spec_from_file_location('iso_scan',root/'MC3_VIP_ISO_Analyzer_v0_2.py')
reader=importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)
iso=reader.scan_iso(source,False)
udf=scan(source)
start,end=9702,454764
overlaps=[]
for name,entry in iso['files'].items():
    lo=entry['sector']; hi=lo+(entry['bytes']+2047)//2048
    if lo<end and hi>start:
        overlaps.append({'filesystem':'ISO9660','path':name})
for entry in udf['files']+udf['directories']:
    for extent in entry['extents']:
        lo=extent['sector']; hi=lo+(extent['bytes']+2047)//2048
        if lo<end and hi>start:
            overlaps.append({'filesystem':'UDF','path':entry['path']})
nonzero=0
value=hashlib.sha256()
with source.open('rb') as stream:
    stream.seek(start*2048)
    remaining=(end-start)*2048
    while remaining:
        data=stream.read(min(8388608,remaining))
        if not data:
            raise ValueError('Truncated gap')
        value.update(data)
        nonzero+=bool(data.strip(b'\0'))
        remaining-=len(data)
    stream.seek(2074717*2048)
    manifest=stream.read(1048576)
result=dict(source=str(source),source_sha256=TRUSTED_RETAIL_SHA256,start_sector=start,end_exclusive_sector=end,
            reclaimed_candidate_bytes=(end-start)*2048,nonzero_chunks=nonzero,gap_sha256=value.hexdigest(),
            allocation_overlaps=overlaps,iso_warnings=iso['warnings'],udf_warnings=udf['warnings'],
            manifest_all_zero=len(manifest)==1048576 and not any(manifest),
            interpretation='Static layout evidence only; relocated Retail archives still require gameplay testing.')
with (root/'Retail_Relocation_Inspection.json').open('x',encoding='utf-8') as stream:
    stream.write(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2),flush=True)
