#!/usr/bin/env python3
"""Create an isolated VIP v1.1-A PCSX2 test ISO, never modifying the source ISO.

Requires the exact trusted VIP v1.1-A reference ISO and a rebuilt Dave ASSETS.DAT.
The replacement is padded to the original allocation; ISO9660/UDF metadata is
left untouched, so this is appropriate ONLY for a same-extent test image.
"""
import argparse
import hashlib
from pathlib import Path
import struct

SECTOR = 2048
ISO_BYTES = 8_539_963_392
START_SECTOR = 928_161
ALLOC = 1_808_326_656
EXPECTED_ISO_SHA = 'b792163c131b57d76f6ebff99a0e0029f67f653309c97e02a136c3767f2c839d'
EXPECTED_ASSETS_SHA = '4b9ad47132aa3fcaa5650b6c59c16ddd5a02c58cbff4e731607e3cffe87019ca'
CHUNK = 8 * 1024 * 1024


def digest_file(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(CHUNK), b''):
            h.update(block)
    return h.hexdigest()


def digest_extent(f, start, size):
    h = hashlib.sha256()
    f.seek(start)
    while size:
        block = f.read(min(CHUNK, size))
        if not block:
            raise ValueError('Unexpected EOF hashing ISO extent')
        h.update(block)
        size -= len(block)
    return h.hexdigest()


def read_exact(f, at, count):
    f.seek(at)
    result = f.read(count)
    if len(result) != count:
        raise ValueError('Unexpected end of ISO')
    return result


def validate_extent(f):
    for pvd_sector in (16, 2_084_960):
        pvd = read_exact(f, pvd_sector * SECTOR, SECTOR)
        if pvd[:6] != b'\x01CD001':
            raise ValueError(f'Missing ISO9660 primary descriptor at {pvd_sector}')
    pvd = read_exact(f, 16 * SECTOR, SECTOR)
    root_sector, root_size = struct.unpack_from('<II', pvd, 158)[0], struct.unpack_from('<I', pvd, 166)[0]
    if not (0 < root_size <= SECTOR):
        raise ValueError('Unexpected root directory size')
    directory = read_exact(f, root_sector * SECTOR, root_size)
    pos = 0
    found = None
    while pos < len(directory) and directory[pos]:
        record_len = directory[pos]
        if record_len < 34 or pos + record_len > len(directory):
            raise ValueError('Malformed ISO9660 directory record')
        name_len = directory[pos + 32]
        name = directory[pos + 33:pos + 33 + name_len].decode('ascii', 'replace')
        if name == 'ASSETS.DAT;1':
            found = (struct.unpack_from('<I', directory, pos + 2)[0],
                     struct.unpack_from('<I', directory, pos + 10)[0])
        pos += record_len
    if found != (START_SECTOR, ALLOC):
        raise ValueError(f'Unexpected ASSETS.DAT ISO9660 extent: {found}')
    # UDF file entry is known from the VIP reference layout.
    fe = read_exact(f, 347 * SECTOR, SECTOR)
    partition = read_exact(f, 34 * SECTOR, SECTOR)
    partition_start = struct.unpack_from('<I', partition, 188)[0]
    udf_extent = (struct.unpack_from('<I', fe, 312)[0] + partition_start,
                  struct.unpack_from('<Q', fe, 56)[0],
                  struct.unpack_from('<I', fe, 308)[0])
    if struct.unpack_from('<H', fe)[0] != 261 or udf_extent != (START_SECTOR, ALLOC, ALLOC):
        raise ValueError(f'Unexpected ASSETS.DAT UDF extent: {udf_extent}')
    if read_exact(f, START_SECTOR * SECTOR, 4) != b'Dave':
        raise ValueError('Source ASSETS.DAT does not start with Dave')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--iso', type=Path, required=True, help='Original, unmodified VIP v1.1-A ISO')
    ap.add_argument('--assets', type=Path, required=True, help='Verified experimental ASSETS.DAT')
    ap.add_argument('--output', type=Path, required=True, help='New test ISO path')
    ap.add_argument('--build', action='store_true', help='Create test ISO; otherwise preflight only')
    args = ap.parse_args()
    iso, assets, output = (p.resolve() for p in (args.iso, args.assets, args.output))
    if len({iso, assets, output}) != 3:
        raise ValueError('Source ISO, archive, and output must be different files')
    if output.exists():
        raise FileExistsError(f'Refusing to overwrite existing output: {output}')
    if iso.stat().st_size != ISO_BYTES:
        raise ValueError('Unexpected source ISO size')
    size = assets.stat().st_size
    if not (16 <= size <= ALLOC):
        raise ValueError(f'Rebuilt archive does not fit the allocation: {size} > {ALLOC}')
    if assets.open('rb').read(4) != b'Dave':
        raise ValueError('Replacement archive does not have Dave signature')
    print('VIP v1.1-A isolated ISO patch preflight')
    print('Original ISO:', iso)
    print('Replacement ASSETS.DAT:', assets)
    print('New test ISO:', output)
    print('Replacement bytes:', f'{size:,}')
    print('Zero padding:', f'{ALLOC - size:,}')
    with iso.open('rb') as f:
        validate_extent(f)
        print('Checking original ASSETS.DAT SHA-256...')
        original_hash = digest_extent(f, START_SECTOR * SECTOR, ALLOC)
        if original_hash != EXPECTED_ASSETS_SHA:
            raise ValueError(f'Original ASSETS.DAT SHA mismatch: {original_hash}')
    print('Checking full source ISO SHA-256 (may take a few minutes)...')
    iso_hash = digest_file(iso)
    if iso_hash != EXPECTED_ISO_SHA:
        raise ValueError(f'Source ISO SHA mismatch: {iso_hash}')
    print('PREFLIGHT PASSED: trusted ISO and filesystem extent verified.')
    if not args.build:
        print('Add --build to create the test ISO. Nothing was written.')
        return
    print('Copying source ISO into new test ISO...')
    try:
        with iso.open('rb') as src, output.open('xb') as dst:
            for block in iter(lambda: src.read(CHUNK), b''):
                dst.write(block)
        print('Replacing ASSETS.DAT data region...')
        with assets.open('rb') as replacement, output.open('r+b') as dst:
            dst.seek(START_SECTOR * SECTOR)
            for block in iter(lambda: replacement.read(CHUNK), b''):
                dst.write(block)
            remaining = ALLOC - size
            while remaining:
                count = min(CHUNK, remaining)
                dst.write(b'\x00' * count)
                remaining -= count
        if output.stat().st_size != ISO_BYTES:
            raise ValueError('Output ISO size changed')
        print('Verifying patched archive and zero padding...')
        with output.open('rb') as f:
            validate_extent(f)
            actual = digest_extent(f, START_SECTOR * SECTOR, size)
            expected = digest_file(assets)
            if actual != expected:
                raise ValueError('Patched region SHA mismatch')
            f.seek(START_SECTOR * SECTOR + size)
            if f.read(ALLOC - size) != b'\x00' * (ALLOC - size):
                raise ValueError('Padding is not zero-filled')
        print('PASS: Test ISO created; replacement region and allocation verified.')
        print('Test ISO:', output)
        print('This does not establish PCSX2 compatibility; boot test is still required.')
    except Exception:
        print('WARNING: Output may be partial or invalid; do not boot:', output)
        raise


if __name__ == '__main__':
    main()
