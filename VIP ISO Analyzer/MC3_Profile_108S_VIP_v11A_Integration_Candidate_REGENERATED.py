#!/usr/bin/env python3
"""Profile binding for MC3 dual-profile launcher; never modifies source ISOs."""
import argparse
import hashlib
from pathlib import Path
import sys
from MC3_ISO_Extractor_VIP_v11A_Integration_Candidate import classify

PROFILE = {
    'VERIFIED_RETAIL_REFERENCE': 'retail',
    'RETAIL_CUSTOM_WITH_MANIFEST': 'retail',
    'VERIFIED_VIP_REFERENCE': 'vip',
    'VERIFIED_VIP_V11A_REFERENCE': 'vip',
    'VIP_CUSTOM_WITH_MANIFEST': 'vip',
}

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(4*1024*1024), b''):
            h.update(b)
    return h.hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['inspect','record','validate'])
    parser.add_argument('source',type=Path)
    parser.add_argument('workspace',type=Path,nargs='?')
    parser.add_argument('fallback_list',type=Path,nargs='?')
    args=parser.parse_args()
    if args.action=='inspect':
        kind,_,_=classify(args.source.resolve(strict=True))
        if kind not in PROFILE: raise ValueError(f'Unsupported ISO: {kind}')
        print(f'PROFILE: {PROFILE[kind]} ({kind})')
        return
    if args.action=='record':
        source=args.source.resolve(strict=True)
        workspace=args.workspace.resolve(strict=True)
        kind,_,_=classify(source)
        if kind not in PROFILE: raise ValueError(f'Unsupported ISO: {kind}')
        if not (workspace/'STREAMS.DAT').is_file() or not (workspace/'ASSETS.DAT').is_file():
            raise ValueError('Archives missing from extracted workspace')
        manifest=workspace/'STREAMS.LST'
        if not manifest.exists():
            if not args.fallback_list: raise ValueError('Missing original filename list')
            fallback=args.fallback_list.resolve(strict=True)
            # This is the verified VIP list, also retained as the established retail fallback.
            if PROFILE[kind]=='vip' and digest(fallback).upper()!='AE9085AB98E25A012FE849A354772B52E454B0D7A858229CBE38C14D97DCB5EF':
                raise ValueError('Original VIP filename list SHA256 mismatch')
            manifest.write_bytes(fallback.read_bytes())
        (workspace/'MC3_PROFILE.txt').write_text(PROFILE[kind]+'\n',encoding='utf-8')
        (workspace/'MC3_SOURCE_ISO.txt').write_text(str(source)+'\n',encoding='utf-8')
        (workspace/'MC3_SOURCE_CLASS.txt').write_text(kind+'\n',encoding='utf-8')
        (workspace/'MC3_SOURCE_SHA256.txt').write_text(digest(source)+'\n',encoding='utf-8')
        print(f'WORKSPACE PROFILE RECORDED: {PROFILE[kind]} ({kind})')
        return
    workspace=args.source.resolve(strict=True)
    profile=(workspace/'MC3_PROFILE.txt').read_text(encoding='utf-8').strip()
    kind=(workspace/'MC3_SOURCE_CLASS.txt').read_text(encoding='utf-8').strip()
    source=Path((workspace/'MC3_SOURCE_ISO.txt').read_text(encoding='utf-8').strip())
    if PROFILE.get(kind)!=profile: raise ValueError('Workspace profile and source classification disagree')
    if not source.is_file(): raise ValueError(f'Recorded source ISO missing: {source}')
    if digest(source)!=(workspace/'MC3_SOURCE_SHA256.txt').read_text(encoding='utf-8').strip():
        raise ValueError('Recorded source ISO SHA256 mismatch')
    if not (workspace/'STREAMS.LST').is_file(): raise ValueError('Missing filename manifest')
    for n in ('ASSETS.DAT','STREAMS.DAT'):
        if not (workspace/n).is_file(): raise ValueError(f'Missing {n}')
    print(f'WORKSPACE PROFILE VALID: {profile} ({kind})')

if __name__=='__main__':
    try: main()
    except (OSError,ValueError,UnicodeError) as exc:
        print(f'ERROR: {exc}',file=sys.stderr);sys.exit(1)
