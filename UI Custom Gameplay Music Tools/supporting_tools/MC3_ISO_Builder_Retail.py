#!/usr/bin/env python3
"""MC3 retail / VIP dual-layer ISO DAT replacement builder.

Only the two specifically validated MC3 layouts are supported.
The source ISO is never opened for writing. Standard library, Python 3.9+.
Use --check-only for a read-only compatibility preflight.
"""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import struct
import sys

SECTOR = 2048
TOTAL_SECTORS = 4_169_904
LAYER2_START = 2_084_944
PARTITION_START = 266
ROOT_SECTOR = 261
CHUNK = 8 * 1024 * 1024
OUT_NAME = 'MC3_Modified_DUB.iso'

# These are *exact* observed archive layouts, not generic MC3 compatibility.
PROFILES = {
    'VIP Expansion': {
        'filename': 'MC3-VIP-Expansion-ONLY.iso',
        'archives': [
            ('TEXTURE.DAT', 9702, 794_839_040, 344, b'Dave'),
            ('STREAMS.DAT', 397807, 1_033_197_568, 345, b'Hash'),
            ('BANKS.DAT', 902298, 52_967_424, 346, b'DAVE'),
            ('ASSETS.DAT', 928161, 1_729_191_936, 347, b'Dave'),
        ],
    },
    'Retail USA': {
        'filename': 'Midnight Club 3 - DUB Edition Remix (USA).iso',
        'archives': [
            ('TEXTURE.DAT', 454764, 794_839_040, 344, b'Dave'),
            ('STREAMS.DAT', 842869, 1_025_642_496, 345, b'Hash'),
            ('BANKS.DAT', 1343671, 52_967_424, 346, b'DAVE'),
            ('ASSETS.DAT', 1369534, 1_444_214_784, 347, b'Dave'),
        ],
    },
}


def read_exact(f, position, size):
    f.seek(position)
    data = f.read(size)
    if len(data) != size:
        raise ValueError(f'Unexpected EOF at byte {position}')
    return data


def u16(buf, off):
    return struct.unpack_from('<H', buf, off)[0]


def u32(buf, off):
    return struct.unpack_from('<I', buf, off)[0]


def u64(buf, off):
    return struct.unpack_from('<Q', buf, off)[0]


def crc16(data):
    crc = 0
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            crc = ((crc << 1) ^ (0x1021 if crc & 0x8000 else 0)) & 0xFFFF
    return crc


def tag_checksum(buf):
    return sum(buf[i] for i in range(16) if i != 4) & 0xFF


def inspect_base(f, dat_info):
    f.seek(0, os.SEEK_END)
    if f.tell() != TOTAL_SECTORS * SECTOR:
        raise ValueError('Source ISO has unexpected physical size')
    for pvd_sector in (16, 2_084_960):
        pvd = read_exact(f, pvd_sector * SECTOR, SECTOR)
        if pvd[:6] != b'\x01CD001':
            raise ValueError(f'Invalid ISO9660 PVD at sector {pvd_sector}')
    pvd = read_exact(f, 16 * SECTOR, SECTOR)
    root_size = u32(pvd, 166)
    if u32(pvd, 158) != ROOT_SECTOR or not (1 <= root_size <= SECTOR):
        raise ValueError('Unexpected ISO9660 root directory location/size')
    root = read_exact(f, ROOT_SECTOR * SECTOR, root_size)
    part = read_exact(f, 34 * SECTOR, SECTOR)
    if u16(part, 0) != 5 or u32(part, 188) != PARTITION_START or u32(part, 192) != 2_084_693:
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
        if sector != expected_next or size % SECTOR:
            raise ValueError(f'Unsupported non-contiguous DAT layout: {name}')
        expected_next = sector + size // SECTOR
        key = name + ';1'
        if key not in records:
            raise ValueError(f'Missing ISO9660 root entry: {key}')
        pos = records[key]
        if u32(root, pos + 2) != sector or u32(root, pos + 10) != size:
            raise ValueError(f'Unexpected base ISO9660 allocation: {name}')
        if struct.unpack_from('>I', root, pos + 6)[0] != sector or struct.unpack_from('>I', root, pos + 14)[0] != size:
            raise ValueError(f'Unexpected big-endian ISO9660 allocation: {name}')
        fe = read_exact(f, fe_sector * SECTOR, SECTOR)
        if u16(fe, 0) != 261 or u32(fe, 12) != fe_sector - PARTITION_START:
            raise ValueError(f'Unexpected UDF FE tag: {name}')
        if u16(fe, 10) > SECTOR - 16 or crc16(fe[16:16 + u16(fe, 10)]) != u16(fe, 8) or tag_checksum(fe) != fe[4]:
            raise ValueError(f'Invalid source UDF integrity fields: {name}')
        if (u16(fe, 34) & 7) != 0 or u32(fe, 168) != 132 or u32(fe, 172) != 8:
            raise ValueError(f'Unexpected UDF allocation descriptor layout: {name}')
        if u64(fe, 56) != size or u32(fe, 312) + PARTITION_START != sector or u32(fe, 308) != size:
            raise ValueError(f'Unexpected UDF archive allocation: {name}')
        expected_blocks = (size + SECTOR - 1) // SECTOR
        if u64(fe, 64) != expected_blocks:
            raise ValueError(f'Unexpected UDF recorded blocks: {name}')
        if read_exact(f, sector * SECTOR, 4) != signature:
            raise ValueError(f'Unexpected source DAT signature: {name}')
    return records, root_size


def plan(root, dat_info, replacements, relocate_archives=False):
    rows = []
    if relocate_archives and dat_info != PROFILES['Retail USA']['archives']:
        raise ValueError('Retail relocation requires exact original archive geometry')
    next_sector = 9702 if relocate_archives else dat_info[0][1]
    for name, base_sector, base_size, fe_sector, signature in dat_info:
        candidate = replacements / name
        use_replacement = name in ('STREAMS.DAT', 'ASSETS.DAT')
        if use_replacement and not candidate.is_file():
            raise ValueError(f'Required replacement missing: {candidate}')
        if not use_replacement and candidate.exists():
            raise ValueError(f'Unexpected replacement {candidate}; this prototype only supports STREAMS and ASSETS')
        size = candidate.stat().st_size if use_replacement else base_size
        if size < 4 or size > 0xFFFFFFFF:
            raise ValueError(f'Invalid ISO9660 size for {name}: {size}')
        if size % SECTOR:
            raise ValueError(f'{name} is not 2048-byte aligned')
        if use_replacement:
            with candidate.open('rb') as f:
                if f.read(4) != signature:
                    raise ValueError(f'Invalid replacement signature: {name}')
        sectors = (size + SECTOR - 1) // SECTOR
        end = next_sector + sectors - 1
        original_last = dat_info[-1][1] + dat_info[-1][2] // SECTOR - 1
        if end > original_last:
            raise ValueError(f'{name} exceeds the original verified DAT region')
        if end >= LAYER2_START:
            raise ValueError(f'{name} extends into the second layer')
        rows.append(dict(name=name, base_sector=base_sector, base_size=base_size,
                         fe_sector=fe_sector, signature=signature, path=candidate if use_replacement else None,
                         size=size, sector=next_sector, end=end))
        next_sector = end + 1
    return rows


def check_relocation_space(source):
    """The fingerprint-verified Retail has a zero prefix gap ending at TEXTURE."""
    with source.open('rb') as stream:
        stream.seek(9702 * SECTOR)
        remaining = (454764 - 9702) * SECTOR
        while remaining:
            data = stream.read(min(CHUNK, remaining))
            if not data or data.strip(b'\0'):
                raise ValueError('Retail relocation region is not entirely zero-filled')
            remaining -= len(data)
    print('Retail relocation space: 911,486,976 zero bytes verified', flush=True)


def patch_metadata(out, records, rows, root_size):
    root = bytearray(read_exact(out, ROOT_SECTOR * SECTOR, root_size))
    for row in rows:
        name, sector, size = row['name'], row['sector'], row['size']
        off = records[name + ';1']
        struct.pack_into('<I', root, off + 2, sector)
        struct.pack_into('>I', root, off + 6, sector)
        struct.pack_into('<I', root, off + 10, size)
        struct.pack_into('>I', root, off + 14, size)
        fe_off = row['fe_sector'] * SECTOR
        fe = bytearray(read_exact(out, fe_off, SECTOR))
        struct.pack_into('<Q', fe, 56, size)
        struct.pack_into('<Q', fe, 64, (size + SECTOR - 1) // SECTOR)
        # Existing VIP builder encodes the full byte length here, including
        # bit 30 for ASSETS.DAT. Preserve this observed layout deliberately.
        struct.pack_into('<I', fe, 308, size)
        struct.pack_into('<I', fe, 312, sector - PARTITION_START)
        crc_len = u16(fe, 10)
        struct.pack_into('<H', fe, 8, crc16(fe[16:16 + crc_len]))
        fe[4] = tag_checksum(fe)
        out.seek(fe_off)
        out.write(fe)
    out.seek(ROOT_SECTOR * SECTOR)
    out.write(root)


def copy_archive(src, dst, length):
    remaining = length
    while remaining:
        chunk = src.read(min(CHUNK, remaining))
        if not chunk:
            raise ValueError('Unexpected EOF while copying archive')
        dst.write(chunk)
        remaining -= len(chunk)


def hash_region(f, start, length):
    h = hashlib.sha256()
    f.seek(start)
    while length:
        block = f.read(min(CHUNK, length))
        if not block:
            raise ValueError('Unexpected EOF during verification')
        h.update(block)
        length -= len(block)
    return h.hexdigest()


def verify(source_path, output_path, rows, root_size):
    with source_path.open('rb') as base, output_path.open('rb') as out:
        if out.seek(0, os.SEEK_END) != TOTAL_SECTORS * SECTOR:
            raise ValueError('Output ISO size mismatch')
        records = inspect_output(out, rows, root_size)
        if len(records) != 4:
            raise ValueError('Not all DAT records verified')
        for row in rows:
            offset = row['sector'] * SECTOR
            with (row['path'].open('rb') if row['path'] else source_path.open('rb')) as input_file:
                if not row['path']:
                    input_file.seek(row['base_sector'] * SECTOR)
                expected = hashlib.sha256()
                remaining = row['size']
                while remaining:
                    block = input_file.read(min(CHUNK, remaining))
                    if not block:
                        raise ValueError(f'Unexpected input EOF: {row["name"]}')
                    expected.update(block)
                    remaining -= len(block)
            actual = hash_region(out, offset, row['size'])
            if actual != expected.hexdigest():
                raise ValueError(f'Archive SHA256 mismatch: {row["name"]}')
            print(f'  {row["name"]}: SHA256 PASS')
        from iso_preservation import verify_protected_bytes
        verify_protected_bytes(source_path, output_path,
            [(ROOT_SECTOR*SECTOR,(ROOT_SECTOR+1)*SECTOR), (344*SECTOR,348*SECTOR),
             (rows[0]['sector']*SECTOR,(rows[-1]['end']+1)*SECTOR),
             (MANIFEST_SECTOR*SECTOR,MANIFEST_SECTOR*SECTOR+MANIFEST_CAPACITY)])
        print('  All protected bytes, including the entire second layer: SHA256 PASS')


def inspect_output(out, rows, root_size):
    pvd = read_exact(out, 16 * SECTOR, SECTOR)
    if pvd[:6] != b'\x01CD001':
        raise ValueError('Output PVD invalid')
    if u32(pvd, 158) != ROOT_SECTOR or u32(pvd, 166) != root_size:
        raise ValueError('Output root directory descriptor mismatch')
    root = read_exact(out, ROOT_SECTOR * SECTOR, root_size)
    found = []
    off = 0
    while off < len(root):
        n = root[off]
        if not n:
            break
        if n < 34 or off + n > len(root):
            raise ValueError('Output ISO9660 root record invalid')
        name_len = root[off + 32]
        name = root[off + 33:off + 33 + name_len].decode('ascii', 'replace')
        for row in rows:
            if name == row['name'] + ';1':
                sector, size = row['sector'], row['size']
                if (u32(root, off + 2) != sector or u32(root, off + 10) != size or
                    struct.unpack_from('>I', root, off + 6)[0] != sector or
                    struct.unpack_from('>I', root, off + 14)[0] != size):
                    raise ValueError(f'Output ISO9660 record mismatch: {name}')
                fe = read_exact(out, row['fe_sector'] * SECTOR, SECTOR)
                if (u16(fe, 0) != 261 or u64(fe, 56) != size or
                    u64(fe, 64) != (size + SECTOR - 1) // SECTOR or
                    u32(fe, 308) != size or u32(fe, 312) + PARTITION_START != sector or
                    crc16(fe[16:16 + u16(fe, 10)]) != u16(fe, 8) or
                    tag_checksum(fe) != fe[4]):
                    raise ValueError(f'Output UDF FE mismatch: {name}')
                found.append(name)
        off += n
    return found


# Step 108L.2: manifest embedding into a new experimental ISO.
MANIFEST_SECTOR = 2_074_717
MANIFEST_CAPACITY = 1_048_576
MANIFEST_MAGIC = b'MC3STREAMSLSTv1\0'
MANIFEST_HEADER = struct.Struct('<16sIQ32s4s')


def check_manifest_preflight(source, rows, manifest_path):
    if not manifest_path.is_file():
        raise ValueError(f'Missing manifest source: {manifest_path}')
    payload = manifest_path.read_bytes()
    if not payload:
        raise ValueError('STREAMS.LST is empty')
    names = [line for line in payload.decode('utf-8').splitlines() if line.strip()]
    if len(names) != len(set(names)):
        raise ValueError('STREAMS.LST contains duplicate filename entries')
    package_size = MANIFEST_HEADER.size + len(payload)
    if package_size > MANIFEST_CAPACITY:
        raise ValueError(f'Manifest too large: {package_size:,} > {MANIFEST_CAPACITY:,}')
    first = MANIFEST_SECTOR
    last = first + MANIFEST_CAPACITY // SECTOR - 1
    if last >= LAYER2_START:
        raise ValueError('Manifest reservation crosses layer boundary')
    for row in rows:
        if not (row['end'] < first or row['sector'] > last):
            raise ValueError(f'Manifest reservation overlaps planned {row["name"]}')
    with source.open('rb') as f:
        f.seek(first * SECTOR)
        region = f.read(MANIFEST_CAPACITY)
    if len(region) != MANIFEST_CAPACITY:
        raise ValueError('Source ISO manifest reservation is truncated')
    if any(region):
        raise ValueError('Manifest reservation is not empty in the original ISO; refusing unsafe assumption')
    header = MANIFEST_HEADER.pack(MANIFEST_MAGIC, 1, len(payload), hashlib.sha256(payload).digest(), b'\0'*4)
    if len(header) != 64:
        raise ValueError('Unexpected manifest header size')
    print('\nManifest preflight:')
    print(f'  Filename entries: {len(names):,}')
    print(f'  STREAMS.LST bytes: {len(payload):,}')
    print(f'  Package bytes: {package_size:,} / {MANIFEST_CAPACITY:,}')
    print(f'  STREAMS.LST SHA256: {hashlib.sha256(payload).hexdigest()}')
    print(f'  Reserved sectors: {first:,}..{last:,}')
    print('  Source reservation zero-filled: PASS')
    print('  Planned DAT/manifest non-overlap: PASS')
    print('  Manifest header serialization: PASS')
    return header + payload


def main():
    parser = argparse.ArgumentParser(description='MC3 verified-layout ISO builder')
    parser.add_argument('--profile', choices=('retail',), default='retail',
                        help='Step 108L.1 currently supports Retail USA only')
    parser.add_argument('--source', default=None,
                        help='Original verified ISO path (any filename or location)')
    parser.add_argument('--manifest', default='ISO_FILES/STREAMS.LST',
                        help='Path to current STREAMS.LST')
    parser.add_argument('--replacement-dir', default='ISO_FILES',
                        help='Directory containing compiled STREAMS.DAT and ASSETS.DAT (default: ISO_FILES)')
    parser.add_argument('--output', default='MC3_Modified_DUB.iso',
                        help='New experimental ISO filename; existing outputs are never overwritten')
    parser.add_argument('--yes', action='store_true', help='Skip interactive confirmation; launcher already authorized build')
    parser.add_argument('--check-only', action='store_true',
                        help='Read-only validation and archive layout simulation')
    parser.add_argument('--relocate-archives', action='store_true',
                        help='Move trusted Retail archives into the verified zero prefix gap')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    replacement_dir = Path(args.replacement_dir)
    if not replacement_dir.is_absolute():
        replacement_dir = root / replacement_dir
    profile_name = 'Retail USA' if args.profile == 'retail' else 'VIP Expansion'
    profile = PROFILES[profile_name]
    dat_info = profile['archives']
    source = Path(args.source).expanduser().resolve() if args.source else (root / profile['filename']).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    output = output.resolve()
    if output == source.resolve() or output == (root / 'MC3Dub_CustomMusic_Retail.iso').resolve():
        raise ValueError('Refusing to replace the source or working production ISO')
    if not source.is_file():
        raise ValueError(f'Missing base ISO: {source}')
    print(f'MC3 PS2 Ultimate Music Tools - ISO Builder 108Q (manifest-enabled) ({profile_name})')
    print(f'Replacement directory: {replacement_dir}')
    print('Validating original ISO...')
    from MC3_ISO_Extractor import classify
    source_kind, _, _ = classify(source)
    if source_kind != 'VERIFIED_RETAIL_REFERENCE':
        raise ValueError('Retail building requires the fingerprint-verified original USA ISO; unsupported/custom sources need separate layout validation')
    with source.open('rb') as f:
        records, root_size = inspect_base(f, dat_info)
    if args.relocate_archives:
        check_relocation_space(source)
    from archive_build_gate import check_records
    check_records(replacement_dir, 'retail-expanded' if args.relocate_archives else args.profile)
    rows = plan(root, dat_info, replacement_dir, relocate_archives=args.relocate_archives)
    print('Source layout and DAT signatures: PASS')
    print(f'ISO9660 root directory size: {root_size} bytes')
    print('\nPlanned DAT layout:')
    for row in rows:
        print(f'  {row["name"]:<12} {row["sector"]:>8}..{row["end"]:<8} {row["size"]:>12} bytes')
    original_last = dat_info[-1][1] + dat_info[-1][2] // SECTOR - 1
    print(f'  Original DAT region ends: {original_last}')
    print(f'  Remaining before second layer: {LAYER2_START - rows[-1]["end"] - 1} sectors')
    print('  Archives fit the zero-gap relocation region before the manifest: PASS' if args.relocate_archives
          else '  All planned DAT writes remain inside the original DAT region: PASS')
    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path
    manifest_package = check_manifest_preflight(source, rows, manifest_path)
    if args.check_only:
        print('\nSTEP 108Q PREFLIGHT PASS. Read-only; no ISO or other files changed.')
        return 0
    if output.exists():
        raise ValueError(f'Output already exists; refusing overwrite: {output}')
    if not output.parent.is_dir():
        raise ValueError(f'Output directory missing: {output.parent}')
    print('\nThis operation will create a NEW 8.54 GB manifest-enabled ISO.')
    print(f'Output: {output}')
    if not args.yes and input('Proceed with manifest-enabled ISO build? (Y/N), then Enter: ').strip().lower() != 'y':
        print('Cancelled. No ISO created.')
        return 2
    # A distinct temporary path ensures that even an interrupted build cannot
    # damage the existing verified ISO. Refuse to overwrite stale temp files.
    staging = output.with_name(output.name + '.building.tmp')
    if staging.exists():
        raise ValueError(f'Temporary output already exists: {staging}. Move or remove it after inspection.')
    try:
        print('Copying source ISO (second layer preserved)...')
        with source.open('rb') as inp, staging.open('xb') as out:
            shutil.copyfileobj(inp, out, CHUNK)
            out.flush()
        print('Inserting DAT archives...')
        with source.open('rb') as base, staging.open('r+b') as out:
            for row in rows:
                print(' ', row['name'])
                out.seek(row['sector'] * SECTOR)
                if row['path']:
                    with row['path'].open('rb') as inp:
                        copy_archive(inp, out, row['size'])
                else:
                    base.seek(row['base_sector'] * SECTOR)
                    copy_archive(base, out, row['size'])
            print('Embedding STREAMS.LST manifest in reserved first-layer region...')
            out.seek(MANIFEST_SECTOR * SECTOR)
            out.write(manifest_package)
            print('Updating ISO9660 and UDF metadata...')
            patch_metadata(out, records, rows, root_size)
            out.flush()
            os.fsync(out.fileno())
        print('Verifying output...')
        verify(source, staging, rows, root_size)
        with staging.open('rb') as out:
            region = read_exact(out, MANIFEST_SECTOR * SECTOR, MANIFEST_CAPACITY)
        if region[:len(manifest_package)] != manifest_package:
            raise ValueError('Embedded manifest readback mismatch')
        if any(region[len(manifest_package):]):
            raise ValueError('Unexpected data after embedded manifest')
        magic, version, length, digest, reserved = MANIFEST_HEADER.unpack(region[:64])
        payload = region[64:64+length]
        if (magic != MANIFEST_MAGIC or version != 1 or reserved != b'\0'*4 or
                hashlib.sha256(payload).digest() != digest or
                payload != manifest_path.read_bytes()):
            raise ValueError('Embedded manifest integrity verification failed')
        print('  Embedded STREAMS.LST: SHA256 and byte-for-byte PASS')
        # Atomic replacement on the same filesystem, only after verification.
        if output.exists():
            raise ValueError('Output appeared during build; refusing overwrite')
        os.link(staging, output)
        staging.unlink()
        print(f'\nSUCCESS: {output}')
        print('Next: test in PCSX2, including cinematics and custom music.')
        return 0
    except Exception:
        print(f'Existing ISO preserved (if present). Incomplete staging file may exist: {staging}')
        print('Do not use the staging file; inspect and remove it before retrying.')
        raise


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyboardInterrupt) as exc:
        print(f'\nERROR: {exc}', file=sys.stderr)
        sys.exit(1)
