#!/usr/bin/env python3
"""MC3 unified ISO extraction: ISO9660/UDF inspection, source detection, and DAT extraction.

This is a conservative consolidation of the verified 108K / 108S extraction path.
The Retail geometry cross-check is implemented locally (legacy v4 validator).
CLI: python MC3_ISO_Extractor.py ISO --output-dir STAGING --production [--extract --yes]
"""
import argparse
import hashlib
from pathlib import Path
import struct
import sys

# Retail reference geometry validation, migrated without changing the validation algorithm.
# Previously: MC3_ISO_Builder_v4.inspect_base and its helper functions.
import os
_RETAIL_SECTOR = 2048
_RETAIL_TOTAL_SECTORS = 4_169_904
_RETAIL_ROOT_SECTOR = 261
_RETAIL_PARTITION_START = 266
_RETAIL_ARCHIVES = [
    ('TEXTURE.DAT', 454764, 794_839_040, 344, b'Dave'),
    ('STREAMS.DAT', 842869, 1_025_642_496, 345, b'Hash'),
    ('BANKS.DAT', 1343671, 52_967_424, 346, b'DAVE'),
    ('ASSETS.DAT', 1369534, 1_444_214_784, 347, b'Dave'),
]

def _retail_read_exact(f, position, size):
    f.seek(position)
    data = f.read(size)
    if len(data) != size:
        raise ValueError(f'Unexpected EOF at byte {position}')
    return data


def _retail_u16(buf, off):
    return struct.unpack_from('<H', buf, off)[0]


def _retail_u32(buf, off):
    return struct.unpack_from('<I', buf, off)[0]


def _retail_u64(buf, off):
    return struct.unpack_from('<Q', buf, off)[0]


def _retail_crc16(data):
    crc = 0
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            crc = ((crc << 1) ^ (0x1021 if crc & 0x8000 else 0)) & 0xFFFF
    return crc


def _retail_tag_checksum(buf):
    return sum(buf[i] for i in range(16) if i != 4) & 0xFF


def _retail_inspect_base(f, dat_info):
    f.seek(0, os.SEEK_END)
    if f.tell() != _RETAIL_TOTAL_SECTORS * _RETAIL_SECTOR:
        raise ValueError('Source ISO has unexpected physical size')
    for pvd_sector in (16, 2_084_960):
        pvd = _retail_read_exact(f, pvd_sector * _RETAIL_SECTOR, _RETAIL_SECTOR)
        if pvd[:6] != b'\x01CD001':
            raise ValueError(f'Invalid ISO9660 PVD at sector {pvd_sector}')
    pvd = _retail_read_exact(f, 16 * _RETAIL_SECTOR, _RETAIL_SECTOR)
    root_size = _retail_u32(pvd, 166)
    if _retail_u32(pvd, 158) != _RETAIL_ROOT_SECTOR or not (1 <= root_size <= _RETAIL_SECTOR):
        raise ValueError('Unexpected ISO9660 root directory location/size')
    root = _retail_read_exact(f, _RETAIL_ROOT_SECTOR * _RETAIL_SECTOR, root_size)
    part = _retail_read_exact(f, 34 * _RETAIL_SECTOR, _RETAIL_SECTOR)
    if _retail_u16(part, 0) != 5 or _retail_u32(part, 188) != _RETAIL_PARTITION_START or _retail_u32(part, 192) != 2_084_693:
        raise ValueError('Unexpected UDF partition descriptor')
    records = {}
    off = 0
    while off < len(root):
        length = root[off]
        if length == 0:
            break
        if length < 34 or off + length > len(root):
            raise ValueError('Invalid root directory record')
        name_len = root[off + 32]
        if 33 + name_len > length:
            raise ValueError('Invalid root record name length')
        name = root[off + 33:off + 33 + name_len].decode('ascii', 'replace')
        records[name] = off
        off += length
    expected_next = dat_info[0][1]
    for name, sector, size, fe_sector, signature in dat_info:
        if sector != expected_next or size % _RETAIL_SECTOR:
            raise ValueError(f'Unsupported non-contiguous DAT layout: {name}')
        expected_next = sector + size // _RETAIL_SECTOR
        key = name + ';1'
        if key not in records:
            raise ValueError(f'Missing ISO9660 root entry: {key}')
        pos = records[key]
        if _retail_u32(root, pos + 2) != sector or _retail_u32(root, pos + 10) != size:
            raise ValueError(f'Unexpected base ISO9660 allocation: {name}')
        if struct.unpack_from('>I', root, pos + 6)[0] != sector or struct.unpack_from('>I', root, pos + 14)[0] != size:
            raise ValueError(f'Unexpected big-endian ISO9660 allocation: {name}')
        fe = _retail_read_exact(f, fe_sector * _RETAIL_SECTOR, _RETAIL_SECTOR)
        if _retail_u16(fe, 0) != 261 or _retail_u32(fe, 12) != fe_sector - _RETAIL_PARTITION_START:
            raise ValueError(f'Unexpected UDF FE tag: {name}')
        if _retail_u16(fe, 10) > _RETAIL_SECTOR - 16 or _retail_crc16(fe[16:16 + _retail_u16(fe, 10)]) != _retail_u16(fe, 8) or _retail_tag_checksum(fe) != fe[4]:
            raise ValueError(f'Invalid source UDF integrity fields: {name}')
        if (_retail_u16(fe, 34) & 7) != 0 or _retail_u32(fe, 168) != 132 or _retail_u32(fe, 172) != 8:
            raise ValueError(f'Unexpected UDF allocation descriptor layout: {name}')
        if _retail_u64(fe, 56) != size or _retail_u32(fe, 312) + _RETAIL_PARTITION_START != sector or _retail_u32(fe, 308) != size:
            raise ValueError(f'Unexpected UDF archive allocation: {name}')
        expected_blocks = (size + _RETAIL_SECTOR - 1) // _RETAIL_SECTOR
        if _retail_u64(fe, 64) != expected_blocks:
            raise ValueError(f'Unexpected UDF recorded blocks: {name}')
        if _retail_read_exact(f, sector * _RETAIL_SECTOR, 4) != signature:
            raise ValueError(f'Unexpected source DAT signature: {name}')
    return records, root_size


SECTOR = 2048


TOTAL_BYTES = 8_539_963_392


PARTITION_START = 266


ROOT_SECTOR = 261


LAYER2_START = 2_084_944


MANIFEST_SECTOR = 2_074_717


MANIFEST_CAPACITY = 1_048_576


HEADER = struct.Struct('<16sIQ32s4s')


MAGIC = b'MC3STREAMSLSTv1\0'


FES = {'TEXTURE.DAT': (344,b'Dave'), 'STREAMS.DAT': (345,b'Hash'),
       'BANKS.DAT': (346,b'DAVE'), 'ASSETS.DAT': (347,b'Dave')}


CHUNK = 8 * 1024 * 1024


def read_at(f, offset, size):
    f.seek(offset)
    data = f.read(size)
    if len(data) != size:
        raise ValueError(f'Unexpected EOF at offset {offset}')
    return data


def inspect(f):
    f.seek(0, 2)
    if f.tell() != TOTAL_BYTES:
        raise ValueError('Unexpected ISO size; only tested Retail USA dual-layer layout supported')
    for sector in (16, 2_084_960):
        if read_at(f, sector*SECTOR, 6) != b'\x01CD001':
            raise ValueError(f'ISO9660 PVD missing at sector {sector}')
    pvd = read_at(f, 16*SECTOR, SECTOR)
    root_sector, root_size = struct.unpack_from('<I', pvd, 158)[0], struct.unpack_from('<I', pvd, 166)[0]
    if root_sector != ROOT_SECTOR or not (1 <= root_size <= SECTOR):
        raise ValueError('Unexpected ISO9660 root directory')
    partition = read_at(f, 34*SECTOR, SECTOR)
    if struct.unpack_from('<H', partition)[0] != 5 or struct.unpack_from('<I', partition, 188)[0] != PARTITION_START:
        raise ValueError('Unexpected UDF partition descriptor')
    root = read_at(f, root_sector*SECTOR, root_size)
    entries = {}
    pos = 0
    while pos < len(root):
        n = root[pos]
        if not n:
            break
        if n < 34 or pos+n > len(root):
            raise ValueError('Malformed ISO9660 root entry')
        name_length = root[pos+32]
        if 33+name_length > n:
            raise ValueError('Malformed ISO9660 filename')
        name = root[pos+33:pos+33+name_length].decode('ascii', 'replace')
        entries[name] = (struct.unpack_from('<I', root, pos+2)[0],
                         struct.unpack_from('<I', root, pos+10)[0])
        pos += n
    layout = {}
    spans = []
    for name, (fe_sector, signature) in FES.items():
        if name+';1' not in entries:
            raise ValueError(f'Missing ISO9660 entry: {name}')
        start, size = entries[name+';1']
        fe = read_at(f, fe_sector*SECTOR, SECTOR)
        if struct.unpack_from('<H', fe)[0] != 261:
            raise ValueError(f'Unexpected UDF File Entry for {name}')
        udf_size = struct.unpack_from('<Q', fe, 56)[0]
        udf_start = struct.unpack_from('<I', fe, 312)[0] + PARTITION_START
        udf_length = struct.unpack_from('<I', fe, 308)[0]
        if udf_start != start or udf_size != size or udf_length != size:
            raise ValueError(f'ISO9660/UDF disagreement for {name}')
        if size <= 0 or size % SECTOR or start < 0 or start+size//SECTOR > LAYER2_START:
            raise ValueError(f'Invalid DAT allocation: {name}')
        if read_at(f, start*SECTOR, 4) != signature:
            raise ValueError(f'Invalid DAT signature: {name}')
        layout[name] = (start, size)
        spans.append((start, start+size//SECTOR, name))
    spans.sort()
    for a, b in zip(spans, spans[1:]):
        if a[1] > b[0]:
            raise ValueError(f'Overlapping DAT extents: {a[2]} and {b[2]}')
    return layout


def read_manifest(f):
    header = read_at(f, MANIFEST_SECTOR*SECTOR, HEADER.size)
    if header == b'\0'*HEADER.size:
        return None
    magic, version, length, checksum, reserved = HEADER.unpack(header)
    if magic != MAGIC:
        raise ValueError('Unexpected data in manifest reservation (unrecognized magic)')
    if version != 1 or reserved != b'\0'*4:
        raise ValueError('Unsupported or malformed manifest header')
    if not 0 < length <= MANIFEST_CAPACITY-HEADER.size:
        raise ValueError('Invalid manifest payload length')
    payload = read_at(f, MANIFEST_SECTOR*SECTOR+HEADER.size, length)
    if hashlib.sha256(payload).digest() != checksum:
        raise ValueError('Embedded manifest SHA256 mismatch')
    names = [x for x in payload.decode('utf-8').splitlines() if x.strip()]
    if not names or len(names) != len(set(names)):
        raise ValueError('Invalid or duplicate manifest filenames')
    return payload, len(names)


def extract_region(f, start, size, target):
    f.seek(start*SECTOR)
    remaining = size
    sha = hashlib.sha256()
    with target.open('xb') as out:
        while remaining:
            chunk = f.read(min(CHUNK, remaining))
            if not chunk:
                raise ValueError('Unexpected EOF while extracting')
            out.write(chunk)
            sha.update(chunk)
            remaining -= len(chunk)
    return sha.hexdigest()


def legacy_extractor_main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('iso', type=Path, help='Original or modified Retail USA ISO filename')
    parser.add_argument('--check-only', action='store_true', help='Inspect only; create no files')
    parser.add_argument('--output-dir', type=Path, default=Path('Extracted_DATs_108K'),
                        help='Destination folder; refuses existing output files')
    args = parser.parse_args()
    if not args.iso.is_file():
        raise ValueError(f'ISO not found: {args.iso}')
    print('MC3 Experimental ISO Extractor v4 - Step 108K')
    print(f'Source: {args.iso}')
    with args.iso.open('rb') as f:
        layout = inspect(f)
        manifest = read_manifest(f)
    print('ISO9660/UDF DAT metadata and signatures: PASS')
    for name in ('STREAMS.DAT','ASSETS.DAT'):
        sector, size = layout[name]
        print(f'  {name}: sector {sector:,}; {size:,} bytes')
    if manifest is None:
        print('Embedded STREAMS.LST: ABSENT (normal for original Retail USA ISO)')
    else:
        payload, count = manifest
        print(f'Embedded STREAMS.LST: PASS; {len(payload):,} bytes; {count:,} names')
        print(f'  SHA256: {hashlib.sha256(payload).hexdigest()}')
    print(f'Output directory: {args.output_dir}')
    targets = [args.output_dir / name for name in ('STREAMS.DAT','ASSETS.DAT')]
    if manifest is not None:
        targets.append(args.output_dir / 'STREAMS.LST')
    if any(p.exists() for p in targets):
        raise ValueError('Refusing to overwrite: '+', '.join(str(p) for p in targets if p.exists()))
    if args.check_only:
        print('CHECK-ONLY PASS: No files created or changed.')
        return 0
    if input('Extract into new output files? (Y/N), then Enter: ').strip().lower() != 'y':
        print('Cancelled; no files created.')
        return 0
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with args.iso.open('rb') as f:
        for name in ('STREAMS.DAT','ASSETS.DAT'):
            sector, size = layout[name]
            target = args.output_dir / name
            digest = extract_region(f, sector, size, target)
            print(f'{name}: extracted; SHA256 {digest}')
    if manifest is not None:
        target = args.output_dir / 'STREAMS.LST'
        with target.open('xb') as out:
            out.write(manifest[0])
        if target.read_bytes() != manifest[0]:
            raise ValueError('Recovered STREAMS.LST verification failed')
        print('STREAMS.LST: recovered byte-for-byte; PASS')
    print('SUCCESS: Source ISO unchanged. DAT archives are not yet decompiled.')
    return 0



RETAIL_LAYOUT = {
    'TEXTURE.DAT': (454764, 794839040),
    'STREAMS.DAT': (842869, 1025642496),
    'BANKS.DAT': (1343671, 52967424),
    'ASSETS.DAT': (1369534, 1444214784),
}


VIP_LAYOUT = {
    'TEXTURE.DAT': (9702, 794839040),
    'STREAMS.DAT': (397807, 1033197568),
    'BANKS.DAT': (902298, 52967424),
    'ASSETS.DAT': (928161, 1729191936),
}


VIP_V11A_LAYOUT = {
    'TEXTURE.DAT': (9702, 794839040),
    'STREAMS.DAT': (397807, 1033197568),
    'BANKS.DAT': (902298, 52967424),
    'ASSETS.DAT': (928161, 1808326656),
}

# Candidate digest from the user's analyzer report; full ISO hash is checked at runtime.
TRUSTED_VIP_V11A_SHA256 = 'b792163c131b57d76f6ebff99a0e0029f67f653309c97e02a136c3767f2c839d'


TRUSTED_RETAIL_SHA256 = 'de199f7e7f57b7cb603a129217f7482d50644fd66558450dfeb5612857b732f9'
TRUSTED_RETAIL_EXECUTABLE_SHA256 = '1b237ade5cafaf8ddd9fd049f40d81eb46f38f2600a8f1c7273d4f836973fe9d'


TRUSTED_VIP_SHA256 = '906ada438e097d4668feabd6ef8b8d388876811181cb89ea6b1648e5f2acbe4c'


CHUNK = 8 * 1024 * 1024


def sha256_file(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(CHUNK), b''):
            h.update(chunk)
    return h.hexdigest()


def matches_modified_profile(layout, reference):
    """Require known anchor, unchanged non-replaced DAT sizes, contiguous order.

    Modified STREAMS and ASSETS may change sizes; they must remain inside the
    original verified DAT allocation region. Unknown layouts are rejected.
    """
    names = ('TEXTURE.DAT', 'STREAMS.DAT', 'BANKS.DAT', 'ASSETS.DAT')
    if set(layout) != set(names):
        return False
    if layout['TEXTURE.DAT'] != reference['TEXTURE.DAT']:
        return False
    if layout['BANKS.DAT'][1] != reference['BANKS.DAT'][1]:
        return False
    end_limit = reference['ASSETS.DAT'][0] + reference['ASSETS.DAT'][1] // SECTOR
    next_sector = reference['TEXTURE.DAT'][0]
    for name in names:
        sector, size = layout[name]
        if sector != next_sector or size <= 0 or size % SECTOR:
            return False
        next_sector += size // SECTOR
        if next_sector > end_limit or next_sector > LAYER2_START:
            return False
    return True


def executable_sha256(path):
    """Identify relocated Retail outputs without guessing from their VIP-like anchor."""
    with path.open('rb') as stream:
        pvd = read_at(stream, 16 * SECTOR, SECTOR)
        sector = struct.unpack_from('<I', pvd, 158)[0]
        length = struct.unpack_from('<I', pvd, 166)[0]
        if not 0 < length <= SECTOR:
            raise ValueError('Unexpected root length while identifying custom ISO')
        directory = read_at(stream, sector * SECTOR, length)
        pos = 0
        while pos < length and directory[pos]:
            record_length = directory[pos]
            if record_length < 34 or pos + record_length > length:
                raise ValueError('Malformed root while identifying custom ISO')
            name_length = directory[pos + 32]
            if 33 + name_length > record_length:
                raise ValueError('Malformed root name')
            name = directory[pos + 33:pos + 33 + name_length]
            if name == b'SLUS_213.55;1':
                at = struct.unpack_from('<I', directory, pos + 2)[0] * SECTOR
                size = struct.unpack_from('<I', directory, pos + 10)[0]
                if not 0 < size <= 16 * 1024 * 1024 or at + size > path.stat().st_size:
                    raise ValueError('Invalid executable extent')
                return hashlib.sha256(read_at(stream, at, size)).hexdigest()
            pos += record_length
    return None


def custom_layout_kind(path, layout):
    if matches_modified_profile(layout, RETAIL_LAYOUT):
        return 'RETAIL_CUSTOM_WITH_MANIFEST'
    if layout.get('TEXTURE.DAT', (None,))[0] == 9702 and executable_sha256(path) == TRUSTED_RETAIL_EXECUTABLE_SHA256:
        # Re-importing this new layout is not yet supported. In particular it
        # must never be recorded as VIP merely because TEXTURE now starts at 9702.
        return 'UNSUPPORTED_RETAIL_RELOCATED_LAYOUT'
    if matches_modified_profile(layout, VIP_LAYOUT):
        return 'VIP_CUSTOM_WITH_MANIFEST'
    return 'UNSUPPORTED_CUSTOM_LAYOUT'


def classify(path, retail_sha256=TRUSTED_RETAIL_SHA256, vip_sha256=TRUSTED_VIP_SHA256):
    with path.open('rb') as f:
        layout = inspect(f)
        manifest = read_manifest(f)
        # Reject nonzero bytes beyond a valid embedded manifest too.
        f.seek(MANIFEST_SECTOR * SECTOR)
        region = f.read(MANIFEST_CAPACITY)
        if len(region) != MANIFEST_CAPACITY:
            raise ValueError('Manifest reservation is truncated')
        if manifest is None:
            if any(region):
                raise ValueError('Manifest absent but reserved region is not zero-filled')
        else:
            payload, _ = manifest
            package_end = 64 + len(payload)
            if any(region[package_end:]):
                raise ValueError('Embedded manifest has nonzero trailing padding')

    if manifest is not None:
        kind = custom_layout_kind(path, layout)
        payload, count = manifest
        return kind, layout, (count, hashlib.sha256(payload).hexdigest())

    if layout == RETAIL_LAYOUT:
        print('Retail reference layout matched; hashing full ISO...', flush=True)
        kind = ('VERIFIED_RETAIL_REFERENCE' if sha256_file(path) == retail_sha256.lower()
                else 'RETAIL_LAYOUT_BUT_HASH_MISMATCH')
    elif layout == VIP_LAYOUT:
        print('VIP reference layout matched; hashing full ISO...', flush=True)
        kind = ('VERIFIED_VIP_REFERENCE' if sha256_file(path) == vip_sha256.lower()
                else 'VIP_LAYOUT_BUT_HASH_MISMATCH')
    elif layout == VIP_V11A_LAYOUT:
        print('VIP v1.1-A reference layout matched; hashing full ISO...', flush=True)
        kind = ('VERIFIED_VIP_V11A_REFERENCE'
                if sha256_file(path) == TRUSTED_VIP_V11A_SHA256
                else 'VIP_V11A_LAYOUT_BUT_HASH_MISMATCH')
    else:
        kind = 'UNSUPPORTED_MANIFEST_FREE_LAYOUT'
    return kind, layout, None


def detector_main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('iso', type=Path)
    args = p.parse_args()
    if not args.iso.is_file():
        raise ValueError(f'ISO not found: {args.iso}')
    print('MC3 Step 108S - Retail/VIP Source Detector Experiment (READ ONLY)')
    print(f'Source: {args.iso}')
    result, layout, manifest = classify(args.iso)
    print('ISO9660/UDF DAT inspection: PASS')
    for name in FES:
        sector, size = layout[name]
        print(f'  {name}: {sector:,}..{sector + size//SECTOR-1:,}; {size:,} bytes')
    if manifest:
        print(f'Embedded STREAMS.LST: PASS; {manifest[0]:,} names; SHA256 {manifest[1]}')
    else:
        print('Embedded STREAMS.LST: ABSENT; reservation zero-filled')
    print(f'CLASSIFICATION: {result}')
    supported = {'VERIFIED_RETAIL_REFERENCE', 'VERIFIED_VIP_REFERENCE',
                 'RETAIL_CUSTOM_WITH_MANIFEST', 'VIP_CUSTOM_WITH_MANIFEST'}
    print('ROUTE CANDIDATE: Supported profile' if result in supported else
          'ROUTING BLOCKED: Unsupported or unverified ISO')
    print('READ ONLY: No files created or modified.')
    return 0 if result in supported else 2



NAMES = ('STREAMS.DAT', 'ASSETS.DAT')


def sha_region(source, sector, size):
    h = hashlib.sha256()
    with source.open('rb') as iso:
        iso.seek(sector * SECTOR)
        remaining = size
        while remaining:
            data = iso.read(min(CHUNK, remaining))
            if not data:
                raise ValueError('Unexpected EOF verifying source archive')
            h.update(data)
            remaining -= len(data)
    return h.hexdigest()


def copy_region(source, sector, size, destination):
    h = hashlib.sha256()
    with source.open('rb') as iso, destination.open('xb') as out:
        iso.seek(sector * SECTOR)
        remaining = size
        while remaining:
            data = iso.read(min(CHUNK, remaining))
            if not data:
                raise ValueError('Unexpected EOF extracting archive')
            out.write(data)
            h.update(data)
            remaining -= len(data)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('iso', type=Path)
    p.add_argument('--output-dir', type=Path, required=True,
                   help='Separate test output folder; do not use ISO_FILES')
    p.add_argument('--production', action='store_true', help='Permit project ISO_FILES as output')
    p.add_argument('--yes', action='store_true', help='Skip second prompt after launcher confirmation')
    p.add_argument('--extract', action='store_true',
                   help='Enable actual extraction after explicit Y + Enter confirmation')
    args = p.parse_args()
    if args.yes and not (args.production and args.extract):
        raise ValueError('--yes requires --production --extract')
    source = args.iso.resolve(strict=True)
    target = args.output_dir.resolve()
    working = Path.cwd().resolve()
    if not source.is_file():
        raise ValueError(f'Not a file: {source}')
    if (target == working / 'ISO_FILES' and not args.production) or target == working or target == source.parent:
        raise ValueError('Unsafe output directory: use a separate named test folder')
    if target == source or source in target.parents:
        raise ValueError('Output directory conflicts with source ISO')
    if target.exists() and (not target.is_dir() or target.is_symlink()):
        raise ValueError('Output directory must be a real directory')

    print('MC3 Step 108S.80 - Retail/VIP Extraction Router Experiment')
    print(f'Source: {source}')
    classification, layout, manifest_info = classify(source)
    print(f'CLASSIFICATION: {classification}')
    if classification == 'VERIFIED_RETAIL_REFERENCE':
        with source.open('rb') as f:
            _retail_inspect_base(f, _RETAIL_ARCHIVES)
        print('RETAIL EXTRACTOR v3 COMPATIBILITY: PASS')
        print('ROUTE: Verified retail DAT extraction (v3 validated layout)')
        manifest_payload = None
    elif classification in ('VERIFIED_VIP_REFERENCE', 'VERIFIED_VIP_V11A_REFERENCE'):
        # The source detector has already authenticated the full VIP ISO SHA256.
        # Reinspect to guard against a changed source before any extraction.
        with source.open('rb') as f:
            if inspect(f) != layout or read_manifest(f) is not None:
                raise ValueError('VIP reference changed during inspection')
        print('VIP REFERENCE COMPATIBILITY: PASS (' + classification + ')')
        print('ROUTE: Verified original VIP DAT extraction (no embedded manifest)')
        print('NOTE: VIP STREAMS decompilation needs the verified filename list.')
        manifest_payload = None
    elif classification in ('RETAIL_CUSTOM_WITH_MANIFEST', 'VIP_CUSTOM_WITH_MANIFEST'):
        with source.open('rb') as f:
            if inspect(f) != layout:
                raise ValueError('ISO layout changed during inspection')
            manifest = read_manifest(f)
        if manifest is None or len(manifest[0]) == 0:
            raise ValueError('Validated manifest disappeared')
        manifest_payload = manifest[0]
        if (manifest[1], hashlib.sha256(manifest_payload).hexdigest()) != manifest_info:
            raise ValueError('Manifest changed during inspection')
        print(f'CUSTOM EXTRACTOR v4 COMPATIBILITY: PASS ({manifest[1]:,} names)')
        print('ROUTE: Modified DAT extraction + embedded STREAMS.LST recovery')
    else:
        print('ROUTING BLOCKED: Unsupported or unverified source')
        return 2

    names = list(NAMES) + (['STREAMS.LST'] if manifest_payload is not None else [])
    print(f'Output directory: {target}')
    for name in NAMES:
        sector, size = layout[name]
        print(f'  {name}: sector {sector:,}; {size:,} bytes')
    if manifest_payload is not None:
        print(f'  STREAMS.LST: {len(manifest_payload):,} bytes (embedded manifest)')
    # Refuse any preexisting output, even in preflight. Do not mix generations.
    if target.exists() and any(target.iterdir()) and not (args.production and not args.extract):
        raise ValueError('Output folder is not empty; use a fresh directory')
    if any((target / name).exists() for name in names) and not (args.production and not args.extract):
        raise ValueError('Output conflict; refusing to overwrite')
    if not args.extract:
        print('PREFLIGHT PASSED. No files created, modified, or deleted.')
        print('To extract: repeat with --extract and confirm Y + Enter.')
        return 0
    if not args.yes and input('Extract to this output folder? (Y/N), then Enter: ').strip().lower() != 'y':
        print('CANCELLED. No files created.')
        return 0
    # Recheck immediately before writing; never overwrite an existing directory's contents.
    if target.exists() and any(target.iterdir()):
        raise ValueError('Output directory became nonempty; extraction blocked')
    target.mkdir(parents=True, exist_ok=True)
    created = []
    try:
        for name in NAMES:
            sector, size = layout[name]
            destination = target / name
            print(f'Extracting {name}...', flush=True)
            created.append(destination)
            actual = copy_region(source, sector, size, destination)
            expected = sha_region(source, sector, size)
            if actual != expected or destination.stat().st_size != size:
                raise ValueError(f'{name} verification failed')
            print(f'  {name}: size and source SHA256 PASS ({actual})', flush=True)
        if manifest_payload is not None:
            destination = target / 'STREAMS.LST'
            created.append(destination)
            with destination.open('xb') as out:
                out.write(manifest_payload)
            if destination.read_bytes() != manifest_payload:
                raise ValueError('STREAMS.LST verification failed')
            print('  STREAMS.LST: byte-for-byte manifest verification PASS')
    except Exception:
        print('EXTRACTION FAILED. Cleaning up files created in this run.', file=sys.stderr)
        for path in created:
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                print(f'WARNING: Could not remove {path}: {exc}', file=sys.stderr)
        raise
    print('EXTRACTION SUCCESS. Source ISO unchanged; DAT files not yet decompiled.')
    return 0



if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, UnicodeError, KeyboardInterrupt) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
