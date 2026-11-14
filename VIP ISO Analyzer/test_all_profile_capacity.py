"""Profile budgets and refusal paths must not borrow v1.1-A capacity."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from test_vip_capacity import capacity
from test_build_capacity_integration import index
import archive_build_gate as gate


class AllProfileTests(unittest.TestCase):
    def test_budgets_match_each_engine_geometry(self):
        import MC3_ISO_Builder_VIP as vip
        import MC3_ISO_Builder_Retail as retail
        for profile, info in (('vip',vip.PROFILES['VIP Expansion']['archives']), ('retail',retail.PROFILES['Retail USA']['archives'])):
            with self.subTest(profile=profile):
                sizes = {row[0]:row[2] for row in info}
                result = capacity.assess(sizes['ASSETS.DAT'], sizes['STREAMS.DAT'], layout_profile=profile)
                self.assertEqual(result['remaining_bytes'], 0)
                self.assertEqual(result['shared_layout_capacity_bytes'], sizes['ASSETS.DAT'] + sizes['STREAMS.DAT'])
                self.assertTrue(result['passes_size_policy'])

    def test_exact_fit_and_one_byte_sector_overrun_for_every_profile(self):
        for profile in capacity.CAPACITY_PROFILES:
            with self.subTest(profile=profile):
                streams = 1087309824
                limit = capacity.assess(10000, streams, layout_profile=profile)['max_assets_allocated_with_these_streams']
                self.assertTrue(capacity.assess(limit, streams, layout_profile=profile)['fits_assumed_layout'])
                self.assertEqual(capacity.assess(limit + 1, streams, layout_profile=profile)['over_capacity_bytes'], 2048)

    def test_source_fingerprints_cannot_select_the_wrong_budget(self):
        for profile, definition in capacity.CAPACITY_PROFILES.items():
            for other, other_definition in capacity.CAPACITY_PROFILES.items():
                result = capacity.assess(10000, 10000, other_definition['sha256'], layout_profile=profile)
                self.assertEqual(result['profile'] == definition['verified_class'], definition['sha256'] == other_definition['sha256'])

    def test_gate_saves_actionable_capacity_failure_report(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'capacity.json'
            records = [index('ASSETS', 1805909737), index('STREAMS', 1087309824)]
            with patch.object(gate, 'inspect_archive', side_effect=records), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(ValueError) as error:
                    gate.check_records(Path('.'), 'vip', report)
            result = json.loads(report.read_text())
            self.assertEqual(result['layout_profile'], 'vip')
            self.assertGreater(result['over_capacity_bytes'], 0)
            self.assertIn('VIP v1.0-C capacity exceeded', str(error.exception))
            self.assertIn('MiB', str(error.exception))

    def test_invalid_index_also_generates_failure_report(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'capacity.json'
            with patch.object(gate, 'inspect_archive', side_effect=ValueError('truncated table')), self.assertRaises(ValueError):
                gate.check_records(Path('.'), 'retail', report)
            result = json.loads(report.read_text())
            self.assertEqual(result['failed_archive'], 'ASSETS')
            self.assertEqual(result['status'], 'INVALID_OR_UNSUPPORTED_ARCHIVE_INDEX')

    def test_each_profile_blocks_high_records_even_when_space_fits(self):
        for profile in capacity.CAPACITY_PROFILES:
            with self.subTest(profile=profile):
                assets = index('ASSETS', 100000, False)
                streams = index('STREAMS', 100000)
                result = capacity.assess(100000,100000, assets_index=assets,streams_index=streams,layout_profile=profile)
                self.assertTrue(result['fits_assumed_layout'])
                self.assertFalse(result['passes_size_policy'])


if __name__ == '__main__':
    unittest.main()
