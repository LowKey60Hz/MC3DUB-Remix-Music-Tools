"""Headless dashboard checks using a temporary workspace only."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys
import tempfile
import unittest
import json
from unittest.mock import patch, Mock

PROJECT = Path(__file__).resolve().parent.parent/'UI Custom Gameplay Music Tools'
sys.path.insert(0, str(PROJECT/'gui'))
import main as gui
from PySide6.QtWidgets import QPushButton


class DashboardTests(unittest.TestCase):
    def test_capacity_real_background_process_and_cache(self):
        import shutil
        from PySide6.QtCore import QEventLoop, QTimer
        tools=self.root/'supporting_tools'
        tools.mkdir(exist_ok=True)
        for source in (PROJECT/'supporting_tools').glob('*.py'):
            shutil.copy2(source,tools/source.name)
        workspace=self.root/'ISO_FILES'; workspace.mkdir(exist_ok=True)
        (workspace/'MC3_PROFILE.txt').write_text('retail')
        (workspace/'MC3_SOURCE_CLASS.txt').write_text('VERIFIED_RETAIL_REFERENCE')
        self.window.capacity_timer.stop()
        self.window.capacity_pending=True
        self.window.capacity_tick()
        process=self.window.capacity_process
        self.assertIsNotNone(process)
        loop=QEventLoop()
        process.finished.connect(loop.quit)
        QTimer.singleShot(10000,loop.quit)
        loop.exec()
        self.assertIsNone(self.window.capacity_process)
        self.assertIn('Projected use:',self.window.workspace_capacity_status.text())
        self.assertTrue((self.root/'support_logs/workspace_capacity_cache.json').is_file())

    def show_capacity(self, used, budget=100*1048576, *, risks=None, code=0, cancelled=False):
        report={'used_bytes':used,'capacity_bytes':budget,'over_capacity_bytes':max(0,used-budget),
                'remaining_bytes':max(0,budget-used),'assets_bytes':used//2,'streams_bytes':used-used//2,
                'record_risks':risks or []}
        process=Mock()
        process.readAllStandardOutput.return_value=('MC3_CAPACITY_JSON:'+json.dumps(report)).encode()
        process.property.return_value=cancelled
        self.window.capacity_process=process
        self.window.capacity_finished(process,str(self.root.resolve()),code,gui.QProcess.NormalExit)
        return process

    def test_capacity_meter_remaining_overage_and_near_limit(self):
        self.show_capacity(80*1048576)
        self.assertIn('20.00 MiB remaining',self.window.workspace_capacity_status.text())
        self.assertEqual(self.window.workspace_capacity_bar.value(),800)
        self.assertIn('staged audio excluded',self.window.workspace_capacity_detail.text())
        self.show_capacity(95*1048576)
        self.assertIn('Approaching capacity',self.window.workspace_capacity_status.text())
        self.show_capacity(110*1048576)
        self.assertIn('Over capacity by 10.00 MiB',self.window.workspace_capacity_status.text())
        self.assertEqual(self.window.workspace_capacity_bar.value(),1000)

    def test_capacity_record_warning_and_error_are_not_a_fit_claim(self):
        self.show_capacity(30*1048576,risks=['ASSETS record limit exceeded.'])
        self.assertIn('record limit exceeded',self.window.workspace_capacity_status.text())
        self.show_capacity(30*1048576,code=1)
        self.assertIn('unavailable',self.window.workspace_capacity_status.text())
        self.assertEqual(self.window.workspace_capacity_bar.format(),'Unavailable')

    def test_stale_capacity_result_does_not_replace_current_status(self):
        self.window.workspace_capacity_status.setText('Waiting for new workspace')
        self.show_capacity(30*1048576,cancelled=True)
        self.assertEqual(self.window.workspace_capacity_status.text(),'Waiting for new workspace')

    def test_capacity_worker_is_cancelled_during_processing_and_deferred(self):
        process=Mock()
        self.window.capacity_process=process
        self.window.capacity_pending=False
        self.window.soundtrack_busy=True
        try:
            self.window.capacity_tick()
            process.kill.assert_called_once()
            process.setProperty.assert_called_with('superseded',True)
            self.assertTrue(self.window.capacity_pending)
        finally:
            self.window.capacity_process=None
            self.window.soundtrack_busy=False

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
            self.window.race_current_remove_buttons[0].click()
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
            self.window.race_current_remove_buttons[0].click()
            process.assert_not_called()
        self.assertFalse(self.window.race_busy)

    def test_staged_loading_preview_plays_four_times_and_stop_restores_single_play(self):
        folder = self.root/'Loading Music'
        folder.mkdir()
        source = folder/'Artist - Loading.wav'
        source.write_bytes(b'temporary audio fixture')
        self.window.loading_refresh()
        self.window.loading_table.selectRow(0)
        player = self.window.loading_preview_player
        with patch.object(player, 'setSource') as set_source, patch.object(player, 'play') as play:
            self.window.loading_staged_preview_button.click()
            self.assertEqual(player.loops(), 4)
            self.assertEqual(Path(set_source.call_args.args[0].toLocalFile()), source)
            play.assert_called_once()
            self.assertEqual(self.window.loading_staged_preview_source, source)
            self.window.loading_preview_stop()
            self.assertEqual(player.loops(), 1)
            self.assertIsNone(self.window.loading_staged_preview_source)

    def test_staged_loading_preview_requires_a_selected_track(self):
        with patch.object(self.window.loading_preview_player, 'play') as play:
            self.window.loading_staged_preview()
            play.assert_not_called()
        self.assertIn('Select exactly one', self.window.loading_staged_preview_status.text())

    def test_already_installed_tracks_are_a_successful_noop_without_prompt(self):
        self.window.race_busy = True
        self.window.race_process = None
        self.window.race_prompt_answered = False
        self.window.race_prompt_tail = '[INFO] No new songs to install. No changes made.\n'
        with patch.object(gui.QMessageBox, 'information') as info, patch.object(gui.QMessageBox, 'warning') as warning:
            self.window.race_finished(0, gui.QProcess.NormalExit)
        warning.assert_not_called()
        self.assertEqual(info.call_args.args[1], 'No changes needed')
        self.assertIn('already installed', self.window.race_state.text())
        self.assertNotIn('Build', info.call_args.args[2])
        self.assertFalse(self.window.race_busy)

    def test_noop_message_does_not_override_a_nonzero_exit(self):
        self.window.race_busy = True
        self.window.race_process = None
        self.window.race_prompt_answered = False
        self.window.race_prompt_tail = '[INFO] No new songs to install. No changes made.\n'
        with patch.object(gui.QMessageBox, 'information') as info, patch.object(gui.QMessageBox, 'warning') as warning:
            self.window.race_finished(1, gui.QProcess.NormalExit)
        warning.assert_called_once()
        info.assert_not_called()

    def test_zero_exit_without_confirmation_or_noop_is_not_claimed_as_updated(self):
        self.window.race_busy = True
        self.window.race_process = None
        self.window.race_prompt_answered = False
        self.window.race_prompt_tail = '[CANCELED] No changes made.\n'
        with patch.object(gui.QMessageBox, 'information') as info, patch.object(gui.QMessageBox, 'warning') as warning:
            self.window.race_finished(0, gui.QProcess.NormalExit)
        warning.assert_called_once()
        info.assert_not_called()

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
