"""Multi-song preview/removal tests; only temporary fixtures are modified."""
import ast
import contextlib
import io
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

PROJECT = Path(__file__).resolve().parent.parent/'UI Custom Gameplay Music Tools'
sys.path.insert(0,str(PROJECT/'supporting_tools'))
import manage_gameplay_soundtrack as manager
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication,QTableWidget,QTableWidgetItem,QAbstractItemView


class MultiRemovalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.folder=self.root/'STREAMS/Music/HipHop'
        self.folder.mkdir(parents=True)
        self.refs=['music/HipHop/'+name for name in ('A','B','C')]
        for name in ('A','B','C'):
            (self.folder/(name+'.rsm')).write_bytes(name.encode())
        self.play=self.root/'rap_race_music.play'
        self.play.write_bytes(manager.encode(self.refs,'\n',True))
        self.parsed={self.play:manager.parse(self.play,strict=True)}

    def invoke(self,action,refs,shared=False):
        parsed=dict(self.parsed)
        if shared:
            extra=self.root/'special.play'
            extra.write_bytes(manager.encode([self.refs[1]],'\n',True))
            parsed[extra]=manager.parse(extra,strict=True)
        with patch.object(manager,'collect',return_value=(parsed,{self.play:'hip-hop'},set(),set())), patch.object(manager,'stage_metadata',return_value=(contextlib.nullcontext(),[])), patch.object(manager,'install_metadata'), contextlib.redirect_stdout(io.StringIO()):
            manager.change(self.root,action,'songs',refs)

    def test_preview_changes_nothing(self):
        before=self.play.read_bytes()
        self.invoke('check',self.refs[:2])
        self.assertEqual(self.play.read_bytes(),before)
        self.assertTrue(all((self.folder/(n+'.rsm')).exists() for n in ('A','B','C')))

    def test_apply_removes_selected_only_and_deduplicates(self):
        self.invoke('apply',[self.refs[0],self.refs[1],self.refs[0]])
        self.assertEqual(manager.parse(self.play,strict=True)[2],[self.refs[2]])
        self.assertFalse((self.folder/'A.rsm').exists())
        self.assertFalse((self.folder/'B.rsm').exists())
        self.assertTrue((self.folder/'C.rsm').exists())

    def test_shared_audio_is_preserved(self):
        self.invoke('apply',self.refs[:2],shared=True)
        self.assertFalse((self.folder/'A.rsm').exists())
        self.assertTrue((self.folder/'B.rsm').exists())

    def test_invalid_selection_prevents_all_changes(self):
        before=self.play.read_bytes()
        with self.assertRaises(ValueError):
            self.invoke('apply',[self.refs[0],'music/HipHop/Unknown'])
        self.assertEqual(self.play.read_bytes(),before)
        self.assertTrue((self.folder/'A.rsm').exists())

    def test_cli_multiple_and_legacy_single_reference(self):
        for args,expected in [(['check','songs',*self.refs[:2]],self.refs[:2]),(['check','song',self.refs[0]],self.refs[0]),(['check','genre','hip-hop'],'hip-hop'),(['check','all'],None)]:
            with patch.object(sys,'argv',['manager',*args,'--root',str(self.root)]),patch.object(manager,'change') as call:
                manager.main()
                self.assertEqual(call.call_args.args[-1],expected)

    def test_gui_collects_selected_rows_only(self):
        app=QApplication.instance() or QApplication([])
        tree=ast.parse((PROJECT/'gui/main.py').read_text(encoding='utf-8-sig'))
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Window')
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='preview_soundtrack')
        scope={'Qt':Qt}
        exec(compile(ast.Module(body=[method],type_ignores=[]),'preview','exec'),scope)
        table=QTableWidget(3,2)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        for row,ref in enumerate(self.refs):
            item=QTableWidgetItem(ref)
            item.setData(Qt.UserRole,ref)
            table.setItem(row,0,item)
        from PySide6.QtCore import QItemSelectionModel
        for row in (0,2):
            table.selectionModel().select(table.model().index(row,0),QItemSelectionModel.Select|QItemSelectionModel.Rows)
        state=SimpleNamespace(soundtrack_ready=lambda:True,song_table=table,soundtrack_progress=Mock(),soundtrack_state=Mock(),log=Mock(),start_soundtrack_process=Mock(),root=self.root)
        scope['preview_soundtrack'](state,'song')
        self.assertEqual(state.start_soundtrack_process.call_args.args[1],['check','songs',self.refs[0],self.refs[2]])
        self.assertNotIn(self.refs[1],state.soundtrack_target[1])


if __name__=='__main__':
    unittest.main(verbosity=2)
