"""Dedicated trusted VIP v1.1-A builder with record/capacity/content gates.

Only the original fingerprint is supported as a source. Every byte outside
explicit archive, root/UDF entry and manifest changes is preserved and checked.
"""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import struct
import sys
import zlib
import MC3_ISO_Builder_VIP as engine
from MC3_ISO_Extractor import TRUSTED_VIP_V11A_SHA256, sha256_file
from MC3_ASSETS_Builder_V11A import verify_assets
from archive_build_gate import check_records
from vip_capacity import assess_archives, aligned
from hash_build import get_hash_func, HASHED

INFO = [
    ('TEXTURE.DAT', 9702, 794839040, 344, b'Dave'),
    ('STREAMS.DAT', 397807, 1033197568, 345, b'Hash'),
    ('BANKS.DAT', 902298, 52967424, 346, b'DAVE'),
    ('ASSETS.DAT', 928161, 1808326656, 347, b'Dave')]


def make_rows(replacements):
    rows, position = [], INFO[0][1]
    for name, sector, base_size, fe, signature in INFO:
        path = replacements / name if name in ('STREAMS.DAT', 'ASSETS.DAT') else None
        if path is None and (replacements / name).exists():
            raise ValueError('Only STREAMS and ASSETS replacements are supported')
        payload_size = path.stat().st_size if path else base_size
        size = aligned(payload_size)
        if not 4 <= payload_size <= 0xffffffff or size > 0xffffffff:
            raise ValueError('Archive size cannot be represented')
        row = dict(name=name, base_sector=sector, base_size=base_size, fe_sector=fe,
                   signature=signature, path=path, payload_size=payload_size,
                   size=size, sector=position, end=position + size // 2048 - 1)
        rows.append(row)
        position += size // 2048
    if position > engine.MANIFEST_SECTOR:
        raise ValueError('Archive layout reaches the manifest reservation')
    return rows


def verify_streams(archive, folder, manifest):
    expected, names = {}, set()
    calc = get_hash_func('mclub')
    for path in folder.rglob('*'):
        if not path.is_file():
            continue
        if not path.resolve().is_relative_to(folder.resolve()):
            raise ValueError('STREAMS source escapes project')
        name = path.relative_to(folder).as_posix()
        hashed = name.startswith(HASHED)
        key = int(path.stem, 16) if hashed else calc(name.strip())
        if key in expected:
            raise ValueError('STREAMS hash collision')
        expected[key] = path
        if not hashed:
            names.add(name.strip())
    listed = manifest.read_text(encoding='utf-8').splitlines()
    if len(listed) != len(set(listed)) or set(listed) != names:
        raise ValueError('STREAMS manifest does not match active source names')
    with archive.open('rb') as stream:
        magic, count = struct.unpack('<4sI', stream.read(8))
        if magic != b'Hash' or count != len(expected):
            raise ValueError('STREAMS count differs from active source')
        records = [struct.unpack('<III', stream.read(12)) for _ in range(count)]
        for key, offset, size in records:
            if key not in expected:
                raise ValueError('STREAMS hash not present in active source')
            stream.seek(offset)
            if hashlib.sha256(stream.read(size)).hexdigest() != sha256_file(expected[key]):
                raise ValueError('STREAMS payload mismatch: ' + str(expected[key]))
    print(f'STREAMS contents and manifest verified: {count:,} records', flush=True)


def verify_unchanged(source, output, allowed):
    size = source.stat().st_size
    with source.open('rb') as base, output.open('rb') as out:
        if output.stat().st_size != size:
            raise ValueError('Output image size changed')
        cursor = 0
        for lo, hi in sorted(allowed) + [(size, size)]:
            if not 0 <= cursor <= lo <= hi <= size:
                raise ValueError('Invalid permitted change ranges')
            if engine.hash_region(base, cursor, lo - cursor) != engine.hash_region(out, cursor, lo - cursor):
                raise ValueError('Protected bytes changed outside permitted ranges')
            cursor = hi


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=['vip-v11a'], default='vip-v11a')
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--replacement-dir', type=Path, default=Path('ISO_FILES'))
    parser.add_argument('--manifest', type=Path, default=Path('ISO_FILES/STREAMS.LST'))
    parser.add_argument('--output', type=Path, default=Path('MC3_Modified_VIP.iso'))
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--yes', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    source = args.source.resolve()
    replacements, manifest, output = [p.resolve() if p.is_absolute() else (root / p).resolve()
                                      for p in (args.replacement_dir, args.manifest, args.output)]
    staging = output.with_name(output.name + '.building.tmp')
    if output in {source, manifest, replacements / 'ASSETS.DAT', replacements / 'STREAMS.DAT'}:
        raise ValueError('Output must not overwrite any input')
    if not args.check_only and (output.exists() or staging.exists()):
        raise FileExistsError('Output/staging already exists; refusing overwrite')
    print('Validating original VIP v1.1-A fingerprint...', flush=True)
    if sha256_file(source) != TRUSTED_VIP_V11A_SHA256:
        raise ValueError('Unsupported original source; dedicated v1.1-A fingerprint required')
    with source.open('rb') as inp:
        records, root_size = engine.inspect_base(inp, INFO)
    check_records(replacements, 'vip-v11a')
    result = assess_archives(replacements / 'ASSETS.DAT', replacements / 'STREAMS.DAT', TRUSTED_VIP_V11A_SHA256)
    if not result['passes_size_policy']:
        raise ValueError('Capacity/record policy blocked: ' + result['status'])
    print(f'Capacity PASS: {result["remaining_bytes"]:,} shared bytes remain', flush=True)
    rows = make_rows(replacements)
    package, _ = engine.prepare_manifest(source, rows, manifest)
    verify_assets(source, replacements / 'ASSETS.DAT', root / 'ASSETS')
    verify_streams(replacements / 'STREAMS.DAT', root / 'STREAMS', manifest)
    print('Source, capacity, records, contents and manifest preflight PASS', flush=True)
    if args.check_only:
        return 0
    if not args.yes and input('Create a separate verified ISO? (Y/N): ').strip().lower() != 'y':
        return 2
    if shutil.disk_usage(output.parent).free < source.stat().st_size + engine.CHUNK:
        raise ValueError('Insufficient disk space for new ISO')
    expected_hashes = {}
    print('Copying reference to separate staging image...', flush=True)
    with source.open('rb') as inp, staging.open('xb') as out:
        shutil.copyfileobj(inp, out, engine.CHUNK)
    with source.open('rb') as base, staging.open('r+b') as out:
        for row in rows:
            out.seek(row['sector'] * 2048)
            value = hashlib.sha256()
            with (row['path'] or source).open('rb') as inp:
                if not row['path']:
                    inp.seek(row['base_sector'] * 2048)
                remaining = row['payload_size']
                while remaining:
                    data = inp.read(min(remaining, engine.CHUNK))
                    if not data:
                        raise ValueError('Unexpected archive EOF')
                    out.write(data)
                    value.update(data)
                    remaining -= len(data)
            out.write(b'\0' * (row['size'] - row['payload_size']))
            expected_hashes[row['name']] = value.hexdigest()
        engine.patch_metadata(out, records, rows, root_size)
        out.seek(engine.MANIFEST_SECTOR * 2048)
        out.write(package)
        out.flush()
        os.fsync(out.fileno())
    print('Verifying image metadata, payloads and all protected bytes...', flush=True)
    with staging.open('rb') as out:
        engine.inspect_output(out, rows, root_size)
        for row in rows:
            if engine.hash_region(out, row['sector'] * 2048, row['payload_size']) != expected_hashes[row['name']]:
                raise ValueError('Archive read-back mismatch')
            out.seek(row['sector'] * 2048 + row['payload_size'])
            if any(out.read(row['size'] - row['payload_size'])):
                raise ValueError('Archive padding mismatch')
    engine.verify_manifest(staging, package)
    verify_unchanged(source, staging, [(261 * 2048, 262 * 2048), (344 * 2048, 348 * 2048),
                     (rows[0]['sector'] * 2048, (rows[-1]['end'] + 1) * 2048),
                     (engine.MANIFEST_SECTOR * 2048, engine.MANIFEST_SECTOR * 2048 + engine.MANIFEST_CAPACITY)])
    staging.rename(output)
    print('SUCCESS: v1.1-A ISO verified; second layer and other protected bytes unchanged: ' + str(output), flush=True)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, struct.error, zlib.error) as error:
        print('BUILD BLOCKED: ' + str(error), file=sys.stderr)
        sys.exit(1)
