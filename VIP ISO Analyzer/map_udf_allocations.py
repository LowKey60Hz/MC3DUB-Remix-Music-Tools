"""Read-only, constrained ECMA-167 UDF allocation traversal for the MC3 reference.

Supports recorded short/long allocation descriptors and embedded directories.
Rejects unfamiliar layouts rather than treating them as free space.
Reference: https://ecma-international.org/publications-and-standards/standards/ecma-167/
"""
import binascii
import json
from pathlib import Path
import struct

S = 2048
u16 = lambda b, p: struct.unpack_from('<H', b, p)[0]
u32 = lambda b, p: struct.unpack_from('<I', b, p)[0]
u64 = lambda b, p: struct.unpack_from('<Q', b, p)[0]


def tag(data, expected, location=None):
    if len(data) < 16 or u16(data, 0) != expected:
        raise ValueError(f'Unexpected UDF descriptor, expected {expected}')
    if sum(data[:4] + data[5:16]) % 256 != data[4]:
        raise ValueError('Descriptor tag checksum mismatch')
    length = u16(data, 10)
    if 16 + length > len(data) or binascii.crc_hqx(data[16:16 + length], 0) != u16(data, 8):
        raise ValueError('Descriptor CRC mismatch')
    if location is not None and u32(data, 12) != location:
        raise ValueError('Descriptor tag location mismatch')


def scan(iso):
    files, directories, visited, warnings = [], [], set(), []
    with iso.open('rb') as stream:
        def read(sector, length=S):
            if sector < 0 or sector * S + length > iso.stat().st_size:
                raise ValueError('Out-of-image extent')
            stream.seek(sector * S)
            result = stream.read(length)
            if len(result) != length:
                raise ValueError('Truncated extent')
            return result
        partition = read(34)
        tag(partition, 5, 34)
        start, blocks = u32(partition, 188), u32(partition, 192)
        lvd = read(35)
        tag(lvd, 6, 35)
        if u32(lvd, 212) != S or u32(lvd, 268) != 1:
            raise ValueError('Unsupported logical block size or partition maps')
        if lvd[440:442] != b'\x01\x06':
            raise ValueError('Unsupported partition map')
        fsd_location = u32(lvd, 252)
        if u16(lvd, 256) != 0:
            raise ValueError('Unsupported file-set partition')
        fsd = read(start + fsd_location)
        tag(fsd, 256, fsd_location)
        root_icb = u32(fsd, 404)
        if u16(fsd, 408) != 0:
            raise ValueError('Unsupported root partition')

        def walk(icb, path, depth=0):
            if depth > 32 or len(visited) > 100000 or icb >= blocks:
                raise ValueError('Traversal bounds exceeded')
            if icb in visited:
                raise ValueError('Repeated ICB outside parent link')
            visited.add(icb)
            fe = read(start + icb)
            tag(fe, 261, icb)
            kind, mode = fe[27], u16(fe, 34) & 7
            length, ea, ad_bytes = u64(fe, 56), u32(fe, 168), u32(fe, 172)
            at = 176 + ea
            if at + ad_bytes > len(fe):
                raise ValueError('Allocation descriptors exceed FE')
            extents = []
            if mode in (0, 1):
                stride = 8 if mode == 0 else 16
                if ad_bytes % stride:
                    raise ValueError('Misaligned allocation descriptors')
                for pos in range(at, at + ad_bytes, stride):
                    size, block = u32(fe, pos), u32(fe, pos + 4)
                    if size >> 30 and mode == 0 and ad_bytes == 8 and size == length and path.lower() == '/assets.dat':
                        warnings.append({'path': path, 'issue': 'Extent length includes ECMA extent-type bits. Diagnostic uses observed full 32-bit length matching information length; not a standard recorded-extent interpretation.', 'raw_extent_length': size})
                    elif size >> 30 or (mode == 1 and u16(fe, pos + 8) != 0):
                        raise ValueError(f'Unsupported extent: {path}, mode={mode}, size={size:#x}, block={block}, partition={u16(fe, pos + 8) if mode == 1 else 0}')
                    if block + (size + S - 1) // S > blocks:
                        raise ValueError('Extent exceeds UDF partition')
                    extents.append({'sector': start + block, 'bytes': size})
                if sum(x['bytes'] for x in extents) < length:
                    raise ValueError('Allocation shorter than file')
            elif mode != 3:
                raise ValueError('Unsupported allocation descriptor type')
            item = {'path': path or '/', 'icb_sector': start + icb,
                    'bytes': length, 'extents': extents, 'allocation_mode': mode}
            if kind != 4:
                files.append(item)
                return
            directories.append(item)
            if length > 16 * 1024 * 1024:
                raise ValueError('Directory exceeds diagnostic limit')
            data = fe[at:at + ad_bytes] if mode == 3 else b''.join(read(x['sector'], x['bytes']) for x in extents)
            data = data[:length]
            pos = 0
            while pos < len(data):
                if not data[pos:].strip(b'\0'):
                    break
                if len(data) - pos < 38:
                    raise ValueError('Truncated file identifier')
                fid = data[pos:]
                name_len, impl_len = fid[19], u16(fid, 36)
                record_len = (38 + impl_len + name_len + 3) & ~3
                if record_len > len(fid):
                    raise ValueError('Truncated file identifier body')
                tag(fid[:record_len], 257)
                flags = fid[18]
                if not flags & (4 | 8):
                    if u16(fid, 28) != 0:
                        raise ValueError('Unsupported child partition')
                    encoded = fid[38 + impl_len:38 + impl_len + name_len]
                    if not encoded or encoded[0] not in (8, 16):
                        raise ValueError('Unsupported UDF name encoding')
                    name = encoded[1:].decode('latin1' if encoded[0] == 8 else 'utf-16-be')
                    if '/' in name or name in ('.', '..'):
                        raise ValueError('Invalid UDF name')
                    walk(u32(fid, 24), path + '/' + name, depth + 1)
                pos += record_len
        walk(root_icb, '')
    region = (1811133 * S, 2074717 * S)
    touching = [x for x in files if any(e['sector'] * S < region[1] and e['sector'] * S + e['bytes'] > region[0] for e in x['extents'])]
    return {'iso': str(iso), 'partition_start': start, 'partition_blocks': blocks,
            'files': files, 'directories': directories, 'warnings': warnings, 'files_touching_post_assets_region': touching,
            'limitation': 'Maps reachable UDF files only; not certification of free space or game relocation support.'}


if __name__ == '__main__':
    root = Path(__file__).resolve().parent
    result = scan(root.parent / "Base ISO's/Midnight Club 3 VIP v1.1-A.iso")
    (root / 'UDF_Allocation_Map.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'files': len(result['files']), 'directories': len(result['directories']), 'warnings': result['warnings'],
                      'post_assets_files': result['files_touching_post_assets_region']}, indent=2))
