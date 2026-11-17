"""Offscreen restart tests; only temporary fixture folders may be cleared."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys
import tempfile
import unittest
import textwrap
from unittest.mock import patch
from test_workspace_cleanup import fixture, cleanup, GUI

sys.path.insert(0, str(GUI))
import main as gui
from PySide6.QtCore import QEventLoop, QTimer


class RestartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = gui.QApplication.instance() or gui.QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root, self.iso = fixture(self.directory.name)
        for name in ('MC3_ISO_Extractor.py','MC3_PS2_Streams.lst','dave.py','hash_build.py'):
            (self.root / 'supporting_tools' / name).write_text('# fixture')
        with patch.object(gui.Window, 'start_auto_validation'), patch.object(gui.Window, 'title_preview_original'):
            self.window = gui.Window()
        self.window.root = self.root
        self.previous = Path(self.directory.name) / 'previous.iso'
        self.previous.write_bytes(b'previous source')
        self.window.iso_path = self.previous
        self.window.selected_iso_label.setText(str(self.previous))

    def tearDown(self):
        self.window.extraction_busy = False
        self.window.build_busy = False
        self.window.validator = None
        self.window.close()
        self.directory.cleanup()

    def select(self, reply):
        with patch.object(gui.QFileDialog, 'getOpenFileName', return_value=(str(self.iso), '')), \
             patch.object(gui.QMessageBox, 'question', return_value=reply), patch.object(gui.Window, 'begin_extraction') as begin:
            self.window.select_iso()
            if reply == gui.QMessageBox.Yes:
                begin.assert_called_once()
            else:
                begin.assert_not_called()

    def begin(self):
        self.select(gui.QMessageBox.Yes)
        with patch.object(gui.QMessageBox, 'question') as question, patch.object(gui.Window, 'next_extraction_step'):
            self.window.begin_extraction()
            question.assert_not_called()

    def test_no_keeps_selection_and_all_workspace_files(self):
        self.select(gui.QMessageBox.No)
        self.assertEqual(self.window.iso_path, self.previous)
        self.assertEqual(self.window.selected_iso_label.text(), str(self.previous))
        self.assertIsNone(self.window.workspace_reset_authorization)
        self.assertTrue(all((self.root / name / 'nested/old.json').is_file() for name in cleanup.WORKSPACE_FOLDERS))

    def test_logs_alone_do_not_report_a_loaded_workspace(self):
        with patch('sys.stdout'):
            cleanup.clear_workspace(self.root, self.iso)
        log = self.root/'support_logs/old_gui.stderr.log'
        log.write_text('previous extraction failed')
        with patch.object(gui.QFileDialog, 'getOpenFileName', return_value=(str(self.iso), '')), \
                patch.object(gui.QMessageBox, 'question') as question, \
                patch.object(gui.Window, 'begin_extraction') as begin:
            self.window.select_iso()
            question.assert_not_called()
            begin.assert_not_called()
        self.assertEqual(self.window.iso_path, self.iso)
        self.assertIsNone(self.window.workspace_reset_authorization)
        self.assertEqual(log.read_text(), 'previous extraction failed')
        with patch.object(gui.QMessageBox, 'question', return_value=gui.QMessageBox.Yes) as question, \
                patch.object(gui.Window, 'next_extraction_step'):
            self.window.begin_extraction()
        self.assertEqual(question.call_args.args[1], 'Confirm ISO extraction')
        self.assertNotIn('Clear previous ISO workspace', [step[0] for step in self.window.extraction_steps])

    def test_partial_game_data_still_requires_restart_confirmation(self):
        with patch('sys.stdout'):
            cleanup.clear_workspace(self.root, self.iso)
        (self.root/'ISO_FILES').mkdir()
        with patch.object(gui.QMessageBox, 'question', return_value=gui.QMessageBox.No) as question:
            self.assertFalse(self.window.confirm_workspace_restart(self.iso))
        self.assertEqual(question.call_args.args[1], 'ISO Workspace Already Loaded')

    def test_yes_defers_cleanup_until_both_preflight_checks_pass(self):
        self.begin()
        labels = [s[0] for s in self.window.extraction_steps]
        self.assertEqual(labels[:4], ['ISO preflight','Profile inspection','Clear previous ISO workspace','ISO archive extraction'])
        self.assertTrue(all((self.root / name / 'nested/old.json').is_file() for name in cleanup.WORKSPACE_FOLDERS))
        self.assertFalse(self.window.extraction_stage.exists())

    def test_failed_preflight_preserves_current_workspace(self):
        self.begin()
        with patch.object(gui.QMessageBox, 'critical'), patch.object(gui.Window, 'next_extraction_step') as next_step:
            self.window.extraction_finished(2, gui.QProcess.NormalExit)
            next_step.assert_not_called()
        self.assertFalse(self.window.extraction_busy)
        self.assertIsNone(self.window.workspace_reset_authorization)
        self.assertTrue(all((self.root / name / 'nested/old.json').is_file() for name in cleanup.WORKSPACE_FOLDERS))

    def test_successful_cleanup_clears_views_and_advances_to_archive_extraction(self):
        self.begin()
        self.window.step_index = 2
        self.window.extraction_cleanup_started = True
        self.window.soundtrack_songs = [{'stale': True}]
        cleanup.clear_workspace(self.root, self.iso)
        with patch.object(gui.Window, 'next_extraction_step') as next_step:
            self.window.extraction_finished(0, gui.QProcess.NormalExit)
            next_step.assert_called_once()
        self.assertEqual(self.window.step_index, 3)
        self.assertEqual(self.window.soundtrack_songs, [])
        self.assertFalse(self.window.profile_verified)
        self.assertIsNone(self.window.workspace_reset_authorization)
        self.assertTrue(all(self.window.loading_slot_table.cellWidget(i, 1).currentIndex() == 0 for i in range(18)))

    def test_cleanup_failure_never_starts_archive_extraction(self):
        self.begin()
        self.window.step_index = 2
        self.window.extraction_cleanup_started = True
        self.window.extraction_error_tail = 'Cleanup stopped: file in use\n'
        with patch.object(gui.QMessageBox, 'critical') as critical, patch.object(gui.Window, 'next_extraction_step') as next_step:
            self.window.extraction_finished(1, gui.QProcess.NormalExit)
            next_step.assert_not_called()
            self.assertIn('Cleanup stopped: file in use', critical.call_args.args[-1])
        self.assertFalse(self.window.extraction_busy)
        self.assertEqual(self.window.step_index, 2)

    def test_busy_operation_blocks_selection(self):
        self.window.build_busy = True
        with patch.object(gui.QFileDialog, 'getOpenFileName') as picker, patch.object(gui.QMessageBox, 'information'):
            self.window.select_iso()
            picker.assert_not_called()

    def test_source_inside_workspace_is_rejected_without_confirmation(self):
        candidate = self.root / 'ISO_FILES/new.iso'
        candidate.write_bytes(b'keep source')
        with patch.object(gui.QFileDialog, 'getOpenFileName', return_value=(str(candidate), '')), \
             patch.object(gui.QMessageBox, 'question') as question, patch.object(gui.QMessageBox, 'warning') as warning:
            self.window.select_iso()
            question.assert_not_called()
            warning.assert_called_once()
        self.assertEqual(candidate.read_bytes(), b'keep source')

    def test_staged_workspace_activation_uses_dynamic_step_position(self):
        self.begin()
        cleanup.clear_workspace(self.root, self.iso)
        stage = self.window.extraction_stage
        stage.mkdir()
        for name in ('ASSETS.DAT','STREAMS.DAT','STREAMS.LST','MC3_PROFILE.txt'):
            (stage / name).write_text('fixture')
        self.window.step_index = next(i for i, step in enumerate(self.window.extraction_steps) if step[0] == 'Decompile ASSETS')
        with patch.object(gui.QProcess, 'start'):
            self.window.next_extraction_step()
        self.assertTrue(self.window.extraction_workspace_activated)
        self.assertFalse(stage.exists())
        self.assertTrue((self.root / 'ISO_FILES/ASSETS.DAT').is_file())

    def test_changed_selection_invalidates_cleanup_authorization(self):
        self.begin()
        self.window.step_index = 2
        self.window.iso_path = self.previous
        with patch.object(gui.QMessageBox, 'critical'), patch.object(gui.QProcess, 'start') as start:
            self.window.next_extraction_step()
            start.assert_not_called()
        self.assertFalse(self.window.extraction_busy)
        self.assertTrue(all((self.root / name / 'nested/old.json').is_file() for name in cleanup.WORKSPACE_FOLDERS))

    def test_background_cleanup_and_full_extraction_chain_on_miniature_fixture(self):
        extractor = '''
            import argparse
            from pathlib import Path
            p=argparse.ArgumentParser()
            p.add_argument('iso')
            p.add_argument('--output-dir',type=Path,required=True)
            p.add_argument('--production',action='store_true')
            p.add_argument('--extract',action='store_true')
            p.add_argument('--yes',action='store_true')
            a=p.parse_args()
            if a.extract:
                a.output_dir.mkdir()
                for name in ('ASSETS.DAT','STREAMS.DAT'):
                    (a.output_dir/name).write_bytes(b'new archive fixture')
        '''
        profile = '''
            import sys
            from pathlib import Path
            if sys.argv[1]=='record':
                out=Path(sys.argv[3])
                for name,text in {'MC3_PROFILE.txt':'vip',
                    'MC3_SOURCE_CLASS.txt':'VERIFIED_VIP_V11A_REFERENCE',
                    'MC3_SOURCE_ISO.txt':sys.argv[2],
                    'MC3_SOURCE_SHA256.txt':'fixture',
                    'STREAMS.LST':'music/song.rsm'}.items():
                    (out/name).write_text(text)
        '''
        decompile = '''
            import sys
            from pathlib import Path
            out=Path(sys.argv[sys.argv.index('-o')+1])
            out.mkdir()
            (out/'fresh-resource.bin').write_bytes(b'fresh resource')
        '''
        tools = self.root / 'supporting_tools'
        for name, script in (('MC3_ISO_Extractor.py',extractor),('MC3_Profile_108S.py',profile),
                             ('dave.py',decompile),('hash_build.py',decompile)):
            (tools / name).write_text(textwrap.dedent(script), encoding='utf-8')
        loop = QEventLoop()
        outcome = []
        def complete(*args):
            outcome.append('success')
            loop.quit()
        def fail(*args):
            outcome.append(str(args[-1]))
            loop.quit()
        with patch.object(gui.QFileDialog, 'getOpenFileName', return_value=(str(self.iso), '')), \
             patch.object(gui.QMessageBox, 'question', return_value=gui.QMessageBox.Yes), \
             patch.object(gui.QMessageBox, 'information', side_effect=complete), \
             patch.object(gui.QMessageBox, 'critical', side_effect=fail), \
             patch.object(gui.Window, 'start_auto_validation'):
            self.window.select_iso()
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(loop.quit)
            timer.start(15000)
            loop.exec()
            timer.stop()
        if self.window.extractor and self.window.extractor.state() != gui.QProcess.NotRunning:
            self.window.extractor.kill()
            self.window.extractor.waitForFinished(3000)
        self.assertEqual(outcome, ['success'], self.window.log_box.toPlainText())
        self.assertTrue((self.root / 'ASSETS/fresh-resource.bin').is_file())
        self.assertTrue((self.root / 'STREAMS/fresh-resource.bin').is_file())
        self.assertTrue((self.root / 'ISO_FILES/MC3_PROFILE.txt').is_file())
        self.assertTrue(all(not (self.root / name / 'nested/old.json').exists() for name in cleanup.WORKSPACE_FOLDERS))
        self.assertEqual(list((self.root / 'support_logs').iterdir()), [])
        self.assertFalse(self.window.extraction_stage.exists())
        self.assertEqual((self.root / 'MC3_Modified_VIP.iso').read_bytes(), b'keep output')
        self.assertEqual(self.iso.read_bytes(), b'keep original')

    def test_switching_project_cancels_pending_reset_authorization(self):
        self.select(gui.QMessageBox.Yes)
        other = self.root.parent / 'other project'
        (other / 'supporting_tools').mkdir(parents=True)
        (other / 'supporting_tools/MC3_Profile_108S.py').write_text('# fixture')
        with patch.object(gui.QFileDialog, 'getExistingDirectory', return_value=str(other)), \
             patch.object(gui.Window, 'title_preview_original'), patch.object(gui.Window, 'start_auto_validation'):
            self.window.select_root()
        self.assertIsNone(self.window.workspace_reset_authorization)
        self.assertTrue(all((self.root / name / 'nested/old.json').is_file() for name in cleanup.WORKSPACE_FOLDERS))


if __name__ == '__main__':
    unittest.main()
