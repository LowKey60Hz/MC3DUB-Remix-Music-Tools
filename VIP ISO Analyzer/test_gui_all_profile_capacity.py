"""Offscreen profile routing, visible capacity failures and persistent logs."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from test_workspace_cleanup import fixture, GUI
from test_vip_capacity import capacity
sys.path.insert(0,str(GUI))
import main as gui
from PySide6.QtCore import QByteArray


class ProfileGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = gui.QApplication.instance() or gui.QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root,self.iso = fixture(self.directory.name)
        names = ('dave.py','hash_build.py','MC3_ISO_Builder.py','MC3_ISO_Builder_Retail.py','MC3_ISO_Builder_VIP.py',
                 'MC3_ASSETS_Builder_V11A.py','MC3_ISO_Builder_V11A.py','vip_capacity.py','archive_build_gate.py','iso_preservation.py')
        for name in names:
            (self.root/'supporting_tools'/name).write_text('# fixture')
        for name in ('ASSETS.DAT','STREAMS.DAT','STREAMS.LST'):
            (self.root/'ISO_FILES'/name).write_bytes(b'fixture')
        with patch.object(gui.Window,'start_auto_validation'),patch.object(gui.Window,'title_preview_original'):
            self.window=gui.Window()
        self.window.root=self.root

    def tearDown(self):
        self.window.close_build_log()
        self.window.build_busy=False
        self.window.close()
        self.directory.cleanup()

    def bind(self,profile):
        kind={'retail':'RETAIL_CUSTOM_WITH_MANIFEST','retail-expanded':'VERIFIED_RETAIL_REFERENCE','vip':'VIP_CUSTOM_WITH_MANIFEST',
              'vip-expanded':'VERIFIED_VIP_REFERENCE','vip-v11a':'VERIFIED_VIP_V11A_REFERENCE'}[profile]
        values={'MC3_PROFILE.txt':'retail' if profile.startswith('retail') else 'vip','MC3_SOURCE_CLASS.txt':kind,
                'MC3_SOURCE_ISO.txt':str(self.iso),'MC3_SOURCE_SHA256.txt':capacity.CAPACITY_PROFILES[profile]['sha256']}
        for name,value in values.items():
            (self.root/'ISO_FILES'/name).write_text(value)
        self.window.profile_verified=True
        self.window.update_build_controls()

    def test_each_gui_path_selects_its_own_capacity_profile(self):
        for profile in capacity.CAPACITY_PROFILES:
            with self.subTest(profile=profile):
                self.window.build_busy=False
                self.bind(profile)
                with patch.object(gui.QMessageBox,'question',return_value=gui.QMessageBox.Yes),patch.object(gui.Window,'start_build_step'):
                    self.window.begin_build()
                step=next(step for step in self.window.build_steps if step[0]=='Check compiled archive capacity and record ranges')
                args=step[2]
                self.assertEqual(args[args.index('--profile')+1],profile)
                self.assertIn('--report',args)
                engine_profile={'vip-expanded':'vip','retail-expanded':'retail'}.get(profile,profile)
                self.assertIn(engine_profile,self.window.build_steps[-1][2])
                self.assertEqual('--expand-v10' in self.window.build_steps[-1][2], profile=='vip-expanded')
                self.assertEqual('--relocate-archives' in self.window.build_steps[-1][2], profile=='retail-expanded')

    def test_capacity_failure_is_visible_logged_and_stops_before_copy(self):
        self.bind('vip')
        self.window.build_steps=[('Check compiled archive capacity and record ranges','fixture.py',[])]
        self.window.build_index=0
        self.window.build_busy=True
        self.window.build_profile='vip'
        path=self.root/'support_logs/build_capacity_latest.json'
        self.window.build_capacity_report_path=path
        result=capacity.assess(1805909737,1087309824,layout_profile='vip')
        path.write_text(json.dumps(result))
        with patch.object(gui.QProcess,'start'):
            self.window.start_build_step()
        error=b'VIP v1.0-C capacity exceeded by 130830336 bytes (124.77 MiB).\n'
        with patch.object(self.window.build_process,'readAllStandardOutput',return_value=QByteArray(error)), \
             patch.object(gui.QMessageBox,'critical') as dialog,patch.object(gui.Window,'start_build_step') as next_step:
            self.window.build_step_finished(1,gui.QProcess.NormalExit)
            next_step.assert_not_called()
            self.assertIn('capacity exceeded',dialog.call_args.args[-1])
        text=(self.root/'support_logs/last_build.log').read_text()
        self.assertIn('Check compiled archive capacity and record ranges',text)
        self.assertIn('capacity exceeded',text)
        self.assertIn('process exit code 1',text)
        self.assertIn('VIP v1.0-C',self.window.build_capacity_label.text())
        self.assertIn('Over capacity',self.window.build_capacity_label.text())
        self.assertFalse(self.window.build_busy)


if __name__=='__main__':
    unittest.main()
