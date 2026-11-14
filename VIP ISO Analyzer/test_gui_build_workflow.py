"""Offscreen GUI sequencing test: no compilation, prompts or ISO writes."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys
import unittest
import tempfile
from unittest.mock import patch
from test_workspace_cleanup import fixture

ROOT = Path(__file__).resolve().parent.parent / 'UI Custom Gameplay Music Tools'
sys.path.insert(0, str(ROOT / 'gui'))
import main as gui


class GuiBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = gui.QApplication.instance() or gui.QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root, iso = fixture(self.directory.name)
        names = ('dave.py','hash_build.py','MC3_ISO_Builder.py','MC3_ISO_Builder_VIP.py',
                 'MC3_ASSETS_Builder_V11A.py','MC3_ISO_Builder_V11A.py','vip_capacity.py','archive_build_gate.py')
        for name in names:
            (self.root / 'supporting_tools' / name).write_text('# fixture')
        values = {'MC3_PROFILE.txt':'vip','MC3_SOURCE_CLASS.txt':'VERIFIED_VIP_V11A_REFERENCE',
                  'MC3_SOURCE_ISO.txt':str(iso),'MC3_SOURCE_SHA256.txt':'fixture',
                  'ASSETS.DAT':'fixture','STREAMS.DAT':'fixture','STREAMS.LST':'fixture'}
        for name,value in values.items():
            (self.root / 'ISO_FILES' / name).write_text(value)

    def tearDown(self):
        self.directory.cleanup()

    def test_v11a_enabled_and_gate_precedes_copy(self):
        with patch.object(gui, 'ROOT', self.root), patch.object(gui.Window, 'start_auto_validation'), patch.object(gui.Window, 'title_preview_original'):
            window = gui.Window()
        try:
            window.profile_verified = True
            window.update_build_controls()
            self.assertTrue(window.build_button.isEnabled())
            self.assertIn('v1.1-A', window.build_profile_label.text())
            with patch.object(gui.QMessageBox, 'question', return_value=gui.QMessageBox.Yes), \
                 patch.object(gui.QMessageBox, 'warning') as warning, patch.object(gui.Window, 'start_build_step') as start:
                window.begin_build()
                warning.assert_not_called()
                start.assert_called_once()
            labels = [step[0] for step in window.build_steps]
            self.assertLess(labels.index('Compile STREAMS.DAT'), labels.index('Check compiled archive capacity and record ranges'))
            self.assertLess(labels.index('Check compiled archive capacity and record ranges'), labels.index('Build and verify pending ISO'))
            self.assertTrue(window.build_steps[1][1].endswith('MC3_ASSETS_Builder_V11A.py'))
            self.assertIn('vip-v11a', window.build_steps[-1][2])
            self.assertEqual(window.build_progress.maximum(), len(window.build_steps))
            index = labels.index('Check compiled archive capacity and record ranges')
            window.build_index = index
            window.build_error_tail = 'ASSETS blocked: high-offset resource\n'
            with patch.object(gui.Window, 'build_failed') as failed, patch.object(gui.Window, 'start_build_step') as next_step:
                window.build_step_finished(1, gui.QProcess.NormalExit)
                failed.assert_called_once()
                self.assertIn('ASSETS blocked: high-offset resource', failed.call_args.args[0])
                next_step.assert_not_called()
                self.assertEqual(window.build_index, index)
            with patch.object(gui.Window, 'build_output_ready', side_effect=lambda: setattr(window, 'build_busy', False)), \
                 patch.object(gui.Window, 'start_build_step') as next_step:
                window.build_step_finished(0, gui.QProcess.NormalExit)
                next_step.assert_not_called()
                self.assertEqual(window.build_index, index)
        finally:
            window.build_busy = False
            window.close()


if __name__ == '__main__':
    unittest.main()
