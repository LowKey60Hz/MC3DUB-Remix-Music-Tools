"""Normal music adapters operate with Python scripts and no encoder EXE/DLL."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

PROJECT=Path(__file__).resolve().parent.parent/'UI Custom Gameplay Music Tools'
TOOLS=PROJECT/'supporting_tools'
sys.path.insert(0,str(TOOLS))
import add_gameplay_songs as gameplay
import sync_winlose_folders as race
import update_title_theme as theme


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.tools=self.root/'supporting_tools'; self.tools.mkdir()
        for name in ('audio_processor.py','rstm_build.py','ps_adpcm_encoder.py'):
            shutil.copy2(TOOLS/name,self.tools/name)
        self.real_run=subprocess.run

    def wav(self,path):
        path.parent.mkdir(parents=True,exist_ok=True)
        with wave.open(str(path),'wb') as audio:
            audio.setparams((2,2,44100,0,'NONE','not compressed'))
            audio.writeframes(struct.pack('<hh',1000,-1000)*280)
        return path

    def guarded_run(self,command,*args,**kwargs):
        self.assertEqual(command[0],sys.executable)
        self.assertTrue(str(command[1]).endswith('.py'))
        kwargs.update(stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        result=self.real_run(command,*args,**kwargs)
        self.assertEqual(result.returncode,0,result.stdout)
        return result

    def assert_rsm(self,path):
        raw=path.read_bytes()
        self.assertEqual(raw[:4],b'RSTM')
        self.assertEqual(struct.unpack_from('<II',raw,8),(44100,2))
        self.assertEqual(struct.unpack_from('<I',raw,0x18)[0],len(raw)-2048)
        self.assertFalse(list(self.tools.glob('*.exe')))
        self.assertFalse(list(self.tools.glob('*.dll')))

    def test_gameplay_and_garage_conversion_without_native_encoder(self):
        self.wav(self.root/'Custom Music/1_Dancehall/Artist - Dance.wav')
        self.wav(self.root/'Custom Music/1_The_Garage_Shop/Artist - Garage.wav')
        music=self.root/'STREAMS/Music'; music.mkdir(parents=True)
        for genre in ('Dancehall','Instrumental'):
            (music/genre).mkdir()
        with patch.object(sys,'argv',['add_gameplay_songs.py',str(self.root),'--yes']),patch.object(gameplay.subprocess,'run',side_effect=self.guarded_run),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gameplay.main(),0)
        files=list(music.rglob('*.rsm'))
        self.assertEqual(len(files),2)
        for path in files:self.assert_rsm(path)
        self.assertFalse((self.root/'ASSETS').exists())

    def test_win_and_lose_use_shared_python_encoder(self):
        for kind in ('Win','Lose'):
            song=self.wav(self.root/f'Custom Music/2_{kind}/Artist - {kind}.wav')
            output=self.root/f'{kind}.rsm'
            with tempfile.TemporaryDirectory(dir=self.root) as scratch,patch.object(race.subprocess,'run',side_effect=self.guarded_run):
                race.encode(song,output,self.tools,Path(scratch))
            self.assert_rsm(output)

    def test_title_theme_updates_existing_frontend_playlists(self):
        self.wav(self.root/'Custom Music/3_Theme Song/Artist - Theme.wav')
        music=self.root/'STREAMS/Music/HipHop'; music.mkdir(parents=True)
        paths=[]
        for city in theme.CITIES:
            path=self.root/f'ASSETS/tune/audio/playlist/city/{city}/music/frontend.play'
            path.parent.mkdir(parents=True); path.write_text('num_songs: 1\nmusic\\HipHop\\MFresh_FrontEnd\n')
            paths.append(path)
        with patch.object(sys,'argv',['update_title_theme.py',str(self.root)]),patch.object(theme.subprocess,'run',side_effect=self.guarded_run),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(theme.main(),0)
        installed=list(music.glob('*.rsm')); self.assertEqual(len(installed),1)
        self.assert_rsm(installed[0])
        for path in paths:self.assertIn(installed[0].stem,path.read_text())


if __name__=='__main__':
    unittest.main(verbosity=2)
