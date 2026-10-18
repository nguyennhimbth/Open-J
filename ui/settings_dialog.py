"""Open-J: Settings & Theme Configuration Dialog.
Broadcast-standard settings modal featuring 4 dedicated tabs:
1. Visuals & Theme Package (including OpenGL GPU Hardware Acceleration)
2. Typography & Fonts (Section 1: Clue/Answer/Category Header, Section 2: Point Grid 200..2000; Dynamic vs Custom size modes)
3. Animation & Intro / Outro (Point Zoom toggle, 3D Flip toggle, Intro Video -> Static Standby Merge after N seconds, Outro Music on Static Standby)
4. Broadcast Sound Manager (Per-event audio bindings without folder override or wager waiting music)
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QFont, QColor, QPainter
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
    QDoubleSpinBox,
    QComboBox,
    QFontComboBox,
    QCheckBox,
    QPushButton,
    QFileDialog,
    QColorDialog,
    QFontDialog,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
)

from core.event_bus import event_bus
from ui.theme_manager import ThemePackageEngine, ThemeConfigManager


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
    padding: 10px 16px;
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
    margin-top: 22px;
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
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QFontComboBox {
    background-color: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 6px 10px;
    min-height: 24px;
    color: #f0f6fc;
    font-size: 13px;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QFontComboBox:focus {
    border: 1px solid #58a6ff;
}
QCheckBox {
    color: #e6edf3;
    font-size: 13px;
    font-weight: 600;
    spacing: 8px;
}
QPushButton {
    background-color: #21262d;
    border: 1px solid #30363d;
    border-radius: 6px;
    color: #c9d1d9;
    padding: 7px 14px;
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
        self.setMinimumSize(220, 130)
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
    """Studio Broadcast Configuration Dialog:
    Tab 1: Visuals & Theme Package
    Tab 2: Typography & Fonts (Clue/Answer/Category Header + Point Grid Values)
    Tab 3: Animation & Intro/Outro (Point Zoom toggle + Standby Intro Video Merge + Outro Music)
    Tab 4: Broadcast Sound Manager (Individual event audio bindings)
    """

    def __init__(self, theme_data, audio_manager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("System Settings, Visual Customization, Fonts, Animations & Sound Manager")
        self.resize(940, 720)
        self.setStyleSheet(APP_STYLE)

        loaded = ThemeConfigManager.load_theme_xml()
        self.theme = dict(loaded)
        if isinstance(theme_data, dict):
            for k, v in theme_data.items():
                if k in self.theme and isinstance(v, dict) and isinstance(self.theme[k], dict):
                    self.theme[k].update(v)
                else:
                    self.theme[k] = v

        self.audio_manager = audio_manager

        layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget(self)

        self.tab1 = self._build_theme_tab()
        self.tab2 = self._build_font_tab()
        self.tab3 = self._build_animation_tab()
        self.tab4 = self._build_sound_tab()

        self.tab_widget.addTab(self.tab1, "1. Visuals & Theme")
        self.tab_widget.addTab(self.tab2, "2. Typography & Fonts")
        self.tab_widget.addTab(self.tab3, "3. Animation & Intro/Outro")
        self.tab_widget.addTab(self.tab4, "4. Broadcast Sound Manager")
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

    # =========================================================================
    # TAB 1: VISUALS & THEME PACKAGE
    # =========================================================================

    def _build_theme_tab(self):
        widget = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # 0. Graphic Engine Profile & OpenGL Hardware Acceleration
        perf_box = QGroupBox("0. GRAPHIC ENGINE PROFILE & OPENGL HARDWARE ACCELERATION")
        perf_layout = QFormLayout(perf_box)
        self.combo_perf_profile = QComboBox()
        self.combo_perf_profile.addItem("Profile 3 - Studio Max (OpenGL GPU + 4x MSAA + VSync)", "ultra")
        self.combo_perf_profile.addItem("Profile 2 - Balanced / Smooth (60 FPS Cached)", "smooth")
        self.combo_perf_profile.addItem("Profile 1 - Power Saver (30 FPS Basic)", "basic")

        curr_prof = self.theme.get("performance_profile", "ultra")
        idx = {"ultra": 0, "smooth": 1, "basic": 2}.get(curr_prof, 0)
        self.combo_perf_profile.setCurrentIndex(idx)
        perf_layout.addRow("TV Display Render Pipeline:", self.combo_perf_profile)

        gl_status = "Active (PySide6 QOpenGLWidget + VSync)"
        try:
            import OpenGL.GL  # noqa: F401
            gl_status += " + PyOpenGL Accelerated"
        except Exception:
            gl_status += " (Tip: 'pip install PyOpenGL PyOpenGL_accelerate' for extra GL bindings)"
        lbl_gl = QLabel(f"OpenGL Pipeline Status: {gl_status}")
        lbl_gl.setStyleSheet("color: #3fb950; font-weight: bold;")
        perf_layout.addRow("GPU Status:", lbl_gl)
        layout.addWidget(perf_box)

        # 1. Category Headers (Red Zone)
        cat_box = QGroupBox("1. CATEGORY HEADERS - RED ZONE (TOP 6 CELLS)")
        cat_layout = QFormLayout(cat_box)

        lbl_cat_note = QLabel(
            "Logo fills 100% of the yellow category cell edge-to-edge. "
            "Also switches back to this logo automatically when all 5 clues in a column are answered."
        )
        lbl_cat_note.setWordWrap(True)
        lbl_cat_note.setStyleSheet("color: #8b949e; font-style: italic; margin-bottom: 4px;")
        cat_layout.addRow(lbl_cat_note)

        ch_data = self.theme.get("category_headers", {})

        row_unrev = QHBoxLayout()
        self.edit_cat_unrev = QLineEdit(ch_data.get("unrevealed_image", ""))
        btn_b_unrev = QPushButton("Browse...")
        btn_b_unrev.clicked.connect(lambda: self._browse_image(self.edit_cat_unrev))
        row_unrev.addWidget(self.edit_cat_unrev)
        row_unrev.addWidget(btn_b_unrev)
        cat_layout.addRow("Unrevealed / Exhausted Header Logo:", row_unrev)

        row_rev = QHBoxLayout()
        self.edit_cat_rev = QLineEdit(ch_data.get("revealed_image", ""))
        btn_b_rev = QPushButton("Browse...")
        btn_b_rev.clicked.connect(lambda: self._browse_image(self.edit_cat_rev))
        row_rev.addWidget(self.edit_cat_rev)
        row_rev.addWidget(btn_b_rev)
        cat_layout.addRow("Revealed Category Background:", row_rev)

        self.combo_cat_fit = QComboBox()
        self.combo_cat_fit.addItems(["stretch", "zoom", "tile"])
        self.combo_cat_fit.setCurrentText(ch_data.get("fit_mode", "stretch"))
        cat_layout.addRow("Category Image Fit Mode:", self.combo_cat_fit)

        self.chk_auto_crop_logo = QCheckBox("Auto-crop inner borders on Header Logo so logo fills 100% of cell")
        self.chk_auto_crop_logo.setChecked(bool(ch_data.get("auto_crop_logo", True)))
        cat_layout.addRow("Full-Cell Logo Fill:", self.chk_auto_crop_logo)
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
        self.combo_pt_fit.addItems(["zoom", "stretch", "tile"])
        self.combo_pt_fit.setCurrentText(pg_data.get("fit_mode", "zoom"))
        point_layout.addRow("Tile Image Fit Mode:", self.combo_pt_fit)
        layout.addWidget(point_box)

        # 3. Clue Screen Cards
        clue_box = QGroupBox("3. CLUE CARDS & FINAL JEOPARDY BACKGROUNDS (FULL-BLEED 100%)")
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

        # 5. Bezel Simulation
        bezel_box = QGroupBox("5. MATRIX BEZEL SIMULATION (100% SQUARE INDUSTRIAL EDGES)")
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

        # 6. Theme Package Manager
        zip_box = QGroupBox("6. THEME PACKAGE MANAGER (.ZIP)")
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

    # =========================================================================
    # TAB 2: TYPOGRAPHY & FONTS (REQUIREMENTS #2 & #6)
    # =========================================================================

    def _build_font_tab(self):
        widget = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(18)

        ch_font = self.theme.get("category_headers", {}).get("font", {})
        cs_data = self.theme.get("clue_screen", {})
        cs_font = cs_data.get("font", {})
        sh_data = cs_data.get("shadow", {})
        pg_font = self.theme.get("point_grid", {}).get("font", {})

        # ---------------------------------------------------------------------
        # SECTION 1: CLUE QUESTION, ANSWER OVERLAY & CATEGORY HEADER TYPOGRAPHY
        # ---------------------------------------------------------------------
        sec1_box = QGroupBox("1. CÂU HỎI, ĐÁP ÁN & TIÊU ĐỀ CHỦ ĐỀ (CLUE, ANSWER & CATEGORY HEADERS)")
        sec1_layout = QFormLayout(sec1_box)
        sec1_layout.setSpacing(12)

        lbl_sec1_info = QLabel(
            "Unified typography across Round 1/2 Clues, Final Jeopardy Clues, Answer Overlays, and Category Headers.\n"
            "• Dynamic Mode: Automatically scales font size to fit screen/cell bounds without ever clipping long words (e.g. 'ARCHITECTURE', 'ABBREVIATIONS').\n"
            "• Custom Mode: Uses your exact chosen font sizes below."
        )
        lbl_sec1_info.setWordWrap(True)
        lbl_sec1_info.setStyleSheet("color: #8b949e; font-style: italic;")
        sec1_layout.addRow(lbl_sec1_info)

        # Font Family + Bold + Color
        fam_row = QHBoxLayout()
        self.font_combo_shared = QFontComboBox()
        init_family = cs_font.get("family") or ch_font.get("family", "ITC Korinna")
        self.font_combo_shared.setCurrentFont(QFont(init_family))
        self.chk_shared_bold = QCheckBox("Bold")
        self.chk_shared_bold.setChecked(bool(cs_font.get("bold", True)))

        self.shared_font_color = cs_font.get("color", "#FFFFFF")
        self.btn_shared_color = QPushButton(f"Color ({self.shared_font_color})")
        self.btn_shared_color.setStyleSheet(f"background-color: {self.shared_font_color}; color: #000000; font-weight: bold;")
        self.btn_shared_color.clicked.connect(self._choose_shared_font_color)

        fam_row.addWidget(self.font_combo_shared, 1)
        fam_row.addWidget(self.chk_shared_bold)
        fam_row.addWidget(self.btn_shared_color)
        sec1_layout.addRow("Shared Font Family & Style:", fam_row)

        # Sizing Mode: Dynamic vs Custom
        self.combo_shared_font_mode = QComboBox()
        self.combo_shared_font_mode.addItem("Dynamic (Auto-fit theo màn hình & ô - Chống tràn chữ)", "dynamic")
        self.combo_shared_font_mode.addItem("Custom Fixed Size (Tự chọn kích thước cố định)", "custom")
        shared_mode = cs_font.get("mode") or ch_font.get("mode", "dynamic")
        self.combo_shared_font_mode.setCurrentIndex(0 if shared_mode == "dynamic" else 1)
        self.combo_shared_font_mode.currentIndexChanged.connect(self._on_shared_font_mode_changed)
        sec1_layout.addRow("Font Sizing Mode (Chế độ):", self.combo_shared_font_mode)

        # Custom Sizes (Category Header, Clue Text, Answer Overlay)
        self.spin_cat_font_size = QSpinBox()
        self.spin_cat_font_size.setRange(12, 96)
        self.spin_cat_font_size.setValue(int(ch_font.get("size", 28)))
        self.spin_cat_font_size.setSuffix(" pt")
        sec1_layout.addRow("Category Header Font Size (Tiêu đề chủ đề):", self.spin_cat_font_size)

        self.spin_clue_font_size = QSpinBox()
        self.spin_clue_font_size.setRange(16, 120)
        self.spin_clue_font_size.setValue(int(cs_font.get("size", 48)))
        self.spin_clue_font_size.setSuffix(" pt")
        sec1_layout.addRow("Clue & Final Question Size (Câu hỏi):", self.spin_clue_font_size)

        self.spin_answer_font_size = QSpinBox()
        self.spin_answer_font_size.setRange(12, 72)
        self.spin_answer_font_size.setValue(int(cs_font.get("answer_size", 30)))
        self.spin_answer_font_size.setSuffix(" pt")
        sec1_layout.addRow("Answer Overlay Size (Đáp án):", self.spin_answer_font_size)

        # Drop Shadow
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
        sec1_layout.addRow("Drop Shadow:", sh_row)

        layout.addWidget(sec1_box)

        # ---------------------------------------------------------------------
        # SECTION 2: POINT GRID VALUES TYPOGRAPHY (200, 400, 600...)
        # ---------------------------------------------------------------------
        sec2_box = QGroupBox("2. BẢNG ĐIỂM ($200, $400, $600, $800, $1000...) (POINT GRID TYPOGRAPHY)")
        sec2_layout = QFormLayout(sec2_box)
        sec2_layout.setSpacing(12)

        pt_fam_row = QHBoxLayout()
        self.font_combo_points = QFontComboBox()
        self.font_combo_points.setCurrentFont(QFont(pg_font.get("family", "Impact")))
        self.chk_points_bold = QCheckBox("Bold")
        self.chk_points_bold.setChecked(bool(pg_font.get("bold", True)))

        self.point_font_color = pg_font.get("color", "#FFA500")
        self.btn_point_font_color = QPushButton(f"Color ({self.point_font_color})")
        self.btn_point_font_color.setStyleSheet(f"background-color: {self.point_font_color}; color: #000000; font-weight: bold;")
        self.btn_point_font_color.clicked.connect(self._choose_point_font_color)

        pt_fam_row.addWidget(self.font_combo_points, 1)
        pt_fam_row.addWidget(self.chk_points_bold)
        pt_fam_row.addWidget(self.btn_point_font_color)
        sec2_layout.addRow("Point Grid Font Family & Style:", pt_fam_row)

        self.combo_point_font_mode = QComboBox()
        self.combo_point_font_mode.addItem("Dynamic (Auto-fit theo kích thước ô màn hình)", "dynamic")
        self.combo_point_font_mode.addItem("Custom Fixed Size (Tự chọn kích thước cố định)", "custom")
        pt_mode = pg_font.get("mode", "dynamic")
        self.combo_point_font_mode.setCurrentIndex(0 if pt_mode == "dynamic" else 1)
        sec2_layout.addRow("Point Font Sizing Mode (Chế độ):", self.combo_point_font_mode)

        self.spin_point_font_size = QSpinBox()
        self.spin_point_font_size.setRange(16, 140)
        self.spin_point_font_size.setValue(int(pg_font.get("size", 48)))
        self.spin_point_font_size.setSuffix(" pt")
        sec2_layout.addRow("Point Value Font Size (Cỡ chữ bảng điểm):", self.spin_point_font_size)

        layout.addWidget(sec2_box)
        layout.addStretch()

        scroll.setWidget(container)
        v = QVBoxLayout(widget)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(scroll)
        return widget

    def _on_shared_font_mode_changed(self):
        pass

    def _choose_shared_font_color(self):
        c = QColorDialog.getColor(QColor(self.shared_font_color), self, "Select Clue / Header Text Color")
        if c.isValid():
            self.shared_font_color = c.name()
            self.btn_shared_color.setText(f"Color ({self.shared_font_color})")
            self.btn_shared_color.setStyleSheet(f"background-color: {self.shared_font_color}; color: #000000; font-weight: bold;")

    def _choose_point_font_color(self):
        c = QColorDialog.getColor(QColor(self.point_font_color), self, "Select Point Value Text Color")
        if c.isValid():
            self.point_font_color = c.name()
            self.btn_point_font_color.setText(f"Color ({self.point_font_color})")
            self.btn_point_font_color.setStyleSheet(f"background-color: {self.point_font_color}; color: #000000; font-weight: bold;")

    # =========================================================================
    # TAB 3: ANIMATION & INTRO / OUTRO (REQUIREMENTS #5 & #7)
    # =========================================================================

    def _build_animation_tab(self):
        widget = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(18)

        anim_data = self.theme.get("animations", {})
        sb_img = self.theme.get("standby_screen", {}).get("image_path", "")

        # 1. Point Zoom & Card Flip Animation Controls
        zoom_box = QGroupBox("1. HIỆU ỨNG CHUYỂN CẢNH BẢNG ĐIỂM & DAILY DOUBLE (BOARD & CLUE ANIMATIONS)")
        zoom_layout = QFormLayout(zoom_box)
        zoom_layout.setSpacing(12)

        self.chk_enable_point_zoom = QCheckBox("Chạy animation Zoom vào ô điểm khi mở câu hỏi (Enable Point Tile Zoom Animation)")
        self.chk_enable_point_zoom.setChecked(bool(anim_data.get("enable_point_zoom", True)))
        zoom_layout.addRow("Point Tile Zoom:", self.chk_enable_point_zoom)

        self.spin_zoom_duration = QSpinBox()
        self.spin_zoom_duration.setRange(100, 2000)
        self.spin_zoom_duration.setSingleStep(50)
        self.spin_zoom_duration.setValue(int(anim_data.get("zoom_duration_ms", 400)))
        self.spin_zoom_duration.setSuffix(" ms")
        zoom_layout.addRow("Zoom Animation Duration:", self.spin_zoom_duration)

        self.chk_enable_dd_flip = QCheckBox("Chạy animation lật 3D Daily Double -> Nền đen -> Câu hỏi (Enable 3D Card Flip)")
        self.chk_enable_dd_flip.setChecked(bool(anim_data.get("enable_dd_flip", True)))
        zoom_layout.addRow("Daily Double 3D Flip:", self.chk_enable_dd_flip)

        self.spin_flip_duration = QSpinBox()
        self.spin_flip_duration.setRange(300, 2500)
        self.spin_flip_duration.setSingleStep(50)
        self.spin_flip_duration.setValue(int(anim_data.get("flip_duration_ms", 900)))
        self.spin_flip_duration.setSuffix(" ms")
        zoom_layout.addRow("3D Flip Duration:", self.spin_flip_duration)

        layout.addWidget(zoom_box)

        # 2. Standby Screen + Intro Video Merge + Outro Music
        intro_box = QGroupBox("2. NỀN CHỜ QUẢNG CÁO + VIDEO INTRO MERGE + NHẠC OUTRO (STANDBY, INTRO & OUTRO)")
        intro_layout = QFormLayout(intro_box)
        intro_layout.setSpacing(12)

        lbl_intro_note = QLabel(
            "• Intro Video: Plays video on TV Display, then after your chosen time (seconds) smoothly cross-fades/merges into the Static Standby Wallpaper.\n"
            "• Outro Music: Displays the Static Standby Wallpaper on TV and plays the Outro audio track."
        )
        lbl_intro_note.setWordWrap(True)
        lbl_intro_note.setStyleSheet("color: #8b949e; font-style: italic;")
        intro_layout.addRow(lbl_intro_note)

        # Static Standby Wallpaper
        row_sb = QHBoxLayout()
        self.edit_sb_img = QLineEdit(sb_img)
        btn_b_sb = QPushButton("Browse Image...")
        btn_b_sb.clicked.connect(lambda: self._browse_image(self.edit_sb_img))
        row_sb.addWidget(self.edit_sb_img, 1)
        row_sb.addWidget(btn_b_sb)
        intro_layout.addRow("Static Standby Wallpaper (Hình nền chờ tĩnh):", row_sb)

        # Intro Video File
        row_vid = QHBoxLayout()
        self.edit_intro_video = QLineEdit(anim_data.get("intro_video_path", ""))
        btn_b_vid = QPushButton("Browse Video...")
        btn_b_vid.clicked.connect(lambda: self._browse_video(self.edit_intro_video))
        btn_clr_vid = QPushButton("Clear")
        btn_clr_vid.clicked.connect(lambda: self.edit_intro_video.setText(""))
        row_vid.addWidget(self.edit_intro_video, 1)
        row_vid.addWidget(btn_b_vid)
        row_vid.addWidget(btn_clr_vid)
        intro_layout.addRow("Intro Video File (.mp4/.mov/.mkv):", row_vid)

        # Merge Delay (seconds)
        self.spin_intro_merge_sec = QDoubleSpinBox()
        self.spin_intro_merge_sec.setRange(0.0, 600.0)
        self.spin_intro_merge_sec.setSingleStep(0.5)
        self.spin_intro_merge_sec.setDecimals(1)
        self.spin_intro_merge_sec.setValue(float(anim_data.get("intro_merge_seconds", 5.0)))
        self.spin_intro_merge_sec.setSuffix(" s (0 = đợi hết video mới merge)")
        intro_layout.addRow("Merge into Standby Image after (Thời gian chạy video):", self.spin_intro_merge_sec)

        # Crossfade Duration (ms)
        self.spin_intro_fade_ms = QSpinBox()
        self.spin_intro_fade_ms.setRange(200, 5000)
        self.spin_intro_fade_ms.setSingleStep(100)
        self.spin_intro_fade_ms.setValue(int(anim_data.get("intro_fade_duration_ms", 1500)))
        self.spin_intro_fade_ms.setSuffix(" ms")
        intro_layout.addRow("Cross-fade Merge Duration (Độ mượt khi hoà trộn):", self.spin_intro_fade_ms)

        # Outro Music File
        outro_val = anim_data.get("outro_music_path") or self.theme.get("sounds", {}).get("outro_music", "")
        row_outro = QHBoxLayout()
        self.edit_outro_music = QLineEdit(outro_val)
        btn_b_outro = QPushButton("Browse Audio...")
        btn_b_outro.clicked.connect(lambda: self._browse_sound(self.edit_outro_music))
        btn_clr_outro = QPushButton("Clear")
        btn_clr_outro.clicked.connect(lambda: self.edit_outro_music.setText(""))
        row_outro.addWidget(self.edit_outro_music, 1)
        row_outro.addWidget(btn_b_outro)
        row_outro.addWidget(btn_clr_outro)
        intro_layout.addRow("Outro Music (Nhạc Outro trên nền tĩnh):", row_outro)

        # Live Action Buttons
        act_row = QHBoxLayout()
        btn_run_intro = QPushButton("▶ Chạy Video Intro -> Merge Nền Chờ trên TV")
        btn_run_intro.setStyleSheet("background-color: #1f6feb; color: white; font-weight: bold; padding: 8px 14px;")
        btn_run_intro.clicked.connect(self._on_trigger_intro_video_now)

        btn_run_outro = QPushButton("🎵 Chạy Nhạc Outro trên Nền Chờ Tĩnh")
        btn_run_outro.setStyleSheet("background-color: #8957e5; color: white; font-weight: bold; padding: 8px 14px;")
        btn_run_outro.clicked.connect(self._on_trigger_outro_music_now)

        btn_stop_media = QPushButton("⏹ Dừng Media")
        btn_stop_media.setStyleSheet("background-color: #da3633; color: white; font-weight: bold; padding: 8px 14px;")
        btn_stop_media.clicked.connect(self._on_stop_standby_media)

        act_row.addWidget(btn_run_intro)
        act_row.addWidget(btn_run_outro)
        act_row.addWidget(btn_stop_media)
        intro_layout.addRow("Live Broadcast Trigger:", act_row)

        layout.addWidget(intro_box)
        layout.addStretch()

        scroll.setWidget(container)
        v = QVBoxLayout(widget)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(scroll)
        return widget

    def _on_trigger_intro_video_now(self):
        self._collect_ui_to_theme()
        event_bus.update_theme_config.emit(self.theme)
        vid = self.edit_intro_video.text().strip()
        if not vid or not os.path.isfile(vid):
            QMessageBox.warning(self, "Missing Intro Video", "Please select a valid Intro Video file first!")
            return
        event_bus.trigger_standby_intro_video.emit({
            "video_path": vid,
            "merge_seconds": self.spin_intro_merge_sec.value(),
            "fade_duration_ms": self.spin_intro_fade_ms.value(),
        })

    def _on_trigger_outro_music_now(self):
        self._collect_ui_to_theme()
        event_bus.update_theme_config.emit(self.theme)
        outro = self.edit_outro_music.text().strip()
        if not outro or not os.path.isfile(outro):
            QMessageBox.warning(self, "Missing Outro Music", "Please select a valid Outro Music audio file first!")
            return
        event_bus.trigger_standby_outro_music.emit(outro)

    def _on_stop_standby_media(self):
        self.audio_manager.stop_all()
        event_bus.stop_standby_media.emit()

    # =========================================================================
    # TAB 4: BROADCAST SOUND MANAGER (REQUIREMENT #7)
    # =========================================================================

    def _build_sound_tab(self):
        widget = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # Notice: Top folder-level selector removed per Requirement #7!
        # Final Jeopardy Wager Waiting Music removed per Requirement #7!
        event_box = QGroupBox("INDIVIDUAL EVENT AUDIO BINDINGS (TUỲ CHỌN ÂM THANH TỪNG MỤC RIÊNG BIỆT)")
        event_layout = QFormLayout(event_box)
        event_layout.setSpacing(10)

        lbl_snd_note = QLabel(
            "Configure each sound effect individually. Leave blank or click 'Clear' to keep an event completely silent."
        )
        lbl_snd_note.setWordWrap(True)
        lbl_snd_note.setStyleSheet("color: #8b949e; font-style: italic; margin-bottom: 6px;")
        event_layout.addRow(lbl_snd_note)

        sound_labels = {
            "board_fill": "1. Board Opening Fanfare (Lật mở 30 ô điểm):",
            "round_category_intro": "2. Round 1 & 2 Category Reveal (Giới thiệu chủ đề đầu vòng 1 & 2):",
            "daily_double": "3. Daily Double Reveal Fanfare (Hiệu ứng mở Daily Double):",
            "timeout": "4. Timeout 5s / Lockout Tone (Hết giờ trả lời 5s):",
            "correct": "5. Correct Response Chime (Trả lời Đúng):",
            "wrong": "6. Incorrect Response Tone (Trả lời Sai):",
            "final_category_intro": "7. Final Jeopardy Category Reveal (Giới thiệu chủ đề Vòng Cuối):",
            "think_30s": "8. Final Jeopardy 30s Think Music (Nhạc suy nghĩ 30s Vòng Cuối):",
            "outro_music": "9. Broadcast Outro Music (Nhạc kết thúc trên nền chờ tĩnh):",
        }

        sounds_dict = self.theme.get("sounds", {})
        self.sound_edits: Dict[str, QLineEdit] = {}

        for k, lbl in sound_labels.items():
            row = QHBoxLayout()
            val = sounds_dict.get(k, "")
            if k == "final_category_intro" and not val:
                val = sounds_dict.get("category_intro", "")
            edit = QLineEdit(val)
            self.sound_edits[k] = edit

            btn_b = QPushButton("Browse...")
            btn_b.clicked.connect(lambda chk=False, e=edit, key=k: self._browse_sound_key(e, key))

            btn_clr = QPushButton("Clear")
            btn_clr.clicked.connect(lambda chk=False, e=edit, key=k: self._clear_sound_key(e, key))

            btn_play = QPushButton("Play")
            btn_play.setStyleSheet("background-color: #238636; color: white; padding: 4px 10px;")
            btn_play.clicked.connect(lambda chk=False, e=edit: self._preview_sound(e.text().strip()))

            btn_stop = QPushButton("Stop")
            btn_stop.setStyleSheet("background-color: #da3633; color: white; padding: 4px 10px;")
            btn_stop.clicked.connect(lambda: self.audio_manager.stop_all())

            row.addWidget(edit, 1)
            row.addWidget(btn_b)
            row.addWidget(btn_clr)
            row.addWidget(btn_play)
            row.addWidget(btn_stop)
            event_layout.addRow(lbl, row)

        # Keep outro_music synced between Tab 3 and Tab 4
        self.edit_outro_music.textChanged.connect(
            lambda txt: self.sound_edits["outro_music"].setText(txt)
            if self.sound_edits["outro_music"].text() != txt else None
        )
        self.sound_edits["outro_music"].textChanged.connect(
            lambda txt: self.edit_outro_music.setText(txt)
            if self.edit_outro_music.text() != txt else None
        )

        layout.addWidget(event_box)
        layout.addStretch()

        scroll.setWidget(container)
        v = QVBoxLayout(widget)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(scroll)
        return widget

    def _browse_image(self, target_line_edit: QLineEdit):
        f, _ = QFileDialog.getOpenFileName(
            self, "Select Graphic Asset", "", "Image Files (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)"
        )
        if f:
            target_line_edit.setText(f)

    def _browse_video(self, target_line_edit: QLineEdit):
        f, _ = QFileDialog.getOpenFileName(
            self, "Select Intro Video File", "", "Video Files (*.mp4 *.mov *.mkv *.avi *.webm *.wmv);;All Files (*)"
        )
        if f:
            target_line_edit.setText(f)

    def _browse_sound(self, target_line_edit: QLineEdit):
        f, _ = QFileDialog.getOpenFileName(
            self, "Select Audio File", "", "Audio Files (*.wav *.mp3 *.m4a *.aac *.ogg *.flac);;All Files (*)"
        )
        if f:
            target_line_edit.setText(f)

    def _browse_sound_key(self, target_line_edit: QLineEdit, key: str):
        self._browse_sound(target_line_edit)

    def _clear_sound_key(self, target_line_edit: QLineEdit, key: str):
        target_line_edit.setText("")
        self.audio_manager.set_sound_file(key, "")

    def _preview_sound(self, file_path: str):
        if file_path and os.path.isfile(file_path):
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

    def _on_export_zip(self):
        self._collect_ui_to_theme()
        ThemeConfigManager.save_theme_xml(self.theme)

        f, _ = QFileDialog.getSaveFileName(
            self, "Export Theme Package (.zip)", "Jeopardy_Broadcast_Theme.zip", "Zip Archive (*.zip);;All Files (*)"
        )
        if f:
            try:
                xml_path = str(PROJECT_ROOT / "ui" / "assets" / "theme.xml")
                assets_dir = str(PROJECT_ROOT / "ui" / "assets")
                ThemePackageEngine.export_theme_to_zip(xml_path, assets_dir, f)
                QMessageBox.information(self, "Export Successful", f"Theme package exported successfully:\n{f}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", str(e))

    def _on_import_zip(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Import Theme Package (.zip)", "", "Zip Archive (*.zip);;All Files (*)"
        )
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

        # Shared Typography (Section 1 of Font Tab: Clue, Answer & Category Header)
        shared_family = self.font_combo_shared.currentFont().family()
        shared_bold = self.chk_shared_bold.isChecked()
        shared_color = self.shared_font_color
        shared_mode = self.combo_shared_font_mode.currentData()
        cat_size = self.spin_cat_font_size.value()
        clue_size = self.spin_clue_font_size.value()
        ans_size = self.spin_answer_font_size.value()

        # Category Headers
        ch = self.theme.setdefault("category_headers", {})
        ch["unrevealed_image"] = self.edit_cat_unrev.text().strip()
        ch["revealed_image"] = self.edit_cat_rev.text().strip()
        ch["fit_mode"] = self.combo_cat_fit.currentText()
        ch["auto_crop_logo"] = self.chk_auto_crop_logo.isChecked()
        ch["font"] = {
            "family": shared_family,
            "size": cat_size,
            "bold": shared_bold,
            "color": shared_color,
            "mode": shared_mode,
        }

        # Point Grid (Section 2 of Font Tab: Point Values 200, 400...)
        pg = self.theme.setdefault("point_grid", {})
        pg["use_image"] = self.combo_pt_mode.currentData()
        pg["tile_image"] = self.edit_tile_img.text().strip()
        pg["solid_color"] = self.pt_solid_color
        pg["fit_mode"] = self.combo_pt_fit.currentText()
        pg["font"] = {
            "family": self.font_combo_points.currentFont().family(),
            "size": self.spin_point_font_size.value(),
            "bold": self.chk_points_bold.isChecked(),
            "color": self.point_font_color,
            "mode": self.combo_point_font_mode.currentData(),
        }

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

        cs["font"] = {
            "family": shared_family,
            "size": clue_size,
            "answer_size": ans_size,
            "header_size": cat_size,
            "bold": shared_bold,
            "color": shared_color,
            "mode": shared_mode,
        }
        sh = cs.setdefault("shadow", {})
        sh["blur"] = self.spin_sh_blur.value()
        sh["dx"] = self.spin_sh_dx.value()
        sh["dy"] = self.spin_sh_dy.value()

        # Standby Screen
        sb = self.theme.setdefault("standby_screen", {})
        sb["image_path"] = self.edit_sb_img.text().strip()

        # Visual FX
        vfx = self.theme.setdefault("visual_fx", {})
        vfx["daily_double_splash"] = self.edit_dd_splash.text().strip()
        vfx["final_logo_splash"] = self.edit_final_logo.text().strip()

        # Animations & Intro/Outro
        anim = self.theme.setdefault("animations", {})
        anim["enable_point_zoom"] = self.chk_enable_point_zoom.isChecked()
        anim["zoom_duration_ms"] = self.spin_zoom_duration.value()
        anim["enable_dd_flip"] = self.chk_enable_dd_flip.isChecked()
        anim["flip_duration_ms"] = self.spin_flip_duration.value()
        anim["intro_video_path"] = self.edit_intro_video.text().strip()
        anim["intro_merge_seconds"] = self.spin_intro_merge_sec.value()
        anim["intro_fade_duration_ms"] = self.spin_intro_fade_ms.value()
        anim["outro_music_path"] = self.edit_outro_music.text().strip()

        # Sounds (Individual bindings only, no wager_music)
        sounds = {}
        for k, e in self.sound_edits.items():
            path_val = e.text().strip()
            sounds[k] = path_val
            self.audio_manager.set_sound_file(k, path_val)
        if anim["outro_music_path"] and not sounds.get("outro_music"):
            sounds["outro_music"] = anim["outro_music_path"]
            self.audio_manager.set_sound_file("outro_music", anim["outro_music_path"])
        self.theme["sounds"] = sounds

    def _on_apply(self):
        """Immediately stops all audio, writes XML, emits updates, and accepts dialog."""
        self.audio_manager.stop_all()
        self._collect_ui_to_theme()

        ThemeConfigManager.save_theme_xml(self.theme)

        event_bus.set_performance_profile.emit(self.theme.get("performance_profile", "ultra"))
        event_bus.reload_theme_config.emit()
        event_bus.update_theme_config.emit(self.theme)
        self.accept()

    def _on_cancel(self):
        self.audio_manager.stop_all()
        self.reject()


__all__ = ["TVBezelPreviewWidget", "SettingsDialog"]
