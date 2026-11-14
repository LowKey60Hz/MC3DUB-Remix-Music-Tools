#!/usr/bin/env python3
"""Experimental Dave archive rebuild v5 (variable-size replacements). No production files are overwritten.

Uses the original archive's complete header/filename table, entry ordering,
compression flags, and original physical payload ordering. This is a research
prototype, NOT an ISO-ready or game-validated builder.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

ORIGINAL_ALLOCATION = 1_808_326_656
ALIGN_SMALL = 32
ALIGN_LARGE = 2048


def align_up(x, a):
    return (x + a - 1) // a * a


def safe_path(root, name):
    if '\\' in name or name.startswith('/') or '..' in name.split('/'):
        raise ValueError('Unsafe archive path: ' + name)
    path = root.joinpath(*name.split('/'))
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Path escapes source folder: ' + name)
    return path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report', type=Path, default=Path('VIP_v11A_Archive_Entry_Report.json'))
    p.add_argument('--archive', type=Path, default=Path('VIP_v11A_Extraction_Test/ASSETS.DAT'))
    p.add_argument('--source', type=Path, default=Path('VIP_v11A_ASSETS_Decompiled'))
    p.add_argument('--output', type=Path, default=Path('VIP_v11A_ASSETS_Experimental.dat'))
    p.add_argument('--build', action='store_true', help='Actually build new archive (default: preflight only)')
    p.add_argument('--verify', action='store_true', help='After build, verify all file records against source files')
    p.add_argument('--optimize-pck', action='store_true', help='Recompress unchanged compressed .pck records only if smaller')
    args = p.parse_args()
    report = json.loads(args.report.read_text(encoding='utf-8'))
    entries = report['all_entries']
    archive = args.archive.resolve()
    source = args.source.resolve()
    output = args.output.resolve()
    if output == archive or output == args.report.resolve():
        raise ValueError('Output must not overwrite the source archive or report')
    if output.exists():
        raise FileExistsError('Refusing to overwrite existing output: ' + str(output))
    if not source.is_dir():
        raise FileNotFoundError(source)
    with archive.open('rb') as f:
        magic, count, entry_block_size, name_block_size = struct.unpack('<4sIII', f.read(16))
        if magic != b'Dave' or count != len(entries):
            raise ValueError('Archive magic/count mismatch with report')
        first_payload = min(e['data_offset'] for e in entries if not e['directory_record'])
        table_end = 0x800 + entry_block_size + name_block_size
        if table_end > first_payload:
            raise ValueError('Original header overlaps file payloads')
        f.seek(0)
        prefix = f.read(first_payload)
    files = [e for e in entries if not e['directory_record']]
    paths = {}
    for e in files:
        if e['name'] not in paths:
            path = safe_path(source, e['name'])
            if not path.is_file():
                raise FileNotFoundError(path)
            paths[e['name']] = path
    print('EXPERIMENTAL VIP v1.1-A Dave builder')
    print('Entries:', len(entries), '| File records:', len(files), '| Unique source files:', len(paths))
    print('Original first payload:', first_payload)
    changed_sizes = sum(paths[e['name']].stat().st_size != e['full_size'] for e in files)
    print('File records with changed uncompressed sizes:', changed_sizes)
    print('Original archive bytes:', archive.stat().st_size)
    print('Output:', output)
    print('Original archive remains unchanged.')
    if not args.build:
        print('PREFLIGHT PASSED. Add --build to create a new archive.')
        return

    # Preserve the original physical order, not the logical filename-table order.
    physical = sorted(files, key=lambda e: e['data_offset'])
    offsets = {}
    sizes = {}
    reused_count = 0
    recompressed_count = 0
    modified_count = 0
    optimized_count = 0
    optimized_payload_bytes = 0
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with archive.open('rb') as original, output.open('xb') as dst:
            dst.write(prefix)
            pos = first_payload
            for n, e in enumerate(physical, 1):
                # Preserve a conservative per-record alignment category. This is
                # an approximation, not proof of the original builder's rules.
                boundary = ALIGN_LARGE if e['data_offset'] % ALIGN_LARGE == 0 else ALIGN_SMALL
                pos = align_up(pos, boundary)
                if pos > 0xFFFFFFFF:
                    raise ValueError('Offset exceeds Dave 32-bit field')
                path = paths[e['name']]
                data = path.read_bytes()
                # Prefer the exact original payload for unchanged files. This
                # retains original compression, including records whose
                # compressed size is only one byte smaller than raw content.
                original.seek(e['data_offset'])
                old_payload = original.read(e['stored_size'])
                if len(old_payload) != e['stored_size']:
                    raise ValueError('Original payload truncated: ' + e['name'])
                try:
                    old_raw = zlib.decompress(old_payload, -15) if e['compressed'] else old_payload
                except zlib.error as exc:
                    raise ValueError('Original payload decompression failed: ' + e['name']) from exc
                if len(old_raw) != e['full_size']:
                    raise ValueError('Original payload size mismatch: ' + e['name'])
                if old_raw == data:
                    stored = old_payload
                    if args.optimize_pck and e['compressed'] and e['name'].lower().endswith('.pck'):
                        obj = zlib.compressobj(9, zlib.DEFLATED, -15)
                        candidate = obj.compress(data) + obj.flush()
                        if len(candidate) < len(old_payload) and len(candidate) < len(data):
                            if zlib.decompress(candidate, -15) != data:
                                raise ValueError('Optimized payload verification failed: ' + e['name'])
                            stored = candidate
                            optimized_count += 1
                            optimized_payload_bytes += len(old_payload) - len(candidate)
                    if stored is old_payload:
                        reused_count += 1
                else:
                    modified_count += 1
                    if e['compressed']:
                        obj = zlib.compressobj(9, zlib.DEFLATED, -15)
                        stored = obj.compress(data) + obj.flush()
                        if zlib.decompress(stored, -15) != data:
                            raise ValueError('Compression round-trip failed: ' + e['name'])
                        # dave.py only decompresses when stored_size < full_size.
                        # Never write compressed bytes with equal/larger sizes.
                        if len(stored) >= len(data):
                            raise ValueError(
                                'Modified file cannot be safely compressed with level 9: '
                                + e['name'] + f' ({len(data)} -> {len(stored)} bytes)'
                            )
                        recompressed_count += 1
                    else:
                        stored = data
                dst.seek(pos)
                dst.write(stored)
                offsets[e['index']] = pos
                sizes[e['index']] = len(stored)
                pos += len(stored)
                if pos > ORIGINAL_ALLOCATION:
                    raise ValueError(
                        f'Archive exceeds original allocation while writing {e["name"]}: '
                        f'{pos:,} > {ORIGINAL_ALLOCATION:,} bytes'
                    )
                if n % 1000 == 0:
                    print(f'Written {n:,}/{len(physical):,} records; {pos:,} bytes')
            # Directory entries have zero sizes. Set their pointers to the next
            # logical file record (or final end if none). Their offset semantics
            # require independent game validation.
            next_offset = pos
            for e in reversed(entries):
                if e['directory_record']:
                    offsets[e['index']] = next_offset
                    sizes[e['index']] = 0
                else:
                    next_offset = offsets[e['index']]
            for e in entries:
                idx = e['index']
                if idx < 0 or idx >= count:
                    raise ValueError('Invalid entry index')
                dst.seek(0x800 + idx * 16 + 4)
                full_size = paths[e['name']].stat().st_size if not e['directory_record'] else e['full_size']
                dst.write(struct.pack('<III', offsets[idx], full_size, sizes[idx]))
            dst.truncate(pos)
        print('Original payloads reused:', reused_count)
        print('Unchanged PCK records optimized:', optimized_count)
        print('Gross PCK payload bytes saved:', optimized_payload_bytes)
        print('Modified file records:', modified_count)
        print('Modified compressed records recompressed:', recompressed_count)
        print('Built archive:', output)
        print('Output bytes:', output.stat().st_size)
        print('Allocation limit:', ORIGINAL_ALLOCATION)
        print('Difference:', output.stat().st_size - ORIGINAL_ALLOCATION)
        print('Fits allocation:', output.stat().st_size <= ORIGINAL_ALLOCATION)
        if output.stat().st_size > ORIGINAL_ALLOCATION:
            raise ValueError('Output exceeds original ASSETS.DAT allocation')
        if args.verify:
            print('Verifying every archive record...')
            with output.open('rb') as f:
                for n, e in enumerate(files, 1):
                    idx = e['index']
                    f.seek(offsets[idx]); payload = f.read(sizes[idx])
                    if len(payload) != sizes[idx]:
                        raise ValueError('Truncated payload: ' + e['name'])
                    raw = zlib.decompress(payload, -15) if e['compressed'] else payload
                    if len(raw) != paths[e['name']].stat().st_size or hashlib.sha256(raw).digest() != hashlib.sha256(paths[e['name']].read_bytes()).digest():
                        raise ValueError('Content mismatch: ' + e['name'])
                    if n % 2000 == 0:
                        print(f'Verified {n:,}/{len(files):,}')
            print('ALL FILE RECORDS VERIFIED')
        print('WARNING: Variable-size archive has not been game-tested. Do not inject into a production ISO.')
    except Exception:
        if output.exists():
            print('Partial output may exist and should be deleted:', output)
        raise


if __name__ == '__main__':
    main()
