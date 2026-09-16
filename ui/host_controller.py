"""Open-J: Host Controller Dashboard.
Main control console for Jeopardy! game show host and studio operator.
Built with PySide6, SQLite, XML, and decoupled event-bus architecture.
Adheres strictly to official Jeopardy! rules (Season 40 & 41 standard).
"""

import os
import sys
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

# Ensure project root is in sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QFont, QColor, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
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
)

from core.event_bus import event_bus
from core.score_core import ScoreEngine
from core.question_core import QuestionEngine
from ui.audio_manager import AudioManager
from ui.theme_manager import ThemePackageEngine, ThemeConfigManager, AssetRenderer


# =============================================================================
# STYLESHEET CONSTANTS
# =============================================================================

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


# =============================================================================
# WIDGET: BEZEL PREVIEW
# =============================================================================

class TVBezelPreviewWidget(QWidget):
    """Mô phỏng trực quan ma trận màn hình ghép 6x5 góc vuông."""

    def __init__(self, bezel_width=8, bezel_color="#000000", parent=None):
        super().__init__(parent)
        self.bezel_width = bezel_width
        self.bezel_color = QColor(bezel_color)
        self.setMinimumSize(220, 140)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_bezel(self, width, color):
        self.bezel_width = width
        self.bezel_color = QColor(color)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        painter.fillRect(rect, self.bezel_color)

        cols, rows = 6, 5
        bw = max(1, int(self.bezel_width * min(rect.width(), rect.height()) / 400))
        avail_w = rect.width() - (cols + 1) * bw
        avail_h = rect.height() - (rows + 1) * bw

        if avail_w <= 0 or avail_h <= 0:
            return

        cell_w = avail_w / cols
        cell_h = avail_h / rows
        screen_blue = QColor("#060CE9")
        header_blue = QColor("#000a8a")

        for r in range(rows):
            for c in range(cols):
                x = bw + c * (cell_w + bw)
                y = bw + r * (cell_h + bw)
                cell_color = header_blue if r == 0 else screen_blue
                painter.fillRect(int(x), int(y), int(cell_w), int(cell_h), cell_color)
                painter.setPen(QColor(255, 255, 255, 30))
                painter.drawRect(int(x), int(y), int(cell_w) - 1, int(cell_h) - 1)


# =============================================================================
# MODAL: SETTINGS & SOUND DIALOG
# =============================================================================

class SettingsDialog(QDialog):
    """Hộp thoại cấu hình Studio: Theme XML, Thẻ câu hỏi, Logo, Bezel, Fit Mode, Sound Manager và Zip Packager."""

    def __init__(self, theme_data, audio_manager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙ Cài đặt Hệ thống, Tùy biến Đồ họa & Quản lý Gói Theme")
        self.resize(880, 680)
        self.setStyleSheet(APP_STYLE)

        # Nạp theme từ XML hoặc dữ liệu hiện có
        loaded = ThemeConfigManager.load_theme_xml()
        self.theme = dict(loaded)
        if isinstance(theme_data, dict):
            # Cập nhật các trường nếu có
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

        self.tab_widget.addTab(self.tab1, "1. Giao diện, Đồ họa & Gói Theme (Visuals & Theme Packager)")
        self.tab_widget.addTab(self.tab2, "2. Quản lý Âm thanh Phát sóng (Sound Manager)")
        layout.addWidget(self.tab_widget)

        btn_box = QHBoxLayout()
        btn_apply = QPushButton("💾 Lưu cài đặt & Đóng")
        btn_apply.setStyleSheet("background-color: #238636; color: white; font-weight: bold; font-size: 14px; padding: 10px 22px;")
        btn_apply.clicked.connect(self._on_apply)

        btn_close = QPushButton("Đóng")
        btn_close.clicked.connect(self._on_cancel)

        btn_box.addStretch()
        btn_box.addWidget(btn_apply)
        btn_box.addWidget(btn_close)
        layout.addLayout(btn_box)

    def _build_theme_tab(self):
        widget = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # 1. Category Headers (6 ô chủ đề)
        cat_box = QGroupBox("1. 6 Ô CHỦ ĐỀ TRÊN CÙNG (CATEGORY HEADERS)")
        cat_layout = QFormLayout(cat_box)

        ch_data = self.theme.get("category_headers", {})

        # Unrevealed image (Logo địa cầu)
        self.edit_cat_unrev = QLineEdit(ch_data.get("unrevealed_image", ""))
        btn_unrev = QPushButton("Duyệt ảnh Logo...")
        btn_unrev.clicked.connect(lambda: self._browse_file(self.edit_cat_unrev, "Ảnh Logo địa cầu chưa mở"))
        unrev_row = QHBoxLayout()
        unrev_row.addWidget(self.edit_cat_unrev, 1)
        unrev_row.addWidget(btn_unrev)

        # Revealed image (Nền chủ đề đã mở)
        self.edit_cat_rev = QLineEdit(ch_data.get("revealed_image", ""))
        btn_rev = QPushButton("Duyệt ảnh nền...")
        btn_rev.clicked.connect(lambda: self._browse_file(self.edit_cat_rev, "Ảnh nền ô chủ đề đã mở"))
        rev_row = QHBoxLayout()
        rev_row.addWidget(self.edit_cat_rev, 1)
        rev_row.addWidget(btn_rev)

        # Fit mode
        self.combo_cat_fit = QComboBox()
        self.combo_cat_fit.addItems(["zoom (Zoom Phủ Kín - Aspect Ratio Crop)", "tile (Lặp Họa Tiết - Pattern Repeat)"])
        if ch_data.get("fit_mode") == "tile":
            self.combo_cat_fit.setCurrentIndex(1)
        else:
            self.combo_cat_fit.setCurrentIndex(0)

        cat_layout.addRow("Ảnh trạng thái CHƯA MỞ (Unrevealed Logo):", unrev_row)
        cat_layout.addRow("Ảnh trạng thái ĐÃ MỞ (Revealed Background):", rev_row)
        cat_layout.addRow("Tỉ lệ căn chỉnh ảnh (Fit Mode):", self.combo_cat_fit)
        layout.addWidget(cat_box)

        # 2. Point Grid (30 ô điểm số)
        point_box = QGroupBox("2. 30 Ô ĐIỂM SỐ MA TRẬN (POINT GRID: 200 - 1000)")
        pt_layout = QFormLayout(point_box)

        pg_data = self.theme.get("point_grid", {})

        self.chk_pt_use_image = QCheckBox(" Dùng ảnh/texture nền (Bỏ chọn nếu muốn dùng Màu đặc)")
        self.chk_pt_use_image.setChecked(bool(pg_data.get("use_image", True)))
        self.chk_pt_use_image.setStyleSheet("color: #58a6ff; font-weight: bold;")

        self.btn_pt_color = QPushButton("Chọn màu đặc ô điểm...")
        pt_col = pg_data.get("solid_color", "#060CE9")
        self.btn_pt_color.setStyleSheet(f"background-color: {pt_col}; color: white; font-weight: bold;")
        self.btn_pt_color.clicked.connect(self._choose_point_color)

        self.edit_pt_tile = QLineEdit(pg_data.get("tile_image", ""))
        btn_pt_tile = QPushButton("Duyệt ảnh Texture...")
        btn_pt_tile.clicked.connect(lambda: self._browse_file(self.edit_pt_tile, "Ảnh texture ô điểm"))
        pt_tile_row = QHBoxLayout()
        pt_tile_row.addWidget(self.edit_pt_tile, 1)
        pt_tile_row.addWidget(btn_pt_tile)

        self.combo_pt_fit = QComboBox()
        self.combo_pt_fit.addItems(["zoom (Zoom Phủ Kín - Mặc định)", "tile (Lặp Họa Tiết)"])
        if pg_data.get("fit_mode") == "tile":
            self.combo_pt_fit.setCurrentIndex(1)
        else:
            self.combo_pt_fit.setCurrentIndex(0)

        pt_layout.addRow("Chế độ nền ô điểm:", self.chk_pt_use_image)
        pt_layout.addRow("Màu đặc (khi không dùng ảnh):", self.btn_pt_color)
        pt_layout.addRow("Ảnh Texture nền ô điểm:", pt_tile_row)
        pt_layout.addRow("Tỉ lệ căn chỉnh ảnh ô điểm:", self.combo_pt_fit)
        layout.addWidget(point_box)

        # 3. Clue Screen (Thẻ câu hỏi thường & Final)
        clue_box = QGroupBox("3. THẺ CÂU HỎI (CLUE CARDS) & FONT CHỮ DÙNG CHUNG")
        cl_layout = QFormLayout(clue_box)

        cs_data = self.theme.get("clue_screen", {})
        std_card = cs_data.get("standard_card", {})
        fin_card = cs_data.get("final_card", {})

        # Standard Card (Blue)
        self.chk_std_img = QCheckBox(" Dùng ảnh texture nền (Vòng 1 & 2)")
        self.chk_std_img.setChecked(bool(std_card.get("use_image", True)))
        self.chk_std_img.setStyleSheet("color: #58a6ff; font-weight: bold;")

        self.btn_std_color = QPushButton("Màu thẻ Vòng 1 & 2...")
        std_col = std_card.get("color", "#060CE9")
        self.btn_std_color.setStyleSheet(f"background-color: {std_col}; color: white; font-weight: bold;")
        self.btn_std_color.clicked.connect(self._choose_std_card_color)

        self.edit_std_img = QLineEdit(std_card.get("image_path", ""))
        btn_std_img = QPushButton("Duyệt texture...")
        btn_std_img.clicked.connect(lambda: self._browse_file(self.edit_std_img, "Ảnh texture thẻ câu hỏi Vòng 1 & 2"))
        std_row = QHBoxLayout()
        std_row.addWidget(self.edit_std_img, 1)
        std_row.addWidget(btn_std_img)

        # Final Card (Red)
        self.chk_fin_img = QCheckBox(" Dùng ảnh texture nền thứ 2 (Vòng 3 Final Jeopardy)")
        self.chk_fin_img.setChecked(bool(fin_card.get("use_image", True)))
        self.chk_fin_img.setStyleSheet("color: #e11d48; font-weight: bold;")

        self.btn_fin_color = QPushButton("Màu thẻ Final Jeopardy...")
        fin_col = fin_card.get("color", "#8B0000")
        self.btn_fin_color.setStyleSheet(f"background-color: {fin_col}; color: white; font-weight: bold;")
        self.btn_fin_color.clicked.connect(self._choose_fin_card_color)

        self.edit_fin_img = QLineEdit(fin_card.get("image_path", ""))
        btn_fin_img = QPushButton("Duyệt texture...")
        btn_fin_img.clicked.connect(lambda: self._browse_file(self.edit_fin_img, "Ảnh texture thẻ Final Jeopardy"))
        fin_row = QHBoxLayout()
        fin_row.addWidget(self.edit_fin_img, 1)
        fin_row.addWidget(btn_fin_img)

        # Shared Font for Clue and Category Headers
        cf_data = cs_data.get("font", {"family": "Georgia", "size": 48, "bold": True})
        self.shared_font = dict(cf_data)

        self.btn_shared_font = QPushButton("Chọn Font câu hỏi & Chủ đề...")
        self.btn_shared_font.clicked.connect(self._choose_shared_font)
        self.lbl_shared_font = QLabel(f"{self.shared_font.get('family', 'Georgia')}, {self.shared_font.get('size', 48)}pt, {'Bold' if self.shared_font.get('bold') else 'Normal'}")
        self.lbl_shared_font.setStyleSheet("color: #58a6ff; font-weight: bold; background-color: #0d1117; padding: 6px; border-radius: 4px;")
        f_row = QHBoxLayout()
        f_row.addWidget(self.btn_shared_font)
        f_row.addWidget(self.lbl_shared_font, 1)

        cl_layout.addRow("Nền thẻ câu hỏi Vòng 1 & 2:", self.chk_std_img)
        cl_layout.addRow("Màu thẻ Vòng 1 & 2:", self.btn_std_color)
        cl_layout.addRow("Ảnh texture thẻ Vòng 1 & 2 (Xanh):", std_row)
        cl_layout.addRow("Nền thẻ câu hỏi Final (Nền 2):", self.chk_fin_img)
        cl_layout.addRow("Màu thẻ Final Jeopardy:", self.btn_fin_color)
        cl_layout.addRow("Ảnh texture thẻ Final (Đỏ):", fin_row)
        cl_layout.addRow("Font dùng chung (Clue & Category):", f_row)
        layout.addWidget(clue_box)

        # 4. Visual FX (Daily Double Splash & Final Logo Splash)
        vfx_box = QGroupBox("4. HIỆU ỨNG DAILY DOUBLE & CHUYỂN CẢNH (VISUAL FX)")
        vfx_layout = QFormLayout(vfx_box)

        vfx_data = self.theme.get("visual_fx", {})

        self.edit_dd_splash = QLineEdit(vfx_data.get("daily_double_splash", ""))
        btn_dd_splash = QPushButton("Duyệt ảnh Daily Double...")
        btn_dd_splash.clicked.connect(lambda: self._browse_file(self.edit_dd_splash, "Ảnh đồ họa Daily Double"))
        dd_row = QHBoxLayout()
        dd_row.addWidget(self.edit_dd_splash, 1)
        dd_row.addWidget(btn_dd_splash)

        self.edit_final_logo = QLineEdit(vfx_data.get("final_logo_splash", ""))
        btn_final_logo = QPushButton("Duyệt ảnh Logo Final...")
        btn_final_logo.clicked.connect(lambda: self._browse_file(self.edit_final_logo, "Ảnh Logo Final Jeopardy"))
        fl_row = QHBoxLayout()
        fl_row.addWidget(self.edit_final_logo, 1)
        fl_row.addWidget(btn_final_logo)

        vfx_layout.addRow("Ảnh đồ họa Daily Double Splash:", dd_row)
        vfx_layout.addRow("Ảnh đồ họa Logo Final Jeopardy:", fl_row)
        layout.addWidget(vfx_box)

        # 5. Standby Screen (Màn hình chờ Wallpaper)
        standby_box = QGroupBox("5. MÀN HÌNH CHỜ (STANDBY SCREEN WALLPAPER)")
        sb_layout = QFormLayout(standby_box)
        sb_data = self.theme.get("standby_screen", {})

        self.edit_standby_img = QLineEdit(sb_data.get("image_path", ""))
        btn_standby = QPushButton("Duyệt ảnh Standby...")
        btn_standby.clicked.connect(lambda: self._browse_file(self.edit_standby_img, "Ảnh màn hình chờ (Wallpaper)"))
        sb_row = QHBoxLayout()
        sb_row.addWidget(self.edit_standby_img, 1)
        sb_row.addWidget(btn_standby)
        sb_layout.addRow("Ảnh nền Standby (Full-bleed & Mosaic 36 ô):", sb_row)
        layout.addWidget(standby_box)

        # 6. Bezel Simulation
        bezel_box = QGroupBox("6. MÔ PHỎNG VIỀN GHÉP (BEZEL SIMULATION - VUÔNG CẠNH 100%)")
        b_layout = QHBoxLayout(bezel_box)
        ctrl_frame = QFrame()
        cf_layout = QFormLayout(ctrl_frame)

        self.bezel_spin = QSpinBox()
        self.bezel_spin.setRange(0, 24)
        self.bezel_spin.setValue(int(self.theme.get("bezel_width", 8)))
        self.bezel_spin.setSuffix(" px")
        self.bezel_spin.valueChanged.connect(self._on_bezel_changed)

        self.btn_bezel_color = QPushButton("Chọn màu viền...")
        self.btn_bezel_color.setStyleSheet(f"background-color: {self.theme.get('bezel_color', '#000000')}; color: white;")
        self.btn_bezel_color.clicked.connect(self._choose_bezel_color)

        cf_layout.addRow("Độ dày viền khe:", self.bezel_spin)
        cf_layout.addRow("Màu khe viền ghép:", self.btn_bezel_color)
        b_layout.addWidget(ctrl_frame, 1)

        self.bezel_preview = TVBezelPreviewWidget(int(self.theme.get("bezel_width", 8)), self.theme.get("bezel_color", "#000000"))
        b_layout.addWidget(self.bezel_preview, 1)
        layout.addWidget(bezel_box)

        # 6. Theme Package Manager (Zip export / import)
        zip_box = QGroupBox("7. ĐÓNG GÓI GÓI THEME (THEME PACKAGE MANAGER)")
        zb_layout = QHBoxLayout(zip_box)

        btn_export_zip = QPushButton("📦 Xuất toàn bộ Theme ra file Zip...")
        btn_export_zip.setStyleSheet("background-color: #1f6feb; color: white; font-weight: bold; padding: 10px;")
        btn_export_zip.clicked.connect(self._export_theme_zip)

        btn_import_zip = QPushButton("📥 Nạp Theme từ file Zip...")
        btn_import_zip.setStyleSheet("background-color: #8957e5; color: white; font-weight: bold; padding: 10px;")
        btn_import_zip.clicked.connect(self._import_theme_zip)

        zb_layout.addWidget(btn_export_zip)
        zb_layout.addWidget(btn_import_zip)
        layout.addWidget(zip_box)

        scroll.setWidget(container)
        outer = QVBoxLayout(widget)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        return widget

    def _build_sound_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        dir_box = QGroupBox("THƯ MỤC ÂM THANH STUDIO")
        db_layout = QHBoxLayout(dir_box)
        self.dir_edit = QLineEdit(str(self.audio_manager.sounds_dir))
        btn_dir = QPushButton("Duyệt thư mục...")
        btn_dir.clicked.connect(self._on_browse_sounds_dir)
        db_layout.addWidget(self.dir_edit, 1)
        db_layout.addWidget(btn_dir)
        layout.addWidget(dir_box)

        event_box = QGroupBox("GÁN TẬP TIN ÂM THANH THEO SỰ KIỆN (KHÔNG CHẠY ÂM DEMO)")
        eb_layout = QVBoxLayout(event_box)

        events_def = [
            ("fill", "Board Fill (Lật ngẫu nhiên 30 ô / Coin drop)"),
            ("category_intro", "Category Reveal Intro (Giới thiệu chủ đề)"),
            ("daily_double", "Daily Double Fanfare / Laser"),
            ("think_music", "Think Music (Nhạc suy nghĩ 30s Final)"),
            ("time_out", "Time Out (Hết giờ suy nghĩ / Buzzer)"),
            ("correct", "Correct (Trả lời đúng / Chime)"),
            ("wrong", "Wrong / Incorrect (Trả lời sai / Buzzer)"),
        ]

        sounds_dict = self.theme.get("sounds", {})
        self.sound_edits = {}
        for key, title in events_def:
            row = QHBoxLayout()
            lbl = QLabel(f"• {title} [{key}]:")
            lbl.setFixedWidth(290)

            cur_file = sounds_dict.get(key, "")
            if not cur_file:
                cur_file = self.audio_manager.sound_files.get(key, "")

            edit = QLineEdit(cur_file)
            self.sound_edits[key] = edit

            btn_browse = QPushButton("Chọn...")
            btn_browse.clicked.connect(lambda chk=False, k=key, e=edit: self._on_browse_sound_file(k, e))

            btn_test = QPushButton("▶ Nghe thử")
            btn_test.setStyleSheet("color: #3fb950; font-weight: bold;")
            btn_test.clicked.connect(lambda chk=False, k=key, e=edit: self._test_sound_preview(k, e))

            row.addWidget(lbl)
            row.addWidget(edit, 1)
            row.addWidget(btn_browse)
            row.addWidget(btn_test)
            eb_layout.addLayout(row)

        layout.addWidget(event_box)
        layout.addStretch()
        return widget

    def _browse_file(self, line_edit: QLineEdit, dialog_title: str):
        f, _ = QFileDialog.getOpenFileName(self, dialog_title, "", "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)")
        if f:
            line_edit.setText(f)

    def _choose_point_color(self):
        c = QColorDialog.getColor(QColor(self.theme.get("point_grid", {}).get("solid_color", "#060CE9")), self, "Chọn màu đặc ô điểm số")
        if c.isValid():
            self.theme.setdefault("point_grid", {})["solid_color"] = c.name()
            self.btn_pt_color.setStyleSheet(f"background-color: {c.name()}; color: white; font-weight: bold;")

    def _choose_std_card_color(self):
        c = QColorDialog.getColor(QColor(self.theme.get("clue_screen", {}).get("standard_card", {}).get("color", "#060CE9")), self, "Chọn màu thẻ câu hỏi Vòng 1 & 2")
        if c.isValid():
            self.theme.setdefault("clue_screen", {}).setdefault("standard_card", {})["color"] = c.name()
            self.btn_std_color.setStyleSheet(f"background-color: {c.name()}; color: white; font-weight: bold;")

    def _choose_fin_card_color(self):
        c = QColorDialog.getColor(QColor(self.theme.get("clue_screen", {}).get("final_card", {}).get("color", "#8B0000")), self, "Chọn màu thẻ Final Jeopardy")
        if c.isValid():
            self.theme.setdefault("clue_screen", {}).setdefault("final_card", {})["color"] = c.name()
            self.btn_fin_color.setStyleSheet(f"background-color: {c.name()}; color: white; font-weight: bold;")

    def _choose_shared_font(self):
        curr = self.shared_font
        qf = QFont(curr.get("family", "Georgia"), curr.get("size", 48))
        qf.setBold(bool(curr.get("bold", True)))
        ok, font = QFontDialog.getFont(qf, self, "Chọn Font dùng chung cho Manh Mối & Tiêu Đề Chủ Đề")
        if ok:
            self.shared_font = {
                "family": font.family(),
                "size": font.pointSize(),
                "bold": font.bold(),
                "color": "#FFFFFF"
            }
            desc = f"{font.family()}, {font.pointSize()}pt, {'Bold' if font.bold() else 'Normal'}"
            self.lbl_shared_font.setText(desc)

    def _choose_bezel_color(self):
        c = QColorDialog.getColor(QColor(self.theme.get("bezel_color", "#000000")), self, "Chọn màu viền Bezel")
        if c.isValid():
            hex_c = c.name()
            self.theme["bezel_color"] = hex_c
            self.btn_bezel_color.setStyleSheet(f"background-color: {hex_c}; color: white;")
            self.bezel_preview.set_bezel(self.bezel_spin.value(), hex_c)

    def _on_bezel_changed(self):
        w = self.bezel_spin.value()
        c = self.theme.get("bezel_color", "#000000")
        self.theme["bezel_width"] = w
        self.bezel_preview.set_bezel(w, c)

    def _on_browse_sounds_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Chọn thư mục âm thanh", self.dir_edit.text())
        if d:
            self.dir_edit.setText(d)
            self.audio_manager.sounds_dir = Path(d)

    def _on_browse_sound_file(self, key, edit):
        f, _ = QFileDialog.getOpenFileName(self, f"Chọn file âm thanh cho {key}", self.dir_edit.text(), "Audio Files (*.wav *.mp3 *.ogg);;All Files (*)")
        if f:
            edit.setText(f)
            self.audio_manager.set_sound_file(key, f)

    def _test_sound_preview(self, key, edit):
        fn = edit.text().strip()
        if fn and os.path.exists(fn):
            self.audio_manager.set_sound_file(key, fn)
            self.audio_manager.play_sound(key)
        else:
            self.audio_manager.play_sound(key)

    def _export_theme_zip(self):
        """Xuất toàn bộ cấu hình và assets thành file .zip"""
        self._collect_ui_to_theme()
        # Lưu theme.xml tạm
        ThemeConfigManager.save_theme_xml(self.theme)

        f, _ = QFileDialog.getSaveFileName(self, "Xuất gói Theme ra file Zip", "broadcast_theme.openj-theme", "Open-J Theme (*.openj-theme *.zip);;All Files (*)")
        if f:
            try:
                xml_path = str(PROJECT_ROOT / "ui" / "assets" / "theme.xml")
                assets_dir = str(PROJECT_ROOT / "ui" / "assets")
                ThemePackageEngine.export_theme_to_zip(xml_path, assets_dir, f)
                QMessageBox.information(self, "Thành công", f"Đã xuất gói theme trọn gói thành công!\n{f}")
            except Exception as e:
                QMessageBox.critical(self, "Lỗi", f"Không thể xuất file zip: {e}")

    def _import_theme_zip(self):
        """Nạp gói theme từ file .zip"""
        f, _ = QFileDialog.getOpenFileName(self, "Chọn gói Theme để nạp", "", "Open-J Theme (*.openj-theme *.zip);;All Files (*)")
        if f:
            try:
                extract_to = str(PROJECT_ROOT / "ui" / "assets")
                xml_path = ThemePackageEngine.import_theme_from_zip(f, extract_to)
                self.theme = ThemeConfigManager.load_theme_xml(str(xml_path))
                event_bus.reload_theme_config.emit()
                event_bus.update_theme_config.emit(self.theme)
                QMessageBox.information(self, "Thành công", "Đã nạp và giải nén gói Theme thành công! Giao diện đã được làm mới.")
                self.accept()
            except Exception as e:
                QMessageBox.critical(self, "Lỗi", f"Không thể nạp file zip: {e}")

    def _collect_ui_to_theme(self):
        """Thu thập dữ liệu từ các widget trên UI vào self.theme dict."""
        self.theme["bezel_width"] = self.bezel_spin.value()

        # CategoryHeaders
        ch = self.theme.setdefault("category_headers", {})
        ch["unrevealed_image"] = self.edit_cat_unrev.text().strip()
        ch["revealed_image"] = self.edit_cat_rev.text().strip()
        ch["fit_mode"] = "tile" if "tile" in self.combo_cat_fit.currentText() else "zoom"
        ch["font"] = dict(self.shared_font)

        # PointGrid
        pg = self.theme.setdefault("point_grid", {})
        pg["use_image"] = self.chk_pt_use_image.isChecked()
        pg["tile_image"] = self.edit_pt_tile.text().strip()
        pg["fit_mode"] = "tile" if "tile" in self.combo_pt_fit.currentText() else "zoom"

        # ClueScreen
        cs = self.theme.setdefault("clue_screen", {})
        std = cs.setdefault("standard_card", {})
        std["use_image"] = self.chk_std_img.isChecked()
        std["image_path"] = self.edit_std_img.text().strip()

        fin = cs.setdefault("final_card", {})
        fin["use_image"] = self.chk_fin_img.isChecked()
        fin["image_path"] = self.edit_fin_img.text().strip()

        cs["font"] = dict(self.shared_font)

        # StandbyScreen
        sb = self.theme.setdefault("standby_screen", {})
        sb["image_path"] = self.edit_standby_img.text().strip()

        # VisualFX
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
        """
        Bấm [Lưu cài đặt]:
        - Ngay lập tức dừng mọi âm thanh đang phát.
        - Áp dụng cấu hình và lưu ra theme.xml.
        - Bắn tín hiệu reload_theme_config và update_theme_config.
        - Đóng Dialog ngay lập tức (self.accept()), tuyệt đối không rò rỉ âm thanh demo.
        """
        self.audio_manager.stop_all()
        self._collect_ui_to_theme()

        # Ghi ra file XML chuẩn Broadcast
        ThemeConfigManager.save_theme_xml(self.theme)

        # Bắn tín hiệu cập nhật sang TV Display
        event_bus.reload_theme_config.emit()
        event_bus.update_theme_config.emit(self.theme)

        self.accept()

    def _on_cancel(self):
        self.audio_manager.stop_all()
        self.reject()


# =============================================================================
# MAIN CONTROLLER WINDOW
# =============================================================================

class HostControllerWindow(QMainWindow):
    """Bàn điều khiển Host và Studio Operator chuẩn Broadcast."""

    def __init__(self, q_engine=None, s_engine=None, db_path="data/questions.db", parent=None):
        super().__init__(parent)
        if not os.path.isabs(db_path):
            db_path = str((project_root / db_path).resolve())
        self.db_path = db_path

        self.setWindowTitle("Open-J | Host Controller Dashboard (Season 40 & 41 Standard)")
        self.setMinimumSize(1280, 800)
        self.resize(1366, 860)

        # Core Engines
        if q_engine is None:
            q_engine = QuestionEngine(self.db_path)
            q_engine.seed_sample_data(force_reset=False)
        self.q_engine = q_engine

        self.contestants = {
            "p1": {"name": "Ken Jennings", "status": "Đương kim vô địch", "wins": 74, "prev_earnings": 2520700, "score": 0},
            "p2": {"name": "Gold Ship", "status": "Người chơi mới", "wins": 0, "prev_earnings": 0, "score": 0},
            "p3": {"name": "Agnes Tachyon", "status": "Người chơi mới", "wins": 0, "prev_earnings": 0, "score": 0},
        }

        if s_engine is None:
            s_engine = ScoreEngine([self.contestants["p1"]["name"], self.contestants["p2"]["name"], self.contestants["p3"]["name"]])
        self.s_engine = s_engine

        self.audio_manager = AudioManager(parent=self)

        # Internal State
        self.current_round = 1
        self.selected_clue = None
        self.selected_points = 200
        self.clue_buttons = {}
        self.board_cache = {}
        self.category_names = [f"Chủ đề {i+1}" for i in range(6)]

        # Theme State
        self.theme = ThemeConfigManager.load_theme_xml()

        # Final Jeopardy State
        self.final_clue_data = None
        self.final_wagers = {"p1": 0, "p2": 0, "p3": 0}
        self.final_timer = QTimer(self)
        self.final_timer_seconds = 30
        self.final_timer.timeout.connect(self._on_final_timer_tick)

        # Buzzer & 5-Second Countdown State
        self.buzzer_locked = False
        self.buzzer_active_player = None
        self.tv_answer_visible = False
        self.is_final_answer_visible = False
        self.host_timer_5s = QTimer(self)
        self.host_timer_5s.setInterval(100)
        self.host_timer_5s.timeout.connect(self._on_host_timer_5s_tick)
        self.host_timer_remaining_ms = 5000

        # Build UI
        self.setStyleSheet(APP_STYLE)
        self._build_top_header()
        self._build_central_tabs()
        self._build_bottom_dock()
        self._register_event_bus()

        # Load Data
        self._load_board_for_round(1)
        self._load_final_jeopardy_data()
        self._refresh_database_table()

    def _build_top_header(self):
        header_widget = QWidget()
        header_widget.setStyleSheet("background-color: #161b22; border-bottom: 1px solid #30363d;")
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(16, 10, 16, 10)
        header_layout.setSpacing(10)

        # Row 1: Standby Controls & Settings
        row1 = QHBoxLayout()
        row1.setSpacing(10)

        title_lbl = QLabel("OPEN-J | BROADCAST ENGINE")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 900; color: #58a6ff; letter-spacing: 1px;")

        self.btn_standby_normal = QPushButton("📺 Màn Hình Chờ Thường")
        self.btn_standby_normal.setStyleSheet("""
            QPushButton {
                background-color: #21262d; border: 1px solid #30363d; color: #c9d1d9;
                font-weight: bold; padding: 6px 14px; border-radius: 6px;
            }
            QPushButton:hover { background-color: #30363d; border-color: #58a6ff; color: #58a6ff; }
        """)
        self.btn_standby_normal.clicked.connect(lambda: event_bus.trigger_standby_mode.emit("normal"))

        self.btn_standby_mosaic = QPushButton("🧩 Màn Hình Chờ Ghép Bảng")
        self.btn_standby_mosaic.setStyleSheet("""
            QPushButton {
                background-color: #21262d; border: 1px solid #30363d; color: #c9d1d9;
                font-weight: bold; padding: 6px 14px; border-radius: 6px;
            }
            QPushButton:hover { background-color: #30363d; border-color: #f59e0b; color: #f59e0b; }
        """)
        self.btn_standby_mosaic.clicked.connect(lambda: event_bus.trigger_standby_mode.emit("mosaic"))

        self.btn_standby_off = QPushButton("▶ Vào Trận Đấu / Tắt Chờ")
        self.btn_standby_off.setStyleSheet("""
            QPushButton {
                background-color: #1f6feb; border: 1px solid #388bfd; color: #ffffff;
                font-weight: bold; padding: 6px 14px; border-radius: 6px;
            }
            QPushButton:hover { background-color: #388bfd; }
        """)
        self.btn_standby_off.clicked.connect(lambda: event_bus.trigger_standby_mode.emit("off"))

        self.btn_settings = QPushButton("⚙ Cài đặt & Âm thanh")
        self.btn_settings.setStyleSheet("""
            QPushButton {
                background-color: #21262d; border: 1px solid #30363d; color: #58a6ff;
                font-weight: bold; padding: 6px 14px; border-radius: 6px;
            }
            QPushButton:hover { background-color: #30363d; border-color: #58a6ff; }
        """)
        self.btn_settings.clicked.connect(self._open_settings_dialog)

        row1.addWidget(title_lbl)
        row1.addStretch()
        row1.addWidget(self.btn_standby_normal)
        row1.addWidget(self.btn_standby_mosaic)
        row1.addWidget(self.btn_standby_off)
        row1.addWidget(self.btn_settings)

        # Row 2: Segmented Round Buttons
        row2 = QHBoxLayout()
        row2.setSpacing(12)

        lbl_round_tag = QLabel("ĐIỀU PHỐI VÒNG:")
        lbl_round_tag.setStyleSheet("font-size: 13px; font-weight: 800; color: #8b949e;")

        self.btn_round1 = QPushButton("[ 1. VÒNG 1: JEOPARDY ]")
        self.btn_round2 = QPushButton("[ 2. VÒNG 2: DOUBLE JEOPARDY ]")
        self.btn_round3 = QPushButton("[ 3. VÒNG FINAL JEOPARDY ]")

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

        row2.addWidget(lbl_round_tag)
        row2.addWidget(self.btn_round1, 1)
        row2.addWidget(self.btn_round2, 1)
        row2.addWidget(self.btn_round3, 1)

        header_layout.addLayout(row1)
        header_layout.addLayout(row2)

        self.header_widget = header_widget

    def _open_settings_dialog(self):
        dlg = SettingsDialog(self.theme, self.audio_manager, self)
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

        self.tabs.addTab(self.tab1, "Tab 1: Chuẩn bị & Người chơi")
        self.tabs.addTab(self.tab2, "Tab 2: Điều phối Vòng 1 & 2")
        self.tabs.addTab(self.tab3, "Tab 3: Điều phối Vòng 3 (Final)")
        self.tabs.addTab(self.tab4, "Tab 4: Quản lý CSDL (SQLite)")
        self.tabs.currentChanged.connect(self._on_tab_changed)

        c_layout.addWidget(self.tabs)
        self.setCentralWidget(container)

    # =========================================================================
    # TAB 1: PREGAME SETUP
    # =========================================================================

    def _build_tab1_pregame(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        header = QLabel("THIẾT LẬP THÔNG TIN 3 NGƯỜI CHƠI (SEASON 40 & 41 STANDARD)")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #58a6ff;")
        layout.addWidget(header)

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(16)
        self.p_inputs = {}

        defaults = [
            ("p1", "Người chơi 1 (Bục Trái)", "Ken Jennings", "Đương kim vô địch", 74, 2520700),
            ("p2", "Người chơi 2 (Bục Giữa)", "Gold Ship", "Người chơi mới", 0, 0),
            ("p3", "Người chơi 3 (Bục Phải)", "Agnes Tachyon", "Người chơi mới", 0, 0),
        ]

        for p_id, title, d_name, d_status, d_wins, d_prev in defaults:
            box = QGroupBox(title)
            b_layout = QFormLayout(box)
            b_layout.setSpacing(12)

            name_edit = QLineEdit(d_name)
            status_combo = QComboBox()
            status_combo.addItems(["Người chơi mới", "Đương kim vô địch"])
            status_combo.setCurrentText(d_status)

            wins_spin = QSpinBox()
            wins_spin.setRange(0, 100)
            wins_spin.setValue(d_wins)

            prev_spin = QSpinBox()
            prev_spin.setRange(0, 10000000)
            prev_spin.setValue(d_prev)
            prev_spin.setPrefix("$ ")

            b_layout.addRow("Tên người chơi:", name_edit)
            b_layout.addRow("Trạng thái:", status_combo)
            b_layout.addRow("Số ngày thắng:", wins_spin)
            b_layout.addRow("Tiền tích lũy:", prev_spin)

            self.p_inputs[p_id] = {
                "name": name_edit,
                "status": status_combo,
                "wins": wins_spin,
                "prev": prev_spin,
            }
            cards_layout.addWidget(box)

        layout.addLayout(cards_layout)

        btn_layout = QHBoxLayout()
        self.btn_lock_roster = QPushButton(" [Khóa danh sách & Bắt đầu trận đấu]")
        self.btn_lock_roster.setStyleSheet("""
            QPushButton {
                background-color: #238636;
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 20px;
            }
            QPushButton:hover { background-color: #2ea043; }
        """)
        self.btn_lock_roster.clicked.connect(self._on_lock_roster)

        self.roster_status = QLabel("Trạng thái: Sẵn sàng khóa danh sách.")
        self.roster_status.setStyleSheet("color: #8b949e; font-style: italic;")

        btn_layout.addWidget(self.btn_lock_roster)
        btn_layout.addWidget(self.roster_status)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        layout.addStretch()
        return widget

    def _on_lock_roster(self):
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

        event_bus.players_updated.emit(self.contestants)
        event_bus.score_updated.emit(self.s_engine.get_all_scores())

        self.roster_status.setText("✓ Đã khóa danh sách & phát dữ liệu thành công!")
        self.roster_status.setStyleSheet("color: #3fb950; font-weight: bold;")
        self.tabs.setCurrentIndex(1)

    # =========================================================================
    # TAB 2: ROUND 1 & 2 COORDINATION (FLEXIBLE STUDIO FX & AUTO/MANUAL INTRO)
    # =========================================================================

    def _build_tab2_board(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # KHU VỰC 1: Category Reveal Controls
        cat_group = QGroupBox("KHU VỰC 1: ĐIỀU KHIỂN GIỚI THIỆU CHỦ ĐỀ (CATEGORY REVEAL CONTROLS)")
        cat_layout = QHBoxLayout(cat_group)
        cat_layout.setContentsMargins(12, 10, 12, 10)
        cat_layout.setSpacing(10)

        self.chk_auto_intro = QCheckBox(" Chạy Tự Động")
        self.chk_auto_intro.setChecked(False)
        self.chk_auto_intro.setVisible(False)

        self.btn_cat_intro = QPushButton(" Intro Chủ Đề")
        self.btn_cat_intro.setVisible(False)

        btn_blank = QPushButton(" Bảng Trống")
        btn_blank.setStyleSheet("background-color: #21262d; color: #c9d1d9; font-weight: bold; padding: 7px 12px;")
        btn_blank.clicked.connect(lambda: event_bus.trigger_board_blank.emit())

        btn_fill = QPushButton(" Fill Ngẫu Nhiên")
        btn_fill.setStyleSheet("background-color: #21262d; color: #c9d1d9; font-weight: bold; padding: 7px 12px;")
        btn_fill.clicked.connect(lambda: event_bus.trigger_board_fill.emit())

        self.btn_step0 = QPushButton(" 1. Mở Cột (Logo)")
        self.btn_step0.setStyleSheet("background-color: #30363d; color: white; font-weight: bold; padding: 7px 12px;")
        self.btn_step0.clicked.connect(self._on_cat_open_col)

        self.btn_step1 = QPushButton(" 2. Lộ Tên")
        self.btn_step1.setStyleSheet("background-color: #1f6feb; color: white; font-weight: bold; padding: 7px 12px;")
        self.btn_step1.clicked.connect(lambda: (event_bus.trigger_category_fade_logo.emit(), event_bus.trigger_category_reveal_step.emit(1)))

        self.btn_next_cat = QPushButton(" 3. Trượt Tiếp >>")
        self.btn_next_cat.setStyleSheet("background-color: #238636; color: white; font-weight: bold; padding: 7px 12px;")
        self.btn_next_cat.clicked.connect(self._on_cat_slide_next)

        self.btn_cancel_intro = QPushButton(" Về Bảng")
        self.btn_cancel_intro.setStyleSheet("background-color: #d29922; color: #0d1117; font-weight: bold; padding: 7px 12px;")
        self.btn_cancel_intro.clicked.connect(lambda: event_bus.cancel_category_reveal.emit())

        btn_obs_fs = QPushButton("📺 OBS: F11")
        btn_obs_fs.setStyleSheet("background-color: #8957e5; color: white; font-weight: bold; padding: 7px 12px;")
        btn_obs_fs.clicked.connect(lambda: event_bus.set_display_fullscreen_toggle.emit())

        cat_layout.addWidget(btn_blank)
        cat_layout.addWidget(btn_fill)
        cat_layout.addWidget(self.btn_step0)
        cat_layout.addWidget(self.btn_step1)
        cat_layout.addWidget(self.btn_next_cat)
        cat_layout.addWidget(self.btn_cancel_intro)
        cat_layout.addWidget(btn_obs_fs)
        cat_layout.addStretch()

        layout.addWidget(cat_group)

        # KHU VỰC 2: Ma Trận 6x5 & Khung Soi Đáp Án + Đồng Hồ 5s + Lệnh 2 Bước
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
            lbl = QLabel(f"CHỦ ĐỀ {c+1}")
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

        # Right: Peek Box + 5-Second Countdown + 2-Step Broadcast Controls
        right_frame = QFrame()
        right_frame.setStyleSheet("background-color: #161b22; border: 1px solid #30363d; border-radius: 6px;")
        r_layout = QVBoxLayout(right_frame)
        r_layout.setContentsMargins(14, 12, 14, 12)
        r_layout.setSpacing(10)

        peek_lbl = QLabel("HOST SECRET PEEK BOX (SOI ĐÁP ÁN BÍ MẬT)")
        peek_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #f59e0b;")
        r_layout.addWidget(peek_lbl)

        self.peek_text = QTextEdit()
        self.peek_text.setReadOnly(True)
        self.peek_text.setStyleSheet("background-color: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 8px; color: #f0f6fc;")
        self.peek_text.setMaximumHeight(150)
        self.peek_text.setMinimumHeight(100)
        self._set_peek_placeholder()
        r_layout.addWidget(self.peek_text)

        # Đồng Hồ Đếm Ngược Host 5 Giây
        timer_box = QGroupBox("⏱ ĐỒNG HỒ HOST 5 GIÂY (BUZZER COUNTDOWN)")
        tb_layout = QVBoxLayout(timer_box)
        tb_layout.setSpacing(6)

        t_row = QHBoxLayout()
        self.host_timer_lbl = QLabel("05.0s")
        self.host_timer_lbl.setStyleSheet("font-size: 22px; font-weight: 900; color: #3fb950; font-family: monospace;")
        self.host_timer_lbl.setAlignment(Qt.AlignCenter)

        self.btn_timer_start = QPushButton("▶ Bắt đầu 5s")
        self.btn_timer_start.setStyleSheet("background-color: #238636; color: white; font-weight: bold; padding: 5px 10px;")
        self.btn_timer_start.clicked.connect(self._start_host_timer_5s)

        self.btn_timer_stop = QPushButton("⏹ Dừng / Reset 5s")
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

        # Lệnh Phát Sóng 2 Bước Chuẩn
        cmd_box = QGroupBox("LỆNH PHÁT SÓNG & ĐIỀU KHIỂN (2 BƯỚC)")
        cb_layout = QVBoxLayout(cmd_box)
        cb_layout.setSpacing(7)

        self.btn_display_clue = QPushButton("1. 🚀 [Bắn lên TV / Zoom Điểm]")
        self.btn_display_clue.setStyleSheet("""
            QPushButton {
                background-color: #1f6feb; color: white; font-weight: bold;
                font-size: 13px; padding: 8px; border: 1px solid #388bfd;
            }
            QPushButton:hover { background-color: #388bfd; }
        """)
        self.btn_display_clue.clicked.connect(self._on_display_clue_clicked)

        self.btn_clue_reveal = QPushButton("2. 📋 [Xác nhận mở câu hỏi]")
        self.btn_clue_reveal.setStyleSheet("""
            QPushButton {
                background-color: #8957e5; color: white; font-weight: bold;
                font-size: 13px; padding: 8px; border: 1px solid #a371f7;
            }
            QPushButton:hover { background-color: #a371f7; }
        """)
        self.btn_clue_reveal.clicked.connect(self._on_clue_reveal_clicked)

        self.btn_reveal_dd = QPushButton("★ [Mở nội dung câu hỏi Daily Double]")
        self.btn_reveal_dd.setStyleSheet("""
            QPushButton {
                background-color: #e11d48; color: white; font-weight: bold;
                font-size: 13px; padding: 8px; border: 1px solid #f43f5e;
            }
            QPushButton:hover { background-color: #f43f5e; }
        """)
        self.btn_reveal_dd.setVisible(False)
        self.btn_reveal_dd.clicked.connect(self._on_reveal_dd_clicked)

        self.btn_toggle_answer = QPushButton("👁 [Hiện Đáp Án trên TV]")
        self.btn_toggle_answer.setStyleSheet("""
            QPushButton {
                background-color: #21262d; color: #8b949e; font-weight: bold;
                font-size: 13px; padding: 8px; border: 1px solid #30363d;
            }
            QPushButton:hover { background-color: #30363d; color: #ffffff; }
        """)
        self.btn_toggle_answer.clicked.connect(self._on_toggle_tv_answer_clicked)

        self.btn_close_clue = QPushButton("↩ [Đóng câu hỏi / Quay về bảng]")
        self.btn_close_clue.setStyleSheet("""
            QPushButton {
                background-color: #d29922; color: #0d1117; font-weight: bold;
                font-size: 13px; padding: 8px; border: 1px solid #e3b341;
            }
            QPushButton:hover { background-color: #e3b341; }
        """)
        self.btn_close_clue.clicked.connect(self._on_close_clue_clicked)

        self.clue_status = QLabel("Trạng thái TV: Đang ở màn hình Bảng chính")
        self.clue_status.setStyleSheet("color: #8b949e; font-style: italic;")

        cb_layout.addWidget(self.btn_display_clue)
        cb_layout.addWidget(self.btn_clue_reveal)
        cb_layout.addWidget(self.btn_reveal_dd)
        cb_layout.addWidget(self.btn_toggle_answer)
        cb_layout.addWidget(self.btn_close_clue)
        cb_layout.addWidget(self.clue_status)
        r_layout.addWidget(cmd_box)

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        right_scroll.setWidget(right_frame)

        splitter.addWidget(right_scroll)
        splitter.setStretchFactor(0, 65)
        splitter.setStretchFactor(1, 35)
        layout.addWidget(splitter)


        return widget

    def _on_auto_intro_toggled(self, checked):
        if checked:
            self.btn_cat_intro.setVisible(True)
            self.btn_step0.setVisible(False)
            self.btn_step1.setVisible(False)
            self.btn_next_cat.setEnabled(False)
            self.btn_next_cat.setVisible(False)
        else:
            self.btn_cat_intro.setVisible(False)
            self.btn_step0.setVisible(True)
            self.btn_step1.setVisible(True)
            self.btn_next_cat.setEnabled(True)
            self.btn_next_cat.setVisible(True)

    def _on_cat_open_col(self):
        self.intro_col_index = 0
        event_bus.trigger_category_show_logo.emit(0)
        event_bus.trigger_category_reveal_step.emit(0)

    def _on_cat_slide_next(self):
        event_bus.trigger_category_slide_next.emit()
        event_bus.trigger_category_reveal_step.emit(2)

    def _on_intro_clicked(self):
        is_auto = self.chk_auto_intro.isChecked()
        event_bus.trigger_category_reveal.emit({"auto": is_auto, "step": 0, "col_index": 0})

    def _update_round_button_styles(self):
        active = (
            "background-color: #1f6feb; color: #ffffff; font-weight: 900; "
            "border: 2px solid #FFD700; padding: 7px 18px; border-radius: 6px; font-size: 13px;"
        )
        inactive = (
            "background-color: #21262d; color: #8b949e; font-weight: bold; "
            "border: 1px solid #30363d; padding: 7px 18px; border-radius: 6px; font-size: 13px;"
        )
        self.btn_round1.setStyleSheet(active if self.current_round == 1 else inactive)
        self.btn_round2.setStyleSheet(active if self.current_round == 2 else inactive)
        self.btn_round3.setStyleSheet(active if self.current_round == 3 else inactive)

    def _on_round_button_clicked(self, round_id):
        self.current_round = round_id
        self._update_round_button_styles()
        if round_id in (1, 2):
            self.tabs.setCurrentIndex(1)
            event_bus.change_round.emit(round_id)
            self._load_board_for_round(round_id)
        elif round_id == 3:
            self.tabs.setCurrentIndex(2)
            event_bus.change_round.emit(3)

    def _on_tab_changed(self, index):
        if index == 1:
            if self.current_round not in (1, 2):
                self.current_round = 1
            self._update_round_button_styles()
        elif index == 2:
            self.current_round = 3
            self._update_round_button_styles()

    def _set_peek_placeholder(self):
        self.peek_text.setHtml(
            "<div style='color: #8b949e; font-style: italic; text-align: center; margin-top: 60px;'>"
            "<i>Nhấp chọn một ô điểm trên bảng ma trận để soi trước câu hỏi, đáp án đúng và tình trạng ảnh...</i>"
            "</div>"
        )

    def _load_board_for_round(self, round_id):
        self.board_cache.clear()
        self.selected_clue = None
        self._set_peek_placeholder()

        base_multiplier = 200 if round_id == 1 else 400

        with self._get_db_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM questions WHERE round_id = ? ORDER BY col_index, row_index", (round_id,))
            rows = cursor.fetchall()

        for row in rows:
            d = dict(row)
            c, r = d["col_index"], d["row_index"]
            if 0 <= c < 6 and 0 <= r < 5:
                self.board_cache[(c, r)] = d

        for c in range(6):
            cat_name = f"CHỦ ĐỀ {c+1}"
            for r in range(5):
                if (c, r) in self.board_cache:
                    cat_name = self.board_cache[(c, r)]["category_name"].upper()
                    break
            self.cat_headers[c].setText(cat_name)

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
                "question_text": f"(Chưa có nội dung câu hỏi cho ô Cột {col+1}, Hàng {row+1})",
                "answer_text": "(Chưa có đáp án)",
                "asset_filename": "",
                "is_daily_double": 0,
                "is_used": 0,
            }

        self.selected_clue = curr_clue
        self.selected_points = curr_clue["points"]
        self._update_dock_quick_point_buttons(self.selected_points)

        asset_fn = curr_clue.get("asset_filename", "")
        asset_p = Path("ui/assets/image") / asset_fn if asset_fn else None
        has_asset = bool(asset_fn and asset_p.exists())
        asset_desc = f"<span style='color:#3fb950;'>✓ Có ảnh ({asset_fn})</span>" if has_asset else "<span style='color:#8b949e;'>Chỉ text</span>"
        dd_badge = "<span style='background-color:#da3633; color:white; padding:2px 6px; border-radius:3px; font-weight:bold;'>CÓ (DAILY DOUBLE!)</span>" if curr_clue["is_daily_double"] else "<span style='color:#8b949e;'>Không</span>"

        html = f"""
        <div style="font-family: Arial, sans-serif;">
            <p style="margin: 0 0 6px 0; font-size: 14px;">
                <b>Chủ đề:</b> <span style="color: #58a6ff; font-weight: bold;">{curr_clue['category_name']}</span>
            </p>
            <p style="margin: 0 0 8px 0; font-size: 13px;">
                <b>Mức điểm:</b> <span style="color: #f59e0b; font-weight: bold;">${curr_clue['points']}</span> &nbsp;|&nbsp; 
                <b>Daily Double:</b> {dd_badge}
            </p>
            <div style="background-color: #0b1354; border-left: 4px solid #1f6feb; padding: 8px; border-radius: 4px; margin-bottom: 8px;">
                <b style="color: #58a6ff;">Nội dung câu hỏi (Clue):</b><br/>
                <span style="font-size: 14px; color: #ffffff;">{curr_clue['question_text']}</span>
            </div>
            <div style="background-color: #0e2a1b; border-left: 4px solid #238636; padding: 8px; border-radius: 4px; margin-bottom: 8px;">
                <b style="color: #3fb950;">Đáp án đúng (Host Only):</b><br/>
                <span style="font-size: 15px; font-weight: bold; color: #3fb950;">{curr_clue['answer_text']}</span>
            </div>
            <p style="margin: 2px 0 0 0; font-size: 12px;"><b>Tình trạng Asset:</b> {asset_desc}</p>
        </div>
        """
        self.peek_text.setHtml(html)

    def _on_display_clue_clicked(self):
        if not self.selected_clue:
            QMessageBox.warning(self, "Chưa chọn câu hỏi", "Vui lòng chọn 1 ô trên bảng trước!")
            return

        payload = dict(self.selected_clue)
        asset_fn = payload.get("asset_filename", "")
        asset_path = Path("ui/assets/image") / asset_fn if asset_fn else None
        payload["has_asset"] = bool(asset_fn and asset_path and asset_path.exists())
        payload["asset_path"] = str(asset_path.resolve()) if payload["has_asset"] else ""

        # Step 1: Kích hoạt Zoom ô điểm số hoặc Daily Double Splash trên TV
        event_bus.trigger_clue_zoom.emit(payload)
        event_bus.request_clue_zoom.emit(payload)

        # Reset TV answer overlay
        self.tv_answer_visible = False
        self.btn_toggle_answer.setText("👁 [Hiện Đáp Án trên TV]")
        self.btn_toggle_answer.setStyleSheet("background-color: #21262d; color: #8b949e; font-weight: bold; font-size: 13px; padding: 8px; border: 1px solid #30363d;")

        if payload.get("is_daily_double"):
            self.clue_status.setText("★ DAILY DOUBLE! Đang phóng to điểm và bung Splash. Bấm '2. Xác nhận mở câu hỏi' để hiện nội dung.")
            self.clue_status.setStyleSheet("color: #f59e0b; font-weight: bold;")
            self.btn_reveal_dd.setVisible(True)
        else:
            self.btn_reveal_dd.setVisible(False)
            self.clue_status.setText(f"✓ Đang phóng to ô điểm trên TV [{payload['category_name']} ${payload['points']}]. Bấm '2. Xác nhận mở câu hỏi' để hiện thẻ câu hỏi.")
            self.clue_status.setStyleSheet("color: #3fb950; font-weight: bold;")

    def _on_clue_reveal_clicked(self):
        if not self.selected_clue:
            return
        payload = dict(self.selected_clue)
        asset_fn = payload.get("asset_filename", "")
        asset_path = Path("ui/assets/image") / asset_fn if asset_fn else None
        payload["has_asset"] = bool(asset_fn and asset_path and asset_path.exists())
        payload["asset_path"] = str(asset_path.resolve()) if payload["has_asset"] else ""

        event_bus.trigger_clue_reveal.emit()
        event_bus.display_question.emit(payload)
        self.btn_reveal_dd.setVisible(False)
        self.clue_status.setText("✓ Đã mở nội dung câu hỏi lên TV!")
        self.clue_status.setStyleSheet("color: #3fb950; font-weight: bold;")

    def _on_reveal_dd_clicked(self):
        self._on_clue_reveal_clicked()

    def _on_toggle_tv_answer_clicked(self):
        if not self.selected_clue:
            return
        self.tv_answer_visible = not self.tv_answer_visible
        ans_text = self.selected_clue.get("answer_text", "")
        event_bus.toggle_tv_answer.emit(self.tv_answer_visible, ans_text)
        if self.tv_answer_visible:
            self.btn_toggle_answer.setText("👁 [Ẩn Đáp Án trên TV]")
            self.btn_toggle_answer.setStyleSheet("background-color: #238636; color: white; font-weight: bold; font-size: 13px; padding: 8px; border: 1px solid #3fb950;")
        else:
            self.btn_toggle_answer.setText("👁 [Hiện Đáp Án trên TV]")
            self.btn_toggle_answer.setStyleSheet("background-color: #21262d; color: #8b949e; font-weight: bold; font-size: 13px; padding: 8px; border: 1px solid #30363d;")

    def _on_close_clue_clicked(self):
        if not self.selected_clue:
            return

        clue_id = self.selected_clue.get("id")
        col = self.selected_clue["col_index"]
        row = self.selected_clue["row_index"]

        if clue_id:
            with self._get_db_conn() as conn:
                conn.cursor().execute("UPDATE questions SET is_used = 1 WHERE id = ?", (clue_id,))
                conn.commit()

        self.selected_clue["is_used"] = 1
        if (col, row) in self.board_cache:
            self.board_cache[(col, row)]["is_used"] = 1

        btn = self.clue_buttons[(col, row)]
        self._apply_clue_button_style(btn, is_used=True, is_selected=False, is_dd=bool(self.selected_clue.get("is_daily_double")))

        # Reset TV answer overlay
        self.tv_answer_visible = False
        self.btn_toggle_answer.setText("👁 [Hiện Đáp Án trên TV]")
        self.btn_toggle_answer.setStyleSheet("background-color: #21262d; color: #8b949e; font-weight: bold; font-size: 13px; padding: 8px; border: 1px solid #30363d;")
        event_bus.toggle_tv_answer.emit(False, "")

        # Close clue on TV
        event_bus.close_question.emit()
        self.clue_status.setText("Trạng thái TV: Đã đóng câu hỏi. Trở về bảng.")
        self.clue_status.setStyleSheet("color: #8b949e; font-style: italic;")

        # Auto-reset buzzers and stop 5s timer
        self._reset_buzzers()

    # =========================================================================
    # TAB 3: FINAL JEOPARDY
    # =========================================================================

    def _build_tab3_final(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        top_row = QHBoxLayout()
        header = QLabel("ĐIỀU PHỐI VÒNG 3: FINAL JEOPARDY! SEQUENCER")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #58a6ff;")

        self.chk_manual_override = QCheckBox(" Bật Chế Độ Nhập Thủ Công (Manual Override)")
        self.chk_manual_override.setStyleSheet("color: #f59e0b; font-weight: bold; font-size: 13px;")
        self.chk_manual_override.toggled.connect(self._on_manual_override_toggled)

        top_row.addWidget(header)
        top_row.addStretch()
        top_row.addWidget(self.chk_manual_override)
        layout.addLayout(top_row)

        self.manual_frame = QFrame()
        self.manual_frame.setStyleSheet("background-color: #1c2128; border: 1px solid #f59e0b; border-radius: 6px; padding: 8px;")
        mf_layout = QFormLayout(self.manual_frame)
        self.edit_cat = QLineEdit()
        self.edit_cat.setPlaceholderText("Nhập tên chủ đề Final...")
        self.edit_clue = QLineEdit()
        self.edit_clue.setPlaceholderText("Nhập nội dung manh mối Final...")
        self.edit_ans = QLineEdit()
        self.edit_ans.setPlaceholderText("Nhập đáp án đúng...")
        mf_layout.addRow("Chủ đề thủ công:", self.edit_cat)
        mf_layout.addRow("Manh mối thủ công:", self.edit_clue)
        mf_layout.addRow("Đáp án thủ công:", self.edit_ans)
        self.manual_frame.setVisible(False)
        layout.addWidget(self.manual_frame)

        # Step 1: Splash Logo Final
        self.step1_box = QGroupBox("BƯỚC 1: HIỂN THỊ LOGO SPLASH VÒNG FINAL")
        s1_layout = QVBoxLayout(self.step1_box)
        self.btn_show_splash = QPushButton(" [1. Mở Splash Logo Final]")
        self.btn_show_splash.setStyleSheet("background-color: #8957e5; color: white; font-weight: bold; padding: 8px;")
        self.btn_show_splash.clicked.connect(self._on_show_splash)
        s1_layout.addWidget(self.btn_show_splash)
        layout.addWidget(self.step1_box)

        # Step 2: Category & Wagers
        self.step2_box = QGroupBox("BƯỚC 2: CÔNG BỐ CHỦ ĐỀ & KHÓA CƯỢC 3 NGƯỜI CHƠI")
        s2_layout = QVBoxLayout(self.step2_box)

        self.final_cat_lbl = QLabel("Chủ đề Final: Đang nạp từ CSDL...")
        self.final_cat_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #f59e0b;")
        s2_layout.addWidget(self.final_cat_lbl)

        w_layout = QHBoxLayout()
        self.wager_spins = {}
        self.wager_notes = {}
        for p_id in ("p1", "p2", "p3"):
            box = QFrame()
            box.setStyleSheet("background-color: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 8px;")
            b_lay = QVBoxLayout(box)
            name_lbl = QLabel(self.contestants[p_id]["name"])
            name_lbl.setStyleSheet("font-weight: bold; color: #58a6ff;")
            note = QLabel("Điểm: $0")
            note.setStyleSheet("color: #8b949e; font-size: 12px;")
            spin = QSpinBox()
            spin.setRange(0, 100000)
            spin.setPrefix("Cược: $ ")
            b_lay.addWidget(name_lbl)
            b_lay.addWidget(note)
            b_lay.addWidget(spin)
            w_layout.addWidget(box)
            self.wager_spins[p_id] = spin
            self.wager_notes[p_id] = note
        s2_layout.addLayout(w_layout)

        self.btn_lock_wagers = QPushButton(" [2. Công Bố Chủ Đề & Khóa Cược]")
        self.btn_lock_wagers.setStyleSheet("background-color: #238636; color: white; font-weight: bold; padding: 8px;")
        self.btn_lock_wagers.clicked.connect(self._on_lock_wagers)
        s2_layout.addWidget(self.btn_lock_wagers)
        layout.addWidget(self.step2_box)

        # Step 3: Clue & 30s Countdown
        self.step3_box = QGroupBox("BƯỚC 3: HIỂN THỊ MANH MỐI & PHÁT THINK MUSIC (30S)")
        self.step3_box.setEnabled(False)
        s3_layout = QVBoxLayout(self.step3_box)

        self.final_clue_preview = QTextEdit()
        self.final_clue_preview.setReadOnly(True)
        self.final_clue_preview.setMaximumHeight(85)
        s3_layout.addWidget(self.final_clue_preview)

        t_layout = QHBoxLayout()
        self.btn_start_30s = QPushButton(" [3. Mở Manh Mối & Bắt Đầu 30s]")
        self.btn_start_30s.setStyleSheet("background-color: #1f6feb; color: white; font-weight: bold; padding: 8px 16px;")
        self.btn_start_30s.clicked.connect(self._on_start_30s)

        self.btn_stop_30s = QPushButton(" [Dừng khẩn cấp]")
        self.btn_stop_30s.setStyleSheet("background-color: #da3633; color: white; font-weight: bold; padding: 8px 16px;")
        self.btn_stop_30s.setEnabled(False)
        self.btn_stop_30s.clicked.connect(self._on_stop_30s_emergency)

        self.btn_toggle_final_answer = QPushButton("👁 [Hiện Đáp Án Final trên TV]")
        self.btn_toggle_final_answer.setStyleSheet("background-color: #21262d; color: #8b949e; font-weight: bold; padding: 8px 16px; border: 1px solid #30363d;")
        self.btn_toggle_final_answer.clicked.connect(self._on_toggle_final_answer_clicked)

        self.timer_bar = QProgressBar()
        self.timer_bar.setRange(0, 30)
        self.timer_bar.setValue(30)
        self.timer_bar.setFormat("30 giây")

        t_layout.addWidget(self.btn_start_30s)
        t_layout.addWidget(self.btn_stop_30s)
        t_layout.addWidget(self.btn_toggle_final_answer)
        t_layout.addWidget(self.timer_bar, 1)
        s3_layout.addLayout(t_layout)
        layout.addWidget(self.step3_box)

        # Step 4: Grading & Champion (Host Only)
        self.step4_box = QGroupBox("BƯỚC 4: CHẤM ĐIỂM & TỔNG KẾT (CHỈ HIỂN THỊ TRÊN HOST)")
        self.step4_box.setEnabled(False)
        s4_layout = QVBoxLayout(self.step4_box)

        g_layout = QHBoxLayout()
        self.grade_checks = {}
        for p_id in ("p1", "p2", "p3"):
            box = QFrame()
            box.setStyleSheet("background-color: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 6px;")
            b_lay = QVBoxLayout(box)
            p_lbl = QLabel(self.contestants[p_id]["name"])
            p_lbl.setStyleSheet("font-weight: bold; color: #58a6ff;")
            chk = QCheckBox(" Trả lời ĐÚNG")
            chk.setChecked(True)
            chk.setStyleSheet("color: #3fb950; font-weight: bold;")
            b_lay.addWidget(p_lbl)
            b_lay.addWidget(chk)
            g_layout.addWidget(box)
            self.grade_checks[p_id] = chk
        s4_layout.addLayout(g_layout)

        self.btn_calc_final = QPushButton(" [Tổng kết & Chấm Điểm]")
        self.btn_calc_final.setStyleSheet("background-color: #a371f7; color: white; font-weight: bold; padding: 9px;")
        self.btn_calc_final.clicked.connect(self._on_calc_final)
        s4_layout.addWidget(self.btn_calc_final)

        layout.addWidget(self.step4_box)
        layout.addStretch()
        return widget

    def _on_manual_override_toggled(self, checked):
        self.manual_frame.setVisible(checked)
        if checked:
            cat = self.edit_cat.text().strip() or "CHỦ ĐỀ THỦ CÔNG"
            self.final_cat_lbl.setText(f"Chủ đề Final (Manual): {cat.upper()}")
            for spin in self.wager_spins.values():
                spin.setEnabled(True)
        else:
            self._load_final_jeopardy_data()

    def _load_final_jeopardy_data(self):
        with self._get_db_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM questions WHERE round_id = 3 LIMIT 1")
            row = cursor.fetchone()

        if row:
            self.final_clue_data = dict(row)
            self.final_cat_lbl.setText(f"Chủ đề Final Jeopardy: {self.final_clue_data['category_name'].upper()}")
            html = f"<b>Manh mối:</b> <span style='color:#58a6ff;'>{self.final_clue_data['question_text']}</span><br/><b>Đáp án Host:</b> <span style='color:#3fb950;'>{self.final_clue_data['answer_text']}</span>"
            self.final_clue_preview.setHtml(html)
        else:
            self.final_clue_data = None
            self.final_cat_lbl.setText("Chủ đề Final: (Chưa cấu hình câu hỏi Round 3)")
            self.final_clue_preview.setText("Vui lòng nạp dữ liệu ở Tab 4 hoặc tích chọn Manual Override.")

    def _on_show_splash(self):
        cat_name = self.edit_cat.text().strip() if self.chk_manual_override.isChecked() else (self.final_clue_data['category_name'] if self.final_clue_data else "FINAL JEOPARDY")
        event_bus.trigger_final_step.emit(1, {"category": cat_name})
        self.step2_box.setEnabled(True)

    def _on_lock_wagers(self):
        for p_id in ("p1", "p2", "p3"):
            self.final_wagers[p_id] = self.wager_spins[p_id].value()
            self.wager_spins[p_id].setEnabled(False)

        cat_name = self.edit_cat.text().strip() if self.chk_manual_override.isChecked() else (self.final_clue_data['category_name'] if self.final_clue_data else "FINAL JEOPARDY")
        event_bus.trigger_final_step.emit(2, {"category": cat_name, "wagers": self.final_wagers})

        self.btn_lock_wagers.setEnabled(False)
        self.step3_box.setEnabled(True)

    def _on_start_30s(self):
        self.btn_start_30s.setEnabled(False)
        self.btn_stop_30s.setEnabled(True)
        self.final_timer_seconds = 30
        self.timer_bar.setValue(30)
        self.timer_bar.setFormat("30 giây")

        if self.chk_manual_override.isChecked():
            clue_text = self.edit_clue.text().strip() or "Manh mối Final thủ công"
            ans_text = self.edit_ans.text().strip() or "Đáp án thủ công"
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
        event_bus.play_sound_event.emit("think_music")
        self.final_timer.start(1000)

    def _on_stop_30s_emergency(self):
        self.final_timer.stop()
        self.audio_manager.stop_music()
        self.timer_bar.setFormat("ĐÃ DỪNG KHẨN CẤP")
        self.btn_stop_30s.setEnabled(False)
        self.step4_box.setEnabled(True)

    def _on_toggle_final_answer_clicked(self):
        self.is_final_answer_visible = not self.is_final_answer_visible
        if self.chk_manual_override.isChecked():
            ans = self.edit_ans.text().strip()
        else:
            ans = self.final_clue_data.get("answer_text", "") if self.final_clue_data else ""

        event_bus.toggle_tv_answer.emit(self.is_final_answer_visible, ans)
        if self.is_final_answer_visible:
            self.btn_toggle_final_answer.setText("👁 [Ẩn Đáp Án Final trên TV]")
            self.btn_toggle_final_answer.setStyleSheet("background-color: #238636; color: white; font-weight: bold; padding: 8px 16px; border: 1px solid #3fb950;")
        else:
            self.btn_toggle_final_answer.setText("👁 [Hiện Đáp Án Final trên TV]")
            self.btn_toggle_final_answer.setStyleSheet("background-color: #21262d; color: #8b949e; font-weight: bold; padding: 8px 16px; border: 1px solid #30363d;")

    def _on_final_timer_tick(self):
        self.final_timer_seconds -= 1
        self.timer_bar.setValue(self.final_timer_seconds)
        self.timer_bar.setFormat(f"{self.final_timer_seconds} giây")

        # Đúng sau 15 giây đếm ngược: kích hoạt cross-fade Xanh -> Đỏ
        if self.final_timer_seconds == 15:
            event_bus.start_final_crossfade.emit()

        if self.final_timer_seconds <= 0:
            self.final_timer.stop()
            self.timer_bar.setFormat("HẾT GIỜ! ĐẶT BÚT!")
            self.btn_stop_30s.setEnabled(False)
            event_bus.play_sound_event.emit("timeout")
            self.step4_box.setEnabled(True)

    def _on_calc_final(self):
        final_totals = {}
        for p_id in ("p1", "p2", "p3"):
            wager = self.final_wagers[p_id]
            is_correct = self.grade_checks[p_id].isChecked()
            cur = self.contestants[p_id]["score"]
            new_score = cur + wager if is_correct else cur - wager
            if is_correct:
                self.s_engine.add_correct(p_id, wager)
            else:
                self.s_engine.add_incorrect(p_id, wager)
            self.contestants[p_id]["score"] = new_score
            final_totals[p_id] = new_score

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
        # Lưu ý: TV Display ẨN HOÀN TOÀN màn hình quán quân
        event_bus.winner_announced.emit(results)
        event_bus.play_sound_event.emit("correct")

        QMessageBox.information(
            self,
            "Quán quân Chung cuộc! (Bảng điều khiển Host)",
            f"🏆 Quán quân: {self.contestants[w_id]['name']} (${w_score})\n"
            f"🥈 Á quân: {self.contestants[s_id]['name']} (${s_score}) - $3,000\n"
            f"🥉 Hạng ba: {self.contestants[t_id]['name']} (${t_score}) - $2,000\n\n"
            "(Lưu ý: Màn hình TV không hiển thị bảng điểm vinh danh để đảm bảo tính thẩm mỹ phát sóng)"
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
        lbl = QLabel("Lọc theo Vòng:")
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["Tất cả các vòng", "Round 1 (Jeopardy)", "Round 2 (Double Jeopardy)", "Round 3 (Final Jeopardy)"])
        self.filter_combo.currentIndexChanged.connect(self._refresh_database_table)

        btn_add = QPushButton("+ Thêm dòng mới")
        btn_add.clicked.connect(self._on_add_db_row)

        btn_del = QPushButton("- Xóa dòng đã chọn")
        btn_del.clicked.connect(self._on_delete_db_row)

        btn_reset = QPushButton(" Đặt lại chưa mở (Reset is_used)")
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
        self.btn_save_db = QPushButton(" [Lưu toàn bộ thay đổi vào Database]")
        self.btn_save_db.setStyleSheet("background-color: #238636; color: white; font-weight: bold; padding: 9px 20px;")
        self.btn_save_db.clicked.connect(self._on_save_db)

        self.db_status = QLabel("Sẵn sàng.")
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
        self.db_status.setText(f"Đã tải {len(rows)} câu hỏi.")

    def _on_add_db_row(self):
        r = self.db_table.rowCount()
        self.db_table.insertRow(r)
        id_item = QTableWidgetItem("NEW")
        id_item.setFlags(id_item.flags() ^ Qt.ItemIsEditable)
        self.db_table.setItem(r, 0, id_item)
        self.db_table.setItem(r, 1, QTableWidgetItem("1"))
        self.db_table.setItem(r, 2, QTableWidgetItem("0"))
        self.db_table.setItem(r, 3, QTableWidgetItem("0"))
        self.db_table.setItem(r, 4, QTableWidgetItem("Chủ đề mới"))
        self.db_table.setItem(r, 5, QTableWidgetItem("200"))
        self.db_table.setItem(r, 6, QTableWidgetItem("Nội dung câu hỏi?"))
        self.db_table.setItem(r, 7, QTableWidgetItem("Đáp án chuẩn"))
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
                conn.cursor().execute("DELETE FROM questions WHERE id = ?", (int(id_text),))
                conn.commit()
        self.db_table.removeRow(cur)
        self.db_status.setText("Đã xóa dòng.")

    def _on_reset_used_flags(self):
        with self._get_db_conn() as conn:
            conn.cursor().execute("UPDATE questions SET is_used = 0")
            conn.commit()
        self._refresh_database_table()
        self._load_board_for_round(self.current_round)
        QMessageBox.information(self, "Đã đặt lại", "Tất cả câu hỏi đã được đặt về CHƯA MỞ (is_used = 0).")

    def _on_save_db(self):
        try:
            with self._get_db_conn() as conn:
                cursor = conn.cursor()
                for r in range(self.db_table.rowCount()):
                    id_text = self.db_table.item(r, 0).text()
                    round_id = int(self.db_table.item(r, 1).text() or 1)
                    col_idx = int(self.db_table.item(r, 2).text() or 0)
                    row_idx = int(self.db_table.item(r, 3).text() or 0)
                    cat_name = self.db_table.item(r, 4).text()
                    points = int(self.db_table.item(r, 5).text() or 0)
                    q_text = self.db_table.item(r, 6).text()
                    ans_text = self.db_table.item(r, 7).text()
                    asset = self.db_table.item(r, 8).text()
                    is_dd = 1 if self.db_table.item(r, 9).checkState() == Qt.Checked else 0
                    is_used = 1 if self.db_table.item(r, 10).checkState() == Qt.Checked else 0

                    if id_text == "NEW":
                        cursor.execute("""
                        INSERT INTO questions (round_id, col_index, row_index, category_name, points, question_text, answer_text, asset_filename, is_daily_double, is_used)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (round_id, col_idx, row_idx, cat_name, points, q_text, ans_text, asset, is_dd, is_used))
                    else:
                        cursor.execute("""
                        UPDATE questions SET round_id=?, col_index=?, row_index=?, category_name=?, points=?, question_text=?, answer_text=?, asset_filename=?, is_daily_double=?, is_used=?
                        WHERE id = ?
                        """, (round_id, col_idx, row_idx, cat_name, points, q_text, ans_text, asset, is_dd, is_used, int(id_text)))
                conn.commit()

            self._refresh_database_table()
            self._load_board_for_round(self.current_round)
            self._load_final_jeopardy_data()
            QMessageBox.information(self, "Lưu thành công", "Đã đồng bộ CSDL SQLite thành công!")
        except Exception as ex:
            QMessageBox.critical(self, "Lỗi lưu CSDL", str(ex))

    # =========================================================================
    # BOTTOM DOCK: LIVE SCORING CONSOLE
    # =========================================================================

    def _build_bottom_dock(self):
        self.score_dock = QDockWidget("BẢNG TÍNH ĐIỂM TRỰC TIẾP & CHUÔNG 3 NGƯỜI CHƠI (LIVE SCORING & BUZZER)", self)
        self.score_dock.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)

        dock_widget = QWidget()
        layout = QVBoxLayout(dock_widget)
        layout.setContentsMargins(14, 8, 14, 10)
        layout.setSpacing(8)

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

            lamp_lbl = QLabel("CHUÔNG SẴN SÀNG")
            lamp_lbl.setStyleSheet("background-color: #21262d; color: #3fb950; font-size: 10px; font-weight: bold; padding: 2px 6px; border-radius: 4px;")
            lamp_lbl.setAlignment(Qt.AlignCenter)

            top_p.addWidget(name_lbl)
            top_p.addStretch()
            top_p.addWidget(lamp_lbl)

            btn_buzzer = QPushButton("🔔 BẤM CHUÔNG")
            btn_buzzer.setStyleSheet("""
                QPushButton {
                    background-color: #d29922; color: #0d1117; font-weight: 900;
                    padding: 6px; font-size: 12px; border-radius: 5px;
                }
                QPushButton:hover { background-color: #e3b341; }
                QPushButton:disabled { background-color: #21262d; color: #484f58; }
            """)
            btn_buzzer.clicked.connect(lambda chk=False, pid=p_id: self._on_buzzer_pressed(pid))

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

            btn_c_add = QPushButton("+ Đúng")
            btn_c_add.setStyleSheet("background-color: #238636; color: white; font-weight: bold; padding: 5px;")
            btn_c_add.clicked.connect(lambda chk=False, pid=p_id, s=spin: self._adjust_score(pid, s.value(), True))

            btn_c_sub = QPushButton("- Sai")
            btn_c_sub.setStyleSheet("background-color: #da3633; color: white; font-weight: bold; padding: 5px;")
            btn_c_sub.clicked.connect(lambda chk=False, pid=p_id, s=spin: self._adjust_score(pid, s.value(), False))

            r2.addWidget(spin, 1)
            r2.addWidget(btn_c_add)
            r2.addWidget(btn_c_sub)

            c_lay.addLayout(top_p)
            c_lay.addWidget(btn_buzzer)
            c_lay.addWidget(score_lbl)
            c_lay.addLayout(r1)
            c_lay.addLayout(r2)

            self.score_cards[p_id] = {
                "card_frame": card,
                "name_lbl": name_lbl,
                "lamp_lbl": lamp_lbl,
                "btn_buzzer": btn_buzzer,
                "score_lbl": score_lbl,
                "btn_add": btn_add,
                "btn_sub": btn_sub,
                "spin": spin,
            }
            cards.addWidget(card)

        layout.addLayout(cards)

        bot = QHBoxLayout()
        btn_undo = QPushButton("↩ [Hoàn tác điểm số (Undo)]")
        btn_undo.setStyleSheet("background-color: #d29922; color: #0d1117; font-weight: bold; padding: 6px 16px;")
        btn_undo.clicked.connect(self._on_undo_score)

        btn_reset_buzzers = QPushButton("🔔 [Mở Khóa Chuông (Reset Buzzers)]")
        btn_reset_buzzers.setStyleSheet("background-color: #238636; color: white; font-weight: bold; padding: 6px 16px;")
        btn_reset_buzzers.clicked.connect(self._reset_buzzers)

        bot.addWidget(btn_undo)
        bot.addWidget(btn_reset_buzzers)
        bot.addStretch()
        layout.addLayout(bot)

        self.score_dock.setWidget(dock_widget)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.score_dock)

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
        event_bus.modify_score.emit(player_id, points, is_correct)
        event_bus.score_updated.emit(scores)

        # Tự động mở khóa chuông và dừng timer 5s khi cho điểm
        self._reset_buzzers()

    def _on_buzzer_pressed(self, player_id):
        if self.buzzer_locked:
            return
        self.buzzer_locked = True
        self.buzzer_active_player = player_id

        # Khóa 2 người còn lại, highlight người bấm
        for pid in ("p1", "p2", "p3"):
            card_data = self.score_cards[pid]
            if pid == player_id:
                card_data["card_frame"].setStyleSheet(
                    "background-color: #1a2234; border: 2px solid #FFD700; border-radius: 8px; padding: 8px;"
                )
                card_data["lamp_lbl"].setText("🔔 ĐÃ BẤM CHUÔNG!")
                card_data["lamp_lbl"].setStyleSheet(
                    "background-color: #FFD700; color: #000000; font-size: 10px; font-weight: 900; padding: 2px 6px; border-radius: 4px;"
                )
            else:
                card_data["card_frame"].setStyleSheet(
                    "background-color: #161b22; border: 1px solid #21262d; border-radius: 8px; padding: 8px;"
                )
                card_data["lamp_lbl"].setText("ĐÃ KHÓA")
                card_data["lamp_lbl"].setStyleSheet(
                    "background-color: #21262d; color: #484f58; font-size: 10px; font-weight: bold; padding: 2px 6px; border-radius: 4px;"
                )
                card_data["btn_buzzer"].setEnabled(False)

        # Bắn tín hiệu và phát âm thanh chuông
        event_bus.trigger_buzzer_press.emit(player_id)
        event_bus.play_sound_event.emit("time_out")

        # Tự động kích hoạt đồng hồ Host 5 giây
        self._start_host_timer_5s()

    def _reset_buzzers(self):
        self.buzzer_locked = False
        self.buzzer_active_player = None

        for pid in ("p1", "p2", "p3"):
            card_data = self.score_cards[pid]
            card_data["card_frame"].setStyleSheet(
                "background-color: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 8px;"
            )
            card_data["lamp_lbl"].setText("CHUÔNG SẴN SÀNG")
            card_data["lamp_lbl"].setStyleSheet(
                "background-color: #21262d; color: #3fb950; font-size: 10px; font-weight: bold; padding: 2px 6px; border-radius: 4px;"
            )
            card_data["btn_buzzer"].setEnabled(True)

        self._stop_host_timer_5s()
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
            event_bus.play_sound_event.emit("time_out")
            self.host_timer_lbl.setText("00.0s - HẾT GIỜ!")
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
            self.score_cards[p_id]["name_lbl"].setText(self.contestants[p_id]["name"])

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

            if hasattr(self, "wager_notes") and p_id in self.wager_notes:
                self.wager_notes[p_id].setText(f"Điểm: ${sc}")
                if not self.chk_manual_override.isChecked():
                    if sc > 0:
                        self.wager_spins[p_id].setRange(0, sc)
                        self.wager_spins[p_id].setValue(min(sc, 1000))
                        self.wager_spins[p_id].setEnabled(True)
                    else:
                        self.wager_spins[p_id].setRange(0, 1000)
                        self.wager_spins[p_id].setValue(0)

    # -------------------------------------------------------------------------
    # EVENT BUS HANDLERS
    # -------------------------------------------------------------------------

    def _register_event_bus(self):
        event_bus.score_updated.connect(self._on_score_updated)
        event_bus.change_round.connect(self._on_change_round)

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

    def closeEvent(self, event):
        reply = QMessageBox.question(
            self,
            "Xác nhận đóng và Reset",
            "Bạn có muốn Reset toàn bộ trạng thái ván đấu (Điểm về 0, mở lại tất cả câu hỏi đã dùng) trước khi thoát không?",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.s_engine.reset_scores()
            scores = self.s_engine.get_all_scores()
            for pid in self.contestants:
                self.contestants[pid]["score"] = 0
            event_bus.score_updated.emit(scores)
            self.q_engine.reset_all_used()
            event_bus.reset_game_state.emit()
            event.accept()
        elif reply == QMessageBox.No:
            event.accept()
        else:
            event.ignore()


# Backward compatibility alias
HostController = HostControllerWindow


# =============================================================================
# STANDALONE ENTRY POINT
# =============================================================================

def main():
    app = QApplication(sys.argv)
    window = HostControllerWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
