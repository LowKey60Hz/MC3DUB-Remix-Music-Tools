"""Capacity gates must fail before ISO copying; legacy budgets remain separate."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parent.parent / 'UI Custom Gameplay Music Tools/supporting_tools'
sys.path.insert(0, str(TOOLS))
import archive_build_gate as gate
import MC3_ISO_Builder_V11A as builder
import MC3_ASSETS_Builder_V11A as compiler
import MC3_ISO_Builder_VIP as legacy
import MC3_ISO_Extractor as extractor


def index(kind, size, passes=True):
    return dict(kind=kind, archive_bytes=size, index_validated=True, passes_record_policy=passes,
                live_record_count=1, max_live_end_exclusive=size, risks=[] if passes else ['High offset'])


class BuildGateTests(unittest.TestCase):
    def test_v11a_replacements_do_not_silently_use_legacy_vip_budget(self):
        values = [index('ASSETS', 1805909737), index('STREAMS', 1087309824)]
        with patch.object(gate, 'inspect_archive', side_effect=values), contextlib.redirect_stdout(io.StringIO()):
            gate.check_records(Path('.'), 'vip-v11a')
        with patch.object(gate, 'inspect_archive', side_effect=values), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
            gate.check_records(Path('.'), 'vip')

    def test_engine_rejects_record_failure_without_copying_iso(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / 'source.iso', root / 'out.iso'
            source.write_bytes(b'unchanged')
            args = ['builder', '--source', str(source), '--output', str(output), '--replacement-dir', str(root), '--yes']
            with patch('sys.argv', args), patch.object(builder, 'sha256_file', return_value=builder.TRUSTED_VIP_V11A_SHA256), \
                 patch.object(builder.engine, 'inspect_base', return_value=({}, 100)), \
                 patch.object(builder, 'check_records', side_effect=ValueError('High offset')), \
                 patch.object(builder.shutil, 'copyfileobj') as copy, contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(ValueError):
                    builder.main()
                copy.assert_not_called()
            self.assertEqual(source.read_bytes(), b'unchanged')
            self.assertFalse(output.exists())
            self.assertFalse(output.with_name(output.name + '.building.tmp').exists())

    def test_compiler_does_not_replace_existing_archive_on_source_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output, files = root / 'source.iso', root / 'ASSETS.DAT', root / 'ASSETS'
            source.write_bytes(b'iso')
            output.write_bytes(b'keep verified archive')
            files.mkdir()
            with patch.object(compiler, 'sha256_file', return_value='unsupported'), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
                compiler.compile_assets(source, files, output, replace=True)
            self.assertEqual(output.read_bytes(), b'keep verified archive')

    def test_profile_layout_rounds_archive_sizes_before_relocation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'STREAMS.DAT').write_bytes(b'Hash' + bytes(5))
            (root / 'ASSETS.DAT').write_bytes(b'Dave' + bytes(13))
            rows = builder.make_rows(root)
            self.assertEqual(rows[1]['size'], 2048)
            self.assertEqual(rows[3]['size'], 2048)
            self.assertTrue(all(a['end'] + 1 == b['sector'] for a, b in zip(rows, rows[1:])))

    def test_renamed_legacy_reference_is_not_treated_as_custom(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'renamed-original.iso'
            source.write_bytes(b'fixture')
            args = ['builder', '--profile', 'vip', '--source', str(source), '--output', str(root / 'out.iso')]
            with patch('sys.argv', args), patch.object(extractor, 'classify', return_value=('VERIFIED_VIP_REFERENCE', {}, None)), \
                 patch.object(legacy, 'inspect_base', return_value=({}, 100)) as original, \
                 patch.object(legacy, 'inspect_modified_vip') as custom, \
                 patch.object(gate, 'check_records', side_effect=ValueError('stop after classification')), \
                 contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
                legacy.main()
            original.assert_called_once()
            custom.assert_not_called()


if __name__ == '__main__':
    unittest.main()
