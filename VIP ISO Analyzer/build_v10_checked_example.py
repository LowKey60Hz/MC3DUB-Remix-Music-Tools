"""Validate current v1.0-C compiled content and create an isolated expansion test ISO."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zlib
from MC3_VIP_Archive_Entry_Analyzer import analyze

root=Path(__file__).resolve().parent
project=root.parent/'UI Custom Gameplay Music Tools'
sys.path.insert(0,str(project/'supporting_tools'))
import MC3_ISO_Builder_VIP as engine
from MC3_ISO_Extractor import TRUSTED_VIP_SHA256, sha256_file
from MC3_ISO_Builder_V11A import verify_streams
from archive_build_gate import check_records

workspace=project/'ISO_FILES'
source=root.parent/"Base ISO's/Midnight Club 3 VIP v1.0-C.iso"
output=root/'MC3_VIP_v10C_Expanded_Music_Test.iso'
report_path=root/'V10_Expanded_Build_Verification.json'
if output.exists() or output.with_name(output.name+'.building.tmp').exists() or report_path.exists():
    raise FileExistsError('Refusing to overwrite existing expansion test artifacts')
if (workspace/'MC3_SOURCE_CLASS.txt').read_text().strip()!='VERIFIED_VIP_REFERENCE':
    raise ValueError('Current workspace is not bound to original v1.0-C; no build attempted')
if (workspace/'MC3_SOURCE_SHA256.txt').read_text().strip().lower()!=TRUSTED_VIP_SHA256:
    raise ValueError('Current workspace fingerprint is not v1.0-C')
if Path((workspace/'MC3_SOURCE_ISO.txt').read_text().strip()).resolve()!=source.resolve():
    raise ValueError('Workspace source path differs from selected v1.0-C original')
inputs={name:sha256_file(workspace/name) for name in ('ASSETS.DAT','STREAMS.DAT','STREAMS.LST')}
check_records(workspace,'vip-expanded',root/'V10_Expanded_Capacity_Diagnostic.json')
print('Verifying all compiled ASSETS against active files...',flush=True)
entries=analyze(workspace/'ASSETS.DAT',None,1)['all_entries']
files=[e for e in entries if not e['directory_record']]
source_files=project/'ASSETS'
expected={e['name'] for e in files}
actual={p.relative_to(source_files).as_posix() for p in source_files.rglob('*') if p.is_file()}
if expected!=actual:
    raise ValueError('Compiled ASSETS names differ from active source')
with (workspace/'ASSETS.DAT').open('rb') as archive:
    for n,entry in enumerate(files,1):
        path=source_files.joinpath(*entry['name'].split('/')).resolve()
        if not path.is_relative_to(source_files.resolve()):
            raise ValueError('Unsafe archive path')
        archive.seek(entry['data_offset'])
        data=archive.read(entry['stored_size'])
        raw=zlib.decompress(data,-15) if entry['compressed'] else data
        if len(raw)!=entry['full_size'] or hashlib.sha256(raw).hexdigest()!=sha256_file(path):
            raise ValueError('Compiled ASSETS mismatch: '+entry['name'])
        if n%4000==0:
            print(f'Verified {n:,}/{len(files):,} ASSETS records',flush=True)
verify_streams(workspace/'STREAMS.DAT',project/'STREAMS',workspace/'STREAMS.LST')
log=root/'V10_Expanded_Build_Verification.log'
command=[sys.executable,'-u',str(project/'supporting_tools/MC3_ISO_Builder.py'),'--profile','vip',
         '--expand-v10','--source',str(source),'--replacement-dir',str(workspace),
         '--manifest',str(workspace/'STREAMS.LST'),'--output',str(output),'--yes']
print('Creating separate v1.0-C expansion test image...',flush=True)
with log.open('x',encoding='utf-8') as saved:
    process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
    for line in process.stdout:
        saved.write(line)
        saved.flush()
        print(line,end='',flush=True)
    code=process.wait()
if code:
    raise SystemExit(code)
if any(sha256_file(workspace/name)!=value for name,value in inputs.items()):
    raise ValueError('Compiled inputs changed during the build; output needs inspection')
result=dict(source=str(source),output=str(output),sha256=sha256_file(output),
            verified_assets_records=len(files),active_sources_verified=True,compiled_inputs_unchanged=True,
            automated_build_and_preservation_checks_passed=True,runtime_status='NOT TESTED')
with report_path.open('x',encoding='utf-8') as saved:
    saved.write(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2),flush=True)
