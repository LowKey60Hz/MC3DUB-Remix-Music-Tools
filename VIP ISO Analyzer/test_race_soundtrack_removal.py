"""Removal and replacement regressions; all mutations use temporary workspaces."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent/'UI Custom Gameplay Music Tools'
sys.path.insert(0, str(PROJECT/'supporting_tools'))
import remove_race_soundtracks as manager
import sync_winlose_folders as sync


class RemovalTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.music = self.root/'STREAMS/Music/Win_Lose'
        self.music.mkdir(parents=True)
        for name, value in [('win1', b'A'), ('win2', b'B'), ('win3', b'C'), ('loose1', b'L')]:
            (self.music/(name+'.rsm')).write_bytes(value)
        self.plays = []
        for city in ('atlanta', 'detroit', 'sd', 'tokyo'):
            folder = self.root/f'ASSETS/tune/audio/playlist/city/{city}/music'
            folder.mkdir(parents=True)
            for genre in range(6):
                path = folder/f'{genre}_raceover_music.play'
                path.write_bytes(b'num_songs: 3\r\nmusic\\Win_Lose\\win1\r\nmusic\\Win_Lose\\win2\r\nmusic\\Win_Lose\\win3\r\n')
                self.plays.append(path)
                (folder/f'{genre}_raceover_lose_music.play').write_text('num_songs: 1\nmusic\\Win_Lose\\loose1\n')
        history = self.root/'support_logs/winlose_add_history.json'
        history.parent.mkdir()
        history.write_text(json.dumps({'Win': {'old': 'win3'}, 'Lose': {'keep': 'loose1'}}))

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def remove(self, names, kind='Win', apply=True):
        with contextlib.redirect_stdout(io.StringIO()):
            return manager.remove(self.root, kind, names, apply)

    def test_remove_to_two_uses_only_two_rsms_and_abb(self):
        lose = {p: p.read_bytes() for p in self.root.rglob('*_raceover_lose_music.play')}
        self.remove(['win2.rsm'])
        self.assertEqual((self.music/'win1.rsm').read_bytes(), b'A')
        self.assertEqual((self.music/'win3.rsm').read_bytes(), b'C')
        self.assertFalse((self.music/'win2.rsm').exists())
        expected = ['num_songs: 3', r'music\Win_Lose\win1', r'music\Win_Lose\win3', r'music\Win_Lose\win3']
        self.assertTrue(all(p.read_text().splitlines() == expected for p in self.plays))
        self.assertEqual({p: p.read_bytes() for p in lose}, lose)
        self.assertEqual((self.music/'loose1.rsm').read_bytes(), b'L')
        self.assertEqual(json.loads((self.root/'support_logs/winlose_add_history.json').read_text()), {'Lose': {'keep': 'loose1'}})

    def test_duplicate_audio_removes_all_copies_and_one_remaining_is_nonempty(self):
        (self.music/'win3.rsm').write_bytes(b'B')
        self.remove(['win2.rsm'])
        self.assertEqual(sorted(p.name for p in self.music.glob('win*.rsm')), ['win1.rsm'])
        self.assertEqual(self.plays[0].read_text().splitlines(), ['num_songs: 1', r'music\Win_Lose\win1'])

    def test_invalid_selection_and_foreign_reference_make_no_changes(self):
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.remove(['../win1.rsm'])
        self.assertEqual(self.snapshot(), before)
        external = self.root/'ASSETS/other.play'
        external.write_text('num_songs: 1\nmusic\\Win_Lose\\win2\n')
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'another playlist'):
            self.remove(['win2.rsm'])
        self.assertEqual(self.snapshot(), before)

    def test_dry_run_preserves_everything(self):
        before = self.snapshot()
        self.remove(['win1.rsm'], apply=False)
        self.assertEqual(self.snapshot(), before)

    def test_audio_install_failure_restores_audio_playlists_and_history(self):
        before = self.snapshot()
        original = shutil.copyfile
        failed = False
        def copy(source, destination, *args, **kwargs):
            nonlocal failed
            if Path(destination) == self.music/'win1.rsm' and not failed:
                failed = True
                raise OSError('simulated disk failure')
            return original(source, destination, *args, **kwargs)
        with patch.object(manager.shutil, 'copyfile', side_effect=copy):
            with self.assertRaises(OSError):
                self.remove(['win2.rsm'])
        self.assertEqual(self.snapshot(), before)

    def test_missing_placeholder_metadata_blocks_last_removal(self):
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.remove(['win1.rsm', 'win2.rsm', 'win3.rsm'])
        self.assertEqual(self.snapshot(), before)

    def test_last_removal_with_real_metadata_codec(self):
        source = ROOT/'Two_Win_Run_01_Source/ASSETS/fonts'
        if not source.is_dir():
            self.skipTest('Local extracted string tables unavailable')
        tools = self.root/'supporting_tools'
        tools.mkdir()
        shutil.copyfile(PROJECT/'supporting_tools/strtbl.py', tools/'strtbl.py')
        destination = self.root/'ASSETS/fonts'
        destination.mkdir()
        for name in ('mcstrings02.strtbl', 'mcstrings08.strtbl'):
            shutil.copyfile(source/name, destination/name)
        self.remove(['win1.rsm', 'win2.rsm', 'win3.rsm'])
        self.assertFalse(list(self.music.glob('win*.rsm')))
        self.assertEqual(self.plays[0].read_text().splitlines(), ['num_songs: 1', manager.PLACEHOLDERS['Win']])
        self.remove(['loose1.rsm'], kind='Lose')
        self.assertFalse(list(self.music.glob('loose*.rsm')))
        for p in self.root.rglob('*_raceover_lose_music.play'):
            self.assertEqual(p.read_text().splitlines(), ['num_songs: 1', manager.PLACEHOLDERS['Lose']])

    def test_replace_two_sources_produces_two_rsms_and_three_refs(self):
        staged = self.root/'Custom Music/2_Win'
        staged.mkdir(parents=True)
        for name in ('a.mp3', 'b.mp3'):
            (staged/name).write_bytes(name.encode())
        tools = self.root/'supporting_tools'
        tools.mkdir()
        for name in ('audio_processor.py', 'rstm_build.py', 'ps2str.exe'):
            (tools/name).touch()
        def encode(song, output, *_):
            output.write_bytes(song.read_bytes())
        with patch.object(sync, 'encode', side_effect=encode), patch('builtins.input', return_value='y'), \
                patch.object(sys, 'argv', ['sync', str(self.root), 'replace']), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sync.main(), 0)
        self.assertEqual(sorted(p.name for p in self.music.glob('win*.rsm')), ['win1.rsm', 'win3.rsm'])
        self.assertEqual(self.plays[0].read_text().splitlines(), ['num_songs: 3', r'music\Win_Lose\win1', r'music\Win_Lose\win3', r'music\Win_Lose\win3'])
        # Re-running Replace accepts the duplicate playlist reference.
        with patch.object(sync, 'encode', side_effect=encode), patch('builtins.input', return_value='y'), \
                patch.object(sys, 'argv', ['sync', str(self.root), 'replace']), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sync.main(), 0)

    def test_add_after_empty_placeholder_replaces_the_placeholder_reference(self):
        for path in self.music.glob('win*.rsm'):
            path.unlink()
        for path in self.plays:
            path.write_text('num_songs: 1\n'+manager.PLACEHOLDERS['Win']+'\n')
        staged = self.root/'Custom Music/2_Win'
        staged.mkdir(parents=True)
        (staged/'new.mp3').write_bytes(b'new song')
        tools = self.root/'supporting_tools'
        tools.mkdir()
        for name in ('audio_processor.py', 'rstm_build.py', 'ps2str.exe'):
            (tools/name).touch()
        def encode(song, output, *_):
            output.write_bytes(song.read_bytes())
        with patch.object(sync, 'encode', side_effect=encode), patch('builtins.input', return_value='y'), \
                patch.object(sys, 'argv', ['sync', str(self.root), 'add']), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sync.main(), 0)
        self.assertEqual(self.plays[0].read_text().splitlines(), ['num_songs: 1', r'music\Win_Lose\win1'])
        self.assertEqual((self.music/'win1.rsm').read_bytes(), b'new song')

    def prepare_add(self, kind='Win'):
        staged = self.root/'Custom Music'/('2_Win' if kind == 'Win' else '2_Lose')
        staged.mkdir(parents=True, exist_ok=True)
        song = staged/(kind+'.mp3')
        song.write_bytes(('custom '+kind+' song').encode())
        tools = self.root/'supporting_tools'
        tools.mkdir(exist_ok=True)
        for name in ('audio_processor.py', 'rstm_build.py', 'ps2str.exe'):
            (tools/name).touch()
        return song, hashlib.sha256(song.read_bytes()).hexdigest()

    def add_with_encoder(self):
        def encode(song, output, *_):
            output.write_bytes(b'encoded '+song.read_bytes())
        with patch.object(sync, 'encode', side_effect=encode) as encoder, patch('builtins.input', return_value='y'), \
                patch.object(sys, 'argv', ['sync', str(self.root), 'add']), contextlib.redirect_stdout(io.StringIO()) as log:
            self.assertEqual(sync.main(), 0, log.getvalue())
        return encoder, log.getvalue()

    def test_legacy_history_does_not_skip_restored_win_and_lose_audio(self):
        win, win_hash = self.prepare_add('Win')
        lose, lose_hash = self.prepare_add('Lose')
        history = self.root/'support_logs/winlose_add_history.json'
        history.write_text(json.dumps({'Win': {win_hash: 'win1'}, 'Lose': {lose_hash: 'loose1'}}))
        _, log = self.add_with_encoder()
        self.assertIn('[STALE HISTORY]', log)
        self.assertEqual((self.music/'win1.rsm').read_bytes(), b'A')
        self.assertEqual((self.music/'loose1.rsm').read_bytes(), b'L')
        records = json.loads(history.read_text())
        for kind, song, source_hash in [('Win', win, win_hash), ('Lose', lose, lose_hash)]:
            record = records[kind][source_hash]
            audio = self.music/(record['slot']+'.rsm')
            self.assertEqual(audio.read_bytes(), b'encoded '+song.read_bytes())
            self.assertEqual(record['rsm_sha256'], hashlib.sha256(audio.read_bytes()).hexdigest())
        # Repeating Add now proves the installed audio and does no conversion.
        encoder, log = self.add_with_encoder()
        encoder.assert_not_called()
        self.assertIn('Already added (audio verified)', log)

    def test_legacy_history_is_migrated_only_after_matching_audio(self):
        song, source_hash = self.prepare_add()
        (self.music/'win1.rsm').write_bytes(b'encoded '+song.read_bytes())
        history = self.root/'support_logs/winlose_add_history.json'
        history.write_text(json.dumps({'Win': {source_hash: 'win1'}}))
        before = {p: p.read_bytes() for p in self.plays}
        encoder, log = self.add_with_encoder()
        self.assertEqual(encoder.call_count, 1)  # Verification only.
        self.assertIn('No new songs to install', log)
        self.assertEqual({p: p.read_bytes() for p in self.plays}, before)
        record = json.loads(history.read_text())['Win'][source_hash]
        self.assertEqual(record['slot'], 'win1')
        self.assertEqual(record['rsm_sha256'], hashlib.sha256((self.music/'win1.rsm').read_bytes()).hexdigest())

    def test_changed_audio_invalidates_hash_verified_history(self):
        song, source_hash = self.prepare_add()
        expected = b'encoded '+song.read_bytes()
        history = self.root/'support_logs/winlose_add_history.json'
        history.write_text(json.dumps({'Win': {source_hash: {'slot': 'win1',
                           'rsm_sha256': hashlib.sha256(expected).hexdigest()}}}))
        encoder, log = self.add_with_encoder()
        self.assertEqual(encoder.call_count, 1)  # New installation, no legacy verification.
        self.assertIn('[STALE HISTORY]', log)
        record = json.loads(history.read_text())['Win'][source_hash]
        self.assertNotEqual(record['slot'], 'win1')
        self.assertEqual((self.music/(record['slot']+'.rsm')).read_bytes(), expected)

    def test_unreferenced_audio_is_not_treated_as_installed_for_playback(self):
        song, source_hash = self.prepare_add()
        audio = self.music/'win9.rsm'
        audio.write_bytes(b'encoded '+song.read_bytes())
        history = self.root/'support_logs/winlose_add_history.json'
        history.write_text(json.dumps({'Win': {source_hash: {'slot': 'win9',
                           'rsm_sha256': hashlib.sha256(audio.read_bytes()).hexdigest()}}}))
        encoder, log = self.add_with_encoder()
        self.assertEqual(encoder.call_count, 1)
        self.assertIn('[STALE HISTORY]', log)
        record = json.loads(history.read_text())['Win'][source_hash]
        self.assertIn('music\\Win_Lose\\'+record['slot'], self.plays[0].read_text())


if __name__ == '__main__':
    unittest.main(verbosity=2)
