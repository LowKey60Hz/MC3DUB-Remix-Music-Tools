#!/usr/bin/env python3
"""MC3 VIP ISO Compatibility Analyzer v0.2 — read-only MC3 profile-aware comparison.

No third-party dependencies. No writes to input images. Reports are diagnostic,
not automatic verification that a game image can boot or be safely rebuilt.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
from datetime import datetime, timezone

SECTOR = 2048
ARCHIVE_SUFFIXES = ('.DAT', '.LST')

def sha256_file(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def read_sector(f, n):
    f.seek(n * SECTOR)
    return f.read(SECTOR)

def both_endian_32(b, at):
    le = struct.unpack_from('<I', b, at)[0]
    be = struct.unpack_from('>I', b, at + 4)[0]
    if le != be:
        raise ValueError('ISO9660 endian mismatch')
    return le

def directory_records(f, extent, length, max_entries=100000):
    if length < 0 or length > 256 * 1024 * 1024:
        raise ValueError('Unreasonable directory size')
    f.seek(extent * SECTOR)
    data = f.read(length)
    if len(data) != length:
        raise ValueError('Truncated directory')
    i, count = 0, 0
    while i < len(data):
        size = data[i]
        if not size:
            i = ((i // SECTOR) + 1) * SECTOR
            continue
        if size < 34 or i + size > len(data):
            raise ValueError('Invalid ISO9660 directory record')
        rec = data[i:i + size]
        name_len = rec[32]
        if 33 + name_len > size:
            raise ValueError('Invalid filename length')
        name_bytes = rec[33:33 + name_len]
        if name_bytes not in (b'\x00', b'\x01'):
            name = name_bytes.decode('ascii', errors='replace').split(';')[0]
            yield name, both_endian_32(rec, 2), both_endian_32(rec, 10), bool(rec[25] & 2)
        i += size
        count += 1
        if count > max_entries:
            raise ValueError('Directory entry limit exceeded')

def scan_iso(path, hash_iso=True):
    size = path.stat().st_size
    result = {'path': str(path.resolve()), 'bytes': size, 'sectors_2048': size // SECTOR,
              'sector_remainder': size % SECTOR, 'sha256': sha256_file(path) if hash_iso else None,
              'iso9660': {'detected': False}, 'udf': {'markers': []}, 'files': {}, 'warnings': []}
    with path.open('rb') as f:
        pvd = None
        for n in range(16, min(64, size // SECTOR)):
            s = read_sector(f, n)
            if s[1:6] == b'CD001' and s[0] == 1:
                pvd = s
                result['iso9660']['pvd_sector'] = n
                break
        if pvd:
            root = pvd[156:]
            try:
                vol_sectors = both_endian_32(pvd, 80)
                result['iso9660'].update({'detected': True,
                    'volume_id': pvd[40:72].decode('ascii', errors='replace').strip(),
                    'volume_sectors': vol_sectors,
                    'root_extent': both_endian_32(root, 2),
                    'root_bytes': both_endian_32(root, 10)})
                visited = set()
                def walk(prefix, extent, length, depth):
                    if depth > 24 or len(result['files']) > 100000:
                        raise ValueError('Directory traversal safety limit exceeded')
                    if (extent, length) in visited:
                        return
                    visited.add((extent, length))
                    if extent * SECTOR + length > size:
                        raise ValueError('Directory extends beyond image')
                    for name, pos, nbytes, is_dir in directory_records(f, extent, length):
                        full = prefix + '/' + name if prefix else '/' + name
                        if pos * SECTOR + nbytes > size:
                            result['warnings'].append('Out-of-bounds entry: ' + full)
                            continue
                        if is_dir:
                            walk(full, pos, nbytes, depth + 1)
                        else:
                            result['files'][full] = {'sector': pos, 'bytes': nbytes}
                walk('', result['iso9660']['root_extent'], result['iso9660']['root_bytes'], 0)
            except (ValueError, struct.error) as e:
                result['warnings'].append('ISO9660 parse incomplete: ' + str(e))
        else:
            result['warnings'].append('ISO9660 primary volume descriptor not found')
        # UDF volume recognition sequences commonly appear near sector 16 onward.
        # These are marker observations, NOT a complete UDF parser.
        for n in range(16, min(64, size // SECTOR)):
            s = read_sector(f, n)
            tag = s[1:6]
            if tag in (b'BEA01', b'NSR02', b'NSR03', b'TEA01'):
                result['udf']['markers'].append({'sector': n, 'tag': tag.decode('ascii')})
        # Report sector 256 anchor tag as a hint, without asserting UDF validity.
        if size // SECTOR > 256:
            s = read_sector(f, 256)
            result['udf']['anchor_256_tag_id'] = struct.unpack_from('<H', s, 0)[0]
    return result

def compare(old, new):
    fields = ['bytes', 'sectors_2048', 'sector_remainder', 'sha256']
    differences = []
    for k in fields:
        if old[k] != new[k]:
            differences.append({'type': 'image', 'field': k, 'old': old[k], 'new': new[k]})
    for k in ['detected', 'volume_id', 'volume_sectors', 'root_extent', 'root_bytes', 'pvd_sector']:
        a, b = old['iso9660'].get(k), new['iso9660'].get(k)
        if a != b:
            differences.append({'type': 'iso9660', 'field': k, 'old': a, 'new': b})
    if old['udf'] != new['udf']:
        differences.append({'type': 'udf_observation', 'old': old['udf'], 'new': new['udf']})
    old_files, new_files = old['files'], new['files']
    for path in sorted(set(old_files) | set(new_files)):
        a, b = old_files.get(path), new_files.get(path)
        if a != b:
            differences.append({'type': 'file_layout', 'path': path, 'old': a, 'new': b,
                'archive_candidate': path.upper().endswith(ARCHIVE_SUFFIXES)})
    return differences

def markdown_report(data):
    old, new, diffs = data['baseline'], data['candidate'], data['differences']
    lines = ['# MC3 VIP ISO Compatibility Report', '',
             'Diagnostic only. Does not establish that an ISO is compatible or bootable.', '',
             '## Input images', '',
             '| Property | Known working | New candidate |', '|---|---|---|']
    for label, key in [('Path', 'path'), ('Bytes', 'bytes'), ('2048-byte sectors', 'sectors_2048'), ('SHA-256', 'sha256')]:
        lines.append(f'| {label} | `{old[key]}` | `{new[key]}` |')
    lines += ['', '## ISO9660', '']
    for label, key in [('Detected','detected'), ('Volume ID','volume_id'), ('Volume sectors','volume_sectors'), ('Root extent','root_extent')]:
        lines.append(f'- **{label}:** `{old["iso9660"].get(key)}` → `{new["iso9660"].get(key)}`')
    lines += ['', '## Filesystem and archive layout differences', '']
    layout = [d for d in diffs if d['type'] == 'file_layout']
    if layout:
        lines += ['| File | Old sector / bytes | New sector / bytes |', '|---|---|---|']
        for d in layout[:1000]:
            def fmt(x): return f'{x["sector"]} / {x["bytes"]}' if x else 'Not present'
            lines.append(f'| `{d["path"].replace("|", "\\|")}` | {fmt(d["old"])} | {fmt(d["new"])} |')
        if len(layout) > 1000:
            lines.append(f'\nOnly first 1000 of {len(layout)} file changes shown; JSON contains all.')
    else:
        lines.append('No ISO9660 file location/size differences detected (or directory enumeration unavailable).')
    lines += ['', '## Other changes', '']
    other = [d for d in diffs if d['type'] != 'file_layout']
    for d in other:
        lines.append(f'- **{d["type"]} / {d.get("field", "markers")}:** `{d.get("old")}` → `{d.get("new")}`')
    if not other: lines.append('No other metadata changes detected.')
    lines += ['', '## Interpretation', '',
              '- A different SHA-256 alone does not prove a layout change.',
              '- Matching file extents do not prove matching file contents.',
              '- ISO9660 directory records may not describe all UDF-visible content.',
              '- UDF marker detection is not full UDF filesystem validation.',
              '- Layer boundaries, protected sectors, archive internals and profile-specific rules require integration with existing MC3 scripts.',
              '- Do not modify working extractor/builder validation based only on this report.', '',
              '## Warnings', '']
    warnings = [f'{side}: {w}' for side, scan in [('Baseline', old), ('Candidate', new)] for w in scan['warnings']]
    lines += ['- ' + w for w in warnings] if warnings else ['None.']
    return '\n'.join(lines) + '\n'

# Profile rules transcribed from the supplied 108S extractor and VIP builder.
VIP_10C = {'TEXTURE.DAT': (9702, 794839040), 'STREAMS.DAT': (397807, 1033197568),
           'BANKS.DAT': (902298, 52967424), 'ASSETS.DAT': (928161, 1729191936)}
EXPECTED_SIGNATURES = {'TEXTURE.DAT': b'Dave', 'STREAMS.DAT': b'Hash',
                       'BANKS.DAT': b'DAVE', 'ASSETS.DAT': b'Dave'}
FE_SECTORS = {'TEXTURE.DAT': 344, 'STREAMS.DAT': 345, 'BANKS.DAT': 346, 'ASSETS.DAT': 347}
PARTITION_START = 266
LAYER2_START = 2084944
MANIFEST_SECTOR = 2074717
MANIFEST_CAPACITY = 1048576

def _u16(data, off): return struct.unpack_from('<H', data, off)[0]
def _u32(data, off): return struct.unpack_from('<I', data, off)[0]
def _u64(data, off): return struct.unpack_from('<Q', data, off)[0]
def _crc16(data):
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ (0x1021 if crc & 0x8000 else 0)) & 0xffff
    return crc

def profile_inspection(path, scan):
    checks = {}
    def check(name, ok, detail):
        checks[name] = {'pass': bool(ok), 'detail': detail}
    layout = {}
    with path.open('rb') as f:
        check('physical_sector_count', scan['sectors_2048'] == 4169904 and scan['sector_remainder'] == 0,
              f"Observed {scan['sectors_2048']} sectors")
        for sector in (16, 2084960):
            check(f'layer_pvd_{sector}', read_sector(f, sector)[:6] == b'\x01CD001', f'PVD sector {sector}')
        part = read_sector(f, 34)
        check('udf_partition', _u16(part,0)==5 and _u32(part,188)==266 and _u32(part,192)==2084693,
              f'tag={_u16(part,0)} start={_u32(part,188)} length={_u32(part,192)}')
        check('root_directory', scan['iso9660'].get('root_extent')==261 and
              1<=scan['iso9660'].get('root_bytes',0)<=2048,
              f"sector={scan['iso9660'].get('root_extent')} bytes={scan['iso9660'].get('root_bytes')}")
        for name, sig in EXPECTED_SIGNATURES.items():
            rec = scan['files'].get('/'+name)
            if not rec:
                check('archive_'+name, False, 'ISO9660 root record missing')
                continue
            sector, size = rec['sector'], rec['bytes']
            layout[name] = [sector,size]
            f.seek(sector*SECTOR)
            actual_sig=f.read(4)
            fe=read_sector(f,FE_SECTORS[name])
            crc_len=_u16(fe,10)
            udf_ok = (_u16(fe,0)==261 and _u32(fe,12)==FE_SECTORS[name]-PARTITION_START and
                      _u64(fe,56)==size and _u64(fe,64)==(size+SECTOR-1)//SECTOR and
                      _u32(fe,308)==size and _u32(fe,312)+PARTITION_START==sector and
                      _u32(fe,168)==132 and _u32(fe,172)==8 and
                      (_u16(fe,34)&7)==0 and crc_len<=SECTOR-16 and
                      _crc16(fe[16:16+crc_len])==_u16(fe,8) and
                      (sum(fe[i] for i in range(16) if i!=4)&255)==fe[4])
            check('archive_'+name, actual_sig==sig and udf_ok and size>0 and size%SECTOR==0,
                  f'sector={sector} size={size} signature={actual_sig.hex()} expected={sig.hex()} UDF_FE_valid={udf_ok}')
        spans=sorted((v[0],v[0]+v[1]//SECTOR,n) for n,v in layout.items())
        contiguous=len(spans)==4 and all(a[1]==b[0] for a,b in zip(spans,spans[1:]))
        check('archive_contiguity', contiguous, 'Archive sectors must be contiguous in TEXTURE/STREAMS/BANKS/ASSETS order')
        check('archive_layer_boundary', bool(spans) and spans[-1][1]<=LAYER2_START,
              f'last_exclusive_sector={spans[-1][1] if spans else "unknown"}, layer2={LAYER2_START}')
        f.seek(MANIFEST_SECTOR*SECTOR)
        reserved=f.read(MANIFEST_CAPACITY)
        check('manifest_reserved_zero',len(reserved)==MANIFEST_CAPACITY and not any(reserved),
              'Zero-filled reservation required for an original manifest-free VIP ISO')
    old_end=VIP_10C['ASSETS.DAT'][0]+VIP_10C['ASSETS.DAT'][1]//SECTOR
    new_end=layout.get('ASSETS.DAT',[0,0])[0]+layout.get('ASSETS.DAT',[0,0])[1]//SECTOR
    check('fits_old_vip_archive_region',new_end<=old_end,
          f'candidate end exclusive={new_end}; v1.0-C end exclusive={old_end}; overrun={max(0,new_end-old_end)} sectors')
    check('matches_v10c_layout',all(layout.get(n)==list(v) for n,v in VIP_10C.items()),
          'Exact archive sector/size match required by current manifest-free extractor')
    check('matches_v10c_sha256',scan['sha256']=='906ada438e097d4668feabd6ef8b8d388876811181cb89ea6b1648e5f2acbe4c' if scan['sha256'] else False,
          'Current trusted VIP SHA-256; skipped hash cannot establish a match')
    return {'checks':checks,'archive_layout':layout,
            'first_layer_archive_end_exclusive':new_end,
            'old_vip_archive_end_exclusive':old_end,
            'old_builder_capacity_exceeded_bytes':max(0,new_end-old_end)*SECTOR,
            'likely_extractor_classification': ('VERIFIED_VIP_REFERENCE' if checks['matches_v10c_layout']['pass'] and checks['matches_v10c_sha256']['pass'] else
                                                'VIP_LAYOUT_BUT_HASH_MISMATCH' if checks['matches_v10c_layout']['pass'] else
                                                'UNSUPPORTED_MANIFEST_FREE_LAYOUT')}

def profile_markdown(report):
    a,b=report['profile_analysis']['baseline'],report['profile_analysis']['candidate']
    lines=['','## Existing MC3 tool compatibility checks','','| Check | v1.0-C | v1.1-A |','|---|---|---|']
    for name in a['checks']:
        def label(obj): return 'PASS' if obj['checks'][name]['pass'] else 'FAIL'
        lines.append(f'| `{name}` | {label(a)} | {label(b)} |')
    lines += ['',f"- Expected current extractor classification for candidate: **`{b['likely_extractor_classification']}`**.",
              f"- Old VIP builder archive region exceeded by candidate: **{b['old_builder_capacity_exceeded_bytes']:,} bytes**.",
              '- The current builder also uses source-path equality to decide whether a VIP source is modified; a renamed original may be incorrectly treated as modified.',
              '- This report does not authorize bypassing signature, UDF, manifest, sector, or SHA-256 validation.',
              '- A new version-specific archive capacity and trusted reference must be verified before patching.',
              '', '### Failed candidate checks', '']
    for name,v in b['checks'].items():
        if not v['pass']:
            lines.append(f'- **{name}**: {v["detail"]}')
    return '\n'.join(lines)+'\n'

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--baseline', type=Path, required=True, help='Known working VIP ISO')
    ap.add_argument('--candidate', type=Path, required=True, help='New VIP ISO')
    ap.add_argument('--output', type=Path, default=Path('VIP_Analysis_Report'), help='Output filename prefix')
    ap.add_argument('--skip-hash', action='store_true', help='Skip full ISO SHA256 (faster)')
    args = ap.parse_args()
    for p in (args.baseline, args.candidate):
        if not p.is_file(): ap.error(f'ISO not found: {p}')
    if args.baseline.resolve() == args.candidate.resolve():
        ap.error('Baseline and candidate must be different files')
    print('Scanning known working ISO (read-only)...', flush=True)
    old = scan_iso(args.baseline, not args.skip_hash)
    print('Scanning new ISO (read-only)...', flush=True)
    new = scan_iso(args.candidate, not args.skip_hash)
    diffs = compare(old, new)
    report = {'analyzer_version': '0.2', 'generated_utc': datetime.now(timezone.utc).isoformat(),
              'baseline': old, 'candidate': new, 'differences': diffs,
              'profile_analysis': {'baseline': profile_inspection(args.baseline,old),
                                   'candidate': profile_inspection(args.candidate,new)}}
    output = args.output.expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    json_path = output.with_suffix('.json')
    md_path = output.with_suffix('.md')
    json_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    md_path.write_text(markdown_report(report)+profile_markdown(report), encoding='utf-8')
    print(f'Found {len(diffs)} differences.\nReport: {md_path}\nData: {json_path}')
    return 0

if __name__ == '__main__':
    try: sys.exit(main())
    except (OSError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
