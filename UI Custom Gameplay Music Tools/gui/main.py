"""MC3 Ultimate Music Tools — music workflows and verified Retail/VIP ISO building."""
import sys
import json
from datetime import datetime
from pathlib import Path
import os
import re
import shutil
import random
import tempfile
import wave
import uuid
from workspace_cleanup import cleanup_plan
from PySide6.QtCore import Qt, QProcess, QUrl
from frontend_playlist import resolve_frontend_rsm, FrontendPlaylistError
from race_playlist import read_race_tracks
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QFrame, QStackedWidget, QTextEdit, QFileDialog, QMessageBox,
    QSizePolicy, QProgressBar, QScrollArea, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QLineEdit, QSlider,
    QStyledItemDelegate, QStyle, QGridLayout)

ROOT = Path(__file__).resolve().parent.parent
SECTIONS = [
    ('Dashboard', 'Dashboard'),
    ('ISO Extraction - Start Here', 'ISO Extraction'),
    ('Remove Soundtracks', 'Remove Current Gameplay Soundtrack(s)'),
    ('Gameplay / Garage Music', 'Custom Gameplay and Garage Music'),
    ('Title Theme Soundtrack', 'Update Title Music'),
    ('Lose/Win (Race Transition) Music', 'Update Lose, Win & Race Transition Music'),
    ('Loading Screen Music', 'Update Loading Screen Music'),
    ('Build ISO', 'Compile DAT Archives & Build ISO'),
    ('About', 'About'),
]
STYLE = '''
QWidget { background: #15171b; color: #eceef2; font-family: "Segoe UI"; font-size: 12px; }
QFrame#sidebar { background: #1c1e23; border-right: 1px solid #30333a; }
QFrame#panel { background: #202228; border: 1px solid #34373f; border-radius: 7px; }
QPushButton { background: #292c33; border: 1px solid #444750; border-radius: 5px; padding: 9px 12px; text-align: left; }
QPushButton:hover { border-color: #d94150; background: #343038; }
QPushButton:disabled { color: #858890; background: #24262b; border-color: #34363c; }
QPushButton#navActive { background: #452127; border-left: 3px solid #f04455; color: white; }
QPushButton#primary { background: #8d2834; border-color: #c53d4b; text-align: center; }
QPushButton#primary:hover { background: #a53240; }
QTextEdit { background: #101115; border: 1px solid #33363e; border-radius: 5px; color: #d4d7de; font-family: Consolas; font-size: 11px; }
QLabel#muted { color: #a4a8b1; }
QLabel#heading { font-size: 19px; font-weight: 650; }
QLabel#accent { color: #ff6472; font-weight: 600; }
'''

SOUNDTRACK_SELECTION_STYLE = '''
QTableWidget::item:selected {
    background: #54262e;
    color: #ffffff;
    border: 1px solid #d94150;
    border-radius: 5px;
}
'''


class SoundtrackSelectionDelegate(QStyledItemDelegate):
    """Keep keyboard selection without the native white focus rectangle."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.state &= ~QStyle.State_HasFocus


def apply_soundtrack_selection_theme(table):
    table.setItemDelegate(SoundtrackSelectionDelegate(table))
    table.setStyleSheet(SOUNDTRACK_SELECTION_STYLE)


class StagedMusicTable(QTableWidget):
    """File Explorer drop target; does not change internal row-edit behavior."""
    def __init__(self, owner):
        super().__init__(0, 3)
        self.owner = owner
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setDropIndicatorShown(False)
        self.setDragEnabled(False)
        apply_soundtrack_selection_theme(self)
        self._normal_style = self.styleSheet()

    def _eligible(self, event):
        if self.owner.custom_genre.currentData() is None:
            return False
        if self.owner.custom_busy or self.owner.title_busy or self.owner.build_busy or self.owner.extraction_busy or self.owner.race_busy or self.owner.soundtrack_busy:
            return False
        mime = event.mimeData()
        if not mime.hasUrls():
            return False
        urls = mime.urls()
        return bool(urls) and all(u.isLocalFile() and Path(u.toLocalFile()).is_file()
                                  and Path(u.toLocalFile()).suffix.lower() in ('.mp3', '.wav')
                                  for u in urls)

    def dragEnterEvent(self, event):
        if self._eligible(event):
            event.acceptProposedAction()
            self.setStyleSheet(self._normal_style + ' QTableWidget { border: 2px solid #d94150; }')
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._eligible(event):
            event.acceptProposedAction()
        else:
            event.ignore()
            self.setStyleSheet(self._normal_style)

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self._normal_style)
        event.accept()

    def dropEvent(self, event):
        self.setStyleSheet(self._normal_style)
        if not self._eligible(event):
            event.ignore()
            return
        paths = [u.toLocalFile() for u in event.mimeData().urls()]
        event.acceptProposedAction()
        self.owner.custom_stage_files(paths)


class RaceMusicTable(QTableWidget):
    """Drop MP3/WAV files into the Win or Lose staging list."""
    def __init__(self, owner, kind):
        super().__init__(0, 1)
        self.owner = owner
        self.kind = kind
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setDragEnabled(False)
        self.setDropIndicatorShown(False)
        apply_soundtrack_selection_theme(self)
        self._normal_style = self.styleSheet()

    def _eligible(self, event):
        o = self.owner
        if any((o.race_busy, o.build_busy, o.extraction_busy,
                o.soundtrack_busy, o.custom_busy, o.title_busy)):
            return False
        mime = event.mimeData()
        if not mime.hasUrls():
            return False
        urls = mime.urls()
        return bool(urls) and all(
            u.isLocalFile() and Path(u.toLocalFile()).is_file()
            and Path(u.toLocalFile()).suffix.lower() in ('.mp3', '.wav')
            for u in urls
        )

    def dragEnterEvent(self, event):
        if self._eligible(event):
            event.acceptProposedAction()
            self.setStyleSheet(self._normal_style + ' QTableWidget { border: 2px solid #d94150; }')
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._eligible(event):
            event.acceptProposedAction()
        else:
            event.ignore()
            self.setStyleSheet(self._normal_style)

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self._normal_style)
        event.accept()

    def dropEvent(self, event):
        self.setStyleSheet(self._normal_style)
        if not self._eligible(event):
            event.ignore()
            return
        paths = [u.toLocalFile() for u in event.mimeData().urls()]
        event.acceptProposedAction()
        self.owner.race_stage_files(self.kind, paths)


class TitleThemeDropLabel(QLabel):
    """Accept one MP3/WAV from Windows Explorer for the title theme."""
    def __init__(self, owner):
        super().__init__('No staged title theme')
        self.owner = owner
        self.setAcceptDrops(True)
        self.setFixedHeight(38)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet('QLabel { border: 1px dashed #656974; border-radius: 5px; padding: 5px 9px; }')
        self.setToolTip('Drop one MP3 or WAV file here to stage a replacement title theme.')

    def _file(self, event):
        if any((self.owner.title_busy, self.owner.custom_busy, self.owner.build_busy,
                self.owner.extraction_busy, self.owner.race_busy,
                self.owner.soundtrack_busy, self.owner.loading_busy)):
            return None
        mime = event.mimeData()
        if not mime.hasUrls() or len(mime.urls()) != 1:
            return None
        url = mime.urls()[0]
        if not url.isLocalFile():
            return None
        path = Path(url.toLocalFile())
        return path if path.is_file() and path.suffix.lower() in ('.mp3', '.wav') else None

    def dragEnterEvent(self, event):
        if self._file(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._file(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        source = self._file(event)
        if source is None:
            event.ignore()
            return
        event.acceptProposedAction()
        self.owner.title_stage_file(source)


class AssignmentComboBox(QComboBox):
    """Keep mouse-wheel scrolling on the slot list, not on a hovered combo."""

    def wheelEvent(self, event):
        # Do not change a slot assignment with an accidental wheel movement.
        # Ignoring the event lets the containing table scroll instead.
        event.ignore()


class LoadingMusicTable(QTableWidget):
    """Accept Explorer MP3/WAV drops directly on the existing staged list."""
    def __init__(self, owner):
        super().__init__(0, 1)
        self.owner = owner
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setDragEnabled(False)
        self.setDropIndicatorShown(False)
        apply_soundtrack_selection_theme(self)
        self._normal_style = self.styleSheet()

    def _eligible(self, event):
        o = self.owner
        if any((o.loading_busy, o.race_busy, o.build_busy, o.extraction_busy,
                o.soundtrack_busy, o.custom_busy, o.title_busy)):
            return False
        mime = event.mimeData()
        if not mime.hasUrls():
            return False
        urls = mime.urls()
        return bool(urls) and all(
            u.isLocalFile() and Path(u.toLocalFile()).is_file()
            and Path(u.toLocalFile()).suffix.lower() in ('.mp3', '.wav')
            for u in urls
        )

    def dragEnterEvent(self, event):
        if self._eligible(event):
            event.acceptProposedAction()
            self.setStyleSheet(self._normal_style + ' QTableWidget { border: 2px solid #d94150; }')
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._eligible(event):
            event.acceptProposedAction()
        else:
            event.ignore()
            self.setStyleSheet(self._normal_style)

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self._normal_style)
        event.accept()

    def dropEvent(self, event):
        self.setStyleSheet(self._normal_style)
        if not self._eligible(event):
            event.ignore()
            return
        paths = [u.toLocalFile() for u in event.mimeData().urls()]
        event.acceptProposedAction()
        self.owner.loading_stage_files(paths)


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.root = ROOT
        self.setWindowTitle('MC3 Ultimate Music Tools — Phase 9 Loading Screen Music')
        self.validator = None
        self.extractor = None
        self.iso_path = None
        self.extraction_steps = []
        self.step_index = 0
        self.extraction_busy = False
        self.workspace_reset_authorization = None
        self.extraction_stage = None
        self.extraction_workspace_activated = False
        self.extraction_cleanup_started = False
        self.soundtrack_process = None
        self.soundtrack_busy = False
        self.soundtrack_stage = None
        self.soundtrack_target = None
        self.profile_verified = False
        self.soundtrack_songs = []
        self.dashboard_catalog_state = 'waiting'
        self.race_busy = False
        self.loading_busy = False
        self.loading_process = None
        self.loading_config_path = None
        self.loading_output_text = ''
        self.custom_busy = False
        self.title_busy = False
        self.title_process = None
        self.title_preview_process = None
        self.title_preview_temp = None
        self.title_preview_source = None
        self.title_preview_manual = False
        self.title_preview_player = QMediaPlayer(self)
        self.title_preview_output = QAudioOutput(self)
        self.title_preview_output.setVolume(0.65)
        self.title_preview_player.setAudioOutput(self.title_preview_output)
        self.title_preview_player.positionChanged.connect(self.title_preview_position)
        self.title_preview_player.durationChanged.connect(self.title_preview_duration)
        self.title_preview_player.playbackStateChanged.connect(self.title_preview_playback_state)
        self.title_preview_player.errorOccurred.connect(self.title_preview_media_error)
        # One shared decoder/player for current Win and Lose tracks.
        self.race_preview_temp = None
        self.race_preview_process = None
        self.race_preview_source = None
        self.race_preview_player = QMediaPlayer(self)
        self.race_preview_output = QAudioOutput(self)
        self.race_preview_output.setVolume(0.70)
        self.race_preview_player.setAudioOutput(self.race_preview_output)
        self.race_preview_player.playbackStateChanged.connect(self.race_preview_state_changed)
        self.race_preview_player.errorOccurred.connect(self.race_preview_error)
        # Read-only gameplay soundtrack preview, independent of removal actions.
        self.gameplay_preview_temp = None
        self.gameplay_preview_process = None
        self.gameplay_preview_source = None
        self.gameplay_preview_player = QMediaPlayer(self)
        self.gameplay_preview_output = QAudioOutput(self)
        self.gameplay_preview_output.setVolume(0.70)
        self.gameplay_preview_player.setAudioOutput(self.gameplay_preview_output)
        self.gameplay_preview_player.playbackStateChanged.connect(self.gameplay_preview_update)
        self.gameplay_preview_player.errorOccurred.connect(self.gameplay_preview_error)
        self.gameplay_preview_player.positionChanged.connect(self.gameplay_preview_position)
        self.gameplay_preview_player.durationChanged.connect(self.gameplay_preview_duration)
        # Independent read-only preview for the Current Gameplay Tracks panel.
        self.custom_preview_temp = None
        self.custom_preview_process = None
        self.custom_preview_source = None
        self.custom_preview_player = QMediaPlayer(self)
        self.custom_preview_output = QAudioOutput(self)
        self.custom_preview_output.setVolume(0.70)
        self.custom_preview_player.setAudioOutput(self.custom_preview_output)
        self.custom_preview_player.playbackStateChanged.connect(self.custom_preview_update)
        self.custom_preview_player.errorOccurred.connect(self.custom_preview_error)
        self.custom_preview_player.positionChanged.connect(self.custom_preview_position)
        self.custom_preview_player.durationChanged.connect(self.custom_preview_duration)
        self.loading_preview_temp = None
        self.loading_preview_slot = None
        self.loading_preview_player = QMediaPlayer(self)
        self.loading_preview_output = QAudioOutput(self)
        self.loading_preview_output.setVolume(0.70)
        self.loading_preview_player.setAudioOutput(self.loading_preview_output)
        self.loading_preview_player.positionChanged.connect(self.loading_preview_position)
        self.loading_preview_player.durationChanged.connect(self.loading_preview_duration)
        self.loading_preview_player.playbackStateChanged.connect(self.loading_preview_state_changed)
        self.loading_preview_player.errorOccurred.connect(self.loading_preview_error)
        self.custom_process = None
        self.custom_index = 0
        self.custom_steps = []
        self.race_process = None
        self.race_prompt_answered = False
        self.race_prompt_tail = ""
        self.build_busy = False
        self.build_process = None
        self.build_steps = []
        self.build_index = 0
        self.build_output = None
        self.build_pending = None
        self.build_profile = None
        self.build_log_file = None
        self.build_capacity_report_path = None
        self.resize(1200, 800)
        self.setMinimumSize(980, 660)
        self.setStyleSheet(STYLE)
        outer = QWidget(); self.setCentralWidget(outer)
        layout = QHBoxLayout(outer); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)
        sidebar = QFrame(); sidebar.setObjectName('sidebar'); sidebar.setFixedWidth(202)
        side = QVBoxLayout(sidebar); side.setContentsMargins(10, 17, 10, 12); side.setSpacing(5)
        name = QLabel('MC3 MUSIC TOOLS'); name.setObjectName('accent'); side.addWidget(name)
        subtitle = QLabel('Ultimate Music Tools  •  v0.1'); subtitle.setObjectName('muted'); side.addWidget(subtitle)
        side.addSpacing(18)
        self.nav = []
        for i, (label, _) in enumerate(SECTIONS):
            if i == 8: side.addStretch(1)
            b = QPushButton(label); b.clicked.connect(lambda _, index=i: self.navigate(index))
            if i == 1:
                b.setText('ISO Extraction -\nStart Here')
                b.setMinimumHeight(48)
            if label == 'Lose/Win (Race Transition) Music':
                b.setText('Lose/Win (Race\nTransition) Music')
                b.setMinimumHeight(48)
            side.addWidget(b); self.nav.append(b)
        layout.addWidget(sidebar)
        right = QWidget(); r = QVBoxLayout(right); r.setContentsMargins(20, 18, 20, 12); r.setSpacing(12)
        self.stack = QStackedWidget(); r.addWidget(self.stack, 1)
        self.stack.addWidget(self.dashboard())
        self.stack.addWidget(self.extraction_page())
        self.stack.addWidget(self.soundtrack_page())
        self.stack.addWidget(self.custom_music_page())
        self.stack.addWidget(self.title_music_page())
        self.stack.addWidget(self.race_music_page())
        self.stack.addWidget(self.loading_music_page())
        self.stack.addWidget(self.build_page())
        for label, title in SECTIONS[8:]: self.stack.addWidget(self.section(label, title))
        log_head = QHBoxLayout(); log_head.addWidget(QLabel('Activity Log'))
        log_head.addStretch(1)
        toggle = QPushButton('Hide log'); toggle.setFixedWidth(90); toggle.clicked.connect(lambda: self.toggle_log(toggle))
        log_head.addWidget(toggle); r.addLayout(log_head)
        self.log_box = QTextEdit(); self.log_box.setReadOnly(True); self.log_box.setFixedHeight(95); r.addWidget(self.log_box)
        self.status = QLabel('Ready  •  ISO extraction integration'); self.status.setObjectName('muted'); r.addWidget(self.status)
        layout.addWidget(right, 1)
        self.navigate(0)
        self.log('GUI started; no processing engines invoked.')
        self.refresh_workspace()
        self.start_auto_validation()
        self.loading_refresh() 

    def log(self, message):
        self.log_box.append(f'[{datetime.now():%H:%M:%S}] {message}')

    def panel(self, title):
        frame = QFrame(); frame.setObjectName('panel')
        v = QVBoxLayout(frame); v.setContentsMargins(15, 12, 15, 12); v.setSpacing(8)
        t = QLabel(title); t.setStyleSheet('font-weight: 600; font-size: 13px;'); v.addWidget(t)
        return frame, v

    def dashboard(self):
        page = QWidget(); v = QVBoxLayout(page); v.setContentsMargins(0,0,0,0); v.setSpacing(13)
        h = QLabel('Dashboard'); h.setObjectName('heading'); v.addWidget(h)
        card, cv = self.panel('Current Workspace')
        self.profile = QLabel('Game profile: Not detected'); cv.addWidget(self.profile)
        self.workspace = QLabel('Workspace: Checking…'); self.workspace.setObjectName('muted'); cv.addWidget(self.workspace)
        self.source = QLabel('Recorded source ISO: Not recorded'); self.source.setObjectName('muted'); self.source.setWordWrap(True)
        self.source.setTextInteractionFlags(Qt.TextSelectableByMouse); self.source.setMinimumHeight(48)
        cv.addWidget(self.source)
        self.validation = QLabel('Profile validation: Not run'); self.validation.setObjectName('muted'); self.validation.setWordWrap(True); cv.addWidget(self.validation)
        v.addWidget(card)
        overview = QHBoxLayout(); overview.setSpacing(12)
        card, cv = self.panel('Total Gameplay & Garage Songs')
        self.dashboard_song_total = QLabel('—')
        self.dashboard_song_total.setStyleSheet('font-size: 32px; font-weight: 700; color: #ff6472;')
        cv.addWidget(self.dashboard_song_total)
        self.dashboard_song_status = QLabel('Load an ISO workspace to see your soundtrack.')
        self.dashboard_song_status.setObjectName('muted'); self.dashboard_song_status.setWordWrap(True)
        cv.addWidget(self.dashboard_song_status)
        overview.addWidget(card, 1)
        card, cv = self.panel('Current Title Theme Soundtrack')
        self.dashboard_title_theme = QLabel('—')
        self.dashboard_title_theme.setWordWrap(True)
        self.dashboard_title_theme.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.dashboard_title_theme.setStyleSheet('font-size: 16px; font-weight: 600;')
        cv.addWidget(self.dashboard_title_theme)
        overview.addWidget(card, 1)
        v.addLayout(overview)
        card, cv = self.panel('Songs by Genre & Garage Shop')
        grid = QGridLayout(); grid.setHorizontalSpacing(24); grid.setVerticalSpacing(16)
        self.dashboard_genre_counts = {}
        for position, (key, name) in enumerate((
            ('dancehall', 'Dancehall'), ('drum-and-bass', 'Drum and Bass'),
            ('hip-hop', 'Hip-Hop'), ('rock', 'Rock'), ('techno', 'Techno'),
            ('garage-shop', 'Garage Shop'),
        )):
            cell = QVBoxLayout(); cell.setSpacing(3)
            label = QLabel(name); label.setObjectName('muted'); cell.addWidget(label)
            count = QLabel('—'); count.setStyleSheet('font-size: 23px; font-weight: 600;')
            cell.addWidget(count)
            self.dashboard_genre_counts[key] = count
            grid.addLayout(cell, position // 3, position % 3)
        cv.addLayout(grid); v.addWidget(card)
        card, cv = self.panel('Lose & Win Songs')
        race_counts = QHBoxLayout(); race_counts.setSpacing(24)
        self.dashboard_race_counts = {}
        for kind in ('Lose', 'Win'):
            column = QVBoxLayout(); column.setSpacing(3)
            label = QLabel(kind + ' Songs'); label.setObjectName('muted'); column.addWidget(label)
            count = QLabel('—'); count.setStyleSheet('font-size: 23px; font-weight: 600;')
            column.addWidget(count)
            self.dashboard_race_counts[kind] = count
            race_counts.addLayout(column, 1)
        cv.addLayout(race_counts); v.addWidget(card)
        v.addStretch(1)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        return scroll

    def update_dashboard_metrics(self):
        if not hasattr(self, 'dashboard_song_total'):
            return
        ready = self.profile_verified and self.dashboard_catalog_state == 'ready'
        if ready:
            groups = {key: set() for key in self.dashboard_genre_counts}
            for song in self.soundtrack_songs:
                if song['genre'] in groups:
                    groups[song['genre']].add(song['ref'].replace('\\', '/').casefold())
            self.dashboard_song_total.setText(f'{len(set().union(*groups.values())):,}')
            for key, label in self.dashboard_genre_counts.items():
                label.setText(f'{len(groups[key]):,}')
            self.dashboard_song_status.setText('Current gameplay and Garage Shop soundtrack.')
        else:
            self.dashboard_song_total.setText('—')
            for label in self.dashboard_genre_counts.values():
                label.setText('—')
            message = 'Load and verify an ISO workspace to see your soundtrack.'
            if self.profile_verified:
                message = ('Soundtrack unavailable. See the Activity Log.' if self.dashboard_catalog_state == 'error'
                           else 'Updating soundtrack…')
            self.dashboard_song_status.setText(message)
        self.dashboard_title_theme.setToolTip('')
        for kind, label in self.dashboard_race_counts.items():
            label.setText('—')
            label.setToolTip('')
            if self.profile_verified:
                try:
                    tracks = read_race_tracks(self.root, kind)
                    unique = {track.casefold(): track for track in tracks}
                    folder = self.root/'STREAMS/Music/Win_Lose'
                    missing = [track for track in unique.values()
                               if not (folder/(track.rsplit('\\', 1)[-1]+'.rsm')).is_file()]
                    if missing:
                        raise ValueError('Referenced audio files are missing: ' + ', '.join(missing))
                    label.setText(f'{len(unique):,}')
                except (OSError, UnicodeError, ValueError) as exc:
                    label.setToolTip(str(exc))
        if not self.profile_verified:
            self.dashboard_title_theme.setText('—')
            return
        try:
            reference, source = resolve_frontend_rsm(self.root)
            self.dashboard_title_theme.setText(source.name)
            self.dashboard_title_theme.setToolTip(reference)
        except (FrontendPlaylistError, OSError) as exc:
            self.dashboard_title_theme.setText('Unavailable')
            self.dashboard_title_theme.setToolTip(str(exc))

    def extraction_page(self):
        page = QWidget(); v = QVBoxLayout(page); v.setContentsMargins(0,0,0,0); v.setSpacing(13)
        title = QLabel('ISO Extraction'); title.setObjectName('heading'); v.addWidget(title)
        card, cv = self.panel('Select Original ISO')
        hint = QLabel('Select a supported Retail USA or VIP Expansion ISO. Your source ISO will not be modified.')
        hint.setWordWrap(True); hint.setObjectName('muted'); cv.addWidget(hint)
        row = QHBoxLayout()
        self.selected_iso_label = QLabel('No ISO selected'); self.selected_iso_label.setWordWrap(True)
        row.addWidget(self.selected_iso_label, 1)
        self.browse_iso = QPushButton('Browse ISO…'); self.browse_iso.setFixedWidth(125)
        self.browse_iso.clicked.connect(self.select_iso); row.addWidget(self.browse_iso)
        cv.addLayout(row); v.addWidget(card)
        card, cv = self.panel('Extraction')
        self.extraction_status = QLabel('Select an ISO to begin.'); self.extraction_status.setObjectName('muted'); cv.addWidget(self.extraction_status)
        self.extraction_progress = QProgressBar(); self.extraction_progress.setRange(0, 5)
        self.extraction_progress.setValue(0); self.extraction_progress.setTextVisible(True); cv.addWidget(self.extraction_progress)
        self.run_extraction = QPushButton('Run ISO Extraction'); self.run_extraction.setObjectName('primary')
        self.run_extraction.setEnabled(False); self.run_extraction.clicked.connect(self.begin_extraction)
        cv.addWidget(self.run_extraction)
        v.addWidget(card)
        note = QLabel('If a workspace is already loaded, you can restart from a fresh ISO.\n'
                      'After the new ISO passes preflight, the current STREAMS, ASSETS, ISO_FILES and support_logs folders are cleared.')
        note.setObjectName('muted'); note.setWordWrap(True); v.addWidget(note)
        v.addStretch(1)
        return page

    def select_iso(self):
        if self.extraction_operation_running():
            QMessageBox.information(self, 'Operation in progress', 'Wait for the current operation to finish before selecting another ISO.')
            return
        filename, _ = QFileDialog.getOpenFileName(self, 'Select Midnight Club 3 ISO', str(self.root), 'ISO images (*.iso);;All files (*)')
        if not filename: return
        candidate = Path(filename).resolve()
        if not candidate.is_file() or candidate.suffix.lower() != '.iso':
            QMessageBox.warning(self, 'Invalid ISO', 'Select an existing .iso file.')
            return
        if not self.confirm_workspace_restart(candidate):
            return
        self.iso_path = candidate
        self.selected_iso_label.setText(str(candidate))
        self.extraction_status.setText('ISO selected — ready to validate and restart the workspace.' if self.workspace_reset_authorization else 'ISO selected — ready for preflight and extraction.')
        self.extraction_progress.setValue(0)
        self.run_extraction.setEnabled(True)
        self.log(f'Source ISO selected: {candidate}')
        if self.workspace_reset_authorization:
            self.begin_extraction()

    def extraction_operation_running(self):
        return (any(getattr(self, name, False) for name in ('extraction_busy','build_busy','soundtrack_busy','race_busy','custom_busy','title_busy','loading_busy'))
                or bool(self.validator and self.validator.state() != QProcess.NotRunning))

    def confirm_workspace_restart(self, candidate):
        try:
            targets = cleanup_plan(self.root, candidate)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, 'Workspace restart unavailable', str(error))
            return False
        # An empty support_logs folder alone is not a loaded ISO workspace.
        try:
            loaded = any(path.name != 'support_logs' or any(path.iterdir()) for path in targets)
        except OSError as error:
            QMessageBox.warning(self, 'Workspace restart unavailable', str(error))
            return False
        if not loaded:
            self.workspace_reset_authorization = None
            return True
        authorization = (self.root.resolve(), candidate.resolve())
        if self.workspace_reset_authorization == authorization:
            return True
        reply = QMessageBox.question(self, 'ISO Workspace Already Loaded',
            'An ISO workspace is already loaded. Restart from a fresh ISO?\n\n'
            f'New ISO:\n{candidate}\n\n'
            'After the new ISO passes validation, the current folders will be permanently cleared:\n'
            'STREAMS\nASSETS\nISO_FILES\nsupport_logs\n\n'
            'Current workspace edits and support logs will be lost. The source ISO and other project files are kept.\n\n'
            'Choose Yes to validate the new ISO and restart extraction. Choose No to keep the current workspace.',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return False
        self.workspace_reset_authorization = authorization
        return True

    def stop_workspace_previews(self):
        self.gameplay_preview_stop()
        self.custom_preview_stop()
        self.race_preview_stop()
        self.title_preview_stop()
        self.loading_preview_stop()

    def reset_workspace_views(self):
        self.profile_verified = False
        self.soundtrack_songs = []
        self.song_filter.setCurrentIndex(0)
        self.song_search.clear()
        self.filter_soundtrack()
        for name in ('gameplay_preview_source','custom_preview_source','race_preview_source','title_preview_source'):
            setattr(self, name, None)
        self.title_preview_manual = False
        self.custom_refresh()
        self.race_refresh()
        self.title_refresh()
        self.title_state.setText('Workspace changed; select a title track to preview or process.')
        self.loading_progress.setValue(0)
        for slot in range(self.loading_slot_table.rowCount()):
            self.loading_slot_table.cellWidget(slot, 1).setCurrentIndex(0)
        self.loading_refresh()
        self.refresh_workspace()

    def begin_extraction(self):
        if self.extraction_operation_running():
            QMessageBox.information(self, 'Operation in progress', 'Wait for the current operation to finish before extracting an ISO.')
            return
        if not self.iso_path or not self.iso_path.is_file():
            QMessageBox.warning(self, 'ISO missing', 'Select an existing ISO file first.')
            return
        tools = self.root / 'supporting_tools'
        required = ['MC3_ISO_Extractor.py', 'MC3_Profile_108S.py', 'MC3_PS2_Streams.lst', 'dave.py', 'hash_build.py']
        missing = [name for name in required if not (tools / name).is_file()]
        if missing:
            QMessageBox.warning(self, 'Missing utilities', 'Required supporting tools missing: ' + ', '.join(missing))
            return
        if not self.confirm_workspace_restart(self.iso_path):
            return
        reset = self.workspace_reset_authorization == (self.root.resolve(), self.iso_path.resolve())
        if not reset:
            reply = QMessageBox.question(self, 'Confirm ISO extraction',
                f'Extract and decompile the selected ISO?\n\n{self.iso_path}\n\n'
                'This creates ISO_FILES, ASSETS, and STREAMS in the selected project folder. '
                'The source ISO will remain unchanged.',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes: return
        stage = self.root / ('MC3_108S_Staging_' + uuid.uuid4().hex)
        self.extraction_stage = stage
        self.extraction_workspace_activated = False
        self.extraction_cleanup_started = False
        workspace = self.root / 'ISO_FILES'
        tools = self.root / 'supporting_tools'
        self.extraction_steps = [
            ('ISO preflight', tools / 'MC3_ISO_Extractor.py', [str(self.iso_path), '--output-dir', str(stage), '--production']),
            ('Profile inspection', tools / 'MC3_Profile_108S.py', ['inspect', str(self.iso_path)]),
            ('ISO archive extraction', tools / 'MC3_ISO_Extractor.py', [str(self.iso_path), '--output-dir', str(stage), '--extract', '--production', '--yes']),
            ('Record game profile', tools / 'MC3_Profile_108S.py', ['record', str(self.iso_path), str(stage), str(tools / 'MC3_PS2_Streams.lst')]),
            ('Decompile ASSETS', tools / 'dave.py', ['X', str(workspace / 'ASSETS.DAT'), '-o', str(self.root / 'ASSETS')]),
            ('Decompile STREAMS', tools / 'hash_build.py', []),
        ]
        if reset:
            self.extraction_steps.insert(2, ('Clear previous ISO workspace', Path(__file__).with_name('workspace_cleanup.py'),
                ['--root',str(self.root.resolve()),'--source-iso',str(self.iso_path.resolve())]))
        self.extraction_busy = True; self.step_index = 0
        self.extraction_progress.setRange(0, len(self.extraction_steps) + 1)
        self.extraction_progress.setValue(0)
        self.run_extraction.setEnabled(False); self.browse_iso.setEnabled(False)
        self.stop_workspace_previews()
        self.set_soundtrack_buttons()
        self.update_build_controls()
        self.log('Extraction started. Original ISO will remain unchanged.')
        self.next_extraction_step()

    def next_extraction_step(self):
        if (self.step_index < len(self.extraction_steps)
                and self.extraction_steps[self.step_index][0] == 'Decompile ASSETS'
                and not self.extraction_workspace_activated):
            stage = self.extraction_stage
            target = self.root / 'ISO_FILES'
            try:
                if target.exists(): raise RuntimeError('ISO_FILES unexpectedly exists; refusing overwrite')
                if not all((stage / name).is_file() for name in ('ASSETS.DAT', 'STREAMS.DAT', 'STREAMS.LST', 'MC3_PROFILE.txt')):
                    raise RuntimeError('Staged workspace missing required archives, manifest or profile metadata')
                stage.rename(target)
                self.extraction_workspace_activated = True
                self.log('Staged archives activated as ISO_FILES.')
                self.extraction_progress.setValue(self.step_index + 1)
            except Exception as exc:
                self.extraction_failed(f'Workspace activation failed: {exc}')
                return
        if self.step_index >= len(self.extraction_steps):
            if not self.folder_has_files(self.root / 'ASSETS') or not self.folder_has_files(self.root / 'STREAMS'):
                self.extraction_failed('Decompiled folder is empty or missing.')
                return
            self.extraction_busy = False
            self.browse_iso.setEnabled(True); self.run_extraction.setEnabled(True)
            self.extraction_progress.setValue(self.extraction_progress.maximum())
            self.extraction_status.setText('Extraction and DAT decompilation completed successfully.')
            self.workspace_reset_authorization = None
            self.status.setText('Extraction complete  •  Verifying profile integrity')
            self.log('SUCCESS: ISO_FILES, ASSETS, and STREAMS are ready.')
            self.reset_workspace_views()
            self.start_auto_validation()
            QMessageBox.information(self, 'Extraction complete', 'ISO extraction and DAT decompilation completed successfully.')
            return
        title, script, args = self.extraction_steps[self.step_index]
        if title == 'Clear previous ISO workspace':
            if self.workspace_reset_authorization != (self.root.resolve(), self.iso_path.resolve()):
                self.extraction_failed('Workspace cleanup authorization no longer matches the selected ISO/project.')
                return
            self.profile_verified = False
            self.extraction_cleanup_started = True
            self.update_build_controls()
        if title == 'Decompile STREAMS':
            manifest = self.root / 'ISO_FILES' / 'STREAMS.LST'
            if not manifest.is_file(): manifest = self.root / 'supporting_tools' / 'MC3_PS2_Streams.lst'
            args = ['X', str(self.root / 'ISO_FILES' / 'STREAMS.DAT'), '-nl', str(manifest),
                    '-a', 'mclub', '-th', '45', '-o', str(self.root / 'STREAMS')]
        self.extraction_status.setText(f'Running: {title}…')
        self.extraction_error_tail = ''
        self.log(f'[{self.step_index+1}/{len(self.extraction_steps)}] {title}')
        self.extractor = QProcess(self)
        self.extractor.setWorkingDirectory(str(self.root))
        self.extractor.setProgram(sys.executable)
        self.extractor.setArguments(['-u', str(script), *args])
        self.extractor.setProcessChannelMode(QProcess.MergedChannels)
        self.extractor.readyReadStandardOutput.connect(self.extraction_output)
        self.extractor.finished.connect(self.extraction_finished)
        self.extractor.errorOccurred.connect(self.extraction_error)
        self.extractor.start()

    @staticmethod
    def folder_has_files(path):
        return path.is_dir() and any(p.is_file() for p in path.rglob('*'))

    def extraction_output(self):
        if self.extractor:
            chunk = bytes(self.extractor.readAllStandardOutput()).decode('utf-8', errors='replace')
            self.extraction_error_tail = (getattr(self, 'extraction_error_tail', '') + chunk)[-4096:]
            for line in chunk.splitlines():
                if line.strip(): self.log(line)

    def extraction_finished(self, exit_code, exit_status):
        self.extraction_output()
        if not self.extraction_busy: return
        if self.extraction_steps[self.step_index][0] == 'Clear previous ISO workspace':
            self.workspace_reset_authorization = None
            self.reset_workspace_views()
        if exit_status != QProcess.NormalExit or exit_code != 0:
            lines = getattr(self, 'extraction_error_tail', '').strip().splitlines()
            detail = ('\n' + lines[-1]) if lines else ''
            self.extraction_failed(f'{self.extraction_steps[self.step_index][0]} failed (exit code {exit_code}).' + detail)
            return
        self.step_index += 1
        self.extraction_progress.setValue(self.step_index + int(self.extraction_workspace_activated))
        self.next_extraction_step()

    def extraction_error(self, error):
        if self.extractor:
            self.log(f'Extraction process error: {self.extractor.errorString()}')
        if error == QProcess.FailedToStart:
            self.extraction_failed('Python process could not start.')

    def extraction_failed(self, message):
        if not self.extraction_busy: return
        self.extraction_busy = False
        self.extraction_status.setText('Extraction failed — see Activity Log.')
        self.status.setText('Extraction failed  •  Inspect workspace before retrying')
        self.log('ERROR: ' + message)
        self.log('Remaining files and partial output were retained for inspection.' if self.extraction_cleanup_started
                 else 'The previous workspace was not cleared; partial output was retained for inspection.')
        if self.extraction_stage:
            self.log('Extraction staging path: ' + str(self.extraction_stage))
        self.workspace_reset_authorization = None
        self.browse_iso.setEnabled(True)
        self.run_extraction.setEnabled(bool(self.iso_path and self.iso_path.is_file()))
        self.refresh_workspace()
        QMessageBox.critical(self, 'Extraction failed', message + '\n\nReview the Activity Log. Partial files were retained for inspection.')

    def soundtrack_page(self):
        page = QWidget(); v = QVBoxLayout(page); v.setContentsMargins(0,0,0,0); v.setSpacing(10)
        heading = QLabel('Remove Current Gameplay Soundtracks'); heading.setObjectName('heading'); v.addWidget(heading)
        card, cv = self.panel('Current Gameplay Soundtrack')
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel('Filter:'))
        self.song_filter = QComboBox()
        for label, key in [('All','all'),('Dancehall','dancehall'),('Drum and Bass','drum-and-bass'),('Hip-Hop','hip-hop'),('Rock','rock'),('Techno','techno'),('Garage Shop','garage-shop')]:
            self.song_filter.addItem(label,key)
        self.song_filter.currentIndexChanged.connect(self.filter_soundtrack)
        toolbar.addWidget(self.song_filter,1)
        toolbar.addWidget(QLabel('Search:'))
        self.song_search = QLineEdit(); self.song_search.setPlaceholderText('Title, artist or reference…')
        self.song_search.textChanged.connect(self.filter_soundtrack)
        toolbar.addWidget(self.song_search,2)
        self.song_load_button = QPushButton('Refresh Soundtrack')
        self.song_load_button.clicked.connect(self.load_soundtrack)
        toolbar.addWidget(self.song_load_button)
        cv.addLayout(toolbar)
        self.song_status = QLabel('Soundtrack loads automatically after profile verification. You can also refresh it.')
        self.song_status.setObjectName('muted'); cv.addWidget(self.song_status)
        self.song_table = QTableWidget(0,2)
        apply_soundtrack_selection_theme(self.song_table)
        self.song_table.setHorizontalHeaderLabels(['Artist - Song', 'Genre'])
        self.song_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        self.song_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeToContents)
        self.song_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.song_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.song_table.setToolTip('Use Ctrl+click to select multiple songs or Shift+click to select a range.')
        self.song_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.song_table.verticalHeader().setVisible(False)
        self.song_table.setMinimumHeight(145)
        self.song_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.song_table.itemSelectionChanged.connect(self.set_soundtrack_buttons)
        self.song_table.itemSelectionChanged.connect(self.gameplay_preview_selection_changed)
        cv.addWidget(self.song_table,1)
        preview_row = QHBoxLayout()
        self.gameplay_preview_play_button = QPushButton('Play / Resume')
        self.gameplay_preview_play_button.clicked.connect(self.gameplay_preview_toggle)
        preview_row.addWidget(self.gameplay_preview_play_button, 1)
        self.gameplay_preview_stop_button = QPushButton('Stop')
        self.gameplay_preview_stop_button.clicked.connect(self.gameplay_preview_stop)
        preview_row.addWidget(self.gameplay_preview_stop_button, 1)
        self.song_remove = QPushButton('Remove Selected Songs…'); self.song_remove.setObjectName('primary')
        self.song_remove.clicked.connect(lambda: self.preview_soundtrack('song'))
        preview_row.addWidget(self.song_remove, 2)
        cv.addLayout(preview_row)
        self.gameplay_preview_seek = QSlider(Qt.Horizontal)
        self.gameplay_preview_seek.setRange(0, 0)
        self.gameplay_preview_seek.setEnabled(False)
        self.gameplay_preview_seek.sliderMoved.connect(self.gameplay_preview_player.setPosition)
        cv.addWidget(self.gameplay_preview_seek)
        self.gameplay_preview_time = QLabel('00:00 / 00:00')
        self.gameplay_preview_time.setObjectName('muted')
        cv.addWidget(self.gameplay_preview_time)
        self.gameplay_preview_status = QLabel('')
        self.gameplay_preview_status.setObjectName('muted')
        self.gameplay_preview_status.setWordWrap(True)
        self.gameplay_preview_status.hide()  # No blank status row when there is no message.
        cv.addWidget(self.gameplay_preview_status)
        v.addWidget(card,1)
        card, cv = self.panel('Remove All by Category')
        line = QHBoxLayout()
        self.genre_selector = QComboBox()
        for title,key in [('Select category…',None),('Dancehall','dancehall'),('Drum and Bass','drum-and-bass'),('Hip-Hop','hip-hop'),('Rock','rock'),('Techno','techno'),('Garage Shop','garage-shop'),('All Gameplay & Garage Shop Music','all')]:
            self.genre_selector.addItem(title,key)
        self.genre_selector.currentIndexChanged.connect(self.set_soundtrack_buttons)
        line.addWidget(self.genre_selector,1)
        self.genre_remove = QPushButton('Remove All..'); self.genre_remove.setObjectName('primary')
        self.genre_remove.clicked.connect(lambda: self.preview_soundtrack('genre'))
        line.addWidget(self.genre_remove)
        cv.addLayout(line); v.addWidget(card)
        self.soundtrack_state = QLabel('')
        self.soundtrack_state.setObjectName('muted'); self.soundtrack_state.setWordWrap(True)
        v.addWidget(self.soundtrack_state)
        self.soundtrack_progress = QProgressBar()
        self.soundtrack_progress.setRange(0, 100)
        self.soundtrack_progress.setValue(0)
        v.addWidget(self.soundtrack_progress)
        self.soundtrack_songs = []
        self.build_busy = False
        self.build_process = None
        self.build_steps = []
        self.build_index = 0
        self.build_output = None
        self.build_pending = None
        self.build_profile = None
        self.set_soundtrack_buttons()
        self.gameplay_preview_update()
        return page

    @staticmethod
    def gameplay_preview_format_time(milliseconds):
        seconds = max(0, int(milliseconds) // 1000)
        return f'{seconds // 60:02d}:{seconds % 60:02d}'

    def gameplay_preview_position(self, position):
        if hasattr(self, 'gameplay_preview_seek'):
            if not self.gameplay_preview_seek.isSliderDown():
                self.gameplay_preview_seek.setValue(position)
            self.gameplay_preview_time.setText(
                f'{self.gameplay_preview_format_time(position)} / '
                f'{self.gameplay_preview_format_time(self.gameplay_preview_player.duration())}')

    def gameplay_preview_duration(self, duration):
        if hasattr(self, 'gameplay_preview_seek'):
            self.gameplay_preview_seek.setRange(0, max(0, duration))
            self.gameplay_preview_seek.setEnabled(duration > 0)
            self.gameplay_preview_position(self.gameplay_preview_player.position())

    def gameplay_preview_set_status(self, message):
        """Display preview diagnostics without reserving an empty row."""
        self.gameplay_preview_status.setText(message)
        self.gameplay_preview_status.setVisible(bool(message.strip()))

    def gameplay_preview_selected_source(self):
        row = self.song_table.currentRow()
        item = self.song_table.item(row, 0) if row >= 0 else None
        selected_rows = self.song_table.selectionModel().selectedRows()
        if not selected_rows:
            return None
        if item is None or not item.isSelected():
            item = self.song_table.item(min(index.row() for index in selected_rows), 0)
        if item is None:
            return None
        ref = item.data(Qt.UserRole)
        if not isinstance(ref, str):
            return None
        # Catalog references are relative to STREAMS and begin with music/.
        # Do not accept absolute paths, parent traversal, or unexpected extensions.
        normalized = ref.replace('\\', '/').strip()
        parts = normalized.split('/')
        if len(parts) < 3 or parts[0].casefold() != 'music' or any(
                part in ('', '.', '..') for part in parts):
            return None
        base = (self.root / 'STREAMS' / 'Music').resolve()
        relative = Path(*parts[1:]).with_suffix('.rsm')
        candidate = base / relative
        if candidate.is_file():
            return candidate
        # Original archives sometimes vary only in filename capitalization.
        current = base
        for part in relative.parts:
            if not current.is_dir():
                return None
            matches = [entry for entry in current.iterdir() if entry.name.casefold() == part.casefold()]
            if len(matches) != 1:
                return None
            current = matches[0]
        return current if current.is_file() and current.resolve().is_relative_to(base) else None

    def gameplay_preview_selection_changed(self):
        self.gameplay_preview_stop()
        self.gameplay_preview_update()

    def gameplay_preview_update(self, *_):
        button = getattr(self, 'gameplay_preview_play_button', None)
        if button is None:
            return
        selected = self.gameplay_preview_selected_source()
        button.setEnabled(selected is not None and self.gameplay_preview_process is None)
        button.setText('Pause' if self.gameplay_preview_player.playbackState() == QMediaPlayer.PlayingState
                       else 'Play / Resume')
        self.gameplay_preview_stop_button.setEnabled(
            self.gameplay_preview_source is not None or self.gameplay_preview_process is not None)

    def gameplay_preview_toggle(self):
        source = self.gameplay_preview_selected_source()
        if source is None:
            self.gameplay_preview_set_status('The selected soundtrack RSM file could not be found.')
            return
        if (self.gameplay_preview_source == source and self.gameplay_preview_temp is not None
                and self.gameplay_preview_player.source().isValid()):
            if self.gameplay_preview_player.playbackState() == QMediaPlayer.PlayingState:
                self.gameplay_preview_player.pause()
            else:
                self.gameplay_preview_player.play()
            return
        if self.gameplay_preview_process is not None:
            return
        decoder = self.root / 'supporting_tools' / 'rsm_decoder.py'
        if not decoder.is_file():
            self.gameplay_preview_set_status('Missing supporting_tools/rsm_decoder.py')
            return
        self.gameplay_preview_stop()
        self.gameplay_preview_source = source
        self.gameplay_preview_temp = tempfile.TemporaryDirectory(prefix='mc3_gameplay_preview_')
        output = Path(self.gameplay_preview_temp.name) / 'gameplay_preview.wav'
        process = QProcess(self)
        self.gameplay_preview_process = process
        process.setProgram(sys.executable)
        process.setArguments([str(decoder), str(source), str(output), '--full'])
        process.setWorkingDirectory(str(self.root))
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.finished.connect(lambda code, status, proc=process, wav=output:
                                 self.gameplay_preview_decoded(proc, wav, code, status))
        process.errorOccurred.connect(lambda error, proc=process: self.gameplay_preview_decode_error(proc, error))
        self.gameplay_preview_set_status(f'Decoding {source.name}…')
        self.gameplay_preview_update()
        process.start()

    def gameplay_preview_decoded(self, process, output, code, status):
        if process is not self.gameplay_preview_process:
            process.deleteLater()
            return
        message = bytes(process.readAllStandardOutput()).decode('utf-8', errors='replace').strip()
        self.gameplay_preview_process = None
        process.deleteLater()
        if status != QProcess.NormalExit or code != 0 or not output.is_file():
            self.gameplay_preview_set_status('RSM decoding failed: ' + (message[-300:] if message else str(code)))
            self.gameplay_preview_update()
            return
        self.gameplay_preview_player.setSource(QUrl.fromLocalFile(str(output)))
        self.gameplay_preview_set_status('')
        self.gameplay_preview_player.play()
        self.gameplay_preview_update()

    def gameplay_preview_decode_error(self, process, error):
        if process is self.gameplay_preview_process and error == QProcess.FailedToStart:
            self.gameplay_preview_process = None
            self.gameplay_preview_set_status('Unable to start the Python RSM decoder.')
            process.deleteLater()
            self.gameplay_preview_update()

    def gameplay_preview_stop(self):
        self.gameplay_preview_player.stop()
        self.gameplay_preview_player.setSource(QUrl())
        if hasattr(self, 'gameplay_preview_seek'):
            self.gameplay_preview_seek.setRange(0, 0)
            self.gameplay_preview_seek.setEnabled(False)
            self.gameplay_preview_time.setText('00:00 / 00:00')
        process = self.gameplay_preview_process
        if process is not None:
            self.gameplay_preview_process = None
            process.kill()
            process.deleteLater()
        if self.gameplay_preview_temp is not None:
            self.gameplay_preview_temp.cleanup()
            self.gameplay_preview_temp = None
        self.gameplay_preview_source = None
        if hasattr(self, 'gameplay_preview_status'):
            self.gameplay_preview_set_status('')
        self.gameplay_preview_update()

    def gameplay_preview_error(self, error, message):
        if error != QMediaPlayer.NoError and hasattr(self, 'gameplay_preview_status'):
            self.gameplay_preview_set_status('Audio playback error: ' + message)

    def filter_soundtrack(self):
        if hasattr(self, 'gameplay_preview_player'):
            self.gameplay_preview_stop()
        if not hasattr(self,'song_table'): return
        key = self.song_filter.currentData()
        self.song_table.setRowCount(0)
        names = {'dancehall':'Dancehall','drum-and-bass':'Drum and Bass','hip-hop':'Hip-Hop','rock':'Rock','techno':'Techno','garage-shop':'Garage Shop'}
        for song in self.soundtrack_songs:
            if key != 'all' and song['genre'] != key: continue
            search = self.song_search.text().strip().casefold()
            if search and search not in (song['title'] + ' ' + song['ref']).casefold(): continue
            row = self.song_table.rowCount(); self.song_table.insertRow(row)
            item = QTableWidgetItem(song['title']); item.setData(Qt.UserRole,song['ref'])
            self.song_table.setItem(row,0,item)
            self.song_table.setItem(row,1,QTableWidgetItem(names.get(song['genre'],song['genre'])))
        self.song_status.setText(f'{self.song_table.rowCount()} displayed / {len(self.soundtrack_songs)} total song(s).')
        self.set_soundtrack_buttons()

    def soundtrack_ready(self):
        return (self.profile_verified and not self.soundtrack_busy and not self.extraction_busy
                and (self.root/'ASSETS').is_dir() and (self.root/'STREAMS'/'Music').is_dir()
                and (self.root/'supporting_tools'/'manage_gameplay_soundtrack.py').is_file())

    def set_soundtrack_buttons(self):
        ready = self.soundtrack_ready()
        self.song_load_button.setEnabled(ready)
        selected = bool(self.song_table.selectionModel().selectedRows())
        self.song_remove.setEnabled(ready and selected)
        self.genre_remove.setEnabled(ready and self.genre_selector.currentData() is not None)
        self.genre_selector.setEnabled(ready)
        self.song_filter.setEnabled(ready)
        self.song_search.setEnabled(ready)

    def start_soundtrack_process(self, script, args, stage):
        self.soundtrack_busy = True; self.soundtrack_stage = stage
        if stage in ('check', 'apply'):
            self.soundtrack_progress.setRange(0, 0)  # Busy until the engine finishes.
            self.soundtrack_state.setText('Previewing soundtrack removal…' if stage == 'check' else 'Applying soundtrack removal…')
        self.set_soundtrack_buttons()
        self.soundtrack_process = QProcess(self)
        self.soundtrack_process.setWorkingDirectory(str(self.root))
        self.soundtrack_process.setProgram(sys.executable)
        self.soundtrack_process.setArguments(['-u', str(script), *args, '--root', str(self.root)] if script.name == 'manage_gameplay_soundtrack.py' else ['-u', str(script), '--root', str(self.root)])
        self.soundtrack_process.setProcessChannelMode(QProcess.MergedChannels)
        self.soundtrack_buffer = ''
        self.soundtrack_process.readyReadStandardOutput.connect(self.soundtrack_output)
        self.soundtrack_process.finished.connect(self.soundtrack_finished)
        self.soundtrack_process.errorOccurred.connect(self.soundtrack_error)
        self.soundtrack_process.start()

    def soundtrack_output(self):
        if not self.soundtrack_process: return
        chunk = bytes(self.soundtrack_process.readAllStandardOutput()).decode('utf-8', errors='replace')
        self.soundtrack_buffer += chunk
        if self.soundtrack_stage != 'catalog':
            for line in chunk.splitlines():
                if line.strip(): self.log(line)

    def soundtrack_error(self, error):
        if error == QProcess.FailedToStart:
            self.log('ERROR: Soundtrack Python process failed to start.')
            self.soundtrack_busy = False; self.set_soundtrack_buttons()
            if self.soundtrack_stage == 'catalog':
                self.dashboard_catalog_state = 'error'
                self.update_dashboard_metrics()
            self.soundtrack_state.setText('Could not start the soundtrack process.')
            if self.soundtrack_stage in ('check', 'apply'):
                self.soundtrack_progress.setRange(0, 100)
                self.soundtrack_progress.setValue(0)

    def load_soundtrack(self):
        if not self.soundtrack_ready():
            QMessageBox.warning(self, 'Workspace not verified', 'Wait for successful automatic profile verification and check the extracted workspace.')
            return
        self.song_status.setText('Loading song catalog…')
        self.dashboard_catalog_state = 'loading'
        self.update_dashboard_metrics()
        self.start_soundtrack_process(Path(__file__).with_name('soundtrack_catalog.py'), [], 'catalog')

    def preview_soundtrack(self, scope):
        if not self.soundtrack_ready():
            QMessageBox.warning(self, 'Workspace not ready', 'A verified extracted workspace is required.')
            return
        if scope == 'song':
            rows = sorted(index.row() for index in self.song_table.selectionModel().selectedRows())
            items = [self.song_table.item(row, 0) for row in rows]
            items = [item for item in items if item is not None and item.data(Qt.UserRole)]
            refs = list(dict.fromkeys(item.data(Qt.UserRole) for item in items))
            if not refs: return
            args = ['check', 'songs', *refs]
            target = f'{len(refs)} selected song(s):\n' + '\n'.join(item.text() for item in items)
        elif scope == 'genre':
            category = self.genre_selector.currentData()
            if category is None: return
            args = ['check', 'all'] if category == 'all' else ['check', 'genre', category]
            target = f'category: {self.genre_selector.currentText()}'
        else:
            args = ['check', 'all']
            target = 'ALL gameplay and Garage Shop music'
        self.soundtrack_target = (args[1:], target)
        self.soundtrack_progress.setRange(0, 100)
        self.soundtrack_progress.setValue(0)
        self.soundtrack_state.setText('Running read-only preview: ' + target)
        self.log('Soundtrack removal preview started: ' + target)
        self.start_soundtrack_process(self.root/'supporting_tools'/'manage_gameplay_soundtrack.py', args, 'check')

    def soundtrack_finished(self, code, status):
        self.soundtrack_output()
        stage = self.soundtrack_stage
        output = self.soundtrack_buffer
        self.soundtrack_busy = False
        self.set_soundtrack_buttons()
        if stage in ('check', 'apply'):
            self.soundtrack_progress.setRange(0, 100)
            self.soundtrack_progress.setValue(100 if status == QProcess.NormalExit and code == 0 else 0)
        if status != QProcess.NormalExit or code != 0:
            self.soundtrack_state.setText(f'{stage} failed; no further actions will run.')
            self.log(f'ERROR: Soundtrack {stage} failed (exit code {code}). Output: {output[-3500:]}')
            if stage == 'catalog':
                self.song_status.setText('Catalog failed; see Activity Log for details.')
                self.dashboard_catalog_state = 'error'
                self.update_dashboard_metrics()
            if stage == 'apply':
                QMessageBox.critical(self, 'Removal failed', 'The operation failed. Inspect the Activity Log and workspace before retrying.')
            return
        if stage == 'catalog':
            try:
                marker = 'MC3_CATALOG_JSON:'
                payload = next((line[len(marker):] for line in output.splitlines() if line.startswith(marker)),None)
                if payload is None: raise ValueError('Catalog result marker not found')
                data = json.loads(payload)
                if not isinstance(data,list): raise ValueError('Invalid catalog data')
                for item in data:
                    if not isinstance(item,dict) or not all(isinstance(item.get(k),str) for k in ('ref','title','genre')):
                        raise ValueError('Invalid catalog entry')
                self.soundtrack_songs = data
                self.dashboard_catalog_state = 'ready'
                self.filter_soundtrack()
                self.custom_update_current_tracks()
                self.log(f'Loaded {len(data)} soundtrack entries (read-only).')
            except (ValueError, TypeError) as exc:
                self.soundtrack_songs = []
                self.dashboard_catalog_state = 'error'
                self.filter_soundtrack()
                self.song_status.setText('Catalog failed; inspect Activity Log.')
                self.log(f'ERROR: Soundtrack catalog: {exc}; process output: {output[-1800:]}')
            self.update_dashboard_metrics()
            self.set_soundtrack_buttons()
        elif stage == 'check':
            self.soundtrack_progress.setValue(0)
            args, target = self.soundtrack_target
            self.soundtrack_state.setText('Preview completed. No files changed.')
            reply = QMessageBox.warning(self, 'Confirm soundtrack removal',
                'Preview succeeded for ' + target + '.\n\n'
                'Applying may DELETE RSM audio and MODIFY playlists and metadata.\n'
                'Back up ASSETS and STREAMS before proceeding.\n\n'
                'Apply these changes?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.log('Confirmed soundtrack removal: ' + target)
                self.soundtrack_state.setText('Applying changes: ' + target)
                self.start_soundtrack_process(self.root/'supporting_tools'/'manage_gameplay_soundtrack.py', ['apply', *args], 'apply')
            else:
                self.log('Soundtrack removal cancelled; preview only.')
                self.soundtrack_progress.setValue(0)
        elif stage == 'apply':
            self.soundtrack_state.setText('Removal completed. Refreshing the current soundtrack…')
            self.log('Soundtrack changes applied. Automatically refreshing the catalog…')
            # Keep the existing catalog visible until its replacement loads. The
            # current genre filter and search text are preserved by filter_soundtrack().
            # The catalog process runs asynchronously, keeping the GUI responsive.
            if self.soundtrack_ready():
                self.load_soundtrack()
                QMessageBox.information(self, 'Soundtrack updated',
                    'Removal completed. The soundtrack list is refreshing automatically.\n'
                    'Build a new ISO to use the changes in-game.')
            else:
                self.song_status.setText('Automatic refresh unavailable; check the workspace and refresh manually.')
                self.log('WARNING: Removal succeeded, but the catalog could not be refreshed automatically.')
                QMessageBox.warning(self, 'Soundtrack updated',
                    'Removal completed, but the catalog could not be refreshed automatically.\n'
                    'Check the Activity Log and refresh manually when the workspace is ready.')

    def custom_music_page(self):
        page = QWidget(); v = QVBoxLayout(page); v.setContentsMargins(0,0,0,0); v.setSpacing(9)
        heading = QLabel('Custom Gameplay and Garage Music'); heading.setObjectName('heading'); v.addWidget(heading)
        hint = QLabel('Update Gameplay and Garage Shop Music. Add MP3/WAV tracks by selecting a Genre or Garage Shop and drag/drop into the Staged Section. Artist and Song name MUST be filled.')
        hint.setObjectName('muted'); hint.setWordWrap(True); v.addWidget(hint)
        # One category filter controls both the installed and staged soundtracks.
        filter_row = QHBoxLayout()
        self.custom_genre = QComboBox()
        self.custom_genres = [('Dancehall','1_Dancehall'),('Drum and Bass','1_Drum_N_Bass'),('Hip-Hop','1_HipHop'),('Rock','1_Rock'),('Techno','1_Techno'),('Garage Shop','1_The_Garage_Shop')]
        self.custom_genre.addItem('All', None)
        for label, folder in self.custom_genres: self.custom_genre.addItem(label, folder)
        self.custom_genre.currentIndexChanged.connect(self.custom_refresh)
        filter_row.addWidget(QLabel('Genre:'))
        filter_row.addWidget(self.custom_genre, 1)
        v.addLayout(filter_row)

        columns = QHBoxLayout()
        columns.setSpacing(12)
        current_card, current_cv = self.panel('Current Gameplay Tracks')
        self.custom_current_table = QTableWidget(0, 2)
        apply_soundtrack_selection_theme(self.custom_current_table)
        self.custom_current_table.setHorizontalHeaderLabels(['Artist - Song', 'Genre'])
        self.custom_current_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.custom_current_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.custom_current_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.custom_current_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.custom_current_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.custom_current_table.verticalHeader().setVisible(False)
        current_cv.addWidget(self.custom_current_table, 1)
        self.custom_current_count = QLabel('Loading current soundtrack catalog…')
        self.custom_current_count.setObjectName('muted')
        current_cv.addWidget(self.custom_current_count)
        self.custom_current_table.itemSelectionChanged.connect(self.custom_preview_selection_changed)
        controls = QHBoxLayout()
        self.custom_preview_play_button = QPushButton('Play / Resume')
        self.custom_preview_play_button.clicked.connect(self.custom_preview_toggle)
        controls.addWidget(self.custom_preview_play_button, 1)
        self.custom_preview_stop_button = QPushButton('Stop')
        self.custom_preview_stop_button.clicked.connect(self.custom_preview_stop)
        controls.addWidget(self.custom_preview_stop_button, 1)
        current_cv.addLayout(controls)
        self.custom_preview_seek = QSlider(Qt.Horizontal)
        self.custom_preview_seek.setRange(0, 0)
        self.custom_preview_seek.setEnabled(False)
        self.custom_preview_seek.sliderMoved.connect(self.custom_preview_player.setPosition)
        current_cv.addWidget(self.custom_preview_seek)
        self.custom_preview_time = QLabel('00:00 / 00:00')
        self.custom_preview_time.setObjectName('muted')
        current_cv.addWidget(self.custom_preview_time)
        self.custom_preview_status = QLabel('')
        self.custom_preview_status.setObjectName('muted')
        self.custom_preview_status.setWordWrap(True)
        self.custom_preview_status.hide()
        current_cv.addWidget(self.custom_preview_status)
        self.custom_preview_update()
        columns.addWidget(current_card, 1)

        card, cv = self.panel('Staged Gameplay Soundtracks')
        self.custom_add_button = QPushButton('Add MP3/WAV…')
        self.custom_add_button.clicked.connect(self.custom_add)
        self.custom_table = StagedMusicTable(self)
        self.custom_table.setHorizontalHeaderLabels(['Artist Name','Song Name','Genre'])
        self.custom_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        self.custom_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.Stretch)
        self.custom_table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeToContents)
        self.custom_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.custom_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.custom_table.itemChanged.connect(self.custom_rename_item)
        self.custom_table.setToolTip('Drag MP3/WAV files from File Explorer onto this table to stage them in the selected category.')
        cv.addWidget(self.custom_table,1)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.custom_add_button, 1)
        remove = QPushButton('Remove Staged Track')
        remove.clicked.connect(self.custom_remove)
        row.addWidget(remove, 1)
        cv.addLayout(row)
        # Keep the processing feedback and final action at the bottom of the
        # staged panel, rather than in a separate Process Custom Music card.
        self.custom_state = QLabel('Ready to inspect staged music.')
        self.custom_state.setObjectName('muted')
        cv.addWidget(self.custom_state)
        self.custom_progress = QProgressBar()
        self.custom_progress.setRange(0, 3)
        self.custom_progress.setValue(0)
        cv.addWidget(self.custom_progress)
        self.custom_run = QPushButton('Add Tracks')
        self.custom_run.setObjectName('primary')
        self.custom_run.clicked.connect(self.custom_begin)
        cv.addWidget(self.custom_run)
        columns.addWidget(card, 1)
        v.addLayout(columns, 1)
        self.custom_refresh()
        return page

    def custom_folder(self):
        folder = self.custom_genre.currentData()
        return self.root / 'Custom Music' / folder if folder else None

    def custom_refresh(self, *_):
        category = self.custom_genre.currentData()
        self.custom_add_button.setEnabled(category is not None and not self.custom_busy)
        folders = [(label, folder) for label, folder in self.custom_genres if category is None or folder == category]
        if not hasattr(self, 'custom_partial_metadata'):
            self.custom_partial_metadata = {}
        entries = []
        for label, folder in folders:
            path = self.root / 'Custom Music' / folder
            if path.is_dir():
                entries.extend((label, p) for p in path.iterdir()
                               if p.is_file() and p.suffix.lower() in ('.mp3','.wav'))
        entries.sort(key=lambda entry:(entry[0].casefold(), entry[1].name.casefold()))
        self.custom_update_current_tracks()
        self.custom_table.blockSignals(True)
        try:
            self.custom_table.setRowCount(0)
            for label, file in entries:
                row = self.custom_table.rowCount(); self.custom_table.insertRow(row)
                if ' - ' in file.stem:
                    artist, song = file.stem.split(' - ', 1)
                else:
                    # One-field filenames default to Artist; remember Song-only
                    # edits within this GUI session because the filename alone
                    # cannot distinguish the two columns.
                    artist, song = self.custom_partial_metadata.get(str(file), (file.stem, ''))
                for column, value in ((0,artist),(1,song)):
                    item = QTableWidgetItem(value)
                    item.setData(Qt.UserRole, str(file))
                    item.setToolTip(file.name)
                    self.custom_table.setItem(row,column,item)
                category_item = QTableWidgetItem(label)
                category_item.setFlags(category_item.flags() & ~Qt.ItemIsEditable)
                category_item.setData(Qt.UserRole, str(file))
                self.custom_table.setItem(row,2,category_item)
        finally:
            self.custom_table.blockSignals(False)
        if hasattr(self,'custom_state') and not self.custom_busy:
            scope = 'all categories' if category is None else self.custom_genre.currentText()
            self.custom_state.setText(f'{len(entries)} staged file(s) in {scope}. Double-click Artist or Song to rename.')

    @staticmethod
    def custom_preview_format_time(milliseconds):
        seconds = max(0, int(milliseconds) // 1000)
        return f'{seconds // 60:02d}:{seconds % 60:02d}'

    def custom_preview_position(self, position):
        if hasattr(self, 'custom_preview_seek'):
            if not self.custom_preview_seek.isSliderDown():
                self.custom_preview_seek.setValue(position)
            self.custom_preview_time.setText(
                f'{self.custom_preview_format_time(position)} / '
                f'{self.custom_preview_format_time(self.custom_preview_player.duration())}')

    def custom_preview_duration(self, duration):
        if hasattr(self, 'custom_preview_seek'):
            self.custom_preview_seek.setRange(0, max(0, duration))
            self.custom_preview_seek.setEnabled(duration > 0)
            self.custom_preview_position(self.custom_preview_player.position())

    def custom_preview_set_status(self, message):
        """Display preview diagnostics without reserving an empty row."""
        self.custom_preview_status.setText(message)
        self.custom_preview_status.setVisible(bool(message.strip()))

    def custom_preview_selected_source(self):
        row = self.custom_current_table.currentRow()
        item = self.custom_current_table.item(row, 0) if row >= 0 else None
        if item is None or not self.custom_current_table.selectedItems():
            return None
        ref = item.data(Qt.UserRole)
        if not isinstance(ref, str):
            return None
        # Catalog references are relative to STREAMS and begin with music/.
        # Do not accept absolute paths, parent traversal, or unexpected extensions.
        normalized = ref.replace('\\', '/').strip()
        parts = normalized.split('/')
        if len(parts) < 3 or parts[0].casefold() != 'music' or any(
                part in ('', '.', '..') for part in parts):
            return None
        base = (self.root / 'STREAMS' / 'Music').resolve()
        relative = Path(*parts[1:]).with_suffix('.rsm')
        candidate = base / relative
        if candidate.is_file():
            return candidate
        # Original archives sometimes vary only in filename capitalization.
        current = base
        for part in relative.parts:
            if not current.is_dir():
                return None
            matches = [entry for entry in current.iterdir() if entry.name.casefold() == part.casefold()]
            if len(matches) != 1:
                return None
            current = matches[0]
        return current if current.is_file() and current.resolve().is_relative_to(base) else None

    def custom_preview_selection_changed(self):
        self.custom_preview_stop()
        self.custom_preview_update()

    def custom_preview_update(self, *_):
        button = getattr(self, 'custom_preview_play_button', None)
        if button is None:
            return
        selected = self.custom_preview_selected_source()
        button.setEnabled(selected is not None and self.custom_preview_process is None)
        button.setText('Pause' if self.custom_preview_player.playbackState() == QMediaPlayer.PlayingState
                       else 'Play / Resume')
        self.custom_preview_stop_button.setEnabled(
            self.custom_preview_source is not None or self.custom_preview_process is not None)

    def custom_preview_toggle(self):
        source = self.custom_preview_selected_source()
        if source is None:
            self.custom_preview_set_status('The selected soundtrack RSM file could not be found.')
            return
        if (self.custom_preview_source == source and self.custom_preview_temp is not None
                and self.custom_preview_player.source().isValid()):
            if self.custom_preview_player.playbackState() == QMediaPlayer.PlayingState:
                self.custom_preview_player.pause()
            else:
                self.custom_preview_player.play()
            return
        if self.custom_preview_process is not None:
            return
        decoder = self.root / 'supporting_tools' / 'rsm_decoder.py'
        if not decoder.is_file():
            self.custom_preview_set_status('Missing supporting_tools/rsm_decoder.py')
            return
        self.custom_preview_stop()
        self.custom_preview_source = source
        self.custom_preview_temp = tempfile.TemporaryDirectory(prefix='mc3_custom_preview_')
        output = Path(self.custom_preview_temp.name) / 'custom_preview.wav'
        process = QProcess(self)
        self.custom_preview_process = process
        process.setProgram(sys.executable)
        process.setArguments([str(decoder), str(source), str(output), '--full'])
        process.setWorkingDirectory(str(self.root))
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.finished.connect(lambda code, status, proc=process, wav=output:
                                 self.custom_preview_decoded(proc, wav, code, status))
        process.errorOccurred.connect(lambda error, proc=process: self.custom_preview_decode_error(proc, error))
        self.custom_preview_set_status(f'Decoding {source.name}…')
        self.custom_preview_update()
        process.start()

    def custom_preview_decoded(self, process, output, code, status):
        if process is not self.custom_preview_process:
            process.deleteLater()
            return
        message = bytes(process.readAllStandardOutput()).decode('utf-8', errors='replace').strip()
        self.custom_preview_process = None
        process.deleteLater()
        if status != QProcess.NormalExit or code != 0 or not output.is_file():
            self.custom_preview_set_status('RSM decoding failed: ' + (message[-300:] if message else str(code)))
            self.custom_preview_update()
            return
        self.custom_preview_player.setSource(QUrl.fromLocalFile(str(output)))
        self.custom_preview_set_status('')
        self.custom_preview_player.play()
        self.custom_preview_update()

    def custom_preview_decode_error(self, process, error):
        if process is self.custom_preview_process and error == QProcess.FailedToStart:
            self.custom_preview_process = None
            self.custom_preview_set_status('Unable to start the Python RSM decoder.')
            process.deleteLater()
            self.custom_preview_update()

    def custom_preview_stop(self):
        self.custom_preview_player.stop()
        self.custom_preview_player.setSource(QUrl())
        if hasattr(self, 'custom_preview_seek'):
            self.custom_preview_seek.setRange(0, 0)
            self.custom_preview_seek.setEnabled(False)
            self.custom_preview_time.setText('00:00 / 00:00')
        process = self.custom_preview_process
        if process is not None:
            self.custom_preview_process = None
            process.kill()
            process.deleteLater()
        if self.custom_preview_temp is not None:
            self.custom_preview_temp.cleanup()
            self.custom_preview_temp = None
        self.custom_preview_source = None
        if hasattr(self, 'custom_preview_status'):
            self.custom_preview_set_status('')
        self.custom_preview_update()

    def custom_preview_error(self, error, message):
        if error != QMediaPlayer.NoError and hasattr(self, 'custom_preview_status'):
            self.custom_preview_set_status('Audio playback error: ' + message)

    def custom_update_current_tracks(self):
        """Read-only view of the existing catalog, filtered by the shared category."""
        if not hasattr(self, 'custom_current_table'):
            return
        genre_keys = {
            '1_Dancehall': 'dancehall',
            '1_Drum_N_Bass': 'drum-and-bass',
            '1_HipHop': 'hip-hop',
            '1_Rock': 'rock',
            '1_Techno': 'techno',
            '1_The_Garage_Shop': 'garage-shop',
        }
        category = self.custom_genre.currentData()
        key = genre_keys.get(category) if category else None
        table = self.custom_current_table
        self.custom_preview_stop()
        table.setRowCount(0)
        names = {v: k for k, v in [
            ('Dancehall', 'dancehall'), ('Drum and Bass', 'drum-and-bass'),
            ('Hip-Hop', 'hip-hop'), ('Rock', 'rock'), ('Techno', 'techno'),
            ('Garage Shop', 'garage-shop')]}
        for song in self.soundtrack_songs:
            if key is not None and song['genre'] != key:
                continue
            row = table.rowCount()
            table.insertRow(row)
            title = QTableWidgetItem(song['title'])
            title.setData(Qt.UserRole, song['ref'])
            table.setItem(row, 0, title)
            table.setItem(row, 1, QTableWidgetItem(names.get(song['genre'], song['genre'])))
        self.custom_preview_update()
        self.custom_current_count.setText(f'{table.rowCount()} current soundtrack(s)' if self.soundtrack_songs
                                          else 'No soundtrack catalog loaded yet.')

    def custom_rename_item(self, item):
        if item.column() not in (0, 1): return
        old = Path(item.data(Qt.UserRole) or '')
        if not old.is_file():
            QMessageBox.warning(self, 'File missing', 'The staged file no longer exists. Refreshing the list.')
            self.custom_refresh(); return
        row = item.row()
        artist = self.custom_table.item(row, 0).text().strip()
        song = self.custom_table.item(row, 1).text().strip()
        # Exactly one field may be empty. Both empty is never valid.
        if not artist and not song:
            QMessageBox.warning(self, 'Invalid song details',
                'Artist Name and Song Name cannot both be blank. At least one is required.')
            self.custom_refresh(); return
        invalid = set('<>:"/\\|?*')
        def valid(value):
            return (not value or (not any(c in invalid or ord(c) < 32 for c in value)
                                  and not value.endswith(('.', ' '))
                                  and value not in ('.', '..')))
        if not valid(artist) or not valid(song):
            QMessageBox.warning(self, 'Invalid song details',
                'Windows filename characters \\ / : * ? " < > | are not allowed. '
                'Names also cannot end with a period or space.')
            self.custom_refresh(); return
        if self.custom_busy or self.title_busy or self.build_busy or self.extraction_busy or self.race_busy or self.soundtrack_busy:
            QMessageBox.warning(self, 'Processing in progress', 'Wait for processing to finish before renaming files.')
            self.custom_refresh(); return
        # A one-field entry retains its single-name filename; two populated
        # fields use the established Artist - Song convention.
        stem = f'{artist} - {song}' if artist and song else (artist or song)
        dest = old.with_name(f'{stem}{old.suffix}')
        if dest.exists() and dest != old:
            QMessageBox.warning(self, 'Filename already exists',
                f'Cannot rename because {dest.name} already exists.')
            self.custom_refresh(); return
        try:
            if dest != old:
                old.rename(dest)
                self.log(f'Renamed staged music: {old.name} -> {dest.name}')
            if not hasattr(self, 'custom_partial_metadata'):
                self.custom_partial_metadata = {}
            self.custom_partial_metadata.pop(str(old), None)
            if not (artist and song):
                self.custom_partial_metadata[str(dest)] = (artist, song)
        except OSError as exc:
            QMessageBox.critical(self, 'Rename failed', str(exc))
        self.custom_refresh()

    def custom_add(self):
        if self.custom_busy or self.title_busy or self.build_busy or self.extraction_busy or self.race_busy or self.soundtrack_busy: return
        folder = self.custom_folder()
        if folder is None: return
        is_theme = self.custom_genre.currentData() == '3_Theme Song'
        if is_theme:
            filename,_ = QFileDialog.getOpenFileName(self,'Select one title theme',str(self.root),'Audio (*.mp3 *.wav)')
            files = [filename] if filename else []
        else:
            files,_ = QFileDialog.getOpenFileNames(self,'Select custom gameplay music',str(self.root),'Audio (*.mp3 *.wav)')
        if not files: return
        self.custom_stage_files(files)

    def custom_stage_files(self, files):
        """Shared file-picker / Explorer-drop staging, preserving existing confirmations."""
        if self.custom_busy or self.title_busy or self.build_busy or self.extraction_busy or self.race_busy or self.soundtrack_busy:
            return
        folder = self.custom_folder()
        if folder is None:
            return
        is_theme = self.custom_genre.currentData() == '3_Theme Song'
        files = [str(f) for f in files if str(f) and Path(f).is_file() and Path(f).suffix.lower() in ('.mp3', '.wav')]
        if not files:
            return
        if is_theme and len(files) != 1:
            QMessageBox.warning(self, 'One title theme only', 'Drop or select exactly one MP3/WAV file for Title Theme.')
            return
        folder.mkdir(parents=True,exist_ok=True)
        if is_theme:
            existing = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in ('.mp3','.wav')]
            if existing and QMessageBox.question(self,'Replace staged title theme',
                'Only one title theme can be processed. Replace the existing staged theme file?',
                QMessageBox.Yes|QMessageBox.No,QMessageBox.No) != QMessageBox.Yes: return
            # Copy first; only remove other staged themes after the copy succeeds.
        for filename in files:
            source = Path(filename); dest = folder/source.name
            if source.resolve() == dest.resolve(): continue
            if dest.exists() and QMessageBox.question(self,'Replace staged file',f'Replace {dest.name}?',
                    QMessageBox.Yes|QMessageBox.No,QMessageBox.No) != QMessageBox.Yes: continue
            try:
                shutil.copy2(source,dest)
                if is_theme:
                    for old in existing:
                        if old != dest: old.unlink()
                self.log(f'Staged {self.custom_genre.currentText()}: {dest.name}')
            except OSError as exc:
                QMessageBox.critical(self,'Cannot stage music',str(exc)); break
        self.custom_refresh()

    def custom_remove(self):
        if self.custom_busy or self.title_busy or self.build_busy or self.extraction_busy or self.race_busy or self.soundtrack_busy: return
        selected = []
        for index in self.custom_table.selectionModel().selectedRows():
            item = self.custom_table.item(index.row(),2)
            if item:
                selected.append(Path(item.data(Qt.UserRole)))
        if not selected: return
        if QMessageBox.question(self,'Remove staged music',
            'Remove selected files from Custom Music staging?\n\n'+'\n'.join(p.name for p in selected),
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No) != QMessageBox.Yes: return
        for file in selected:
            try:
                file.unlink()
                self.log(f'Removed staged music: {file.name}')
            except OSError as exc: QMessageBox.critical(self,'Cannot remove file',str(exc))
        self.custom_refresh()

    def custom_begin(self):
        if self.custom_busy or self.title_busy or self.build_busy or self.extraction_busy or self.race_busy or self.soundtrack_busy: return
        if not self.profile_verified:
            QMessageBox.warning(self,'Profile not verified','Wait for automatic SHA-256 verification.'); return
        if not all((self.root/name).is_dir() for name in ('ASSETS','STREAMS','ISO_FILES')):
            QMessageBox.warning(self,'Workspace incomplete','Extract and validate the ISO before processing music.'); return
        tools = self.root/'supporting_tools'
        scripts = ['add_gameplay_songs.py','register_song_playlists.py','register_song_metadata.py']
        missing = [x for x in scripts if not (tools/x).is_file()]
        if missing:
            QMessageBox.warning(self,'Missing processing utility',', '.join(missing)); return
        counts = {}
        for name,folder in self.custom_genres:
            path = self.root/'Custom Music'/folder
            counts[name] = len([p for p in path.iterdir() if p.is_file() and p.suffix.lower() in ('.mp3','.wav')]) if path.is_dir() else 0
        if not any(counts.values()):
            QMessageBox.information(self,'No staged music','Add MP3/WAV files to at least one category first.'); return
        summary = '\n'.join(f'{name}: {count}' for name,count in counts.items() if count)
        reply = QMessageBox.warning(self,'Confirm custom music processing',
            'The existing gameplay engine will run three stages in order:\n'
            '1. Convert gameplay music\n2. Register playlists\n3. Register metadata\n4. Update title theme\n\n'
            +summary+'\n\nBack up ASSETS and STREAMS before proceeding. Continue?',
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        if reply != QMessageBox.Yes: return
        self.custom_steps = list(zip(['Convert gameplay music','Register playlists','Register metadata'],scripts))
        self.custom_busy = True; self.custom_index = 0; self.custom_run.setEnabled(False)
        self.custom_progress.setValue(0)
        self.log('Custom music processing confirmed; starting existing four-stage pipeline.')
        self.custom_next()

    def custom_next(self):
        if not self.custom_busy: return
        if self.custom_index == len(self.custom_steps):
            self.custom_busy = False; self.custom_run.setEnabled(True)
            self.custom_state.setText('Processing completed. Build ISO to test in PCSX2.')
            self.log('SUCCESS: All three gameplay music processing stages completed.')
            # Refresh the shared catalog only after all processing stages succeed.
            # Its completion handler updates both gameplay soundtrack tables.
            if self.soundtrack_ready():
                self.log('Custom music completed. Refreshing gameplay soundtrack catalog…')
                self.load_soundtrack()
            else:
                self.log('WARNING: Automatic soundtrack refresh unavailable; use Refresh Soundtrack when ready.')
            QMessageBox.information(self,'Custom music complete','Processing completed successfully. Build a modified ISO to test in PCSX2.')
            return
        label,filename = self.custom_steps[self.custom_index]
        self.custom_state.setText(f'Stage {self.custom_index+1}/{len(self.custom_steps)}: {label}')
        self.log(f'CUSTOM MUSIC [{self.custom_index+1}/{len(self.custom_steps)}] {label}')
        process = QProcess(self)
        self.custom_process = process
        process.setWorkingDirectory(str(self.root))
        process.setProgram(sys.executable)
        process.setArguments(['-u',str(self.root/'supporting_tools'/filename),str(self.root), '--yes'])
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(self.custom_read)
        process.finished.connect(self.custom_finished)
        process.errorOccurred.connect(self.custom_error)
        process.start()

    def custom_read(self):
        if self.custom_process:
            chunk = bytes(self.custom_process.readAllStandardOutput()).decode('utf-8',errors='replace')
            for line in chunk.splitlines():
                if line.strip(): self.log(line.rstrip())

    def custom_finished(self,code,status):
        if not self.custom_busy: return
        self.custom_read()
        if status != QProcess.NormalExit or code != 0:
            self.custom_fail(f'Stage {self.custom_index+1} failed (exit code {code}).'); return
        self.custom_index += 1
        self.custom_progress.setValue(self.custom_index)
        self.custom_next()

    def custom_error(self,error):
        if error == QProcess.FailedToStart:
            self.custom_fail('Could not start the custom music processing utility.')

    def custom_fail(self,message):
        if not self.custom_busy: return
        self.custom_busy = False; self.custom_run.setEnabled(True)
        self.custom_state.setText('Processing failed — see Activity Log.')
        self.log('CUSTOM MUSIC FAILED: '+message)
        QMessageBox.critical(self,'Custom music processing failed',message+'\nLater stages were not run. Check the Activity Log.')

    def title_music_page(self):
        page = QWidget(); v = QVBoxLayout(page); v.setContentsMargins(0,0,0,0); v.setSpacing(10)
        h = QLabel('Title Theme Soundtrack'); h.setObjectName('heading'); v.addWidget(h)
        hint = QLabel("Replace the game's Main Menu theme song with a replacement MP3/WAV audio track")
        hint.setObjectName('muted'); hint.setWordWrap(True); v.addWidget(hint)
        card, cv = self.panel('Current Title Theme Soundtrack')
        self.title_preview_file = QLabel('Detecting current title theme…')
        self.title_preview_file.setObjectName('muted'); self.title_preview_file.setWordWrap(True)
        cv.addWidget(self.title_preview_file)
        preview_buttons = QHBoxLayout()
        self.title_preview_play = QPushButton('Play / Pause')
        self.title_preview_play.clicked.connect(self.title_preview_toggle)
        preview_buttons.addWidget(self.title_preview_play)
        stop = QPushButton('Stop'); stop.clicked.connect(self.title_preview_stop); preview_buttons.addWidget(stop)
        cv.addLayout(preview_buttons)
        self.title_preview_seek = QSlider(Qt.Horizontal); self.title_preview_seek.setRange(0, 0)
        self.title_preview_seek.sliderMoved.connect(self.title_preview_player.setPosition)
        cv.addWidget(self.title_preview_seek)
        self.title_preview_time = QLabel('00:00 / 00:00'); self.title_preview_time.setObjectName('muted')
        cv.addWidget(self.title_preview_time)
        # Only display status text for decoding, playback, or playlist errors.
        self.title_preview_status = QLabel('')
        self.title_preview_status.setObjectName('muted'); self.title_preview_status.setWordWrap(True)
        cv.addWidget(self.title_preview_status)
        v.addWidget(card)
        card, cv = self.panel('Replacement Title Theme Soundtrack')
        self.title_file_label = TitleThemeDropLabel(self); self.title_file_label.setWordWrap(True)
        cv.addWidget(self.title_file_label)
        buttons = QHBoxLayout()
        add = QPushButton('Select MP3/WAV…'); add.clicked.connect(self.title_add); buttons.addWidget(add)
        remove = QPushButton('Remove Staged Theme'); remove.clicked.connect(self.title_remove); buttons.addWidget(remove)
        cv.addLayout(buttons); v.addWidget(card)
        card, cv = self.panel('Process Title Music')
        note = QLabel('Runs only update_title_theme.py. Gameplay music, garage music, and their metadata processing are not rerun.')
        note.setObjectName('muted'); note.setWordWrap(True); cv.addWidget(note)
        self.title_state = QLabel('Ready.'); self.title_state.setObjectName('muted'); cv.addWidget(self.title_state)
        self.title_progress = QProgressBar(); self.title_progress.setRange(0,1); self.title_progress.setValue(0); cv.addWidget(self.title_progress)
        self.title_run = QPushButton('Update Title Music'); self.title_run.setObjectName('primary')
        self.title_run.clicked.connect(self.title_begin); cv.addWidget(self.title_run)
        v.addWidget(card); v.addStretch(1)
        self.title_refresh()
        return page

    @staticmethod
    def title_preview_clock(ms):
        seconds = max(0, int(ms) // 1000)
        return f'{seconds // 60:02d}:{seconds % 60:02d}'

    def title_preview_original(self):
        # Resolve the currently assigned theme from all four city playlists.
        try:
            reference, source = resolve_frontend_rsm(self.root)
        except FrontendPlaylistError as exc:
            self.title_preview_file.setText('Unable to detect current title theme')
            self.title_preview_status.setText(str(exc))
            return None
        self.title_preview_file.setText(Path(reference).name)
        self.title_preview_status.setText('')
        return source

    def title_preview_use_playlist(self):
        self.title_preview_stop()
        self.title_preview_manual = False
        self.title_preview_source = None
        self.title_preview_original()

    def title_preview_choose(self):
        filename, _ = QFileDialog.getOpenFileName(self, 'Choose RSM to preview', str(self.root), 'Rockstar RSM (*.rsm *.RSM)')
        if filename:
            self.title_preview_stop()
            self.title_preview_source = Path(filename)
            self.title_preview_manual = True
            self.title_preview_file.setText('Source: ' + str(self.title_preview_source))
            self.title_preview_status.setText('Ready to decode and preview.')

    def title_preview_toggle(self):
        state = self.title_preview_player.playbackState()
        if state == QMediaPlayer.PlayingState:
            self.title_preview_player.pause()
            return
        if self.title_preview_player.source().isValid() and self.title_preview_temp:
            self.title_preview_player.play()
            return
        if self.title_preview_process and self.title_preview_process.state() != QProcess.NotRunning:
            return
        source = self.title_preview_source if self.title_preview_manual else self.title_preview_original()
        if source is None or not source.is_file():
            if self.title_preview_manual:
                self.title_preview_status.setText('Selected RSM is missing. Choose another file or use the playlist.')
            return
        decoder = self.root / 'supporting_tools' / 'rsm_decoder.py'
        if not decoder.is_file():
            self.title_preview_status.setText('Missing supporting_tools/rsm_decoder.py')
            return
        self.title_preview_stop()
        self.title_preview_source = source
        self.title_preview_file.setText(source.stem)
        self.title_preview_temp = tempfile.TemporaryDirectory(prefix='mc3_title_preview_')
        output = Path(self.title_preview_temp.name) / 'title_preview.wav'
        process = QProcess(self); self.title_preview_process = process
        process.setProgram(sys.executable)
        process.setArguments([str(decoder), str(source), str(output), '--full'])
        process.setWorkingDirectory(str(self.root))
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.finished.connect(lambda code, status, proc=process, wav=output: self.title_preview_decoded(proc, wav, code, status))
        process.errorOccurred.connect(lambda error, proc=process: self.title_preview_decode_error(proc, error))
        self.title_preview_status.setText('Decoding RSM for playback…')
        self.title_preview_play.setEnabled(False)
        process.start()

    def title_preview_decoded(self, process, output, code, status):
        if process is not self.title_preview_process:
            process.deleteLater()
            return
        message = bytes(process.readAllStandardOutput()).decode('utf-8', errors='replace').strip()
        self.title_preview_process = None
        process.deleteLater()
        self.title_preview_play.setEnabled(True)
        if status != QProcess.NormalExit or code != 0 or not output.is_file():
            self.title_preview_status.setText('RSM decoding failed. ' + (message[-350:] if message else f'Exit code {code}'))
            return
        self.title_preview_player.setSource(QUrl.fromLocalFile(str(output)))
        self.title_preview_status.setText('')
        self.title_preview_player.play()

    def title_preview_decode_error(self, process, error):
        if process is self.title_preview_process and error == QProcess.FailedToStart:
            self.title_preview_status.setText('Could not start the Python RSM decoder.')
            self.title_preview_process = None
            self.title_preview_play.setEnabled(True)
            process.deleteLater()

    def title_preview_stop(self):
        self.title_preview_player.stop()
        self.title_preview_player.setSource(QUrl())
        process = self.title_preview_process
        if process is not None:
            self.title_preview_process = None
            process.kill()
            process.deleteLater()
        if self.title_preview_temp is not None:
            self.title_preview_temp.cleanup()
            self.title_preview_temp = None
        self.title_preview_seek.setRange(0, 0)
        self.title_preview_time.setText('00:00 / 00:00')
        self.title_preview_play.setEnabled(True)

    def title_preview_position(self, position):
        if not self.title_preview_seek.isSliderDown():
            self.title_preview_seek.setValue(position)
        self.title_preview_time.setText(self.title_preview_clock(position) + ' / ' +
                                        self.title_preview_clock(self.title_preview_player.duration()))

    def title_preview_duration(self, duration):
        self.title_preview_seek.setRange(0, max(0, duration))
        self.title_preview_position(self.title_preview_player.position())

    def title_preview_playback_state(self, state):
        self.title_preview_play.setText('Pause' if state == QMediaPlayer.PlayingState else 'Play / Resume')

    def title_preview_media_error(self, error, message):
        if error != QMediaPlayer.NoError:
            self.title_preview_status.setText('Audio playback error: ' + message)

    def title_folder(self):
        return self.root / 'Custom Music' / '3_Theme Song'

    def title_sources(self):
        folder = self.title_folder()
        return sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in ('.mp3','.wav')), key=lambda p:p.name.casefold()) if folder.is_dir() else []

    def title_refresh(self):
        files = self.title_sources()
        self.title_file_label.setText('Staged: ' + ', '.join(p.name for p in files) if files else 'Drag and drop MP3/WAV here...')
        if len(files) > 1:
            self.title_state.setText('More than one title theme staged. Remove extras before processing.')

    def title_add(self):
        if any((self.title_busy,self.custom_busy,self.build_busy,self.extraction_busy,self.race_busy,self.soundtrack_busy,self.loading_busy)): return
        filename, _ = QFileDialog.getOpenFileName(self,'Select one title theme',str(self.root),'Audio (*.mp3 *.wav)')
        if not filename: return
        self.title_stage_file(Path(filename))

    def title_stage_file(self, source):
        """Shared staging behavior for the file picker and Explorer drag/drop."""
        if any((self.title_busy,self.custom_busy,self.build_busy,self.extraction_busy,self.race_busy,self.soundtrack_busy,self.loading_busy)): return
        source = Path(source)
        if not source.is_file() or source.suffix.lower() not in ('.mp3', '.wav'):
            QMessageBox.warning(self, 'Unsupported audio', 'Select one existing MP3 or WAV file.')
            return
        folder = self.title_folder()
        existing = self.title_sources()
        if existing and QMessageBox.question(self,'Replace staged title theme',
            'Replace the existing staged title theme?', QMessageBox.Yes|QMessageBox.No,QMessageBox.No) != QMessageBox.Yes: return
        try:
            folder.mkdir(parents=True,exist_ok=True)
            dest = folder/source.name
            if source.resolve() != dest.resolve():
                shutil.copy2(source,dest)
            for old in existing:
                if old != dest: old.unlink()
            self.title_state.setText('Title theme staged. Ready to process.')
            self.log(f'Staged title theme: {dest.name}')
        except OSError as exc:
            QMessageBox.critical(self,'Cannot stage title theme',str(exc))
        self.title_refresh()

    def title_remove(self):
        if any((self.title_busy,self.custom_busy,self.build_busy,self.extraction_busy,self.race_busy,self.soundtrack_busy,self.loading_busy)): return
        files = self.title_sources()
        if not files: return
        if QMessageBox.question(self,'Remove staged title theme','Remove staged title theme file(s)?',
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No) != QMessageBox.Yes: return
        try:
            for file in files: file.unlink()
            self.log('Removed staged title theme.')
            self.title_state.setText('Ready.')
        except OSError as exc:
            QMessageBox.critical(self,'Cannot remove title theme',str(exc))
        self.title_refresh()

    def title_begin(self):
        if any((self.title_busy,self.custom_busy,self.build_busy,self.extraction_busy,self.race_busy,self.soundtrack_busy,self.loading_busy)): return
        if not self.profile_verified:
            QMessageBox.warning(self,'Profile not verified','Wait for automatic SHA-256 verification.'); return
        if not all((self.root/name).is_dir() for name in ('ASSETS','STREAMS','ISO_FILES')):
            QMessageBox.warning(self,'Workspace incomplete','Extract and validate the ISO before processing title music.'); return
        files = self.title_sources()
        if len(files) != 1:
            QMessageBox.warning(self,'Title theme required','Stage exactly one MP3/WAV file.'); return
        script = self.root/'supporting_tools'/'update_title_theme.py'
        if not script.is_file():
            QMessageBox.warning(self,'Missing utility',str(script)); return
        if QMessageBox.question(self,'Confirm title music update',
            f'Update the title theme using {files[0].name}?\n\nBack up ASSETS and STREAMS before proceeding.',
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No) != QMessageBox.Yes: return
        self.title_busy = True; self.title_run.setEnabled(False)
        self.title_progress.setValue(0); self.title_state.setText('Updating title theme…')
        process = QProcess(self); self.title_process = process
        process.setWorkingDirectory(str(self.root)); process.setProgram(sys.executable)
        process.setArguments(['-u',str(script),str(self.root),'--yes'])
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(self.title_read)
        process.finished.connect(self.title_finished)
        process.errorOccurred.connect(self.title_error)
        self.log('TITLE MUSIC: Starting independent title theme update.')
        process.start()

    def title_read(self):
        if self.title_process:
            chunk = bytes(self.title_process.readAllStandardOutput()).decode('utf-8',errors='replace')
            for line in chunk.splitlines():
                if line.strip(): self.log(line.rstrip())

    def title_finished(self,code,status):
        if not self.title_busy: return
        self.title_read()
        self.title_busy = False; self.title_run.setEnabled(True)
        if status == QProcess.NormalExit and code == 0:
            self.title_progress.setValue(1)
            self.title_state.setText('Title music updated. Build ISO to test in PCSX2.')
            self.title_preview_use_playlist()
            self.update_dashboard_metrics()
            self.log('SUCCESS: Title music updated independently.')
            QMessageBox.information(self,'Title music updated','Title music updated. Build a modified ISO to test in PCSX2.')
        else:
            self.title_state.setText('Title music processing failed — see Activity Log.')
            self.log(f'TITLE MUSIC FAILED: exit code {code}')
            QMessageBox.critical(self,'Title music processing failed',f'Utility exited with code {code}. Check the Activity Log.')

    def title_error(self,error):
        if error == QProcess.FailedToStart and self.title_busy:
            self.title_busy = False; self.title_run.setEnabled(True)
            self.title_state.setText('Could not start title music utility.')
            self.log('TITLE MUSIC FAILED: Process could not start.')
            QMessageBox.critical(self,'Title music processing failed','Could not start update_title_theme.py.')

    def race_music_page(self):
        page = QWidget(); v = QVBoxLayout(page); v.setContentsMargins(0,0,0,0); v.setSpacing(10)
        h = QLabel('Lose/Win (Race Transition) Music'); h.setObjectName('heading'); v.addWidget(h)
        info = QLabel('Update Lose or Win Tracks during Race-Over Transitions. Win Tracks are also used when entering a race or changing locations. Drag and drop MP3/WAV tracks to respective Staged Soundtracks section.')
        info.setWordWrap(True); info.setObjectName('muted'); v.addWidget(info)
        # Match Loading Screen Music: two clearly separated side-by-side panels.
        columns = QHBoxLayout(); columns.setSpacing(12)
        self.race_tables = {}
        self.race_current_tables = {}

        current_card, current_layout = self.panel('Current Soundtracks')
        staged_card, staged_layout = self.panel('Staged Soundtracks')
        for kind in ('Win', 'Lose'):
            current_label = QLabel(f'Current {kind}/Race Transition Tracks' if kind == 'Win' else f'Current {kind} Tracks')
            current_label.setStyleSheet('font-weight: 600; color: #eceef2;')
            current_layout.addWidget(current_label)
            current = QTableWidget(0, 1)
            current.setHorizontalHeaderLabels(['Game soundtrack (RSM)'])
            current.horizontalHeader().hide()
            current.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            current.setEditTriggers(QAbstractItemView.NoEditTriggers)
            current.setSelectionBehavior(QAbstractItemView.SelectRows)
            current.setSelectionMode(QAbstractItemView.SingleSelection)
            apply_soundtrack_selection_theme(current)
            current.itemSelectionChanged.connect(lambda k=kind: self.race_preview_selection_changed(k))
            current.setMinimumHeight(145)
            current.setToolTip('Read-only tracks referenced by the extracted race-over playlists.')
            current_layout.addWidget(current, 1)
            self.race_current_tables[kind] = current
            staged_label = QLabel(f'Staged {kind}/Race Transition Tracks' if kind == 'Win' else f'Staged {kind} Tracks')
            staged_label.setStyleSheet('font-weight: 600; color: #eceef2;')
            staged_layout.addWidget(staged_label)
            table = RaceMusicTable(self, kind)
            table.setHorizontalHeaderLabels(['Staged file'])
            table.horizontalHeader().hide()
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.setMinimumHeight(112)
            table.setToolTip(f'Drag MP3/WAV files from File Explorer here to stage {kind} tracks.')
            staged_layout.addWidget(table, 1)
            self.race_tables[kind] = table
            # Each category owns its add/remove actions.  Refreshing still
            # happens automatically in the existing staging callbacks.
            track_actions = QHBoxLayout(); track_actions.setSpacing(8)
            add = QPushButton('Add MP3/WAV…')
            add.clicked.connect(lambda _, k=kind: self.race_add_files(k))
            track_actions.addWidget(add, 1)
            clear = QPushButton('Remove Selected Staged File')
            clear.clicked.connect(lambda _, k=kind: self.race_remove_selected(k))
            track_actions.addWidget(clear, 1)
            staged_layout.addLayout(track_actions)

        # One shared player controls the selected track in either current list.
        preview_actions = QHBoxLayout(); preview_actions.setSpacing(8)
        self.race_preview_play_button = QPushButton('Play / Resume')
        self.race_preview_play_button.clicked.connect(self.race_preview_toggle_selected)
        preview_actions.addWidget(self.race_preview_play_button, 1)
        stop = QPushButton('Stop')
        stop.clicked.connect(self.race_preview_stop)
        preview_actions.addWidget(stop, 1)
        current_layout.addLayout(preview_actions)

        self.race_preview_status = QLabel('')
        self.race_preview_status.setObjectName('muted')
        self.race_preview_status.setWordWrap(True)
        current_layout.addWidget(self.race_preview_status)
        self.race_preview_update_buttons()

        # Keep the processing controls directly beneath the staged tracks,
        # similar to the Apply Loading Screen Music controls.
        staged_layout.addSpacing(4)
        self.race_state = QLabel('')
        self.race_state.setObjectName('muted')
        self.race_state.setWordWrap(True)
        staged_layout.addWidget(self.race_state)
        self.race_progress = QProgressBar()
        self.race_progress.setRange(0, 100)
        self.race_progress.setValue(0)
        self.race_progress.setFormat('%p%')
        staged_layout.addWidget(self.race_progress)
        actions = QHBoxLayout(); actions.setSpacing(8)
        self.race_buttons = []
        for label, mode in [('Replace Existing', 'replace'), ('Add Tracks', 'add')]:
            button = QPushButton(label)
            button.setObjectName('primary')
            button.clicked.connect(lambda _, m=mode: self.race_apply(m))
            actions.addWidget(button, 1)
            self.race_buttons.append(button)
        staged_layout.addLayout(actions)

        columns.addWidget(current_card, 1)
        columns.addWidget(staged_card, 1)
        v.addLayout(columns, 1)
        self.race_refresh()
        return page

    def race_source_dir(self, kind):
        return self.root / 'Custom Music' / ('2_Win' if kind == 'Win' else '2_Lose')

    def race_refresh(self):
        for kind, table in self.race_tables.items():
            folder = self.race_source_dir(kind)
            files = sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in ('.mp3','.wav')),
                           key=lambda p:p.name.casefold()) if folder.is_dir() else []
            table.setRowCount(0)
            for file in files:
                row = table.rowCount(); table.insertRow(row)
                table.setItem(row,0,QTableWidgetItem(file.name))
        self.race_refresh_current()
        # Refresh the lists silently; retain processing status/errors when present.

    def race_refresh_current(self):
        """Read installed Win/Lose tracks from the same playlists used by the engine."""
        self.race_preview_stop()
        for kind, table in self.race_current_tables.items():
            table.setRowCount(0)
            message = None
            entries = []
            try:
                entries = read_race_tracks(self.root, kind)
            except (OSError, UnicodeError, ValueError) as exc:
                message = str(exc)
            if message:
                table.insertRow(0)
                item = QTableWidgetItem(message)
                item.setFlags(Qt.ItemIsEnabled)
                table.setItem(0, 0, item)
                table.setToolTip(message)
                continue
            for entry in entries:
                stem = entry.rsplit('\\', 1)[-1]
                file = self.root / 'STREAMS' / 'Music' / 'Win_Lose' / (stem + '.rsm')
                table.insertRow(table.rowCount())
                item = QTableWidgetItem(stem + '.rsm' + ('' if file.is_file() else ' (file missing)'))
                # A playable RSM must be selectable for the shared preview controls.
                # Keep missing files visible but disabled for playback.
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                item.setToolTip(entry)
                if file.is_file():
                    item.setData(Qt.UserRole, str(file))
                table.setItem(table.rowCount() - 1, 0, item)
        self.race_preview_update_buttons()
        self.update_dashboard_metrics()

    def race_preview_selected_kind(self):
        for kind in ('Win', 'Lose'):
            table = self.race_current_tables.get(kind)
            if table is not None and table.selectedItems():
                return kind
        return None

    def race_preview_toggle_selected(self):
        kind = self.race_preview_selected_kind()
        if kind is not None:
            self.race_preview_toggle(kind)

    def race_preview_update_buttons(self):
        button = getattr(self, 'race_preview_play_button', None)
        if button is None:
            return
        kind = self.race_preview_selected_kind()
        item = None
        if kind is not None:
            table = self.race_current_tables[kind]
            item = table.item(table.currentRow(), 0)
        valid = item is not None and isinstance(item.data(Qt.UserRole), str)
        button.setEnabled(valid and self.race_preview_process is None)
        playing = (valid and self.race_preview_source == item.data(Qt.UserRole)
                   and self.race_preview_player.playbackState() == QMediaPlayer.PlayingState)
        button.setText('Pause' if playing else 'Play / Resume')

    def race_preview_selection_changed(self, kind):
        if not hasattr(self, 'race_preview_player'):
            return
        # A selection in either list becomes the only active preview selection.
        table = self.race_current_tables[kind]
        if table.currentRow() >= 0 and table.selectedItems():
            other = 'Lose' if kind == 'Win' else 'Win'
            other_table = self.race_current_tables.get(other)
            if other_table is not None and other_table.selectedItems():
                other_table.blockSignals(True)
                other_table.clearSelection()
                other_table.blockSignals(False)
            self.race_preview_stop()
        self.race_preview_update_buttons()

    def race_preview_toggle(self, kind):
        table = self.race_current_tables[kind]
        item = table.item(table.currentRow(), 0) if table.currentRow() >= 0 else None
        source = item.data(Qt.UserRole) if item else None
        if not isinstance(source, str):
            return
        if (self.race_preview_source == source and self.race_preview_temp is not None
                and self.race_preview_player.source().isValid()):
            if self.race_preview_player.playbackState() == QMediaPlayer.PlayingState:
                self.race_preview_player.pause()
            else:
                self.race_preview_player.play()
            return
        if self.race_preview_process is not None:
            return
        source_path = Path(source)
        if not source_path.is_file():
            self.race_preview_status.setText(f'RSM file missing: {source_path.name}')
            return
        decoder = self.root / 'supporting_tools' / 'rsm_decoder.py'
        if not decoder.is_file():
            self.race_preview_status.setText('Missing supporting_tools/rsm_decoder.py')
            return
        self.race_preview_stop()
        self.race_preview_source = source
        self.race_preview_temp = tempfile.TemporaryDirectory(prefix='mc3_race_preview_')
        output = Path(self.race_preview_temp.name) / 'race_preview.wav'
        process = QProcess(self)
        self.race_preview_process = process
        process.setProgram(sys.executable)
        process.setArguments([str(decoder), str(source_path), str(output), '--full'])
        process.setWorkingDirectory(str(self.root))
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.finished.connect(lambda code, status, proc=process, wav=output:
                                 self.race_preview_decoded(proc, wav, code, status))
        process.errorOccurred.connect(lambda error, proc=process: self.race_preview_decode_error(proc, error))
        self.race_preview_status.setText(f'Decoding {source_path.name} for preview…')
        self.race_preview_update_buttons()
        process.start()

    def race_preview_decoded(self, process, output, code, status):
        if process is not self.race_preview_process:
            process.deleteLater()
            return
        message = bytes(process.readAllStandardOutput()).decode('utf-8', errors='replace').strip()
        self.race_preview_process = None
        process.deleteLater()
        if status != QProcess.NormalExit or code != 0 or not output.is_file():
            self.race_preview_status.setText('RSM decoding failed: ' + (message[-300:] if message else str(code)))
            self.race_preview_update_buttons()
            return
        self.race_preview_player.setSource(QUrl.fromLocalFile(str(output)))
        self.race_preview_status.setText('')
        self.race_preview_player.play()
        self.race_preview_update_buttons()

    def race_preview_decode_error(self, process, error):
        if process is self.race_preview_process and error == QProcess.FailedToStart:
            self.race_preview_process = None
            self.race_preview_status.setText('Unable to start the Python RSM decoder.')
            process.deleteLater()
            self.race_preview_update_buttons()

    def race_preview_stop(self):
        self.race_preview_player.stop()
        self.race_preview_player.setSource(QUrl())
        process = self.race_preview_process
        if process is not None:
            self.race_preview_process = None
            process.kill()
            process.deleteLater()
        if self.race_preview_temp is not None:
            self.race_preview_temp.cleanup()
            self.race_preview_temp = None
        self.race_preview_source = None
        if hasattr(self, 'race_preview_status'):
            self.race_preview_status.setText('')
        self.race_preview_update_buttons()

    def race_preview_state_changed(self, state):
        self.race_preview_update_buttons()

    def race_preview_error(self, error, message):
        if error != QMediaPlayer.NoError and hasattr(self, 'race_preview_status'):
            self.race_preview_status.setText('Audio playback error: ' + message)

    def race_add_files(self, kind):
        if any((self.race_busy, self.build_busy, self.extraction_busy,
                self.soundtrack_busy, self.custom_busy, self.title_busy)):
            return
        files, _ = QFileDialog.getOpenFileNames(
            self, f'Select {kind} MP3/WAV files', str(self.root), 'Audio (*.mp3 *.wav)')
        if files:
            self.race_stage_files(kind, files)

    def race_stage_files(self, kind, files):
        """Shared staging logic for file picker and drag/drop."""
        if kind not in ('Win', 'Lose') or any((
                self.race_busy, self.build_busy, self.extraction_busy,
                self.soundtrack_busy, self.custom_busy, self.title_busy)):
            return
        folder = self.race_source_dir(kind)
        folder.mkdir(parents=True, exist_ok=True)
        for filename in files:
            source = Path(filename)
            if not source.is_file() or source.suffix.lower() not in ('.mp3', '.wav'):
                QMessageBox.warning(self, 'Unsupported audio file',
                                    f'Only MP3/WAV files are supported: {source.name}')
                continue
            dest = folder / source.name
            if source.resolve() == dest.resolve():
                continue
            if dest.exists() and QMessageBox.question(
                    self, 'Replace staged file', f'Replace existing staged file?\n{dest.name}',
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                continue
            try:
                shutil.copy2(source, dest)
                self.log(f'Staged {kind} audio: {dest.name}')
            except OSError as exc:
                QMessageBox.critical(self, 'Could not stage file', str(exc))
                break
        self.race_refresh()

    def race_remove_selected(self, kind=None):
        if self.race_busy: return
        selected=[]
        tables = ((kind, self.race_tables[kind]),) if kind in self.race_tables else self.race_tables.items()
        for category,table in tables:
            for index in table.selectionModel().selectedRows():
                item=table.item(index.row(),0)
                if item: selected.append(self.race_source_dir(category)/item.text())
        if not selected: return
        if QMessageBox.question(self,'Remove staged files',
            'Remove selected source files from the staging folders?\n\n'+'\n'.join(p.name for p in selected),
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No) != QMessageBox.Yes: return
        for file in selected:
            try: file.unlink()
            except OSError as exc: QMessageBox.critical(self,'Cannot remove staged file',str(exc))
        self.race_refresh()

    def race_apply(self, mode):
        if self.race_busy or self.build_busy or self.extraction_busy or self.soundtrack_busy: return
        if not self.profile_verified:
            QMessageBox.warning(self,'Profile not verified','Wait for automatic SHA-256 verification.'); return
        script=self.root/'supporting_tools'/'sync_winlose_folders.py'
        if not script.is_file() or not (self.root/'ASSETS').is_dir() or not (self.root/'STREAMS').is_dir():
            QMessageBox.warning(self,'Workspace incomplete','The extracted ASSETS/STREAMS workspace or original utility is missing.'); return
        staged={k:[p for p in self.race_source_dir(k).iterdir() if p.is_file() and p.suffix.lower() in ('.mp3','.wav')]
                if self.race_source_dir(k).is_dir() else [] for k in ('Win','Lose')}
        if not any(staged.values()):
            QMessageBox.information(self,'No source music','Add MP3/WAV files to the Win or Lose staging folders first.'); return
        description=f'Mode: {mode.upper()}\nWin: {len(staged["Win"])} source file(s)\nLose: {len(staged["Lose"])} source file(s)'
        if QMessageBox.warning(self,'Confirm Win/Lose changes',description+'\n\n'
            'The existing engine will update RSM audio and race playlists. '
            'No permanent audio backups are created. Back up ASSETS and STREAMS first.\n\nProceed?',
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No) != QMessageBox.Yes: return
        self.race_busy=True; self.race_prompt_answered=False; self.race_prompt_tail=''
        self.race_active_mode = mode
        for button in self.race_buttons: button.setEnabled(False)
        self.race_progress.setRange(0, 0)  # Indeterminate: the engine reports no numeric progress.
        self.race_progress.setFormat('Processing…')
        self.race_state.setText(f'Processing {mode} music…'); self.log(f'Win/Lose processing started: {mode}')
        self.race_process=QProcess(self)
        self.race_process.setWorkingDirectory(str(self.root))
        self.race_process.setProgram(sys.executable)
        self.race_process.setArguments(['-u',str(script),str(self.root),mode])
        self.race_process.setProcessChannelMode(QProcess.MergedChannels)
        self.race_process.readyReadStandardOutput.connect(self.race_output)
        self.race_process.finished.connect(self.race_finished)
        self.race_process.errorOccurred.connect(self.race_error)
        self.race_process.start()

    def race_output(self):
        if not self.race_process: return
        chunk=bytes(self.race_process.readAllStandardOutput()).decode('utf-8',errors='replace')
        if not chunk: return
        for line in chunk.splitlines():
            if line.strip(): self.log(line.rstrip())
        self.race_prompt_tail=(self.race_prompt_tail+chunk)[-400:]
        expected=re.search(r'Proceed with (replace|add) for nonempty folders\? \(Y/N\):',self.race_prompt_tail,re.I)
        if expected and not self.race_prompt_answered:
            if expected.group(1).lower()!=self.race_active_mode:
                self.log('ERROR: Unexpected operation mode in confirmation prompt.'); self.race_process.kill(); return
            self.race_prompt_answered=True
            self.log('Acknowledged previously approved Win/Lose operation.')
            self.race_process.write(b'Y\n')
        elif re.search(r'\(Y/N\):',self.race_prompt_tail,re.I) and not self.race_prompt_answered:
            self.log('ERROR: Unexpected interactive prompt; stopping operation.')
            self.race_process.kill()

    def race_error(self,error):
        if error == QProcess.FailedToStart:
            self.log('ERROR: Win/Lose utility could not start: '+self.race_process.errorString())

    def race_finished(self,code,status):
        self.race_output()
        success=status==QProcess.NormalExit and code==0 and self.race_prompt_answered
        self.race_busy=False
        self.race_progress.setRange(0, 100)
        self.race_progress.setValue(100 if success else 0)
        self.race_progress.setFormat('%p%' if success else 'Stopped — see Activity Log')
        for button in self.race_buttons: button.setEnabled(True)
        if success:
            self.race_state.setText('Win/Lose music updated. Build an ISO to test in PCSX2.')
            self.log('Win/Lose music operation completed successfully.')
            QMessageBox.information(self,'Win/Lose music updated','Processing completed. Build a modified ISO and test in PCSX2.')
        else:
            self.race_state.setText('Win/Lose processing did not complete; review Activity Log.')
            self.log(f'Win/Lose processing failed or stopped (exit code {code}).')
            QMessageBox.warning(self,'Win/Lose processing stopped','Review the Activity Log before retrying. Inspect the workspace if files may have changed.')
        self.race_refresh()
        if success:
            self.race_state.setText('Win/Lose music updated. Build an ISO to test in PCSX2.')
        else:
            self.race_state.setText('Win/Lose processing did not complete; review Activity Log.')

    def loading_music_page(self):
        page = QWidget(); v = QVBoxLayout(page); v.setContentsMargins(0,0,0,0); v.setSpacing(9)
        title = QLabel('Loading Screen Music'); title.setObjectName('heading'); v.addWidget(title)
        hint = QLabel('Stage MP3/WAV audio and assign it to the 18 available loading-screen slots. MP3/WAV audio must be no longer than 9.493 seconds.')
        hint.setObjectName('muted'); hint.setWordWrap(True); v.addWidget(hint)
        panels = QHBoxLayout(); panels.setSpacing(12)
        card, cv = self.panel('Staged Loading Music')
        self.loading_table = LoadingMusicTable(self)
        self.loading_table.setHorizontalHeaderLabels(['Audio File'])
        self.loading_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.loading_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.loading_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        cv.addWidget(self.loading_table, 1)
        row = QHBoxLayout()
        add = QPushButton('Add MP3/WAV…'); add.clicked.connect(self.loading_add); row.addWidget(add)
        remove = QPushButton('Remove Selected'); remove.clicked.connect(self.loading_remove); row.addWidget(remove)
        cv.addLayout(row); panels.addWidget(card, 1)
        card, cv = self.panel('Slot Assignment')
        row = QHBoxLayout(); row.addWidget(QLabel('Method:'))
        self.loading_mode = QComboBox()
        self.loading_mode.addItem('Manual Selection', 'M')
        self.loading_mode.addItem('Automatic Randomized', 'A')
        self.loading_mode.addItem('Evenly Distributed', 'E')
        self.loading_mode.currentIndexChanged.connect(self.loading_update_mode)
        row.addWidget(self.loading_mode, 1)
        cv.addLayout(row)
        self.loading_note = QLabel('Manual Selection: choose a staged track for each slot you want to replace. Other slots remain unchanged.')
        self.loading_note.setObjectName('muted'); self.loading_note.setWordWrap(True)
        cv.addWidget(self.loading_note)
        self.loading_slot_table = QTableWidget(18, 2)
        self.loading_slot_table.setObjectName('loadingSlotTable')
        apply_soundtrack_selection_theme(self.loading_slot_table)
        self.loading_slot_table.setHorizontalHeaderLabels(['Slot', 'Assigned Track'])
        self.loading_slot_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.loading_slot_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.loading_slot_table.verticalHeader().setVisible(False)
        for n in range(1,19):
            item = QTableWidgetItem(str(n)); item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.loading_slot_table.setItem(n-1, 0, item)
            choice = AssignmentComboBox(); choice.addItem('Leave unchanged', '')
            self.loading_slot_table.setCellWidget(n-1, 1, choice)
        cv.addWidget(self.loading_slot_table, 1)
        # Preview the *existing* RAW file for the highlighted slot, not its staged replacement.
        self.loading_slot_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.loading_slot_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.loading_slot_table.itemSelectionChanged.connect(self.loading_preview_selection_changed)
        preview_row = QHBoxLayout()
        self.loading_preview_play_button = QPushButton('Preview Selected Slot')
        self.loading_preview_play_button.clicked.connect(self.loading_preview_toggle)
        preview_row.addWidget(self.loading_preview_play_button)
        self.loading_preview_stop_button = QPushButton('Stop')
        self.loading_preview_stop_button.clicked.connect(self.loading_preview_stop)
        preview_row.addWidget(self.loading_preview_stop_button)
        cv.addLayout(preview_row)
        self.loading_preview_seek = QSlider(Qt.Horizontal)
        self.loading_preview_seek.setRange(0, 0)
        self.loading_preview_seek.sliderMoved.connect(self.loading_preview_player.setPosition)
        cv.addWidget(self.loading_preview_seek)
        self.loading_preview_status = QLabel('Select a slot to hear its current loading-screen music.')
        self.loading_preview_status.setObjectName('muted')
        self.loading_preview_status.setWordWrap(True)
        cv.addWidget(self.loading_preview_status)
        self.loading_slot_table.selectRow(0)
        self.loading_state = QLabel('Ready.'); self.loading_state.setObjectName('muted'); cv.addWidget(self.loading_state)
        self.loading_progress = QProgressBar()
        self.loading_progress.setRange(0, 100)
        self.loading_progress.setValue(0)
        cv.addWidget(self.loading_progress)
        self.loading_run = QPushButton('Apply Loading Screen Music'); self.loading_run.setObjectName('primary')
        self.loading_run.clicked.connect(self.loading_begin); cv.addWidget(self.loading_run)
        panels.addWidget(card, 1)
        v.addLayout(panels, 1)
        return page

    def loading_preview_selection_changed(self):
        if not hasattr(self, 'loading_preview_status'):
            return
        self.loading_preview_stop()
        slot = self.loading_slot_table.currentRow() + 1
        if 1 <= slot <= 18:
            self.loading_preview_status.setText(f'Slot {slot} selected — preview plays the existing ASSETS audio.')

    def loading_preview_toggle(self):
        if self.loading_mode.currentData() != 'M':
            return
        slot = self.loading_slot_table.currentRow() + 1
        if not 1 <= slot <= 18:
            self.loading_preview_status.setText('Select a slot from 1 to 18 first.')
            return
        if self.loading_preview_slot == slot and self.loading_preview_temp is not None:
            if self.loading_preview_player.playbackState() == QMediaPlayer.PlayingState:
                self.loading_preview_player.pause()
            else:
                self.loading_preview_player.play()
            return
        self.loading_preview_stop()
        raw = self.root / 'ASSETS' / 'audio' / 'loadscreen' / f'{slot}.raw'
        if not raw.is_file():
            self.loading_preview_status.setText(f'Slot {slot}: missing {raw}. Extract ASSETS first.')
            return
        try:
            size = raw.stat().st_size
            if size == 0 or size % 2:
                raise ValueError('RAW audio must contain a nonempty, even number of bytes.')
            # convert_loading_raw.py outputs 24 kHz, mono, signed 16-bit PCM.
            # A WAV wrapper allows QMediaPlayer to play it without an external decoder.
            self.loading_preview_temp = tempfile.TemporaryDirectory(prefix='mc3_loading_preview_')
            wav = Path(self.loading_preview_temp.name) / f'slot_{slot}.wav'
            with wave.open(str(wav), 'wb') as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(24000)
                with raw.open('rb') as inp:
                    out.writeframes(inp.read())
            self.loading_preview_slot = slot
            self.loading_preview_player.setSource(QUrl.fromLocalFile(str(wav)))
            self.loading_preview_player.play()
            self.loading_preview_status.setText(f'Playing existing loading-screen slot {slot}.')
        except (OSError, ValueError) as exc:
            self.loading_preview_stop()
            self.loading_preview_status.setText(f'Unable to preview slot {slot}: {exc}')

    def loading_preview_stop(self):
        if not hasattr(self, 'loading_preview_player'):
            return
        self.loading_preview_player.stop()
        self.loading_preview_player.setSource(QUrl())
        self.loading_preview_slot = None
        if self.loading_preview_temp is not None:
            self.loading_preview_temp.cleanup()
            self.loading_preview_temp = None
        if hasattr(self, 'loading_preview_seek'):
            self.loading_preview_seek.setRange(0, 0)
        if hasattr(self, 'loading_preview_play_button'):
            self.loading_preview_play_button.setText('Preview Selected Slot')

    def loading_preview_position(self, position):
        if hasattr(self, 'loading_preview_seek') and not self.loading_preview_seek.isSliderDown():
            self.loading_preview_seek.setValue(position)

    def loading_preview_duration(self, duration):
        if hasattr(self, 'loading_preview_seek'):
            self.loading_preview_seek.setRange(0, max(0, duration))

    def loading_preview_state_changed(self, state):
        if hasattr(self, 'loading_preview_play_button'):
            self.loading_preview_play_button.setText('Pause Preview' if state == QMediaPlayer.PlayingState else 'Preview / Resume Slot')

    def loading_preview_error(self, error, message):
        if error != QMediaPlayer.NoError and hasattr(self, 'loading_preview_status'):
            self.loading_preview_status.setText('Audio playback error: ' + message)

    def loading_files(self):
        folder = self.root / 'Loading Music'
        return sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in ('.mp3','.wav')),
                      key=lambda p: p.name.casefold()) if folder.is_dir() else []

    def loading_refresh(self):
        if not hasattr(self, 'loading_table'): return
        files = self.loading_files()
        self.loading_table.setRowCount(len(files))
        for i, f in enumerate(files):
            item = QTableWidgetItem(f.name); item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.loading_table.setItem(i, 0, item)
        for slot in range(18):
            combo = self.loading_slot_table.cellWidget(slot, 1)
            previous = combo.currentData()
            combo.blockSignals(True); combo.clear(); combo.addItem('Leave unchanged', '')
            for f in files: combo.addItem(f.name, f.name)
            index = combo.findData(previous)
            combo.setCurrentIndex(max(index, 0)); combo.blockSignals(False)
        if not self.loading_busy and self.loading_progress.value() != 100:
            self.loading_state.setText(f'{len(files)} staged track(s). Maximum 18 source tracks.')
        self.loading_update_mode()

    def loading_add(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Add Loading Music', str(self.root), 'Audio Files (*.mp3 *.wav)')
        if paths:
            self.loading_stage_files(paths)

    def loading_stage_files(self, paths):
        """Shared staging path for the file picker and Explorer drag-and-drop."""
        if any((self.loading_busy, self.race_busy, self.build_busy,
                self.extraction_busy, self.soundtrack_busy, self.custom_busy, self.title_busy)):
            QMessageBox.information(self, 'Operation in progress', 'Wait until the current operation finishes.')
            return
        sources = [Path(p) for p in paths]
        if not sources:
            return
        if any(not p.is_file() or p.suffix.lower() not in ('.mp3', '.wav') for p in sources):
            QMessageBox.warning(self, 'Unsupported audio', 'Only MP3 and WAV files can be staged.')
            return
        folder = self.root / 'Loading Music'
        folder.mkdir(parents=True, exist_ok=True)
        existing = {p.name.casefold() for p in self.loading_files()}
        if len(existing | {p.name.casefold() for p in sources}) > 18:
            QMessageBox.warning(self, 'Too many tracks', 'Loading Music supports a maximum of 18 source tracks.')
            return
        for source in sources:
            dest = folder / source.name
            if source.resolve() == dest.resolve():
                continue
            if dest.exists() and QMessageBox.question(
                    self, 'Replace staged file', f'Replace {dest.name}?',
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                continue
            try:
                shutil.copy2(source, dest)
            except OSError as exc:
                QMessageBox.warning(self, 'Staging failed', str(exc))
        self.loading_refresh()

    def loading_remove(self):
        rows = sorted({i.row() for i in self.loading_table.selectedIndexes()}, reverse=True)
        if not rows: return
        if QMessageBox.question(self, 'Remove staged files', f'Remove {len(rows)} selected staged file(s)?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes: return
        for row in rows:
            item = self.loading_table.item(row, 0)
            if item:
                try: (self.root / 'Loading Music' / item.text()).unlink()
                except OSError as exc: QMessageBox.warning(self, 'Remove failed', str(exc))
        self.loading_refresh()

    def loading_update_mode(self, *_):
        if not hasattr(self, 'loading_mode'): return
        manual = self.loading_mode.currentData() == 'M'
        self.loading_slot_table.setEnabled(manual)
        if hasattr(self, 'loading_preview_play_button'):
            self.loading_preview_play_button.setEnabled(manual)
            self.loading_preview_stop_button.setEnabled(manual)
            self.loading_preview_seek.setEnabled(manual)
            if not manual:
                self.loading_preview_stop()
        self.loading_note.setText(
            'Manual Selection: choose a staged track for each slot you want to replace. Other slots remain unchanged.' if manual else
            ('Automatic Randomized: assigns each staged track to a different randomly selected slot. Unselected slots remain unchanged.'
             if self.loading_mode.currentData() == 'A' else
             'Evenly Distributed: fills all 18 slots, distributing them as evenly as possible among the staged tracks.'))

    def loading_begin(self):
        if any((self.loading_busy, self.build_busy, self.extraction_busy, self.soundtrack_busy,
                self.race_busy, self.custom_busy, self.title_busy)): return
        if not self.profile_verified:
            QMessageBox.warning(self, 'Profile not verified', 'Wait for automatic profile verification.'); return
        files = self.loading_files()
        if not files or len(files) > 18:
            QMessageBox.warning(self, 'Staged music', 'Stage between 1 and 18 MP3/WAV tracks.'); return
        target = self.root / 'ASSETS' / 'audio' / 'loadscreen'
        if not target.is_dir() or any(not (target / f'{n}.raw').is_file() for n in range(1,19)):
            QMessageBox.warning(self, 'Missing slots', 'Extract ASSETS first; all 18 loading-screen RAW slots are required.'); return
        mode = self.loading_mode.currentData()
        if mode == 'M':
            assignments = [{'slot': n, 'source': self.loading_slot_table.cellWidget(n-1,1).currentData()}
                           for n in range(1,19) if self.loading_slot_table.cellWidget(n-1,1).currentData()]
        elif mode == 'A':
            assignments = [{'slot': slot, 'source': file.name} for slot, file in
                           zip(random.sample(range(1,19), len(files)), files)]
        else:
            assignments = [{'slot': slot, 'source': files[min((slot-1)*len(files)//18, len(files)-1)].name}
                           for slot in range(1,19)]
        if not assignments:
            QMessageBox.information(self, 'No assignments', 'Select at least one slot to replace.'); return
        preview = '\n'.join(f"Slot {x['slot']}: {x['source']}" for x in sorted(assignments, key=lambda x:x['slot']))
        if QMessageBox.warning(self, 'Confirm loading-screen changes',
            f'Method: {self.loading_mode.currentText()}\nAssignments: {len(assignments)}\n\n{preview}\n\n'
            'These slots will be overwritten in the extracted ASSETS workspace. Back up ASSETS first. Continue?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes: return
        helper = Path(__file__).parent / 'loading_apply.py'
        if not helper.is_file():
            QMessageBox.critical(self, 'Missing helper', 'gui/loading_apply.py is missing.'); return
        import json
        import tempfile
        handle = tempfile.NamedTemporaryFile(mode='w', suffix='.json', prefix='MC3_Loading_',
                                             dir=self.root, encoding='utf-8', delete=False)
        try:
            json.dump({'assignments': assignments}, handle); handle.close()
            self.loading_config_path = Path(handle.name)
        except Exception:
            handle.close(); raise
        self.loading_output_text = ''
        self.loading_busy = True; self.loading_run.setEnabled(False)
        self.loading_progress.setRange(0, 0)  # Indeterminate until helper exits successfully.
        self.loading_progress.setFormat('Processing…')
        self.loading_state.setText('Converting and applying loading-screen audio…')
        self.log(f'Loading-screen processing started: {mode}, {len(assignments)} assignments.')
        self.loading_process = QProcess(self)
        self.loading_process.setWorkingDirectory(str(self.root))
        self.loading_process.setProgram(sys.executable)
        self.loading_process.setArguments(['-u', str(helper), str(self.root), str(self.loading_config_path)])
        self.loading_process.setProcessChannelMode(QProcess.MergedChannels)
        self.loading_process.readyReadStandardOutput.connect(self.loading_output)
        self.loading_process.finished.connect(self.loading_finished)
        self.loading_process.errorOccurred.connect(self.loading_error)
        self.loading_process.start()

    def loading_output(self):
        if self.loading_process:
            data = bytes(self.loading_process.readAllStandardOutput()).decode('utf-8', errors='replace')
            self.loading_output_text += data
            for line in data.splitlines():
                if line.strip(): self.log(line)

    def loading_error(self, error):
        if error == QProcess.FailedToStart:
            self.log('ERROR: Loading-screen helper could not start: ' + self.loading_process.errorString())

    def loading_finished(self, code, status):
        self.loading_output()
        self.loading_busy = False; self.loading_run.setEnabled(True)
        success = status == QProcess.NormalExit and code == 0
        self.loading_progress.setRange(0, 100)
        self.loading_progress.setValue(100 if success else 0)
        self.loading_progress.setFormat('%p%' if success else 'Stopped — see Activity Log')
        if self.loading_config_path:
            try: self.loading_config_path.unlink(missing_ok=True)
            except OSError: pass
            self.loading_config_path = None
        if status == QProcess.NormalExit and code == 0:
            self.loading_state.setText('Loading-screen slots updated. Build ISO to test in PCSX2.')
            QMessageBox.information(self, 'Loading-screen music updated', 'Slot replacements completed. Build a new ISO and test in PCSX2.')
        else:
            self.loading_state.setText('Loading-screen processing stopped; review Activity Log.')
            message = 'Loading-screen processing stopped. Review the Activity Log for details.'
            for line in reversed(self.loading_output_text.splitlines()):
                if line.startswith('[LOADING_FAILURE] '):
                    try:
                        failure = json.loads(line[len('[LOADING_FAILURE] '):])
                        message = f"Failed audio: {failure['filename']}\n\nReason: {failure['reason']}"
                        if failure.get('no_slots_changed') is True:
                            message += '\n\nNo slots were changed.'
                        break
                    except (ValueError, KeyError, TypeError):
                        continue
            QMessageBox.warning(self, 'Loading-screen processing stopped', message)

    def build_page(self):
        page = QWidget(); v = QVBoxLayout(page); v.setContentsMargins(0,0,0,0); v.setSpacing(13)
        h = QLabel('Build ISO'); h.setObjectName('heading'); v.addWidget(h)
        card, cv = self.panel('Compile DAT Archives & Build ISO')
        hint = QLabel('Compiles ASSETS.DAT and STREAMS.DAT, checks archive capacity and resource offsets, then builds and verifies a separate ISO. The original ISO is never modified.')
        hint.setWordWrap(True); hint.setObjectName('muted'); cv.addWidget(hint)
        self.build_profile_label = QLabel('Game profile: Awaiting verification'); cv.addWidget(self.build_profile_label)
        self.build_output_label = QLabel('Output: Not determined'); self.build_output_label.setWordWrap(True)
        self.build_output_label.setTextInteractionFlags(Qt.TextSelectableByMouse); cv.addWidget(self.build_output_label)
        self.build_state = QLabel('Verify the extracted workspace before building.'); self.build_state.setObjectName('muted')
        self.build_state.setWordWrap(True); cv.addWidget(self.build_state)
        self.build_capacity_label = QLabel('Capacity: checked for the selected ISO version after compilation.')
        self.build_capacity_label.setWordWrap(True); cv.addWidget(self.build_capacity_label)
        self.build_progress = QProgressBar(); self.build_progress.setRange(0, 7); self.build_progress.setValue(0)
        cv.addWidget(self.build_progress)
        self.build_button = QPushButton('Compile DAT Archives & Build ISO'); self.build_button.setObjectName('primary')
        self.build_button.setEnabled(False); self.build_button.clicked.connect(self.begin_build); cv.addWidget(self.build_button)
        v.addWidget(card)
        note = QLabel('An existing output is preserved until a new pending ISO passes the builder checks. '
                      'Do not close the application during compilation or building. A failed build may leave updated DAT archives or a pending ISO for inspection.')
        note.setObjectName('muted'); note.setWordWrap(True); v.addWidget(note)
        v.addStretch(1)
        return page

    def build_profile_info(self):
        workspace = self.root / 'ISO_FILES'
        try:
            profile = (workspace / 'MC3_PROFILE.txt').read_text(encoding='utf-8').strip().lower()
            source = Path((workspace / 'MC3_SOURCE_ISO.txt').read_text(encoding='utf-8').strip()).resolve()
        except (OSError, UnicodeError, ValueError):
            return None, None
        return profile if profile in ('retail', 'vip') else None, source

    def vip_v11a_workspace(self):
        """True only for the distinct VIP v1.1-A source classification."""
        return self.read_metadata(self.root / 'ISO_FILES' / 'MC3_SOURCE_CLASS.txt') == 'VERIFIED_VIP_V11A_REFERENCE'

    def update_build_controls(self):
        profile, source = self.build_profile_info()
        vip_v11a = self.vip_v11a_workspace()
        vip_v10_expanded = profile == 'vip' and self.read_metadata(self.root/'ISO_FILES'/'MC3_SOURCE_CLASS.txt') == 'VERIFIED_VIP_REFERENCE'
        retail_expanded = profile == 'retail' and self.read_metadata(self.root/'ISO_FILES'/'MC3_SOURCE_CLASS.txt') == 'VERIFIED_RETAIL_REFERENCE'
        output = self.root / ('MC3_Modified_VIP.iso' if profile == 'vip' else 'MC3_Modified_DUB.iso')
        self.build_profile_label.setText('Game profile: ' + ('VIP v1.1-A' if vip_v11a else 'VIP v1.0-C expanded' if vip_v10_expanded else 'Retail USA expanded' if retail_expanded else {'retail':'Retail USA','vip':'VIP v1.0-C'}.get(profile, 'Not detected')))
        self.build_output_label.setText('Output: ' + (str(output) if profile else 'Not determined'))
        ready = (self.profile_verified and profile in ('retail', 'vip') and source is not None
                 and source.is_file() and not self.build_busy and not self.extraction_busy and not self.soundtrack_busy
                 and not any(getattr(self, name, False) for name in ('race_busy','custom_busy','title_busy','loading_busy'))
                 and (not self.validator or self.validator.state() == QProcess.NotRunning))
        self.build_button.setEnabled(bool(ready))
        if not self.build_busy:
            self.build_state.setText('Ready to compile, check capacity and build.' if ready else 'Waiting for verified extracted workspace.')

    def begin_build(self):
        if self.build_busy or not self.profile_verified:
            return
        if any(getattr(self, name, False) for name in ('extraction_busy','soundtrack_busy','race_busy','custom_busy','title_busy','loading_busy')):
            return
        vip_v11a = self.vip_v11a_workspace()
        profile, source = self.build_profile_info()
        vip_v10_expanded = profile == 'vip' and self.read_metadata(self.root/'ISO_FILES'/'MC3_SOURCE_CLASS.txt') == 'VERIFIED_VIP_REFERENCE'
        retail_expanded = profile == 'retail' and self.read_metadata(self.root/'ISO_FILES'/'MC3_SOURCE_CLASS.txt') == 'VERIFIED_RETAIL_REFERENCE'
        if profile not in ('retail','vip') or source is None or not source.is_file():
            QMessageBox.warning(self, 'Missing source', 'The recorded source ISO is missing or the profile is invalid.')
            return
        workspace = self.root / 'ISO_FILES'
        tools = self.root / 'supporting_tools'
        required = [workspace / x for x in ('ASSETS.DAT','STREAMS.DAT','STREAMS.LST','MC3_PROFILE.txt','MC3_SOURCE_SHA256.txt','MC3_SOURCE_CLASS.txt','MC3_SOURCE_ISO.txt')]
        required += [tools / x for x in ('dave.py','hash_build.py','MC3_Profile_108S.py','MC3_ISO_Builder.py',
                                       'MC3_ISO_Builder_Retail.py' if profile == 'retail' else 'MC3_ISO_Builder_VIP.py')]
        required += [self.root / 'ASSETS', self.root / 'STREAMS']
        required += [tools / x for x in ('archive_build_gate.py','vip_capacity.py')]
        if vip_v11a:
            required += [tools / x for x in ('MC3_ASSETS_Builder_V11A.py','MC3_ISO_Builder_V11A.py')]
        else:
            required += [tools / 'iso_preservation.py']
        missing = [str(x) for x in required if not x.exists()]
        if missing:
            QMessageBox.warning(self, 'Missing build inputs', 'Required files or folders missing:\n' + '\n'.join(missing[:12])); return
        for folder in (self.root/'ASSETS',self.root/'STREAMS'):
            for file in folder.rglob('*'):
                if file.is_file() and (file.name.lower().endswith('.bak') or '.bak.' in file.name.lower()):
                    QMessageBox.warning(self, 'Backup file detected', f'Move backup files outside game folders before compiling:\n{file}'); return
        output = self.root / ('MC3_Modified_VIP.iso' if profile == 'vip' else 'MC3_Modified_DUB.iso')
        pending = output.with_name(output.stem + '.pending_build.iso')
        if source.resolve() in (output.resolve(),pending.resolve()):
            QMessageBox.critical(self, 'Unsafe path', 'The source ISO must not be the output or pending ISO.'); return
        if pending.exists() or Path(str(pending)+'.building.tmp').exists():
            QMessageBox.warning(self, 'Pending build exists', f'A previous pending build exists. Inspect it before continuing:\n{pending}'); return
        overwrite = output.exists()
        profile_name = 'VIP v1.1-A' if vip_v11a else 'VIP v1.0-C expanded' if vip_v10_expanded else 'Retail USA expanded' if retail_expanded else {'retail':'Retail USA','vip':'VIP v1.0-C'}[profile]
        message = (f'Profile: {profile_name}\nSource ISO: {source}\nOutput ISO: {output}\n\n'
                   'The following extracted archives will be replaced:\nISO_FILES\\ASSETS.DAT\nISO_FILES\\STREAMS.DAT\n\n'
                   + ('An existing output ISO will be replaced ONLY after successful build verification.\n\n' if overwrite else '')
                   + 'Proceed with compilation and building?')
        if QMessageBox.question(self, 'Confirm ISO build', message, QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        common = ['--profile','vip-v11a' if vip_v11a else profile,'--replacement-dir','ISO_FILES','--manifest','ISO_FILES/STREAMS.LST']
        common += ['--source', str(source)]
        if vip_v10_expanded:
            common += ['--expand-v10']
        if retail_expanded:
            common += ['--relocate-archives']
        builder = str(tools/'MC3_ISO_Builder.py')
        self.build_steps = [
            ('Validate source ISO (SHA-256)',str(tools/'MC3_Profile_108S.py'),['validate',str(workspace)]),
            ('Compile ASSETS.DAT',str(tools/'dave.py'), ['B','-ca','-cn','-cf','-fc','1'] + (['-d'] if profile == 'vip' else []) + [str(self.root/'ASSETS'),str(workspace/'ASSETS.DAT')]),
            ('Compile STREAMS.DAT',str(tools/'hash_build.py'),['B',str(self.root/'STREAMS'),str(workspace/'STREAMS.DAT'),'-a','MClub']),
            ('Validate compiled workspace',str(tools/'MC3_Profile_108S.py'),['validate',str(workspace)]),
            ('ISO builder preflight',builder,common+['--check-only']),
            ('Build and verify pending ISO',builder,common+['--output',str(pending),'--yes'])]
        if vip_v11a:
            self.build_steps[1] = ('Compile ASSETS.DAT', str(tools/'MC3_ASSETS_Builder_V11A.py'),
                ['--iso',str(source),'--source',str(self.root/'ASSETS'),'--output',str(workspace/'ASSETS.DAT'),'--replace'])
            # The dedicated engine performs full preflight immediately before
            # copying. Avoid a second full content pass in a separate process.
            self.build_steps = [step for step in self.build_steps if step[0] != 'ISO builder preflight']
        self.build_steps.insert(4, ('Check compiled archive capacity and record ranges',
            str(tools/'archive_build_gate.py'), ['--replacement-dir',str(workspace), '--profile','vip-v11a' if vip_v11a else 'vip-expanded' if vip_v10_expanded else 'retail-expanded' if retail_expanded else profile,
                '--report',str(self.root/'support_logs'/'build_capacity_latest.json')]))
        self.build_capacity_report_path = self.root/'support_logs'/'build_capacity_latest.json'
        self.build_capacity_label.setText('Capacity: waiting for freshly compiled archives.')
        self.build_index = 0; self.build_busy = True; self.build_output = output
        self.build_pending = pending; self.build_profile = profile
        self.build_progress.setRange(0, len(self.build_steps))
        self.build_progress.setValue(0); self.build_button.setEnabled(False)
        self.log('ISO build confirmed; source ISO protected.'); self.start_build_step()

    def append_build_log(self, text):
        if self.build_log_file is not None:
            try:
                self.build_log_file.write(text)
                self.build_log_file.flush()
            except OSError as error:
                self.close_build_log()
                self.log('Build log could not be updated: ' + str(error))

    def close_build_log(self):
        if self.build_log_file is not None:
            try:
                self.build_log_file.close()
            except OSError:
                pass
            self.build_log_file = None

    def show_build_capacity(self):
        try:
            report = json.loads(self.build_capacity_report_path.read_text(encoding='utf-8'))
            if report.get('status') == 'INVALID_OR_UNSUPPORTED_ARCHIVE_INDEX':
                self.build_capacity_label.setText('Capacity check stopped: ' + report.get('error', 'Invalid archive index'))
                return
            label = report['layout_label']
            used = report['assets_allocated_bytes'] + report['streams_allocated_bytes']
            budget = report['shared_layout_capacity_bytes']
            if report['over_capacity_bytes']:
                detail = f'Over capacity by {report["over_capacity_bytes"] / 1048576:.2f} MiB.'
            elif not report['passes_size_policy']:
                detail = 'Resource-offset check blocked the build.'
            else:
                detail = f'{report["remaining_bytes"] / 1048576:.2f} MiB remaining.'
            self.build_capacity_label.setText(f'{label}: {used / 1048576:.2f} / {budget / 1048576:.2f} MiB used. {detail}')
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.build_capacity_label.setText('Capacity report unavailable; see Activity Log.')
            self.log('Could not read capacity report: ' + str(error))

    def start_build_step(self):
        if self.build_index >= len(self.build_steps):
            self.finish_build_success(); return
        if self.build_index == 0 and self.build_log_file is None:
            try:
                folder = self.root / 'support_logs'
                folder.mkdir(parents=True, exist_ok=True)
                self.build_log_file = (folder / 'last_build.log').open('w', encoding='utf-8')
                self.append_build_log(f'MC3 build {datetime.now().isoformat()}\nProject: {self.root}\n{self.build_profile_label.text()}\n')
            except OSError as error:
                self.build_failed('Cannot create support_logs/last_build.log: ' + str(error))
                return
        label,script,args = self.build_steps[self.build_index]
        self.build_state.setText(f'Step {self.build_index+1}/{len(self.build_steps)}: {label}')
        self.status.setText(f'Building ISO • {label}')
        self.log(f'BUILD [{self.build_index+1}/{len(self.build_steps)}] {label}')
        self.append_build_log(f'\nBUILD [{self.build_index+1}/{len(self.build_steps)}] {label}\n')
        self.build_prompt_tail = ''
        self.build_error_tail = ''
        self.build_prompt_answered = False
        self.build_process = QProcess(self)
        self.build_process.setWorkingDirectory(str(self.root))
        self.build_process.setProgram(sys.executable)
        self.build_process.setArguments(['-u',script,*args])
        self.build_process.setProcessChannelMode(QProcess.MergedChannels)
        self.build_process.readyReadStandardOutput.connect(self.build_output_ready)
        self.build_process.finished.connect(self.build_step_finished)
        self.build_process.errorOccurred.connect(self.build_process_error)
        self.build_process.start()

    def build_output_ready(self):
        if self.build_process:
            chunk = bytes(self.build_process.readAllStandardOutput()).decode('utf-8',errors='replace')
            self.append_build_log(chunk)
            self.build_error_tail = (getattr(self, 'build_error_tail', '') + chunk)[-4096:]
            for line in chunk.splitlines():
                if line.strip(): self.log(line.rstrip())
            # Both archive compilers use input() and do not terminate their
            # overwrite prompt with a newline. Inspect raw chunks as well.
            self.build_prompt_tail = (self.build_prompt_tail + chunk)[-512:]
            prompt = re.search(r'Warning!\s*Output file already exists\.\s*Overwrite\?\s*\(Y/N\):',
                               self.build_prompt_tail, re.IGNORECASE)
            if prompt and not self.build_prompt_answered:
                label = self.build_steps[self.build_index][0]
                expected = {'Compile ASSETS.DAT': 'ASSETS.DAT',
                            'Compile STREAMS.DAT': 'STREAMS.DAT'}
                if label not in expected:
                    self.build_failed('Unexpected overwrite prompt outside DAT compilation.'); return
                target = self.root / 'ISO_FILES' / expected[label]
                if not target.is_file():
                    self.build_failed('Unexpected overwrite prompt: expected target missing: ' + str(target)); return
                self.build_prompt_answered = True
                self.log('Confirmed previously authorized overwrite of ' + expected[label])
                self.build_process.write(b'Y\n')
            elif re.search(r'\(Y/N\):', self.build_prompt_tail, re.IGNORECASE) and not self.build_prompt_answered:
                self.build_failed('Unexpected interactive confirmation prompt; build stopped for safety.')

    def build_process_error(self, error):
        if error == QProcess.FailedToStart:
            self.build_failed('Could not start the build utility: ' + self.build_process.errorString())

    def build_step_finished(self, code, status):
        if not self.build_busy: return
        self.build_output_ready()
        if not self.build_busy: return
        label = self.build_steps[self.build_index][0]
        if label == 'Check compiled archive capacity and record ranges':
            self.show_build_capacity()
        if status != QProcess.NormalExit or code != 0:
            lines = getattr(self, 'build_error_tail', '').strip().splitlines()
            detail = ('\n' + lines[-1]) if lines else ''
            self.build_failed(f'{label} failed (process exit code {code}).' + detail); return
        self.build_index += 1
        self.build_progress.setValue(self.build_index)
        self.start_build_step()

    def finish_build_success(self):
        pending,output = self.build_pending,self.build_output
        if not pending.is_file() or pending.stat().st_size == 0:
            self.build_failed('Builder did not produce a nonempty pending ISO.'); return
        try:
            # Atomic replacement on the same volume; never replace the original source ISO.
            os.replace(pending,output)
            if not output.is_file() or output.stat().st_size == 0:
                raise OSError('Final ISO missing or empty')
        except OSError as exc:
            self.build_failed(f'Could not publish pending ISO: {exc}'); return
        self.build_busy = False
        self.append_build_log('SUCCESS: Verified ISO published to ' + str(output) + '\n')
        self.close_build_log()
        self.build_state.setText('Build complete: ' + str(output))
        self.status.setText('ISO build complete • Ready for PCSX2 testing')
        self.log('SUCCESS: Verified ISO published to ' + str(output))
        self.update_build_controls()
        QMessageBox.information(self,'ISO build complete',f'Created:\n{output}\n\nTest the ISO in PCSX2.')

    def build_failed(self, reason):
        if not self.build_busy: return
        self.append_build_log('BUILD FAILED: ' + reason + '\n')
        self.close_build_log()
        self.build_busy = False
        self.build_state.setText('Build failed — see Activity Log')
        self.status.setText('ISO build failed')
        self.log('BUILD FAILED: '+reason)
        self.log('Any pending ISO or compiled DAT archives were retained for inspection.')
        self.update_build_controls()
        QMessageBox.critical(self,'ISO build failed',reason+'\nSee Activity Log for details.')

    def section(self, label, title):
        page = QWidget(); v = QVBoxLayout(page); v.setContentsMargins(0,0,0,0); v.setSpacing(13)
        h = QLabel(label); h.setObjectName('heading'); v.addWidget(h)
        card, cv = self.panel(title)
        info = QLabel('This workflow will be connected to the existing tested Python utilities in a later phase.\nNo game files will be changed in this preview.')
        info.setWordWrap(True); info.setObjectName('muted'); cv.addWidget(info)
        if label == 'About':
            info.setText('MC3 Ultimate Music Tools\nRetail USA and verified VIP Expansion sources, including VIP v1.1-A.\nBuilds check archive capacity and resource offsets before creating a separate verified ISO.')
        if label != 'About':
            action = QPushButton('Run ' + label); action.setEnabled(False); cv.addWidget(action)
        v.addWidget(card); v.addStretch(1)
        return page

    def navigate(self, index):
        if self.stack.currentIndex() == 2 and index != 2:
            self.gameplay_preview_stop()
        if self.stack.currentIndex() == 3 and index != 3:
            self.custom_preview_stop()
        if self.stack.currentIndex() == 5 and index != 5:
            self.race_preview_stop()
        if self.stack.currentIndex() == 4 and index != 4:
            self.title_preview_stop()
        if self.stack.currentIndex() == 6 and index != 6:
            self.loading_preview_stop()
        self.stack.setCurrentIndex(index)
        if index == 0:
            self.update_dashboard_metrics()
            if self.soundtrack_ready():
                self.load_soundtrack()
        if index == 5:
            # The page is built before ISO extraction; reload on each visit.
            self.race_refresh()
        if index == 4:
            self.title_refresh()
            if not self.title_preview_manual and self.title_preview_player.playbackState() != QMediaPlayer.PlayingState:
                self.title_preview_original()
        for i, b in enumerate(self.nav): b.setObjectName('navActive' if i == index else '')
        for b in self.nav: b.style().unpolish(b); b.style().polish(b)

    def toggle_log(self, button):
        visible = not self.log_box.isVisible(); self.log_box.setVisible(visible)
        button.setText('Hide log' if visible else 'Show log')

    def select_root(self):
        folder = QFileDialog.getExistingDirectory(self, 'Select MC3 project root', str(self.root))
        if not folder: return
        candidate = Path(folder)
        if not (candidate/'supporting_tools'/'MC3_Profile_108S.py').is_file():
            QMessageBox.warning(self, 'Invalid project folder', 'Select the project root containing supporting_tools/MC3_Profile_108S.py.')
            return
        if self.extraction_busy or self.soundtrack_busy or self.build_busy or self.race_busy or self.custom_busy or self.title_busy or (self.validator and self.validator.state() != QProcess.NotRunning):
            QMessageBox.information(self, 'Operation in progress', 'Wait for the current operation to finish before changing project folders.')
            return
        self.title_preview_stop()
        self.title_preview_source = None
        self.title_preview_manual = False
        self.root = candidate
        self.workspace_reset_authorization = None
        self.profile_verified = False
        self.soundtrack_songs = []
        self.filter_soundtrack(); self.set_soundtrack_buttons()
        self.refresh_workspace()
        self.race_refresh()
        self.title_refresh()
        self.title_preview_original()
        self.start_auto_validation()
        self.log(f'Project folder selected: {candidate}')

    @staticmethod
    def read_metadata(path):
        try:
            return path.read_text(encoding='utf-8-sig').strip()
        except (OSError, UnicodeError):
            return None

    def refresh_and_validate(self):
        if self.validator and self.validator.state() != QProcess.NotRunning:
            self.log('Verification already running; please wait.')
            return
        self.refresh_workspace()
        self.start_auto_validation()

    def refresh_workspace(self):
        self.profile_verified = False
        self.dashboard_catalog_state = 'waiting'
        self.update_dashboard_metrics()
        self.build_capacity_label.setText('Capacity: checked for the selected ISO version after compilation.')
        self.set_soundtrack_buttons()
        workspace = self.root / 'ISO_FILES'
        profile = self.read_metadata(workspace / 'MC3_PROFILE.txt')
        kind = self.read_metadata(workspace / 'MC3_SOURCE_CLASS.txt')
        source_text = self.read_metadata(workspace / 'MC3_SOURCE_ISO.txt')
        expected = {
            'VERIFIED_RETAIL_REFERENCE': 'retail',
            'RETAIL_CUSTOM_WITH_MANIFEST': 'retail',
            'VERIFIED_VIP_REFERENCE': 'vip',
            'VERIFIED_VIP_V11A_REFERENCE': 'vip',
            'VIP_CUSTOM_WITH_MANIFEST': 'vip',
        }
        known = {'retail': 'Retail USA', 'vip': 'VIP Expansion'}
        consistent = profile in known and expected.get(kind) == profile
        label = known.get(profile, 'Not detected' if profile is None else 'Unknown / invalid')
        self.profile.setText(f'Game profile: {label} ({"metadata consistent" if consistent else "unverified metadata"})')
        needed = ('ASSETS.DAT', 'STREAMS.DAT', 'STREAMS.LST')
        missing = [name for name in needed if not (workspace / name).is_file()]
        if not workspace.is_dir():
            status = 'Not extracted (ISO_FILES missing)'
        elif missing:
            status = 'Incomplete (missing: ' + ', '.join(missing) + ')'
        else:
            status = 'Required archives and manifest present (not validated)'
        self.workspace.setText('Workspace: ' + status)
        if source_text:
            source_path = Path(source_text)
            source_status = 'found' if source_path.is_file() else 'missing'
            self.source.setText(f'Recorded source ISO ({source_status}):\n{source_text}')
        else:
            self.source.setText('Recorded source ISO: Not recorded')
        if not (self.validator and self.validator.state() != QProcess.NotRunning):
            self.validation.setText('Profile integrity: Awaiting automatic verification' if consistent and not missing else 'Profile integrity: Not available — workspace incomplete')
        self.log(f'Workspace checked: {workspace} (metadata inspected)')
        self.update_build_controls()

    def start_auto_validation(self):
        """Verify recorded ISO hash using the original read-only profile utility."""
        if self.extraction_busy or self.soundtrack_busy or self.build_busy or self.race_busy or self.custom_busy or self.title_busy or (self.validator and self.validator.state() != QProcess.NotRunning):
            return
        workspace = self.root / 'ISO_FILES'
        required = ('MC3_PROFILE.txt', 'MC3_SOURCE_CLASS.txt', 'MC3_SOURCE_ISO.txt',
                    'MC3_SOURCE_SHA256.txt', 'ASSETS.DAT', 'STREAMS.DAT', 'STREAMS.LST')
        if not workspace.is_dir() or any(not (workspace / item).is_file() for item in required):
            return
        if not (self.root / 'supporting_tools' / 'MC3_Profile_108S.py').is_file():
            return
        self.validate_profile()

    def validate_profile(self):
        script = self.root / 'supporting_tools' / 'MC3_Profile_108S.py'
        workspace = self.root / 'ISO_FILES'
        if not script.is_file() or not workspace.is_dir():
            QMessageBox.warning(self, 'Missing files', 'The profile utility or workspace is missing.')
            return
        if self.validator and self.validator.state() != QProcess.NotRunning:
            return
        self.validator = QProcess(self)
        self.validator.setWorkingDirectory(str(self.root))
        self.validator.setProgram(sys.executable)
        self.validator.setArguments([str(script), 'validate', str(workspace)])
        self.validator.setProcessChannelMode(QProcess.MergedChannels)
        self.validator.readyReadStandardOutput.connect(self.validation_output)
        self.validator.finished.connect(self.validation_finished)
        self.validator.errorOccurred.connect(self.validation_error)
        self.validation.setText('Profile integrity: Verifying source ISO (SHA-256)…')
        self.log('Automatic read-only profile verification started (SHA-256).')
        self.validator.start()

    def validation_output(self):
        if self.validator:
            chunk = bytes(self.validator.readAllStandardOutput()).decode('utf-8', errors='replace').strip()
            if chunk:
                for line in chunk.splitlines():
                    self.log(line)

    def validation_finished(self, exit_code, exit_status):
        self.validation_output()
        success = exit_status == QProcess.NormalExit and exit_code == 0
        self.profile_verified = success
        self.update_dashboard_metrics()
        self.set_soundtrack_buttons()
        self.update_build_controls()
        self.validation.setText('Profile integrity: Verified (SHA-256)' if success
                                else f'Profile integrity: FAILED (exit code {exit_code}); see Activity Log')
        self.log('Automatic profile validation PASSED.' if success else 'Automatic profile validation FAILED; no files modified.')
        if success and not self.soundtrack_songs and not self.soundtrack_busy and self.soundtrack_ready():
            self.load_soundtrack()
        self.status.setText('Workspace ready  •  Integrity verified' if success else 'Integrity verification failed  •  Check Activity Log')

    def validation_error(self, error):
        self.log(f'Validation process error: {self.validator.errorString()}')
        if error == QProcess.FailedToStart:
            self.validation.setText('Profile integrity: Verification could not start')
    
    def closeEvent(self, event):
        if self.loading_busy:
            QMessageBox.information(self, 'Loading-screen processing in progress', 'Wait for loading-screen music processing to finish.')
            event.ignore(); return
        if self.race_busy:
            QMessageBox.information(self, 'Race music operation in progress', 'Wait for music processing to finish before closing.')
            event.ignore(); return
        if self.build_busy:
            QMessageBox.information(self,'ISO build in progress','Wait for ISO compilation and building to finish before closing.')
            event.ignore(); return
        if self.soundtrack_busy:
            QMessageBox.information(self, 'Soundtrack operation in progress', 'Wait for the soundtrack operation to finish before closing.')
            event.ignore()
            return
        if self.extraction_busy:
            QMessageBox.information(self, 'Extraction in progress', 'Wait for extraction to finish before closing.')
            event.ignore()
            return
        if self.validator and self.validator.state() != QProcess.NotRunning:
            QMessageBox.information(self, 'Validation in progress',
                                    'Wait for read-only ISO validation to finish before closing.')
            event.ignore()
        else:
            self.title_preview_stop()
            self.loading_preview_stop()
            self.race_preview_stop()
            self.gameplay_preview_stop()
            event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = Window(); window.show()
    sys.exit(app.exec())
