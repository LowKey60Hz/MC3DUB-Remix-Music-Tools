#!/usr/bin/env python3
"""Read-only comparison of original MC3 Hash STREAMS.DAT against current STREAMS files.
Never extracts or modifies files. Uses original archive index and the original LST.
"""
import argparse
from pathlib import Path
import struct
from collections import Counter


def mclub_hash(name):
    result = 0
    for i, c in enumerate(name.upper().replace('\\', '/').encode('ascii'), 1):
        result = (((result << 1) | (result >> 31)) + c * i) & 0xffffffff
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--folder', type=Path, required=True)
    args = p.parse_args()
    archive, manifest, folder = args.archive, args.manifest, args.folder
    for path in (archive, manifest):
        if not path.is_file():
            p.error(f'Missing file: {path}')
    if not folder.is_dir():
        p.error(f'Missing folder: {folder}')

    with archive.open('rb') as f:
        if f.read(4) != b'Hash':
            p.error('Expected little-endian Hash archive')
        count = struct.unpack('<I', f.read(4))[0]
        if count > 1000000 or 8 + 12 * count > archive.stat().st_size:
            p.error('Invalid archive index')
        entries = {}
        for _ in range(count):
            h, offset, size = struct.unpack('<III', f.read(12))
            if h in entries or offset + size > archive.stat().st_size:
                p.error('Duplicate hash or invalid payload extent')
            entries[h] = (offset, size)

    names = {}
    for raw in manifest.read_text(encoding='utf-8-sig').splitlines():
        name = raw.strip().replace('\\', '/')
        if not name:
            continue
        for candidate in (name, name + '.rsm', name + '.stm'):
            h = mclub_hash(candidate)
            if h in entries:
                names.setdefault(h, candidate)
                break

    files = {}
    for path in folder.rglob('*'):
        if not path.is_file():
            continue
        relative = path.relative_to(folder).as_posix()
        if relative.startswith('__hashed/'):
            try:
                h = int(path.stem, 16)
            except ValueError:
                h = mclub_hash(relative)
        else:
            try:
                h = mclub_hash(relative)
            except UnicodeEncodeError:
                print(f'WARNING: Non-ASCII filename ignored: {relative}')
                continue
        if h in files:
            p.error(f'Hash collision among source files: {relative} and {files[h][0]}')
        files[h] = (relative, path.stat().st_size)

    changed = []
    same = 0
    missing = []
    added = []
    original_payload = sum(size for _, size in entries.values())
    for h, (offset, size) in entries.items():
        if h not in files:
            missing.append((names.get(h, f'#{h:08X}'), size))
        else:
            name, current = files[h]
            if current != size:
                changed.append((name, size, current, current - size))
            else:
                same += 1
    for h, (name, size) in files.items():
        if h not in entries:
            added.append((name, size))

    print('READ-ONLY ORIGINAL STREAMS COMPARISON')
    print(f'Original archive entries: {len(entries):,}')
    print(f'Original manifest hashes matched: {len(names):,}')
    print(f'Current files: {len(files):,}')
    print(f'Original payload bytes: {original_payload:,}')
    print(f'Current payload bytes: {sum(s for _, s in files.values()):,}')
    print(f'Same-size matching files: {same:,} (contents NOT compared)')
    print(f'Changed-size matching files: {len(changed):,}')
    print(f'Files absent from current folder: {len(missing):,}')
    print(f'Files newly added to current folder: {len(added):,}')
    print(f'Net payload change: {sum(s for _, s in files.values()) - original_payload:+,} bytes')
    print(f'Original archive padding/index: {archive.stat().st_size - original_payload:,} bytes')
    print('\nTOP 25 SIZE CHANGES (bytes):')
    for name, before, after, delta in sorted(changed, key=lambda x: abs(x[3]), reverse=True)[:25]:
        print(f'  {delta:+12,}  {before:>12,} -> {after:>12,}  {name}')
    print('\nTOP 15 ADDED FILES:')
    for name, size in sorted(added, key=lambda x: x[1], reverse=True)[:15]:
        print(f'  {size:>12,}  {name}')
    print('\nTOP 15 MISSING ORIGINAL FILES:')
    for name, size in sorted(missing, key=lambda x: x[1], reverse=True)[:15]:
        print(f'  {size:>12,}  {name}')
    print('\nNo files were written or changed.')

if __name__ == '__main__':
    main()
