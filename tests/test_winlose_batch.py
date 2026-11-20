"""Win/Lose batching must preserve exact audio, slot rules and transactions."""
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
sys.path.insert(0,str(TOOLS))
import sync_winlose_folders as race


class WinLoseBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.real_run = subprocess.run
        self.real_temp = tempfile.TemporaryDirectory

    def fixture(self,name,win=2,lose=2,long=False):
        root = self.root/name
        tools = root/'supporting_tools'
        tools.mkdir(parents=True)
        for filename in ('audio_processor.py','rstm_build.py','ps_adpcm_encoder.py'):
            shutil.copy2(TOOLS/filename,tools/filename)
        music = root/'STREAMS/Music/Win_Lose'
        music.mkdir(parents=True)
        (music/'win1.rsm').write_bytes(b'original win')
        (music/'loose1.rsm').write_bytes(b'original lose')
        for city in ('atlanta','detroit','sd','tokyo'):
            folder = root/f'ASSETS/tune/audio/playlist/city/{city}/music'
            folder.mkdir(parents=True)
            for i in range(6):
                for suffix,stem in (('music','win1'),('lose_music','loose1')):
                    (folder/f'{i}_raceover_{suffix}.play').write_bytes(
                        ('\ufeffnum_songs: 1\r\nmusic\\Win_Lose\\'+stem+'\r\n').encode('utf-8'))
        for kind,count in (('Win',win),('Lose',lose)):
            folder = root/'Custom Music'/('2_'+kind)
            folder.mkdir(parents=True)
            for i in range(count):
                with wave.open(str(folder/f'{kind} - {i}.wav'),'wb') as audio:
                    audio.setparams((2,2,44100,0,'NONE','not compressed'))
                    amplitude = (i+1)*4096
                    audio.writeframes(struct.pack('<hhhh',amplitude,-amplitude,0,0)*(220500 if long else 140))
        history = root/'support_logs/winlose_add_history.json'
        history.parent.mkdir()
        history.write_text(json.dumps({'Win':{'old':'win1'},'Lose':{'old':'loose1'}}))
        return root

    def run_race(self,root,mode='replace',serial=False):
        log = io.StringIO()
        def quiet_run(command,**kwargs):
            capture = 'stdout' not in kwargs
            if capture:
                kwargs.update(stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            result = self.real_run(command,**kwargs)
            if capture: print(result.stdout)
            return result
        def scratch(*args,**kwargs):
            kwargs['dir'] = self.root
            return self.real_temp(*args,**kwargs)
        with patch.object(sys,'argv',['sync_winlose_folders.py',str(root),mode,*(['--serial'] if serial else [])]), \
                patch('builtins.input',return_value='y'),contextlib.redirect_stdout(log), \
                patch.object(race.subprocess,'run',side_effect=quiet_run), \
                patch.object(race.tempfile,'TemporaryDirectory',side_effect=scratch):
            code = race.main()
        self.assertFalse(list(self.root.glob('mc3_winlose_*')))
        return code,log.getvalue()

    def snapshot(self,root):
        return {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*')
                if p.is_file() and '__pycache__' not in p.parts}

    def test_real_parallel_replace_matches_serial_and_two_win_workaround(self):
        serial = self.fixture('serial',long=True)
        parallel = self.fixture('parallel',long=True)
        self.assertEqual(self.run_race(serial,serial=True)[0],0)
        with patch.object(race.audio_batch,'available_resources',return_value=(12,16000*1024*1024)):
            code,log = self.run_race(parallel)
        self.assertEqual(code,0,log)
        self.assertIn('up to 3 Win/Lose song(s)',log)
        self.assertEqual(self.snapshot(serial),self.snapshot(parallel))
        music = parallel/'STREAMS/Music/Win_Lose'
        self.assertEqual(sorted(p.stem for p in music.glob('win*.rsm')),['win1','win3'])
        for path in parallel.rglob('*_raceover_music.play'):
            self.assertEqual(path.read_text(encoding='utf-8-sig').splitlines(),[
                'num_songs: 3',r'music\Win_Lose\win1',r'music\Win_Lose\win3',r'music\Win_Lose\win3'])
        for path in parallel.rglob('*_raceover_lose_music.play'):
            self.assertEqual(path.read_text(encoding='utf-8-sig').splitlines(),[
                'num_songs: 2',r'music\Win_Lose\loose1',r'music\Win_Lose\loose3'])

    def test_parallel_add_matches_serial_and_verified_history_skips_retry(self):
        serial = self.fixture('add_serial')
        parallel = self.fixture('add_parallel')
        self.assertEqual(self.run_race(serial,'add',serial=True)[0],0)
        with patch.object(race.audio_batch,'available_resources',return_value=(12,16000*1024*1024)):
            code,log = self.run_race(parallel,'add')
        self.assertEqual(code,0,log)
        self.assertEqual(self.snapshot(serial),self.snapshot(parallel))
        before = self.snapshot(parallel)
        with patch.object(race,'encode',side_effect=AssertionError('Already installed')):
            code,log = self.run_race(parallel,'add')
        self.assertEqual(code,0,log)
        self.assertIn('No new songs to install',log)
        self.assertEqual(self.snapshot(parallel),before)

    def test_conversion_failure_changes_no_audio_playlists_or_history(self):
        root = self.fixture('conversion_failure')
        before = self.snapshot(root)
        barrier = threading.Barrier(3,timeout=10)
        def encode(song,output,*args):
            barrier.wait()
            if song.name=='Win - 1.wav': raise RuntimeError('Failed test audio: '+song.name)
            output.write_bytes(b'RSTM'+bytes(2048))
        with patch.object(race.audio_batch,'batch_width',return_value=3),patch.object(race,'encode',side_effect=encode):
            code,log = self.run_race(root)
        self.assertEqual(code,1)
        self.assertIn('Win - 1.wav',log)
        self.assertEqual(self.snapshot(root),before)

    def test_install_failure_rolls_back_both_categories(self):
        root = self.fixture('install_failure')
        before = self.snapshot(root)
        original = shutil.copyfileobj
        def copy(source,destination,*args,**kwargs):
            if Path(destination.name).name=='loose1.rsm':
                destination.write(b'partial')
                raise OSError('simulated install failure')
            return original(source,destination,*args,**kwargs)
        with patch.object(race.audio_batch,'batch_width',return_value=3),patch.object(
                race.shutil,'copyfileobj',side_effect=copy):
            code,log = self.run_race(root)
        self.assertEqual(code,1)
        self.assertIn('[ROLLBACK] Previous files restored',log)
        self.assertEqual(self.snapshot(root),before)

    def test_win_only_keeps_lose_unchanged_and_unknown_resources_stay_serial(self):
        root = self.fixture('win_only',win=2,lose=0)
        before = {p:p.read_bytes() for p in root.rglob('*') if p.is_file() and (
            p.name.startswith('loose') or p.name.endswith('_raceover_lose_music.play'))}
        with patch.object(race.audio_batch,'available_resources',return_value=(12,None)),patch.object(
                race.audio_batch,'ThreadPoolExecutor',side_effect=AssertionError('Must stay serial')):
            code,log = self.run_race(root)
        self.assertEqual(code,0,log)
        self.assertIn('up to 1 Win/Lose song(s)',log)
        self.assertEqual({p:p.read_bytes() for p in before},before)
        self.assertEqual(json.loads((root/'support_logs/winlose_add_history.json').read_text()),{'Lose':{'old':'loose1'}})

    def test_normal_cli_loads_shared_batching_without_native_encoders(self):
        root = self.fixture('cli')
        for filename in ('sync_winlose_folders.py','add_gameplay_songs.py',
                         'remove_race_soundtracks.py','gameplay_placeholders.py'):
            shutil.copy2(TOOLS/filename,root/'supporting_tools'/filename)
        result = self.real_run([sys.executable,str(root/'supporting_tools/sync_winlose_folders.py'),
                                str(root),'replace'],input='y\n',capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('Win/Lose song(s) at a time',result.stdout)
        self.assertEqual(sorted(p.stem for p in (root/'STREAMS/Music/Win_Lose').glob('*.rsm')),
                         ['loose1','loose3','win1','win3'])


if __name__=='__main__':
    unittest.main(verbosity=2)
