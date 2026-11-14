"""Boundary tests; no multi-gigabyte fixtures or ISO writes."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parent.parent / 'UI Custom Gameplay Music Tools/supporting_tools/vip_capacity.py'
spec = importlib.util.spec_from_file_location('vip_capacity', path)
capacity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capacity)


class CapacityTests(unittest.TestCase):
    def test_tested_combination(self):
        result = capacity.assess(1805909737, 1087309824, capacity.REFERENCE_SHA256)
        self.assertEqual(result['remaining_bytes'], 488124416)
        self.assertTrue(result['exact_experimental_builder_sizes'])
        self.assertIsNone(result['game_maximum_bytes'])

    def test_exact_capacity_and_one_byte_over(self):
        limit = capacity.assess(1805909737, 1087309824)['max_assets_allocated_with_these_streams']
        self.assertTrue(capacity.assess(limit, 1087309824)['fits_assumed_layout'])
        over = capacity.assess(limit + 1, 1087309824)
        self.assertFalse(over['fits_assumed_layout'])
        self.assertEqual(over['over_capacity_bytes'], 2048)

    def test_shared_budget_is_symmetric(self):
        a, b = capacity.assess(2000000000, 1100000000), capacity.assess(1100000000, 2000000000)
        self.assertEqual(a['remaining_bytes'], b['remaining_bytes'])

    def test_two_gib_fits_space_but_does_not_establish_runtime_support(self):
        result = capacity.assess(2**31, 1087309824)
        self.assertTrue(result['fits_assumed_layout'])
        # Outer size is within the passing size-only probe's range, but without
        # actual records the conservative fallback must still block it.
        self.assertTrue(result['within_tested_size_envelope'])
        self.assertTrue(any('2 GiB' in warning for warning in result['warnings']))
        self.assertFalse(result['exact_experimental_builder_sizes'])
        self.assertFalse(result['passes_size_policy'])
        self.assertEqual(result['status'], 'EXCEEDS_ASSETS_TESTED_SIZE_POLICY')

    def test_last_sector_below_boundary_passes_policy(self):
        result = capacity.assess(2147481600, 1087309824)
        self.assertTrue(result['passes_size_policy'])
        self.assertEqual(result['max_assets_within_size_policy_bytes'], 2147481600)
        self.assertEqual(result['assets_growth_within_size_policy_bytes'], 0)

    def test_one_byte_past_tested_sector_is_blocked_after_rounding(self):
        result = capacity.assess(2147481601, 1087309824)
        self.assertEqual(result['assets_allocated_bytes'], 2**31)
        self.assertFalse(result['passes_size_policy'])

    def test_unknown_future_reference_is_unsupported(self):
        result = capacity.assess(1805909737, 1087309824, 'future-hash')
        self.assertEqual(result['status'], 'FITS_LAYOUT_UNSUPPORTED_SOURCE')

    def test_overflow_and_invalid_sizes(self):
        self.assertFalse(capacity.assess(2**32, 1087309824)['fits_assumed_layout'])
        for value in (-1, 0, True, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                capacity.assess(value, 1087309824)


if __name__ == '__main__':
    unittest.main()
