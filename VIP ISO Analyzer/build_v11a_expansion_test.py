"""Isolated v1.1-A expansion experiment. Default is preflight; --build creates a new test ISO.

Overwrites carried-over data with unresolved runtime relevance in the NEW image.
Never use its output as a known-good production image without game testing.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import struct

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent / 'UI Custom Gameplay Music Tools'
CHUNK = 8 * 1024 * 1024


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(CHUNK), b''):
            value.update(data)
    return value.hexdigest()


def verify_unchanged(base, output, size, allowed, hash_region):
    cursor = 0
    for lo, hi in sorted(allowed) + [(size, size)]:
        if not 0 <= cursor <= lo <= hi <= size:
            raise ValueError('Invalid allowed change ranges')
        if hash_region(base, cursor, lo - cursor) != hash_region(output, cursor, lo - cursor):
            raise ValueError('Bytes outside authorized change ranges differ')
        cursor = hi
    if output.seek(0, 2) != size:
        raise ValueError('Image size changed')


def check_streams(path, folder, hashes):
    expected = {}
    for source in folder.rglob('*'):
        if not source.is_file():
            continue
        name = source.relative_to(folder).as_posix()
        key = int(source.stem, 16) if name.startswith(hashes.HASHED) else hashes.get_hash_func('mclub')(name.strip())
        if key in expected:
            raise ValueError('STREAMS hash collision')
        expected[key] = source
    seen = set()
    with path.open('rb') as stream:
        magic, count = struct.unpack('<4sI', stream.read(8))
        if magic != b'Hash' or count != len(expected):
            raise ValueError('STREAMS header/source count mismatch')
        records = [struct.unpack('<III', stream.read(12)) for _ in range(count)]
        for key, offset, size in records:
            if key not in expected or key in seen or offset < 8 + count * 12 or offset + size > path.stat().st_size:
                raise ValueError('Invalid STREAMS record')
            seen.add(key)
            stream.seek(offset)
            if hashlib.sha256(stream.read(size)).hexdigest() != digest(expected[key]):
                raise ValueError('STREAMS payload mismatch: ' + str(expected[key]))
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', action='store_true')
    args = parser.parse_args()
    source = ROOT.parent / "Base ISO's/Midnight Club 3 VIP v1.1-A.iso"
    output = ROOT / 'MC3_VIP_v11A_Expansion_Experimental.iso'
    partial = output.with_suffix('.iso.partial')
    if output.exists() or partial.exists():
        raise FileExistsError('Experimental output/partial already exists; refusing overwrite')
    tools = module('vip_tools', PROJECT / 'supporting_tools/MC3_ISO_Builder_VIP.py')
    trusted = module('trusted_v11a', ROOT / 'MC3_VIP_v11A_ISO_Test_Patcher.py')
    assets = ROOT / 'VIP_v11A_ASSETS_v5_Test.dat'
    streams = ROOT / 'VIP_v11A_STREAMS_Test.dat'
    print('Checking trusted reference ISO SHA-256...', flush=True)
    if digest(source) != trusted.EXPECTED_ISO_SHA:
        raise ValueError('Reference ISO SHA-256 mismatch')
    info = [(name, sector, size, fe, signature) for name, sector, size, fe, signature in tools.PROFILES['VIP Expansion']['archives']]
    info[-1] = ('ASSETS.DAT', 928161, 1808326656, 347, b'Dave')
    with source.open('rb') as stream:
        records, root_size = tools.inspect_base(stream, info)
    print('Verifying experimental STREAMS against active files...', flush=True)
    count = check_streams(streams, PROJECT / 'STREAMS', module('hash_tools', PROJECT / 'supporting_tools/hash_build.py'))
    print('Verifying experimental ASSETS against active files...', flush=True)
    validation = module('v5_validate', ROOT / 'validate_v5_snapshot.py').validate(ROOT, PROJECT / 'ASSETS')
    if not validation['passed']:
        raise ValueError('ASSETS independent validation failed')
    position, rows = info[0][1], []
    for name, sector, size, fe, signature in info:
        replacement = {'STREAMS.DAT': streams, 'ASSETS.DAT': assets}.get(name)
        payload_size = replacement.stat().st_size if replacement else size
        allocated = (payload_size + 2047) // 2048 * 2048
        rows.append(dict(name=name, base_sector=sector, base_size=size, fe_sector=fe,
                         signature=signature, path=replacement, payload_size=payload_size,
                         size=allocated, sector=position, end=position + allocated // 2048 - 1))
        position += allocated // 2048
    # Narrow this experiment to the independently inspected proposal. Do not
    # silently accept future growth into a different unidentified region.
    if position != 1836375 or streams.stat().st_size != 1087309824 or assets.stat().st_size != 1805909737:
        raise ValueError('Inputs differ from inspected proposal; regenerate/review plan first')
    names = [line.strip() for line in (ROOT / 'VIP_v11A_STREAMS_Test.lst').read_text().splitlines()]
    if len(names) != count or len(set(names)) != count:
        raise ValueError('STREAMS manifest count/uniqueness mismatch')
    expected_names = {p.relative_to(PROJECT / 'STREAMS').as_posix() for p in (PROJECT / 'STREAMS').rglob('*') if p.is_file()}
    if set(names) != expected_names:
        raise ValueError('STREAMS manifest does not describe active source files')
    package, _ = tools.prepare_manifest(source, rows, ROOT / 'VIP_v11A_STREAMS_Test.lst')
    print('PREFLIGHT PASSED. Runtime compatibility remains unverified.', flush=True)
    report = {'preflight_passed': True, 'streams_records': count, 'assets_records': validation['verified_records'],
              'output': str(output), 'built': False, 'warning': 'Expansion overwrites suspected leftover data; PCSX2 testing required.'}
    if args.build:
        if shutil.disk_usage(ROOT).free < source.stat().st_size + CHUNK:
            raise ValueError('Insufficient free space for isolated test ISO')
        print('Creating separate experimental image...', flush=True)
        with source.open('rb') as inp, partial.open('xb') as out:
            shutil.copyfileobj(inp, out, CHUNK)
        with source.open('rb') as base, partial.open('r+b') as out:
            for row in rows:
                out.seek(row['sector'] * 2048)
                with (row['path'] or source).open('rb') as inp:
                    if not row['path']:
                        inp.seek(row['base_sector'] * 2048)
                    tools.copy_archive(inp, out, row['payload_size'])
                out.write(b'\0' * (row['size'] - row['payload_size']))
            tools.patch_metadata(out, records, rows, root_size)
            out.seek(tools.MANIFEST_SECTOR * 2048)
            out.write(package)
        # Check payloads, padding, metadata, and ALL bytes outside allowed ranges.
        allowed = [(261 * 2048, (261 + 1) * 2048), (344 * 2048, 348 * 2048),
                   (rows[0]['sector'] * 2048, position * 2048),
                   (tools.MANIFEST_SECTOR * 2048, tools.MANIFEST_SECTOR * 2048 + tools.MANIFEST_CAPACITY)]
        with source.open('rb') as base, partial.open('rb') as out:
            tools.inspect_output(out, rows, root_size)
            for row in rows:
                if row['path']:
                    expected = digest(row['path'])
                else:
                    expected = tools.hash_region(base, row['base_sector'] * 2048, row['payload_size'])
                if tools.hash_region(out, row['sector'] * 2048, row['payload_size']) != expected:
                    raise ValueError('Archive read-back mismatch')
                out.seek(row['sector'] * 2048 + row['payload_size'])
                if any(out.read(row['size'] - row['payload_size'])):
                    raise ValueError('Nonzero archive padding')
            verify_unchanged(base, out, source.stat().st_size, allowed, tools.hash_region)
        tools.verify_manifest(partial, package)
        partial.rename(output)
        report['built'] = True
        report['output_sha256'] = digest(output)
        print('Experimental ISO read-back passed; game testing required.', flush=True)
    (ROOT / 'Expansion_Builder_Result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
