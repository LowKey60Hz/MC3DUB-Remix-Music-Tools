"""Inspect original loading RAW records directly in the trusted Retail ISO."""
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import sys
import wave
import zlib

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'UI Custom Gameplay Music Tools/supporting_tools'))
from MC3_ISO_Extractor import TRUSTED_RETAIL_SHA256, sha256_file
from MC3_ISO_Builder_Retail import PROFILES, inspect_base
from MC3_ASSETS_Builder_V11A import decode_name


def inspect(source):
    print('Verifying untouched Retail reference SHA-256...',flush=True)
    fingerprint=sha256_file(source)
    if fingerprint!=TRUSTED_RETAIL_SHA256:
        raise ValueError('Source is not the verified original Retail ISO')
    info=PROFILES['Retail USA']['archives']
    _,sector,allocation,_,_=next(row for row in info if row[0]=='ASSETS.DAT')
    base=sector*2048
    records=[]
    with source.open('rb') as stream:
        inspect_base(stream,info)
        stream.seek(base)
        magic,count,table_bytes,names_bytes=struct.unpack('<4sIII',stream.read(16))
        if magic!=b'Dave' or table_bytes<count*16 or 2048+table_bytes+names_bytes>allocation:
            raise ValueError('Unexpected original archive header')
        stream.seek(base+2048)
        table=stream.read(count*16)
        stream.seek(base+2048+table_bytes)
        names=stream.read(names_bytes)
        previous=''
        for index in range(count):
            name_offset,offset,full,stored=struct.unpack_from('<IIII',table,index*16)
            if name_offset>=len(names):
                raise ValueError('Invalid original filename reference')
            name=decode_name(names,name_offset,previous)
            previous=name
            match=re.fullmatch(r'audio/loadscreen/([1-9]|1[0-8])\.raw',name,re.IGNORECASE)
            if not match:
                continue
            if offset+stored>allocation or stored>full:
                raise ValueError('Invalid loading payload extent')
            stream.seek(base+offset)
            payload=stream.read(stored)
            raw=zlib.decompress(payload,-15) if stored<full else payload
            if len(payload)!=stored or len(raw)!=full:
                raise ValueError('Original loading data length mismatch')
            header_type='No RIFF/WAVE header; original PCM parameters not established from filename/size alone'
            wave_info=None
            if raw.startswith(b'RIFF') and raw[8:12]==b'WAVE':
                with wave.open(io.BytesIO(raw),'rb') as audio:
                    wave_info=dict(rate=audio.getframerate(),channels=audio.getnchannels(),sample_width=audio.getsampwidth(),frames=audio.getnframes())
                header_type='RIFF/WAVE'
            records.append(dict(slot=int(match.group(1)),name=name,index=index,data_offset=offset,
                                decoded_bytes=full,stored_bytes=stored,compressed=stored<full,
                                decoded_sha256=hashlib.sha256(raw).hexdigest(),first_32_bytes_hex=raw[:32].hex(),
                                header_type=header_type,wave_info=wave_info,
                                equivalent_seconds_at_current_converter_format=full/48000))
    slots=[]
    for slot in range(1,19):
        group=[row for row in records if row['slot']==slot]
        if not group:
            raise ValueError('Missing original loading slot '+str(slot))
        variants={(row['decoded_bytes'],row['decoded_sha256']) for row in group}
        slots.append(dict(slot=slot,record_count=len(group),decoded_variants=len(variants),
                          decoded_sizes=sorted({row['decoded_bytes'] for row in group}),
                          stored_sizes=sorted({row['stored_bytes'] for row in group}),
                          matches_current_tool_limit=any(row['decoded_bytes']==460800 for row in group),
                          exceeds_current_tool_limit=any(row['decoded_bytes']>460800 for row in group)))
    sizes=[row['decoded_bytes'] for row in records]
    return dict(source=str(source),source_sha256=fingerprint,assets_sector=sector,assets_allocation=allocation,
                current_tool_limit_bytes=460800,original_slot_count=len(slots),original_loading_record_count=len(records),
                smallest_original_decoded_bytes=min(sizes),largest_original_decoded_bytes=max(sizes),
                original_records_equal_to_tool_limit=sum(size==460800 for size in sizes),
                original_records_above_tool_limit=sum(size>460800 for size in sizes),
                slots=slots,records=records,
                interpretation='Original sizes characterize shipped assets, not maximum engine allocation. Any duration based only on 48,000 bytes/s is a current-converter-format equivalent, not verified original playback duration.')


if __name__=='__main__':
    source=ROOT.parent/"Base ISO's/Midnight Club 3 - DUB Edition Remix (USA).iso"
    result=inspect(source)
    output=ROOT/'Retail_Original_Loading_Audio.json'
    with output.open('x',encoding='utf-8') as stream:
        stream.write(json.dumps(result,indent=2)+'\n')
    lines=['# Original Retail loading-screen audio','',
           'Read directly from the fingerprint-verified original Retail ASSETS.DAT inside the ISO. Current workspace files were not used.',
           '', '| Slot | Decoded bytes | Stored archive bytes | Records | Decoded variants |',
           '|---|---:|---:|---:|---:|']
    for row in result['slots']:
        lines.append(f'| {row["slot"]} | '+', '.join(f'{x:,}' for x in row['decoded_sizes'])+' | '+', '.join(f'{x:,}' for x in row['stored_sizes'])+f' | {row["record_count"]} | {row["decoded_variants"]} |')
    lines+=['',f'Current tool cap: 460,800 bytes. Original decoded range: {result["smallest_original_decoded_bytes"]:,}–{result["largest_original_decoded_bytes"]:,} bytes.',
            f'Original records exactly at the cap: {result["original_records_equal_to_tool_limit"]}; above it: {result["original_records_above_tool_limit"]}.',
            '',result['interpretation'],'', 'No limits were changed; no game files were extracted to or replaced in the active workspace.']
    (ROOT/'Retail_Original_Loading_Audio.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({key:value for key,value in result.items() if key not in ('records',)},indent=2),flush=True)
