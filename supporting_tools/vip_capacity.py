"""Profile-specific Retail/VIP capacity and compiled record checks.

This checker does not authorize ISO writes or certify game compatibility.
UDF extent reference: https://ecma-international.org/publications-and-standards/standards/ecma-167/
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct

SECTOR = 2048
ARCHIVE_START = 9702
MANIFEST_START = 2074717
TEXTURE_BYTES = 794839040
BANKS_BYTES = 52967424
EXPERIMENTAL_ASSETS_BYTES = 1805909737
TESTED_ASSETS_BYTES = 2154035200  # Size-only image passed; not a live-offset limit.
ASSETS_POLICY_CAP = 2**31 - SECTOR
TESTED_STREAMS_BYTES = 1087309824
V5_ASSETS_CAP = 1808326656
REFERENCE_SHA256 = 'b792163c131b57d76f6ebff99a0e0029f67f653309c97e02a136c3767f2c839d'
CAPACITY_PROFILES = {
    'vip-v11a': dict(label='VIP v1.1-A', archive_start=9702, archive_end=2074717,
                     sha256=REFERENCE_SHA256, verified_class='VERIFIED_V11A_REFERENCE'),
    'vip': dict(label='VIP v1.0-C', archive_start=9702, archive_end=1772493,
                sha256='906ada438e097d4668feabd6ef8b8d388876811181cb89ea6b1648e5f2acbe4c',
                verified_class='VERIFIED_VIP_REFERENCE'),
    'vip-expanded': dict(label='VIP v1.0-C expanded', archive_start=9702, archive_end=2074717,
                         sha256='906ada438e097d4668feabd6ef8b8d388876811181cb89ea6b1648e5f2acbe4c',
                         verified_class='VERIFIED_VIP_REFERENCE'),
    'retail': dict(label='Retail USA', archive_start=454764, archive_end=2074717,
                   sha256='de199f7e7f57b7cb603a129217f7482d50644fd66558450dfeb5612857b732f9',
                   verified_class='VERIFIED_RETAIL_REFERENCE'),
    'retail-expanded': dict(label='Retail USA expanded', archive_start=9702, archive_end=2074717,
                            sha256='de199f7e7f57b7cb603a129217f7482d50644fd66558450dfeb5612857b732f9',
                            verified_class='VERIFIED_RETAIL_REFERENCE'),
}


def aligned(size):
    return (size + SECTOR - 1) // SECTOR * SECTOR


def inspect_archive(path, kind, *, extent_start=0, extent_length=None):
    """Inspect supported Dave/Hash tables only; do not decompress or certify payloads."""
    path = Path(path)
    if kind not in ('ASSETS', 'STREAMS'):
        raise ValueError('Expected ASSETS or STREAMS archive kind')
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        size = before.st_size if extent_length is None else extent_length
        if (isinstance(extent_start,bool) or not isinstance(extent_start,int) or extent_start < 0
                or isinstance(size,bool) or not isinstance(size,int) or size < 4
                or extent_start + size > before.st_size):
            raise ValueError('Invalid archive extent in source file')
        stream.seek(extent_start)
        header_size = 16 if kind == 'ASSETS' else 8
        header = stream.read(header_size)
        if len(header) != header_size:
            raise ValueError(f'{kind}: truncated header')
        magic, count = struct.unpack_from('<4sI', header)
        if magic != (b'Dave' if kind == 'ASSETS' else b'Hash'):
            raise ValueError(f'{kind}: unsupported archive signature')
        if not 0 < count <= 1000000:
            raise ValueError(f'{kind}: unreasonable record count')
        stride = 16 if kind == 'ASSETS' else 12
        if kind == 'ASSETS':
            table_bytes, name_bytes = struct.unpack_from('<II', header, 8)
            if table_bytes < count * stride:
                raise ValueError('ASSETS: entry block shorter than record count')
            table_start = 0x800
            payload_floor = table_start + table_bytes + name_bytes
        else:
            table_start = 8
            payload_floor = table_start + count * stride
        if payload_floor > size:
            raise ValueError(f'{kind}: tables exceed archive')
        stream.seek(extent_start + table_start)
        table = stream.read(count * stride)
        if len(table) != count * stride:
            raise ValueError(f'{kind}: truncated record table')
        ranges, seen_hashes, risks = [], set(), []
        high_count = near_count = decoded_count = zero_pointer_count = 0
        live_count = max_offset = max_end = max_full = 0
        examples = []
        for index in range(count):
            fields = struct.unpack_from('<IIII' if kind == 'ASSETS' else '<III', table, index * stride)
            if kind == 'ASSETS':
                _, offset, full, stored = fields
                if stored > full or (full > 0 and stored == 0):
                    raise ValueError(f'ASSETS: inconsistent stored/decoded size at record {index}')
            else:
                key, offset, stored = fields
                full = stored
                if key in seen_hashes:
                    raise ValueError(f'STREAMS: duplicate hash at record {index}')
                seen_hashes.add(key)
            if stored == 0:
                # Dave includes zero-size directory/empty-file records. Their
                # pointers are still reported: the game may use them as metadata.
                if offset > size:
                    raise ValueError(f'{kind}: empty-record pointer exceeds archive')
                zero_pointer_count += offset > ASSETS_POLICY_CAP
                continue
            end = offset + stored
            if offset < payload_floor or end > size:
                raise ValueError(f'{kind}: payload outside data area at record {index}')
            live_count += 1
            max_offset, max_end, max_full = max(max_offset, offset), max(max_end, end), max(max_full, full)
            high = offset >= 2**31 or end >= 2**31
            near = end > ASSETS_POLICY_CAP
            decoded = kind == 'ASSETS' and full >= 2**31
            high_count += high
            near_count += near
            decoded_count += decoded
            if (near or decoded) and len(examples) < 10:
                examples.append({'index': index, 'offset': offset, 'end_exclusive': end,
                                 'stored_bytes': stored, 'decoded_bytes': full})
            ranges.append((offset, end, full))
        shared_records = 0
        previous = None
        for current in sorted(ranges):
            if previous and current[0] < previous[1]:
                if current != previous:
                    raise ValueError(f'{kind}: unsupported overlapping payload ranges')
                shared_records += 1
            previous = current
        if near_count:
            risks.append('Live payloads extend past the conservative tested low-offset ceiling.')
        if decoded_count:
            risks.append('Individual decoded ASSETS resources reach 2 GiB; decoder behavior is unverified.')
        if zero_pointer_count:
            risks.append('Empty/directory record pointers exceed the conservative low-offset ceiling.')
        after = os.fstat(stream.fileno())
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError(f'{kind}: archive changed during inspection')
    return {'kind': kind, 'path': str(path.resolve()), 'archive_bytes': size,
            'source_extent_offset_bytes': extent_start,
            'index_validated': True, 'payload_contents_verified': False,
            'record_count': count, 'live_record_count': live_count,
            'max_live_offset': max_offset, 'max_live_end_exclusive': max_end,
            'max_decoded_resource_bytes': max_full,
            'records_reaching_2GiB': high_count, 'records_past_conservative_offset_ceiling': near_count,
            'large_decoded_resource_count': decoded_count,
            'high_empty_or_directory_pointer_count': zero_pointer_count,
            'shared_payload_record_count': shared_records,
            'risk_examples': examples, 'risks': risks, 'passes_record_policy': not risks,
            'trailing_bytes_after_last_live_payload': size - max_end,
            'table_sha256': hashlib.sha256(table).hexdigest()}


def assess(assets_bytes, streams_bytes, source_sha256=None, *, assets_index=None, streams_index=None, layout_profile='vip-v11a'):
    if layout_profile not in CAPACITY_PROFILES:
        raise ValueError('Unknown ISO capacity profile')
    geometry = CAPACITY_PROFILES[layout_profile]
    for value in (assets_bytes, streams_bytes):
        if isinstance(value, bool) or not isinstance(value, int) or value < 4:
            raise ValueError('Archive sizes must be integers of at least four bytes')
    total = (geometry['archive_end'] - geometry['archive_start']) * SECTOR
    shared = total - aligned(TEXTURE_BYTES) - aligned(BANKS_BYTES)
    assets, streams = aligned(assets_bytes), aligned(streams_bytes)
    remaining = shared - assets - streams
    field_fit = assets <= 0xffffffff and streams <= 0xffffffff
    layout_fit = remaining >= 0 and field_fit
    for kind, inspection, expected_size in (('ASSETS', assets_index, assets_bytes), ('STREAMS', streams_index, streams_bytes)):
        if inspection is not None and (inspection.get('kind') != kind or inspection.get('archive_bytes') != expected_size or not inspection.get('index_validated')):
            raise ValueError('Mismatched or unvalidated archive inspection')
    assets_policy_fit = assets_index['passes_record_policy'] if assets_index is not None else assets <= ASSETS_POLICY_CAP
    streams_policy_fit = streams_index['passes_record_policy'] if streams_index is not None else streams <= ASSETS_POLICY_CAP
    profile = ('UNVERIFIED_LAYOUT_ASSUMPTION' if source_sha256 is None else
               geometry['verified_class'] if source_sha256 == geometry['sha256'] else
               'UNSUPPORTED_SOURCE_REFERENCE')
    warnings = []
    if not assets_policy_fit:
        warnings.append('ASSETS live-record policy failed.' if assets_index is not None else 'ASSETS reaches 2 GiB after padding. Record inspection is required to distinguish harmless trailing bytes from high-offset resources.')
    if not streams_policy_fit:
        warnings.append('STREAMS live-record policy failed.' if streams_index is not None else 'STREAMS reaches the conservative low-offset ceiling without record inspection.')
    if layout_profile != 'vip-v11a':
        warnings.append('The low-offset policy is conservative for this version; the 2 GiB probes were performed on VIP v1.1-A, not this source.')
    elif assets > aligned(TESTED_ASSETS_BYTES) or streams > aligned(TESTED_STREAMS_BYTES):
        warnings.append('At least one archive exceeds its user-tested size. Layout fit does not establish runtime support.')
    if assets >= 2**31 or streams >= 2**31:
        warnings.append('Outer archive length reaches/crosses 2 GiB. A size-only ASSETS probe passed, but high-offset loading records caused a career crash; record placement and contents require separate checks.')
    if assets_index is not None:
        warnings.extend(assets_index['risks'])
    if streams_index is not None:
        warnings.extend(streams_index['risks'])
    if assets >= 2**30 or streams >= 2**30:
        warnings.append('Observed builder writes full lengths into UDF short extents, whose upper bits normally encode extent type. This layout quirk is not generic UDF support.')
    if layout_profile == 'vip-v11a' and assets_bytes > V5_ASSETS_CAP:
        warnings.append('Existing v5 ASSETS compiler rejects this size regardless of disc headroom.')
    if profile != geometry['verified_class']:
        warnings.append('No trusted source match for ' + geometry['label'] + '. New or modified sources need their own source/layout validation.')
    return {
        'profile': profile,
        'layout_profile': layout_profile,
        'layout_label': geometry['label'],
        'archive_start_sector': geometry['archive_start'],
        'archive_end_exclusive_sector': geometry['archive_end'],
        'status': 'EXCEEDS_LAYOUT_OR_SIZE_FIELDS' if not layout_fit else
                  ('ASSETS_RECORD_POLICY_BLOCKED' if assets_index is not None else 'EXCEEDS_ASSETS_TESTED_SIZE_POLICY') if not assets_policy_fit else
                  'STREAMS_RECORD_POLICY_BLOCKED' if not streams_policy_fit else
                  'FITS_LAYOUT_UNSUPPORTED_SOURCE' if profile == 'UNSUPPORTED_SOURCE_REFERENCE' else
                  'FITS_LAYOUT_RUNTIME_UNVERIFIED',
        'fits_assumed_layout': layout_fit,
        'passes_size_policy': layout_fit and assets_policy_fit and streams_policy_fit,
        'assets_policy_basis': 'LIVE_RECORD_INDEX' if assets_index is not None else 'OUTER_SIZE_FALLBACK',
        'streams_policy_basis': 'LIVE_RECORD_INDEX' if streams_index is not None else 'OUTER_SIZE_FALLBACK',
        'assets_index': assets_index, 'streams_index': streams_index,
        'assets_tested_size_policy_cap_bytes': ASSETS_POLICY_CAP if assets_index is None else None,
        'assets_live_end_policy_cap_bytes': ASSETS_POLICY_CAP,
        'max_assets_within_size_policy_bytes': max(0, min(shared - streams, ASSETS_POLICY_CAP)) if assets_index is None else None,
        'assets_growth_within_size_policy_bytes': max(0, min(shared - streams, ASSETS_POLICY_CAP) - assets) if assets_index is None else None,
        'assets_live_offset_headroom_bytes': max(0, ASSETS_POLICY_CAP - aligned(assets_index['max_live_end_exclusive'])) if assets_index is not None else None,
        'assets_payload_bytes': assets_bytes, 'assets_allocated_bytes': assets,
        'streams_payload_bytes': streams_bytes, 'streams_allocated_bytes': streams,
        'shared_layout_capacity_bytes': shared,
        'remaining_bytes': max(0, remaining), 'over_capacity_bytes': max(0, -remaining),
        'max_assets_allocated_with_these_streams': max(0, min(shared - streams, 0xfffff800)),
        'max_streams_allocated_with_these_assets': max(0, min(shared - assets, 0xfffff800)),
        'within_tested_size_envelope': (assets <= aligned(TESTED_ASSETS_BYTES) and streams <= aligned(TESTED_STREAMS_BYTES)) if layout_profile == 'vip-v11a' else None,
        'exact_experimental_builder_sizes': layout_profile == 'vip-v11a' and assets_bytes == EXPERIMENTAL_ASSETS_BYTES and streams_bytes == TESTED_STREAMS_BYTES,
        'v5_assets_compiler_size_limit_bytes': V5_ASSETS_CAP if layout_profile == 'vip-v11a' else None,
        'game_maximum_bytes': None,
        'warnings': warnings,
        'scope': 'Capacity and optional index/record policy only. No payload verification, build authorization or runtime compatibility guarantee. Live-offset headroom does not measure reclaimable archive gaps.'}


def assess_archives(assets_path, streams_path, source_sha256=None, *, layout_profile='vip-v11a'):
    assets = inspect_archive(assets_path, 'ASSETS')
    streams = inspect_archive(streams_path, 'STREAMS')
    return assess(assets['archive_bytes'], streams['archive_bytes'], source_sha256,
                  assets_index=assets, streams_index=streams, layout_profile=layout_profile)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=tuple(CAPACITY_PROFILES), default='vip-v11a')
    assets = parser.add_mutually_exclusive_group(required=True)
    assets.add_argument('--assets', type=Path)
    assets.add_argument('--assets-bytes', type=int)
    streams = parser.add_mutually_exclusive_group(required=True)
    streams.add_argument('--streams', type=Path)
    streams.add_argument('--streams-bytes', type=int)
    parser.add_argument('--source-iso', type=Path, help='Optional full SHA-256 check of original source; unknown references remain unsupported')
    parser.add_argument('--report', type=Path, help='Write a new JSON report; existing files are never overwritten')
    args = parser.parse_args()
    source_hash = None
    if args.source_iso:
        value = hashlib.sha256()
        with args.source_iso.open('rb') as stream:
            for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                value.update(block)
        source_hash = value.hexdigest()
    try:
        assets_inspection = inspect_archive(args.assets, 'ASSETS') if args.assets else None
        streams_inspection = inspect_archive(args.streams, 'STREAMS') if args.streams else None
        result = assess(assets_inspection['archive_bytes'] if assets_inspection else args.assets_bytes,
                        streams_inspection['archive_bytes'] if streams_inspection else args.streams_bytes,
                        source_hash, assets_index=assets_inspection, streams_index=streams_inspection, layout_profile=args.profile)
    except (ValueError, OSError, struct.error) as error:
        result = {'status': 'INVALID_OR_UNSUPPORTED_ARCHIVE_INDEX', 'error': str(error),
                  'fits_assumed_layout': False, 'passes_size_policy': False,
                  'profile': 'NOT_EVALUATED'}
    result['source_sha256'] = source_hash
    if args.report:
        with args.report.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    if result['status'] == 'INVALID_OR_UNSUPPORTED_ARCHIVE_INDEX':
        raise SystemExit(5)
    if not result['fits_assumed_layout']:
        raise SystemExit(2)
    if result['profile'] == 'UNSUPPORTED_SOURCE_REFERENCE':
        raise SystemExit(3)
    if not result['passes_size_policy']:
        raise SystemExit(4)


if __name__ == '__main__':
    main()
