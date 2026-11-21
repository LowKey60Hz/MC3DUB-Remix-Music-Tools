"""Read-only projection of processed workspace archives; never builds game files.

Matches the active builders' packing rules. Only the optional compression-size
cache is written. Build-time source/index/payload validation stays authoritative.
"""
import argparse
import glob
import json
import os
from pathlib import Path
import tempfile
import zlib

import dave
from hash_build import get_hash_func, HASHED
from vip_capacity import CAPACITY_PROFILES, ASSETS_POLICY_CAP, TEXTURE_BYTES, BANKS_BYTES, aligned
import MC3_ASSETS_Builder_V11A as v11

VERSION = 1


def fingerprint(path):
    stat = path.stat()
    return [stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino]


def inventory(folder, *, directories=False, hidden=True):
    folder = folder.resolve()
    if not folder.is_dir():
        raise ValueError(f'Missing extracted {folder.name} folder')
    result = []
    pattern = os.path.join(glob.escape(str(folder)), '**', '*')
    for value in glob.iglob(pattern, recursive=True, include_hidden=hidden):
        path = Path(value)
        if not path.resolve().is_relative_to(folder):
            raise ValueError('Workspace contains an external file link')
        is_dir = path.is_dir()
        if is_dir and not directories:
            continue
        result.append((path.relative_to(folder).as_posix() + ('/' if is_dir else ''), path,
                       None if is_dir else fingerprint(path)))
    return result


class Sizes:
    def __init__(self, previous):
        self.previous = previous
        self.rows = {}
        self.compressed_files = 0

    def stored(self, path, stamp, key, calculate):
        old = self.previous.get(key)
        if isinstance(old, dict) and old.get('stamp') == stamp and type(old.get('size')) is int and old['size'] >= 0:
            size = old['size']
        else:
            size = calculate()
            if fingerprint(path) != stamp:
                raise ValueError('Workspace changed during estimation; try again')
            self.compressed_files += 1
        self.rows[key] = {'stamp': stamp, 'size': size}
        return size


def compressed_size(path):
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    count = 0
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            count += len(compressor.compress(block))
    return count + len(compressor.flush())


def strict_align(value, amount):
    # dave.py advances even if the value is already aligned.
    return (value // amount + 1) * amount


def project_dave(rows, sizes):
    entries = sorted(rows, key=lambda row: [dave.CHARS.index(c) for c in row[0].lower()])
    if not entries:
        raise ValueError('ASSETS has no entries')
    previous = ''; dedup = 0; names_bytes = 0
    for name, _, _ in entries:
        if len(name) >= 256 or any(c not in dave.CHARS for c in name.lower()):
            raise ValueError('Unsupported ASSETS filename: ' + name)
        name = name.lower()
        if previous == name:
            continue
        suffix = name; prefix = 0
        if dedup:
            for index, (a, b) in enumerate(zip(previous, name), 1):
                if a != b:
                    index -= 1
                    break
            else:
                index = min(len(previous), len(name))
            if index:
                prefix = 2; suffix = name[index:]
            else:
                dedup = 0
        names_bytes += ((len(suffix) + 1 + prefix) * 3 + 3) // 4
        previous = name
        dedup = (dedup + 1) & 31
    position = 2048 + strict_align(len(entries) * 16, 2048) + strict_align(names_bytes, 2048)
    last = None; max_end = 0; max_full = 0
    for name, path, stamp in entries:
        if stamp is None:
            last = (position, 0)
            continue
        full = stamp[0]
        blocked = name.lower().endswith(dave.COMP_EXT_BLOCKLIST)
        can_compress = not blocked or ('/' in name and not name.lower().startswith(dave.COMP_DIR_BLOCKLIST))
        stored = sizes.stored(path, stamp, name, lambda: min(full, compressed_size(path))) if can_compress else full
        if last and 0 < last[1] < 2048:
            prev_offset, prev_stored = last
            stride = strict_align(prev_stored, 32)
            if (prev_offset & 2047) + stride + stored < 2048:
                position = prev_offset + stride
        last = (position, stored)
        if stored:
            max_end = max(max_end, position + stored)
        max_full = max(max_full, full)
        position = strict_align(position + stored, 2048)
    return {'bytes': position, 'max_live_end': max_end, 'max_decoded': max_full, 'records': len(entries)}


def project_v11(rows, sizes, iso):
    paths = {name: (path, stamp) for name, path, stamp in rows}
    source_stamp = fingerprint(iso)
    with iso.open('rb') as original:
        entries, prefix = v11.reference_entries(original)
        if set(paths) != {e['name'] for e in entries if not e['directory']}:
            raise ValueError('VIP v1.1-A ASSETS paths differ from the source layout')
        position = len(prefix); max_end = 0; max_full = 0
        for entry in sorted((e for e in entries if not e['directory']), key=lambda e: e['offset']):
            path, stamp = paths[entry['name']]
            alignment = 2048 if entry['offset'] % 2048 == 0 else 32
            position = (position + alignment - 1) // alignment * alignment
            def calculate():
                original.seek(v11.START + entry['offset'])
                old = original.read(entry['stored'])
                compressed = entry['stored'] < entry['full']
                decoded = zlib.decompress(old, -15) if compressed else old
                if len(old) != entry['stored'] or len(decoded) != entry['full']:
                    raise ValueError('Invalid source ASSETS payload')
                data = path.read_bytes()
                if data == decoded:
                    return min(len(old), compressed_size(path)) if compressed and entry['name'].lower().endswith('.pck') else len(old)
                if not compressed:
                    return len(data)
                count = compressed_size(path)
                if count >= len(data):
                    raise ValueError('Replacement cannot retain ASSETS compression: ' + entry['name'])
                return count
            stored = sizes.stored(path, stamp, str(entry['index']), calculate)
            position += stored
            if stored:
                max_end = max(max_end, position)
            max_full = max(max_full, stamp[0])
    if fingerprint(iso) != source_stamp:
        raise ValueError('Source ISO changed during estimation')
    return {'bytes': position, 'max_live_end': max_end, 'max_decoded': max_full, 'records': len(entries)}


def project_streams(rows):
    get_hash = get_hash_func('MClub'); keys = {}; files = []
    for name, path, stamp in rows:
        native = name.replace('/', os.sep)
        key = int(Path(name).stem, 16) if native.startswith(HASHED) else get_hash(name.strip())
        if key in keys or not 0 <= key <= 0xffffffff:
            raise ValueError('Invalid or duplicate STREAMS filename hash')
        keys[key] = name; files.append((name, path, stamp))
    if not files:
        raise ValueError('STREAMS has no files')
    position = physical_end = 8 + len(files) * 12
    max_end = 0
    for _, _, stamp in sorted(files, key=lambda row: row[0].upper().replace('\\', '/')):
        position = aligned(position)
        if stamp[0]:
            physical_end = max(physical_end, position + stamp[0])
            max_end = max(max_end, position + stamp[0])
        position += stamp[0]
    if position % 2048:
        physical_end = max(physical_end, aligned(position))
    return {'bytes': physical_end, 'max_live_end': max_end, 'records': len(files)}


def layout_profile(root):
    workspace = root/'ISO_FILES'
    profile = (workspace/'MC3_PROFILE.txt').read_text(encoding='utf-8').strip().lower()
    source_class = (workspace/'MC3_SOURCE_CLASS.txt').read_text(encoding='utf-8').strip()
    if profile == 'vip' and source_class == 'VERIFIED_VIP_V11A_REFERENCE':
        return 'vip-v11a'
    if profile == 'vip':
        return 'vip-expanded' if source_class == 'VERIFIED_VIP_REFERENCE' else 'vip'
    if profile == 'retail':
        return 'retail-expanded' if source_class == 'VERIFIED_RETAIL_REFERENCE' else 'retail'
    raise ValueError('Unknown workspace profile')


def estimate(root, cache_path=None):
    root = Path(root).resolve(); profile = layout_profile(root)
    geometry = CAPACITY_PROFILES[profile]
    iso = None
    if profile == 'vip-v11a':
        iso = Path((root/'ISO_FILES/MC3_SOURCE_ISO.txt').read_text(encoding='utf-8').strip()).resolve()
    cache_key = [VERSION, str(root), profile, str(iso), fingerprint(iso) if iso else None]
    previous = {}
    if cache_path and Path(cache_path).is_file():
        try:
            saved = json.loads(Path(cache_path).read_text(encoding='utf-8'))
            if saved.get('key') == cache_key and isinstance(saved.get('rows'), dict):
                previous = saved['rows']
        except (OSError, ValueError, AttributeError):
            pass
    sizes = Sizes(previous)
    assets = inventory(root/'ASSETS', directories=profile in ('vip', 'vip-expanded'))
    streams = inventory(root/'STREAMS', hidden=False)
    a = project_v11(assets, sizes, iso) if profile == 'vip-v11a' else project_dave(assets, sizes)
    s = project_streams(streams)
    if iso and fingerprint(iso) != cache_key[-1]:
        raise ValueError('Source ISO changed during estimation')
    # Do not publish a projection assembled from different workspace states.
    if assets != inventory(root/'ASSETS', directories=profile in ('vip', 'vip-expanded')) or streams != inventory(root/'STREAMS', hidden=False):
        raise ValueError('Workspace changed during estimation; try again')
    budget = (geometry['archive_end'] - geometry['archive_start']) * 2048 - TEXTURE_BYTES - BANKS_BYTES
    used = aligned(a['bytes']) + aligned(s['bytes'])
    risks = []
    for kind, data in (('ASSETS', a), ('STREAMS', s)):
        if data['max_live_end'] > ASSETS_POLICY_CAP:
            risks.append(kind + ' projected live data exceeds the conservative record-offset limit.')
    if a['max_decoded'] >= 2**31:
        risks.append('An ASSETS resource reaches the unverified 2 GiB decoded-size boundary.')
    if cache_path:
        path = Path(cache_path); path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='capacity_', suffix='.tmp', dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump({'key': cache_key, 'rows': sizes.rows}, stream)
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)
    return {'layout_profile': profile, 'layout_label': geometry['label'], 'assets_bytes': a['bytes'],
            'streams_bytes': s['bytes'], 'used_bytes': used, 'capacity_bytes': budget,
            'remaining_bytes': max(0, budget - used), 'over_capacity_bytes': max(0, used - budget),
            'record_risks': risks, 'new_compression_calculations': sizes.compressed_files,
            'staged_audio_included': False, 'is_projection': True, 'build_validation_required': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--cache', type=Path)
    args = parser.parse_args()
    try:
        print('MC3_CAPACITY_JSON:' + json.dumps(estimate(args.root, args.cache)), flush=True)
    except (OSError, ValueError, KeyError, TypeError, zlib.error) as exc:
        parser.exit(1, 'Capacity estimate unavailable: ' + str(exc) + '\n')
