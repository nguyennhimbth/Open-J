"""Open-J: TV Studio Broadcast Display Engine.
Full-screen secondary display window simulating industrial video wall TV bezel,
state machine visual sequences (Blank, Random Fill, Category Reveal with 3-layer slide transitions,
Point Zoom broadcast transitions, Clean Clue Cards, and Final Jeopardy dual-background screen),
AssetRenderer dual fitting (zoom vs tile), and audio subsystem synchronization via EventBus.
"""

import os
import sys
import math
import random
from pathlib import Path
from typing import Dict, Optional, Tuple

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import Qt, QTimer, Slot, QPropertyAnimation, QEasingCurve, QRect, QParallelAnimationGroup, QPoint, Property
from PySide6.QtGui import QFont, QFontMetrics, QColor, QPainter, QBrush, QPen, QPixmap, QKeyEvent, QTransform
from PySide6.QtCore import Qt, QTimer, Slot, QPropertyAnimation, QEasingCurve, QRect, QParallelAnimationGroup, QPoint, QPointF, Property
from PySide6.QtGui import QFont, QFontMetrics, QColor, QPainter, QBrush, QPen, QPixmap, QKeyEvent, QTransform, QPolygonF
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


def draw_cover_image(painter: QPainter, target_rect: QRect, pixmap: QPixmap, smooth: bool = True):
    """Scale and crop to fill the target rectangle while maintaining original aspect ratio."""
    if not pixmap or pixmap.isNull():
        return
    transform = Qt.SmoothTransformation if smooth else Qt.FastTransformation
    scaled = pixmap.scaled(
        target_rect.size(),
        Qt.KeepAspectRatioByExpanding,
        transform
    )
    # Center and crop overflow
    x = target_rect.x() + (target_rect.width() - scaled.width()) // 2
    y = target_rect.y() + (target_rect.height() - scaled.height()) // 2
    painter.save()
    painter.setClipRect(target_rect)
    painter.drawPixmap(x, y, scaled)
    painter.restore()


def draw_contain_image(painter: QPainter, target_rect: QRect, pixmap: QPixmap, smooth: bool = True):
    """Preserve original aspect ratio and center logo/icon."""
    if not pixmap or pixmap.isNull():
        return
    transform = Qt.SmoothTransformation if smooth else Qt.FastTransformation
    scaled = pixmap.scaled(
        target_rect.size(),
        Qt.KeepAspectRatio,
        transform
    )
    # Center within bounding box
    x = target_rect.x() + (target_rect.width() - scaled.width()) // 2
    y = target_rect.y() + (target_rect.height() - scaled.height()) // 2
    painter.save()
    painter.setClipRect(target_rect)
    painter.drawPixmap(x, y, scaled)
    painter.restore()


def draw_mosaic_tile(painter: QPainter, cell_rect: QRect, cell_in_grid: QRect, grid_rect: QRect, full_pixmap: QPixmap, smooth: bool = True):
    """
    Vẽ từng mảnh của một bức ảnh duy nhất lên từng ô sao cho toàn bộ 36 ô
    tạo thành một bức tranh liền mạch bị chia cắt bởi viền Bezel.
    Renders contiguous mosaic fragments across video wall cells separated by bezel borders.
    """
    if not full_pixmap or full_pixmap.isNull() or grid_rect.width() <= 0 or grid_rect.height() <= 0:
        return
    transform = Qt.SmoothTransformation if smooth else Qt.FastTransformation
    # Scale source image across full 6x6 matrix area
    scaled_full = full_pixmap.scaled(
        grid_rect.size(),
        Qt.KeepAspectRatioByExpanding,
        transform
    )
    # Centering offset coordinates in grid_rect
    offset_x = (scaled_full.width() - grid_rect.width()) // 2
    offset_y = (scaled_full.height() - grid_rect.height()) // 2
    
    # Calculate slice coordinates for this cell
    src_x = (cell_in_grid.x() - grid_rect.x()) + offset_x
    src_y = (cell_in_grid.y() - grid_rect.y()) + offset_y
    src_w = cell_in_grid.width()
    src_h = cell_in_grid.height()
    
    # Draw slice into cell_rect
    painter.drawPixmap(cell_rect, scaled_full, QRect(src_x, src_y, src_w, src_h))


# =============================================================================
# AUTO-FIT LABEL: DYNAMIC FONT SIZING WIDGET
# =============================================================================

class AutoFitLabel(QLabel):
    """Auto-fitting QLabel dynamically calculating optimal point size based on QFontMetrics.
    Used for: Clue Screen, Final Jeopardy Clue, Bottom Answer Overlay.
    Replaces fixed font size with dynamic bounds fitting.
    """

    def __init__(self, max_point_size: int = 54, min_point_size: int = 18, parent=None):
        super().__init__(parent)
        self.max_point_size = max_point_size
        self.min_point_size = min_point_size
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_font_size()

    def setText(self, text: str):
        super().setText(text)
        self._adjust_font_size()

    def _adjust_font_size(self):
        text = self.text()
        if not text:
            return
        target_rect = self.contentsRect()
        if target_rect.width() <= 0 or target_rect.height() <= 0:
            return
        current_font = QFont(self.font())
        best_size = self.min_point_size
        for size in range(self.max_point_size, self.min_point_size - 1, -2):
            current_font.setPointSize(size)
            metrics = QFontMetrics(current_font)
            bounding = metrics.boundingRect(
                QRect(0, 0, target_rect.width(), 0),
                Qt.AlignCenter | Qt.TextWordWrap,
                text
            )
            if bounding.height() <= target_rect.height() and bounding.width() <= target_rect.width():
                best_size = size
                break
        current_font.setPointSize(best_size)
        self.setFont(current_font)


class _CoverImageWidget(QWidget):
    """Specialized visual container supporting full-bleed cover, centered contain, or solid fills."""
    def __init__(self, parent=None, mode="cover"):
        super().__init__(parent)
        self.pixmap: Optional[QPixmap] = None
        self.bg_color = QColor("#060CE9")
        self.fallback_text = ""
        self.fallback_font = QFont("Impact", 72, QFont.Bold)
        self.fallback_color = QColor("#FFCC00")
        self.mode = mode  # "cover" or "contain"
        self.smooth_transform = True
        self.setStyleSheet(FLAT_CARD_STYLE)

    def set_pixmap(self, pixmap: Optional[QPixmap]):
        self.pixmap = pixmap
        self.update()

    def set_bg_color(self, color: QColor):
        self.bg_color = color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.smooth_transform:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = self.rect()
        if self.pixmap and not self.pixmap.isNull():
            if self.mode == "contain":
                draw_contain_image(painter, rect, self.pixmap, smooth=self.smooth_transform)
            else:
                draw_cover_image(painter, rect, self.pixmap, smooth=self.smooth_transform)
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
    Top row category header cell in the 6x6 matrix (100% sharp flat borders).
    Supports 3 visual states:
    - is_mosaic == True: Sliced tile of the 36-tile standby mosaic video wall.
    - is_revealed == False: Displays Unrevealed header logo (Globe Jeopardy logo).
    - is_revealed == True: Displays Revealed background with centered category title.
    """

    def __init__(self, title="CATEGORY", parent=None):
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
                # Sharp inner border
                painter.setPen(QPen(QColor(255, 255, 255, 25), 1))
                painter.drawRect(rect.adjusted(0, 0, -1, -1))
                return

        if not self.is_revealed:
            # Unrevealed state: display Jeopardy logo
            if self.unrevealed_pixmap and not self.unrevealed_pixmap.isNull():
                AssetRenderer.render_background(painter, rect, self.unrevealed_pixmap, self.fit_mode)
            else:
                painter.fillRect(rect, self.bg_color)
        else:
            # Revealed state: display category title on background
            if self.revealed_pixmap and not self.revealed_pixmap.isNull():
                AssetRenderer.render_background(painter, rect, self.revealed_pixmap, self.fit_mode)
            else:
                painter.fillRect(rect, self.bg_color)

            # Draw category title (All caps, bold, drop shadow)
            font = QFont(self.font_family, self.font_size)
            font.setBold(self.font_bold)
            painter.setFont(font)

            # Black drop shadow
            painter.setPen(QColor(0, 0, 0, 240))
            painter.drawText(rect.adjusted(3, 3, 3, 3), Qt.AlignCenter | Qt.TextWordWrap, str(self.title).upper())

            # White text
            painter.setPen(self.text_color)
            painter.drawText(rect, Qt.AlignCenter | Qt.TextWordWrap, str(self.title).upper())

        # Sharp inner border
        painter.setPen(QPen(QColor(255, 255, 255, 35), 1))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))


class TVClueCell(QWidget):
    """
    Clue point cell in the 6x5 matrix. 100% sharp borders, bold gold typography with black drop shadow.
    Supports solid color fill or custom texture via AssetRenderer.
    """

    STATE_BLANK = 0   # Blank unpopulated background
    STATE_POINTS = 1  # Active illuminated point value
    STATE_USED = 2    # Opened / used clue (darkened out)

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

        # Cell background (texture or solid color)
        if self.use_image and self.tile_pixmap and not self.tile_pixmap.isNull():
            AssetRenderer.render_background(painter, rect, self.tile_pixmap, self.fit_mode)
        else:
            painter.fillRect(rect, self.solid_color)

        # Inner border
        painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))

        if self.state == self.STATE_POINTS:
            font = QFont(self.font_family, self.font_size, QFont.Bold)
            painter.setFont(font)

            txt = str(self.points)

            # Black drop shadow
            painter.setPen(QColor(0, 0, 0, 245))
            painter.drawText(rect.adjusted(4, 4, 4, 4), Qt.AlignCenter, txt)

            # Golden point text
            painter.setPen(self.text_gold)
            painter.drawText(rect, Qt.AlignCenter, txt)


# =============================================================================
# 2. POINT ZOOM WIDGET (POINT EXPANSION TRANSITION)
# =============================================================================

class TVPointZoomWidget(QWidget):
    """
    Full-window point zoom widget expanding the selected point tile into a centered massive number.
    Smooth zoom transition from cell coordinates to full display (350-450ms OutCubic).
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
        w, h = rect.width(), rect.height()

        # When expanded to full window, frame with outer black letterbox/pillarbox (Ref. Image 4)
        if w >= 600 and h >= 400:
            painter.fillRect(rect, QColor("#000000"))
            card_w = max(100, int(w * 0.90))
            card_h = max(100, int(h * 0.90))
            card_x = (w - card_w) // 2
            card_y = (h - card_h) // 2
            card_rect = QRect(card_x, card_y, card_w, card_h)
        else:
            card_rect = rect

        if self.use_image and self.tile_pixmap and not self.tile_pixmap.isNull():
            AssetRenderer.render_background(painter, card_rect, self.tile_pixmap, self.fit_mode)
        else:
            painter.fillRect(card_rect, self.solid_color)

        # Giant centered point value with dynamic scaling
        calc_size = max(36, int(card_rect.height() * 0.48))
        font = QFont(self.font_family, calc_size, QFont.Bold)
        painter.setFont(font)

        txt = str(self.points)

        # Black drop shadow
        offset = max(3, int(calc_size * 0.08))
        painter.setPen(QColor(0, 0, 0, 245))
        painter.drawText(card_rect.adjusted(offset, offset, offset, offset), Qt.AlignCenter, txt)

        # Gold text
        painter.setPen(self.text_gold)
        painter.drawText(card_rect, Qt.AlignCenter, txt)


# =============================================================================
# 3. 3D HORIZONTAL CARD FLIP TRANSITION WIDGET (POWERPOINT FLIP EFFECT)
# =============================================================================

class TVCardFlipTransitionWidget(QWidget):
    """
    3D Horizontal Card Flip Transition Widget (PowerPoint Flip Effect).
    Performs authentic hardware-accelerated 3D card flip around Qt.YAxis:
      - Phase 1 (0° -> 90°): Rotates front face (Daily Double splash) edge-on.
      - Phase 2 (90° -> 180°): Rotates back face (Clue Question card) from edge-on to front.
    Uses QPropertyAnimation with QEasingCurve.InOutCubic.
    Performs authentic hardware-accelerated 3D card flip matching PowerPoint's <p14:flip dir="r"/>:
      - Direction: Flips horizontally to the right around the vertical center axis.
      - Phase 1 (0° -> 90°): Rotates front face (Daily Double splash) with perspective foreshortening.
      - Phase 2 (90° -> 180°): Rotates back face (Clue Question card) from edge-on to full flat display.
      - Duration: 1200ms (matching PowerPoint broadcast timing).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0.0
        self.front_pixmap: Optional[QPixmap] = None
        self.back_pixmap: Optional[QPixmap] = None
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)
        self.setStyleSheet("background-color: transparent; border: none;")
        self.hide()

    def get_angle(self) -> float:
        return self._angle

    def set_angle(self, angle: float):
        self._angle = float(angle)
        self.update()

    angle = Property(float, get_angle, set_angle)

    def start_flip(self, front_pixmap: QPixmap, back_pixmap: QPixmap, duration: int = 1200, finished_callback=None):
        self.front_pixmap = front_pixmap
        self.back_pixmap = back_pixmap
        self._angle = 0.0
        self.show()
        self.raise_()

        self.anim = QPropertyAnimation(self, b"angle")
        self.anim.setDuration(duration)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(180.0)
        self.anim.setEasingCurve(QEasingCurve.InOutCubic)

        def _on_finished():
            self.hide()
            if finished_callback:
                finished_callback()

        self.anim.finished.connect(_on_finished)
        self.anim.start()

    def paintEvent(self, event):
        if not self.front_pixmap or not self.back_pixmap:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        w = self.width()
        h = self.height()
        ang = self._angle

        is_front = ang <= 90.0
        pix = self.front_pixmap if is_front else self.back_pixmap
        if not pix or pix.isNull():
            return

        rot_deg = ang if is_front else (ang - 180.0)

        # Basic 3D effect with QTransform projection
        t = QTransform()
        t.translate(w / 2.0, h / 2.0)
        
        # Add slight perspective projection
        persp = 0.0015
        if not is_front:
            persp = -persp
        t.m31 = persp * rot_deg
        
        t.rotate(rot_deg, Qt.YAxis)
        t.translate(-w / 2.0, -h / 2.0)

        painter.setTransform(t)
        scaled_pix = pix.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        px = (w - scaled_pix.width()) // 2
        py = (h - scaled_pix.height()) // 2
        painter.drawPixmap(px, py, scaled_pix)

# =============================================================================
# 4. CATEGORY REVEAL 3-LAYER TRANSITION CARD & ENGINE
# =============================================================================

class TVCategoryCardWidget(QWidget):
    """
    Single Card block for Category Reveal consisting of 3 flat layers (Flat 100%):
    - Layer 1 (Card Background): Deep blue rectangular frame, 100% flat (88% centered box).
    - Layer 2 (Category Title Text): Uppercase category title, bold typography, centered with shadow.
    - Layer 3 (Logo Overlay): Logo cover graphic with QGraphicsOpacityEffect, covering 100% of card.
    """

    def __init__(self, logo_path=None, parent=None):
        super().__init__(parent)
        self.logo_path = logo_path
        self.setStyleSheet(FLAT_CARD_STYLE)

        self.title = "CATEGORY"
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

        # Layer 3: Logo Overlay (Cover 100% of card face)
        self.logo_overlay = _CoverImageWidget(self.inner_box, mode="cover")
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
        # Framing: Cụm Logo + Chủ đề được thu nhỏ 10% (đạt kích thước 90%) và căn giữa theo PART1.pdf
        card_w = max(100, int(w * 0.90))
        card_h = max(100, int(h * 0.90))
        card_x = (w - card_w) // 2
        card_y = (h - card_h) // 2
        self.inner_box.setGeometry(card_x, card_y, card_w, card_h)
        self.title_label.setGeometry(30, 30, max(1, card_w - 60), max(1, card_h - 60))
        self.logo_overlay.setGeometry(0, 0, card_w, card_h)


class TVCategoryRevealWidget(QWidget):
    """
    Transition Engine managing manual 6-category intro sequence via Host controls:
    - Step 1: Open column with Logo covering title at 100% opacity. Holds for Host cue.
    - Step 2: Host command -> Fade out Logo from 1.0 to 0.0 over 500ms revealing category title.
    - Step 3: Host command -> Slides left smoothly to load the subsequent category column.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #000000;")

        self.categories = [f"CATEGORY {i+1}" for i in range(6)]
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
        """Action 1: Open specified category column covered 100% by logo, awaiting Host command."""
        self.current_index = max(0, min(col_index, len(self.categories) - 1))
        w, h = self.width(), self.height()
        self.active_card = self.card_a
        self.next_card = self.card_b

        self.active_card.setGeometry(0, 0, w, h)
        self.next_card.setGeometry(w, 0, w, h)

        cat_title = self.categories[self.current_index] if self.current_index < len(self.categories) else f"CHỦ ĐỀ {self.current_index+1}"
        cat_title = self.categories[self.current_index] if self.current_index < len(self.categories) else f"CATEGORY {self.current_index+1}"
        self.active_card.set_category_title(cat_title)
        self.active_card.reset_logo_opacity()
        self.active_card.show()
        self.next_card.show()

    def fade_logo(self):
        """Action 2: Trigger fade-out animation to reveal category title over 500ms."""
        self.active_card.fade_out_logo(duration=500)

    @Slot(bool)
    def slide_next(self, auto_fade: bool = False):
        """Action 3: Slide current card left and bring in the next category."""
        self._pending_auto_fade = auto_fade
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
        if getattr(self, "_pending_auto_fade", False):
            self._pending_auto_fade = False
            QTimer.singleShot(150, self.fade_logo)

    def handle_manual_step(self, step: int):
        """Handle step control from Host."""
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
    Standard Sony Pictures Television broadcast clue card:
    - Deep blue card occupying ~82% width and ~84% height, centered.
    - Framed by black pillarbox/letterbox (#000000).
    - Typography: ITC Korinna (fallback Georgia), ALL CAPS, centered.
    - Crisp black drop shadow (offset: 3px, 3px, #000000).
    - Bottom Answer Overlay: 50-70px above card bottom, plain white text, no boxes.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #000000; border: none;")
        self.question_text = ""
        self.bg_color = QColor("#060CE9")
        self.bg_pixmap: Optional[QPixmap] = None
        self.asset_pixmap: Optional[QPixmap] = None
        self.font_family = "ITC Korinna"
        self.font_size = 50          # max point size for dynamic fitting
        self.font_size_min = 18      # min point size
        self.smooth_transform = True

                # Sony broadcast standard answer overlay - AutoFitLabel
        self.answer_label = AutoFitLabel(max_point_size=32, min_point_size=14, parent=self)
        self.answer_label.setStyleSheet("""
            QLabel {
                background-color: transparent;
                color: #ffffff;
                border: none;
                padding: 0px;
            }
        """)
        ans_shadow = QGraphicsDropShadowEffect(self.answer_label)
        ans_shadow.setBlurRadius(2)
        ans_shadow.setOffset(2, 2)
        ans_shadow.setColor(QColor("#000000"))
        self.answer_label.setGraphicsEffect(ans_shadow)
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
        if visible and text:
                        # White text
            self.answer_label.setText(str(text).upper())
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

    def _fit_font_size(self, text: str, text_rect: QRect) -> int:
        """Find optimal font size fitting text_rect using reverse search."""
        best = self.font_size_min
        for size in range(self.font_size, self.font_size_min - 1, -2):
            f = QFont(self.font_family, size, QFont.Bold)
            m = QFontMetrics(f)
            b = m.boundingRect(
                QRect(0, 0, text_rect.width(), 0),
                Qt.AlignCenter | Qt.TextWordWrap,
                text
            )
            if b.height() <= text_rect.height() and b.width() <= text_rect.width():
                best = size
                break
        return best

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.smooth_transform:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.TextAntialiasing)

        w, h = self.width(), self.height()

        # 1. Outer framing: Solid black #000000 (Broadcast letterbox/pillarbox)
        painter.fillRect(QRect(0, 0, w, h), QColor("#000000"))

        # 2. Blue clue card frame: FULL SCREEN (16:9 100% width/height)
        card_w = w
        card_h = h
        card_x = 0
        card_y = 0
        card_rect = QRect(card_x, card_y, card_w, card_h)

        if self.bg_pixmap and not self.bg_pixmap.isNull():
            draw_cover_image(painter, card_rect, self.bg_pixmap, smooth=self.smooth_transform)
        else:
            painter.fillRect(card_rect, self.bg_color)

        # 3. Render Clue content with dynamic font sizing
        if self.asset_pixmap and not self.asset_pixmap.isNull():
            img_rect = QRect(card_x + 40, card_y + 30, card_w - 80, int(card_h * 0.50))
            text_rect = QRect(card_x + 40, card_y + int(card_h * 0.54), card_w - 80, int(card_h * 0.40))

            scaled_asset = self.asset_pixmap.scaled(
                img_rect.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation if self.smooth_transform else Qt.FastTransformation
            )
            ax = img_rect.x() + (img_rect.width() - scaled_asset.width()) // 2
            ay = img_rect.y() + (img_rect.height() - scaled_asset.height()) // 2
            painter.drawPixmap(ax, ay, scaled_asset)

            dyn_size = self._fit_font_size(self.question_text, text_rect)
            font = QFont(self.font_family, dyn_size, QFont.Bold)
            painter.setFont(font)
            # Sharp drop shadow (offset 3, 3)
            painter.setPen(QColor(0, 0, 0, 255))
            painter.drawText(text_rect.adjusted(3, 3, 3, 3), Qt.AlignCenter | Qt.TextWordWrap, self.question_text)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(text_rect, Qt.AlignCenter | Qt.TextWordWrap, self.question_text)
        else:
            text_rect = QRect(card_x + 50, card_y + 40, card_w - 100, card_h - 80)
            dyn_size = self._fit_font_size(self.question_text, text_rect)
            font = QFont(self.font_family, dyn_size, QFont.Bold)
            painter.setFont(font)
            # Sharp drop shadow (offset 3, 3)
            painter.setPen(QColor(0, 0, 0, 255))
            painter.drawText(text_rect.adjusted(3, 3, 3, 3), Qt.AlignCenter | Qt.TextWordWrap, self.question_text)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(text_rect, Qt.AlignCenter | Qt.TextWordWrap, self.question_text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        card_w = max(100, int(w * 0.82))
        card_h = max(100, int(h * 0.84))
        card_y = (h - card_h) // 2
        lbl_w = min(int(card_w * 0.90), 1000)
        lbl_h = max(60, int(card_h * 0.12))
        # Positioned 50-70px above bottom edge of clue frame
        lbl_y = card_y + card_h - 60 - lbl_h
        self.answer_label.setGeometry((w - lbl_w) // 2, lbl_y, lbl_w, lbl_h)


class TVFinalScreenWidget(QWidget):
    """
    Final Jeopardy Sequencer (3 Steps + 15s Blue-to-Red Cross-fade):
    - Step 1 (trigger_final_step(1)): Full-bleed cover Final Jeopardy Splash Logo.
    - Step 2 (trigger_final_step(2)): Flat card displaying Category Name in uppercase, centered.
    - Step 3 (trigger_final_step(3)): Final Clue card with stacked backgrounds:
      * Base background: RED, Overlay: BLUE (opacity=1.0).
      * Starts 30s Think Music countdown.
      * Exactly at 15s elapsed: Cross-fade animates Blue opacity from 1.0 to 0.0 over 2500ms -> Deep Red.
    - Champion / Scoring reveal: STRICTLY HIDDEN ON TV (Host Controller only).
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

        # 15s Cross-fade timer
        self.crossfade_timer = QTimer(self)
        self.crossfade_timer.setSingleShot(True)
        self.crossfade_timer.timeout.connect(self.start_crossfade)

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

        self.cat_name_lbl = AutoFitLabel(max_point_size=92, min_point_size=36, parent=self.cat_card)
        self.cat_name_lbl.setStyleSheet("font-weight: 900; color: #ffffff; border: none; background: transparent;")
        self.cat_name_lbl.setFont(QFont("Georgia", 76, QFont.Bold))
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
        # Foreground content: Clue text only, no metadata or bottom progress bar
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

        self.clue_content_lbl = AutoFitLabel(max_point_size=56, min_point_size=20, parent=self.clue_fg)
        self.clue_content_lbl.setStyleSheet("font-weight: 900; color: #ffffff; border: none; background: transparent;")
        clue_shadow = QGraphicsDropShadowEffect(self.clue_content_lbl)
        clue_shadow.setBlurRadius(2)
        clue_shadow.setOffset(2, 2)
        clue_shadow.setColor(QColor("#000000"))
        self.clue_content_lbl.setGraphicsEffect(clue_shadow)

                # Sony broadcast standard answer overlay - AutoFitLabel
        self.answer_label = AutoFitLabel(max_point_size=32, min_point_size=14, parent=self.clue_fg)
        self.answer_label.setStyleSheet("""
            QLabel {
                background-color: transparent;
                color: #ffffff;
                border: none;
                padding: 0px;
            }
        """)
        ans_shadow = QGraphicsDropShadowEffect(self.answer_label)
        ans_shadow.setBlurRadius(2)
        ans_shadow.setOffset(2, 2)
        ans_shadow.setColor(QColor("#000000"))
        self.answer_label.setGraphicsEffect(ans_shadow)
        self.answer_label.setVisible(False)

        fg_layout.addWidget(self.clue_content_lbl, 1)

        self._update_visibility()

    def set_answer_overlay(self, visible: bool, text: str = ""):
        if visible and text:
            self.answer_label.setText(str(text).upper())
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
        self.crossfade_timer.stop()
        if hasattr(self, "crossfade_anim") and self.crossfade_anim.state() == QPropertyAnimation.Running:
            self.crossfade_anim.stop()

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
            self.crossfade_timer.start(15000)

    def restart_final_countdown(self):
        """Reset to Blue base immediately, restart 30s countdown, schedule 15s crossfade."""
        if hasattr(self, "crossfade_anim") and self.crossfade_anim.state() == QPropertyAnimation.Running:
            self.crossfade_anim.stop()
        self.blue_opacity.setOpacity(1.0)
        self.countdown_timer.stop()
        self.countdown_ms = 30000
        self.progress_bar.setValue(300)
        self.countdown_timer.start()
        self.crossfade_timer.stop()
        self.crossfade_timer.start(15000)

    def start_crossfade(self):
        """Trigger smooth crossfade animation from Blue to Red over 2500ms."""
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
    """Broadcast TV Studio / Video Wall secondary display window."""

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
        self.category_names = [f"CATEGORY {i+1}" for i in range(6)]
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

        # PowerPoint 3D horizontal card flip transition overlay widget
        self.card_flip_widget = TVCardFlipTransitionWidget(self)


        self.stack.setCurrentIndex(self.INDEX_STANDBY_NORMAL)

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
        """Instant toggle between Borderless Fullscreen and Windowed mode for OBS capture."""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        if hasattr(self, "point_zoom_widget") and self.point_zoom_widget.isVisible():
            self.point_zoom_widget.setGeometry(0, 0, w, h)
        if hasattr(self, "card_flip_widget") and self.card_flip_widget.isVisible():
            self.card_flip_widget.setGeometry(0, 0, w, h)

    # -------------------------------------------------------------------------
    # UI PAGE BUILDERS
    # -------------------------------------------------------------------------

    def _build_page_board(self):
        """6x6 Matrix (1 category header row + 5 point rows) with industrial black bezels."""
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
        """Category Reveal Engine (3 layers: background, title, logo overlay)."""
        self.cat_reveal_widget = TVCategoryRevealWidget(self)
        self.cat_reveal_widget.set_categories(self.category_names)
        self.stack.addWidget(self.cat_reveal_widget)  # INDEX_CATEGORY_REVEAL = 1

    def _build_page_daily_double(self):
        """Daily Double Splash Image Graphic (Full-Bleed Cover)."""
        self.dd_splash_widget = _CoverImageWidget(self)
        self.dd_splash_widget.fallback_text = "DAILY DOUBLE"
        self.stack.addWidget(self.dd_splash_widget)  # INDEX_DAILY_DOUBLE = 2

    def _build_page_clean_clue(self):
        """Clean clue card screen (Flat 100% Broadcast Standard)."""
        self.clue_screen_widget = TVClueScreenWidget(self)
        self.stack.addWidget(self.clue_screen_widget)  # INDEX_QUESTION = 3

    def _build_page_final(self):
        """Final Jeopardy Sequencer (3 steps + 15s Blue-to-Red cross-fade)."""
        self.final_screen_widget = TVFinalScreenWidget(self)
        self.stack.addWidget(self.final_screen_widget)  # INDEX_FINAL = 4

    def _build_page_standby(self):
        """Standard Standby Wallpaper Screen (Full-Bleed 100%)."""
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
        """Blank Board State: Red Zone (Row 0) preserves custom header logo; 30 clue cells clear to blank fill."""
        self.fill_timer.stop()
        self.stack.setCurrentIndex(self.INDEX_BOARD)
        for cell in self.cat_cells:
            cell.set_revealed(False)
            cell.set_mosaic(False)
        for cell in self.cells.values():
            cell.set_mosaic(False)
            cell.set_state(TVClueCell.STATE_BLANK)

    @Slot(int, int)
    def handle_category_step(self, action: int, col_index: int):
        """Step sequencer for category reveals:
        action: 1=Show Logo covering column, 2=Reveal Title, 3=Slide Next, 4=Return to Board
        """
        if action == 1:
            self.handle_category_show_logo(col_index)
        elif action == 2:
            self.handle_category_fade_logo()
        elif action == 3:
            self.handle_category_slide_next(auto_fade=False)
        elif action == 4:
            self.handle_cancel_category_reveal()

    @Slot()
    def handle_restart_final_timer(self):
        """Restarts 30s Final Jeopardy timer, resets audio, restores Blue base."""
        if self.stack.currentIndex() == self.INDEX_FINAL:
            self.final_screen_widget.restart_final_countdown()
            event_bus.play_sound_event.emit("think_30s")

    @Slot(bool)
    def handle_toggle_tv_window(self, visible: bool):
        """Shows or hides the secondary TV window from Host Controller."""
        if visible:
            self.show()
            self.raise_()
        else:
            self.hide()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_F11:
            self.toggle_fullscreen()
            event.accept()
        else:
            super().keyPressEvent(event)

    @Slot()
    def start_board_fill(self):
        """Randomly reveal 30 point cells. Plays single board fill sound effect upon start."""
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
        """Action 1: Open category column with logo covering title, awaiting Host command."""
        cats = [self.cat_cells[i].title for i in range(6)]
        self.cat_reveal_widget.set_categories(cats)
        self.stack.setCurrentIndex(self.INDEX_CATEGORY_REVEAL)
        self.cat_reveal_widget.show_column(col_index)

    @Slot()
    def handle_category_fade_logo(self):
        """Action 2: Trigger fade-out animation to reveal category title over 500ms."""
        if self.stack.currentIndex() == self.INDEX_CATEGORY_REVEAL:
            self.cat_reveal_widget.fade_logo()

    @Slot(bool)
    def handle_category_slide_next(self, auto_fade: bool = False):
        """Action 3: Slide to next category column (optionally auto-fading logo)."""
        if self.stack.currentIndex() == self.INDEX_CATEGORY_REVEAL:
            self.cat_reveal_widget.slide_next(auto_fade=auto_fade)

    @Slot(int)
    def handle_category_reveal_step(self, step: int):
        """Backward compatibility: control step 0 (Logo), 1 (Fade), 2 (Slide next)."""
        if self.stack.currentIndex() != self.INDEX_CATEGORY_REVEAL:
            cats = [self.cat_cells[i].title for i in range(6)]
            self.cat_reveal_widget.set_categories(cats)
            self.stack.setCurrentIndex(self.INDEX_CATEGORY_REVEAL)
            self.cat_reveal_widget.show_column(0)
        self.cat_reveal_widget.handle_manual_step(step)

    @Slot()
    def handle_category_next(self):
        self.handle_category_slide_next()
        self.handle_category_slide_next(auto_fade=False)

    @Slot()
    def handle_cancel_category_reveal(self):
        """Complete or cancel category reveal: return to board and reveal all categories."""
        if self.stack.currentIndex() == self.INDEX_CATEGORY_REVEAL:
            self.cat_reveal_widget.cancel()
            self.stack.setCurrentIndex(self.INDEX_BOARD)
            # Ensure all 6 category titles are displayed on the board
            for cell in self.cat_cells:
                cell.set_revealed(True)

    # --- POINT ZOOM TRANSITION & 2-STEP AIRING FLOW ---
    @Slot(dict)
    def handle_request_clue_zoom(self, payload: dict):
        """Step 1: Expand selected point tile or Daily Double splash to full screen."""
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
        """Step 1 complete: Hold full screen on point value or Daily Double splash."""
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
            # Hold giant point value full-screen
            self.point_zoom_widget.setGeometry(0, 0, self.width(), self.height())
            self.point_zoom_widget.show()
            self.point_zoom_widget.raise_()

    @Slot()
    def handle_clue_reveal(self):
        """Step 2: Airing command to reveal clue text.
        If current view is Daily Double (or payload is Daily Double), execute PowerPoint 3D horizontal card flip.
        """
        if not self.pending_clue_payload:
            return

        if self.stack.currentIndex() == self.INDEX_DAILY_DOUBLE or self.pending_clue_payload.get("is_daily_double"):
            self._trigger_daily_double_flip_transition()
        else:
            self.show_question(self.pending_clue_payload)

    def _trigger_daily_double_flip_transition(self):
        """Executes PowerPoint-style 3D horizontal card flip from Daily Double to Clue Question."""
        w, h = max(400, self.width()), max(300, self.height())
        front_pix = QPixmap(w, h)
        front_pix.fill(QColor("#000000"))
        self.dd_splash_widget.render(front_pix)

        payload = self.pending_clue_payload
        raw_text = payload.get("question_text", "")
        has_asset = payload.get("has_asset", False)
        asset_path = payload.get("asset_path", "")

        self.clue_screen_widget.resize(w, h)
        self.clue_screen_widget.set_clue(raw_text, has_asset, asset_path)

        back_pix = QPixmap(w, h)
        back_pix.fill(QColor("#000000"))
        self.clue_screen_widget.render(back_pix)

        self.card_flip_widget.setGeometry(0, 0, w, h)

        def _on_flip_done():
            self.show_question(self.pending_clue_payload)

        self.card_flip_widget.start_flip(front_pix, back_pix, duration=650, finished_callback=_on_flip_done)
        self.card_flip_widget.start_flip(front_pix, back_pix, duration=1200, finished_callback=_on_flip_done)

    handle_clue_zoom = handle_request_clue_zoom


    @Slot(str)
    def show_daily_double_splash(self, splash_path: str):
        """Display Daily Double splash graphic (Full-Bleed Cover)."""
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
        """Toggle optional bottom answer overlay display."""
        curr = self.stack.currentIndex()
        if curr == self.INDEX_QUESTION:
            self.clue_screen_widget.set_answer_overlay(is_visible, answer_text)
        elif curr == self.INDEX_FINAL:
            self.final_screen_widget.set_answer_overlay(is_visible, answer_text)

    handle_toggle_answer = handle_toggle_tv_answer

    # --- STANDBY ENGINE (NORMAL & MOSAIC 36 Ô) ---
    # STANDBY ENGINE (NORMAL & MOSAIC 36 CELLS)

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
            for cell in self.cat_cells:
                cell.set_revealed(True)

    def _set_mosaic_mode(self, enabled: bool):
        pix = self.standby_pixmap if enabled else None
        for cell in self.cat_cells:
            cell.set_mosaic(enabled, pix)
        for cell in self.cells.values():
            cell.set_mosaic(enabled, pix)

    @Slot()
    def handle_reset_game_state(self):
        """Reset full TV display state to initial defaults."""
        self.close_question()
        self._setup_default_board()

    # --- FINAL JEOPARDY TRANSITIONS (3 STEPS + 15S CROSS-FADE) ---
    @Slot(int, dict)
    def handle_final_step(self, step: int, data: dict):
        """Coordinate Final Jeopardy sequence. Winner summary strictly kept on Host, hidden on TV."""
        if step == 2:
            event_bus.play_sound_event.emit("category_intro")
        if step in (1, 2, 3):
            self.stack.setCurrentIndex(self.INDEX_FINAL)
            self.final_screen_widget.set_step(step, data)
        # Step >= 4 (Final scores): Never display winner podiums on TV!

    @Slot()
    def handle_final_crossfade(self):
        """Trigger Blue to Red background crossfade."""
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
        if round_id in (1, 2):
            self.stack.setCurrentIndex(self.INDEX_BOARD)
            for cell in self.cat_cells:
                cell.set_revealed(True)

    @Slot()
    def reload_theme_from_disk(self):
        """Reload theme.xml from disk and apply immediately."""
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

        # Standby Screen Wallpaper (Static & Mosaic 36)
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
    # PERFORMANCE PROFILES & DATA SYNCHRONIZATION
    # -------------------------------------------------------------------------

    @Slot(str)
    def apply_performance_profile(self, profile_mode: str):
        """Apply performance profile: basic, smooth, ultra."""
        self.performance_profile = (profile_mode or "smooth").lower()
        if self.performance_profile == "ultra":
            try:
                from PySide6.QtOpenGLWidgets import QOpenGLWidget
                if not hasattr(self, "_gl_widget"):
                    self._gl_widget = QOpenGLWidget(self)
                    self._gl_widget.lower()
                    self._gl_widget.resize(self.size())
            except Exception as e:
                print(f"[TVDisplay] Ultra OpenGL notice: {e}")
            self.animation_fps = 60
            self.smooth_transform = True
        elif self.performance_profile == "smooth":
            self.animation_fps = 60
            self.smooth_transform = True
        else:  # "basic"
            self.animation_fps = 30
            self.smooth_transform = False

        # Update rendering hints for child components
        if hasattr(self, "clue_screen_widget"):
            self.clue_screen_widget.smooth_transform = self.smooth_transform
        if hasattr(self, "cat_reveal_widget"):
            self.cat_reveal_widget.card_a.inner_box.smooth_transform = self.smooth_transform
            self.cat_reveal_widget.card_b.inner_box.smooth_transform = self.smooth_transform
        self.update()

    @Slot(list)
    def handle_sync_categories(self, categories: list):
        """Synchronizes exactly 6 categories from Host Controller to TV board and reveal widgets."""
        self.category_names = list(categories)
        while len(self.category_names) < 6:
            self.category_names.append(f"CATEGORY {len(self.category_names)+1}")
        for i in range(6):
            if i < len(self.cat_cells):
                self.cat_cells[i].set_title(self.category_names[i])
                self.cat_cells[i].set_revealed(True)
        if hasattr(self, "cat_reveal_widget"):
            self.cat_reveal_widget.set_categories(self.category_names)

    @Slot(list)
    def handle_sync_board_state(self, board_items: list):
        """Synchronizes state of 30 clue cells from Host to TV display."""
        for item in board_items:
            c = item.get("col_index", 0)
            r = item.get("row_index", 0)
            pts = item.get("points", 0)
            is_used = bool(item.get("is_used", 0))
            cell = self.cells.get((c, r))
            if cell:
                cell.set_points(pts)
                if is_used:
                    cell.set_state(TVClueCell.STATE_USED)
                else:
                    cell.set_state(TVClueCell.STATE_POINTS)

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
        event_bus.trigger_category_step.connect(self.handle_category_step)
        event_bus.restart_final_timer.connect(self.handle_restart_final_timer)
        event_bus.toggle_tv_window.connect(self.handle_toggle_tv_window)
        event_bus.set_tv_fullscreen.connect(self.toggle_fullscreen)
        event_bus.set_display_fullscreen_toggle.connect(self.toggle_fullscreen)
        event_bus.sync_categories_to_tv.connect(self.handle_sync_categories)
        event_bus.sync_board_state_to_tv.connect(self.handle_sync_board_state)
        event_bus.set_performance_profile.connect(self.apply_performance_profile)



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
