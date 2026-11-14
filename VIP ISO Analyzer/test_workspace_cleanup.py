"""Cleanup tests operate exclusively on temporary miniature project fixtures."""
import contextlib
import io
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

GUI = Path(__file__).resolve().parent.parent / 'UI Custom Gameplay Music Tools/gui'
sys.path.insert(0, str(GUI))
import workspace_cleanup as cleanup


def fixture(directory):
    root = Path(directory) / 'project'
    (root / 'supporting_tools').mkdir(parents=True)
    (root / 'supporting_tools/MC3_Profile_108S.py').write_text('# fixture')
    for name in cleanup.WORKSPACE_FOLDERS:
        (root / name / 'nested').mkdir(parents=True)
        (root / name / 'nested/old.json').write_text('{"old":true}')
    (root / 'Custom Music').mkdir()
    (root / 'Custom Music/keep.wav').write_bytes(b'staged music')
    (root / 'MC3_Modified_VIP.iso').write_bytes(b'keep output')
    iso = Path(directory) / 'new.iso'
    iso.write_bytes(b'keep original')
    return root.resolve(), iso.resolve()


class CleanupTests(unittest.TestCase):
    def test_only_owned_directories_are_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            root, iso = fixture(directory)
            with contextlib.redirect_stdout(io.StringIO()):
                cleared = cleanup.clear_workspace(root, iso)
            self.assertEqual(cleared, list(cleanup.WORKSPACE_FOLDERS))
            self.assertTrue(all(not (root / name).exists() for name in ('ASSETS','STREAMS','ISO_FILES')))
            self.assertEqual(list((root / 'support_logs').iterdir()), [])
            self.assertEqual(iso.read_bytes(), b'keep original')
            self.assertEqual((root / 'Custom Music/keep.wav').read_bytes(), b'staged music')
            self.assertEqual((root / 'MC3_Modified_VIP.iso').read_bytes(), b'keep output')
            self.assertTrue((root / 'supporting_tools/MC3_Profile_108S.py').is_file())

    def test_source_inside_a_cleanup_target_blocks_all_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _ = fixture(directory)
            iso = root / 'ISO_FILES/new.iso'
            iso.write_bytes(b'keep source')
            with self.assertRaises(ValueError):
                cleanup.clear_workspace(root, iso)
            self.assertTrue(all((root / name / 'nested/old.json').is_file() for name in cleanup.WORKSPACE_FOLDERS))

    def test_non_directory_target_and_wrong_project_root_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            iso = root / 'source.iso'
            iso.write_bytes(b'iso')
            with self.assertRaises(ValueError):
                cleanup.cleanup_plan(root, iso)
            (root / 'supporting_tools').mkdir()
            (root / 'supporting_tools/MC3_Profile_108S.py').write_text('# fixture')
            (root / 'ASSETS').write_bytes(b'not a directory')
            with self.assertRaises(ValueError):
                cleanup.clear_workspace(root, iso)
            self.assertEqual((root / 'ASSETS').read_bytes(), b'not a directory')

    def test_nested_link_is_detected_before_any_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            root, iso = fixture(directory)
            original = cleanup.is_link
            with patch.object(cleanup, 'is_link', side_effect=lambda path: path == root / 'ASSETS/nested' or original(path)):
                with self.assertRaises(ValueError):
                    cleanup.clear_workspace(root, iso)
            self.assertTrue(all((root / name / 'nested/old.json').is_file() for name in cleanup.WORKSPACE_FOLDERS))

    def test_windows_reparse_flag_is_rejected(self):
        path = Mock()
        path.lstat.return_value = SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        self.assertTrue(cleanup.is_link(path))

    def test_failure_stops_without_removing_remaining_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            root, iso = fixture(directory)
            original = cleanup.shutil.rmtree
            def remove(path):
                if path.name == 'ASSETS':
                    raise PermissionError('file in use')
                original(path)
            with patch.object(cleanup.shutil, 'rmtree', side_effect=remove), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(OSError) as error:
                    cleanup.clear_workspace(root, iso)
            self.assertIn('Already cleared: STREAMS', str(error.exception))
            self.assertTrue((root / 'ISO_FILES/nested/old.json').is_file())
            self.assertTrue((root / 'support_logs/nested/old.json').is_file())
            self.assertEqual(iso.read_bytes(), b'keep original')

    def test_cleanup_worker_cli_with_spaces_in_paths(self):
        with tempfile.TemporaryDirectory(prefix='cleanup fixture ') as directory:
            root, iso = fixture(directory)
            process = subprocess.run([sys.executable, str(GUI / 'workspace_cleanup.py'), '--root', str(root), '--source-iso', str(iso)], capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertIn('Workspace cleanup completed', process.stdout)
            self.assertEqual(list((root / 'support_logs').iterdir()), [])
            self.assertEqual(iso.read_bytes(), b'keep original')


if __name__ == '__main__':
    unittest.main()
