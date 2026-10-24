"""Open-J: Host Controller Dashboard.
Main broadcast control console for Jeopardy! game show host and studio operator.
Includes:
- Inline Daily Double Contestant & Wager Panel before 3D Flip Clue Reveal (Requirement #8)
- Clean 3D Flip trigger without premature question background bleed (Requirement #8)
- Final Jeopardy Replay, Reset & Database/Manual Override Engine (Requirement #10)
- Top-ribbon Intro Video -> Standby Merge & Outro Music broadcast controls (Requirement #7)
- Synchronized individual audio event bindings (Requirement #7)
"""

import os
import sys
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QFont, QColor, QPainter, QAction
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMenuBar,
    QMenu,
    QWidget,
    QTabWidget,
    QDockWidget,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QSpinBox,
    QComboBox,
    QPushButton,
    QTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFileDialog,
    QColorDialog,
    QFontDialog,
    QMessageBox,
    QProgressBar,
    QCheckBox,
    QButtonGroup,
    QSplitter,
    QFrame,
    QScrollArea,
    QSizePolicy,
    QInputDialog,
)

from core.event_bus import event_bus
from core.score_core import ScoreEngine
from data.db_manager import DBManager
from core.question_core import QuestionEngine
from ui.audio_manager import AudioManager
from ui.theme_manager import ThemePackageEngine, ThemeConfigManager, AssetRenderer
from ui.settings_dialog import TVBezelPreviewWidget, SettingsDialog


APP_STYLE = """
QMainWindow, QDialog {
    background-color: #0d1117;
    color: #e6edf3;
}
QTabWidget::pane {
    border: 1px solid #30363d;
    background-color: #161b22;
    top: -1px;
}
QTabBar::tab {
    background: #0d1117;
    color: #8b949e;
    border: 1px solid #30363d;
    padding: 10px 18px;
    font-size: 13px;
    font-weight: bold;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: #161b22;
    color: #58a6ff;
    border-bottom-color: #161b22;
}
QTabBar::tab:hover:!selected {
    background: #21262d;
    color: #c9d1d9;
}
QGroupBox {
    border: 1px solid #30363d;
    border-radius: 8px;
    margin-top: 24px;
    padding-top: 14px;
    font-weight: bold;
    color: #58a6ff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 6px;
    background-color: #161b22;
}
QLabel {
    color: #e6edf3;
    font-size: 13px;
}
QLineEdit, QSpinBox, QComboBox {
    background-color: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 6px 10px;
    min-height: 24px;
    color: #f0f6fc;
    font-size: 13px;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border: 1px solid #58a6ff;
}
QPushButton {
    background-color: #21262d;
    border: 1px solid #30363d;
    border-radius: 6px;
    color: #c9d1d9;
    padding: 8px 16px;
    font-weight: 600;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #30363d;
    border-color: #8b949e;
}
QPushButton:pressed {
    background-color: #161b22;
}
QPushButton:disabled {
    background-color: #161b22;
    border-color: #21262d;
    color: #484f58;
}
QTableWidget {
    background-color: #0d1117;
    border: 1px solid #30363d;
    gridline-color: #21262d;
    color: #e6edf3;
}
QHeaderView::section {
    background-color: #161b22;
    color: #8b949e;
    font-weight: bold;
    border: 1px solid #30363d;
    padding: 6px;
}
QProgressBar {
    background-color: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    text-align: center;
    color: #f0f6fc;
    font-weight: bold;
}
QProgressBar::chunk {
    background-color: #238636;
    border-radius: 5px;
}
QDockWidget {
    color: #f0f6fc;
    font-weight: bold;
}
QDockWidget::title {
    background-color: #161b22;
    padding: 8px;
    border-top: 1px solid #30363d;
}
"""


class HostControllerWindow(QMainWindow):
    """Broadcast-standard Host and Studio Operator Console."""

    def __init__(self, q_engine=None, s_engine=None, db_path="data/questions.db", parent=None):
        super().__init__(parent)
        if not os.path.isabs(db_path):
            db_path = str((PROJECT_ROOT / db_path).resolve())
        self.db_path = db_path

        self.setWindowTitle("Open-J | Host Controller Dashboard")
        self.setMinimumSize(1280, 800)
        self.resize(1366, 860)

        # Core Engines
        if q_engine is None:
            q_engine = QuestionEngine(self.db_path)
        self.q_engine = q_engine

        self.contestants = {
            "p1": {"name": "Ken Jennings", "status": "Returning Champion", "wins": 74, "prev_earnings": 2520700, "score": 0},
            "p2": {"name": "Gold Ship", "status": "New Challenger", "wins": 0, "prev_earnings": 0, "score": 0},
            "p3": {"name": "Agnes Tachyon", "status": "New Challenger", "wins": 0, "prev_earnings": 0, "score": 0},
        }

        if s_engine is None:
            s_engine = ScoreEngine([self.contestants["p1"]["name"], self.contestants["p2"]["name"], self.contestants["p3"]["name"]])
        self.s_engine = s_engine

        # Theme & Singleton Audio Manager
        self.theme = ThemeConfigManager.load_theme_xml()
        self.audio_manager = AudioManager(parent=self)
        self.audio_manager.load_from_dict(self.theme.get("sounds", {}))

        # Internal State & Progression Lock
        self.current_round = 1
        self.unlocked_rounds = {1: True, 2: False, 3: False}
        self.selected_clue = None
        self.selected_points = 200
        self.clue_buttons = {}
        self.board_cache = {}
        self.category_names = [f"CATEGORY {i+1}" for i in range(6)]
        self.intro_col_index = 0

        # Final Jeopardy State & Multi-Clue Pool
        self.final_clue_data = None
        self.final_db_clues_list = []
        self.final_db_clue_index = 0
        self.final_wagers = {"p1": 0, "p2": 0, "p3": 0}
        self.final_timer = QTimer(self)
        self.final_timer_seconds = 30
        self.final_timer.timeout.connect(self._on_final_timer_tick)

        # Buzzer & 5-Second Countdown State
        self.buzzer_locked = True
        self.buzzer_active_player = None
        self.excluded_buzzers = set()
        self.tv_answer_visible = False
        self.is_final_answer_visible = False
        self._pending_dd_wager = None
        self._dd_wager_locked = False
        self.host_timer_5s = QTimer(self)
        self.host_timer_5s.setInterval(100)
        self.host_timer_5s.timeout.connect(self._on_host_timer_5s_tick)
        self.host_timer_remaining_ms = 5000

        # Build UI
        self.setStyleSheet(APP_STYLE)
        self._create_menu_bar()
        self._build_top_header()
        self._build_central_tabs()
        self._build_bottom_dock()
        self._register_event_bus()

        # Load Data
        self._load_board_for_round(1)
        self._load_final_jeopardy_data()
        self._refresh_database_table()

    def _create_menu_bar(self):
        menu_bar = self.menuBar()
        menu_bar.setStyleSheet("""
            QMenuBar {
                background-color: #161b22;
                color: #c9d1d9;
                font-weight: bold;
                border-bottom: 1px solid #30363d;
                padding: 2px 6px;
            }
            QMenuBar::item:selected {
                background-color: #30363d;
                color: #58a6ff;
            }
            QMenu {
                background-color: #161b22;
                color: #c9d1d9;
                border: 1px solid #30363d;
                padding: 4px;
            }
            QMenu::item:selected {
                background-color: #1f6feb;
                color: #ffffff;
            }
        """)

        # 1. File Menu
        menu_file = menu_bar.addMenu("File")

        act_load_db = QAction("Load SQLite Database...", self)
        act_load_db.triggered.connect(self._menu_load_db)
        menu_file.addAction(act_load_db)

        act_save_db = QAction("Save Database Changes", self)
        act_save_db.triggered.connect(self._menu_save_db)
        menu_file.addAction(act_save_db)

        menu_file.addSeparator()

        act_reset_game = QAction("Reset Match", self)
        act_reset_game.triggered.connect(self._menu_reset_game)
        menu_file.addAction(act_reset_game)

        act_exit = QAction("Exit", self)
        act_exit.triggered.connect(self.close)
        menu_file.addAction(act_exit)

        # 2. TV Display Menu
        menu_tv = menu_bar.addMenu("TV Display")

        act_open_tv = QAction("Open TV Display", self)
        act_open_tv.triggered.connect(lambda: event_bus.toggle_tv_window.emit(True))
        menu_tv.addAction(act_open_tv)

        act_close_tv = QAction("Close TV Display", self)
        act_close_tv.triggered.connect(lambda: event_bus.toggle_tv_window.emit(False))
        menu_tv.addAction(act_close_tv)

        act_toggle_fs = QAction("Toggle Fullscreen (F11)", self)
        act_toggle_fs.setShortcut("F11")
        act_toggle_fs.triggered.connect(lambda: event_bus.set_tv_fullscreen.emit())
        menu_tv.addAction(act_toggle_fs)

        act_secondary_screen = QAction("Move to Secondary Screen", self)
        act_secondary_screen.triggered.connect(self._menu_move_tv_to_secondary)
        menu_tv.addAction(act_secondary_screen)

        # 3. Settings Menu
        menu_settings = menu_bar.addMenu("Settings")

        act_config = QAction("Visuals, Fonts, Animations & Sound Settings...", self)
        act_config.triggered.connect(self._open_settings_dialog)
        menu_settings.addAction(act_config)

        menu_perf = menu_settings.addMenu("Graphics Profile (OpenGL)")
        act_perf_ultra = QAction("Studio Max (OpenGL GPU + 4x MSAA + VSync)", self)
        act_perf_ultra.triggered.connect(lambda: self._set_perf_profile("ultra"))
        act_perf_smooth = QAction("Smooth (60 FPS Cached)", self)
        act_perf_smooth.triggered.connect(lambda: self._set_perf_profile("smooth"))
        act_perf_basic = QAction("Power Saver (30 FPS)", self)
        act_perf_basic.triggered.connect(lambda: self._set_perf_profile("basic"))
        menu_perf.addAction(act_perf_ultra)
        menu_perf.addAction(act_perf_smooth)
        menu_perf.addAction(act_perf_basic)

        menu_settings.addSeparator()

        act_export_theme = QAction("Export Theme Package (.zip)...", self)
        act_export_theme.triggered.connect(self._menu_export_theme_zip)
        menu_settings.addAction(act_export_theme)

        act_import_theme = QAction("Import Theme Package (.zip)...", self)
        act_import_theme.triggered.connect(self._menu_import_theme_zip)
        menu_settings.addAction(act_import_theme)

    def _menu_load_db(self):
        f, _ = QFileDialog.getOpenFileName(self, "Load SQLite Database", "", "SQLite Database (*.db *.sqlite);;All Files (*)")
        if f:
            self.db_path = f
            self.q_engine = QuestionEngine(self.db_path)
            self._load_board_for_round(self.current_round)
            self._load_final_jeopardy_data()
            self._refresh_database_table()
            QMessageBox.information(self, "Database Loaded", f"Successfully loaded database:\n{f}")

    def _menu_save_db(self):
        QMessageBox.information(self, "Database Saved", "All question data has been saved to SQLite database.")

    def _menu_reset_game(self):
        reply = QMessageBox.question(
            self,
            "Reset Match Confirmation",
            "Are you sure you want to reset all scores and clue states to default?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._reset_entire_game()

    def _reset_entire_game(self):
        self.q_engine.reset_session()
        self.q_engine.reset_all_used()
        if hasattr(self, "s_engine"):
            self.s_engine.reset_scores()
        for p in self.contestants.values():
            p["score"] = 0
        self.unlocked_rounds = {1: True, 2: False, 3: False}
        self.current_round = 1
        self._update_round_button_styles()
        self._update_live_score_display()
        self._load_board_for_round(1)
        self._load_final_jeopardy_data()
        self._reset_final_jeopardy_sequence(keep_clue=True)
        self._reset_buzzers()
        event_bus.reset_game_state.emit()
        self.tabs.setCurrentIndex(0)
        self.roster_status.setText("Status: Match reset. Ready to start.")
        self.roster_status.setStyleSheet("color: #8b949e; font-style: italic;")

    def _menu_move_tv_to_secondary(self):
        screens = QApplication.screens()
        if len(screens) > 1:
            for win in QApplication.topLevelWidgets():
                if win.__class__.__name__ == "TVDisplayWindow":
                    win.setScreen(screens[1])
                    win.showFullScreen()
                    QMessageBox.information(self, "Secondary Display", f"TV Display moved to screen: {screens[1].name()}")
                    return
            QMessageBox.information(self, "Secondary Display", f"Found secondary screen: {screens[1].name()}")
        else:
            QMessageBox.warning(self, "Warning", "No secondary display connected to this system.")

    def _set_perf_profile(self, profile: str):
        self.theme["performance_profile"] = profile
        ThemeConfigManager.save_theme_xml(self.theme)
        event_bus.set_performance_profile.emit(profile)
        QMessageBox.information(self, "Graphics Profile", f"Graphics profile set to: {profile}")

    def _menu_export_theme_zip(self):
        f, _ = QFileDialog.getSaveFileName(self, "Export Theme Package (.zip)", "broadcast_theme.zip", "Zip Packages (*.zip *.openj-theme);;All Files (*)")
        if f:
            try:
                xml_path = str(PROJECT_ROOT / "ui" / "assets" / "theme.xml")
                assets_dir = str(PROJECT_ROOT / "ui" / "assets")
                ThemePackageEngine.export_theme_to_zip(xml_path, assets_dir, f)
                QMessageBox.information(self, "Success", f"Theme package exported successfully:\n{f}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export zip file: {e}")

    def _menu_import_theme_zip(self):
        f, _ = QFileDialog.getOpenFileName(self, "Import Theme Package (.zip)", "", "Zip Packages (*.zip *.openj-theme);;All Files (*)")
        if f:
            try:
                extract_to = str(PROJECT_ROOT / "ui" / "assets")
                xml_path = ThemePackageEngine.import_theme_from_zip(f, extract_to)
                self.theme = ThemeConfigManager.load_theme_xml(str(xml_path))
                event_bus.reload_theme_config.emit()
                event_bus.update_theme_config.emit(self.theme)
                QMessageBox.information(self, "Success", "Theme package imported successfully! Visuals updated.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to import zip file: {e}")

    def closeEvent(self, event):
        reply = QMessageBox.question(
            self,
            "Exit Confirmation",
            "Are you sure you want to close the Host Controller dashboard?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            event.accept()
        else:
            event.ignore()

    def _build_top_header(self):
        """Unified top ribbon consolidating Standby, Intro Video Merge, Outro Music, and Round coordination."""
        header_widget = QWidget()
        header_widget.setStyleSheet("background-color: #161b22; border-bottom: 1px solid #30363d;")
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(16, 8, 16, 8)
        header_layout.setSpacing(10)

        title_lbl = QLabel("OPEN-J | CONTROLLER")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: 900; color: #58a6ff; letter-spacing: 1px;")
        header_layout.addWidget(title_lbl)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.VLine)
        sep1.setStyleSheet("color: #30363d;")
        header_layout.addWidget(sep1)

        # Commercial Break / Standby Waiting Screen Button
        self._break_active = False
        self.btn_commercial_break = QPushButton("CHẾ ĐỘ CHỜ / QUẢNG CÁO (STANDBY)")
        self.btn_commercial_break.setToolTip("Toggle static standby waiting screen on TV display")
        self.btn_commercial_break.setStyleSheet("""
            QPushButton {
                background-color: #21262d; border: 1px solid #30363d; color: #c9d1d9;
                font-weight: bold; padding: 5px 12px; border-radius: 5px; font-size: 12px;
            }
            QPushButton:hover { background-color: #30363d; border-color: #d29922; color: #d29922; }
        """)
        self.btn_commercial_break.clicked.connect(self._on_toggle_commercial_break)
        header_layout.addWidget(self.btn_commercial_break)

        # Requirement #7: Intro Video -> Standby Merge Button
        self.btn_play_intro_video = QPushButton("▶ INTRO VIDEO")
        self.btn_play_intro_video.setToolTip("Play Intro Video on TV then smoothly merge into Static Standby Wallpaper")
        self.btn_play_intro_video.setStyleSheet("""
            QPushButton {
                background-color: #1f6feb; border: 1px solid #388bfd; color: #ffffff;
                font-weight: bold; padding: 5px 12px; border-radius: 5px; font-size: 12px;
            }
            QPushButton:hover { background-color: #388bfd; }
        """)
        self.btn_play_intro_video.clicked.connect(self._on_top_play_intro_video)
        header_layout.addWidget(self.btn_play_intro_video)

        # Requirement #7: Outro Music on Static Standby Button
        self.btn_play_outro_music = QPushButton("🎵 OUTRO MUSIC")
        self.btn_play_outro_music.setToolTip("Show Static Standby Wallpaper on TV and play Outro Music")
        self.btn_play_outro_music.setStyleSheet("""
            QPushButton {
                background-color: #8957e5; border: 1px solid #a371f7; color: #ffffff;
                font-weight: bold; padding: 5px 12px; border-radius: 5px; font-size: 12px;
            }
            QPushButton:hover { background-color: #a371f7; }
        """)
        self.btn_play_outro_music.clicked.connect(self._on_top_play_outro_music)
        header_layout.addWidget(self.btn_play_outro_music)

        header_layout.addStretch()

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setStyleSheet("color: #30363d;")
        header_layout.addWidget(sep2)

        lbl_round_tag = QLabel("ROUND:")
        lbl_round_tag.setStyleSheet("font-size: 11px; font-weight: 800; color: #8b949e;")
        header_layout.addWidget(lbl_round_tag)

        self.btn_round1 = QPushButton("[ 1. JEOPARDY! ]")
        self.btn_round2 = QPushButton("[ 2. DOUBLE JEOPARDY! ]")
        self.btn_round3 = QPushButton("[ 3. FINAL JEOPARDY! ]")

        for b in (self.btn_round1, self.btn_round2, self.btn_round3):
            b.setCursor(Qt.PointingHandCursor)

        self.btn_round1.clicked.connect(lambda: self._on_round_button_clicked(1))
        self.btn_round2.clicked.connect(lambda: self._on_round_button_clicked(2))
        self.btn_round3.clicked.connect(lambda: self._on_round_button_clicked(3))

        self.round_group = QButtonGroup(self)
        self.round_group.addButton(self.btn_round1, 1)
        self.round_group.addButton(self.btn_round2, 2)
        self.round_group.addButton(self.btn_round3, 3)

        self._update_round_button_styles()

        header_layout.addWidget(self.btn_round1)
        header_layout.addWidget(self.btn_round2)
        header_layout.addWidget(self.btn_round3)

        self.header_widget = header_widget

    def _on_toggle_commercial_break(self):
        if not getattr(self, "_break_active", False):
            self._break_active = True
            event_bus.trigger_standby_mode.emit("normal")
            self.btn_commercial_break.setText("RESUME GAMEPLAY (RETURN TO BOARD)")
            self.btn_commercial_break.setStyleSheet("""
                QPushButton {
                    background-color: #238636; border: 1px solid #2ea043; color: #ffffff;
                    font-weight: bold; padding: 5px 12px; border-radius: 5px; font-size: 12px;
                }
                QPushButton:hover { background-color: #2ea043; }
            """)
        else:
            self._break_active = False
            event_bus.stop_standby_media.emit()
            event_bus.trigger_standby_mode.emit("off")
            self.btn_commercial_break.setText("CHẾ ĐỘ CHỜ / QUẢNG CÁO (STANDBY)")
            self.btn_commercial_break.setStyleSheet("""
                QPushButton {
                    background-color: #21262d; border: 1px solid #30363d; color: #c9d1d9;
                    font-weight: bold; padding: 5px 12px; border-radius: 5px; font-size: 12px;
                }
                QPushButton:hover { background-color: #30363d; border-color: #d29922; color: #d29922; }
            """)

    def _on_top_play_intro_video(self):
        anim_cfg = self.theme.get("animations", {})
        vid = anim_cfg.get("intro_video_path", "")
        if not vid or not os.path.isfile(vid):
            QMessageBox.information(
                self,
                "Configure Intro Video",
                "Please select an Intro Video file in Settings -> Tab 3 (Animation & Intro/Outro)."
            )
            self._open_settings_dialog(initial_tab=2)
            return
        self._break_active = True
        self.btn_commercial_break.setText("RESUME GAMEPLAY (RETURN TO BOARD)")
        self.btn_commercial_break.setStyleSheet("""
            QPushButton {
                background-color: #238636; border: 1px solid #2ea043; color: #ffffff;
                font-weight: bold; padding: 5px 12px; border-radius: 5px; font-size: 12px;
            }
            QPushButton:hover { background-color: #2ea043; }
        """)
        event_bus.trigger_standby_intro_video.emit({
            "video_path": vid,
            "merge_seconds": float(anim_cfg.get("intro_merge_seconds", 5.0)),
            "fade_duration_ms": int(anim_cfg.get("intro_fade_duration_ms", 1500)),
        })

    def _on_top_play_outro_music(self):
        anim_cfg = self.theme.get("animations", {})
        outro = anim_cfg.get("outro_music_path") or self.theme.get("sounds", {}).get("outro_music", "")
        if not outro or not os.path.isfile(outro):
            QMessageBox.information(
                self,
                "Configure Outro Music",
                "Please select an Outro Music audio file in Settings -> Tab 3 (Animation) or Tab 4 (Sound Manager)."
            )
            self._open_settings_dialog(initial_tab=2)
            return
        self._break_active = True
        self.btn_commercial_break.setText("RESUME GAMEPLAY (RETURN TO BOARD)")
        self.btn_commercial_break.setStyleSheet("""
            QPushButton {
                background-color: #238636; border: 1px solid #2ea043; color: #ffffff;
                font-weight: bold; padding: 5px 12px; border-radius: 5px; font-size: 12px;
            }
            QPushButton:hover { background-color: #2ea043; }
        """)
        event_bus.trigger_standby_outro_music.emit(outro)

    def _open_settings_dialog(self, initial_tab: int = 0):
        dlg = SettingsDialog(self.theme, self.audio_manager, self)
        if 0 <= initial_tab < dlg.tab_widget.count():
            dlg.tab_widget.setCurrentIndex(initial_tab)
        if dlg.exec():
            self.theme = dlg.theme

    def _build_central_tabs(self):
        container = QWidget()
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.setSpacing(0)
        c_layout.addWidget(self.header_widget)

        self.tabs = QTabWidget(self)
        self.tab1 = self._build_tab1_pregame()
        self.tab2 = self._build_tab2_board()
        self.tab3 = self._build_tab3_final()
        self.tab4 = self._build_tab4_database()

        self.tabs.addTab(self.tab1, "1. Pregame & Roster")
        self.tabs.addTab(self.tab2, "2. Rounds 1 & 2 Board")
        self.tabs.addTab(self.tab3, "3. Final Jeopardy")
        self.tabs.addTab(self.tab4, "4. Database (SQLite)")
        self.tabs.currentChanged.connect(self._on_tab_changed)

        c_layout.addWidget(self.tabs)
        self.setCentralWidget(container)

    # =========================================================================
    # TAB 1: PREGAME SETUP
    # =========================================================================

    def _build_tab1_pregame(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        header = QLabel("CONTESTANT ROSTER SETUP (3 PODIUMS)")
        header.setStyleSheet("font-size: 15px; font-weight: bold; color: #58a6ff;")
        layout.addWidget(header)

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(16)
        self.p_inputs = {}

        defaults = [
            ("p1", "Podium 1 (Stage Left)", "Ken Jennings", "Returning Champion", 74, 2520700),
            ("p2", "Podium 2 (Center)", "Gold Ship", "New Challenger", 0, 0),
            ("p3", "Podium 3 (Stage Right)", "Agnes Tachyon", "New Challenger", 0, 0),
        ]

        for p_id, title, d_name, d_status, d_wins, d_prev in defaults:
            box = QGroupBox(title)
            b_layout = QFormLayout(box)
            b_layout.setContentsMargins(14, 16, 14, 14)
            b_layout.setSpacing(10)

            name_edit = QLineEdit(d_name)
            status_combo = QComboBox()
            status_combo.addItems(["Returning Champion", "New Challenger"])
            status_combo.setCurrentText(d_status)

            wins_spin = QSpinBox()
            wins_spin.setRange(0, 100)
            wins_spin.setValue(d_wins)

            prev_spin = QSpinBox()
            prev_spin.setRange(0, 10000000)
            prev_spin.setValue(d_prev)
            prev_spin.setPrefix("$ ")

            b_layout.addRow("Contestant Name:", name_edit)
            b_layout.addRow("Status:", status_combo)
            b_layout.addRow("Consecutive Wins:", wins_spin)
            b_layout.addRow("Career Earnings:", prev_spin)

            self.p_inputs[p_id] = {
                "name": name_edit,
                "status": status_combo,
                "wins": wins_spin,
                "prev": prev_spin,
            }
            cards_layout.addWidget(box)

        layout.addLayout(cards_layout)

        btn_layout = QHBoxLayout()
        self.btn_lock_roster = QPushButton("[Lock Roster & Start Match]")
        self.btn_lock_roster.setStyleSheet("""
            QPushButton {
                background-color: #238636;
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 22px;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #2ea043; }
        """)
        self.btn_lock_roster.clicked.connect(self._on_lock_roster)

        self.roster_status = QLabel("Status: Ready to lock roster.")
        self.roster_status.setStyleSheet("color: #8b949e; font-style: italic;")

        btn_layout.addWidget(self.btn_lock_roster)
        btn_layout.addWidget(self.roster_status)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background-color: transparent;")
        scroll.setWidget(widget)
        return scroll

    def _on_lock_roster(self):
        DBManager().activate_game_categories()

        # Giữ nguyên màn hình chờ (logo to), không tắt Standby khi bắt đầu trận đấu
        self._break_active = True
        if hasattr(self, "btn_commercial_break"):
            self.btn_commercial_break.setText("RESUME GAMEPLAY (RETURN TO BOARD)")
            self.btn_commercial_break.setStyleSheet("""
                QPushButton {
                    background-color: #238636; border: 1px solid #2ea043; color: #ffffff;
                    font-weight: bold; padding: 5px 12px; border-radius: 5px; font-size: 12px;
                }
                QPushButton:hover { background-color: #2ea043; }
            """)
        event_bus.trigger_standby_mode.emit("normal")

        player_names = []
        for p_id in ("p1", "p2", "p3"):
            info = self.p_inputs[p_id]
            self.contestants[p_id]["name"] = info["name"].text().strip() or f"Player {p_id}"
            self.contestants[p_id]["status"] = info["status"].currentText()
            self.contestants[p_id]["wins"] = info["wins"].value()
            self.contestants[p_id]["prev_earnings"] = info["prev"].value()
            player_names.append(self.contestants[p_id]["name"])

        self.s_engine = ScoreEngine(player_names)
        self._update_dock_player_labels()
        self._update_live_score_display()
        self._refresh_dd_player_combo()

        self.q_engine.lock_session_data()
        self._load_board_for_round(1)
        self._load_final_jeopardy_data()
        self._reset_final_jeopardy_sequence(keep_clue=True)

        event_bus.players_updated.emit(self.contestants)
        event_bus.score_updated.emit(self.s_engine.get_all_scores())

        self.roster_status.setText("Roster locked & match started successfully!")
        self.roster_status.setStyleSheet("color: #3fb950; font-weight: bold;")
        self.tabs.setCurrentIndex(1)

    # =========================================================================
    # TAB 2: ROUND 1 & 2 COORDINATION + INLINE DAILY DOUBLE WAGER (REQ #8)
    # =========================================================================

    def _build_tab2_board(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # CATEGORY REVEAL CONTROLS RIBBON
        cat_group = QGroupBox("CATEGORY REVEAL & BOARD REVEAL")
        cat_layout = QHBoxLayout(cat_group)
        cat_layout.setContentsMargins(12, 10, 12, 10)
        cat_layout.setSpacing(10)

        self.chk_auto_intro = QCheckBox(" Auto Sequence")
        self.chk_auto_intro.setChecked(False)
        self.chk_auto_intro.setVisible(False)

        self.btn_cat_intro = QPushButton(" Intro Categories")
        self.btn_cat_intro.setVisible(False)

        btn_blank = QPushButton("BLANK BOARD")
        btn_blank.setStyleSheet("background-color: #21262d; color: #c9d1d9; font-weight: bold; padding: 7px 12px;")
        btn_blank.clicked.connect(lambda: event_bus.trigger_board_blank.emit())

        btn_fill = QPushButton("RANDOM FILL")
        btn_fill.setStyleSheet("background-color: #21262d; color: #c9d1d9; font-weight: bold; padding: 7px 12px;")
        btn_fill.clicked.connect(lambda: event_bus.trigger_board_fill.emit())

        self.btn_intro_sequence = QPushButton("START CATEGORY INTRO")
        self.btn_intro_sequence.setToolTip("Sequentially open and reveal categories (3 steps per column)")
        self.btn_intro_sequence.setStyleSheet("background-color: #1f6feb; color: white; font-weight: bold; padding: 7px 14px; border-radius: 5px;")
        self.btn_intro_sequence.clicked.connect(self._on_intro_sequence_clicked)

        self.btn_cancel_intro = QPushButton("RETURN TO BOARD")
        self.btn_cancel_intro.setStyleSheet("background-color: #d29922; color: #0d1117; font-weight: bold; padding: 7px 14px; border-radius: 5px;")
        self.btn_cancel_intro.clicked.connect(self._on_cat_cancel)

        btn_obs_fs = QPushButton("OBS: F11")
        btn_obs_fs.setStyleSheet("background-color: #8957e5; color: white; font-weight: bold; padding: 7px 14px; border-radius: 5px;")
        btn_obs_fs.clicked.connect(lambda: event_bus.set_display_fullscreen_toggle.emit())

        cat_layout.addWidget(btn_blank)
        cat_layout.addWidget(btn_fill)
        cat_layout.addWidget(self.btn_intro_sequence)
        cat_layout.addWidget(self.btn_cancel_intro)
        cat_layout.addWidget(btn_obs_fs)
        cat_layout.addStretch()

        layout.addWidget(cat_group)

        splitter = QSplitter(Qt.Horizontal)

        # Left: 6x5 Matrix Board
        left_frame = QFrame()
        left_frame.setStyleSheet("background-color: #000000; border: 1px solid #1e293b; border-radius: 0px;")
        l_layout = QVBoxLayout(left_frame)
        l_layout.setContentsMargins(8, 8, 8, 8)

        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(6)

        self.cat_headers = []
        for c in range(6):
            lbl = QLabel(f"CATEGORY {c+1}")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setWordWrap(True)
            lbl.setStyleSheet("""
                background-color: #0b1354;
                color: #ffffff;
                font-weight: 800;
                font-size: 13px;
                border: 2px solid #1e3a8a;
                border-radius: 0px;
                padding: 6px 2px;
                min-height: 44px;
            """)
            self.cat_headers.append(lbl)
            self.grid_layout.addWidget(lbl, 0, c)

        self.clue_buttons = {}
        for r in range(5):
            for c in range(6):
                btn = QPushButton("$0")
                btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                btn.setMinimumSize(76, 48)
                btn.setCursor(Qt.PointingHandCursor)
                btn.clicked.connect(lambda chk=False, col=c, row=r: self._on_clue_button_clicked(col, row))
                self.clue_buttons[(c, r)] = btn
                self.grid_layout.addWidget(btn, r + 1, c)

        l_layout.addLayout(self.grid_layout)
        splitter.addWidget(left_frame)

        # Right: Peek Box + 5-Second Countdown + Inline DD Wager + 2-Step Broadcast Controls
        right_frame = QFrame()
        right_frame.setStyleSheet("background-color: #161b22; border: 1px solid #30363d; border-radius: 6px;")
        r_layout = QVBoxLayout(right_frame)
        r_layout.setContentsMargins(14, 12, 14, 12)
        r_layout.setSpacing(10)

        peek_lbl = QLabel("CLUE & ANSWER PEEK (HOST ONLY)")
        peek_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #f59e0b;")
        r_layout.addWidget(peek_lbl)

        self.peek_text = QTextEdit()
        self.peek_text.setReadOnly(True)
        self.peek_text.setStyleSheet("background-color: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 8px; color: #f0f6fc;")
        self.peek_text.setMaximumHeight(140)
        self.peek_text.setMinimumHeight(95)
        self._set_peek_placeholder()
        r_layout.addWidget(self.peek_text)

        # 5-Second Countdown
        timer_box = QGroupBox("5S COUNTDOWN")
        tb_layout = QVBoxLayout(timer_box)
        tb_layout.setSpacing(6)

        t_row = QHBoxLayout()
        self.host_timer_lbl = QLabel("05.0s")
        self.host_timer_lbl.setStyleSheet("font-size: 22px; font-weight: 900; color: #3fb950; font-family: monospace;")
        self.host_timer_lbl.setAlignment(Qt.AlignCenter)

        self.btn_timer_start = QPushButton("START 5S")
        self.btn_timer_start.setStyleSheet("background-color: #238636; color: white; font-weight: bold; padding: 5px 10px;")
        self.btn_timer_start.clicked.connect(self._start_host_timer_5s)

        self.btn_timer_stop = QPushButton("CANCEL 5S")
        self.btn_timer_stop.setStyleSheet("background-color: #da3633; color: white; font-weight: bold; padding: 5px 10px;")
        self.btn_timer_stop.clicked.connect(self._reset_host_timer_5s)

        t_row.addWidget(self.host_timer_lbl, 1)
        t_row.addWidget(self.btn_timer_start)
        t_row.addWidget(self.btn_timer_stop)

        self.host_timer_bar = QProgressBar()
        self.host_timer_bar.setRange(0, 5000)
        self.host_timer_bar.setValue(5000)
        self.host_timer_bar.setTextVisible(False)
        self.host_timer_bar.setFixedHeight(8)
        self.host_timer_bar.setStyleSheet("""
            QProgressBar { background-color: #0d1117; border: 1px solid #30363d; border-radius: 4px; }
            QProgressBar::chunk { background-color: #238636; border-radius: 3px; }
        """)

        tb_layout.addLayout(t_row)
        tb_layout.addWidget(self.host_timer_bar)
        r_layout.addWidget(timer_box)

        # 2-Step Broadcast Controls + Inline Daily Double Wager Panel (Requirement #8)
        cmd_box = QGroupBox("BROADCAST PLAYOUT & DAILY DOUBLE WAGER")
        cb_layout = QVBoxLayout(cmd_box)
        cb_layout.setSpacing(8)

        self.btn_display_clue = QPushButton("1. ZOOM POINT CELL / TV SPLASH")
        self.btn_display_clue.setStyleSheet("""
            QPushButton {
                background-color: #1f6feb; color: white; font-weight: bold;
                font-size: 13px; padding: 8px; border: 1px solid #388bfd;
            }
            QPushButton:hover { background-color: #388bfd; }
        """)
        self.btn_display_clue.clicked.connect(self._on_display_clue_clicked)

        # Inline Daily Double Wager Panel (Requirement #8)
        self.dd_wager_frame = QFrame()
        self.dd_wager_frame.setStyleSheet("""
            QFrame {
                background-color: #281219;
                border: 2px solid #e11d48;
                border-radius: 6px;
                padding: 6px;
            }
        """)
        dd_lay = QVBoxLayout(self.dd_wager_frame)
        dd_lay.setContentsMargins(8, 8, 8, 8)
        dd_lay.setSpacing(6)

        lbl_dd_header = QLabel("★ DAILY DOUBLE WAGER ENTRY (NHẬP TIỀN CƯỢC TRƯỚC KHI LẬT CÂU HỎI)")
        lbl_dd_header.setStyleSheet("color: #fda4af; font-weight: 900; font-size: 12px; border: none;")
        dd_lay.addWidget(lbl_dd_header)

        dd_form = QHBoxLayout()
        self.dd_player_combo = QComboBox()
        self._refresh_dd_player_combo()
        self.dd_player_combo.currentIndexChanged.connect(self._on_dd_player_changed)

        self.dd_wager_spin = QSpinBox()
        self.dd_wager_spin.setRange(5, 1000)
        self.dd_wager_spin.setSingleStep(100)
        self.dd_wager_spin.setValue(200)
        self.dd_wager_spin.setPrefix("$ ")

        dd_form.addWidget(QLabel("Player:"))
        dd_form.addWidget(self.dd_player_combo, 1)
        dd_form.addWidget(QLabel("Wager:"))
        dd_form.addWidget(self.dd_wager_spin, 1)
        dd_lay.addLayout(dd_form)

        self.lbl_dd_range_hint = QLabel("Allowed Wager: $5 - $1,000")
        self.lbl_dd_range_hint.setStyleSheet("color: #fbbf24; font-size: 11px; font-weight: bold; border: none;")
        dd_lay.addWidget(self.lbl_dd_range_hint)

        self.btn_reveal_dd = QPushButton("[LOCK DD WAGER & 3D FLIP TO CLUE]")
        self.btn_reveal_dd.setStyleSheet("""
            QPushButton {
                background-color: #e11d48; color: white; font-weight: bold;
                font-size: 13px; padding: 8px; border: 1px solid #f43f5e;
            }
            QPushButton:hover { background-color: #f43f5e; }
        """)
        self.btn_reveal_dd.clicked.connect(self._on_reveal_dd_clicked)
        dd_lay.addWidget(self.btn_reveal_dd)
        self.dd_wager_frame.setVisible(False)

        self.btn_clue_reveal = QPushButton("2. REVEAL CLUE TEXT")
        self.btn_clue_reveal.setStyleSheet("""
            QPushButton {
                background-color: #8957e5; color: white; font-weight: bold;
                font-size: 13px; padding: 8px; border: 1px solid #a371f7;
            }
            QPushButton:hover { background-color: #a371f7; }
        """)
        self.btn_clue_reveal.clicked.connect(self._on_clue_reveal_clicked)

        self.btn_toggle_answer = QPushButton("TOGGLE TV ANSWER")
        self.btn_toggle_answer.setStyleSheet("""
            QPushButton {
                background-color: #21262d; color: #8b949e; font-weight: bold;
                font-size: 13px; padding: 8px; border: 1px solid #30363d;
            }
            QPushButton:hover { background-color: #30363d; color: #ffffff; }
        """)
        self.btn_toggle_answer.clicked.connect(self._on_toggle_tv_answer_clicked)

        self.btn_close_clue = QPushButton("CLOSE CLUE / RETURN TO BOARD")
        self.btn_close_clue.setStyleSheet("""
            QPushButton {
                background-color: #d29922; color: #0d1117; font-weight: bold;
                font-size: 13px; padding: 8px; border: 1px solid #e3b341;
            }
            QPushButton:hover { background-color: #e3b341; }
        """)
        self.btn_close_clue.clicked.connect(self._on_close_clue_clicked)

        self.clue_status = QLabel("TV Status: Main Board active")
        self.clue_status.setStyleSheet("color: #8b949e; font-style: italic;")

        cb_layout.addWidget(self.btn_display_clue)
        cb_layout.addWidget(self.dd_wager_frame)
        cb_layout.addWidget(self.btn_clue_reveal)
        cb_layout.addWidget(self.btn_toggle_answer)
        cb_layout.addWidget(self.btn_close_clue)
        cb_layout.addWidget(self.clue_status)
        r_layout.addWidget(cmd_box)

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        right_scroll.setWidget(right_frame)

        splitter.addWidget(right_scroll)
        splitter.setStretchFactor(0, 64)
        splitter.setStretchFactor(1, 36)
        layout.addWidget(splitter)

        finish_row = QHBoxLayout()
        finish_row.addStretch()
        self.btn_finish_round = QPushButton("COMPLETE ROUND 1 & UNLOCK ROUND 2")
        self.btn_finish_round.setStyleSheet("""
            QPushButton {
                background-color: #238636;
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 24px;
                border-radius: 6px;
                border: 1px solid #2ea043;
            }
            QPushButton:hover { background-color: #2ea043; }
        """)
        self.btn_finish_round.setCursor(Qt.PointingHandCursor)
        self.btn_finish_round.clicked.connect(self._on_finish_round_clicked)
        finish_row.addWidget(self.btn_finish_round)
        layout.addLayout(finish_row)

        return widget

    def _refresh_dd_player_combo(self):
        if not hasattr(self, "dd_player_combo"):
            return
        curr_pid = self.dd_player_combo.currentData() or "p1"
        self.dd_player_combo.blockSignals(True)
        self.dd_player_combo.clear()
        for pid in ("p1", "p2", "p3"):
            self.dd_player_combo.addItem(f"{self.contestants[pid]['name']} (${self.contestants[pid]['score']})", pid)
        idx = {"p1": 0, "p2": 1, "p3": 2}.get(curr_pid, 0)
        self.dd_player_combo.setCurrentIndex(idx)
        self.dd_player_combo.blockSignals(False)
        self._on_dd_player_changed()

    def _on_dd_player_changed(self):
        if not hasattr(self, "dd_player_combo") or not hasattr(self, "dd_wager_spin"):
            return
        pid = self.dd_player_combo.currentData() or "p1"
        score = self.contestants.get(pid, {}).get("score", 0)
        ceiling = 1000 if self.current_round == 1 else 2000
        max_wager = max(score, ceiling)
        self.dd_wager_spin.setRange(5, max_wager)
        default_val = self.selected_points if 5 <= self.selected_points <= max_wager else min(max_wager, ceiling)
        self.dd_wager_spin.setValue(max(5, default_val))
        if hasattr(self, "lbl_dd_range_hint"):
            self.lbl_dd_range_hint.setText(
                f"Contestant Score: ${score:,} | Allowed DD Wager: $5 – ${max_wager:,}"
            )

    def _on_intro_sequence_clicked(self):
        if not hasattr(self, "intro_seq_state"):
            self.intro_seq_state = "SHOW"
            self.intro_col_index = 0

        curr = self.intro_col_index

        if self.intro_seq_state == "SHOW":
            event_bus.trigger_category_step.emit(1, curr)
            self.btn_intro_sequence.setText(f"REVEAL CATEGORY {curr+1}")
            self.btn_intro_sequence.setStyleSheet("background-color: #238636; color: white; font-weight: bold; padding: 7px 14px; border-radius: 5px;")
            self.intro_seq_state = "REVEAL"

        elif self.intro_seq_state == "REVEAL":
            event_bus.trigger_category_step.emit(2, curr)
            event_bus.play_sound_event.emit("round_category_intro")
            if curr < 5:
                self.btn_intro_sequence.setText(f"SLIDE TO CATEGORY {curr+2} (LOGO)")
                self.btn_intro_sequence.setStyleSheet("background-color: #1f6feb; color: white; font-weight: bold; padding: 7px 14px; border-radius: 5px;")
                self.intro_seq_state = "SLIDE"
            else:
                self.btn_intro_sequence.setText("COMPLETE & RETURN TO BOARD")
                self.btn_intro_sequence.setStyleSheet("background-color: #d29922; color: #0d1117; font-weight: bold; padding: 7px 14px; border-radius: 5px;")
                self.intro_seq_state = "RETURN"

        elif self.intro_seq_state == "SLIDE":
            self.intro_col_index += 1
            nxt = self.intro_col_index
            event_bus.trigger_category_step.emit(3, nxt)
            self.btn_intro_sequence.setText(f"REVEAL CATEGORY {nxt+1}")
            self.btn_intro_sequence.setStyleSheet("background-color: #238636; color: white; font-weight: bold; padding: 7px 14px; border-radius: 5px;")
            self.intro_seq_state = "REVEAL"

        elif self.intro_seq_state == "RETURN":
            self._on_cat_cancel()

    def _on_cat_cancel(self):
        self.intro_col_index = 0
        self.intro_seq_state = "SHOW"
        if hasattr(self, "btn_intro_sequence"):
            self.btn_intro_sequence.setText("START CATEGORY INTRO")
            self.btn_intro_sequence.setStyleSheet("background-color: #1f6feb; color: white; font-weight: bold; padding: 7px 14px; border-radius: 5px;")
        event_bus.trigger_category_step.emit(4, 0)
        event_bus.cancel_category_reveal.emit()

    def _on_cat_open_col(self):
        self._on_intro_sequence_clicked()

    def _on_cat_fade_logo(self):
        curr = getattr(self, "intro_col_index", 0)
        event_bus.trigger_category_step.emit(2, curr)
        event_bus.trigger_category_fade_logo.emit()
        event_bus.trigger_category_reveal_step.emit(1)

    def _on_cat_slide_next(self):
        curr = getattr(self, "intro_col_index", 0)
        if curr < 5:
            self.intro_col_index = curr + 1
            nxt = self.intro_col_index
            event_bus.trigger_category_step.emit(3, nxt)
            event_bus.trigger_category_slide_next.emit()
            event_bus.trigger_category_reveal_step.emit(2)
        else:
            self._on_cat_cancel()

    def _on_finish_round_clicked(self):
        if self.current_round == 1:
            reply = QMessageBox.question(
                self,
                "Confirm Round 1 Completion",
                "Are you sure you want to conclude Round 1 and unlock Round 2 (Double Jeopardy)?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.unlocked_rounds[2] = True
                self.btn_finish_round.setText("COMPLETE ROUND 2 & UNLOCK FINAL JEOPARDY")
                self._update_round_button_styles()
                self._on_round_button_clicked(2)
                event_bus.unlock_round.emit(2)
        elif self.current_round == 2:
            reply = QMessageBox.question(
                self,
                "Confirm Round 2 Completion",
                "Are you sure you want to conclude Round 2 and unlock Round 3 (Final Jeopardy)?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.unlocked_rounds[3] = True
                self.btn_finish_round.setText("ALL ROUNDS COMPLETED")
                self.btn_finish_round.setEnabled(False)
                self.btn_finish_round.setStyleSheet("background-color: #21262d; color: #8b949e; font-size: 14px; font-weight: bold; padding: 10px 24px; border-radius: 6px; border: 1px solid #30363d;")
                self._update_round_button_styles()
                self._on_round_button_clicked(3)
                event_bus.unlock_round.emit(3)

    def _update_round_button_styles(self):
        active = (
            "background-color: #1f6feb; color: #ffffff; font-weight: 900; "
            "border: 2px solid #FFD700; padding: 6px 16px; border-radius: 6px; font-size: 12px;"
        )
        inactive = (
            "background-color: #21262d; color: #c9d1d9; font-weight: bold; "
            "border: 1px solid #30363d; padding: 6px 16px; border-radius: 6px; font-size: 12px;"
        )
        locked = (
            "background-color: #161b22; color: #484f58; font-weight: bold; "
            "border: 1px solid #21262d; padding: 6px 16px; border-radius: 6px; font-size: 12px;"
        )
        rounds = [(1, self.btn_round1), (2, self.btn_round2), (3, self.btn_round3)]
        for rid, btn in rounds:
            is_unlocked = self.unlocked_rounds.get(rid, False)
            btn.setEnabled(is_unlocked)
            if not is_unlocked:
                btn.setStyleSheet(locked)
            elif self.current_round == rid:
                btn.setStyleSheet(active)
            else:
                btn.setStyleSheet(inactive)

    def _on_round_button_clicked(self, round_id):
        if not self.unlocked_rounds.get(round_id, False):
            QMessageBox.warning(self, "Round Locked", f"Round {round_id} is locked! Please complete the preceding round first.")
            return
        self.current_round = round_id
        self._update_round_button_styles()

        self._break_active = False
        if hasattr(self, "btn_commercial_break"):
            self.btn_commercial_break.setText("CHẾ ĐỘ CHỜ / QUẢNG CÁO (STANDBY)")
            self.btn_commercial_break.setStyleSheet("""
                QPushButton {
                    background-color: #21262d; border: 1px solid #30363d; color: #c9d1d9;
                    font-weight: bold; padding: 5px 12px; border-radius: 5px; font-size: 12px;
                }
                QPushButton:hover { background-color: #30363d; border-color: #d29922; color: #d29922; }
            """)
        event_bus.stop_standby_media.emit()
        event_bus.trigger_standby_mode.emit("off")

        if round_id in (1, 2):
            self.tabs.setCurrentIndex(1)
            event_bus.change_round.emit(round_id)
            self._load_board_for_round(round_id)
        elif round_id == 3:
            self.tabs.setCurrentIndex(2)
            event_bus.change_round.emit(3)
            self._refresh_final_wagers_ui()

    def _on_tab_changed(self, index):
        if index == 1:
            if self.current_round not in (1, 2):
                self.current_round = 1
            self._update_round_button_styles()
        elif index == 2:
            if not self.unlocked_rounds.get(3, False):
                QMessageBox.warning(self, "Round Locked", "Round 3 (Final Jeopardy) is locked! Please complete Rounds 1 & 2 first.")
                self.tabs.setCurrentIndex(1 if self.unlocked_rounds.get(2, False) else 0)
                return
            self.current_round = 3
            self._update_round_button_styles()
            self._refresh_final_wagers_ui()

    def _set_peek_placeholder(self):
        self.peek_text.setHtml(
            "<div style='color: #8b949e; font-style: italic; text-align: center; margin-top: 32px;'>"
            "<i>Click any board point cell to peek question, answer, and visual asset status...</i>"
            "</div>"
        )

    def _load_board_for_round(self, round_id):
        self.board_cache.clear()
        self.selected_clue = None
        self.dd_wager_frame.setVisible(False)
        self._set_peek_placeholder()

        base_multiplier = 200 if round_id == 1 else 400

        categories = self.q_engine.get_categories_for_round(round_id)
        for c in range(6):
            cat_name = categories[c].upper() if c < len(categories) else f"CATEGORY {c+1}"
            self.cat_headers[c].setText(cat_name)

        board_rows = self.q_engine.get_board_by_round(round_id)
        for row_data in board_rows:
            c, r = row_data["col_index"], row_data["row_index"]
            if 0 <= c < 6 and 0 <= r < 5:
                full_q = self.q_engine.get_question(round_id, c, r)
                self.board_cache[(c, r)] = full_q if full_q else row_data

        board_items = []
        for r in range(5):
            expected_pts = (r + 1) * base_multiplier
            for c in range(6):
                btn = self.clue_buttons[(c, r)]
                clue = self.board_cache.get((c, r))
                pts = clue["points"] if clue else expected_pts
                is_dd = bool(clue["is_daily_double"]) if clue else False
                is_used = bool(clue["is_used"]) if clue else False

                btn.setText(f"[DD] ${pts}" if is_dd else f"${pts}")
                self._apply_clue_button_style(btn, is_used=is_used, is_selected=False, is_dd=is_dd)

                board_items.append({
                    "col_index": c,
                    "row_index": r,
                    "points": pts,
                    "is_used": is_used,
                    "is_daily_double": is_dd,
                })

        cat_names = [self.cat_headers[c].text() for c in range(6)]
        event_bus.sync_categories_to_tv.emit(cat_names)
        event_bus.sync_board_state_to_tv.emit(board_items)

    def _apply_clue_button_style(self, btn, is_used=False, is_selected=False, is_dd=False):
        if is_used:
            btn.setStyleSheet("background-color: #161b22; color: #484f58; font-size: 14px; font-weight: bold; border: 1px solid #21262d; border-radius: 0px;")
        elif is_selected:
            btn.setStyleSheet("background-color: #060CE9; color: #FFCC00; font-size: 15px; font-weight: 900; border: 3px solid #ff3333; border-radius: 0px;")
        else:
            color = "#ff5555" if is_dd else "#FFCC00"
            btn.setStyleSheet(f"background-color: #060CE9; color: {color}; font-size: 15px; font-weight: 800; border: 1px solid #1c279c; border-radius: 0px;")

    def _on_clue_button_clicked(self, col, row):
        for (c, r), b in self.clue_buttons.items():
            clue_data = self.board_cache.get((c, r))
            is_used = bool(clue_data.get("is_used", 0)) if clue_data else False
            is_dd = bool(clue_data.get("is_daily_double", 0)) if clue_data else False
            self._apply_clue_button_style(b, is_used=is_used, is_selected=False, is_dd=is_dd)

        curr_btn = self.clue_buttons[(col, row)]
        curr_clue = self.board_cache.get((col, row))
        is_used = bool(curr_clue.get("is_used", 0)) if curr_clue else False
        is_dd = bool(curr_clue.get("is_daily_double", 0)) if curr_clue else False
        self._apply_clue_button_style(curr_btn, is_used=is_used, is_selected=True, is_dd=is_dd)

        if not curr_clue:
            base_pts = (row + 1) * (200 if self.current_round == 1 else 400)
            curr_clue = {
                "id": None,
                "round_id": self.current_round,
                "col_index": col,
                "row_index": row,
                "category_name": self.cat_headers[col].text(),
                "points": base_pts,
                "question_text": f"(No question content for Col {col+1}, Row {row+1})",
                "answer_text": "(No answer)",
                "asset_filename": "",
                "is_daily_double": 0,
                "is_used": 0,
            }

        self.selected_clue = curr_clue
        self.selected_points = curr_clue["points"]
        self._dd_wager_locked = False
        self._update_dock_quick_point_buttons(self.selected_points)

        # Show inline DD wager panel immediately if this cell is a Daily Double
        if bool(curr_clue.get("is_daily_double")):
            self._refresh_dd_player_combo()
            self.dd_wager_frame.setVisible(True)
        else:
            self.dd_wager_frame.setVisible(False)

        asset_fn = curr_clue.get("asset_filename", "")
        asset_p = Path("ui/assets/image") / asset_fn if asset_fn else None
        has_asset = bool(asset_fn and asset_p.exists())
        asset_desc = f"<span style='color:#3fb950;'>Asset Available ({asset_fn})</span>" if has_asset else "<span style='color:#8b949e;'>Text Only</span>"
        dd_badge = "<span style='background-color:#da3633; color:white; padding:2px 6px; border-radius:3px; font-weight:bold;'>YES (DAILY DOUBLE!)</span>" if curr_clue["is_daily_double"] else "<span style='color:#8b949e;'>No</span>"

        html = f"""
        <div style="font-family: Arial, sans-serif;">
            <p style="margin: 0 0 6px 0; font-size: 14px;">
                <b>Category:</b> <span style="color: #58a6ff; font-weight: bold;">{curr_clue['category_name']}</span>
            </p>
            <p style="margin: 0 0 8px 0; font-size: 13px;">
                <b>Points:</b> <span style="color: #f59e0b; font-weight: bold;">${curr_clue['points']}</span> &nbsp;|&nbsp; 
                <b>Daily Double:</b> {dd_badge}
            </p>
            <div style="background-color: #0b1354; border-left: 4px solid #1f6feb; padding: 8px; border-radius: 4px; margin-bottom: 8px;">
                <b style="color: #58a6ff;">Clue:</b><br/>
                <span style="font-size: 14px; color: #ffffff;">{curr_clue['question_text']}</span>
            </div>
            <div style="background-color: #0e2a1b; border-left: 4px solid #238636; padding: 8px; border-radius: 4px; margin-bottom: 8px;">
                <b style="color: #3fb950;">Correct Answer (Host Only):</b><br/>
                <span style="font-size: 15px; font-weight: bold; color: #3fb950;">{curr_clue['answer_text']}</span>
            </div>
            <p style="margin: 2px 0 0 0; font-size: 12px;"><b>Visual Asset:</b> {asset_desc}</p>
        </div>
        """
        self.peek_text.setHtml(html)

    def _on_display_clue_clicked(self):
        if not self.selected_clue:
            QMessageBox.warning(self, "No Clue Selected", "Please select a point cell on the board first!")
            return

        payload = dict(self.selected_clue)
        asset_fn = payload.get("asset_filename", "")
        asset_path = Path("ui/assets/image") / asset_fn if asset_fn else None
        payload["has_asset"] = bool(asset_fn and asset_path and asset_path.exists())
        payload["asset_path"] = str(asset_path.resolve()) if payload["has_asset"] else ""

        # Emit single zoom request signal (preventing double-animation trigger)
        event_bus.request_clue_zoom.emit(payload)

        self.tv_answer_visible = False
        self.btn_toggle_answer.setText("TOGGLE TV ANSWER")
        self.btn_toggle_answer.setStyleSheet("background-color: #21262d; color: #8b949e; font-weight: bold; font-size: 13px; padding: 8px; border: 1px solid #30363d;")

        if payload.get("is_daily_double"):
            self._dd_wager_locked = False
            self._refresh_dd_player_combo()
            self.dd_wager_frame.setVisible(True)
            self.btn_clue_reveal.setEnabled(False)
            self.clue_status.setText("DAILY DOUBLE on TV! Enter contestant wager in the red box above to unlock & flip clue.")
            self.clue_status.setStyleSheet("color: #f43f5e; font-weight: bold;")
        else:
            self.dd_wager_frame.setVisible(False)
            self.btn_clue_reveal.setEnabled(True)
            self.clue_status.setText(f"Point tile on TV [{payload['category_name']} ${payload['points']}]. Click '2. Reveal Clue Text' to show clue card.")
            self.clue_status.setStyleSheet("color: #3fb950; font-weight: bold;")

    def _on_reveal_dd_clicked(self):
        """Requirement #8: Locks Daily Double wager from inline panel (updates dock scoring buttons)
        and triggers the 3D Flip -> Black Backing -> Clue Question transition on TV.
        """
        if not self.selected_clue:
            return

        p_id = self.dd_player_combo.currentData() or "p1"
        p_name = self.contestants[p_id]["name"]
        wager = self.dd_wager_spin.value()
        round_id = self.current_round

        is_valid, err_msg = self.s_engine.validate_dd_wager(p_id, wager, round_id)
        if not is_valid:
            QMessageBox.warning(self, "Invalid Daily Double Wager", err_msg)
            return

        self._pending_dd_wager = {"player_id": p_id, "wager": wager}
        self._dd_wager_locked = True
        self.selected_points = wager
        self._update_dock_quick_point_buttons(wager)
        self.btn_clue_reveal.setEnabled(True)
        self.clue_status.setText(f"DD Wager Locked: {p_name} wagered ${wager:,}. Flipping to Clue on TV...")
        self.clue_status.setStyleSheet("color: #f59e0b; font-weight: bold;")

        # Trigger 3D flip reveal on TV (DO NOT emit display_question simultaneously!)
        event_bus.trigger_clue_reveal.emit()

    def _on_clue_reveal_clicked(self):
        if not self.selected_clue:
            return

        # If Daily Double and wager hasn't been locked yet, lock the inline spinbox value automatically
        if self.selected_clue.get("is_daily_double") and not self._dd_wager_locked:
            self._on_reveal_dd_clicked()
            return

        # Emit ONLY trigger_clue_reveal (never emit display_question alongside it, which caused the flip background bug!)
        event_bus.trigger_clue_reveal.emit()
        self.dd_wager_frame.setVisible(False)
        self.clue_status.setText("Clue card active on TV!")
        self.clue_status.setStyleSheet("color: #3fb950; font-weight: bold;")

        self.buzzer_locked = True
        self.excluded_buzzers.clear()
        self.buzzer_active_player = None
        self._update_buzzer_lockout_ui()
        event_bus.set_buzzer_lockout.emit(True)

    def _on_toggle_tv_answer_clicked(self):
        if not self.selected_clue:
            return
        self.tv_answer_visible = not self.tv_answer_visible
        ans_text = self.selected_clue.get("answer_text", "")
        event_bus.toggle_tv_answer.emit(self.tv_answer_visible, ans_text)
        if self.tv_answer_visible:
            self.btn_toggle_answer.setText("HIDE TV ANSWER")
            self.btn_toggle_answer.setStyleSheet("background-color: #238636; color: white; font-weight: bold; font-size: 13px; padding: 8px; border: 1px solid #3fb950;")
        else:
            self.btn_toggle_answer.setText("TOGGLE TV ANSWER")
            self.btn_toggle_answer.setStyleSheet("background-color: #21262d; color: #8b949e; font-weight: bold; font-size: 13px; padding: 8px; border: 1px solid #30363d;")

    def _on_close_clue_clicked(self):
        if not self.selected_clue:
            return

        clue_id = self.selected_clue.get("id")
        col = self.selected_clue["col_index"]
        row = self.selected_clue["row_index"]

        if clue_id:
            try:
                self.q_engine.mark_as_used(self.current_round, col, row)
            except TypeError:
                self.q_engine.db.mark_clue_used(clue_id)

        self.selected_clue["is_used"] = 1
        if (col, row) in self.board_cache:
            self.board_cache[(col, row)]["is_used"] = 1

        btn = self.clue_buttons[(col, row)]
        self._apply_clue_button_style(btn, is_used=True, is_selected=False, is_dd=bool(self.selected_clue.get("is_daily_double")))

        # Check if all 5 clues in this column are now used -> visually mark column header on Host
        all_col_used = all(
            bool(self.board_cache.get((col, r), {}).get("is_used", 0))
            for r in range(5)
        )
        if all_col_used and 0 <= col < len(self.cat_headers):
            self.cat_headers[col].setStyleSheet("""
                background-color: #090d16;
                color: #484f58;
                font-weight: 800;
                font-size: 13px;
                border: 2px solid #21262d;
                border-radius: 0px;
                padding: 6px 2px;
                min-height: 44px;
            """)

        self.tv_answer_visible = False
        self.dd_wager_frame.setVisible(False)
        self.btn_clue_reveal.setEnabled(True)
        self.btn_toggle_answer.setText("TOGGLE TV ANSWER")
        self.btn_toggle_answer.setStyleSheet("background-color: #21262d; color: #8b949e; font-weight: bold; font-size: 13px; padding: 8px; border: 1px solid #30363d;")
        event_bus.toggle_tv_answer.emit(False, "")

        event_bus.close_question.emit()
        self.clue_status.setText("TV Status: Clue closed. Returned to board.")
        self.clue_status.setStyleSheet("color: #8b949e; font-style: italic;")

        self._reset_buzzers()

    # =========================================================================
    # TAB 3: FINAL JEOPARDY WITH REPLAY & DB/MANUAL OVERRIDE (REQ #10)
    # =========================================================================

    def _build_tab3_final(self):
        """Final Jeopardy Sequencer with Multi-Play Reset, DB Clue Selector & Manual Override."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        top_row = QHBoxLayout()
        header = QLabel("ROUND 3: FINAL JEOPARDY! SEQUENCER")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #58a6ff;")

        # Requirement #10: Replay / Reset Final Jeopardy & DB Clue Selector
        self.combo_final_db_clues = QComboBox()
        self.combo_final_db_clues.setMinimumWidth(260)
        self.combo_final_db_clues.setToolTip("Select any Round 3 / Final Jeopardy clue from SQLite database")
        self.combo_final_db_clues.currentIndexChanged.connect(self._on_final_db_clue_selected)

        self.btn_next_final_clue = QPushButton("🎲 Đổi Câu Khác Từ DB (Next DB Clue)")
        self.btn_next_final_clue.setStyleSheet("background-color: #1f6feb; color: white; font-weight: bold; padding: 6px 12px;")
        self.btn_next_final_clue.clicked.connect(self._on_cycle_next_final_db_clue)

        self.btn_reset_final_round = QPushButton("↻ Chơi Lại Vòng Cuối (Reset / Replay Final)")
        self.btn_reset_final_round.setStyleSheet("background-color: #d29922; color: #0d1117; font-weight: bold; padding: 6px 14px;")
        self.btn_reset_final_round.clicked.connect(lambda: self._reset_final_jeopardy_sequence(keep_clue=True))

        self.chk_manual_override = QCheckBox(" Enable Manual Override (Nhập thủ công / Mở khoá cược)")
        self.chk_manual_override.setStyleSheet("color: #f59e0b; font-weight: bold; font-size: 13px;")
        self.chk_manual_override.toggled.connect(self._on_manual_override_toggled)

        top_row.addWidget(header)
        top_row.addStretch()
        top_row.addWidget(QLabel("DB Clue:"))
        top_row.addWidget(self.combo_final_db_clues)
        top_row.addWidget(self.btn_next_final_clue)
        top_row.addWidget(self.btn_reset_final_round)
        top_row.addWidget(self.chk_manual_override)
        layout.addLayout(top_row)

        self.manual_frame = QFrame()
        self.manual_frame.setStyleSheet("background-color: #1c2128; border: 1px solid #f59e0b; border-radius: 6px; padding: 8px;")
        mf_layout = QFormLayout(self.manual_frame)
        self.edit_cat = QLineEdit()
        self.edit_cat.setPlaceholderText("Enter Final Category...")
        self.edit_clue = QLineEdit()
        self.edit_clue.setPlaceholderText("Enter Final Clue text...")
        self.edit_ans = QLineEdit()
        self.edit_ans.setPlaceholderText("Enter correct answer...")

        btn_apply_manual = QPushButton("Apply Manual Clue & Reset Final Sequence")
        btn_apply_manual.setStyleSheet("background-color: #238636; color: white; font-weight: bold; padding: 6px 14px;")
        btn_apply_manual.clicked.connect(self._on_apply_manual_final_clicked)

        mf_layout.addRow("Manual Category:", self.edit_cat)
        mf_layout.addRow("Manual Clue:", self.edit_clue)
        mf_layout.addRow("Manual Answer:", self.edit_ans)
        mf_layout.addRow("", btn_apply_manual)
        self.manual_frame.setVisible(False)
        layout.addWidget(self.manual_frame)

        # STEP 1: Final Logo Splash
        self.step1_box = QGroupBox("STEP 1: DISPLAY FINAL JEOPARDY LOGO SPLASH")
        self.step1_box.setMinimumHeight(85)
        s1_layout = QVBoxLayout(self.step1_box)
        self.btn_show_splash = QPushButton("[1. Show Final Splash Logo]")
        self.btn_show_splash.setStyleSheet("background-color: #8957e5; color: white; font-weight: bold; padding: 8px;")
        self.btn_show_splash.clicked.connect(self._on_show_splash)
        s1_layout.addWidget(self.btn_show_splash)
        layout.addWidget(self.step1_box)

        # STEP 2: Category & Wager Entry
        self.step2_box = QGroupBox("STEP 2: ANNOUNCE CATEGORY & ENTER WAGERS")
        self.step2_box.setMinimumHeight(230)
        s2_layout = QVBoxLayout(self.step2_box)

        cat_ctrl_row = QHBoxLayout()
        self.final_cat_lbl = QLabel("Final Category: Loading from database...")
        self.final_cat_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #f59e0b;")

        self.btn_show_category_tv = QPushButton("[Show Category on TV]")
        self.btn_show_category_tv.setStyleSheet("background-color: #1f6feb; color: white; font-weight: bold; padding: 6px 14px;")
        self.btn_show_category_tv.clicked.connect(self._on_show_category_tv)

        self.btn_return_splash_tv = QPushButton("[Return TV to Splash Logo]")
        self.btn_return_splash_tv.setStyleSheet("background-color: #30363d; color: #c9d1d9; font-weight: bold; padding: 6px 14px;")
        self.btn_return_splash_tv.clicked.connect(self._on_show_splash)

        cat_ctrl_row.addWidget(self.final_cat_lbl, 1)
        cat_ctrl_row.addWidget(self.btn_show_category_tv)
        cat_ctrl_row.addWidget(self.btn_return_splash_tv)
        s2_layout.addLayout(cat_ctrl_row)

        w_layout = QHBoxLayout()
        self.wager_spins = {}
        self.wager_notes = {}
        self.wager_name_labels = {}
        for p_id in ("p1", "p2", "p3"):
            box = QFrame()
            box.setMinimumHeight(135)
            box.setObjectName(f"wager_card_{p_id}")
            box.setStyleSheet(f"""
                QFrame#wager_card_{p_id} {{
                    background-color: #161b22;
                    border: 1px solid #30363d;
                    border-radius: 8px;
                    padding: 10px;
                }}
            """)
            b_lay = QVBoxLayout(box)
            b_lay.setSpacing(6)
            name_lbl = QLabel(self.contestants[p_id]["name"])
            name_lbl.setStyleSheet("font-size: 14px; font-weight: 800; color: #58a6ff;")
            self.wager_name_labels[p_id] = name_lbl

            note = QLabel("Score: $0 (Max Wager: $1000)")
            note.setStyleSheet("color: #c9d1d9; font-size: 12px; font-weight: bold;")
            self.wager_notes[p_id] = note

            spin = QSpinBox()
            spin.setRange(0, 1000)
            spin.setSingleStep(100)
            spin.setPrefix("$ ")
            spin.setStyleSheet("""
                QSpinBox {
                    background-color: #0d1117;
                    color: #ffffff;
                    border: 1px solid #30363d;
                    border-radius: 6px;
                    padding: 6px 10px;
                    font-size: 14px;
                    font-weight: bold;
                    min-height: 36px;
                }
                QSpinBox:focus {
                    border: 1px solid #58a6ff;
                }
            """)
            b_lay.addWidget(name_lbl)
            b_lay.addWidget(note)
            b_lay.addWidget(spin)
            w_layout.addWidget(box)
            self.wager_spins[p_id] = spin

        s2_layout.addLayout(w_layout)

        self.btn_lock_wagers = QPushButton("[Lock Wagers & Proceed to Clue]")
        self.btn_lock_wagers.setStyleSheet("""
            QPushButton {
                background-color: #238636;
                color: white;
                font-size: 13px;
                font-weight: bold;
                padding: 10px;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #2ea043; }
        """)
        self.btn_lock_wagers.clicked.connect(self._on_lock_wagers)
        s2_layout.addWidget(self.btn_lock_wagers)
        layout.addWidget(self.step2_box)

        # STEP 3: Reveal Clue & 30-Second Think Music
        self.step3_box = QGroupBox("STEP 3: REVEAL FINAL CLUE & 30-SECOND THINK MUSIC")
        self.step3_box.setMinimumHeight(180)
        self.step3_box.setEnabled(False)
        s3_layout = QVBoxLayout(self.step3_box)

        self.final_clue_preview = QTextEdit()
        self.final_clue_preview.setReadOnly(True)
        self.final_clue_preview.setMaximumHeight(85)
        s3_layout.addWidget(self.final_clue_preview)

        t_layout = QHBoxLayout()
        self.btn_start_30s = QPushButton("3. REVEAL CLUE & START 30S")
        self.btn_start_30s.setStyleSheet("background-color: #1f6feb; color: white; font-weight: bold; padding: 8px 16px;")
        self.btn_start_30s.clicked.connect(self._on_start_30s)

        self.btn_restart_final = QPushButton("RESTART 30S TIMER")
        self.btn_restart_final.setStyleSheet("""
            QPushButton {
                background-color: #0284c7; color: white; font-weight: bold; padding: 8px 16px; border-radius: 4px;
            }
            QPushButton:hover { background-color: #0369a1; }
            QPushButton:disabled { background-color: #21262d; color: #484f58; }
        """)
        self.btn_restart_final.setEnabled(False)
        self.btn_restart_final.clicked.connect(self._on_restart_30s)

        self.btn_stop_30s = QPushButton("EMERGENCY STOP")
        self.btn_stop_30s.setStyleSheet("""
            QPushButton {
                background-color: #da3633; color: white; font-weight: bold; padding: 8px 16px; border-radius: 4px;
            }
            QPushButton:hover { background-color: #f85149; }
            QPushButton:disabled { background-color: #21262d; color: #484f58; }
        """)
        self.btn_stop_30s.setEnabled(False)
        self.btn_stop_30s.clicked.connect(self._on_stop_30s_emergency)

        self.btn_toggle_final_answer = QPushButton("TOGGLE TV ANSWER")
        self.btn_toggle_final_answer.setStyleSheet("background-color: #21262d; color: #8b949e; font-weight: bold; padding: 8px 16px; border: 1px solid #30363d;")
        self.btn_toggle_final_answer.clicked.connect(self._on_toggle_final_answer_clicked)

        self.timer_bar = QProgressBar()
        self.timer_bar.setRange(0, 30)
        self.timer_bar.setValue(30)
        self.timer_bar.setFormat("30 seconds")

        t_layout.addWidget(self.btn_start_30s)
        t_layout.addWidget(self.btn_restart_final)
        t_layout.addWidget(self.btn_stop_30s)
        t_layout.addWidget(self.btn_toggle_final_answer)
        t_layout.addWidget(self.timer_bar, 1)
        s3_layout.addLayout(t_layout)
        layout.addWidget(self.step3_box)

        # STEP 4: Podium Reveal Sequence
        self.step4_box = QGroupBox("STEP 4: SONY PODIUM REVEAL SEQUENCE (3RD -> 2ND -> 1ST)")
        self.step4_box.setMinimumHeight(310)
        self.step4_box.setEnabled(False)
        s4_layout = QVBoxLayout(self.step4_box)

        self.reveal_cards_layout = QHBoxLayout()
        s4_layout.addLayout(self.reveal_cards_layout)

        self.btn_calc_final = QPushButton("DETERMINE CHAMPION")
        self.btn_calc_final.setStyleSheet("""
            QPushButton {
                background-color: #21262d; color: #8b949e; font-weight: bold; font-size: 14px;
                padding: 10px; border-radius: 6px; border: 1px solid #30363d;
            }
        """)
        self.btn_calc_final.setEnabled(False)
        self.btn_calc_final.clicked.connect(self._on_calc_final)
        s4_layout.addWidget(self.btn_calc_final)

        layout.addWidget(self.step4_box)
        layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll.setWidget(widget)
        return scroll

    def _refresh_final_wagers_ui(self):
        """Updates Final Jeopardy wagering UI.
        When Manual Override is active, unlocks wagering for all contestants (even if score <= 0)
        so Final Jeopardy can always be tested or re-played without being blocked!
        """
        override_on = hasattr(self, "chk_manual_override") and self.chk_manual_override.isChecked()
        eligible = self.s_engine.get_final_eligible_players() if hasattr(self, "s_engine") else ["p1", "p2", "p3"]

        for p_id in ("p1", "p2", "p3"):
            c_name = self.contestants[p_id]["name"]
            score = self.contestants[p_id]["score"]
            is_eligible = (p_id in eligible) or override_on

            if p_id in self.wager_name_labels:
                self.wager_name_labels[p_id].setText(c_name)
            if p_id in self.wager_notes:
                if is_eligible:
                    max_w = max(score, 10000 if override_on else 0)
                    tag = " [OVERRIDE UNLOCKED]" if (override_on and score <= 0) else ""
                    self.wager_notes[p_id].setText(f"Score: ${score:,} | Wager: $0 - ${max_w:,}{tag}")
                    self.wager_notes[p_id].setStyleSheet("color: #3fb950; font-size: 12px; font-weight: bold;" if override_on else "color: #c9d1d9; font-size: 12px; font-weight: bold;")
                else:
                    self.wager_notes[p_id].setText(
                        f"Score: ${score} — ELIMINATED (Tick 'Enable Manual Override' to unlock)"
                    )
                    self.wager_notes[p_id].setStyleSheet("color: #da3633; font-size: 12px; font-weight: bold;")
            if p_id in self.wager_spins:
                max_w = max(score, 10000 if override_on else 0)
                self.wager_spins[p_id].setRange(0, max_w)
                self.wager_spins[p_id].setEnabled(is_eligible)

    def _reset_final_jeopardy_sequence(self, keep_clue: bool = True):
        """Requirement #10: Resets and unlocks all steps of Final Jeopardy so it can be re-played
        as many times as desired (with a new DB clue or manual override clue).
        """
        self.final_timer.stop()
        self.audio_manager.stop_all()
        self.final_timer_seconds = 30
        self.is_final_answer_visible = False

        if hasattr(self, "timer_bar"):
            self.timer_bar.setValue(30)
            self.timer_bar.setFormat("30 seconds")

        if hasattr(self, "btn_lock_wagers"):
            self.btn_lock_wagers.setEnabled(True)
        if hasattr(self, "step2_box"):
            self.step2_box.setEnabled(True)
        if hasattr(self, "step3_box"):
            self.step3_box.setEnabled(False)
        if hasattr(self, "btn_start_30s"):
            self.btn_start_30s.setEnabled(True)
        if hasattr(self, "btn_restart_final"):
            self.btn_restart_final.setEnabled(False)
        if hasattr(self, "btn_stop_30s"):
            self.btn_stop_30s.setEnabled(False)
        if hasattr(self, "btn_toggle_final_answer"):
            self.btn_toggle_final_answer.setText("TOGGLE TV ANSWER")
            self.btn_toggle_final_answer.setStyleSheet("background-color: #21262d; color: #8b949e; font-weight: bold; padding: 8px 16px; border: 1px solid #30363d;")

        if hasattr(self, "step4_box"):
            self.step4_box.setEnabled(False)
        if hasattr(self, "btn_calc_final"):
            self.btn_calc_final.setEnabled(False)
            self.btn_calc_final.setStyleSheet("""
                QPushButton {
                    background-color: #21262d; color: #8b949e; font-weight: bold; font-size: 14px;
                    padding: 10px; border-radius: 6px; border: 1px solid #30363d;
                }
            """)

        if hasattr(self, "reveal_cards_layout"):
            while self.reveal_cards_layout.count():
                child = self.reveal_cards_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

        if not keep_clue:
            self._load_final_jeopardy_data()

        self._refresh_final_wagers_ui()
        event_bus.toggle_tv_answer.emit(False, "")
        cat_name = (
            self.edit_cat.text().strip()
            if (hasattr(self, "chk_manual_override") and self.chk_manual_override.isChecked())
            else (self.final_clue_data["category_name"] if self.final_clue_data else "FINAL JEOPARDY")
        )
        # CHÚ Ý: Không tự động emit trigger_final_step(1) khi reset sequence ở hậu trường.
        # Splash Final chỉ hiển thị lên TV khi MC chủ động nhấn nút [1. SHOW SPLASH] (_on_show_splash).

    def _on_manual_override_toggled(self, checked):
        self.manual_frame.setVisible(checked)
        if checked:
            cat = self.edit_cat.text().strip() or (self.final_clue_data["category_name"] if self.final_clue_data else "MANUAL FINAL CATEGORY")
            clue = self.edit_clue.text().strip() or (self.final_clue_data["question_text"] if self.final_clue_data else "")
            ans = self.edit_ans.text().strip() or (self.final_clue_data["answer_text"] if self.final_clue_data else "")
            if not self.edit_cat.text().strip():
                self.edit_cat.setText(cat)
            if not self.edit_clue.text().strip():
                self.edit_clue.setText(clue)
            if not self.edit_ans.text().strip():
                self.edit_ans.setText(ans)
            self._apply_manual_preview_text()
        else:
            self._apply_current_db_final_clue()
        self._reset_final_jeopardy_sequence(keep_clue=True)

    def _apply_manual_preview_text(self):
        cat = self.edit_cat.text().strip() or "MANUAL FINAL CATEGORY"
        clue = self.edit_clue.text().strip() or "(Enter Manual Clue Text above)"
        ans = self.edit_ans.text().strip() or "(Enter Manual Answer above)"
        self.final_cat_lbl.setText(f"Final Category (Manual Override): {cat.upper()}")
        html = f"<b>Clue (Manual):</b> <span style='color:#58a6ff;'>{clue}</span><br/><b>Host Answer:</b> <span style='color:#3fb950;'>{ans}</span>"
        self.final_clue_preview.setHtml(html)

    def _on_apply_manual_final_clicked(self):
        self._apply_manual_preview_text()
        self._reset_final_jeopardy_sequence(keep_clue=True)
        QMessageBox.information(self, "Manual Final Clue Applied", "Manual Final Jeopardy clue applied and sequence reset!")

    def _load_final_jeopardy_data(self):
        """Loads all available Round 3 & Round 4 (Tiebreaker) clues from SQLite DB so host can cycle/pick."""
        with self._get_db_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM questions WHERE round_id IN (3, 4) ORDER BY round_id ASC, id ASC")
            rows = [dict(r) for r in cursor.fetchall()]

        self.final_db_clues_list = rows
        if hasattr(self, "combo_final_db_clues"):
            self.combo_final_db_clues.blockSignals(True)
            self.combo_final_db_clues.clear()
            for idx, r in enumerate(rows):
                r_tag = "R3" if r["round_id"] == 3 else "TB"
                self.combo_final_db_clues.addItem(f"[{r_tag} #{r['id']}] {r['category_name']}", idx)
            self.combo_final_db_clues.blockSignals(False)

        if rows:
            self.final_db_clue_index = min(self.final_db_clue_index, len(rows) - 1)
            if hasattr(self, "combo_final_db_clues"):
                self.combo_final_db_clues.blockSignals(True)
                self.combo_final_db_clues.setCurrentIndex(self.final_db_clue_index)
                self.combo_final_db_clues.blockSignals(False)
            self._apply_current_db_final_clue()
        else:
            self.final_clue_data = None
            self.final_cat_lbl.setText("Final Category: (No Round 3 Clue Configured)")
            self.final_clue_preview.setText("Please add Round 3 clue in Tab 4 or check Manual Override.")

    def _apply_current_db_final_clue(self):
        if not self.final_db_clues_list:
            return
        self.final_db_clue_index = max(0, min(self.final_db_clue_index, len(self.final_db_clues_list) - 1))
        self.final_clue_data = dict(self.final_db_clues_list[self.final_db_clue_index])
        self.final_cat_lbl.setText(f"Final Category: {self.final_clue_data['category_name'].upper()}")
        html = (
            f"<b>Clue:</b> <span style='color:#58a6ff;'>{self.final_clue_data['question_text']}</span><br/>"
            f"<b>Host Answer:</b> <span style='color:#3fb950;'>{self.final_clue_data['answer_text']}</span>"
        )
        self.final_clue_preview.setHtml(html)

    def _on_final_db_clue_selected(self, combo_idx: int):
        if combo_idx < 0 or combo_idx >= len(self.final_db_clues_list):
            return
        self.final_db_clue_index = combo_idx
        if hasattr(self, "chk_manual_override") and self.chk_manual_override.isChecked():
            self.chk_manual_override.setChecked(False)
        self._apply_current_db_final_clue()
        self._reset_final_jeopardy_sequence(keep_clue=True)

    def _on_cycle_next_final_db_clue(self):
        """Cycles to the next Final Jeopardy clue in SQLite DB and resets sequence."""
        if not self.final_db_clues_list:
            self._load_final_jeopardy_data()
        if not self.final_db_clues_list:
            QMessageBox.warning(self, "No Final Clues", "No Round 3 clues found in database. Use Manual Override or add one in Tab 4.")
            return
        self.final_db_clue_index = (self.final_db_clue_index + 1) % len(self.final_db_clues_list)
        if hasattr(self, "combo_final_db_clues"):
            self.combo_final_db_clues.blockSignals(True)
            self.combo_final_db_clues.setCurrentIndex(self.final_db_clue_index)
            self.combo_final_db_clues.blockSignals(False)
        if hasattr(self, "chk_manual_override") and self.chk_manual_override.isChecked():
            self.chk_manual_override.setChecked(False)
        self._apply_current_db_final_clue()
        self._reset_final_jeopardy_sequence(keep_clue=True)

    def _on_show_splash(self):
        cat_name = self.edit_cat.text().strip() if self.chk_manual_override.isChecked() else (self.final_clue_data['category_name'] if self.final_clue_data else "FINAL JEOPARDY")
        event_bus.trigger_final_step.emit(1, {"category": cat_name})
        self.step2_box.setEnabled(True)
        self._refresh_final_wagers_ui()

    def _on_show_category_tv(self):
        cat_name = self.edit_cat.text().strip() if self.chk_manual_override.isChecked() else (self.final_clue_data['category_name'] if self.final_clue_data else "FINAL JEOPARDY")
        # Requirement #7: trigger_final_step(2) plays "final_category_intro" on TV; wager_music removed!
        event_bus.trigger_final_step.emit(2, {"category": cat_name})

    def _on_lock_wagers(self):
        for p_id in ("p1", "p2", "p3"):
            self.final_wagers[p_id] = self.wager_spins[p_id].value()
            self.wager_spins[p_id].setEnabled(False)

        cat_name = self.edit_cat.text().strip() if self.chk_manual_override.isChecked() else (self.final_clue_data['category_name'] if self.final_clue_data else "FINAL JEOPARDY")
        event_bus.submit_final_wagers.emit(self.final_wagers)
        event_bus.trigger_final_step.emit(2, {"category": cat_name, "wagers": self.final_wagers})

        self.btn_lock_wagers.setEnabled(False)
        self.step3_box.setEnabled(True)
        self.btn_start_30s.setEnabled(True)

    def _on_start_30s(self):
        self.btn_start_30s.setEnabled(False)
        self.btn_restart_final.setEnabled(True)
        self.btn_stop_30s.setEnabled(True)
        self.final_timer_seconds = 30
        self.timer_bar.setValue(30)
        self.timer_bar.setFormat("30 seconds")

        if self.chk_manual_override.isChecked():
            clue_text = self.edit_clue.text().strip() or "Manual Final Jeopardy Clue"
            ans_text = self.edit_ans.text().strip() or "Manual Answer"
            clue_data = {
                "round_id": 3,
                "category_name": self.edit_cat.text().strip() or "FINAL JEOPARDY",
                "question_text": clue_text,
                "answer_text": ans_text,
                "has_asset": False,
                "asset_path": ""
            }
        else:
            clue_data = dict(self.final_clue_data) if self.final_clue_data else {"question_text": "Final Jeopardy Clue", "has_asset": False}

        event_bus.trigger_final_step.emit(3, clue_data)
        # Requirement #7: Emit "think_30s" matching Settings key
        event_bus.play_sound_event.emit("think_30s")
        self.final_timer.start(1000)

    def _on_restart_30s(self):
        self.final_timer_seconds = 30
        self.timer_bar.setValue(30)
        self.timer_bar.setFormat("30 seconds")
        self.btn_stop_30s.setEnabled(True)
        self.btn_restart_final.setEnabled(True)
        self.final_timer.stop()
        self.final_timer.start(1000)
        event_bus.restart_final_timer.emit()

    def _on_stop_30s_emergency(self):
        self.final_timer.stop()
        self.audio_manager.stop_music()
        self.timer_bar.setFormat("EMERGENCY STOPPED")
        self.btn_stop_30s.setEnabled(False)
        self.btn_restart_final.setEnabled(True)
        self.step4_box.setEnabled(True)
        self._setup_final_reveal_order()

    def _on_toggle_final_answer_clicked(self):
        self.is_final_answer_visible = not self.is_final_answer_visible
        if self.chk_manual_override.isChecked():
            ans = self.edit_ans.text().strip()
        else:
            ans = self.final_clue_data.get("answer_text", "") if self.final_clue_data else ""

        event_bus.toggle_tv_answer.emit(self.is_final_answer_visible, ans)
        if self.is_final_answer_visible:
            self.btn_toggle_final_answer.setText("HIDE TV ANSWER")
            self.btn_toggle_final_answer.setStyleSheet("background-color: #238636; color: white; font-weight: bold; padding: 8px 16px; border: 1px solid #3fb950;")
        else:
            self.btn_toggle_final_answer.setText("TOGGLE TV ANSWER")
            self.btn_toggle_final_answer.setStyleSheet("background-color: #21262d; color: #8b949e; font-weight: bold; padding: 8px 16px; border: 1px solid #30363d;")

    def _on_final_timer_tick(self):
        self.final_timer_seconds -= 1
        self.timer_bar.setValue(self.final_timer_seconds)
        self.timer_bar.setFormat(f"{self.final_timer_seconds} seconds")

        if self.final_timer_seconds == 15:
            event_bus.start_final_crossfade.emit()

        if self.final_timer_seconds <= 0:
            self.final_timer.stop()
            self.timer_bar.setFormat("TIME OUT! PENS DOWN!")
            self.btn_stop_30s.setEnabled(False)
            self.step4_box.setEnabled(True)
            self._setup_final_reveal_order()

    def _setup_final_reveal_order(self):
        while self.reveal_cards_layout.count():
            child = self.reveal_cards_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        ranked = sorted(
            [("p1", self.contestants["p1"]["score"]),
             ("p2", self.contestants["p2"]["score"]),
             ("p3", self.contestants["p3"]["score"])],
            key=lambda x: x[1]
        )
        self.final_reveal_order = [p[0] for p in ranked]
        self.final_reveal_state = {}
        self.reveal_widgets = {}

        rank_labels = ["3RD PLACE (STEP 1)", "2ND PLACE (STEP 2)", "1ST PLACE (STEP 3 - LEADER)"]

        for idx, p_id in enumerate(self.final_reveal_order):
            self.final_reveal_state[p_id] = 0
            box = QFrame()
            box.setMinimumHeight(210)
            box.setObjectName(f"reveal_card_{p_id}")
            box.setStyleSheet(f"""
                QFrame#reveal_card_{p_id} {{
                    background-color: #161b22;
                    border: 2px solid {'#388bfd' if idx == 0 else '#30363d'};
                    border-radius: 8px;
                    padding: 10px;
                }}
            """)
            b_lay = QVBoxLayout(box)
            b_lay.setSpacing(6)

            tag_lbl = QLabel(rank_labels[idx])
            tag_lbl.setStyleSheet("font-size: 11px; font-weight: 900; color: #f59e0b;")
            p_name = self.contestants[p_id]["name"]
            p_score = self.contestants[p_id]["score"]
            p_wager = self.final_wagers.get(p_id, 0)

            name_lbl = QLabel(f"{p_name} (${p_score})")
            name_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #58a6ff;")

            wager_lbl = QLabel(f"Wager: ${p_wager}")
            wager_lbl.setStyleSheet("font-size: 12px; color: #c9d1d9;")

            resp_edit = QLineEdit()
            resp_edit.setPlaceholderText("Contestant written response...")
            resp_edit.setStyleSheet("background-color: #0d1117; color: white; border: 1px solid #30363d; padding: 6px; border-radius: 4px;")

            chk = QCheckBox(" Response CORRECT")
            chk.setChecked(True)
            chk.setStyleSheet("color: #3fb950; font-weight: bold;")

            btn_step = QPushButton("1. Reveal Response" if idx == 0 else "Waiting...")
            btn_step.setEnabled(idx == 0)
            btn_step.setStyleSheet("""
                QPushButton { background-color: #1f6feb; color: white; font-weight: bold; padding: 6px; border-radius: 4px; }
                QPushButton:disabled { background-color: #21262d; color: #484f58; }
            """)
            btn_step.clicked.connect(lambda chk=False, pid=p_id: self._on_reveal_contestant_step(pid))

            b_lay.addWidget(tag_lbl)
            b_lay.addWidget(name_lbl)
            b_lay.addWidget(wager_lbl)
            b_lay.addWidget(resp_edit)
            b_lay.addWidget(chk)
            b_lay.addWidget(btn_step)

            self.reveal_cards_layout.addWidget(box)
            self.reveal_widgets[p_id] = {
                "frame": box,
                "resp_edit": resp_edit,
                "chk": chk,
                "btn_step": btn_step,
                "wager_lbl": wager_lbl,
                "name_lbl": name_lbl,
                "wager": p_wager,
            }

    def _on_reveal_contestant_step(self, pid):
        st = self.final_reveal_state.get(pid, 0)
        w = self.reveal_widgets[pid]
        resp_text = w["resp_edit"].text().strip() or "(No response)"
        wager = w["wager"]
        is_correct = w["chk"].isChecked()

        if st == 0:
            self.final_reveal_state[pid] = 1
            event_bus.trigger_final_contestant_reveal.emit(pid, resp_text, 0)
            w["btn_step"].setText(f"2. Reveal Wager (${wager}) & Resolve")
            w["btn_step"].setStyleSheet("background-color: #238636; color: white; font-weight: bold; padding: 6px; border-radius: 4px;")
        elif st == 1:
            self.final_reveal_state[pid] = 2
            if is_correct:
                self.s_engine.add_correct(pid, wager)
                event_bus.play_sound_event.emit("correct")
            else:
                self.s_engine.add_incorrect(pid, wager)
                event_bus.play_sound_event.emit("wrong")

            new_score = self.s_engine.get_score(pid)
            self.contestants[pid]["score"] = new_score
            scores = self.s_engine.get_all_scores()
            event_bus.score_updated.emit(scores)
            self._update_live_score_display()

            event_bus.trigger_final_contestant_reveal.emit(pid, resp_text, wager)
            w["name_lbl"].setText(f"{self.contestants[pid]['name']} (${new_score})")
            w["btn_step"].setText("Resolved")
            w["btn_step"].setEnabled(False)
            w["btn_step"].setStyleSheet("background-color: #21262d; color: #8b949e; font-weight: bold; padding: 6px; border-radius: 4px;")

            curr_idx = self.final_reveal_order.index(pid)
            if curr_idx + 1 < len(self.final_reveal_order):
                next_pid = self.final_reveal_order[curr_idx + 1]
                next_w = self.reveal_widgets[next_pid]
                next_w["btn_step"].setText("1. Reveal Response")
                next_w["btn_step"].setEnabled(True)
                next_w["frame"].setStyleSheet(f"QFrame#reveal_card_{next_pid} {{ background-color: #161b22; border: 2px solid #388bfd; border-radius: 8px; padding: 10px; }}")
            else:
                self.btn_calc_final.setEnabled(True)
                self.btn_calc_final.setStyleSheet("""
                    QPushButton {
                        background-color: #8957e5; color: white; font-weight: bold; font-size: 14px;
                        padding: 10px; border-radius: 6px; border: 1px solid #a371f7;
                    }
                    QPushButton:hover { background-color: #a371f7; }
                """)

    def _on_calc_final(self):
        final_totals = {pid: self.contestants[pid]["score"] for pid in ("p1", "p2", "p3")}
        event_bus.score_updated.emit(final_totals)
        self._update_live_score_display()

        ranked = sorted(final_totals.items(), key=lambda x: x[1], reverse=True)
        w_id, w_score = ranked[0]
        s_id, s_score = ranked[1]
        t_id, t_score = ranked[2]

        results = {
            "first": {"id": w_id, "name": self.contestants[w_id]["name"], "score": w_score, "prize": f"${w_score}"},
            "second": {"id": s_id, "name": self.contestants[s_id]["name"], "score": s_score, "prize": "$3,000"},
            "third": {"id": t_id, "name": self.contestants[t_id]["name"], "score": t_score, "prize": "$2,000"},
        }
        event_bus.winner_announced.emit(results)

        QMessageBox.information(
            self,
            "Tournament Champion! (Host Controller Only)",
            f"Champion: {self.contestants[w_id]['name']} (${w_score})\n"
            f"1st Runner-up: {self.contestants[s_id]['name']} (${s_score}) - $3,000\n"
            f"2nd Runner-up: {self.contestants[t_id]['name']} (${t_score}) - $2,000\n\n"
            "(Tip: Click '↻ Chơi Lại Vòng Cuối' or '🎲 Đổi Câu Khác Từ DB' at the top of Tab 3 to replay Final Jeopardy!)"
        )

    # =========================================================================
    # TAB 4: DATABASE MANAGER
    # =========================================================================

    def _build_tab4_database(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        top = QHBoxLayout()
        lbl = QLabel("Filter by Round:")
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All Rounds", "Round 1 (Jeopardy)", "Round 2 (Double Jeopardy)", "Round 3 (Final Jeopardy)"])
        self.filter_combo.currentIndexChanged.connect(self._refresh_database_table)

        btn_add = QPushButton("+ Add Clue Row")
        btn_add.clicked.connect(self._on_add_db_row)

        btn_del = QPushButton("- Delete Selected Row")
        btn_del.clicked.connect(self._on_delete_db_row)

        btn_reset = QPushButton("Reset Used Flags (is_used=0)")
        btn_reset.clicked.connect(self._on_reset_used_flags)

        top.addWidget(lbl)
        top.addWidget(self.filter_combo)
        top.addSpacing(16)
        top.addWidget(btn_add)
        top.addWidget(btn_del)
        top.addWidget(btn_reset)
        top.addStretch()
        layout.addLayout(top)

        self.db_table = QTableWidget()
        self.db_cols = ["ID", "Round", "Col", "Row", "Category", "Points", "Question", "Answer", "Asset File", "Daily Double", "Is Used"]
        self.db_table.setColumnCount(len(self.db_cols))
        self.db_table.setHorizontalHeaderLabels(self.db_cols)
        self.db_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.db_table.horizontalHeader().setStretchLastSection(True)
        self.db_table.setAlternatingRowColors(True)
        layout.addWidget(self.db_table)

        bot = QHBoxLayout()
        self.btn_save_db = QPushButton("[Save All Changes to Database]")
        self.btn_save_db.setStyleSheet("background-color: #238636; color: white; font-weight: bold; padding: 9px 20px;")
        self.btn_save_db.clicked.connect(self._on_save_db)

        self.db_status = QLabel("Ready.")
        self.db_status.setStyleSheet("color: #8b949e;")

        bot.addWidget(self.btn_save_db)
        bot.addWidget(self.db_status)
        bot.addStretch()
        layout.addLayout(bot)

        return widget

    def _get_db_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _refresh_database_table(self):
        f_idx = self.filter_combo.currentIndex()
        q = "SELECT * FROM questions"
        if f_idx == 1:
            q += " WHERE round_id = 1"
        elif f_idx == 2:
            q += " WHERE round_id = 2"
        elif f_idx == 3:
            q += " WHERE round_id = 3"
        q += " ORDER BY round_id, col_index, row_index"

        with self._get_db_conn() as conn:
            rows = conn.cursor().execute(q).fetchall()

        self.db_table.setRowCount(0)
        for r_idx, r in enumerate(rows):
            self.db_table.insertRow(r_idx)
            id_item = QTableWidgetItem(str(r["id"]))
            id_item.setFlags(id_item.flags() ^ Qt.ItemIsEditable)
            self.db_table.setItem(r_idx, 0, id_item)
            self.db_table.setItem(r_idx, 1, QTableWidgetItem(str(r["round_id"])))
            self.db_table.setItem(r_idx, 2, QTableWidgetItem(str(r["col_index"])))
            self.db_table.setItem(r_idx, 3, QTableWidgetItem(str(r["row_index"])))
            self.db_table.setItem(r_idx, 4, QTableWidgetItem(str(r["category_name"])))
            self.db_table.setItem(r_idx, 5, QTableWidgetItem(str(r["points"])))
            self.db_table.setItem(r_idx, 6, QTableWidgetItem(str(r["question_text"])))
            self.db_table.setItem(r_idx, 7, QTableWidgetItem(str(r["answer_text"])))
            self.db_table.setItem(r_idx, 8, QTableWidgetItem(str(r["asset_filename"] or "")))

            dd_item = QTableWidgetItem()
            dd_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            dd_item.setCheckState(Qt.Checked if r["is_daily_double"] else Qt.Unchecked)
            self.db_table.setItem(r_idx, 9, dd_item)

            used_item = QTableWidgetItem()
            used_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            used_item.setCheckState(Qt.Checked if r["is_used"] else Qt.Unchecked)
            self.db_table.setItem(r_idx, 10, used_item)

        self.db_table.resizeColumnsToContents()
        self.db_status.setText(f"Loaded {len(rows)} questions.")

    def _on_add_db_row(self):
        r = self.db_table.rowCount()
        self.db_table.insertRow(r)
        id_item = QTableWidgetItem("NEW")
        id_item.setFlags(id_item.flags() ^ Qt.ItemIsEditable)
        self.db_table.setItem(r, 0, id_item)
        self.db_table.setItem(r, 1, QTableWidgetItem("1"))
        self.db_table.setItem(r, 2, QTableWidgetItem("0"))
        self.db_table.setItem(r, 3, QTableWidgetItem("0"))
        self.db_table.setItem(r, 4, QTableWidgetItem("New Category"))
        self.db_table.setItem(r, 5, QTableWidgetItem("200"))
        self.db_table.setItem(r, 6, QTableWidgetItem("Clue text?"))
        self.db_table.setItem(r, 7, QTableWidgetItem("Correct answer"))
        self.db_table.setItem(r, 8, QTableWidgetItem(""))

        dd = QTableWidgetItem()
        dd.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        dd.setCheckState(Qt.Unchecked)
        self.db_table.setItem(r, 9, dd)

        used = QTableWidgetItem()
        used.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        used.setCheckState(Qt.Unchecked)
        self.db_table.setItem(r, 10, used)

    def _on_delete_db_row(self):
        cur = self.db_table.currentRow()
        if cur < 0:
            return
        id_text = self.db_table.item(cur, 0).text()
        if id_text != "NEW":
            with self._get_db_conn() as conn:
                conn.cursor().execute("DELETE FROM clues WHERE id = ?", (int(id_text),))
                conn.commit()
        self.db_table.removeRow(cur)
        self.db_status.setText("Row deleted.")

    def _on_reset_used_flags(self):
        with self._get_db_conn() as conn:
            conn.cursor().execute("UPDATE clues SET is_used = 0")
            conn.commit()
        self._refresh_database_table()
        self._load_board_for_round(self.current_round)
        QMessageBox.information(self, "Reset Complete", "All questions reset to UNUSED (is_used = 0).")

    def _on_save_db(self):
        try:
            with self._get_db_conn() as conn:
                cursor = conn.cursor()
                for r in range(self.db_table.rowCount()):
                    id_text = self.db_table.item(r, 0).text()
                    round_id = int(self.db_table.item(r, 1).text() or 1)
                    col_idx = int(self.db_table.item(r, 2).text() or 0)
                    row_idx = int(self.db_table.item(r, 3).text() or 0)
                    cat_name = self.db_table.item(r, 4).text().strip() or "Category"
                    points = int(self.db_table.item(r, 5).text() or 0)
                    q_text = self.db_table.item(r, 6).text()
                    ans_text = self.db_table.item(r, 7).text()
                    asset = self.db_table.item(r, 8).text()
                    is_dd = 1 if self.db_table.item(r, 9).checkState() == Qt.Checked else 0
                    is_used = 1 if self.db_table.item(r, 10).checkState() == Qt.Checked else 0

                    # Resolve or create category_id in underlying categories table
                    cursor.execute(
                        "SELECT id FROM categories WHERE name = ? AND round_id = ? LIMIT 1",
                        (cat_name, round_id),
                    )
                    cat_row = cursor.fetchone()
                    if cat_row:
                        cat_id = cat_row["id"]
                    else:
                        cursor.execute(
                            "INSERT INTO categories (name, round_id, description, is_active) VALUES (?, ?, '', 1)",
                            (cat_name, round_id),
                        )
                        cat_id = cursor.lastrowid

                    if id_text == "NEW":
                        cursor.execute("""
                        INSERT INTO clues (category_id, round_id, col_index, row_index, points, clue_text, answer_text, asset_filename, is_daily_double, is_used, is_ongame)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                        """, (cat_id, round_id, col_idx, row_idx, points, q_text, ans_text, asset, is_dd, is_used))
                    else:
                        cursor.execute("""
                        UPDATE clues SET category_id=?, round_id=?, col_index=?, row_index=?, points=?, clue_text=?, answer_text=?, asset_filename=?, is_daily_double=?, is_used=?
                        WHERE id = ?
                        """, (cat_id, round_id, col_idx, row_idx, points, q_text, ans_text, asset, is_dd, is_used, int(id_text)))
                conn.commit()

            self._refresh_database_table()
            self._load_board_for_round(self.current_round)
            self._load_final_jeopardy_data()
            QMessageBox.information(self, "Success", "SQLite database synchronized successfully!")
        except Exception as ex:
            QMessageBox.critical(self, "Database Error", str(ex))

    # =========================================================================
    # BOTTOM DOCK: LIVE SCORING & BUZZER CONTROLS
    # =========================================================================

    def _build_bottom_dock(self):
        self.score_dock = QDockWidget("LIVE SCORING CONSOLE", self)
        self.score_dock.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)

        dock_widget = QWidget()
        dock_layout = QVBoxLayout(dock_widget)
        dock_layout.setContentsMargins(12, 6, 12, 8)
        dock_layout.setSpacing(6)

        dock_header = QHBoxLayout()
        dock_title_lbl = QLabel("LIVE SCORING CONTROLS")
        dock_title_lbl.setStyleSheet("font-size: 12px; font-weight: bold; color: #8b949e;")

        self.btn_dock_toggle = QPushButton("[-] Collapse")
        self.btn_dock_toggle.setStyleSheet("""
            QPushButton {
                background-color: #21262d; color: #c9d1d9; font-weight: bold;
                font-size: 11px; padding: 4px 12px; border: 1px solid #30363d; border-radius: 4px;
            }
            QPushButton:hover { background-color: #30363d; color: #ffffff; }
        """)
        self.btn_dock_toggle.clicked.connect(self._toggle_dock_collapse)

        dock_header.addWidget(dock_title_lbl)
        dock_header.addStretch()
        dock_header.addWidget(self.btn_dock_toggle)
        dock_layout.addLayout(dock_header)

        # 1. COMPACT BAR WIDGET
        self.dock_compact_widget = QWidget()
        compact_layout = QHBoxLayout(self.dock_compact_widget)
        compact_layout.setContentsMargins(4, 2, 4, 2)
        compact_layout.setSpacing(16)

        self.compact_score_labels = {}
        for pid in ("p1", "p2", "p3"):
            lbl = QLabel(f"{self.contestants[pid]['name']}: $0")
            lbl.setStyleSheet("font-size: 13px; font-weight: 800; color: #3fb950; background: #0d1117; padding: 4px 12px; border-radius: 4px; border: 1px solid #21262d;")
            self.compact_score_labels[pid] = lbl
            compact_layout.addWidget(lbl)

        compact_layout.addStretch()
        self.dock_compact_widget.setVisible(False)
        dock_layout.addWidget(self.dock_compact_widget)

        # 2. DETAILED WIDGET
        self.dock_detailed_widget = QWidget()
        detailed_layout = QVBoxLayout(self.dock_detailed_widget)
        detailed_layout.setContentsMargins(0, 0, 0, 0)
        detailed_layout.setSpacing(6)

        cards = QHBoxLayout()
        cards.setSpacing(14)
        self.score_cards = {}

        for p_id in ("p1", "p2", "p3"):
            card = QFrame()
            card.setStyleSheet("background-color: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 8px;")
            c_lay = QVBoxLayout(card)
            c_lay.setSpacing(6)

            top_p = QHBoxLayout()
            name_lbl = QLabel(self.contestants[p_id]["name"])
            name_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #58a6ff;")
            top_p.addWidget(name_lbl)
            top_p.addStretch()

            score_lbl = QLabel("$ 0")
            score_lbl.setStyleSheet("font-size: 26px; font-weight: 900; color: #3fb950; background-color: #0d1117; border: 1px solid #21262d; border-radius: 6px; padding: 4px;")
            score_lbl.setAlignment(Qt.AlignCenter)

            r1 = QHBoxLayout()
            btn_add = QPushButton("+$200")
            btn_add.setStyleSheet("background-color: #238636; color: white; font-weight: bold; padding: 5px;")
            btn_add.clicked.connect(lambda chk=False, pid=p_id: self._adjust_score(pid, self.selected_points, True))

            btn_sub = QPushButton("-$200")
            btn_sub.setStyleSheet("background-color: #da3633; color: white; font-weight: bold; padding: 5px;")
            btn_sub.clicked.connect(lambda chk=False, pid=p_id: self._adjust_score(pid, self.selected_points, False))

            r1.addWidget(btn_add)
            r1.addWidget(btn_sub)

            r2 = QHBoxLayout()
            spin = QSpinBox()
            spin.setRange(0, 50000)
            spin.setValue(100)
            spin.setSingleStep(100)

            btn_c_add = QPushButton("+ Correct")
            btn_c_add.setStyleSheet("background-color: #238636; color: white; font-weight: bold; padding: 5px;")
            btn_c_add.clicked.connect(lambda chk=False, pid=p_id, s=spin: self._adjust_score(pid, s.value(), True))

            btn_c_sub = QPushButton("- Wrong")
            btn_c_sub.setStyleSheet("background-color: #da3633; color: white; font-weight: bold; padding: 5px;")
            btn_c_sub.clicked.connect(lambda chk=False, pid=p_id, s=spin: self._adjust_score(pid, s.value(), False))

            r2.addWidget(spin, 1)
            r2.addWidget(btn_c_add)
            r2.addWidget(btn_c_sub)

            c_lay.addLayout(top_p)
            c_lay.addWidget(score_lbl)
            c_lay.addLayout(r1)
            c_lay.addLayout(r2)

            self.score_cards[p_id] = {
                "card_frame": card,
                "name_lbl": name_lbl,
                "score_lbl": score_lbl,
                "btn_add": btn_add,
                "btn_sub": btn_sub,
                "spin": spin,
            }
            cards.addWidget(card)

        detailed_layout.addLayout(cards)

        bot = QHBoxLayout()
        btn_undo = QPushButton("[Undo Last Score Action]")
        btn_undo.setStyleSheet("background-color: #d29922; color: #0d1117; font-weight: bold; padding: 6px 16px;")
        btn_undo.clicked.connect(self._on_undo_score)

        bot.addWidget(btn_undo)
        bot.addStretch()
        detailed_layout.addLayout(bot)

        dock_layout.addWidget(self.dock_detailed_widget)

        self.score_dock.setWidget(dock_widget)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.score_dock)
        self.resizeDocks([self.score_dock], [260], Qt.Vertical)

    def _toggle_dock_collapse(self):
        self.is_dock_collapsed = not getattr(self, "is_dock_collapsed", False)
        if self.is_dock_collapsed:
            self.dock_detailed_widget.setVisible(False)
            self.dock_compact_widget.setVisible(True)
            self.btn_dock_toggle.setText("[+] Expand")
        else:
            self.dock_compact_widget.setVisible(False)
            self.dock_detailed_widget.setVisible(True)
            self.btn_dock_toggle.setText("[-] Collapse")

    def _update_buzzer_lockout_ui(self):
        pass

    def _adjust_score(self, player_id, points, is_correct):
        if points <= 0:
            return
        if is_correct:
            self.s_engine.add_correct(player_id, points)
            event_bus.play_sound_event.emit("correct")
        else:
            self.s_engine.add_incorrect(player_id, points)
            event_bus.play_sound_event.emit("wrong")

        scores = self.s_engine.get_all_scores()
        for pid in ("p1", "p2", "p3"):
            self.contestants[pid]["score"] = scores.get(pid, 0)
        event_bus.modify_score.emit(player_id, points, is_correct)
        event_bus.score_updated.emit(scores)
        self._update_live_score_display()
        self._refresh_dd_player_combo()

    def _on_buzzer_pressed(self, player_id):
        if self.buzzer_locked or player_id in self.excluded_buzzers:
            return
        self.buzzer_locked = True
        self.buzzer_active_player = player_id

        self._update_buzzer_lockout_ui()
        event_bus.set_buzzer_lockout.emit(True)
        event_bus.trigger_buzzer_press.emit(player_id)
        self._start_host_timer_5s()

    def _reset_buzzers(self):
        self.buzzer_locked = True
        self.buzzer_active_player = None
        self.excluded_buzzers.clear()
        self._update_buzzer_lockout_ui()
        self._stop_host_timer_5s()
        event_bus.set_buzzer_lockout.emit(True)
        event_bus.trigger_buzzer_reset.emit()

    def _start_host_timer_5s(self):
        self.host_timer_remaining_ms = 5000
        self._update_host_timer_display()
        self.host_timer_5s.start()
        event_bus.trigger_host_timer_5s.emit("start")

    def _stop_host_timer_5s(self):
        self.host_timer_5s.stop()
        event_bus.trigger_host_timer_5s.emit("stop")

    def _reset_host_timer_5s(self):
        self.host_timer_5s.stop()
        self.host_timer_remaining_ms = 5000
        self._update_host_timer_display()
        event_bus.trigger_host_timer_5s.emit("reset")

    def _on_host_timer_5s_tick(self):
        self.host_timer_remaining_ms = max(0, self.host_timer_remaining_ms - 100)
        self._update_host_timer_display()
        if self.host_timer_remaining_ms <= 0:
            self.host_timer_5s.stop()
            event_bus.play_sound_event.emit("timeout")
            self.host_timer_lbl.setText("00.0s - TIME OUT!")
            self.host_timer_lbl.setStyleSheet("font-size: 20px; font-weight: 900; color: #f85149; font-family: monospace;")

    def _update_host_timer_display(self):
        secs = self.host_timer_remaining_ms / 1000.0
        self.host_timer_lbl.setText(f"{secs:04.1f}s")
        self.host_timer_bar.setValue(self.host_timer_remaining_ms)
        if secs > 3.0:
            color = "#3fb950"
        elif secs > 1.5:
            color = "#f59e0b"
        else:
            color = "#f85149"
        self.host_timer_lbl.setStyleSheet(f"font-size: 22px; font-weight: 900; color: {color}; font-family: monospace;")

    def _on_undo_score(self):
        if self.s_engine.undo_last_action():
            scores = self.s_engine.get_all_scores()
            event_bus.undo_score.emit()
            event_bus.score_updated.emit(scores)

    def _update_dock_player_labels(self):
        for p_id in ("p1", "p2", "p3"):
            name = self.contestants[p_id]["name"]
            self.score_cards[p_id]["name_lbl"].setText(name)
            if hasattr(self, "compact_score_labels") and p_id in self.compact_score_labels:
                sc = self.contestants[p_id]["score"]
                prefix = f"-${abs(sc)}" if sc < 0 else f"${sc}"
                self.compact_score_labels[p_id].setText(f"{name}: {prefix}")

    def _update_dock_quick_point_buttons(self, points):
        for p_id in ("p1", "p2", "p3"):
            self.score_cards[p_id]["btn_add"].setText(f"+${points}")
            self.score_cards[p_id]["btn_sub"].setText(f"-${points}")

    def _update_live_score_display(self):
        for p_id in ("p1", "p2", "p3"):
            sc = self.contestants[p_id]["score"]
            lbl = self.score_cards[p_id]["score_lbl"]
            if sc < 0:
                lbl.setText(f"-${abs(sc)}")
                lbl.setStyleSheet("font-size: 26px; font-weight: 900; color: #f85149; background-color: #0d1117; border: 1px solid #21262d; border-radius: 6px; padding: 4px;")
            else:
                lbl.setText(f"${sc}")
                lbl.setStyleSheet("font-size: 26px; font-weight: 900; color: #3fb950; background-color: #0d1117; border: 1px solid #21262d; border-radius: 6px; padding: 4px;")

            if hasattr(self, "compact_score_labels") and p_id in self.compact_score_labels:
                name = self.contestants[p_id]["name"]
                prefix = f"-${abs(sc)}" if sc < 0 else f"${sc}"
                self.compact_score_labels[p_id].setText(f"{name}: {prefix}")
                color = "#f85149" if sc < 0 else "#3fb950"
                self.compact_score_labels[p_id].setStyleSheet(f"font-size: 13px; font-weight: 800; color: {color}; background: #0d1117; padding: 4px 12px; border-radius: 4px; border: 1px solid #21262d;")

        self._refresh_final_wagers_ui()

    def _register_event_bus(self):
        event_bus.score_updated.connect(self._on_score_updated)
        event_bus.change_round.connect(self._on_change_round)
        event_bus.unlock_round.connect(self._on_unlock_round_signal)

    @Slot(int)
    def _on_unlock_round_signal(self, round_id):
        self.unlocked_rounds[round_id] = True
        self._update_round_button_styles()

    @Slot(dict)
    def _on_score_updated(self, scores):
        for p_id, score in scores.items():
            if p_id in self.contestants:
                self.contestants[p_id]["score"] = score
        self._update_live_score_display()

    @Slot(int)
    def _on_change_round(self, round_id):
        if round_id in (1, 2, 3) and round_id != self.current_round:
            self.current_round = round_id
            self._update_round_button_styles()
            if round_id in (1, 2):
                self._load_board_for_round(round_id)


HostController = HostControllerWindow


def main():
    app = QApplication(sys.argv)
    window = HostControllerWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
