"""Headless dashboard checks using a temporary workspace only."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parent.parent/'UI Custom Gameplay Music Tools'
sys.path.insert(0, str(PROJECT/'gui'))
import main as gui
from PySide6.QtWidgets import QPushButton


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = gui.QApplication.instance() or gui.QApplication([])
        cls.app.setStyleSheet(gui.STYLE)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        with patch.object(gui,'ROOT',self.root), patch.object(gui.Window,'start_auto_validation'), patch.object(gui.Window,'title_preview_original'):
            self.window = gui.Window()
        self.window.profile_verified = True
        self.window.dashboard_catalog_state = 'ready'
        self.window.soundtrack_songs = [
            {'ref':'music/HipHop/A','genre':'hip-hop','title':'Artist A - Song A'},
            {'ref':'MUSIC\\HIPHOP\\A','genre':'hip-hop','title':'Duplicate'},
            {'ref':'music/Instrumental/B','genre':'garage-shop','title':'Garage Song'},
        ]
        for city in ('atlanta','detroit','sd','tokyo'):
            playlist = self.root/f'ASSETS/tune/audio/playlist/city/{city}/music/frontend.play'
            playlist.parent.mkdir(parents=True)
            playlist.write_text('num_songs: 1\nmusic\\HipHop\\MyTheme\n')
        theme = self.root/'STREAMS/Music/HipHop/MyTheme.rsm'
        theme.parent.mkdir(parents=True)
        theme.write_bytes(b'fixture')
        for city in ('atlanta','detroit','sd','tokyo'):
            folder = self.root/f'ASSETS/tune/audio/playlist/city/{city}/music'
            (folder/f'{city}_raceover_music.play').write_text('num_songs: 3\nmusic\\Win_Lose\\win1\nmusic\\Win_Lose\\win2\nmusic\\Win_Lose\\win1\n')
            (folder/f'{city}_raceover_lose_music.play').write_text('num_songs: 1\nmusic\\Win_Lose\\loose1\n')
        folder = self.root/'STREAMS/Music/Win_Lose'
        folder.mkdir()
        for name in ('win1','win2','loose1'):
            (folder/(name+'.rsm')).write_bytes(('fixture-'+name).encode())

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def test_unique_total_genres_and_current_theme(self):
        self.window.update_dashboard_metrics()
        self.assertEqual(self.window.dashboard_song_total.text(),'2')
        self.assertEqual(self.window.dashboard_genre_counts['hip-hop'].text(),'1')
        self.assertEqual(self.window.dashboard_genre_counts['garage-shop'].text(),'1')
        self.assertEqual(self.window.dashboard_genre_counts['rock'].text(),'0')
        self.assertEqual(self.window.dashboard_title_theme.text(),'MyTheme.rsm')

    def test_empty_catalog_is_zero_not_unknown(self):
        self.window.soundtrack_songs=[]
        self.window.update_dashboard_metrics()
        self.assertEqual(self.window.dashboard_song_total.text(),'0')

    def test_race_counts_deduplicate_tracks_across_cities(self):
        self.window.update_dashboard_metrics()
        self.assertEqual(self.window.dashboard_race_counts['Win'].text(),'2')
        self.assertEqual(self.window.dashboard_race_counts['Lose'].text(),'1')

    def test_current_list_and_dashboard_collapse_repeated_references(self):
        self.window.race_refresh_current()
        self.assertEqual(self.window.race_current_tables['Win'].rowCount(), 2)
        self.assertEqual(self.window.dashboard_race_counts['Win'].text(), '2')

    def test_legacy_duplicate_rsm_is_one_soundtrack_and_refresh_detects_changes(self):
        folder = self.root/'STREAMS/Music/Win_Lose'
        (folder/'win3.rsm').write_bytes((folder/'win2.rsm').read_bytes())
        playlists = list((self.root/'ASSETS/tune/audio/playlist/city').rglob('*_raceover_music.play'))
        for path in playlists:
            path.write_text('num_songs: 3\nmusic\\Win_Lose\\win1\nmusic\\Win_Lose\\win2\nmusic\\Win_Lose\\win3\n')
        before = {p: p.read_bytes() for p in playlists}
        self.window.race_refresh_current()
        self.assertEqual(self.window.race_current_tables['Win'].rowCount(), 2)
        self.assertEqual(self.window.dashboard_race_counts['Win'].text(), '2')
        self.assertEqual({p: p.read_bytes() for p in playlists}, before)
        (folder/'win3.rsm').write_bytes(b'a different third soundtrack')
        self.window.race_refresh_current()
        self.assertEqual(self.window.race_current_tables['Win'].rowCount(), 3)
        self.assertEqual(self.window.dashboard_race_counts['Win'].text(), '3')

    def test_missing_playlist_reference_is_not_an_installed_song(self):
        for path in (self.root/'ASSETS/tune/audio/playlist/city').rglob('*_raceover_music.play'):
            path.write_text('num_songs: 3\nmusic\\Win_Lose\\win1\nmusic\\Win_Lose\\win2\nmusic\\Win_Lose\\win3\n')
        self.window.race_refresh_current()
        table = self.window.race_current_tables['Win']
        self.assertEqual(table.rowCount(), 2)
        self.assertEqual(self.window.dashboard_race_counts['Win'].text(), '2')

    def test_playlist_disagreement_does_not_change_installed_inventory(self):
        playlist=self.root/'ASSETS/tune/audio/playlist/city/tokyo/music/tokyo_raceover_music.play'
        playlist.write_text('num_songs: 1\nmusic\\Win_Lose\\win1\n')
        (self.root/'STREAMS/Music/Win_Lose/loose1.rsm').unlink()
        self.window.update_dashboard_metrics()
        self.assertEqual(self.window.dashboard_race_counts['Win'].text(),'2')
        self.assertEqual(self.window.dashboard_race_counts['Lose'].text(),'0')

    def test_zero_inventory_is_independent_of_playlist_count(self):
        for path in (self.root/'ASSETS/tune/audio/playlist/city').rglob('*_raceover_lose_music.play'):
            path.write_text('num_songs: 0\n')
        self.window.update_dashboard_metrics()
        self.assertEqual(self.window.dashboard_race_counts['Lose'].text(),'1')
        (self.root/'STREAMS/Music/Win_Lose/loose1.rsm').unlink()
        self.window.update_dashboard_metrics()
        self.assertEqual(self.window.dashboard_race_counts['Lose'].text(),'0')

    def test_inventory_includes_unreferenced_audio_without_playlists(self):
        folder = self.root/'STREAMS/Music/Win_Lose'
        (folder/'win10.rsm').write_bytes(b'another installed win')
        (folder/'loose3.rsm').write_bytes(b'another installed lose')
        (folder/'MC3_EmptyGenrePlaceholder.rsm').write_bytes(b'placeholder')
        (folder/'win_backup.rsm').write_bytes(b'backup')
        for path in (self.root/'ASSETS/tune/audio/playlist/city').rglob('*_raceover*music.play'):
            path.unlink()
        self.window.race_refresh_current()
        self.assertEqual(self.window.dashboard_race_counts['Win'].text(), '3')
        self.assertEqual(self.window.dashboard_race_counts['Lose'].text(), '2')
        table = self.window.race_current_tables['Win']
        self.assertEqual([table.item(i, 0).text() for i in range(table.rowCount())],
                         ['win1.rsm', 'win2.rsm', 'win10.rsm'])

    def test_missing_installed_folder_is_unavailable_not_zero(self):
        folder = self.root/'STREAMS/Music/Win_Lose'
        for path in folder.iterdir():
            path.unlink()
        folder.rmdir()
        self.window.update_dashboard_metrics()
        self.assertIn('missing', self.window.dashboard_race_counts['Win'].toolTip())
        self.assertIn('missing', self.window.dashboard_race_counts['Lose'].toolTip())

    def test_current_removal_passes_only_selected_installed_files(self):
        script = self.root/'supporting_tools/remove_race_soundtracks.py'
        script.parent.mkdir()
        script.touch()
        self.window.race_refresh_current()
        table = self.window.race_current_tables['Win']
        table.selectRow(1)
        with patch.object(gui.QMessageBox, 'question', return_value=gui.QMessageBox.Yes), \
                patch.object(gui, 'QProcess') as process:
            self.window.race_remove_current('Win')
            args = process.return_value.setArguments.call_args.args[0]
            selected = args[args.index('--selected')+1:args.index('--apply')]
            self.assertEqual(selected, ['win2.rsm'])
            process.return_value.start.assert_called_once()
            self.assertTrue(self.window.race_busy)
            self.assertTrue(all(not b.isEnabled() for b in self.window.race_current_remove_buttons))
        self.window.race_busy = False
        self.window.race_process = None

    def test_current_removal_cancel_does_not_start_a_process(self):
        script = self.root/'supporting_tools/remove_race_soundtracks.py'
        script.parent.mkdir()
        script.touch()
        self.window.race_refresh_current()
        self.window.race_current_tables['Win'].selectRow(0)
        with patch.object(gui.QMessageBox, 'question', return_value=gui.QMessageBox.No), \
                patch.object(gui, 'QProcess') as process:
            self.window.race_remove_current('Win')
            process.assert_not_called()
        self.assertFalse(self.window.race_busy)

    def test_unverified_workspace_hides_old_numbers_and_theme(self):
        self.window.update_dashboard_metrics()
        self.window.profile_verified=False
        self.window.update_dashboard_metrics()
        self.assertEqual(self.window.dashboard_song_total.text(),'—')
        self.assertEqual(self.window.dashboard_title_theme.text(),'—')
        self.assertTrue(all(label.text()=='—' for label in self.window.dashboard_genre_counts.values()))
        self.assertTrue(all(label.text()=='—' for label in self.window.dashboard_race_counts.values()))

    def test_catalog_failure_is_not_zero(self):
        self.window.dashboard_catalog_state='error'
        self.window.update_dashboard_metrics()
        self.assertEqual(self.window.dashboard_song_total.text(),'—')
        self.assertIn('unavailable',self.window.dashboard_song_status.text())

    def test_missing_theme_is_reported(self):
        (self.root/'STREAMS/Music/HipHop/MyTheme.rsm').unlink()
        self.window.update_dashboard_metrics()
        self.assertEqual(self.window.dashboard_title_theme.text(),'Unavailable')

    def test_dashboard_has_no_removed_buttons_and_refreshes_on_visit(self):
        dashboard=self.window.stack.widget(0)
        names=[button.text() for button in dashboard.findChildren(QPushButton)]
        self.assertNotIn('Refresh workspace',names)
        self.assertNotIn('Select project folder',names)
        with patch.object(self.window,'soundtrack_ready',return_value=True), patch.object(self.window,'load_soundtrack') as refresh:
            self.window.navigate(0)
            refresh.assert_called_once()


if __name__=='__main__':
    unittest.main(verbosity=2)
