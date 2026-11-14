"""Boundary and no-partial-write checks using temporary workspaces only."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

PROJECT = Path(__file__).resolve().parent.parent / 'UI Custom Gameplay Music Tools'
sys.path.insert(0, str(PROJECT / 'supporting_tools'))
import convert_loading_raw as converter
import customize_loading_screens as batch

spec = importlib.util.spec_from_file_location('loading_adapter_test', PROJECT/'gui/loading_apply.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


class LoadingLimitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='MC3_loading_limit_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.music = self.root/'Loading Music'
        self.music.mkdir()
        self.target = self.root/'ASSETS/audio/loadscreen'
        self.target.mkdir(parents=True)
        for slot in range(1,19):
            (self.target/f'{slot}.raw').write_bytes(b'original'+bytes([slot]))
        (self.root/'supporting_tools').mkdir()
        shutil.copyfile(PROJECT/'supporting_tools/convert_loading_raw.py', self.root/'supporting_tools/convert_loading_raw.py')

    def wav(self, name, frames, rate=24000):
        path = self.music/name
        with wave.open(str(path),'wb') as audio:
            audio.setparams((1,2,rate,0,'NONE','not compressed'))
            audio.writeframes(b'\0\0'*frames)
        return path

    def snapshot(self):
        return {p.name:p.read_bytes() for p in self.target.iterdir()}

    def config(self, entries):
        path = self.root/'assignments.json'
        path.write_text(json.dumps({'assignments':entries}))
        return path

    def test_exact_output_cap_and_rejection_preserves_destination(self):
        source = self.wav('accepted.wav',227840)
        output = self.root/'output.raw'
        converter.convert(source,output)
        self.assertEqual(output.stat().st_size,455680)
        output.write_bytes(b'keep-existing-output')
        with self.assertRaisesRegex(ValueError,'455,680'):
            converter.convert(self.wav('too_long.wav',227841),output)
        self.assertEqual(output.read_bytes(),b'keep-existing-output')
        self.assertFalse(output.with_name('output.raw.tmp').exists())

    def test_resampling_boundary(self):
        output = self.root/'resampled.raw'
        converter.convert(self.wav('accepted48.wav',455680,48000),output)
        self.assertEqual(output.stat().st_size,455680)
        output.unlink()
        with self.assertRaises(ValueError):
            converter.convert(self.wav('rejected48.wav',455681,48000),output)
        self.assertFalse(output.exists())

    def test_gui_accepts_cap(self):
        source = self.wav('accepted.wav',227840)
        before = self.snapshot()
        adapter.main(self.root,self.config([{'slot':1,'source':source.name}]))
        self.assertEqual((self.target/'1.raw').stat().st_size,455680)
        self.assertEqual({n:b for n,b in self.snapshot().items() if n!='1.raw'},
                         {n:b for n,b in before.items() if n!='1.raw'})

    def test_gui_mixed_assignment_failure_changes_no_slots(self):
        good = self.wav('accepted.wav',227840)
        bad = self.wav('rejected.wav',227841)
        before = self.snapshot()
        config = self.config([{'slot':1,'source':good.name},{'slot':2,'source':bad.name}])
        with self.assertRaisesRegex(RuntimeError,'9.493 seconds .*445 KiB'):
            adapter.main(self.root,config)
        self.assertEqual(self.snapshot(),before)

    def test_batch_rejects_before_slot_writes(self):
        self.wav('a_accepted.wav',227840)
        self.wav('b_rejected.wav',227841)
        before = self.snapshot()
        with patch.object(sys,'argv',['customize_loading_screens.py',str(self.root)]), patch('builtins.input',return_value='E'):
            self.assertEqual(batch.main(),1)
        self.assertEqual(self.snapshot(),before)
        self.assertEqual((converter.MAX_BYTES,adapter.LIMIT,batch.MAX_RAW_BYTES),(455680,)*3)


if __name__=='__main__':
    with contextlib.redirect_stdout(io.StringIO()):
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(LoadingLimitTests))
    sys.exit(not result.wasSuccessful())
