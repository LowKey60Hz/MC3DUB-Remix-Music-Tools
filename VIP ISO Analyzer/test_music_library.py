"""Music-library archives: temporary round trips, conflict handling and rollback."""
import hashlib
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

GUI = Path(__file__).resolve().parent.parent/'UI Custom Gameplay Music Tools/gui'
sys.path.insert(0, str(GUI))
import music_library as library


class LibraryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.source = self.base/'original project'
        self.target = self.base/'restored project'
        self.source.mkdir(); self.target.mkdir()
        self.archive = self.base/'My Music Library.zip'
        for index, folder in enumerate(library.FOLDERS):
            directory = self.source/folder
            directory.mkdir(parents=True)
            (directory/f'Artist {index} - Song {index}.mp3').write_bytes(('audio '+str(index)).encode())

    def snapshot(self, folder):
        return {p.relative_to(folder): p.read_bytes() for p in folder.rglob('*') if p.is_file()}

    def test_round_trip_preserves_names_categories_audio_and_assignments(self):
        state = {'loading_mode': 'M', 'loading_slots': ['Artist 9 - Song 9.mp3']+['']*17}
        result = library.export_library(self.source, self.archive, state)
        self.assertEqual(result['files'], 10)
        self.assertEqual(result['cleared'], 0)
        imported = library.import_library(self.target, self.archive)
        self.assertEqual(imported['session'], state)
        self.assertEqual(imported['imported'], 10)
        self.assertEqual(self.snapshot(self.source), self.snapshot(self.target))

    def test_verified_export_clears_only_exported_audio(self):
        untouched = self.source/'ASSETS/keep.dat'
        untouched.parent.mkdir(); untouched.write_bytes(b'game archive')
        (self.source/library.FOLDERS[0]/'.gitkeep').touch()
        result = library.export_library(self.source, self.archive, clear_exported=True)
        self.assertEqual(result['cleared'], 10)
        self.assertEqual(untouched.read_bytes(), b'game archive')
        self.assertTrue((self.source/library.FOLDERS[0]/'.gitkeep').exists())
        self.assertFalse(list(self.source.rglob('*.mp3')))
        self.assertEqual(library.import_library(self.target, self.archive)['imported'], 10)

    def test_clear_failure_restores_removed_sources_and_retains_export(self):
        before = self.snapshot(self.source)
        original = Path.unlink
        calls = 0
        def unlink(path, *args, **kwargs):
            nonlocal calls
            if path.suffix == '.mp3':
                calls += 1
                if calls == 2:
                    raise PermissionError('audio is open')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'unlink', unlink):
            result = library.export_library(self.source, self.archive, clear_exported=True)
        self.assertIn('could not be cleared', result['clear_error'])
        self.assertEqual(self.snapshot(self.source), before)
        self.assertTrue(self.archive.is_file())

    def test_duplicate_review_and_per_file_decisions(self):
        library.export_library(self.source, self.archive)
        library.import_library(self.target, self.archive)
        first = sorted(self.snapshot(self.target), key=str)[0]
        (self.target/first).write_bytes(b'different existing audio')
        duplicates = library.inspect_duplicates(self.target, self.archive)['duplicates']
        self.assertEqual(len(duplicates), 10)
        self.assertEqual(sum(not item['identical'] for item in duplicates), 1)
        result = library.import_library(self.target, self.archive, decisions={first.as_posix().casefold(): 'skip'})
        self.assertEqual(result['skipped'], 1)
        self.assertEqual((self.target/first).read_bytes(), b'different existing audio')
        result = library.import_library(self.target, self.archive, decisions={first.as_posix().casefold(): 'replace'})
        self.assertEqual(result['imported'], 1)
        self.assertEqual(self.snapshot(self.source), self.snapshot(self.target))

    def malicious(self, name, payload=b'audio', wrong_hash=False):
        record = {'path': name, 'size': len(payload),
                  'sha256': '0'*64 if wrong_hash else hashlib.sha256(payload).hexdigest()}
        data = {'format': 'MC3 Music Library', 'version': 1, 'files': [record]}
        with zipfile.ZipFile(self.archive, 'w') as archive:
            archive.writestr(library.MANIFEST, json.dumps(data))
            archive.writestr(name, payload)

    def test_path_traversal_and_game_resource_paths_are_rejected(self):
        for name in ('../escape.mp3', 'ASSETS/music.mp3', 'Custom Music/2_Win/../escape.mp3',
                     'Loading Music/CON.mp3', 'Loading Music/audio.exe'):
            self.malicious(name)
            with self.assertRaises(ValueError):
                library.import_library(self.target, self.archive)
            self.assertEqual(self.snapshot(self.target), {})

    def test_corruption_is_rejected_before_any_import(self):
        self.malicious('Loading Music/Artist - Song.mp3', wrong_hash=True)
        with self.assertRaisesRegex(ValueError, 'Corrupt'):
            library.import_library(self.target, self.archive)
        self.assertEqual(self.snapshot(self.target), {})

    def test_import_failure_rolls_back_replaced_audio(self):
        library.export_library(self.source, self.archive)
        library.import_library(self.target, self.archive)
        for path in self.target.rglob('*.mp3'):
            path.write_bytes(b'keep this existing audio')
        before = self.snapshot(self.target)
        original = shutil.copyfile
        count = 0
        def copy(source, destination, *args, **kwargs):
            nonlocal count
            if Path(destination).is_relative_to(self.target):
                count += 1
                if count == 2:
                    raise OSError('simulated disk failure')
            return original(source, destination, *args, **kwargs)
        with patch.object(library.shutil, 'copyfile', side_effect=copy):
            with self.assertRaises(OSError):
                library.import_library(self.target, self.archive, replace=True)
        self.assertEqual(self.snapshot(self.target), before)

    def test_failed_export_does_not_clear_sources_or_replace_existing_archive(self):
        before = self.snapshot(self.source)
        self.archive.write_bytes(b'existing backup')
        with self.assertRaises(FileExistsError):
            library.export_library(self.source, self.archive, clear_exported=True)
        self.assertEqual(self.archive.read_bytes(), b'existing backup')
        self.assertEqual(self.snapshot(self.source), before)

    def test_loading_and_theme_are_explicitly_archived_and_verified_before_clear(self):
        result = library.export_library(self.source, self.archive, clear_exported=True)
        self.assertEqual(result['category_counts']['Loading Music'], 1)
        self.assertEqual(result['category_counts']['Custom Music/3_Theme Song'], 1)
        with zipfile.ZipFile(self.archive) as archive:
            self.assertIn('Loading Music/', archive.namelist())
            self.assertIn('Custom Music/3_Theme Song/', archive.namelist())
            self.assertEqual(archive.read('Loading Music/Artist 9 - Song 9.mp3'), b'audio 9')
            self.assertEqual(archive.read('Custom Music/3_Theme Song/Artist 8 - Song 8.mp3'), b'audio 8')
        self.assertFalse(list((self.source/'Loading Music').glob('*.mp3')))
        self.assertFalse(list((self.source/'Custom Music/3_Theme Song').glob('*.mp3')))

    def test_missing_ui_staged_loading_file_blocks_export_without_clearing(self):
        before = self.snapshot(self.source)
        with self.assertRaisesRegex(ValueError, 'missing from disk'):
            library.export_library(self.source, self.archive, clear_exported=True,
                                   expected_paths=['Loading Music/Missing - Track.wav'])
        self.assertFalse(self.archive.exists())
        self.assertEqual(self.snapshot(self.source), before)


class LibraryUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import main as gui
        cls.gui = gui
        cls.app = gui.QApplication.instance() or gui.QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        with patch.object(self.gui, 'ROOT', self.root), patch.object(self.gui.Window, 'start_auto_validation'), \
                patch.object(self.gui.Window, 'title_preview_original'):
            self.window = self.gui.Window()

    def tearDown(self):
        self.app.processEvents()
        self.window.close(); self.window.deleteLater()
        self.app.processEvents(); self.temp.cleanup()

    def test_menu_is_above_about_and_clearing_is_opt_in(self):
        names = [button.text() for button in self.window.nav]
        self.assertEqual(names[-2:], ['Export/Import Music', 'About'])
        self.assertEqual(self.window.stack.count(), len(names))
        self.assertFalse(self.window.library_clear_after_export.isChecked())

    def test_skip_all_resolves_duplicates_before_import_starts(self):
        gui = self.gui
        review = {'archive': 'library.zip', 'duplicates': [
            {'path': 'Loading Music/Artist - Song.mp3', 'identical': False},
            {'path': 'Custom Music/2_Win/Artist - Song.mp3', 'identical': True}]}
        with patch.object(gui.QMessageBox, 'exec', return_value=gui.QMessageBox.NoToAll) as dialog, \
                patch.object(self.window, 'music_library_start_worker') as start:
            self.window.music_library_finished('review', review)
        self.assertEqual(dialog.call_count, 1)
        self.assertEqual(start.call_args.kwargs['decisions'],
                         {item['path'].casefold(): 'skip' for item in review['duplicates']})

    def test_real_export_worker_finishes_without_blocking_or_clearing_sources(self):
        from PySide6.QtCore import QEventLoop, QTimer
        source = self.root/'Custom Music/1_Dancehall/Artist - Song.mp3'
        source.parent.mkdir(parents=True); source.write_bytes(b'staged audio')
        archive = self.root/'backup.zip'
        loop = QEventLoop()
        poll = QTimer(); poll.timeout.connect(lambda: loop.quit() if not self.window.library_busy else None)
        deadline = QTimer(); deadline.setSingleShot(True); deadline.timeout.connect(loop.quit)
        with patch.object(self.gui.QMessageBox, 'information'), patch.object(self.gui.QMessageBox, 'critical') as error:
            self.window.music_library_start_worker('export', str(archive))
            poll.start(10); deadline.start(5000); loop.exec(); poll.stop(); deadline.stop()
            error.assert_not_called()
        self.assertFalse(self.window.library_busy)
        self.assertTrue(archive.is_file())
        self.assertTrue(source.is_file())
        self.assertIn('Exported and verified 1', self.window.library_status.text())

    def test_real_import_worker_refreshes_staging_and_loading_selection(self):
        from PySide6.QtCore import QEventLoop, QTimer
        source_root = self.root/'export source'
        source = source_root/'Loading Music/Artist - Loading.wav'
        source.parent.mkdir(parents=True); source.write_bytes(b'loading audio')
        archive = self.root/'session.zip'
        state = {'loading_mode': 'M', 'loading_slots': ['Artist - Loading.wav']+['']*17}
        library.export_library(source_root, archive, state)
        loop = QEventLoop()
        poll = QTimer(); poll.timeout.connect(lambda: loop.quit() if not self.window.library_busy else None)
        deadline = QTimer(); deadline.setSingleShot(True); deadline.timeout.connect(loop.quit)
        with patch.object(self.gui.QMessageBox, 'information'), patch.object(self.gui.QMessageBox, 'critical') as error:
            self.window.music_library_start_worker('import', str(archive))
            poll.start(10); deadline.start(5000); loop.exec(); poll.stop(); deadline.stop()
            error.assert_not_called()
        self.assertFalse(self.window.library_busy)
        self.assertEqual(self.window.loading_table.rowCount(), 1)
        self.assertEqual(self.window.loading_slot_table.cellWidget(0, 1).currentData(), 'Artist - Loading.wav')
        self.assertIn('Imported 1', self.window.library_status.text())

    def test_export_clear_refreshes_loading_and_staged_theme_together(self):
        from PySide6.QtCore import QEventLoop, QTimer
        for folder in ('Loading Music', 'Custom Music/3_Theme Song'):
            source = self.root/folder/'Artist - Track.wav'
            source.parent.mkdir(parents=True); source.write_bytes(b'example wav audio')
        self.window.title_refresh(); self.window.loading_refresh()
        self.assertIn('Artist - Track.wav', self.window.title_file_label.text())
        self.assertEqual(self.window.loading_table.rowCount(), 1)
        self.window.library_clear_after_export.setChecked(True)
        archive = self.root/'MC3_Custom_Music_Library.zip'
        loop = QEventLoop()
        poll = QTimer(); poll.timeout.connect(lambda: loop.quit() if not self.window.library_busy else None)
        deadline = QTimer(); deadline.setSingleShot(True); deadline.timeout.connect(loop.quit)
        with patch.object(self.gui.QMessageBox, 'information'), patch.object(self.gui.QMessageBox, 'critical') as error:
            self.window.music_library_start_worker('export', str(archive))
            poll.start(10); deadline.start(5000); loop.exec(); poll.stop(); deadline.stop()
            error.assert_not_called()
        self.assertFalse(self.window.library_busy)
        self.assertEqual(self.window.loading_table.rowCount(), 0)
        self.assertNotIn('Artist - Track.wav', self.window.title_file_label.text())
        self.assertIn('Loading Music: 1', self.window.library_status.text())
        self.assertIn('Title theme: 1', self.window.library_status.text())
        with zipfile.ZipFile(archive) as saved:
            for folder in ('Loading Music', 'Custom Music/3_Theme Song'):
                self.assertEqual(saved.read(folder+'/Artist - Track.wav'), b'example wav audio')


if __name__ == '__main__':
    unittest.main(verbosity=2)
