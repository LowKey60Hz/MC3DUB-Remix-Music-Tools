"""Record-table boundary and corruption tests without large fixtures."""
from pathlib import Path
import struct
import tempfile
import contextlib
import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from test_vip_capacity import capacity


class RecordCapacityTests(unittest.TestCase):
    def scan(self, kind, records, virtual_size=65536):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.dat'
            if kind == 'ASSETS':
                data = bytearray(struct.pack('<4sIII', b'Dave', len(records), len(records) * 16, 0))
                data.extend(bytes(0x800 - len(data)))
                data.extend(b''.join(struct.pack('<IIII', *row) for row in records))
            else:
                data = bytearray(struct.pack('<4sI', b'Hash', len(records)))
                data.extend(b''.join(struct.pack('<III', *row) for row in records))
            path.write_bytes(data)
            # The scanner reads tables only. Simulate logical archive length;
            # no multi-gigabyte test files or payload verification are needed.
            with patch.object(capacity.os, 'fstat', return_value=SimpleNamespace(st_size=virtual_size, st_mtime_ns=1)):
                return capacity.inspect_archive(path, kind)

    def test_large_outer_size_with_low_records_passes(self):
        assets = self.scan('ASSETS', [(0, 4096, 32, 16)], 2154035200)
        streams = self.scan('STREAMS', [(123, 2048, 16)], 1087309824)
        result = capacity.assess(2154035200, 1087309824, capacity.REFERENCE_SHA256,
                                 assets_index=assets, streams_index=streams)
        self.assertTrue(result['passes_size_policy'])
        self.assertEqual(result['assets_policy_basis'], 'LIVE_RECORD_INDEX')
        self.assertFalse(assets['payload_contents_verified'])
        self.assertIsNone(result['assets_growth_within_size_policy_bytes'])

    def test_same_outer_size_with_high_records_is_blocked(self):
        assets = self.scan('ASSETS', [(0, 2**31 + 2048, 32, 16)], 2154035200)
        result = capacity.assess(2154035200, 1087309824, assets_index=assets)
        self.assertFalse(result['passes_size_policy'])
        self.assertEqual(result['status'], 'ASSETS_RECORD_POLICY_BLOCKED')
        self.assertEqual(assets['records_reaching_2GiB'], 1)

    def test_read_end_crossing_boundary_is_blocked_even_with_low_start(self):
        assets = self.scan('ASSETS', [(0, 2**31 - 4096, 8192, 8192)], 2154035200)
        self.assertFalse(assets['passes_record_policy'])

    def test_end_at_tested_ceiling_passes_but_next_byte_is_reviewed(self):
        for end, expected in ((capacity.ASSETS_POLICY_CAP, True), (capacity.ASSETS_POLICY_CAP + 1, False)):
            with self.subTest(end=end):
                result = self.scan('ASSETS', [(0, end - 16, 16, 16)], 2154035200)
                self.assertEqual(result['passes_record_policy'], expected)

    def test_tables_and_payload_bounds_are_enforced(self):
        for row in ((0, 2048, 32, 16), (0, 65530, 32, 16), (0, 4096, 8, 16), (0, 4096, 16, 0)):
            with self.subTest(row=row), self.assertRaises(ValueError):
                self.scan('ASSETS', [row])

    def test_duplicate_stream_hash_is_rejected(self):
        with self.assertRaises(ValueError):
            self.scan('STREAMS', [(1, 2048, 16), (1, 4096, 16)])

    def test_partial_overlap_rejected_exact_payload_alias_allowed(self):
        with self.assertRaises(ValueError):
            self.scan('ASSETS', [(0, 4096, 16, 16), (1, 4104, 16, 16)])
        aliases = self.scan('ASSETS', [(0, 4096, 16, 16), (1, 4096, 16, 16)])
        self.assertEqual(aliases['shared_payload_record_count'], 1)

    def test_stream_high_offsets_are_blocked(self):
        streams = self.scan('STREAMS', [(1, 2**31 + 2048, 16)], 2154035200)
        result = capacity.assess(10000000, 2154035200, streams_index=streams)
        self.assertTrue(result['fits_assumed_layout'])
        self.assertFalse(result['passes_size_policy'])
        self.assertEqual(result['status'], 'STREAMS_RECORD_POLICY_BLOCKED')

    def test_unverified_large_decoded_resource_and_directory_pointer(self):
        decoded = self.scan('ASSETS', [(0, 4096, 2**31, 16)])
        self.assertFalse(decoded['passes_record_policy'])
        directory = self.scan('ASSETS', [(0, 2**31 + 1, 0, 0), (1, 4096, 16, 16)], 2154035200)
        self.assertFalse(directory['passes_record_policy'])

    def test_mismatched_inspection_is_rejected(self):
        assets = self.scan('ASSETS', [(0, 4096, 16, 16)])
        with self.assertRaises(ValueError):
            capacity.assess(99999, 10000, assets_index=assets)

    def test_truncated_and_unsupported_headers_rejected(self):
        for data in (b'Dave', struct.pack('<4sIII', b'DAVE', 1, 16, 0),
                     struct.pack('<4sIII', b'Dave', 1, 15, 0),
                     struct.pack('<4sIII', b'Dave', 1000001, 16000016, 0)):
            with self.subTest(data=data), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'bad.dat'
                path.write_bytes(data)
                with self.assertRaises(ValueError):
                    capacity.inspect_archive(path, 'ASSETS')

    def test_truncated_table_and_change_during_scan_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'truncated.dat'
            path.write_bytes(struct.pack('<4sIII', b'Dave', 1, 16, 0))
            with patch.object(capacity.os, 'fstat', return_value=SimpleNamespace(st_size=65536, st_mtime_ns=1)):
                with self.assertRaises(ValueError):
                    capacity.inspect_archive(path, 'ASSETS')
            data = bytearray(struct.pack('<4sIII', b'Dave', 1, 16, 0))
            data.extend(bytes(2048 - len(data)))
            data.extend(struct.pack('<IIII', 0, 4096, 16, 16))
            path.write_bytes(data)
            stats = [SimpleNamespace(st_size=65536, st_mtime_ns=1), SimpleNamespace(st_size=65536, st_mtime_ns=2)]
            with patch.object(capacity.os, 'fstat', side_effect=stats), self.assertRaises(ValueError):
                capacity.inspect_archive(path, 'ASSETS')

    def test_cli_reports_invalid_archive_with_exit_five(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'invalid.dat'
            path.write_bytes(b'Dave')
            output = io.StringIO()
            with patch('sys.argv', ['vip_capacity', '--assets', str(path), '--streams-bytes', '1087309824']), contextlib.redirect_stdout(output):
                with self.assertRaises(SystemExit) as error:
                    capacity.main()
            self.assertEqual(error.exception.code, 5)
            self.assertEqual(json.loads(output.getvalue())['status'], 'INVALID_OR_UNSUPPORTED_ARCHIVE_INDEX')

    def test_cli_size_only_numbers_keep_conservative_fallback(self):
        output = io.StringIO()
        with patch('sys.argv', ['vip_capacity', '--assets-bytes', '2154035200', '--streams-bytes', '1087309824']), contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit) as error:
                capacity.main()
        self.assertEqual(error.exception.code, 4)
        self.assertEqual(json.loads(output.getvalue())['assets_policy_basis'], 'OUTER_SIZE_FALLBACK')

    def test_archive_extent_inside_iso_uses_relative_offsets_and_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'container.iso'
            archive=bytearray(65536)
            struct.pack_into('<4sIII',archive,0,b'Dave',1,16,0)
            struct.pack_into('<IIII',archive,2048,0,4096,32,16)
            path.write_bytes(bytes(4096)+archive)
            result=capacity.inspect_archive(path,'ASSETS',extent_start=4096,extent_length=65536)
            self.assertEqual(result['archive_bytes'],65536)
            self.assertEqual(result['max_live_end_exclusive'],4112)
            for start,length in ((-1,10),(4096,65537),(4096,0)):
                with self.subTest(start=start,length=length),self.assertRaises(ValueError):
                    capacity.inspect_archive(path,'ASSETS',extent_start=start,extent_length=length)


if __name__ == '__main__':
    unittest.main()
