#!/usr/bin/env python3
r"""Read-only check of one RSM entry in Midnight Club 3 STREAMS.DAT.

Place this file in the project root (beside ISO_FILES and STREAMS), then run:
    py check_streams_song.py
Or pass paths:
    py check_streams_song.py "ISO_FILES\STREAMS.DAT" "STREAMS\Music\Dancehall\KnowGoodFt.MacDre-FeelinMyself(KnowGoodFlip).rsm"
"""
import argparse
import hashlib
from pathlib import Path
import struct
import sys

DEFAULT_NAME = 'KnowGoodFt.MacDre-FeelinMyself(KnowGoodFlip).rsm'
RELATIVE_NAME = 'Music/Dancehall/' + DEFAULT_NAME


def mclub_hash(name):
    value = 0
    for index, char in enumerate(name.upper().replace('\\', '/').encode('ascii'), 1):
        value = (((value << 1) | (value >> 31)) + char * index) & 0xffffffff
    return value


def digest_stream(handle, size):
    hasher = hashlib.sha256()
    remaining = size
    while remaining:
        block = handle.read(min(1024 * 1024, remaining))
        if not block:
            raise EOFError('Unexpected end of file while hashing')
        hasher.update(block)
        remaining -= len(block)
    return hasher.hexdigest()


def main():
    parser = argparse.ArgumentParser(description='Read-only RSM archive verification')
    parser.add_argument('archive', nargs='?', help='Compiled STREAMS.DAT (default: ISO_FILES/STREAMS.DAT)')
    parser.add_argument('rsm', nargs='?', help='Original extracted RSM (default: STREAMS/Music/Dancehall/<song>.rsm)')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    archive = Path(args.archive).resolve() if args.archive else root / 'ISO_FILES' / 'STREAMS.DAT'
    rsm = Path(args.rsm).resolve() if args.rsm else root / 'STREAMS' / 'Music' / 'Dancehall' / DEFAULT_NAME

    print('=== MC3 STREAMS.DAT SONG CHECK (READ ONLY) ===')
    print('Archive:', archive)
    print('Source RSM:', rsm)
    if not archive.is_file() or not rsm.is_file():
        print('[ERROR] Missing file(s). Check paths or supply both paths as arguments.')
        return 2

    # The archive builder hashes paths relative to STREAMS, including the extension.
    expected_hash = mclub_hash(RELATIVE_NAME)
    print('Archive-relative filename:', RELATIVE_NAME)
    print('Expected MClub hash: 0x%08X' % expected_hash)
    print('RSM source size:', rsm.stat().st_size, 'bytes')

    with archive.open('rb') as src:
        header = src.read(8)
        if len(header) != 8 or header[:4] not in (b'Hash', b'hsaH'):
            print('[ERROR] Invalid Hash archive signature.')
            return 2
        endian = '<' if header[:4] == b'Hash' else '>'
        count = struct.unpack(endian + 'I', header[4:])[0]
        archive_size = archive.stat().st_size
        if count > (archive_size - 8) // 12:
            print('[ERROR] Archive index count exceeds file length.')
            return 2
        print('Archive entries:', count)
        found = None
        for _ in range(count):
            record = src.read(12)
            hash_value, offset, size = struct.unpack(endian + 'III', record)
            if hash_value == expected_hash:
                found = (offset, size)
        if found is None:
            print('[NOT FOUND] Expected hash is absent from the archive index.')
            print('Check the relative folder/filename and confirm STREAMS.DAT was rebuilt.')
            return 1
        offset, size = found
        print('[FOUND] Hash entry: offset=%d (0x%X), size=%d bytes' % (offset, offset, size))
        if offset + size > archive_size:
            print('[MISMATCH] Entry extends past the archive end.')
            return 1
        source_size = rsm.stat().st_size
        if size != source_size:
            print('[MISMATCH] Archived size differs from original RSM size.')
            return 1
        src.seek(offset)
        archive_sha = digest_stream(src, size)
    with rsm.open('rb') as original:
        source_sha = digest_stream(original, source_size)
    print('Archive SHA-256:', archive_sha)
    print('Source  SHA-256:', source_sha)
    if archive_sha == source_sha:
        print('[MATCH] Archived audio is byte-for-byte identical to the source RSM.')
        print('This verifies archive inclusion, not whether the game can decode or play it.')
        return 0
    print('[MISMATCH] Archived audio bytes differ from the source RSM.')
    return 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, EOFError, UnicodeError) as exc:
        print('[ERROR]', exc)
        sys.exit(2)
