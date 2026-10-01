"""Open-J: Settings & Theme Configuration Dialog.
Broadcast-standard settings modal for theme visuals, bezels, graphics profiles,
sound bindings, and zip theme package export/import.
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QFont, QColor, QPainter, QBrush, QPen
from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QTabWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QSpinBox,
    QComboBox,
    QPushButton,
    QFileDialog,
    QColorDialog,
    QFontDialog,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
)

from core.event_bus import event_bus
from ui.theme_manager import ThemePackageEngine, ThemeConfigManager, AssetRenderer


APP_STYLE = """
QDialog {
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
    border-radius: 6px;
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
"""


class TVBezelPreviewWidget(QWidget):
    """Real-time Bezel and Matrix Simulation Preview Widget."""

    def __init__(self, bezel_width=8, bezel_color="#000000", parent=None):
        super().__init__(parent)
        self.bezel_width = bezel_width
        self.bezel_color = QColor(bezel_color)
        self.setMinimumSize(220, 140)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_bezel(self, width: int, color_hex: str):
        self.bezel_width = width
        self.bezel_color = QColor(color_hex)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        rect = self.rect()
        painter.fillRect(rect, self.bezel_color)

        cols, rows = 6, 6
        bw = max(2, int(self.bezel_width * 0.4))
        total_w = rect.width() - (bw * (cols + 1))
        total_h = rect.height() - (bw * (rows + 1))
        cell_w = max(4, total_w // cols)
        cell_h = max(4, total_h // rows)

        for r in range(rows):
            for c in range(cols):
                cx = bw + c * (cell_w + bw)
                cy = bw + r * (cell_h + bw)
                c_rect = QRect(cx, cy, cell_w, cell_h)
                if r == 0:
                    painter.fillRect(c_rect, QColor("#1f6feb"))
                else:
                    painter.fillRect(c_rect, QColor("#060CE9"))


class SettingsDialog(QDialog):
    """Studio Broadcast Configuration Dialog: Themes, Visuals, Bezels, Audio & Zip Packages."""

    def __init__(self, theme_data, audio_manager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("System Settings, Visual Customization & Theme Manager")
        self.resize(880, 680)
        self.setStyleSheet(APP_STYLE)

        loaded = ThemeConfigManager.load_theme_xml()
        self.theme = dict(loaded)
        if isinstance(theme_data, dict):
            for k, v in theme_data.items():
                if k in self.theme and isinstance(v, dict):
                    self.theme[k].update(v)
                else:
                    self.theme[k] = v

        self.audio_manager = audio_manager

        layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget(self)

        self.tab1 = self._build_theme_tab()
        self.tab2 = self._build_sound_tab()

        self.tab_widget.addTab(self.tab1, "1. Visuals & Theme Package")
        self.tab_widget.addTab(self.tab2, "2. Broadcast Sound Manager")
        layout.addWidget(self.tab_widget)

        btn_box = QHBoxLayout()
        btn_apply = QPushButton("Save Settings & Close")
        btn_apply.setStyleSheet("background-color: #238636; color: white; font-weight: bold; font-size: 14px; padding: 10px 22px;")
        btn_apply.clicked.connect(self._on_apply)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self._on_cancel)

        btn_box.addStretch()
        btn_box.addWidget(btn_apply)
        btn_box.addWidget(btn_close)
        layout.addLayout(btn_box)

    def closeEvent(self, event):
        self.audio_manager.stop_all()
        super().closeEvent(event)

    def _build_theme_tab(self):
        widget = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # 0. Graphic Engine Profile
        perf_box = QGroupBox("0. GRAPHIC ENGINE PROFILE & PERFORMANCE")
        perf_layout = QFormLayout(perf_box)
        self.combo_perf_profile = QComboBox()
        self.combo_perf_profile.addItem("Profile 2 - Balanced / Smooth (Smooth 60 FPS)", "smooth")
        self.combo_perf_profile.addItem("Profile 1 - Power Saver (Basic 30 FPS)", "basic")
        self.combo_perf_profile.addItem("Profile 3 - Studio Max (Broadcast Ultra - GPU OpenGL)", "ultra")

        curr_prof = self.theme.get("performance_profile", "smooth")
        idx = {"smooth": 0, "basic": 1, "ultra": 2}.get(curr_prof, 0)
        self.combo_perf_profile.setCurrentIndex(idx)
        perf_layout.addRow("TV Display Render Pipeline:", self.combo_perf_profile)
        layout.addWidget(perf_box)

        # 1. Category Headers (Red Zone)
        cat_box = QGroupBox("1. CATEGORY HEADERS - RED ZONE (TOP 6 CELLS)")
        cat_layout = QFormLayout(cat_box)

        lbl_cat_note = QLabel("Note: This graphic remains persistent across all 6 header cells, including Blank Board state.")
        lbl_cat_note.setStyleSheet("color: #8b949e; font-style: italic; margin-bottom: 4px;")
        cat_layout.addRow(lbl_cat_note)

        ch_data = self.theme.get("category_headers", {})

        row_unrev = QHBoxLayout()
        self.edit_cat_unrev = QLineEdit(ch_data.get("unrevealed_image", ""))
        btn_b_unrev = QPushButton("Browse...")
        btn_b_unrev.clicked.connect(lambda: self._browse_image(self.edit_cat_unrev))
        row_unrev.addWidget(self.edit_cat_unrev)
        row_unrev.addWidget(btn_b_unrev)
        cat_layout.addRow("Unrevealed Header Logo (Blank Board):", row_unrev)

        row_rev = QHBoxLayout()
        self.edit_cat_rev = QLineEdit(ch_data.get("revealed_image", ""))
        btn_b_rev = QPushButton("Browse...")
        btn_b_rev.clicked.connect(lambda: self._browse_image(self.edit_cat_rev))
        row_rev.addWidget(self.edit_cat_rev)
        row_rev.addWidget(btn_b_rev)
        cat_layout.addRow("Revealed Category Background:", row_rev)

        self.combo_cat_fit = QComboBox()
        self.combo_cat_fit.addItems(["zoom", "tile"])
        self.combo_cat_fit.setCurrentText(ch_data.get("fit_mode", "zoom"))
        cat_layout.addRow("Category Image Fit Mode:", self.combo_cat_fit)

        btn_cat_font = QPushButton("Configure Header Font...")
        self.cat_font_data = dict(ch_data.get("font", {"family": "Georgia", "size": 28, "bold": True, "color": "#FFFFFF"}))
        btn_cat_font.clicked.connect(self._choose_cat_font)
        cat_layout.addRow("Category Typography:", btn_cat_font)
        layout.addWidget(cat_box)

        # 2. Point Grid (Yellow Zone)
        point_box = QGroupBox("2. POINT GRID MATRIX - YELLOW ZONE (30 CLUE TILES)")
        point_layout = QFormLayout(point_box)
        pg_data = self.theme.get("point_grid", {})

        self.combo_pt_mode = QComboBox()
        self.combo_pt_mode.addItem("Use Background Image / Texture", True)
        self.combo_pt_mode.addItem("Use Solid Fill Color", False)
        self.combo_pt_mode.setCurrentIndex(0 if pg_data.get("use_image", True) else 1)
        point_layout.addRow("Tile Rendering Mode:", self.combo_pt_mode)

        row_tile = QHBoxLayout()
        self.edit_tile_img = QLineEdit(pg_data.get("tile_image", ""))
        btn_b_tile = QPushButton("Browse...")
        btn_b_tile.clicked.connect(lambda: self._browse_image(self.edit_tile_img))
        row_tile.addWidget(self.edit_tile_img)
        row_tile.addWidget(btn_b_tile)
        point_layout.addRow("Tile Texture Image:", row_tile)

        pt_col = pg_data.get("solid_color", "#060CE9")
        self.btn_pt_color = QPushButton(f"Select Color ({pt_col})")
        self.btn_pt_color.setStyleSheet(f"background-color: {pt_col}; color: white; font-weight: bold;")
        self.pt_solid_color = pt_col
        self.btn_pt_color.clicked.connect(self._choose_point_color)
        point_layout.addRow("Solid Fill Color:", self.btn_pt_color)

        self.combo_pt_fit = QComboBox()
        self.combo_pt_fit.addItems(["zoom", "tile"])
        self.combo_pt_fit.setCurrentText(pg_data.get("fit_mode", "zoom"))
        point_layout.addRow("Tile Image Fit Mode:", self.combo_pt_fit)

        btn_pt_font = QPushButton("Configure Point Value Typography...")
        self.pt_font_data = dict(pg_data.get("font", {"family": "Impact", "size": 48, "bold": True, "color": "#FFA500"}))
        btn_pt_font.clicked.connect(self._choose_point_font)
        point_layout.addRow("Point Value Typography:", btn_pt_font)
        layout.addWidget(point_box)

        # 3. Clue Screen Cards
        clue_box = QGroupBox("3. CLUE CARDS & SHARED BROADCAST TYPOGRAPHY")
        clue_layout = QFormLayout(clue_box)
        cs_data = self.theme.get("clue_screen", {})
        std_card = cs_data.get("standard_card", {})
        fin_card = cs_data.get("final_card", {})

        row_blue = QHBoxLayout()
        self.edit_blue_img = QLineEdit(std_card.get("image_path", ""))
        btn_b_blue = QPushButton("Browse...")
        btn_b_blue.clicked.connect(lambda: self._browse_image(self.edit_blue_img))
        row_blue.addWidget(self.edit_blue_img)
        row_blue.addWidget(btn_b_blue)
        clue_layout.addRow("Round 1 & 2 Blue Clue Texture:", row_blue)

        blue_col = std_card.get("color", "#060CE9")
        self.btn_blue_col = QPushButton(f"Select Color ({blue_col})")
        self.btn_blue_col.setStyleSheet(f"background-color: {blue_col}; color: white; font-weight: bold;")
        self.blue_color_val = blue_col
        self.btn_blue_col.clicked.connect(self._choose_blue_color)
        clue_layout.addRow("Blue Solid Color:", self.btn_blue_col)

        row_red = QHBoxLayout()
        self.edit_red_img = QLineEdit(fin_card.get("image_path", ""))
        btn_b_red = QPushButton("Browse...")
        btn_b_red.clicked.connect(lambda: self._browse_image(self.edit_red_img))
        row_red.addWidget(self.edit_red_img)
        row_red.addWidget(btn_b_red)
        clue_layout.addRow("Final Jeopardy 15s Red Texture:", row_red)

        red_col = fin_card.get("color", "#8B0000")
        self.btn_red_col = QPushButton(f"Select Color ({red_col})")
        self.btn_red_col.setStyleSheet(f"background-color: {red_col}; color: white; font-weight: bold;")
        self.red_color_val = red_col
        self.btn_red_col.clicked.connect(self._choose_red_color)
        clue_layout.addRow("Red Solid Color:", self.btn_red_col)

        btn_shared_font = QPushButton("Configure Shared Clue Font...")
        self.clue_font_data = dict(cs_data.get("font", {"family": "Georgia", "size": 48, "bold": True, "color": "#FFFFFF"}))
        btn_shared_font.clicked.connect(self._choose_clue_font)
        clue_layout.addRow("Clue Screen Typography:", btn_shared_font)

        self.lbl_shared_font = QLabel(f"Active Font: {self.clue_font_data.get('family', 'Georgia')} (Syncs to Clue & Final)")
        self.lbl_shared_font.setStyleSheet("color: #58a6ff; font-weight: bold; background-color: #0d1117; padding: 6px; border-radius: 4px;")
        clue_layout.addRow("Typography Sync:", self.lbl_shared_font)

        sh_data = cs_data.get("shadow", {})
        sh_row = QHBoxLayout()
        self.spin_sh_blur = QSpinBox()
        self.spin_sh_blur.setRange(0, 20)
        self.spin_sh_blur.setValue(int(sh_data.get("blur", 2)))
        self.spin_sh_dx = QSpinBox()
        self.spin_sh_dx.setRange(-20, 20)
        self.spin_sh_dx.setValue(int(sh_data.get("dx", 3)))
        self.spin_sh_dy = QSpinBox()
        self.spin_sh_dy.setRange(-20, 20)
        self.spin_sh_dy.setValue(int(sh_data.get("dy", 3)))
        sh_row.addWidget(QLabel("Blur:"))
        sh_row.addWidget(self.spin_sh_blur)
        sh_row.addWidget(QLabel("Offset X:"))
        sh_row.addWidget(self.spin_sh_dx)
        sh_row.addWidget(QLabel("Offset Y:"))
        sh_row.addWidget(self.spin_sh_dy)
        clue_layout.addRow("Drop Shadow Settings:", sh_row)
        layout.addWidget(clue_box)

        # 4. Visual FX & Daily Double
        vfx_box = QGroupBox("4. DAILY DOUBLE GRAPHICS & BROADCAST SPLASH")
        vfx_layout = QFormLayout(vfx_box)
        vfx_data = self.theme.get("visual_fx", {})

        row_dd = QHBoxLayout()
        self.edit_dd_splash = QLineEdit(vfx_data.get("daily_double_splash", ""))
        btn_b_dd = QPushButton("Browse...")
        btn_b_dd.clicked.connect(lambda: self._browse_image(self.edit_dd_splash))
        row_dd.addWidget(self.edit_dd_splash)
        row_dd.addWidget(btn_b_dd)
        vfx_layout.addRow("Daily Double Splash Graphic:", row_dd)

        row_fl = QHBoxLayout()
        self.edit_final_logo = QLineEdit(vfx_data.get("final_logo_splash", ""))
        btn_b_fl = QPushButton("Browse...")
        btn_b_fl.clicked.connect(lambda: self._browse_image(self.edit_final_logo))
        row_fl.addWidget(self.edit_final_logo)
        row_fl.addWidget(btn_b_fl)
        vfx_layout.addRow("Final Jeopardy Splash Graphic:", row_fl)
        layout.addWidget(vfx_box)

        # 5. Standby Mosaic Wall (Yellow Zone)
        standby_box = QGroupBox("5. 36-TILE STANDBY MOSAIC VIDEO WALL")
        standby_layout = QFormLayout(standby_box)
        lbl_sb_note = QLabel("Note: A single high-resolution wallpaper is mapped across all 36 matrix cells, partitioned by black bezels.")
        lbl_sb_note.setStyleSheet("color: #8b949e; font-style: italic; margin-bottom: 4px;")
        standby_layout.addRow(lbl_sb_note)

        sb_img = self.theme.get("standby_screen", {}).get("image_path", "")
        row_sb = QHBoxLayout()
        self.edit_sb_img = QLineEdit(sb_img)
        btn_b_sb = QPushButton("Browse...")
        btn_b_sb.clicked.connect(lambda: self._browse_image(self.edit_sb_img))
        row_sb.addWidget(self.edit_sb_img)
        row_sb.addWidget(btn_b_sb)
        standby_layout.addRow("Standby Mosaic Wallpaper:", row_sb)
        layout.addWidget(standby_box)

        # 6. Bezel Simulation
        bezel_box = QGroupBox("6. MATRIX BEZEL SIMULATION (100% SQUARE INDUSTRIAL EDGES)")
        bezel_layout = QFormLayout(bezel_box)

        self.spin_bezel_w = QSpinBox()
        self.spin_bezel_w.setRange(2, 32)
        self.spin_bezel_w.setValue(int(self.theme.get("bezel_width", 8)))
        self.spin_bezel_w.valueChanged.connect(self._on_bezel_ui_changed)
        bezel_layout.addRow("Bezel Width (px):", self.spin_bezel_w)

        b_col = self.theme.get("bezel_color", "#000000")
        self.btn_bezel_col = QPushButton(f"Bezel Color ({b_col})")
        self.btn_bezel_col.setStyleSheet(f"background-color: {b_col}; color: white; font-weight: bold;")
        self.bezel_color_val = b_col
        self.btn_bezel_col.clicked.connect(self._choose_bezel_color)
        bezel_layout.addRow("Bezel Color:", self.btn_bezel_col)

        self.bezel_preview = TVBezelPreviewWidget(self.spin_bezel_w.value(), self.bezel_color_val)
        bezel_layout.addRow("Matrix Bezel Preview:", self.bezel_preview)
        layout.addWidget(bezel_box)

        # 7. Theme Package Manager
        zip_box = QGroupBox("7. THEME PACKAGE MANAGER (.ZIP)")
        zip_layout = QHBoxLayout(zip_box)

        btn_export_zip = QPushButton("Export Theme Package (.zip)...")
        btn_export_zip.setStyleSheet("background-color: #1f6feb; color: white; font-weight: bold; padding: 8px 16px;")
        btn_export_zip.clicked.connect(self._on_export_zip)

        btn_import_zip = QPushButton("Import Theme Package (.zip)...")
        btn_import_zip.setStyleSheet("background-color: #8957e5; color: white; font-weight: bold; padding: 8px 16px;")
        btn_import_zip.clicked.connect(self._on_import_zip)

        zip_layout.addWidget(btn_export_zip)
        zip_layout.addWidget(btn_import_zip)
        layout.addWidget(zip_box)

        scroll.setWidget(container)
        v = QVBoxLayout(widget)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(scroll)
        return widget

    def _build_sound_tab(self):
        widget = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        dir_box = QGroupBox("STUDIO BROADCAST AUDIO DIRECTORY")
        dir_layout = QHBoxLayout(dir_box)
        self.edit_sound_dir = QLineEdit(str(PROJECT_ROOT / "ui" / "assets" / "sounds"))
        btn_b_sdir = QPushButton("Browse Folder...")
        btn_b_sdir.clicked.connect(self._browse_sound_dir)
        dir_layout.addWidget(self.edit_sound_dir)
        dir_layout.addWidget(btn_b_sdir)
        layout.addWidget(dir_box)

        event_box = QGroupBox("EVENT AUDIO BINDINGS (NO DEMO / SYNTHETIC TONES)")
        event_layout = QFormLayout(event_box)

        sound_labels = {
            "board_fill": "Board Opening Fanfare (1 playback):",
            "daily_double": "Daily Double Laser / Reveal Fanfare:",
            "think_30s": "Final Jeopardy 30s Think Music:",
            "wager_music": "Final Jeopardy Wager Waiting Music:",
            "timeout": "Timeout / Incorrect Tone:",
            "category_intro": "Final Category Reveal Chime:",
        }

        sounds_dict = self.theme.get("sounds", {})
        self.sound_edits = {}

        for k, lbl in sound_labels.items():
            row = QHBoxLayout()
            val = sounds_dict.get(k, "")
            edit = QLineEdit(val)
            self.sound_edits[k] = edit
            btn_b = QPushButton("Browse...")
            btn_b.clicked.connect(lambda chk=False, e=edit: self._browse_sound(e))
            btn_play = QPushButton("Play")
            btn_play.setStyleSheet("background-color: #238636; color: white; padding: 4px 10px;")
            btn_play.clicked.connect(lambda chk=False, e=edit: self._preview_sound(e.text().strip()))

            btn_stop = QPushButton("Stop")
            btn_stop.setStyleSheet("background-color: #da3633; color: white; padding: 4px 10px;")
            btn_stop.clicked.connect(lambda: self.audio_manager.stop_all())

            row.addWidget(edit, 1)
            row.addWidget(btn_b)
            row.addWidget(btn_play)
            row.addWidget(btn_stop)
            event_layout.addRow(lbl, row)

        layout.addWidget(event_box)
        layout.addStretch()

        scroll.setWidget(container)
        v = QVBoxLayout(widget)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(scroll)
        return widget

    def _browse_image(self, target_line_edit: QLineEdit):
        f, _ = QFileDialog.getOpenFileName(self, "Select Graphic Asset", "", "Image Files (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)")
        if f:
            target_line_edit.setText(f)

    def _browse_sound(self, target_line_edit: QLineEdit):
        f, _ = QFileDialog.getOpenFileName(self, "Select Audio File", "", "Audio Files (*.wav *.mp3 *.m4a *.aac);;All Files (*)")
        if f:
            target_line_edit.setText(f)

    def _browse_sound_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Studio Audio Directory", self.edit_sound_dir.text().strip())
        if d:
            self.edit_sound_dir.setText(d)

    def _preview_sound(self, file_path: str):
        if file_path and os.path.isfile(file_path):
            self.audio_manager.stop_all()
            self.audio_manager.play_file(file_path)

    def _choose_point_color(self):
        c = QColorDialog.getColor(QColor(self.pt_solid_color), self, "Select Tile Solid Fill Color")
        if c.isValid():
            self.pt_solid_color = c.name()
            self.btn_pt_color.setText(f"Select Color ({self.pt_solid_color})")
            self.btn_pt_color.setStyleSheet(f"background-color: {self.pt_solid_color}; color: white; font-weight: bold;")

    def _choose_blue_color(self):
        c = QColorDialog.getColor(QColor(self.blue_color_val), self, "Select Round 1 & 2 Blue Color")
        if c.isValid():
            self.blue_color_val = c.name()
            self.btn_blue_col.setText(f"Select Color ({self.blue_color_val})")
            self.btn_blue_col.setStyleSheet(f"background-color: {self.blue_color_val}; color: white; font-weight: bold;")

    def _choose_red_color(self):
        c = QColorDialog.getColor(QColor(self.red_color_val), self, "Select Final 15s Red Color")
        if c.isValid():
            self.red_color_val = c.name()
            self.btn_red_col.setText(f"Select Color ({self.red_color_val})")
            self.btn_red_col.setStyleSheet(f"background-color: {self.red_color_val}; color: white; font-weight: bold;")

    def _choose_bezel_color(self):
        c = QColorDialog.getColor(QColor(self.bezel_color_val), self, "Select Matrix Bezel Color")
        if c.isValid():
            self.bezel_color_val = c.name()
            self.btn_bezel_col.setText(f"Bezel Color ({self.bezel_color_val})")
            self.btn_bezel_col.setStyleSheet(f"background-color: {self.bezel_color_val}; color: white; font-weight: bold;")
            self._on_bezel_ui_changed()

    def _on_bezel_ui_changed(self):
        self.bezel_preview.set_bezel(self.spin_bezel_w.value(), self.bezel_color_val)

    def _choose_cat_font(self):
        curr = QFont(self.cat_font_data.get("family", "Georgia"), int(self.cat_font_data.get("size", 28)))
        ok, f = QFontDialog.getFont(curr, self, "Select Category Header Typography")
        if ok:
            self.cat_font_data["family"] = f.family()
            self.cat_font_data["size"] = f.pointSize()
            self.cat_font_data["bold"] = f.bold()

    def _choose_point_font(self):
        curr = QFont(self.pt_font_data.get("family", "Impact"), int(self.pt_font_data.get("size", 48)))
        ok, f = QFontDialog.getFont(curr, self, "Select Point Value Typography")
        if ok:
            self.pt_font_data["family"] = f.family()
            self.pt_font_data["size"] = f.pointSize()
            self.pt_font_data["bold"] = f.bold()

    def _choose_clue_font(self):
        curr = QFont(self.clue_font_data.get("family", "Georgia"), int(self.clue_font_data.get("size", 48)))
        ok, f = QFontDialog.getFont(curr, self, "Select Clue Screen Typography")
        if ok:
            self.clue_font_data["family"] = f.family()
            self.clue_font_data["size"] = f.pointSize()
            self.clue_font_data["bold"] = f.bold()
            self.lbl_shared_font.setText(f"Active Font: {f.family()} (Syncs to Clue & Final)")

    def _on_export_zip(self):
        self._collect_ui_to_theme()
        ThemeConfigManager.save_theme_xml(self.theme)

        f, _ = QFileDialog.getSaveFileName(self, "Export Theme Package (.zip)", "Jeopardy_Broadcast_Theme.zip", "Zip Archive (*.zip);;All Files (*)")
        if f:
            try:
                xml_path = str(PROJECT_ROOT / "ui" / "assets" / "theme.xml")
                assets_dir = str(PROJECT_ROOT / "ui" / "assets")
                ThemePackageEngine.export_theme_to_zip(xml_path, assets_dir, f)
                QMessageBox.information(self, "Export Successful", f"Theme package exported successfully:\n{f}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", str(e))

    def _on_import_zip(self):
        f, _ = QFileDialog.getOpenFileName(self, "Import Theme Package (.zip)", "", "Zip Archive (*.zip);;All Files (*)")
        if f:
            try:
                assets_dir = str(PROJECT_ROOT / "ui" / "assets")
                xml_extracted = ThemePackageEngine.import_theme_from_zip(f, assets_dir)
                self.theme = ThemeConfigManager.load_theme_xml(str(xml_extracted))
                event_bus.reload_theme_config.emit()
                event_bus.update_theme_config.emit(self.theme)
                QMessageBox.information(self, "Import Successful", "Theme package imported and applied immediately!")
                self.accept()
            except Exception as e:
                QMessageBox.critical(self, "Import Error", str(e))

    def _collect_ui_to_theme(self):
        self.theme["performance_profile"] = self.combo_perf_profile.currentData()

        self.theme["bezel_width"] = self.spin_bezel_w.value()
        self.theme["bezel_color"] = self.bezel_color_val

        # Category Headers
        ch = self.theme.setdefault("category_headers", {})
        ch["unrevealed_image"] = self.edit_cat_unrev.text().strip()
        ch["revealed_image"] = self.edit_cat_rev.text().strip()
        ch["fit_mode"] = self.combo_cat_fit.currentText()
        ch["font"] = dict(self.cat_font_data)

        # Point Grid
        pg = self.theme.setdefault("point_grid", {})
        pg["use_image"] = self.combo_pt_mode.currentData()
        pg["tile_image"] = self.edit_tile_img.text().strip()
        pg["solid_color"] = self.pt_solid_color
        pg["fit_mode"] = self.combo_pt_fit.currentText()
        pg["font"] = dict(self.pt_font_data)

        # Clue Screen
        cs = self.theme.setdefault("clue_screen", {})
        std = cs.setdefault("standard_card", {})
        std["image_path"] = self.edit_blue_img.text().strip()
        std["color"] = self.blue_color_val
        std["use_image"] = bool(std["image_path"])

        fin = cs.setdefault("final_card", {})
        fin["image_path"] = self.edit_red_img.text().strip()
        fin["color"] = self.red_color_val
        fin["use_image"] = bool(fin["image_path"])

        cs["font"] = dict(self.clue_font_data)
        sh = cs.setdefault("shadow", {})
        sh["blur"] = self.spin_sh_blur.value()
        sh["dx"] = self.spin_sh_dx.value()
        sh["dy"] = self.spin_sh_dy.value()

        # Standby Mosaic
        sb = self.theme.setdefault("standby_screen", {})
        sb["image_path"] = self.edit_sb_img.text().strip()

        # Visual FX
        vfx = self.theme.setdefault("visual_fx", {})
        vfx["daily_double_splash"] = self.edit_dd_splash.text().strip()
        vfx["final_logo_splash"] = self.edit_final_logo.text().strip()

        # Sounds
        sounds = self.theme.setdefault("sounds", {})
        for k, e in self.sound_edits.items():
            path_val = e.text().strip()
            sounds[k] = path_val
            if path_val:
                self.audio_manager.set_sound_file(k, path_val)

    def _on_apply(self):
        """Immediately stops all audio, writes XML, emits updates, and accepts dialog."""
        self.audio_manager.stop_all()
        self._collect_ui_to_theme()

        ThemeConfigManager.save_theme_xml(self.theme)

        event_bus.reload_theme_config.emit()
        event_bus.update_theme_config.emit(self.theme)
        self.accept()

    def _on_cancel(self):
        self.audio_manager.stop_all()
        self.reject()


__all__ = ["TVBezelPreviewWidget", "SettingsDialog"]
