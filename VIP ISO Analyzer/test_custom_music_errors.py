"""Strict song-name rejection and actionable GUI failures, using temporary fixtures."""
import contextlib
import io
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parent.parent/'UI Custom Gameplay Music Tools'
sys.path.insert(0, str(PROJECT/'gui'))
sys.path.insert(0, str(PROJECT/'supporting_tools'))
import main as gui
import add_gameplay_songs as converter


class CustomMusicErrorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = gui.QApplication.instance() or gui.QApplication([])

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        with patch.object(gui, 'ROOT', self.root), patch.object(gui.Window, 'start_auto_validation'), \
                patch.object(gui.Window, 'title_preview_original'):
            self.window = gui.Window()

    def tearDown(self):
        self.window.custom_busy = False
        self.window.custom_process = None
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def fail_stage(self, output, index=0):
        self.window.custom_busy = True
        self.window.custom_process = None
        self.window.custom_index = index
        self.window.custom_steps = [('Convert gameplay music', 'convert'), ('Register playlists', 'playlists'),
                                    ('Register metadata', 'metadata')]
        self.window.custom_stage_output = output
        with patch.object(gui.QMessageBox, 'critical') as dialog, patch.object(self.window, 'custom_next') as later:
            self.window.custom_finished(1, gui.QProcess.NormalExit)
            later.assert_not_called()
        return dialog.call_args.args[2]

    def test_invalid_name_dialog_identifies_file_requirement_and_no_changes(self):
        message = self.fail_stage('  [ERROR] Invalid artist - title filename: Almanac.mp3\n'
                                  '[STOP] 1 input error(s). Nothing converted or modified.\n')
        self.assertIn('Almanac.mp3', message)
        self.assertIn('Both Artist Name and Song Name are required', message)
        self.assertIn('no game assets were modified', message)
        self.assertFalse(self.window.custom_busy)

    def test_metadata_failure_reports_actual_reason_without_no_changes_claim(self):
        message = self.fail_stage('[ERROR] Missing mcstrings08.strtbl: fixture/path\n', index=2)
        self.assertIn('Register metadata failed', message)
        self.assertIn('Missing mcstrings08.strtbl', message)
        self.assertNotIn('no game assets were modified', message)

    def test_gui_rejects_clearing_one_field_without_renaming(self):
        folder = self.root/'Custom Music/1_Dancehall'
        folder.mkdir(parents=True)
        original = folder/'Almanac - Butterfly.mp3'
        original.write_bytes(b'original staged song')
        table = self.window.custom_table
        table.blockSignals(True)
        table.setRowCount(1)
        artist = gui.QTableWidgetItem('Almanac')
        artist.setData(gui.Qt.UserRole, str(original))
        table.setItem(0, 0, artist)
        song = gui.QTableWidgetItem('')
        song.setData(gui.Qt.UserRole, str(original))
        table.setItem(0, 1, song)
        table.blockSignals(False)
        with patch.object(gui.QMessageBox, 'warning') as warning:
            self.window.custom_rename_item(song)
        self.assertIn('Both Artist Name and Song Name', warning.call_args.args[2])
        self.assertEqual(original.read_bytes(), b'original staged song')
        self.assertFalse((folder/'Almanac.mp3').exists())

    def test_backend_rejects_single_name_before_any_conversion_or_asset_write(self):
        tools = self.root/'supporting_tools'
        tools.mkdir()
        for name in ('audio_processor.py', 'rstm_build.py', 'ps2str.exe'):
            (tools/name).touch()
        folder = self.root/'Custom Music/1_Dancehall'
        folder.mkdir(parents=True)
        (folder/'Almanac.mp3').write_bytes(b'invalid filename fixture')
        (folder/'Artist - Song.mp3').write_bytes(b'valid filename fixture')
        (self.root/'STREAMS/Music/Dancehall').mkdir(parents=True)
        assets = self.root/'ASSETS/keep.bin'
        assets.parent.mkdir()
        assets.write_bytes(b'untouched game asset')
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch.object(sys, 'argv', ['convert', str(self.root), '--yes']), \
                patch.object(converter.subprocess, 'run') as encode, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(converter.main(), 1)
            encode.assert_not_called()
        self.assertIn('Invalid artist - title filename: Almanac.mp3', output.getvalue())
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(after, before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
