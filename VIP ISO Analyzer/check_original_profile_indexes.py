"""Read original archive indexes in place; no extraction or workspace changes."""
import json
from pathlib import Path
import sys

root=Path(__file__).resolve().parent
sys.path.insert(0,str(root.parent/'UI Custom Gameplay Music Tools/supporting_tools'))
import vip_capacity as capacity
import MC3_ISO_Builder_VIP as vip
import MC3_ISO_Builder_Retail as retail
from MC3_ISO_Builder_V11A import INFO

verified=json.loads((root/'All_Profile_Capacity_Verification.json').read_text())
results={}
for profile,info in (('vip',vip.PROFILES['VIP Expansion']['archives']),('vip-v11a',INFO),('retail',retail.PROFILES['Retail USA']['archives'])):
    source=Path(verified[profile]['source'])
    if verified[profile]['sha256']!=capacity.CAPACITY_PROFILES[profile]['sha256']:
        raise ValueError('Expected fingerprint record mismatch')
    indexes={}
    for name,sector,size,_,_ in info:
        if name in ('ASSETS.DAT','STREAMS.DAT'):
            kind=name.split('.')[0]
            indexes[kind]=capacity.inspect_archive(source,kind,extent_start=sector*2048,extent_length=size)
    result=capacity.assess(indexes['ASSETS']['archive_bytes'],indexes['STREAMS']['archive_bytes'],verified[profile]['sha256'],
        assets_index=indexes['ASSETS'],streams_index=indexes['STREAMS'],layout_profile=profile)
    if not result['passes_size_policy']:
        raise ValueError('Original archive index blocked: '+profile)
    results[profile]=result
    print(profile, 'ASSETS records:',indexes['ASSETS']['live_record_count'],'STREAMS records:',indexes['STREAMS']['live_record_count'],'PASS',flush=True)
with (root/'Original_Profile_Record_Checks.json').open('x',encoding='utf-8') as stream:
    stream.write(json.dumps(results,indent=2)+'\n')
