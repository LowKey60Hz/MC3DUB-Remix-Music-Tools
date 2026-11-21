"""Reference-preserving VIP v1.1-A ASSETS compiler with transactional output.

Reads original records directly from the trusted ISO. Preserves duplicate names,
entry ordering, compression categories and observed per-record alignments.
"""
import argparse
import hashlib
import io
import os
from pathlib import Path
import struct
import zlib
from MC3_ISO_Extractor import TRUSTED_VIP_V11A_SHA256, sha256_file
from vip_capacity import ASSETS_POLICY_CAP, inspect_archive

START = 928161 * 2048
ALLOCATION = 1808326656
CHARS = "\x00 #$()-./?0123456789_abcdefghijklmnopqrstuvwxyz~\x7f"


def decode_name(blob, offset, previous):
    stream = io.BytesIO(blob)
    stream.seek(offset)
    def group():
        data = stream.read(3)
        if len(data) != 3:
            raise ValueError('Filename exceeds name block')
        value = int.from_bytes(data, 'little')
        return [(value >> (i * 6)) & 63 for i in range(4)]
    bits = group()
    name = ''
    if bits[0] >= 0x38:
        prefix = (bits.pop(1) - 0x20) * 8 + bits.pop(0) - 0x38
        if not 0 <= prefix <= len(previous):
            raise ValueError('Invalid filename prefix')
        name = previous[:prefix]
    for _ in range(65536):
        if not bits:
            bits = group()
        value = bits.pop(0)
        if value == 0:
            return name
        if value >= len(CHARS):
            raise ValueError('Invalid filename character')
        name += CHARS[value]
    raise ValueError('Filename too long')


def reference_entries(stream):
    stream.seek(START)
    magic, count, table_bytes, names_bytes = struct.unpack('<4sIII', stream.read(16))
    if magic != b'Dave' or not 0 < count <= 1000000 or table_bytes < count * 16:
        raise ValueError('Unsupported reference ASSETS header')
    if 0x800 + table_bytes + names_bytes > ALLOCATION:
        raise ValueError('Reference tables exceed allocation')
    stream.seek(START + 0x800)
    table = stream.read(count * 16)
    stream.seek(START + 0x800 + table_bytes)
    blob = stream.read(names_bytes)
    if len(table) != count * 16 or len(blob) != names_bytes:
        raise ValueError('Truncated reference tables')
    entries, previous = [], ''
    for index in range(count):
        name_offset, offset, full, stored = struct.unpack_from('<IIII', table, index * 16)
        if name_offset >= names_bytes:
            raise ValueError('Reference name outside name block')
        name = decode_name(blob, name_offset, previous)
        previous = name
        if not name or name.startswith('/') or '\\' in name or any(p in ('.', '..') for p in name.split('/')):
            raise ValueError('Unsafe reference name')
        directory = name.endswith('/')
        if offset + stored > ALLOCATION or stored > full or (directory and (stored or full)):
            raise ValueError('Invalid reference payload')
        entries.append(dict(index=index, name=name, offset=offset, full=full, stored=stored, directory=directory))
    first = min(e['offset'] for e in entries if not e['directory'])
    if first < 0x800 + table_bytes + names_bytes:
        raise ValueError('Payload overlaps tables')
    stream.seek(START)
    return entries, stream.read(first)


def compile_assets(iso, source, output, replace=False):
    iso, source, output = iso.resolve(), source.resolve(), output.resolve()
    pending = output.with_name(output.name + '.compiling.tmp')
    if output == iso or output.is_relative_to(source) or pending.exists() or (output.exists() and not replace):
        raise ValueError('Unsafe output or existing compilation output')
    print('Checking trusted v1.1-A source...', flush=True)
    if sha256_file(iso) != TRUSTED_VIP_V11A_SHA256:
        raise ValueError('Unsupported source ISO; v1.1-A fingerprint required')
    with iso.open('rb') as original:
        entries, prefix = reference_entries(original)
        paths = {}
        for entry in entries:
            if entry['directory'] or entry['name'] in paths:
                continue
            path = source.joinpath(*entry['name'].split('/')).resolve()
            if not path.is_relative_to(source) or not path.is_file():
                raise ValueError('Missing/unsafe source file: ' + entry['name'])
            paths[entry['name']] = path
        actual = {p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()}
        if actual != set(paths):
            raise ValueError('Source has added/missing ASSETS paths; this compiler preserves the trusted filename table. Extra: ' + ', '.join(sorted(actual - set(paths))[:5]))
        files = sorted((e for e in entries if not e['directory']), key=lambda e: e['offset'])
        offsets, sizes, full_sizes = {}, {}, {}
        with pending.open('xb') as out:
            out.write(prefix)
            position = len(prefix)
            for n, entry in enumerate(files, 1):
                alignment = 2048 if entry['offset'] % 2048 == 0 else 32
                position = (position + alignment - 1) // alignment * alignment
                data = paths[entry['name']].read_bytes()
                if len(data) >= 2**31:
                    raise ValueError('Decoded resource reaches unverified 2 GiB boundary')
                original.seek(START + entry['offset'])
                old = original.read(entry['stored'])
                old_raw = zlib.decompress(old, -15) if entry['stored'] < entry['full'] else old
                if len(old) != entry['stored'] or len(old_raw) != entry['full']:
                    raise ValueError('Original payload mismatch')
                compressed = entry['stored'] < entry['full']
                if data == old_raw:
                    payload = old
                    if compressed and entry['name'].lower().endswith('.pck'):
                        compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
                        candidate = compressor.compress(data) + compressor.flush()
                        if len(candidate) < len(payload) and len(candidate) < len(data):
                            payload = candidate
                elif compressed:
                    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
                    payload = compressor.compress(data) + compressor.flush()
                    if len(payload) >= len(data):
                        raise ValueError('Replacement cannot retain compressed category: ' + entry['name'])
                else:
                    payload = data
                if (zlib.decompress(payload, -15) if compressed else payload) != data:
                    raise ValueError('Payload round-trip mismatch')
                if position + len(payload) > ASSETS_POLICY_CAP:
                    raise ValueError('ASSETS live data exceeds conservative low-offset ceiling; reduce content before building')
                out.seek(position)
                out.write(payload)
                index = entry['index']
                offsets[index], sizes[index], full_sizes[index] = position, len(payload), len(data)
                position += len(payload)
                if n % 2000 == 0:
                    print(f'Compiled {n:,}/{len(files):,}; {position:,} bytes', flush=True)
            next_offset = position
            for entry in reversed(entries):
                index = entry['index']
                if entry['directory']:
                    offsets[index], sizes[index], full_sizes[index] = next_offset, 0, 0
                else:
                    next_offset = offsets[index]
            for entry in entries:
                index = entry['index']
                out.seek(0x800 + index * 16 + 4)
                out.write(struct.pack('<III', offsets[index], full_sizes[index], sizes[index]))
            out.truncate(position)
    print('Independently verifying compiled ASSETS records...', flush=True)
    with pending.open('rb') as check:
        for n, entry in enumerate(files, 1):
            check.seek(0x800 + entry['index'] * 16 + 4)
            offset, full, stored = struct.unpack('<III', check.read(12))
            check.seek(offset)
            payload = check.read(stored)
            data = zlib.decompress(payload, -15) if stored < full else payload
            if len(data) != full or hashlib.sha256(data).digest() != hashlib.sha256(paths[entry['name']].read_bytes()).digest():
                raise ValueError('Compiled record/source mismatch: ' + entry['name'])
            if n % 2000 == 0:
                print(f'Verified {n:,}/{len(files):,}', flush=True)
    if not inspect_archive(pending, 'ASSETS')['passes_record_policy']:
        raise ValueError('Compiled ASSETS failed record policy')
    if not replace and output.exists():
        raise FileExistsError(output)
    os.replace(pending, output)
    print(f'ASSETS compile/verification PASS: {output}; {output.stat().st_size:,} bytes', flush=True)


def verify_assets(iso, archive, source):
    """Verify filename identities and every compiled file record against active files."""
    source = source.resolve()
    with iso.open('rb') as original:
        entries, prefix = reference_entries(original)
    expected = {e['name'] for e in entries if not e['directory']}
    actual = {p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()}
    if expected != actual:
        raise ValueError('Active ASSETS paths differ from trusted filename table')
    with archive.open('rb') as check:
        compiled_prefix = check.read(len(prefix))
        name_start = 0x800 + struct.unpack_from('<I', prefix, 8)[0]
        if compiled_prefix[:0x800] != prefix[:0x800] or compiled_prefix[name_start:] != prefix[name_start:]:
            raise ValueError('ASSETS header/filename block changed unexpectedly')
        for n, entry in enumerate(entries):
            at = 0x800 + entry['index'] * 16
            if compiled_prefix[at:at + 4] != prefix[at:at + 4]:
                raise ValueError('ASSETS filename reference changed')
            offset, full, stored = struct.unpack_from('<III', compiled_prefix, at + 4)
            if entry['directory']:
                if full or stored:
                    raise ValueError('ASSETS directory contains data')
                continue
            if (stored < full) != (entry['stored'] < entry['full']):
                raise ValueError('ASSETS compression category changed: ' + entry['name'])
            alignment = 2048 if entry['offset'] % 2048 == 0 else 32
            if offset % alignment:
                raise ValueError('ASSETS record lost required reference alignment: ' + entry['name'])
            path = source.joinpath(*entry['name'].split('/')).resolve()
            if not path.is_relative_to(source):
                raise ValueError('ASSETS source path escapes project')
            check.seek(offset)
            payload = check.read(stored)
            data = zlib.decompress(payload, -15) if stored < full else payload
            if len(data) != full or hashlib.sha256(data).digest() != hashlib.sha256(path.read_bytes()).digest():
                raise ValueError('ASSETS source/content mismatch: ' + entry['name'])
            if n and n % 4000 == 0:
                print(f'Checked ASSETS record {n:,}/{len(entries):,}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iso', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--replace', action='store_true', help='Replace compiled output only after verification')
    args = parser.parse_args()
    try:
        compile_assets(args.iso, args.source, args.output, args.replace)
    except (ValueError, OSError, zlib.error) as error:
        parser.exit(1, str(error) + '\nCompilation output may remain for inspection.\n')
