import unittest
from build_assets_boundary_probes import relocation_plan


class ProbePlanTests(unittest.TestCase):
    def setUp(self):
        self.records = [{'index': 1, 'name': 'audio/loadscreen/1.raw', 'offset': 100,
                         'stored': 4097, 'full': 5000},
                        {'index': 2, 'name': 'audio/loadscreen/1.raw', 'offset': 6000,
                         'stored': 4097, 'full': 5000}]

    def test_below_control_keeps_all_payloads_below_boundary(self):
        plan = relocation_plan(self.records, 1805909737, 'below', 2294034432)
        self.assertEqual(plan['archive_bytes'], 2**31 - 2048)
        self.assertTrue(all(x['new_offset'] + x['stored'] < 2**31 for x in plan['records']))

    def test_above_probe_moves_every_duplicate_beyond_boundary(self):
        plan = relocation_plan(self.records, 1805909737, 'above', 2294034432)
        self.assertEqual(len(plan['records']), 2)
        self.assertTrue(all(x['new_offset'] > 2**31 for x in plan['records']))

    def test_insufficient_capacity_and_no_tail_room_rejected(self):
        with self.assertRaises(ValueError):
            relocation_plan(self.records, 1805909737, 'above', 2**31)
        with self.assertRaises(ValueError):
            relocation_plan(self.records, 2**31, 'below', 2294034432)

    def test_no_probe_resources_rejected(self):
        with self.assertRaises(ValueError):
            relocation_plan([], 1805909737, 'above', 2294034432)


if __name__ == '__main__':
    unittest.main()
