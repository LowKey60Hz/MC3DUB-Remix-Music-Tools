"""Verify every byte outside explicitly permitted ISO changes."""
import hashlib


def region_digest(stream, start, length):
    value = hashlib.sha256()
    stream.seek(start)
    while length:
        data = stream.read(min(length, 8 * 1024 * 1024))
        if not data:
            raise ValueError('Truncated ISO during protected-byte verification')
        value.update(data)
        length -= len(data)
    return value.digest()


def verify_protected_bytes(source, output, allowed):
    size = source.stat().st_size
    if output.stat().st_size != size:
        raise ValueError('Output ISO size changed')
    cursor = 0
    with source.open('rb') as original, output.open('rb') as candidate:
        for lo, hi in sorted(allowed) + [(size, size)]:
            if not 0 <= cursor <= lo <= hi <= size:
                raise ValueError('Invalid ISO change-range plan')
            if region_digest(original, cursor, lo - cursor) != region_digest(candidate, cursor, lo - cursor):
                raise ValueError(f'Protected ISO bytes changed in [{cursor}, {lo})')
            cursor = hi
