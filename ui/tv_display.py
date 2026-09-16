"""Open-J: TV Studio Broadcast Display Engine.
Full-screen secondary display window simulating industrial video wall TV bezel,
state machine visual sequences (Blank, Random Fill, Category Reveal with 3-layer slide transitions,
Point Zoom broadcast transitions, Clean Clue Cards, and Final Jeopardy dual-background screen),
AssetRenderer dual fitting (zoom vs tile), and audio subsystem synchronization via EventBus.
"""

import os
import sys
import random
from pathlib import Path
from typing import Dict, Optional, Tuple

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import Qt, QTimer, Slot, QPropertyAnimation, QEasingCurve, QRect, QParallelAnimationGroup, QPoint
from PySide6.QtGui import QFont, QColor, QPainter, QBrush, QPen, QPixmap, QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QStackedWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QProgressBar,
    QFrame,
    QSizePolicy,
    QPushButton,
    QGraphicsOpacityEffect,
    QGraphicsDropShadowEffect,
)

from core.event_bus import event_bus
from ui.audio_manager import AudioManager
from ui.theme_manager import AssetRenderer, ThemeConfigManager


FLAT_CARD_STYLE = """
    QFrame, QLabel, QWidget {
        border: none;
        outline: none;
        border-radius: 0px;
        background-color: transparent;
    }
"""


def draw_cover_image(painter: QPainter, target_rect: QRect, pixmap: QPixmap):
    """Phóng to theo cạnh lớn hơn để lấp đầy 100% diện tích (Full-Bleed Cover), căn giữa và crop mép thừa."""
    if not pixmap or pixmap.isNull():
        return
    scaled = pixmap.scaled(
        target_rect.size(),
        Qt.KeepAspectRatioByExpanding,
        Qt.SmoothTransformation
    )
    x = target_rect.x() + (target_rect.width() - scaled.width()) // 2
    y = target_rect.y() + (target_rect.height() - scaled.height()) // 2
    painter.save()
    painter.setClipRect(target_rect)
    painter.drawPixmap(x, y, scaled)
    painter.restore()


def draw_mosaic_tile(painter: QPainter, cell_rect: QRect, cell_in_grid: QRect, grid_rect: QRect, full_pixmap: QPixmap):
    """
    Vẽ từng mảnh của một bức ảnh duy nhất lên từng ô sao cho toàn bộ 36 ô
    tạo thành một bức tranh liền mạch bị chia cắt bởi viền Bezel.
    """
    if not full_pixmap or full_pixmap.isNull() or grid_rect.width() <= 0 or grid_rect.height() <= 0:
        return
    # Scale ảnh gốc phủ kín toàn bộ diện tích khung ma trận 6x6
    scaled_full = full_pixmap.scaled(
        grid_rect.size(),
        Qt.KeepAspectRatioByExpanding,
        Qt.SmoothTransformation
    )
    # Tọa độ offset căn giữa trong grid_rect
    offset_x = (scaled_full.width() - grid_rect.width()) // 2
    offset_y = (scaled_full.height() - grid_rect.height()) // 2
    
    # Tính tọa độ vùng cắt tương ứng của cell này trên ảnh lớn
    src_x = (cell_in_grid.x() - grid_rect.x()) + offset_x
    src_y = (cell_in_grid.y() - grid_rect.y()) + offset_y
    src_w = cell_in_grid.width()
    src_h = cell_in_grid.height()
    
    # Vẽ phần ảnh tương ứng vào cell_rect
    painter.drawPixmap(cell_rect, scaled_full, QRect(src_x, src_y, src_w, src_h))


class _CoverImageWidget(QWidget):
    """Widget chuyên vẽ ảnh phủ kín 100% không để dải màu thừa (Full-Bleed Cover) hoặc màu phẳng."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pixmap: Optional[QPixmap] = None
        self.bg_color = QColor("#060CE9")
        self.fallback_text = ""
        self.fallback_font = QFont("Impact", 72, QFont.Bold)
        self.fallback_color = QColor("#FFCC00")
        self.setStyleSheet(FLAT_CARD_STYLE)

    def set_pixmap(self, pixmap: Optional[QPixmap]):
        self.pixmap = pixmap
        self.update()

    def set_bg_color(self, color: QColor):
        self.bg_color = color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = self.rect()
        if self.pixmap and not self.pixmap.isNull():
            draw_cover_image(painter, rect, self.pixmap)
        else:
            painter.fillRect(rect, self.bg_color)
            if self.fallback_text:
                painter.setFont(self.fallback_font)
                painter.setPen(self.fallback_color)
                painter.drawText(rect, Qt.AlignCenter, self.fallback_text)


# =============================================================================
# 1. SQUARE BEZEL CELLS (CATEGORY HEADER & POINT CLUE CELLS)
# =============================================================================

class TVCategoryCell(QWidget):
    """
    Ô tiêu đề Chủ đề ở hàng trên cùng của ma trận 6 cột (Góc vuông 100%).
    Hỗ trợ 3 trạng thái:
    - is_mosaic == True: Hiển thị mảnh ghép trong bức tranh màn hình chờ 36 ô.
    - is_revealed == False: Hiển thị ảnh Unrevealed (Logo địa cầu Jeopardy!)
    - is_revealed == True: Hiển thị ảnh Revealed (hoặc nền tối) kèm tên chủ đề (font Clue)
    """

    def __init__(self, title="CHỦ ĐỀ", parent=None):
        super().__init__(parent)
        self.title = title
        self.is_revealed = False
        self.is_mosaic = False
        self.mosaic_pixmap: Optional[QPixmap] = None

        self.unrevealed_pixmap: Optional[QPixmap] = None
        self.revealed_pixmap: Optional[QPixmap] = None
        self.fit_mode = "zoom"

        self.font_family = "Georgia"
        self.font_size = 22
        self.font_bold = True
        self.text_color = QColor("#ffffff")
        self.bg_color = QColor("#000a8a")

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_title(self, title: str):
        self.title = title
        self.update()

    def set_revealed(self, revealed: bool):
        self.is_revealed = revealed
        self.update()

    def set_mosaic(self, enabled: bool, pixmap: Optional[QPixmap] = None):
        self.is_mosaic = enabled
        self.mosaic_pixmap = pixmap
        self.update()

    def set_images(self, unrevealed_path: str, revealed_path: str, fit_mode: str = "zoom"):
        self.fit_mode = fit_mode
        self.unrevealed_pixmap = QPixmap(unrevealed_path) if unrevealed_path and os.path.exists(unrevealed_path) else None
        self.revealed_pixmap = QPixmap(revealed_path) if revealed_path and os.path.exists(revealed_path) else None
        self.update()

    def set_font_config(self, family: str, size: int, bold: bool = True, color: str = "#ffffff"):
        self.font_family = family
        self.font_size = size
        self.font_bold = bold
        self.text_color = QColor(color)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.TextAntialiasing)

        rect = self.rect()

        if self.is_mosaic and self.mosaic_pixmap and not self.mosaic_pixmap.isNull():
            parent = self.parentWidget()
            if parent:
                top_left = self.mapTo(parent, QPoint(0, 0))
                cell_in_grid = QRect(top_left.x(), top_left.y(), self.width(), self.height())
                draw_mosaic_tile(painter, rect, cell_in_grid, parent.rect(), self.mosaic_pixmap)
                # Viền trong sắc nét
                painter.setPen(QPen(QColor(255, 255, 255, 25), 1))
                painter.drawRect(rect.adjusted(0, 0, -1, -1))
                return

        if not self.is_revealed:
            # Trạng thái chưa mở: Ưu tiên ảnh Logo địa cầu
            if self.unrevealed_pixmap and not self.unrevealed_pixmap.isNull():
                AssetRenderer.render_background(painter, rect, self.unrevealed_pixmap, self.fit_mode)
            else:
                painter.fillRect(rect, self.bg_color)
        else:
            # Trạng thái đã mở: Ảnh nền Revealed hoặc nền xanh đậm + Tên chủ đề
            if self.revealed_pixmap and not self.revealed_pixmap.isNull():
                AssetRenderer.render_background(painter, rect, self.revealed_pixmap, self.fit_mode)
            else:
                painter.fillRect(rect, self.bg_color)

            # Vẽ tên chủ đề (Font đồng bộ Clue font, in hoa, đổ bóng đen)
            font = QFont(self.font_family, self.font_size)
            font.setBold(self.font_bold)
            painter.setFont(font)

            # Drop shadow đen
            painter.setPen(QColor(0, 0, 0, 240))
            painter.drawText(rect.adjusted(3, 3, 3, 3), Qt.AlignCenter | Qt.TextWordWrap, str(self.title).upper())

            # Chữ trắng
            painter.setPen(self.text_color)
            painter.drawText(rect, Qt.AlignCenter | Qt.TextWordWrap, str(self.title).upper())

        # Viền trong sắc nét, vuông vức 100%
        painter.setPen(QPen(QColor(255, 255, 255, 35), 1))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))


class TVClueCell(QWidget):
    """
    Ô điểm số trong ma trận 6x5. Vuông vức 100%, chữ vàng cam có bóng đổ đen.
    Hỗ trợ tùy chọn: Dùng màu đặc HOẶC ảnh/texture nền via AssetRenderer.
    """

    STATE_BLANK = 0   # Nền trơn không có chữ
    STATE_POINTS = 1  # Bật sáng hiển thị giá trị điểm số
    STATE_USED = 2    # Đã mở câu hỏi -> Tắt đèn (nền tối đen)

    def __init__(self, points=200, parent=None):
        super().__init__(parent)
        self.points = points
        self.state = self.STATE_POINTS

        # Background mode
        self.use_image = True
        self.tile_pixmap: Optional[QPixmap] = None
        self.fit_mode = "zoom"
        self.solid_color = QColor("#060CE9")
        self.off_color = QColor("#020512")

        # Font & Text color
        self.font_family = "Impact"
        self.font_size = 48
        self.text_gold = QColor("#FFA500")
        self.is_mosaic = False
        self.mosaic_pixmap: Optional[QPixmap] = None

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_points(self, points: int):
        self.points = points
        self.update()

    def set_state(self, state: int):
        self.state = state
        self.update()

    def set_mosaic(self, enabled: bool, pixmap: Optional[QPixmap] = None):
        self.is_mosaic = enabled
        self.mosaic_pixmap = pixmap
        self.update()

    def set_visual_config(self, use_image: bool, image_path: str, solid_color: str, fit_mode: str = "zoom"):
        self.use_image = use_image
        self.fit_mode = fit_mode
        self.solid_color = QColor(solid_color)
        self.tile_pixmap = QPixmap(image_path) if image_path and os.path.exists(image_path) else None
        self.update()

    def set_font_config(self, family: str, size: int, bold: bool = True, color: str = "#FFA500"):
        self.font_family = family
        self.font_size = size
        self.text_gold = QColor(color)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.TextAntialiasing)

        rect = self.rect()

        if self.is_mosaic and self.mosaic_pixmap and not self.mosaic_pixmap.isNull():
            parent = self.parentWidget()
            if parent:
                top_left = self.mapTo(parent, QPoint(0, 0))
                cell_in_grid = QRect(top_left.x(), top_left.y(), self.width(), self.height())
                draw_mosaic_tile(painter, rect, cell_in_grid, parent.rect(), self.mosaic_pixmap)
                painter.setPen(QPen(QColor(255, 255, 255, 25), 1))
                painter.drawRect(rect.adjusted(0, 0, -1, -1))
                return

        if self.state == self.STATE_USED:
            painter.fillRect(rect, self.off_color)
            painter.setPen(QPen(QColor(255, 255, 255, 12), 1))
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
            return

        # Nền ô (Dùng ảnh hoặc Màu đặc)
        if self.use_image and self.tile_pixmap and not self.tile_pixmap.isNull():
            AssetRenderer.render_background(painter, rect, self.tile_pixmap, self.fit_mode)
        else:
            painter.fillRect(rect, self.solid_color)

        # Viền trong
        painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))

        if self.state == self.STATE_POINTS:
            font = QFont(self.font_family, self.font_size, QFont.Bold)
            painter.setFont(font)

            txt = str(self.points)

            # Drop shadow đen đậm
            painter.setPen(QColor(0, 0, 0, 245))
            painter.drawText(rect.adjusted(4, 4, 4, 4), Qt.AlignCenter, txt)

            # Chữ vàng cam / vàng chanh
            painter.setPen(self.text_gold)
            painter.drawText(rect, Qt.AlignCenter, txt)


# =============================================================================
# 2. POINT ZOOM WIDGET (POINT EXPANSION TRANSITION)
# =============================================================================

class TVPointZoomWidget(QWidget):
    """
    Widget phóng to toàn màn hình số điểm khổng lồ khi Host bấm mở ô câu hỏi.
    Hiệu ứng zoom mượt mà từ tọa độ ô điểm ra toàn màn hình (350-450ms OutCubic).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.points = 200
        self.use_image = True
        self.tile_pixmap: Optional[QPixmap] = None
        self.fit_mode = "zoom"
        self.solid_color = QColor("#060CE9")
        self.font_family = "Impact"
        self.font_size = 120
        self.text_gold = QColor("#FFA500")

        self.hide()

    def set_config(self, points: int, use_image: bool, pixmap: Optional[QPixmap], solid_color: QColor, fit_mode: str = "zoom", font_family: str = "Impact"):
        self.points = points
        self.use_image = use_image
        self.tile_pixmap = pixmap
        self.solid_color = solid_color
        self.fit_mode = fit_mode
        self.font_family = font_family
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.TextAntialiasing)

        rect = self.rect()

        if self.use_image and self.tile_pixmap and not self.tile_pixmap.isNull():
            AssetRenderer.render_background(painter, rect, self.tile_pixmap, self.fit_mode)
        else:
            painter.fillRect(rect, self.solid_color)

        # Viền đen ngoài cùng
        painter.setPen(QPen(QColor(0, 0, 0), 4))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))

        # Điểm số khổng lồ căn giữa (tỉ lệ font tự co dãn theo chiều cao ô)
        calc_size = max(36, int(rect.height() * 0.46))
        font = QFont(self.font_family, calc_size, QFont.Bold)
        painter.setFont(font)

        txt = str(self.points)

        # Drop shadow đen
        offset = max(3, int(calc_size * 0.08))
        painter.setPen(QColor(0, 0, 0, 245))
        painter.drawText(rect.adjusted(offset, offset, offset, offset), Qt.AlignCenter, txt)

        # Chữ vàng cam
        painter.setPen(self.text_gold)
        painter.drawText(rect, Qt.AlignCenter, txt)


# =============================================================================
# 3. CATEGORY REVEAL 3-LAYER TRANSITION CARD & ENGINE
# =============================================================================

class TVCategoryCardWidget(QWidget):
    """
    Khối Card đơn cho Category Reveal gồm 3 lớp phẳng hoàn toàn (Flat 100%):
    - Layer 1 (Card Background): Khung chữ nhật nền xanh texture/màu, vuông vức 100% (88% khung giữa).
    - Layer 2 (Category Title Text): Tên chủ đề in hoa, font Georgia đậm, căn giữa, đổ bóng đen (2,2).
    - Layer 3 (Logo Overlay): Ảnh Logo che phủ với QGraphicsOpacityEffect, phủ kín 100% qua draw_cover_image.
    """

    def __init__(self, logo_path=None, parent=None):
        super().__init__(parent)
        self.logo_path = logo_path
        self.setStyleSheet(FLAT_CARD_STYLE)

        self.title = "CHỦ ĐỀ"
        self.bg_color = QColor("#060CE9")
        self.bg_pixmap: Optional[QPixmap] = None

        # Layer 1: Blue Card Box (88% width, 88% height, centered)
        self.inner_box = _CoverImageWidget(self)
        self.inner_box.set_bg_color(self.bg_color)

        # Layer 2: Category Title Text
        self.title_label = QLabel(self.inner_box)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("color: #ffffff; background: transparent; border: none;")
        font = QFont("Georgia", 52, QFont.Bold)
        self.title_label.setFont(font)

        title_shadow = QGraphicsDropShadowEffect(self.title_label)
        title_shadow.setBlurRadius(2)
        title_shadow.setOffset(2, 2)
        title_shadow.setColor(QColor("#000000"))
        self.title_label.setGraphicsEffect(title_shadow)

        # Layer 3: Logo Overlay
        self.logo_overlay = _CoverImageWidget(self.inner_box)
        self.logo_overlay.fallback_text = "JEOPARDY!"
        self.logo_opacity = QGraphicsOpacityEffect(self.logo_overlay)
        self.logo_opacity.setOpacity(1.0)
        self.logo_overlay.setGraphicsEffect(self.logo_opacity)

        self._load_logo()

    def _load_logo(self):
        p = None
        if self.logo_path and os.path.exists(self.logo_path):
            p = QPixmap(self.logo_path)
        else:
            default_logo = PROJECT_ROOT / "ui" / "assets" / "images" / "header_logo.png"
            if default_logo.exists():
                p = QPixmap(str(default_logo))
        self.logo_overlay.set_pixmap(p)

    def set_logo(self, path: str):
        self.logo_path = path
        self._load_logo()

    def set_bg(self, image_path: str, hex_color: str):
        self.bg_color = QColor(hex_color)
        self.bg_pixmap = QPixmap(image_path) if image_path and os.path.exists(image_path) else None
        self.inner_box.set_pixmap(self.bg_pixmap)
        self.inner_box.set_bg_color(self.bg_color)
        self.logo_overlay.set_bg_color(self.bg_color)

    def set_category_title(self, title: str):
        self.title = str(title).upper()
        self.title_label.setText(self.title)
        self.reset_logo_opacity()

    def set_card_bg_color(self, hex_color: str):
        self.set_bg("", hex_color)

    def reset_logo_opacity(self):
        self.logo_opacity.setOpacity(1.0)

    def fade_out_logo(self, duration=500, finished_callback=None):
        self.anim = QPropertyAnimation(self.logo_opacity, b"opacity")
        self.anim.setDuration(duration)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.setEasingCurve(QEasingCurve.InOutQuad)
        if finished_callback:
            self.anim.finished.connect(finished_callback)
        self.anim.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        self.inner_box.setGeometry(0, 0, w, h)
        self.title_label.setGeometry(40, 40, max(1, w - 80), max(1, h - 80))
        self.logo_overlay.setGeometry(0, 0, w, h)


class TVCategoryRevealWidget(QWidget):
    """
    Transition Engine quản lý chuỗi trượt 6 chủ đề hoàn toàn thủ công theo lệnh Host (Manual Mode):
    - Không dùng timer tự động.
    - Hành động 1: Mở cột, Logo che kín 100% (Opacity = 1.0), TV đứng yên chờ lệnh.
    - Hành động 2: Host bấm -> Fade-out Logo từ 1.0 về 0.0 trong 500ms lộ tên chủ đề.
    - Hành động 3: Host bấm -> Trượt slide sang trái để nạp cột tiếp theo ở trạng thái Logo che kín.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #000000;")

        self.categories = [f"CHỦ ĐỀ {i+1}" for i in range(6)]
        self.current_index = 0
        self.logo_path = ""

        self.card_a = TVCategoryCardWidget(parent=self)
        self.card_b = TVCategoryCardWidget(parent=self)
        self.active_card = self.card_a
        self.next_card = self.card_b

    def set_categories(self, categories):
        self.categories = list(categories)

    def set_logo_path(self, path):
        self.logo_path = path
        self.card_a.set_logo(path)
        self.card_b.set_logo(path)

    def set_card_color(self, hex_color):
        self.card_a.set_card_bg_color(hex_color)
        self.card_b.set_card_bg_color(hex_color)

    def set_card_style(self, bg_image_path: str, hex_color: str):
        self.card_a.set_bg(bg_image_path, hex_color)
        self.card_b.set_bg(bg_image_path, hex_color)

    def show_column(self, col_index: int = 0):
        """Hành động 1: Mở cột tương ứng với Logo che kín 100%, chờ lệnh Host."""
        self.current_index = max(0, min(col_index, len(self.categories) - 1))
        w, h = self.width(), self.height()
        self.active_card = self.card_a
        self.next_card = self.card_b

        self.active_card.setGeometry(0, 0, w, h)
        self.next_card.setGeometry(w, 0, w, h)

        cat_title = self.categories[self.current_index] if self.current_index < len(self.categories) else f"CHỦ ĐỀ {self.current_index+1}"
        self.active_card.set_category_title(cat_title)
        self.active_card.reset_logo_opacity()
        self.active_card.show()
        self.next_card.show()

    def fade_logo(self):
        """Hành động 2: Kích hoạt animation làm mờ Logo từ 1.0 về 0.0 trong 500ms."""
        event_bus.play_sound_event.emit("category_intro")
        self.active_card.fade_out_logo(duration=500)

    @Slot()
    def slide_next(self):
        """Hành động 3: Trượt slide sang trái để nạp cột tiếp theo ở trạng thái Logo che kín."""
        self.current_index += 1
        if self.current_index >= len(self.categories):
            event_bus.close_question.emit()
            return

        w, h = self.width(), self.height()
        next_title = self.categories[self.current_index]
        self.next_card.set_category_title(next_title)
        self.next_card.reset_logo_opacity()
        self.next_card.setGeometry(w, 0, w, h)

        self.anim_group = QParallelAnimationGroup(self)

        anim_out = QPropertyAnimation(self.active_card, b"pos")
        anim_out.setDuration(550)
        anim_out.setStartValue(QPoint(0, 0))
        anim_out.setEndValue(QPoint(-w, 0))
        anim_out.setEasingCurve(QEasingCurve.InOutCubic)

        anim_in = QPropertyAnimation(self.next_card, b"pos")
        anim_in.setDuration(550)
        anim_in.setStartValue(QPoint(w, 0))
        anim_in.setEndValue(QPoint(0, 0))
        anim_in.setEasingCurve(QEasingCurve.InOutCubic)

        self.anim_group.addAnimation(anim_out)
        self.anim_group.addAnimation(anim_in)
        self.anim_group.finished.connect(self._on_slide_finished)

        event_bus.play_sound_event.emit("fill")
        self.anim_group.start()

    def _on_slide_finished(self):
        self.active_card, self.next_card = self.next_card, self.active_card

    def handle_manual_step(self, step: int):
        """Điều khiển từng bước từ Host."""
        if step == 0:
            self.show_column(self.current_index)
        elif step == 1:
            self.fade_logo()
        elif step >= 2:
            self.slide_next()

    def start_sequence(self, auto=False, start_col=0):
        self.show_column(start_col)

    def cancel(self):
        if hasattr(self, "anim_group"):
            self.anim_group.stop()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        if hasattr(self, "active_card"):
            self.active_card.resize(w, h)
        if hasattr(self, "next_card"):
            self.next_card.resize(w, h)


class TVClueScreenWidget(QWidget):
    """
    Khung câu hỏi chuẩn truyền hình phẳng 100% (Flat Design):
    - Phủ trọn vẹn 100% diện tích cửa sổ hiển thị (self.rect()), không viền đen ngoài.
    - Vẽ bằng QPainter: 0 inner borders, 0 box lines, 0 artifact.
    - Chữ trắng in hoa, font Georgia đậm, drop shadow đen (2,2).
    - Lớp hiển thị đáp án tùy chọn (Bottom Answer Overlay) cách mép đáy 50-70px, mặc định ẩn.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #000000; border: none;")
        self.question_text = ""
        self.bg_color = QColor("#060CE9")
        self.bg_pixmap: Optional[QPixmap] = None
        self.asset_pixmap: Optional[QPixmap] = None
        self.font_family = "Georgia"
        self.font_size = 48

        # Lớp hiển thị đáp án tùy chọn (Bottom Answer Overlay)
        self.answer_label = QLabel(self)
        self.answer_label.setAlignment(Qt.AlignCenter)
        self.answer_label.setWordWrap(True)
        self.answer_label.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 0, 0, 0.88);
                color: #EAFF00;
                font-family: Georgia;
                font-size: 28px;
                font-weight: 900;
                border: 2px solid #EAFF00;
                border-radius: 0px;
                padding: 6px 20px;
            }
        """)
        self.answer_label.setVisible(False)

    def set_clue(self, text: str, has_asset: bool = False, asset_path: str = ""):
        self.question_text = str(text).upper()
        if has_asset and asset_path and os.path.exists(asset_path):
            self.asset_pixmap = QPixmap(asset_path)
        else:
            self.asset_pixmap = None
        self.answer_label.setVisible(False)
        self.update()

    def set_answer_overlay(self, visible: bool, text: str = ""):
        if visible:
            display_text = f"ĐÁP ÁN: {str(text).upper()}" if text else "ĐÁP ÁN"
            self.answer_label.setText(display_text)
            self.answer_label.setVisible(True)
            self.answer_label.raise_()
        else:
            self.answer_label.setVisible(False)

    def set_card_visuals(self, use_image: bool, image_path: str, color_hex: str):
        self.bg_color = QColor(color_hex)
        if use_image and image_path and os.path.exists(image_path):
            self.bg_pixmap = QPixmap(image_path)
        else:
            self.bg_pixmap = None
        self.update()

    def set_font_config(self, family: str, size: int):
        self.font_family = family
        self.font_size = size
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.TextAntialiasing)

        w, h = self.width(), self.height()
        card_rect = QRect(0, 0, w, h)

        if self.bg_pixmap and not self.bg_pixmap.isNull():
            draw_cover_image(painter, card_rect, self.bg_pixmap)
        else:
            painter.fillRect(card_rect, self.bg_color)

        if self.asset_pixmap and not self.asset_pixmap.isNull():
            img_rect = QRect(60, 40, w - 120, int(h * 0.48))
            text_rect = QRect(60, int(h * 0.52), w - 120, int(h * 0.38))

            scaled_asset = self.asset_pixmap.scaled(img_rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            ax = img_rect.x() + (img_rect.width() - scaled_asset.width()) // 2
            ay = img_rect.y() + (img_rect.height() - scaled_asset.height()) // 2
            painter.drawPixmap(ax, ay, scaled_asset)

            font = QFont(self.font_family, max(24, int(self.font_size * 0.72)), QFont.Bold)
            painter.setFont(font)
            painter.setPen(QColor(0, 0, 0, 240))
            painter.drawText(text_rect.adjusted(2, 2, 2, 2), Qt.AlignCenter | Qt.TextWordWrap, self.question_text)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(text_rect, Qt.AlignCenter | Qt.TextWordWrap, self.question_text)
        else:
            text_rect = QRect(80, 50, w - 160, h - 140)
            font = QFont(self.font_family, self.font_size, QFont.Bold)
            painter.setFont(font)
            painter.setPen(QColor(0, 0, 0, 240))
            painter.drawText(text_rect.adjusted(2, 2, 2, 2), Qt.AlignCenter | Qt.TextWordWrap, self.question_text)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(text_rect, Qt.AlignCenter | Qt.TextWordWrap, self.question_text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        lbl_w = min(int(w * 0.85), 900)
        lbl_h = 56
        self.answer_label.setGeometry((w - lbl_w) // 2, h - 65 - lbl_h, lbl_w, lbl_h)


class TVFinalScreenWidget(QWidget):
    """
    Quy trình Vòng Final Jeopardy chuẩn hóa (3 bước + Cross-fade Xanh -> Đỏ sau 15s):
    - Bước 1 (trigger_final_step(1)): TV hiển thị ảnh Splash Final Logo phủ toàn màn hình (Full-Bleed Cover).
    - Bước 2 (trigger_final_step(2)): TV chuyển sang màn hình phẳng hiển thị Tên Chủ Đề in hoa, căn giữa.
    - Bước 3 (trigger_final_step(3)): TV mở màn hình Manh mối (Final Clue):
      * 2 lớp nền xếp chồng: Đáy là ĐỎ, Trên là XANH (opacity=1.0).
      * Bắt đầu đếm 30s think music.
      * Sau đúng 15 giây: Animation hạ Opacity nền Xanh từ 1.0 về 0.0 trong 2500ms -> Lộ nền Đỏ kịch tính.
    - Vinh danh Quán quân: ẨN HOÀN TOÀN TRÊN TV DISPLAY (chỉ hiện trên Host Controller).
    """
    STEP_SPLASH = 1
    STEP_CATEGORY = 2
    STEP_CLUE = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #000000; border: none;")
        self.step = self.STEP_SPLASH

        self.category_name = "FINAL JEOPARDY"
        self.clue_text = ""
        self.splash_pixmap: Optional[QPixmap] = None
        self.blue_pixmap: Optional[QPixmap] = None
        self.red_pixmap: Optional[QPixmap] = None
        self.blue_color = QColor("#060CE9")
        self.red_color = QColor("#8B0000")

        # 30s Countdown timer (100ms interval)
        self.countdown_ms = 30000
        self.countdown_timer = QTimer(self)
        self.countdown_timer.setInterval(100)
        self.countdown_timer.timeout.connect(self._on_countdown_tick)

        self._build_ui()

    def _build_ui(self):
        # 1. Step 1: Splash Widget (Full-bleed cover 100%)
        self.splash_widget = _CoverImageWidget(self)
        self.splash_widget.fallback_text = "FINAL JEOPARDY!"

        # 2. Step 2: Flat Category Widget
        self.cat_widget = QWidget(self)
        self.cat_widget.setStyleSheet("background-color: #000000; border: none;")

        self.cat_card = _CoverImageWidget(self.cat_widget)
        self.cat_card.set_bg_color(QColor("#0b1354"))

        self.cat_layout = QVBoxLayout(self.cat_card)
        self.cat_layout.setContentsMargins(40, 40, 40, 40)
        self.cat_layout.setAlignment(Qt.AlignCenter)

        self.cat_round_lbl = QLabel("VÒNG 3: FINAL JEOPARDY!", self.cat_card)
        self.cat_round_lbl.setAlignment(Qt.AlignCenter)
        self.cat_round_lbl.setStyleSheet("font-size: 28px; font-weight: bold; color: #FFA500; border: none; background: transparent;")

        self.cat_sub_lbl = QLabel("CHỦ ĐỀ:", self.cat_card)
        self.cat_sub_lbl.setAlignment(Qt.AlignCenter)
        self.cat_sub_lbl.setStyleSheet("font-size: 36px; font-weight: bold; color: #e6edf3; border: none; background: transparent;")

        self.cat_name_lbl = QLabel("TÊN CHỦ ĐỀ", self.cat_card)
        self.cat_name_lbl.setAlignment(Qt.AlignCenter)
        self.cat_name_lbl.setWordWrap(True)
        self.cat_name_lbl.setStyleSheet("font-size: 54px; font-weight: 900; color: #ffffff; border: none; background: transparent;")
        c_shadow = QGraphicsDropShadowEffect(self.cat_name_lbl)
        c_shadow.setBlurRadius(2)
        c_shadow.setOffset(2, 2)
        c_shadow.setColor(QColor("#000000"))
        self.cat_name_lbl.setGraphicsEffect(c_shadow)

        self.cat_layout.addWidget(self.cat_name_lbl)

        # 3. Step 3: Clue Widget with Stacked Backgrounds
        self.clue_widget = QWidget(self)
        self.clue_widget.setStyleSheet("background-color: #000000; border: none;")

        self.clue_card = QWidget(self.clue_widget)
        self.clue_card.setStyleSheet(FLAT_CARD_STYLE)

        # Bottom layer: Red Card
        self.red_layer = _CoverImageWidget(self.clue_card)
        self.red_layer.set_bg_color(self.red_color)

        # Top layer: Blue Card with Opacity Effect
        self.blue_layer = _CoverImageWidget(self.clue_card)
        self.blue_layer.set_bg_color(self.blue_color)
        self.blue_opacity = QGraphicsOpacityEffect(self.blue_layer)
        self.blue_opacity.setOpacity(1.0)
        self.blue_layer.setGraphicsEffect(self.blue_opacity)

        # Foreground content (CHỈ HIỂN THỊ NỘI DUNG MANH MỐI, KHÔNG METADATA, KHÔNG THANH ĐEN)
        self.clue_fg = QWidget(self.clue_card)
        self.clue_fg.setStyleSheet(FLAT_CARD_STYLE)
        fg_layout = QVBoxLayout(self.clue_fg)
        fg_layout.setContentsMargins(60, 40, 60, 40)
        fg_layout.setAlignment(Qt.AlignCenter)

        # Dummy hidden labels for backward compatibility
        self.clue_title_lbl = QLabel("", self.clue_fg)
        self.clue_title_lbl.setVisible(False)
        self.progress_bar = QProgressBar(self.clue_fg)
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 300)
        self.progress_bar.setValue(300)

        self.clue_content_lbl = QLabel("CÂU HỎI MANH MỐI", self.clue_fg)
        self.clue_content_lbl.setAlignment(Qt.AlignCenter)
        self.clue_content_lbl.setWordWrap(True)
        self.clue_content_lbl.setStyleSheet("font-size: 50px; font-weight: 900; color: #ffffff; border: none; background: transparent;")
        clue_shadow = QGraphicsDropShadowEffect(self.clue_content_lbl)
        clue_shadow.setBlurRadius(2)
        clue_shadow.setOffset(2, 2)
        clue_shadow.setColor(QColor("#000000"))
        self.clue_content_lbl.setGraphicsEffect(clue_shadow)

        # Lớp hiển thị đáp án tùy chọn (Bottom Answer Overlay)
        self.answer_label = QLabel(self.clue_fg)
        self.answer_label.setAlignment(Qt.AlignCenter)
        self.answer_label.setWordWrap(True)
        self.answer_label.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 0, 0, 0.88);
                color: #EAFF00;
                font-family: Georgia;
                font-size: 28px;
                font-weight: 900;
                border: 2px solid #EAFF00;
                border-radius: 0px;
                padding: 6px 20px;
            }
        """)
        self.answer_label.setVisible(False)

        fg_layout.addWidget(self.clue_content_lbl, 1)

        self._update_visibility()

    def set_answer_overlay(self, visible: bool, text: str = ""):
        if visible:
            display_text = f"ĐÁP ÁN: {str(text).upper()}" if text else "ĐÁP ÁN"
            self.answer_label.setText(display_text)
            self.answer_label.setVisible(True)
            self.answer_label.raise_()
        else:
            self.answer_label.setVisible(False)

    def set_visuals(self, splash_path: str, blue_path: str, blue_color: str, red_path: str, red_color: str):
        if splash_path and os.path.exists(splash_path):
            self.splash_pixmap = QPixmap(splash_path)
        else:
            def_splash = PROJECT_ROOT / "ui" / "assets" / "images" / "final_jeopardy_logo.png"
            self.splash_pixmap = QPixmap(str(def_splash)) if def_splash.exists() else None
        self.splash_widget.set_pixmap(self.splash_pixmap)

        self.blue_color = QColor(blue_color)
        self.blue_pixmap = QPixmap(blue_path) if blue_path and os.path.exists(blue_path) else None
        self.blue_layer.set_pixmap(self.blue_pixmap)
        self.blue_layer.set_bg_color(self.blue_color)

        # Set category card background
        self.cat_card.set_pixmap(self.blue_pixmap)
        self.cat_card.set_bg_color(self.blue_color)

        self.red_color = QColor(red_color)
        self.red_pixmap = QPixmap(red_path) if red_path and os.path.exists(red_path) else None
        self.red_layer.set_pixmap(self.red_pixmap)
        self.red_layer.set_bg_color(self.red_color)

    def set_step(self, step: int, data: dict):
        self.step = step
        self.answer_label.setVisible(False)
        if step == self.STEP_SPLASH:
            self.countdown_timer.stop()
            self._update_visibility()

        elif step == self.STEP_CATEGORY:
            self.countdown_timer.stop()
            cat = data.get("category") or data.get("category_name") or "FINAL JEOPARDY"
            self.cat_name_lbl.setText(str(cat).upper())
            self._update_visibility()

        elif step == self.STEP_CLUE:
            clue = data.get("question_text", "")
            self.clue_content_lbl.setText(str(clue).upper())
            self.blue_opacity.setOpacity(1.0)
            self.progress_bar.setValue(300)
            self.countdown_ms = 30000
            self.countdown_timer.start()
            self._update_visibility()

            # Trigger 2.5s Cross-fade after 15 seconds
            QTimer.singleShot(15000, self.start_crossfade)

    def start_crossfade(self):
        """Kích hoạt hiệu ứng chuyển nền từ XANH sang ĐỎ trong 2500ms."""
        if self.step != self.STEP_CLUE:
            return
        if hasattr(self, "crossfade_anim") and self.crossfade_anim.state() == QPropertyAnimation.Running:
            return
        self.crossfade_anim = QPropertyAnimation(self.blue_opacity, b"opacity")
        self.crossfade_anim.setDuration(2500)
        self.crossfade_anim.setStartValue(1.0)
        self.crossfade_anim.setEndValue(0.0)
        self.crossfade_anim.setEasingCurve(QEasingCurve.InOutQuad)
        self.crossfade_anim.start()

    def _on_countdown_tick(self):
        self.countdown_ms -= 100
        val = max(0, int(self.countdown_ms / 100))
        self.progress_bar.setValue(val)
        if self.countdown_ms <= 0:
            self.countdown_timer.stop()

    def _update_visibility(self):
        self.splash_widget.setVisible(self.step == self.STEP_SPLASH)
        self.cat_widget.setVisible(self.step == self.STEP_CATEGORY)
        self.clue_widget.setVisible(self.step == self.STEP_CLUE)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        self.splash_widget.setGeometry(0, 0, w, h)
        self.cat_widget.setGeometry(0, 0, w, h)
        self.clue_widget.setGeometry(0, 0, w, h)

        self.cat_card.setGeometry(0, 0, w, h)
        self.clue_card.setGeometry(0, 0, w, h)

        self.red_layer.setGeometry(0, 0, w, h)
        self.blue_layer.setGeometry(0, 0, w, h)
        self.clue_fg.setGeometry(0, 0, w, h)

        lbl_w = min(int(w * 0.85), 900)
        lbl_h = 56
        self.answer_label.setGeometry((w - lbl_w) // 2, h - 65 - lbl_h, lbl_w, lbl_h)


# =============================================================================
# 4. TV STUDIO DISPLAY WINDOW (MAIN STAGE)
# =============================================================================

class TVDisplayWindow(QMainWindow):
    """Cửa sổ hiển thị Màn hình TV Studio / Video Wall chuẩn phát sóng."""

    INDEX_BOARD = 0
    INDEX_CATEGORY_REVEAL = 1
    INDEX_DAILY_DOUBLE = 2
    INDEX_QUESTION = 3
    INDEX_FINAL = 4
    INDEX_STANDBY_NORMAL = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Open-J | TV Studio Broadcast Display")
        self.resize(1024, 576)
        self.setMinimumSize(800, 450)
        self.setStyleSheet("background-color: #000000;")

        # Audio Subsystem
        self.audio_manager = AudioManager(parent=self)

        # Load Theme Config
        self.theme = ThemeConfigManager.load_theme_xml()
        self.bezel_width = self.theme.get("bezel_width", 8)
        self.bezel_color = QColor(self.theme.get("bezel_color", "#000000"))
        self.standby_pixmap: Optional[QPixmap] = None

        # Board State
        self.current_round = 1
        self.category_names = [f"CHỦ ĐỀ {i+1}" for i in range(6)]
        self.cells: Dict[Tuple[int, int], TVClueCell] = {}
        self.cat_cells = []
        self.current_opened_coords = None
        self.pending_clue_payload = None

        # Random Fill Timer
        self.fill_timer = QTimer(self)
        self.fill_timer.setInterval(60)
        self.fill_timer.timeout.connect(self._on_fill_timer_tick)
        self.fill_queue = []

        # View Stack
        self.stack = QStackedWidget(self)
        self.setCentralWidget(self.stack)

        self._build_page_board()
        self._build_page_category_reveal()
        self._build_page_daily_double()
        self._build_page_clean_clue()
        self._build_page_final()
        self._build_page_standby()

        self.clue_screen = self.clue_screen_widget
        self.final_screen = self.final_screen_widget

        # Zoom overlay widget
        self.point_zoom_widget = TVPointZoomWidget(self)


        self.stack.setCurrentIndex(self.INDEX_BOARD)

        # Register EventBus Handlers
        self._register_event_bus()
        self.apply_theme_config(self.theme)
        self._setup_default_board()

    # -------------------------------------------------------------------------
    # WINDOW MANAGEMENT & OBS HOTKEY (F11)
    # -------------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_F11:
            self.toggle_fullscreen()
            event.accept()
            return
        super().keyPressEvent(event)

    @Slot()
    def toggle_fullscreen(self):
        """Chuyển đổi tức thì giữa Borderless Fullscreen và Windowed mode cho OBS."""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    # -------------------------------------------------------------------------
    # UI PAGE BUILDERS
    # -------------------------------------------------------------------------

    def _build_page_board(self):
        """Ma trận 6x6 (1 hàng chủ đề + 5 hàng điểm) với Bezel đen công nghiệp."""
        self.board_container = QWidget()
        self.board_container.setStyleSheet(f"background-color: {self.bezel_color.name()};")

        self.board_grid = QGridLayout(self.board_container)
        self.board_grid.setContentsMargins(self.bezel_width, self.bezel_width, self.bezel_width, self.bezel_width)
        self.board_grid.setSpacing(self.bezel_width)

        # 6 Category Headers (row 0)
        self.cat_cells = []
        for c in range(6):
            cell = TVCategoryCell(self.category_names[c])
            self.cat_cells.append(cell)
            self.board_grid.addWidget(cell, 0, c)

        # 30 Clue Cells (rows 1-5, cols 0-5)
        self.cells = {}
        for r in range(5):
            pts = (r + 1) * 200
            for c in range(6):
                cell = TVClueCell(points=pts)
                self.cells[(c, r)] = cell
                self.board_grid.addWidget(cell, r + 1, c)

        self.stack.addWidget(self.board_container)  # INDEX_BOARD = 0

    def _build_page_category_reveal(self):
        """Category Reveal Engine 3 lớp."""
        self.cat_reveal_widget = TVCategoryRevealWidget(self)
        self.cat_reveal_widget.set_categories(self.category_names)
        self.stack.addWidget(self.cat_reveal_widget)  # INDEX_CATEGORY_REVEAL = 1

    def _build_page_daily_double(self):
        """Màn hình Daily Double Splash Image Graphic (Full-Bleed Cover)."""
        self.dd_splash_widget = _CoverImageWidget(self)
        self.dd_splash_widget.fallback_text = "DAILY DOUBLE"
        self.stack.addWidget(self.dd_splash_widget)  # INDEX_DAILY_DOUBLE = 2

    def _build_page_clean_clue(self):
        """Khung câu hỏi chuẩn truyền hình phẳng 100% (Flat Design)."""
        self.clue_screen_widget = TVClueScreenWidget(self)
        self.stack.addWidget(self.clue_screen_widget)  # INDEX_QUESTION = 3

    def _build_page_final(self):
        """Vòng 3 Final Jeopardy Sequencer (3 bước + Cross-fade Xanh -> Đỏ)."""
        self.final_screen_widget = TVFinalScreenWidget(self)
        self.stack.addWidget(self.final_screen_widget)  # INDEX_FINAL = 4

    def _build_page_standby(self):
        """Màn hình Chờ Thường (Standard Standby Wallpaper Full-Bleed 100%)."""
        self.standby_normal_widget = _CoverImageWidget(self)
        self.standby_normal_widget.fallback_text = "JEOPARDY!"
        self.stack.addWidget(self.standby_normal_widget)  # INDEX_STANDBY_NORMAL = 5

    # --- Backward compatibility properties ---
    @property
    def final_title(self):
        return self.final_screen_widget.clue_title_lbl

    @property
    def final_content(self):
        return self.final_screen_widget.clue_content_lbl

    @property
    def final_progress(self):
        return self.final_screen_widget.progress_bar

    @property
    def final_logo_label(self):
        return self.final_screen_widget.splash_widget

    @property
    def final_countdown_timer(self):
        return self.final_screen_widget.countdown_timer

    @property
    def clue_card(self):
        return self.clue_screen_widget

    @property
    def dd_splash_label(self):
        return self.dd_splash_widget

    @property
    def category_reveal_widget(self):
        return self.cat_reveal_widget

    # -------------------------------------------------------------------------
    # STATE MACHINE ACTIONS
    # -------------------------------------------------------------------------

    def _setup_default_board(self):
        base = 200 if self.current_round == 1 else 400
        for r in range(5):
            pts = (r + 1) * base
            for c in range(6):
                cell = self.cells.get((c, r))
                if cell:
                    cell.set_points(pts)
                    cell.set_state(TVClueCell.STATE_POINTS)

    @Slot()
    def show_blank_board(self):
        """Bảng trống (chỉ hiện bezel và ô trơn)."""
        self.fill_timer.stop()
        self.stack.setCurrentIndex(self.INDEX_BOARD)
        for cell in self.cells.values():
            cell.set_state(TVClueCell.STATE_BLANK)

    @Slot()
    def start_board_fill(self):
        """Lật mở ngẫu nhiên 30 ô. Chỉ phát 1 file âm thanh mở bảng duy nhất khi bắt đầu."""
        self.show_blank_board()
        all_coords = [(c, r) for c in range(6) for r in range(5)]
        random.shuffle(all_coords)
        self.fill_queue = all_coords
        event_bus.play_sound_event.emit("board_fill")
        self.fill_timer.start()

    def _on_fill_timer_tick(self):
        if not self.fill_queue:
            self.fill_timer.stop()
            return
        c, r = self.fill_queue.pop(0)
        cell = self.cells.get((c, r))
        if cell:
            cell.set_state(TVClueCell.STATE_POINTS)

    # --- CATEGORY REVEAL SLIDE ENGINE (MANUAL MODE) ---
    @Slot(dict)
    def handle_category_reveal(self, config=None):
        if config is None:
            config = {"auto": False, "step": 0, "col_index": 0}
        start_col = int(config.get("col_index", 0))
        self.handle_category_show_logo(start_col)

    @Slot(int)
    def handle_category_show_logo(self, col_index: int = 0):
        """Hành động 1: Mở cột tương ứng với Logo che kín tên chủ đề, đứng im chờ Host."""
        cats = [self.cat_cells[i].title for i in range(6)]
        self.cat_reveal_widget.set_categories(cats)
        self.stack.setCurrentIndex(self.INDEX_CATEGORY_REVEAL)
        self.cat_reveal_widget.show_column(col_index)

    @Slot()
    def handle_category_fade_logo(self):
        """Hành động 2: Kích hoạt fade-out mở tên chủ đề trong 500ms."""
        if self.stack.currentIndex() == self.INDEX_CATEGORY_REVEAL:
            self.cat_reveal_widget.fade_logo()

    @Slot()
    def handle_category_slide_next(self):
        """Hành động 3: Trượt sang cột tiếp theo ở trạng thái Logo che kín."""
        if self.stack.currentIndex() == self.INDEX_CATEGORY_REVEAL:
            self.cat_reveal_widget.slide_next()

    @Slot(int)
    def handle_category_reveal_step(self, step: int):
        """Tương thích ngược: điều khiển bước 0 (Logo), 1 (Fade), 2 (Slide next)."""
        if self.stack.currentIndex() != self.INDEX_CATEGORY_REVEAL:
            cats = [self.cat_cells[i].title for i in range(6)]
            self.cat_reveal_widget.set_categories(cats)
            self.stack.setCurrentIndex(self.INDEX_CATEGORY_REVEAL)
            self.cat_reveal_widget.show_column(0)
        self.cat_reveal_widget.handle_manual_step(step)

    @Slot()
    def handle_category_next(self):
        self.handle_category_slide_next()

    @Slot()
    def handle_cancel_category_reveal(self):
        if self.stack.currentIndex() == self.INDEX_CATEGORY_REVEAL:
            self.cat_reveal_widget.cancel()
            self.stack.setCurrentIndex(self.INDEX_BOARD)

    # --- POINT ZOOM TRANSITION & 2-STEP AIRING FLOW ---
    @Slot(dict)
    def handle_request_clue_zoom(self, payload: dict):
        """Nhịp 1: Kích hoạt zoom phóng to số điểm ô được chọn ra toàn màn hình."""
        self.pending_clue_payload = dict(payload)
        col = payload.get("col_index", 0)
        row = payload.get("row_index", 0)
        self.current_opened_coords = (col, row)

        cell = self.cells.get((col, row))
        if not cell:
            self.show_question(payload)
            return

        cell_rect = cell.geometry()

        top_left = cell.mapTo(self, QPoint(0, 0))
        origin_rect = QRect(top_left.x(), top_left.y(), cell_rect.width(), cell_rect.height())
        target_rect = QRect(0, 0, self.width(), self.height())

        pts = payload.get("points", cell.points)
        self.point_zoom_widget.set_config(
            points=pts,
            use_image=cell.use_image,
            pixmap=cell.tile_pixmap,
            solid_color=cell.solid_color,
            fit_mode=cell.fit_mode,
            font_family=cell.font_family
        )
        self.point_zoom_widget.setGeometry(origin_rect)
        self.point_zoom_widget.show()
        self.point_zoom_widget.raise_()

        self.zoom_anim = QPropertyAnimation(self.point_zoom_widget, b"geometry")
        self.zoom_anim.setDuration(400)
        self.zoom_anim.setStartValue(origin_rect)
        self.zoom_anim.setEndValue(target_rect)
        self.zoom_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.zoom_anim.finished.connect(self._on_zoom_animation_finished)
        self.zoom_anim.start()

    def _on_zoom_animation_finished(self):
        """Nhịp 1 hoàn tất: TV dừng lại giữ nguyên trạng thái (Zoom Điểm hoặc Daily Double)."""
        if not self.pending_clue_payload:
            return

        payload = self.pending_clue_payload
        if payload.get("is_daily_double"):
            self.point_zoom_widget.hide()
            splash_path = self.theme.get("visual_fx", {}).get("daily_double_splash", "")
            if not splash_path or not os.path.exists(splash_path):
                splash_path = str(PROJECT_ROOT / "ui" / "assets" / "images" / "daily_double.png")

            self.show_daily_double_splash(splash_path)
            event_bus.play_sound_event.emit("daily_double")
        else:
            # Giữ nguyên số điểm khổng lồ lấp kín toàn màn hình TV
            self.point_zoom_widget.setGeometry(0, 0, self.width(), self.height())
            self.point_zoom_widget.show()
            self.point_zoom_widget.raise_()

    @Slot()
    def handle_clue_reveal(self):
        """Nhịp 2: Sau khi Host bấm xác nhận mở câu hỏi, TV mới chính thức chuyển cảnh sang thẻ câu hỏi."""
        if self.pending_clue_payload:
            self.show_question(self.pending_clue_payload)

    handle_clue_zoom = handle_request_clue_zoom


    @Slot(str)
    def show_daily_double_splash(self, splash_path: str):
        """Hiển thị đồ họa Daily Double của người dùng (Full-Bleed Cover)."""
        if splash_path and os.path.exists(splash_path):
            pix = QPixmap(splash_path)
            self.dd_splash_widget.set_pixmap(pix)
        else:
            def_splash = PROJECT_ROOT / "ui" / "assets" / "images" / "daily_double.png"
            pix = QPixmap(str(def_splash)) if def_splash.exists() else None
            self.dd_splash_widget.set_pixmap(pix)
        self.stack.setCurrentIndex(self.INDEX_DAILY_DOUBLE)

    # --- CLEAN CLUE DISPLAY (FLAT 100%) ---
    @Slot(dict)
    def show_question(self, question_data: dict = None):
        if question_data is None:
            question_data = self.pending_clue_payload or {}
        self.point_zoom_widget.hide()
        col = question_data.get("col_index", 0)
        row = question_data.get("row_index", 0)
        self.current_opened_coords = (col, row)

        raw_text = question_data.get("question_text", "")
        has_asset = question_data.get("has_asset", False)
        asset_path = question_data.get("asset_path", "")

        self.clue_screen_widget.set_clue(raw_text, has_asset, asset_path)
        self.stack.setCurrentIndex(self.INDEX_QUESTION)

    @Slot()
    def close_question(self):
        self.point_zoom_widget.hide()
        self.clue_screen_widget.set_answer_overlay(False)
        self.final_screen_widget.set_answer_overlay(False)
        if self.current_opened_coords:
            cell = self.cells.get(self.current_opened_coords)
            if cell:
                cell.set_state(TVClueCell.STATE_USED)
        self.stack.setCurrentIndex(self.INDEX_BOARD)

    @Slot(bool, str)
    def handle_toggle_tv_answer(self, is_visible: bool, answer_text: str = ""):
        """Bật/tắt thanh hiển thị đáp án tùy chọn (Bottom Answer Overlay)."""
        curr = self.stack.currentIndex()
        if curr == self.INDEX_QUESTION:
            self.clue_screen_widget.set_answer_overlay(is_visible, answer_text)
        elif curr == self.INDEX_FINAL:
            self.final_screen_widget.set_answer_overlay(is_visible, answer_text)

    handle_toggle_answer = handle_toggle_tv_answer

    # --- STANDBY ENGINE (NORMAL & MOSAIC 36 Ô) ---

    @Slot(str)
    def handle_standby_mode(self, mode: str):
        mode = (mode or "").lower()
        if mode == "normal":
            self._set_mosaic_mode(False)
            self.stack.setCurrentIndex(self.INDEX_STANDBY_NORMAL)
        elif mode == "mosaic":
            self._set_mosaic_mode(True)
            self.stack.setCurrentIndex(self.INDEX_BOARD)
        else: # "off"
            self._set_mosaic_mode(False)
            self.stack.setCurrentIndex(self.INDEX_BOARD)

    def _set_mosaic_mode(self, enabled: bool):
        pix = self.standby_pixmap if enabled else None
        for cell in self.cat_cells:
            cell.set_mosaic(enabled, pix)
        for cell in self.cells.values():
            cell.set_mosaic(enabled, pix)

    @Slot()
    def handle_reset_game_state(self):
        """Đặt lại toàn bộ trạng thái TV về ban đầu."""
        self.close_question()
        self._setup_default_board()

    # --- FINAL JEOPARDY TRANSITIONS (3 STEPS + 15S CROSS-FADE) ---
    @Slot(int, dict)
    def handle_final_step(self, step: int, data: dict):
        """Điều phối 3 bước Vòng Final Jeopardy. Bảng điểm quán quân chỉ hiện trên Host, ẩn 100% trên TV."""
        if step in (1, 2, 3):
            self.stack.setCurrentIndex(self.INDEX_FINAL)
            self.final_screen_widget.set_step(step, data)
        # Nếu step >= 4 (hoặc tổng kết điểm): KHÔNG hiển thị màn hình vinh danh lên TV!

    @Slot()
    def handle_final_crossfade(self):
        """Kích hoạt đổi nền Xanh -> Đỏ."""
        if self.stack.currentIndex() == self.INDEX_FINAL:
            self.final_screen_widget.start_crossfade()

    # -------------------------------------------------------------------------
    # ROUND AND THEME CONFIGURATION
    # -------------------------------------------------------------------------

    @Slot(int)
    def handle_change_round(self, round_id: int):
        self.current_round = round_id
        base = 200 if round_id == 1 else 400
        for r in range(5):
            pts = (r + 1) * base
            for c in range(6):
                cell = self.cells.get((c, r))
                if cell:
                    cell.set_points(pts)
                    cell.set_state(TVClueCell.STATE_POINTS)

    @Slot()
    def reload_theme_from_disk(self):
        """Tải lại theme.xml từ ổ đĩa và áp dụng ngay lập tức."""
        self.theme = ThemeConfigManager.load_theme_xml()
        self.apply_theme_config(self.theme)

    @Slot(dict)
    def apply_theme_config(self, theme_data: dict):
        self.theme = theme_data

        # 1. Bezel
        bw = int(theme_data.get("bezel_width", 8))
        bc = str(theme_data.get("bezel_color", "#000000"))
        self.bezel_width = bw
        self.bezel_color = QColor(bc)

        self.board_container.setStyleSheet(f"background-color: {bc};")
        self.board_grid.setContentsMargins(bw, bw, bw, bw)
        self.board_grid.setSpacing(bw)

        # 2. Category Headers
        ch_data = theme_data.get("category_headers", {})
        unrev_p = ch_data.get("unrevealed_image", "")
        rev_p = ch_data.get("revealed_image", "")
        fit_m = ch_data.get("fit_mode", "zoom")
        f_info = ch_data.get("font", {"family": "Georgia", "size": 28, "bold": True, "color": "#FFFFFF"})

        for cell in self.cat_cells:
            cell.set_images(unrev_p, rev_p, fit_m)
            cell.set_font_config(
                f_info.get("family", "Georgia"),
                int(f_info.get("size", 28)),
                bool(f_info.get("bold", True)),
                f_info.get("color", "#FFFFFF")
            )

        # 3. Point Grid
        pg_data = theme_data.get("point_grid", {})
        use_img = pg_data.get("use_image", True)
        tile_p = pg_data.get("tile_image", "")
        sol_col = pg_data.get("solid_color", "#060CE9")
        pg_fit = pg_data.get("fit_mode", "zoom")
        pg_font = pg_data.get("font", {"family": "Impact", "size": 48, "bold": True, "color": "#FFA500"})

        for cell in self.cells.values():
            cell.set_visual_config(use_img, tile_p, sol_col, pg_fit)
            cell.set_font_config(
                pg_font.get("family", "Impact"),
                int(pg_font.get("size", 48)),
                bool(pg_font.get("bold", True)),
                pg_font.get("color", "#FFA500")
            )

        # 4. Clue Screen Card (Flat 100%)
        cs_data = theme_data.get("clue_screen", {})
        std_card = cs_data.get("standard_card", {})
        std_img = std_card.get("image_path", "")
        std_col = std_card.get("color", "#060CE9")
        std_use = std_card.get("use_image", True)
        cs_font = cs_data.get("font", {"family": "Georgia", "size": 48, "bold": True, "color": "#FFFFFF"})

        self.clue_screen_widget.set_card_visuals(std_use, std_img, std_col)
        self.clue_screen_widget.set_font_config(cs_font.get("family", "Georgia"), int(cs_font.get("size", 48)))

        # 5. Final Jeopardy Visuals
        fin_card = cs_data.get("final_card", {})
        fin_img = fin_card.get("image_path", "")
        fin_col = fin_card.get("color", "#8B0000")
        vfx = theme_data.get("visual_fx", {})
        splash_p = vfx.get("final_logo_splash", "")
        self.final_screen_widget.set_visuals(splash_p, std_img, std_col, fin_img, fin_col)

        # 6. Category Reveal Logo & Style
        logo_cand = unrev_p if unrev_p and os.path.exists(unrev_p) else theme_data.get("logo_path", "")
        self.cat_reveal_widget.set_logo_path(logo_cand)
        self.cat_reveal_widget.set_card_style(rev_p, std_col)

        # 7. Standby Screen Wallpaper (Thường & Mosaic 36 ô)
        sb_img = theme_data.get("standby_screen", {}).get("image_path", "")
        if sb_img and os.path.exists(sb_img):
            self.standby_pixmap = QPixmap(sb_img)
        else:
            def_sb = PROJECT_ROOT / "ui" / "assets" / "images" / "header_revealed_bg.png"
            self.standby_pixmap = QPixmap(str(def_sb)) if def_sb.exists() else None
        self.standby_normal_widget.set_pixmap(self.standby_pixmap)

        # 8. Audio Manager Sync
        sounds_dict = theme_data.get("sounds", {})
        if sounds_dict:
            self.audio_manager.load_from_dict(sounds_dict)

    # -------------------------------------------------------------------------
    # EVENT BUS INTEGRATION
    # -------------------------------------------------------------------------

    def _register_event_bus(self):
        event_bus.trigger_board_blank.connect(self.show_blank_board)
        event_bus.trigger_board_fill.connect(self.start_board_fill)
        event_bus.trigger_category_reveal.connect(self.handle_category_reveal)
        event_bus.trigger_category_reveal_step.connect(self.handle_category_reveal_step)
        event_bus.trigger_category_show_logo.connect(self.handle_category_show_logo)
        event_bus.trigger_category_fade_logo.connect(self.handle_category_fade_logo)
        event_bus.trigger_category_slide_next.connect(self.handle_category_slide_next)
        event_bus.trigger_category_next.connect(self.handle_category_next)
        event_bus.cancel_category_reveal.connect(self.handle_cancel_category_reveal)
        event_bus.request_clue_zoom.connect(self.handle_request_clue_zoom)
        event_bus.trigger_clue_zoom.connect(self.handle_request_clue_zoom)
        event_bus.trigger_clue_reveal.connect(self.handle_clue_reveal)
        event_bus.trigger_daily_double_splash.connect(self.show_daily_double_splash)
        event_bus.display_question.connect(self.show_question)
        event_bus.close_question.connect(self.close_question)
        event_bus.toggle_tv_answer.connect(self.handle_toggle_tv_answer)
        event_bus.trigger_standby_mode.connect(self.handle_standby_mode)
        event_bus.reset_game_state.connect(self.handle_reset_game_state)
        event_bus.change_round.connect(self.handle_change_round)
        event_bus.trigger_final_step.connect(self.handle_final_step)
        event_bus.start_final_crossfade.connect(self.handle_final_crossfade)
        event_bus.update_theme_config.connect(self.apply_theme_config)
        event_bus.reload_theme_config.connect(self.reload_theme_from_disk)
        event_bus.set_display_fullscreen_toggle.connect(self.toggle_fullscreen)



# =============================================================================
# STANDALONE TEST ENTRY POINT
# =============================================================================

def main():
    app = QApplication(sys.argv)
    window = TVDisplayWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
