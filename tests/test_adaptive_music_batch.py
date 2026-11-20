"""Adaptive resource budgets, concurrent conversion, ordered publication/retry."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import wave

TOOLS = Path(__file__).resolve().parent.parent/'UI Custom Gameplay Music Tools/supporting_tools'
sys.path.insert(0, str(TOOLS))
import add_gameplay_songs as music


class BudgetTests(unittest.TestCase):
    def test_resource_limits_and_unknown_resources(self):
        jobs = [(Path(str(i)),) for i in range(31)]
        for cpus, ram, expected in ((1,16000,1),(2,16000,1),(4,16000,1),
                                    (6,16000,2),(8,16000,3),(128,16000,3),
                                    (12,None,1),(12,1000,1),(12,4000,2)):
            with self.subTest(cpus=cpus,ram=ram), patch.object(music,'available_resources',
                    return_value=(cpus,None if ram is None else ram*music.MIB)), patch.object(
                    music,'estimated_conversion_memory',return_value=900*music.MIB):
                self.assertEqual(music.batch_width(jobs), expected)
        with patch.object(music,'available_resources',return_value=(12,16000*music.MIB)), patch.object(
                music,'estimated_conversion_memory',return_value=None):
            self.assertEqual(music.batch_width(jobs),1)

    def test_serial_override_and_single_job_do_not_probe_resources(self):
        with patch.object(music,'available_resources',side_effect=AssertionError('No probe needed')):
            self.assertEqual(music.batch_width([(Path('one'),)]),1)
            self.assertEqual(music.batch_width([(Path('one'),)]*3,serial=True),1)

    def test_large_tracks_reduce_parallelism(self):
        jobs = [(Path(str(i)),) for i in range(3)]
        with patch.object(music,'available_resources',return_value=(12,8000*music.MIB)), patch.object(
                music,'estimated_conversion_memory',side_effect=[2500*music.MIB,2500*music.MIB]):
            self.assertEqual(music.batch_width(jobs),1)


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.real_run = subprocess.run

    def fixture(self, name, long=False):
        root = self.root/name
        tools = root/'supporting_tools'
        tools.mkdir(parents=True)
        for filename in ('audio_processor.py','rstm_build.py','ps_adpcm_encoder.py'):
            shutil.copy2(TOOLS/filename,tools/filename)
        folder = root/'Custom Music/1_Dancehall'
        folder.mkdir(parents=True)
        for song in ('A','B','C','D'):
            with wave.open(str(folder/f'Artist - {song}.wav'),'wb') as audio:
                audio.setparams((2,2,44100,0,'NONE','not compressed'))
                audio.writeframes(struct.pack('<hhhh',4096,-4096,0,0)*(220500 if long else 140))
        (root/'STREAMS/Music/Dancehall').mkdir(parents=True)
        (root/'ASSETS').mkdir()
        (root/'ASSETS/keep.bin').write_bytes(b'original')
        return root

    def run_music(self, root, extra=()):
        output = io.StringIO()
        def quiet_run(command, **kwargs):
            capture = 'stdout' not in kwargs
            if capture:
                kwargs.update(stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            result = self.real_run(command, **kwargs)
            if capture:
                print(result.stdout)
            return result
        with patch.object(sys,'argv',['add_gameplay_songs.py',str(root),'--yes',*extra]),contextlib.redirect_stdout(output),patch.object(music.subprocess,'run',side_effect=quiet_run):
            result = music.main()
        self.assertEqual((root/'ASSETS/keep.bin').read_bytes(),b'original')
        self.assertFalse(list(root.glob('Music_Add_Temp_*')))
        return result, output.getvalue()

    def test_real_serial_and_parallel_outputs_history_and_skip_match(self):
        serial = self.fixture('serial',long=True)
        parallel = self.fixture('parallel',long=True)
        self.assertEqual(self.run_music(serial,('--serial',))[0],0)
        with patch.object(music,'available_resources',return_value=(12,16000*music.MIB)):
            code, log = self.run_music(parallel)
        self.assertEqual(code,0,log)
        self.assertIn('up to 3 song(s)',log)
        for path in (serial/'STREAMS').rglob('*.rsm'):
            self.assertEqual(path.read_bytes(),(parallel/path.relative_to(serial)).read_bytes())
        self.assertEqual(json.loads((serial/'support_logs/music_conversion_history.json').read_text()),
                         json.loads((parallel/'support_logs/music_conversion_history.json').read_text()))
        with patch.object(music,'convert_track',side_effect=AssertionError('Unchanged tracks must skip')):
            code, log = self.run_music(parallel)
        self.assertEqual(code,0)
        self.assertIn('4 unchanged/baselined',log)

    def test_failure_keeps_only_successful_prefix_and_retry_completes(self):
        root = self.fixture('failure')
        barrier = threading.Barrier(3,timeout=10)
        def convert(job,folder,tools,index,total,stopped,capture):
            folder.mkdir()
            barrier.wait()
            output = folder/'output.rsm'
            output.write_bytes(b'RSTM'+bytes(2048))
            if index == 2:
                return output,'RSM encoding failed for Artist - B.wav (exit code 1).',None
            return output,None,None
        with patch.object(music,'batch_width',return_value=3),patch.object(music,'convert_track',side_effect=convert):
            code, log = self.run_music(root)
        self.assertEqual(code,1)
        self.assertIn('Artist - B.wav',log)
        target = root/'STREAMS/Music/Dancehall'
        self.assertEqual([p.name for p in target.iterdir()],['Artist-A.rsm'])
        history = json.loads((root/'support_logs/music_conversion_history.json').read_text())
        self.assertEqual(len(history['tracks']),1)
        kept = (target/'Artist-A.rsm').read_bytes()
        self.assertEqual(self.run_music(root,('--serial',))[0],0)
        self.assertEqual((target/'Artist-A.rsm').read_bytes(),kept)
        self.assertEqual(len(list(target.glob('*.rsm'))),4)

    def test_failed_update_preserves_installed_track_and_history(self):
        root = self.fixture('update')
        self.assertEqual(self.run_music(root,('--serial',))[0],0)
        target = root/'STREAMS/Music/Dancehall/Artist-A.rsm'
        original = target.read_bytes()
        history = (root/'support_logs/music_conversion_history.json').read_bytes()
        (root/'Custom Music/1_Dancehall/Artist - A.wav').write_bytes(b'broken audio')
        code,log = self.run_music(root,('--serial',))
        self.assertEqual(code,1)
        self.assertIn('audio preparation failed',log)
        self.assertEqual(target.read_bytes(),original)
        self.assertEqual((root/'support_logs/music_conversion_history.json').read_bytes(),history)

    def test_batch_size_reduces_when_resources_become_unknown(self):
        root = self.fixture('changing_resources')
        def convert(job,folder,*args):
            folder.mkdir()
            output = folder/'output.rsm'
            output.write_bytes(b'RSTM'+bytes(2048))
            return output,None,None
        with patch.object(music,'available_resources',side_effect=[(6,16000*music.MIB),(12,None)]),patch.object(
                music,'convert_track',side_effect=convert):
            code,log = self.run_music(root)
        self.assertEqual(code,0)
        self.assertIn('up to 2 song(s)',log)
        self.assertIn('up to 1 song(s)',log)
        self.assertEqual(len(list((root/'STREAMS').rglob('*.rsm'))),4)

    def test_failed_copy_does_not_leave_partial_new_track(self):
        root = self.fixture('disk_failure')
        def convert(job,folder,*args):
            folder.mkdir()
            output = folder/'output.rsm'
            output.write_bytes(b'RSTM'+bytes(2048))
            return output,None,None
        def fail_copy(source,output):
            output.write(b'partial')
            raise OSError('disk full')
        with patch.object(music,'convert_track',side_effect=convert),patch.object(
                music.shutil,'copyfileobj',side_effect=fail_copy):
            code,log = self.run_music(root,('--serial',))
        self.assertEqual(code,1)
        self.assertIn('disk full',log)
        self.assertFalse(list((root/'STREAMS').rglob('*.rsm')))
        self.assertFalse((root/'support_logs/music_conversion_history.json').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
