"""Fault-injection checks for preservation outside experimental write ranges."""
import hashlib
import io
import unittest
from build_v11a_expansion_test import verify_unchanged


def hash_region(stream, start, length):
    stream.seek(start)
    return hashlib.sha256(stream.read(length)).hexdigest()


class PreservationTests(unittest.TestCase):
    def check_data(self, changed):
        verify_unchanged(io.BytesIO(bytes(64)), io.BytesIO(changed), 64,
                         [(8, 16), (32, 40)], hash_region)

    def test_only_intended_regions_can_change(self):
        changed = bytearray(64)
        changed[8:16] = bytes([1]) * 8
        changed[32:40] = bytes([2]) * 8
        self.check_data(changed)

    def test_changes_in_every_protected_gap_are_rejected(self):
        for offset in (0, 7, 16, 31, 40, 63):
            with self.subTest(offset=offset):
                changed = bytearray(64)
                changed[offset] = 1
                with self.assertRaises(ValueError):
                    self.check_data(changed)

    def test_image_growth_and_truncation_are_rejected(self):
        for length in (63, 65):
            with self.subTest(length=length), self.assertRaises(ValueError):
                self.check_data(bytes(length))

    def test_overlapping_or_out_of_bounds_permissions_are_rejected(self):
        for ranges in ([(8, 16), (15, 20)], [(-1, 3)], [(60, 65)]):
            with self.subTest(ranges=ranges), self.assertRaises(ValueError):
                verify_unchanged(io.BytesIO(bytes(64)), io.BytesIO(bytes(64)), 64, ranges, hash_region)


if __name__ == '__main__':
    unittest.main()
