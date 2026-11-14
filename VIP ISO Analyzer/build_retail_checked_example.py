"""Build a separate relocated Retail test from the current bound compiled music."""
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
from MC3_ISO_Extractor import TRUSTED_RETAIL_SHA256, sha256_file, classify
from MC3_ISO_Builder_V11A import verify_streams
from archive_build_gate import check_records

workspace=project/'ISO_FILES'
source=root.parent/"Base ISO's/Midnight Club 3 - DUB Edition Remix (USA).iso"
output=root/'MC3_Retail_Expanded_Music_Test.iso'
report_path=root/'Retail_Expanded_Build_Verification.json'
if output.exists() or output.with_name(output.name+'.building.tmp').exists() or report_path.exists():
    raise FileExistsError('Refusing to overwrite existing Retail test artifacts')
if (workspace/'MC3_SOURCE_CLASS.txt').read_text().strip()!='VERIFIED_RETAIL_REFERENCE':
    raise ValueError('Current workspace is not bound to the original Retail source')
if (workspace/'MC3_SOURCE_SHA256.txt').read_text().strip().lower()!=TRUSTED_RETAIL_SHA256:
    raise ValueError('Workspace Retail fingerprint mismatch')
if Path((workspace/'MC3_SOURCE_ISO.txt').read_text().strip()).resolve()!=source.resolve():
    raise ValueError('Workspace source differs from the verified Retail reference')
inputs={name:sha256_file(workspace/name) for name in ('ASSETS.DAT','STREAMS.DAT','STREAMS.LST')}
check_records(workspace,'retail-expanded',root/'Retail_Expanded_Capacity_Diagnostic.json')
print('Verifying compiled Retail ASSETS against active sources...',flush=True)
entries=analyze(workspace/'ASSETS.DAT',None,1)['all_entries']
files=[entry for entry in entries if not entry['directory_record']]
folder=project/'ASSETS'
if {entry['name'] for entry in files}!={p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}:
    raise ValueError('Retail ASSETS source paths differ from compiled archive')
with (workspace/'ASSETS.DAT').open('rb') as stream:
    for n,entry in enumerate(files,1):
        path=folder.joinpath(*entry['name'].split('/')).resolve()
        if not path.is_relative_to(folder.resolve()):
            raise ValueError('Unsafe archive source path')
        stream.seek(entry['data_offset'])
        payload=stream.read(entry['stored_size'])
        raw=zlib.decompress(payload,-15) if entry['compressed'] else payload
        if len(raw)!=entry['full_size'] or hashlib.sha256(raw).hexdigest()!=sha256_file(path):
            raise ValueError('Retail ASSETS content mismatch: '+entry['name'])
        if n%4000==0:
            print(f'Verified {n:,}/{len(files):,} Retail ASSETS records',flush=True)
verify_streams(workspace/'STREAMS.DAT',project/'STREAMS',workspace/'STREAMS.LST')
command=[sys.executable,'-u',str(project/'supporting_tools/MC3_ISO_Builder.py'),'--profile','retail',
         '--relocate-archives','--source',str(source),'--replacement-dir',str(workspace),
         '--manifest',str(workspace/'STREAMS.LST'),'--output',str(output),'--yes']
print('Building separate relocated Retail ISO...',flush=True)
with (root/'Retail_Expanded_Build_Verification.log').open('x',encoding='utf-8') as saved:
    process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
    for line in process.stdout:
        saved.write(line)
        saved.flush()
        print(line,end='',flush=True)
    code=process.wait()
if code:
    raise SystemExit(code)
if any(sha256_file(workspace/name)!=value for name,value in inputs.items()):
    raise ValueError('Compiled inputs changed during Retail test build')
kind,_,_=classify(output)
if kind!='UNSUPPORTED_RETAIL_RELOCATED_LAYOUT':
    raise ValueError('Relocated Retail output classification needs review: '+kind)
result=dict(source=str(source),output=str(output),sha256=sha256_file(output),verified_assets_records=len(files),
            active_sources_verified=True,compiled_inputs_unchanged=True,automated_build_and_preservation_checks_passed=True,
            runtime_status='NOT TESTED',reimport_classification=kind,
            note='Build from the verified original Retail source; relocated output re-import is intentionally blocked instead of being mislabeled as VIP.')
with report_path.open('x',encoding='utf-8') as saved:
    saved.write(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2),flush=True)
