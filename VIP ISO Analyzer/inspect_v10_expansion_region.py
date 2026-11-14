"""Read-only allocation checks for the explicit original-v1.0-C expansion path."""
import json
from pathlib import Path
import struct
from map_udf_allocations import scan

root=Path(__file__).resolve().parent
source=root.parent/"Base ISO's/Midnight Club 3 VIP v1.0-C.iso"
udf=scan(source)
start,end=1772493,2074717
touching=[]
for entry in udf['files']+udf['directories']:
    for extent in entry['extents']:
        lo=extent['sector']
        hi=lo+(extent['bytes']+2047)//2048
        if lo<end and hi>start:
            touching.append(entry['path'])
with source.open('rb') as stream:
    stream.seek(2084960*2048)
    pvd=stream.read(2048)
    if pvd[:7]!=b'\x01CD001\x01':
        raise ValueError('Second-layer descriptor missing')
    stream.seek(end*2048)
    reserved=stream.read(1048576)
result=dict(source=str(source),original_archive_end_exclusive=start,manifest_start=end,
            mapped_allocation_overlaps=touching,manifest_reservation_all_zero=len(reserved)==1048576 and not any(reserved),
            udf_warnings=udf['warnings'],second_layer_pvd_present=True,
            limitation='No claim of game compatibility. Original source hash/layout verified separately; output must preserve every byte outside explicit changes.')
if touching or not result['manifest_reservation_all_zero']:
    raise ValueError('Expansion conflicts with mapped allocations or manifest')
with (root/'V10_Expansion_Allocation_Check.json').open('x',encoding='utf-8') as stream:
    stream.write(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
