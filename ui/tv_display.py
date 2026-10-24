"""Open-J: TV Studio Broadcast Display Engine.
Full-screen secondary display window featuring:
1. Full-bleed Category Header Logo with auto-cropped border removal (Requirement #1)
2. Dual-mode Typography (Dynamic word-safe auto-fit vs Custom fixed size) unified across Category Headers, Clue Cards, Final Jeopardy, and Answer Overlays (Requirements #2 & #6)
3. 100% Full-window background fill on Point Zoom, Category Reveal, and Clue screens (Requirement #3)
4. Automatic Category Header switch to Standby Logo when all 5 clues in a column are answered (Requirement #4)
5. Toggleable Point Zoom animation & Standby Intro Video -> Static Wallpaper Cross-fade Merge + Outro Music (Requirements #5 & #7)
6. Authentic 3D Horizontal Card Flip: Flip -> Solid Black Backing -> Clue Question (Requirement #8)
7. Real OpenGL GPU Hardware Acceleration (QOpenGLWidget + QSurfaceFormat VSync & 4x MSAA + GPU/RAM Pixmap Caching) (Requirement #9)
"""

import os
import sys
import random
from pathlib import Path
from typing import Dict, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import (
    Qt,
    QTimer,
    Slot,
    QPropertyAnimation,
    QEasingCurve,
    QRect,
    QParallelAnimationGroup,
    QPoint,
    Property,
    QUrl,
)
from PySide6.QtGui import (
    QFont,
    QFontMetrics,
    QColor,
    QPainter,
    QBrush,
    QPen,
    QPixmap,
    QImage,
    QKeyEvent,
    QTransform,
    QSurfaceFormat,
)
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
    QGraphicsOpacityEffect,
    QGraphicsDropShadowEffect,
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink, QVideoFrame

try:
    from PySide6.QtOpenGLWidgets import QOpenGLWidget
    HAS_QOPENGL = True
except Exception:
    QOpenGLWidget = QWidget
    HAS_QOPENGL = False

try:
    from OpenGL import GL as gl  # noqa: F401
    HAS_PYOPENGL = True
except Exception:
    HAS_PYOPENGL = False

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


# =============================================================================
# SHARED IMAGE & TYPOGRAPHY HELPERS
# =============================================================================

def draw_cover_image(
    painter: QPainter,
    target_rect: QRect,
    pixmap: QPixmap,
    smooth: bool = True,
    fit_mode: str = "zoom",
    auto_crop: bool = False
):
    """Scale and crop/stretch to fill the target rectangle using AssetRenderer cache."""
    if not pixmap or pixmap.isNull() or target_rect.width() <= 0 or target_rect.height() <= 0:
        return
    AssetRenderer.render_background(
        painter, target_rect, pixmap, fit_mode=fit_mode, smooth=smooth, auto_crop=auto_crop
    )


def draw_contain_image(painter: QPainter, target_rect: QRect, pixmap: QPixmap, smooth: bool = True):
    """Preserve original aspect ratio and center logo/icon using cached scaling."""
    if not pixmap or pixmap.isNull() or target_rect.width() <= 0 or target_rect.height() <= 0:
        return
    scaled = AssetRenderer.get_scaled_pixmap(
        pixmap, target_rect.width(), target_rect.height(), fit_mode="contain", smooth=smooth
    )
    x = target_rect.x() + (target_rect.width() - scaled.width()) // 2
    y = target_rect.y() + (target_rect.height() - scaled.height()) // 2
    painter.save()
    painter.setClipRect(target_rect)
    painter.drawPixmap(x, y, scaled)
    painter.restore()


def draw_mosaic_tile(
    painter: QPainter,
    cell_rect: QRect,
    cell_in_grid: QRect,
    grid_rect: QRect,
    full_pixmap: QPixmap,
    smooth: bool = True
):
    """Renders contiguous mosaic fragments across video wall cells separated by bezel borders."""
    if not full_pixmap or full_pixmap.isNull() or grid_rect.width() <= 0 or grid_rect.height() <= 0:
        return
    scaled_full = AssetRenderer.get_scaled_pixmap(
        full_pixmap, grid_rect.width(), grid_rect.height(), fit_mode="zoom", smooth=smooth
    )
    offset_x = (scaled_full.width() - grid_rect.width()) // 2
    offset_y = (scaled_full.height() - grid_rect.height()) // 2

    src_x = (cell_in_grid.x() - grid_rect.x()) + offset_x
    src_y = (cell_in_grid.y() - grid_rect.y()) + offset_y
    src_w = cell_in_grid.width()
    src_h = cell_in_grid.height()

    painter.drawPixmap(cell_rect, scaled_full, QRect(src_x, src_y, src_w, src_h))


def compute_fitted_font_size(
    font_family: str,
    bold: bool,
    text: str,
    target_rect: QRect,
    max_size: int = 54,
    min_size: int = 10,
    check_longest_word: bool = True
) -> int:
    """Calculates optimal point size so text fits inside target_rect both vertically
    and horizontally, ensuring no single long word (e.g. 'ARCHITECTURE', 'ABBREVIATIONS')
    ever overflows or clips at the left/right edges.
    """
    if not text or target_rect.width() <= 4 or target_rect.height() <= 4:
        return max(min_size, min(max_size, 24))

    avail_w = max(8, target_rect.width() - 6)
    avail_h = max(8, target_rect.height() - 4)
    words = [w for w in text.split() if w]

    font = QFont(font_family)
    font.setBold(bold)

    step = 2 if (max_size - min_size) > 30 else 1
    for size in range(max_size, min_size - 1, -step):
        font.setPointSize(size)
        metrics = QFontMetrics(font)

        if check_longest_word and words:
            max_word_w = max(metrics.horizontalAdvance(w) for w in words)
            if max_word_w > avail_w:
                continue

        bounding = metrics.boundingRect(
            QRect(0, 0, avail_w, 0),
            Qt.AlignCenter | Qt.TextWordWrap,
            text
        )
        if bounding.height() <= avail_h and bounding.width() <= avail_w + 2:
            return size

    return min_size


# =============================================================================
# AUTO-FIT LABEL: DYNAMIC / CUSTOM FONT SIZING WIDGET
# =============================================================================

class AutoFitLabel(QLabel):
    """QLabel supporting both 'dynamic' (screen/bounds auto-fit) and 'custom' (fixed size) modes."""

    def __init__(self, max_point_size: int = 54, min_point_size: int = 14, parent=None):
        super().__init__(parent)
        self.max_point_size = max_point_size
        self.min_point_size = min_point_size
        self.font_mode = "dynamic"  # "dynamic" or "custom"
        self.custom_point_size = max_point_size
        self.font_family = "ITC Korinna"
        self.font_bold = True
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)

    def configure_typography(self, family: str, size: int, bold: bool = True, mode: str = "dynamic", color: str = "#FFFFFF"):
        self.font_family = family
        self.custom_point_size = max(10, int(size))
        self.font_bold = bool(bold)
        self.font_mode = (mode or "dynamic").lower()
        self.setStyleSheet(f"color: {color}; background-color: transparent; border: none; padding: 0px;")
        self._adjust_font_size()
        self.update()

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

        f = QFont(self.font_family)
        f.setBold(self.font_bold)

        if self.font_mode == "custom":
            f.setPointSize(self.custom_point_size)
        else:
            dyn_max = max(self.max_point_size, self.custom_point_size)
            best_size = compute_fitted_font_size(
                self.font_family,
                self.font_bold,
                text,
                target_rect,
                max_size=dyn_max,
                min_size=self.min_point_size,
                check_longest_word=True,
            )
            f.setPointSize(best_size)
        self.setFont(f)


class _CoverImageWidget(QWidget):
    """Specialized visual container supporting full-bleed cover, stretch, contain, or solid fills."""

    def __init__(self, parent=None, mode="cover", auto_crop: bool = False):
        super().__init__(parent)
        self.pixmap: Optional[QPixmap] = None
        self.bg_color = QColor("#060CE9")
        self.fallback_text = ""
        self.fallback_font = QFont("Impact", 72, QFont.Bold)
        self.fallback_color = QColor("#FFCC00")
        self.mode = mode  # "cover", "stretch", or "contain"
        self.auto_crop = auto_crop
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
            elif self.mode == "stretch":
                draw_cover_image(painter, rect, self.pixmap, smooth=self.smooth_transform, fit_mode="stretch", auto_crop=self.auto_crop)
            else:
                draw_cover_image(painter, rect, self.pixmap, smooth=self.smooth_transform, fit_mode="zoom", auto_crop=self.auto_crop)
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
    """Top row category header cell in the 6x6 matrix (100% sharp flat borders).
    - When unrevealed (or when all 5 clues in column are exhausted): fills 100% of the yellow cell
      edge-to-edge with the auto-cropped Jeopardy! logo (Requirement #1 & #4).
    - When revealed: displays Category Title with either Dynamic word-safe auto-fit or Custom font size (Requirement #2 & #6).
    """

    def __init__(self, title="CATEGORY", parent=None):
        super().__init__(parent)
        self.title = title
        self.is_revealed = False
        self.is_mosaic = False
        self.mosaic_pixmap: Optional[QPixmap] = None

        self.unrevealed_pixmap: Optional[QPixmap] = None
        self.revealed_pixmap: Optional[QPixmap] = None
        self.fit_mode = "stretch"
        self.auto_crop_logo = True
        self.smooth_transform = True

        self.font_family = "ITC Korinna"
        self.font_size = 28
        self.font_bold = True
        self.font_mode = "dynamic"
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

    def set_images(self, unrevealed_path: str, revealed_path: str, fit_mode: str = "stretch", auto_crop_logo: bool = True):
        self.fit_mode = fit_mode
        self.auto_crop_logo = auto_crop_logo
        self.unrevealed_pixmap = QPixmap(unrevealed_path) if unrevealed_path and os.path.exists(unrevealed_path) else None
        self.revealed_pixmap = QPixmap(revealed_path) if revealed_path and os.path.exists(revealed_path) else None
        self.update()

    def set_font_config(self, family: str, size: int, bold: bool = True, color: str = "#ffffff", mode: str = "dynamic"):
        self.font_family = family
        self.font_size = max(10, int(size))
        self.font_bold = bool(bold)
        self.text_color = QColor(color)
        self.font_mode = (mode or "dynamic").lower()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.smooth_transform:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.TextAntialiasing)

        rect = self.rect()

        if self.is_mosaic and self.mosaic_pixmap and not self.mosaic_pixmap.isNull():
            parent = self.parentWidget()
            if parent:
                top_left = self.mapTo(parent, QPoint(0, 0))
                cell_in_grid = QRect(top_left.x(), top_left.y(), self.width(), self.height())
                draw_mosaic_tile(painter, rect, cell_in_grid, parent.rect(), self.mosaic_pixmap, smooth=self.smooth_transform)
                return

        if not self.is_revealed:
            # Requirement #1 & #4: Logo fills 100% of the yellow cell box edge-to-edge
            if self.unrevealed_pixmap and not self.unrevealed_pixmap.isNull():
                logo_fit = "stretch" if self.fit_mode in ("stretch", "zoom") else self.fit_mode
                AssetRenderer.render_background(
                    painter,
                    rect,
                    self.unrevealed_pixmap,
                    fit_mode=logo_fit,
                    smooth=self.smooth_transform,
                    auto_crop=self.auto_crop_logo,
                )
            else:
                painter.fillRect(rect, self.bg_color)
        else:
            if self.revealed_pixmap and not self.revealed_pixmap.isNull():
                AssetRenderer.render_background(
                    painter,
                    rect,
                    self.revealed_pixmap,
                    fit_mode=self.fit_mode,
                    smooth=self.smooth_transform,
                    auto_crop=False,
                )
            else:
                painter.fillRect(rect, self.bg_color)

            title_str = str(self.title).upper()
            text_rect = rect.adjusted(6, 4, -6, -4)

            if self.font_mode == "custom":
                active_size = self.font_size
            else:
                max_dyn = max(self.font_size, int(rect.height() * 0.36))
                active_size = compute_fitted_font_size(
                    self.font_family,
                    self.font_bold,
                    title_str,
                    text_rect,
                    max_size=max_dyn,
                    min_size=9,
                    check_longest_word=True,
                )

            font = QFont(self.font_family, active_size)
            font.setBold(self.font_bold)
            painter.setFont(font)

            # Black drop shadow
            painter.setPen(QColor(0, 0, 0, 240))
            painter.drawText(text_rect.adjusted(2, 2, 2, 2), Qt.AlignCenter | Qt.TextWordWrap, title_str)

            # Foreground text
            painter.setPen(self.text_color)
            painter.drawText(text_rect, Qt.AlignCenter | Qt.TextWordWrap, title_str)


class TVClueCell(QWidget):
    """Clue point cell in the 6x5 matrix. Supports Dynamic vs Custom font sizing (Requirement #2 & #6)."""

    STATE_BLANK = 0
    STATE_POINTS = 1
    STATE_USED = 2

    def __init__(self, points=200, parent=None):
        super().__init__(parent)
        self.points = points
        self.state = self.STATE_POINTS

        self.use_image = True
        self.tile_pixmap: Optional[QPixmap] = None
        self.fit_mode = "zoom"
        self.solid_color = QColor("#060CE9")
        self.off_color = QColor("#020512")
        self.smooth_transform = True

        self.font_family = "Impact"
        self.font_size = 48
        self.font_bold = True
        self.font_mode = "dynamic"
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

    def set_font_config(self, family: str, size: int, bold: bool = True, color: str = "#FFA500", mode: str = "dynamic"):
        self.font_family = family
        self.font_size = max(12, int(size))
        self.font_bold = bool(bold)
        self.text_gold = QColor(color)
        self.font_mode = (mode or "dynamic").lower()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.smooth_transform:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.TextAntialiasing)

        rect = self.rect()

        if self.is_mosaic and self.mosaic_pixmap and not self.mosaic_pixmap.isNull():
            parent = self.parentWidget()
            if parent:
                top_left = self.mapTo(parent, QPoint(0, 0))
                cell_in_grid = QRect(top_left.x(), top_left.y(), self.width(), self.height())
                draw_mosaic_tile(painter, rect, cell_in_grid, parent.rect(), self.mosaic_pixmap, smooth=self.smooth_transform)
                return

        if self.state == self.STATE_USED:
            painter.fillRect(rect, self.off_color)
            return

        if self.use_image and self.tile_pixmap and not self.tile_pixmap.isNull():
            AssetRenderer.render_background(
                painter, rect, self.tile_pixmap, self.fit_mode, smooth=self.smooth_transform
            )
        else:
            painter.fillRect(rect, self.solid_color)

        if self.state == self.STATE_POINTS:
            txt = str(self.points)
            if self.font_mode == "custom":
                pt_size = self.font_size
            else:
                max_dyn = max(18, int(rect.height() * 0.48))
                pt_size = compute_fitted_font_size(
                    self.font_family,
                    self.font_bold,
                    txt,
                    rect.adjusted(6, 2, -6, -2),
                    max_size=max_dyn,
                    min_size=14,
                    check_longest_word=True,
                )

            font = QFont(self.font_family, pt_size)
            font.setBold(self.font_bold)
            painter.setFont(font)

            painter.setPen(QColor(0, 0, 0, 245))
            painter.drawText(rect.adjusted(4, 4, 4, 4), Qt.AlignCenter, txt)

            painter.setPen(self.text_gold)
            painter.drawText(rect, Qt.AlignCenter, txt)


# =============================================================================
# 2. POINT ZOOM WIDGET (100% FULL WINDOW FILL - REQUIREMENT #3)
# =============================================================================

class TVPointZoomWidget(QWidget):
    """Full-window point zoom widget expanding the selected point tile into a centered massive number.
    Fills 100% of the window (full yellow zone in Image 3, without any 90% black margin).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.points = 200
        self.use_image = True
        self.tile_pixmap: Optional[QPixmap] = None
        self.fit_mode = "zoom"
        self.solid_color = QColor("#060CE9")
        self.font_family = "Impact"
        self.font_bold = True
        self.text_gold = QColor("#FFA500")
        self.smooth_transform = True
        self.hide()

    def set_config(
        self,
        points: int,
        use_image: bool,
        pixmap: Optional[QPixmap],
        solid_color: QColor,
        fit_mode: str = "zoom",
        font_family: str = "Impact",
        font_bold: bool = True,
        text_color: QColor = QColor("#FFA500"),
    ):
        self.points = points
        self.use_image = use_image
        self.tile_pixmap = pixmap
        self.solid_color = solid_color
        self.fit_mode = fit_mode
        self.font_family = font_family
        self.font_bold = font_bold
        self.text_gold = text_color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.smooth_transform:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.TextAntialiasing)

        # Requirement #3: Fill 100% of the window (full yellow border area, zero black bars!)
        card_rect = self.rect()

        if self.use_image and self.tile_pixmap and not self.tile_pixmap.isNull():
            AssetRenderer.render_background(
                painter, card_rect, self.tile_pixmap, self.fit_mode, smooth=self.smooth_transform
            )
        else:
            painter.fillRect(card_rect, self.solid_color)

        calc_size = max(36, int(card_rect.height() * 0.45))
        font = QFont(self.font_family, calc_size)
        font.setBold(self.font_bold)
        painter.setFont(font)

        txt = str(self.points)
        offset = max(3, int(calc_size * 0.06))

        painter.setPen(QColor(0, 0, 0, 245))
        painter.drawText(card_rect.adjusted(offset, offset, offset, offset), Qt.AlignCenter, txt)

        painter.setPen(self.text_gold)
        painter.drawText(card_rect, Qt.AlignCenter, txt)


# =============================================================================
# 3. 3D HORIZONTAL CARD FLIP WIDGET (FLIP -> BLACK BACKING -> CLUE - REQ #8)
# =============================================================================

class TVCardFlipTransitionWidget(QWidget):
    """Hardware-friendly 3D Horizontal Card Flip Transition Widget.
    Fixes Requirement #8:
    - Always paints a 100% opaque solid #000000 black background behind the foreshortened rotating card
      so the clue question never leaks into the background during the flip.
    - Flips Front (Daily Double Splash) -> 90° Solid Black Edge-On -> Back (Clean Blue Card),
      and reveals the Clue Question text cleanly once the flip completes at 180°.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0.0
        self.front_pixmap: Optional[QPixmap] = None
        self.back_pixmap: Optional[QPixmap] = None
        self.smooth_transform = True
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.hide()

    def get_angle(self) -> float:
        return self._angle

    def set_angle(self, angle: float):
        self._angle = float(angle)
        self.update()

    angle = Property(float, get_angle, set_angle)

    def start_flip(self, front_pixmap: QPixmap, back_pixmap: QPixmap, duration: int = 900, finished_callback=None):
        if hasattr(self, "anim") and self.anim.state() == QPropertyAnimation.Running:
            self.anim.stop()

        self.front_pixmap = front_pixmap
        self.back_pixmap = back_pixmap
        self._angle = 0.0
        self.show()
        self.raise_()

        self.anim = QPropertyAnimation(self, b"angle", self)
        self.anim.setDuration(max(250, int(duration)))
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
        painter = QPainter(self)
        if self.smooth_transform:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)

        w = self.width()
        h = self.height()

        # Always paint pure black #000000 background behind the rotating 3D card!
        painter.fillRect(QRect(0, 0, w, h), QColor("#000000"))

        if not self.front_pixmap or not self.back_pixmap or w <= 0 or h <= 0:
            return

        ang = self._angle
        # Hold pure black for a crisp 4° window right at 90° edge-on
        if 88.0 <= ang <= 92.0:
            return

        is_front = ang < 90.0
        pix = self.front_pixmap if is_front else self.back_pixmap
        if not pix or pix.isNull():
            return

        rot_deg = ang if is_front else (ang - 180.0)

        t = QTransform()
        t.translate(w / 2.0, h / 2.0)
        persp = 0.0012
        if not is_front:
            persp = -persp
        t.m31 = persp * rot_deg
        t.rotate(rot_deg, Qt.YAxis)
        t.translate(-w / 2.0, -h / 2.0)

        painter.setTransform(t)
        scaled_pix = AssetRenderer.get_scaled_pixmap(pix, w, h, fit_mode="zoom", smooth=self.smooth_transform)
        px = (w - scaled_pix.width()) // 2
        py = (h - scaled_pix.height()) // 2
        painter.drawPixmap(px, py, scaled_pix)


# =============================================================================
# 4. CATEGORY REVEAL 3-LAYER TRANSITION CARD & ENGINE (FULL BLEED - REQ #1 & #6)
# =============================================================================

class TVCategoryCardWidget(QWidget):
    """Single full-bleed card block for Category Reveal (100% window fill, auto-cropped logo, synced font)."""

    def __init__(self, logo_path=None, parent=None):
        super().__init__(parent)
        self.logo_path = logo_path
        self.setStyleSheet("background-color: #000000; border: none;")

        self.title = "CATEGORY"
        self.bg_color = QColor("#060CE9")
        self.bg_pixmap: Optional[QPixmap] = None

        # Layer 1: Blue Card Box (90% width & height, centered to create black border)
        self.inner_box = _CoverImageWidget(self, mode="cover")
        self.inner_box.set_bg_color(self.bg_color)

        # Layer 2: Category Title Text (AutoFitLabel supporting Dynamic & Custom modes)
        self.title_label = AutoFitLabel(max_point_size=72, min_point_size=20, parent=self.inner_box)
        self.title_label.configure_typography("ITC Korinna", 52, True, "dynamic", "#FFFFFF")

        self.title_shadow = QGraphicsDropShadowEffect(self.title_label)
        self.title_shadow.setBlurRadius(2)
        self.title_shadow.setOffset(3, 3)
        self.title_shadow.setColor(QColor("#000000"))
        self.title_label.setGraphicsEffect(self.title_shadow)

        # Layer 3: Full-bleed Logo Overlay with auto_crop=True so logo fills 100% of screen
        self.logo_overlay = _CoverImageWidget(self.inner_box, mode="stretch", auto_crop=True)
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

    def set_logo(self, path: str, auto_crop: bool = True):
        self.logo_path = path
        self.logo_overlay.auto_crop = auto_crop
        self._load_logo()

    def set_bg(self, image_path: str, hex_color: str):
        self.bg_color = QColor(hex_color)
        self.bg_pixmap = QPixmap(image_path) if image_path and os.path.exists(image_path) else None
        self.inner_box.set_pixmap(self.bg_pixmap)
        self.inner_box.set_bg_color(self.bg_color)
        self.logo_overlay.set_bg_color(self.bg_color)

    def set_font_config(self, family: str, size: int, bold: bool = True, color: str = "#FFFFFF", mode: str = "dynamic"):
        # Scale up category intro card font relative to small grid cell header size
        intro_size = max(36, int(size * 1.8)) if mode == "custom" else max(64, int(size * 2.0))
        self.title_label.configure_typography(family, intro_size, bold, mode, color)

    def set_category_title(self, title: str):
        self.title = str(title).upper()
        self.title_label.setText(self.title)
        self.reset_logo_opacity()

    def set_card_bg_color(self, hex_color: str):
        self.set_bg("", hex_color)

    def reset_logo_opacity(self):
        self.logo_opacity.setOpacity(1.0)

    def fade_out_logo(self, duration=500, finished_callback=None):
        self.anim = QPropertyAnimation(self.logo_opacity, b"opacity", self)
        self.anim.setDuration(duration)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.setEasingCurve(QEasingCurve.InOutQuad)
        if finished_callback:
            self.anim.finished.connect(finished_callback)
        self.anim.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#000000"))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        # Framing: Cụm Logo + Chủ đề được thu nhỏ 10% (đạt kích thước 90%) và căn giữa để tạo viền đen
        card_w = max(100, int(w * 0.90))
        card_h = max(100, int(h * 0.90))
        card_x = (w - card_w) // 2
        card_y = (h - card_h) // 2
        self.inner_box.setGeometry(card_x, card_y, card_w, card_h)
        self.title_label.setGeometry(30, 30, max(1, card_w - 60), max(1, card_h - 60))
        self.logo_overlay.setGeometry(0, 0, card_w, card_h)


class TVCategoryRevealWidget(QWidget):
    """Transition Engine managing manual 6-category intro sequence via Host controls."""

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

    def set_logo_path(self, path: str, auto_crop: bool = True):
        self.logo_path = path
        self.card_a.set_logo(path, auto_crop=auto_crop)
        self.card_b.set_logo(path, auto_crop=auto_crop)

    def set_card_color(self, hex_color):
        self.card_a.set_card_bg_color(hex_color)
        self.card_b.set_card_bg_color(hex_color)

    def set_card_style(self, bg_image_path: str, hex_color: str):
        self.card_a.set_bg(bg_image_path, hex_color)
        self.card_b.set_bg(bg_image_path, hex_color)

    def set_font_config(self, family: str, size: int, bold: bool = True, color: str = "#FFFFFF", mode: str = "dynamic"):
        self.card_a.set_font_config(family, size, bold, color, mode)
        self.card_b.set_font_config(family, size, bold, color, mode)

    def show_column(self, col_index: int = 0):
        self.current_index = max(0, min(col_index, len(self.categories) - 1))
        w, h = self.width(), self.height()
        self.active_card = self.card_a
        self.next_card = self.card_b

        self.active_card.setGeometry(0, 0, w, h)
        self.next_card.setGeometry(w, 0, w, h)

        cat_title = self.categories[self.current_index] if self.current_index < len(self.categories) else f"CATEGORY {self.current_index+1}"
        self.active_card.set_category_title(cat_title)
        self.active_card.reset_logo_opacity()
        self.active_card.show()
        self.next_card.show()

    def fade_logo(self):
        self.active_card.fade_out_logo(duration=500)

    @Slot(bool)
    def slide_next(self, auto_fade: bool = False):
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
        anim_out.setDuration(500)
        anim_out.setStartValue(QPoint(0, 0))
        anim_out.setEndValue(QPoint(-w, 0))
        anim_out.setEasingCurve(QEasingCurve.InOutCubic)

        anim_in = QPropertyAnimation(self.next_card, b"pos")
        anim_in.setDuration(500)
        anim_in.setStartValue(QPoint(w, 0))
        anim_in.setEndValue(QPoint(0, 0))
        anim_in.setEasingCurve(QEasingCurve.InOutCubic)

        self.anim_group.addAnimation(anim_out)
        self.anim_group.addAnimation(anim_in)
        self.anim_group.finished.connect(self._on_slide_finished)

        # Requirement #7: Use round_category_intro sound (NOT hardcoded "fill"!)
        event_bus.play_sound_event.emit("round_category_intro")
        self.anim_group.start()

    def _on_slide_finished(self):
        self.active_card, self.next_card = self.next_card, self.active_card
        if getattr(self, "_pending_auto_fade", False):
            self._pending_auto_fade = False
            QTimer.singleShot(150, self.fade_logo)

    def handle_manual_step(self, step: int):
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


# =============================================================================
# 5. CLUE SCREEN WIDGET (UNIFIED FONT & FULL-BLEED - REQ #2, #3, #6)
# =============================================================================

class TVClueScreenWidget(QWidget):
    """Standard broadcast clue card (100% full window background, unified Dynamic/Custom typography)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #000000; border: none;")
        self.question_text = ""
        self.bg_color = QColor("#060CE9")
        self.bg_pixmap: Optional[QPixmap] = None
        self.asset_pixmap: Optional[QPixmap] = None

        self.font_family = "ITC Korinna"
        self.font_size = 48
        self.answer_font_size = 30
        self.font_bold = True
        self.font_mode = "dynamic"
        self.text_color = QColor("#FFFFFF")
        self.shadow_dx = 3
        self.shadow_dy = 3
        self.shadow_blur = 2
        self.shadow_color = QColor("#000000")
        self.smooth_transform = True

        self.answer_label = AutoFitLabel(max_point_size=36, min_point_size=14, parent=self)
        self.answer_label.configure_typography(self.font_family, self.answer_font_size, True, "dynamic", "#FFFFFF")
        self.ans_shadow = QGraphicsDropShadowEffect(self.answer_label)
        self.ans_shadow.setBlurRadius(2)
        self.ans_shadow.setOffset(2, 2)
        self.ans_shadow.setColor(QColor("#000000"))
        self.answer_label.setGraphicsEffect(self.ans_shadow)
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

    def set_font_config(
        self,
        family: str,
        size: int,
        bold: bool = True,
        color: str = "#FFFFFF",
        mode: str = "dynamic",
        answer_size: int = 30,
        shadow_dx: int = 3,
        shadow_dy: int = 3,
        shadow_blur: int = 2,
    ):
        self.font_family = family
        self.font_size = max(14, int(size))
        self.answer_font_size = max(12, int(answer_size))
        self.font_bold = bool(bold)
        self.text_color = QColor(color)
        self.font_mode = (mode or "dynamic").lower()
        self.shadow_dx = int(shadow_dx)
        self.shadow_dy = int(shadow_dy)
        self.shadow_blur = int(shadow_blur)

        self.answer_label.configure_typography(
            self.font_family, self.answer_font_size, self.font_bold, self.font_mode, color
        )
        self.ans_shadow.setBlurRadius(self.shadow_blur)
        self.ans_shadow.setOffset(self.shadow_dx, self.shadow_dy)
        self.update()

    def render_background_only(self, target_pixmap: QPixmap):
        """Renders only the full-bleed background card (without question text) for 3D Flip back face."""
        painter = QPainter(target_pixmap)
        if self.smooth_transform:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = target_pixmap.rect()
        if self.bg_pixmap and not self.bg_pixmap.isNull():
            draw_cover_image(painter, rect, self.bg_pixmap, smooth=self.smooth_transform)
        else:
            painter.fillRect(rect, self.bg_color)
        painter.end()

    def _get_active_clue_font_size(self, text: str, text_rect: QRect) -> int:
        if self.font_mode == "custom":
            return self.font_size
        dyn_max = max(self.font_size, int(self.height() * 0.085))
        return compute_fitted_font_size(
            self.font_family,
            self.font_bold,
            text,
            text_rect,
            max_size=dyn_max,
            min_size=16,
            check_longest_word=True,
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.smooth_transform:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.TextAntialiasing)

        w, h = self.width(), self.height()
        card_rect = QRect(0, 0, w, h)

        if self.bg_pixmap and not self.bg_pixmap.isNull():
            draw_cover_image(painter, card_rect, self.bg_pixmap, smooth=self.smooth_transform)
        else:
            painter.fillRect(card_rect, self.bg_color)

        if not self.question_text:
            return

        if self.asset_pixmap and not self.asset_pixmap.isNull():
            img_rect = QRect(40, 28, w - 80, int(h * 0.50))
            text_rect = QRect(50, int(h * 0.54), w - 100, int(h * 0.36))

            draw_contain_image(painter, img_rect, self.asset_pixmap, smooth=self.smooth_transform)
        else:
            pad_x = max(48, int(w * 0.06))
            pad_y = max(40, int(h * 0.08))
            text_rect = QRect(pad_x, pad_y, w - 2 * pad_x, h - 2 * pad_y - 40)

        active_size = self._get_active_clue_font_size(self.question_text, text_rect)
        font = QFont(self.font_family, active_size)
        font.setBold(self.font_bold)
        painter.setFont(font)

        painter.setPen(QColor(0, 0, 0, 250))
        painter.drawText(
            text_rect.adjusted(self.shadow_dx, self.shadow_dy, self.shadow_dx, self.shadow_dy),
            Qt.AlignCenter | Qt.TextWordWrap,
            self.question_text,
        )
        painter.setPen(self.text_color)
        painter.drawText(text_rect, Qt.AlignCenter | Qt.TextWordWrap, self.question_text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        lbl_w = max(200, int(w * 0.86))
        lbl_h = max(52, int(h * 0.11))
        lbl_y = h - lbl_h - max(24, int(h * 0.04))
        self.answer_label.setGeometry((w - lbl_w) // 2, lbl_y, lbl_w, lbl_h)


# =============================================================================
# 6. FINAL JEOPARDY SCREEN WIDGET (UNIFIED FONT WITH CLUE SCREEN - REQ #6)
# =============================================================================

class TVFinalScreenWidget(QWidget):
    """Final Jeopardy Sequencer (3 Steps + 15s Blue-to-Red Cross-fade).
    Fixes Requirement #6: Uses the exact same font family, mode (Dynamic vs Custom),
    weight, color, and drop shadow as TVClueScreenWidget so there is zero font discrepancy!
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

        self.font_family = "ITC Korinna"
        self.font_size = 48
        self.answer_font_size = 30
        self.header_font_size = 28
        self.font_bold = True
        self.font_mode = "dynamic"
        self.text_color = "#FFFFFF"
        self.shadow_dx = 3
        self.shadow_dy = 3
        self.shadow_blur = 2

        self.countdown_ms = 30000
        self.countdown_timer = QTimer(self)
        self.countdown_timer.setInterval(100)
        self.countdown_timer.timeout.connect(self._on_countdown_tick)

        self.crossfade_timer = QTimer(self)
        self.crossfade_timer.setSingleShot(True)
        self.crossfade_timer.timeout.connect(self.start_crossfade)

        self._build_ui()

    def _build_ui(self):
        # 1. Step 1: Splash Widget (Full-bleed 100%)
        self.splash_widget = _CoverImageWidget(self, mode="cover")
        self.splash_widget.fallback_text = "FINAL JEOPARDY!"

        # 2. Step 2: Category Widget
        self.cat_widget = QWidget(self)
        self.cat_widget.setStyleSheet("background-color: #000000; border: none;")

        self.cat_card = _CoverImageWidget(self.cat_widget, mode="cover")
        self.cat_card.set_bg_color(QColor("#0b1354"))

        self.cat_layout = QVBoxLayout(self.cat_card)
        self.cat_layout.setContentsMargins(48, 40, 48, 40)
        self.cat_layout.setAlignment(Qt.AlignCenter)

        self.cat_name_lbl = AutoFitLabel(max_point_size=76, min_point_size=24, parent=self.cat_card)
        self.cat_name_lbl.configure_typography(self.font_family, 56, self.font_bold, self.font_mode, self.text_color)
        self.c_shadow = QGraphicsDropShadowEffect(self.cat_name_lbl)
        self.c_shadow.setBlurRadius(2)
        self.c_shadow.setOffset(3, 3)
        self.c_shadow.setColor(QColor("#000000"))
        self.cat_name_lbl.setGraphicsEffect(self.c_shadow)
        self.cat_layout.addWidget(self.cat_name_lbl)

        # 3. Step 3: Clue Widget with Stacked Backgrounds
        self.clue_widget = QWidget(self)
        self.clue_widget.setStyleSheet("background-color: #000000; border: none;")

        self.clue_card = QWidget(self.clue_widget)
        self.clue_card.setStyleSheet(FLAT_CARD_STYLE)

        self.red_layer = _CoverImageWidget(self.clue_card, mode="cover")
        self.red_layer.set_bg_color(self.red_color)

        self.blue_layer = _CoverImageWidget(self.clue_card, mode="cover")
        self.blue_layer.set_bg_color(self.blue_color)
        self.blue_opacity = QGraphicsOpacityEffect(self.blue_layer)
        self.blue_opacity.setOpacity(1.0)
        self.blue_layer.setGraphicsEffect(self.blue_opacity)

        self.clue_fg = QWidget(self.clue_card)
        self.clue_fg.setStyleSheet(FLAT_CARD_STYLE)
        fg_layout = QVBoxLayout(self.clue_fg)
        fg_layout.setContentsMargins(50, 40, 50, 80)
        fg_layout.setAlignment(Qt.AlignCenter)

        self.clue_title_lbl = QLabel("", self.clue_fg)
        self.clue_title_lbl.setVisible(False)
        self.progress_bar = QProgressBar(self.clue_fg)
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 300)
        self.progress_bar.setValue(300)

        self.clue_content_lbl = AutoFitLabel(max_point_size=54, min_point_size=16, parent=self.clue_fg)
        self.clue_content_lbl.configure_typography(self.font_family, self.font_size, self.font_bold, self.font_mode, self.text_color)
        self.clue_shadow = QGraphicsDropShadowEffect(self.clue_content_lbl)
        self.clue_shadow.setBlurRadius(2)
        self.clue_shadow.setOffset(3, 3)
        self.clue_shadow.setColor(QColor("#000000"))
        self.clue_content_lbl.setGraphicsEffect(self.clue_shadow)

        self.answer_label = AutoFitLabel(max_point_size=36, min_point_size=14, parent=self.clue_fg)
        self.answer_label.configure_typography(self.font_family, self.answer_font_size, self.font_bold, self.font_mode, self.text_color)
        self.ans_shadow = QGraphicsDropShadowEffect(self.answer_label)
        self.ans_shadow.setBlurRadius(2)
        self.ans_shadow.setOffset(2, 2)
        self.ans_shadow.setColor(QColor("#000000"))
        self.answer_label.setGraphicsEffect(self.ans_shadow)
        self.answer_label.setVisible(False)

        fg_layout.addWidget(self.clue_content_lbl, 1)
        self._update_visibility()

    def set_font_config(
        self,
        family: str,
        size: int,
        bold: bool = True,
        color: str = "#FFFFFF",
        mode: str = "dynamic",
        answer_size: int = 30,
        header_size: int = 28,
        shadow_dx: int = 3,
        shadow_dy: int = 3,
        shadow_blur: int = 2,
    ):
        """Synchronizes Final Jeopardy typography with Regular Clue Screen typography (Requirement #6)."""
        self.font_family = family
        self.font_size = max(14, int(size))
        self.answer_font_size = max(12, int(answer_size))
        self.header_font_size = max(14, int(header_size))
        self.font_bold = bool(bold)
        self.text_color = color
        self.font_mode = (mode or "dynamic").lower()
        self.shadow_dx = int(shadow_dx)
        self.shadow_dy = int(shadow_dy)
        self.shadow_blur = int(shadow_blur)

        cat_target_size = max(36, int(self.header_font_size * 1.8)) if self.font_mode == "custom" else max(56, self.font_size)
        self.cat_name_lbl.max_point_size = max(54, cat_target_size)
        self.cat_name_lbl.configure_typography(family, cat_target_size, self.font_bold, self.font_mode, color)

        self.clue_content_lbl.max_point_size = max(48, self.font_size)
        self.clue_content_lbl.configure_typography(family, self.font_size, self.font_bold, self.font_mode, color)

        self.answer_label.max_point_size = max(32, self.answer_font_size)
        self.answer_label.configure_typography(family, self.answer_font_size, self.font_bold, self.font_mode, color)

        for sh in (self.c_shadow, self.clue_shadow, self.ans_shadow):
            sh.setBlurRadius(self.shadow_blur)
            sh.setOffset(self.shadow_dx, self.shadow_dy)
        self.update()

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
            self.crossfade_timer.start(15000)

    def restart_final_countdown(self):
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
        if self.step != self.STEP_CLUE:
            return
        if hasattr(self, "crossfade_anim") and self.crossfade_anim.state() == QPropertyAnimation.Running:
            return
        self.crossfade_anim = QPropertyAnimation(self.blue_opacity, b"opacity", self)
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

        lbl_w = max(200, int(w * 0.86))
        lbl_h = max(52, int(h * 0.11))
        lbl_y = h - lbl_h - max(24, int(h * 0.04))
        self.answer_label.setGeometry((w - lbl_w) // 2, lbl_y, lbl_w, lbl_h)


# =============================================================================
# 7. STANDBY SCREEN WITH INTRO VIDEO -> STATIC IMAGE MERGE & OUTRO (REQ #5 & #7)
# =============================================================================

class TVStandbyIntroWidget(QWidget):
    """Standby Screen Widget supporting:
    - Static Standby Wallpaper (Full-bleed 100%)
    - Intro Video Playback via QMediaPlayer + QVideoSink -> Smooth Cross-fade/Merge into Static Standby
      Wallpaper after user-configured duration (intro_merge_seconds).
    - Outro Music Playback directly over the Static Standby Wallpaper.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pixmap: Optional[QPixmap] = None
        self.current_video_frame_img: Optional[QImage] = None
        self.is_playing_video = False
        self._merge_progress = 1.0  # 0.0 = 100% Video, 1.0 = 100% Static Standby Image
        self.bg_color = QColor("#060CE9")
        self.fallback_text = "JEOPARDY!"
        self.fallback_font = QFont("Impact", 72, QFont.Bold)
        self.fallback_color = QColor("#FFCC00")
        self.smooth_transform = True

        # Video Player + Audio Output + Video Sink for hardware-composited crossfade
        self.video_audio = QAudioOutput(self)
        self.video_audio.setVolume(0.90)
        self.video_sink = QVideoSink(self)
        self.video_sink.videoFrameChanged.connect(self._on_video_frame_changed)

        self.video_player = QMediaPlayer(self)
        self.video_player.setAudioOutput(self.video_audio)
        self.video_player.setVideoSink(self.video_sink)
        self.video_player.mediaStatusChanged.connect(self._on_media_status_changed)

        self.merge_timer = QTimer(self)
        self.merge_timer.setSingleShot(True)
        self.merge_timer.timeout.connect(self._start_crossfade_to_static)
        self._fade_duration_ms = 1500

    def get_merge_progress(self) -> float:
        return self._merge_progress

    def set_merge_progress(self, val: float):
        self._merge_progress = max(0.0, min(1.0, float(val)))
        # Smoothly attenuate video audio as static wallpaper merges in
        if self.is_playing_video:
            self.video_audio.setVolume(max(0.0, 0.90 * (1.0 - self._merge_progress)))
        self.update()

    merge_progress = Property(float, get_merge_progress, set_merge_progress)

    def set_pixmap(self, pixmap: Optional[QPixmap]):
        self.pixmap = pixmap
        self.update()

    def show_static_standby(self):
        """Immediately switches to static standby wallpaper."""
        self.stop_video()
        self._merge_progress = 1.0
        self.update()

    def start_intro_video(self, video_path: str, merge_seconds: float = 5.0, fade_duration_ms: int = 1500):
        """Plays intro video and schedules smooth cross-fade merge into static standby image."""
        if not video_path or not os.path.isfile(video_path):
            self.show_static_standby()
            return

        self.stop_video()
        self._fade_duration_ms = max(200, int(fade_duration_ms))
        self._merge_progress = 0.0
        self.is_playing_video = True
        self.video_audio.setVolume(0.90)

        self.video_player.setSource(QUrl.fromLocalFile(str(Path(video_path).resolve())))
        self.video_player.play()

        if merge_seconds > 0.0:
            self.merge_timer.start(int(merge_seconds * 1000))

        self.update()

    def _on_video_frame_changed(self, frame: QVideoFrame):
        if not self.is_playing_video:
            return
        if frame.isValid():
            img = frame.toImage()
            if not img.isNull():
                self.current_video_frame_img = img
                self.update()

    def _on_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self._merge_progress < 1.0:
                self._start_crossfade_to_static()

    def _start_crossfade_to_static(self):
        self.merge_timer.stop()
        if hasattr(self, "merge_anim") and self.merge_anim.state() == QPropertyAnimation.Running:
            return
        self.merge_anim = QPropertyAnimation(self, b"merge_progress", self)
        self.merge_anim.setDuration(self._fade_duration_ms)
        self.merge_anim.setStartValue(self._merge_progress)
        self.merge_anim.setEndValue(1.0)
        self.merge_anim.setEasingCurve(QEasingCurve.InOutQuad)
        self.merge_anim.finished.connect(self._on_merge_finished)
        self.merge_anim.start()

    def _on_merge_finished(self):
        self.video_player.stop()
        self.is_playing_video = False
        self.current_video_frame_img = None
        self._merge_progress = 1.0
        self.update()

    def stop_video(self):
        self.merge_timer.stop()
        if hasattr(self, "merge_anim") and self.merge_anim.state() == QPropertyAnimation.Running:
            self.merge_anim.stop()
        try:
            self.video_player.stop()
        except Exception:
            pass
        self.is_playing_video = False
        self.current_video_frame_img = None
        self._merge_progress = 1.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.smooth_transform:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = self.rect()

        # 1. Draw live Intro Video frame if active and merge_progress < 1.0
        if self.is_playing_video and self.current_video_frame_img is not None and not self.current_video_frame_img.isNull():
            vid_pix = QPixmap.fromImage(self.current_video_frame_img)
            transform = Qt.SmoothTransformation if self.smooth_transform else Qt.FastTransformation
            scaled_vid = vid_pix.scaled(rect.size(), Qt.KeepAspectRatioByExpanding, transform)
            vx = (rect.width() - scaled_vid.width()) // 2
            vy = (rect.height() - scaled_vid.height()) // 2
            painter.drawPixmap(vx, vy, scaled_vid)
        else:
            painter.fillRect(rect, QColor("#000000"))

        # 2. Overlay Static Standby Wallpaper with opacity = merge_progress
        if self._merge_progress > 0.0:
            painter.save()
            painter.setOpacity(self._merge_progress)
            if self.pixmap and not self.pixmap.isNull():
                draw_cover_image(painter, rect, self.pixmap, smooth=self.smooth_transform)
            else:
                painter.fillRect(rect, self.bg_color)
                if self.fallback_text:
                    painter.setFont(self.fallback_font)
                    painter.setPen(self.fallback_color)
                    painter.drawText(rect, Qt.AlignCenter, self.fallback_text)
            painter.restore()


# =============================================================================
# 8. OPENGL HARDWARE ACCELERATION SURFACE (REQUIREMENT #9)
# =============================================================================

class OpenGLHardwareSurface(QOpenGLWidget):
    """Real OpenGL hardware acceleration context widget initializing GPU VSync,
    multisampling (4x MSAA), and smooth texture blending on the TV Display window.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        if HAS_QOPENGL and isinstance(self, QOpenGLWidget):
            fmt = QSurfaceFormat()
            fmt.setRenderableType(QSurfaceFormat.OpenGL)
            fmt.setSwapBehavior(QSurfaceFormat.DoubleBuffer)
            fmt.setSwapInterval(1)
            fmt.setSamples(4)
            self.setFormat(fmt)

    def initializeGL(self):
        if HAS_PYOPENGL:
            try:
                gl.glEnable(gl.GL_MULTISAMPLE)
                gl.glEnable(gl.GL_BLEND)
                gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
                gl.glHint(gl.GL_LINE_SMOOTH_HINT, gl.GL_NICEST)
                gl.glHint(gl.GL_POLYGON_SMOOTH_HINT, gl.GL_NICEST)
            except Exception:
                pass

    def paintGL(self):
        if HAS_PYOPENGL:
            try:
                gl.glClearColor(0.0, 0.0, 0.0, 1.0)
                gl.glClear(gl.GL_COLOR_BUFFER_BIT)
            except Exception:
                pass


# =============================================================================
# 9. TV STUDIO DISPLAY WINDOW (MAIN STAGE)
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

        # Singleton Audio Subsystem
        self.audio_manager = AudioManager(parent=self)

        # Load Theme Config
        self.theme = ThemeConfigManager.load_theme_xml()
        self.bezel_width = self.theme.get("bezel_width", 8)
        self.bezel_color = QColor(self.theme.get("bezel_color", "#000000"))
        self.standby_pixmap: Optional[QPixmap] = None

        # Animation settings
        self.enable_point_zoom = True
        self.zoom_duration_ms = 400
        self.enable_dd_flip = True
        self.flip_duration_ms = 900
        self.performance_profile = "ultra"
        self.animation_fps = 120
        self.smooth_transform = True

        # Board State
        self.current_round = 1
        self.category_names = [f"CATEGORY {i+1}" for i in range(6)]
        self.cells: Dict[Tuple[int, int], TVClueCell] = {}
        self.cat_cells = []
        self.current_opened_coords = None
        self.pending_clue_payload = None

        # Random Fill Timer
        self.fill_timer = QTimer(self)
        self.fill_timer.setInterval(55)
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

        # 3D horizontal card flip transition overlay widget
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
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        if hasattr(self, "_gl_surface") and self._gl_surface is not None:
            self._gl_surface.setGeometry(0, 0, w, h)
        if hasattr(self, "point_zoom_widget") and self.point_zoom_widget.isVisible():
            self.point_zoom_widget.setGeometry(0, 0, w, h)
        if hasattr(self, "card_flip_widget") and self.card_flip_widget.isVisible():
            self.card_flip_widget.setGeometry(0, 0, w, h)

    # -------------------------------------------------------------------------
    # UI PAGE BUILDERS
    # -------------------------------------------------------------------------

    def _build_page_board(self):
        self.board_container = QWidget()
        self.board_container.setStyleSheet(f"background-color: {self.bezel_color.name()};")

        self.board_grid = QGridLayout(self.board_container)
        self.board_grid.setContentsMargins(self.bezel_width, self.bezel_width, self.bezel_width, self.bezel_width)
        self.board_grid.setSpacing(self.bezel_width)

        self.cat_cells = []
        for c in range(6):
            cell = TVCategoryCell(self.category_names[c])
            self.cat_cells.append(cell)
            self.board_grid.addWidget(cell, 0, c)

        self.cells = {}
        for r in range(5):
            pts = (r + 1) * 200
            for c in range(6):
                cell = TVClueCell(points=pts)
                self.cells[(c, r)] = cell
                self.board_grid.addWidget(cell, r + 1, c)

        # Ensure uniform row/col stretch
        self.board_grid.setRowStretch(0, 10)
        for r in range(1, 6):
            self.board_grid.setRowStretch(r, 10)
        for c in range(6):
            self.board_grid.setColumnStretch(c, 1)

        self.stack.addWidget(self.board_container)  # INDEX_BOARD = 0

    def _build_page_category_reveal(self):
        self.cat_reveal_widget = TVCategoryRevealWidget(self)
        self.cat_reveal_widget.set_categories(self.category_names)
        self.stack.addWidget(self.cat_reveal_widget)  # INDEX_CATEGORY_REVEAL = 1

    def _build_page_daily_double(self):
        self.dd_splash_widget = _CoverImageWidget(self, mode="cover")
        self.dd_splash_widget.fallback_text = "DAILY DOUBLE"
        self.stack.addWidget(self.dd_splash_widget)  # INDEX_DAILY_DOUBLE = 2

    def _build_page_clean_clue(self):
        self.clue_screen_widget = TVClueScreenWidget(self)
        self.stack.addWidget(self.clue_screen_widget)  # INDEX_QUESTION = 3

    def _build_page_final(self):
        self.final_screen_widget = TVFinalScreenWidget(self)
        self.stack.addWidget(self.final_screen_widget)  # INDEX_FINAL = 4

    def _build_page_standby(self):
        self.standby_normal_widget = TVStandbyIntroWidget(self)
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
    # STATE MACHINE ACTIONS & CATEGORY EXHAUSTION LOGIC (REQ #4)
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

    def _update_exhausted_categories(self):
        """Requirement #4: When all 5 questions in a column (yellow zone) have been answered,
        automatically switch that column's category header cell (red zone) back to the Jeopardy! logo.
        """
        for c in range(6):
            if c >= len(self.cat_cells):
                continue
            all_used = all(
                self.cells.get((c, r)) is not None and self.cells[(c, r)].state == TVClueCell.STATE_USED
                for r in range(5)
            )
            if all_used:
                self.cat_cells[c].set_revealed(False)
            else:
                self.cat_cells[c].set_revealed(True)

    @Slot()
    def show_blank_board(self):
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
        if self.stack.currentIndex() == self.INDEX_FINAL:
            self.final_screen_widget.restart_final_countdown()
            event_bus.play_sound_event.emit("think_30s")

    @Slot(bool)
    def handle_toggle_tv_window(self, visible: bool):
        if visible:
            self.show()
            self.raise_()
        else:
            self.hide()

    @Slot()
    def start_board_fill(self):
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

    # --- CATEGORY REVEAL SLIDE ENGINE ---
    @Slot(dict)
    def handle_category_reveal(self, config=None):
        if config is None:
            config = {"auto": False, "step": 0, "col_index": 0}
        start_col = int(config.get("col_index", 0))
        self.handle_category_show_logo(start_col)

    @Slot(int)
    def handle_category_show_logo(self, col_index: int = 0):
        cats = [self.cat_cells[i].title for i in range(6)]
        self.cat_reveal_widget.set_categories(cats)
        self.stack.setCurrentIndex(self.INDEX_CATEGORY_REVEAL)
        self.cat_reveal_widget.show_column(col_index)

    @Slot()
    def handle_category_fade_logo(self):
        if self.stack.currentIndex() == self.INDEX_CATEGORY_REVEAL:
            self.cat_reveal_widget.fade_logo()

    @Slot(bool)
    def handle_category_slide_next(self, auto_fade: bool = False):
        if self.stack.currentIndex() == self.INDEX_CATEGORY_REVEAL:
            self.cat_reveal_widget.slide_next(auto_fade=auto_fade)

    @Slot(int)
    def handle_category_reveal_step(self, step: int):
        if self.stack.currentIndex() != self.INDEX_CATEGORY_REVEAL:
            cats = [self.cat_cells[i].title for i in range(6)]
            self.cat_reveal_widget.set_categories(cats)
            self.stack.setCurrentIndex(self.INDEX_CATEGORY_REVEAL)
            self.cat_reveal_widget.show_column(0)
        self.cat_reveal_widget.handle_manual_step(step)

    @Slot()
    def handle_category_next(self):
        self.handle_category_slide_next(auto_fade=False)

    @Slot()
    def handle_cancel_category_reveal(self):
        if self.stack.currentIndex() == self.INDEX_CATEGORY_REVEAL:
            self.cat_reveal_widget.cancel()
            self.stack.setCurrentIndex(self.INDEX_BOARD)
            self._update_exhausted_categories()

    # --- POINT ZOOM TRANSITION & TOGGLEABLE ANIMATION (REQ #3 & #5) ---
    @Slot(dict)
    def handle_request_clue_zoom(self, payload: dict):
        """Step 1: Expand selected point tile (if enable_point_zoom is True) or jump directly."""
        self.pending_clue_payload = dict(payload)
        col = payload.get("col_index", 0)
        row = payload.get("row_index", 0)
        self.current_opened_coords = (col, row)

        cell = self.cells.get((col, row))
        if not cell:
            self.show_question(payload)
            return

        pts = payload.get("points", cell.points)
        self.point_zoom_widget.set_config(
            points=pts,
            use_image=cell.use_image,
            pixmap=cell.tile_pixmap,
            solid_color=cell.solid_color,
            fit_mode=cell.fit_mode,
            font_family=cell.font_family,
            font_bold=cell.font_bold,
            text_color=cell.text_gold,
        )

        # Requirement #5: Check if Point Tile Zoom animation is enabled in Settings
        if not self.enable_point_zoom:
            self._on_zoom_animation_finished()
            return

        cell_rect = cell.geometry()
        top_left = cell.mapTo(self, QPoint(0, 0))
        origin_rect = QRect(top_left.x(), top_left.y(), cell_rect.width(), cell_rect.height())
        target_rect = QRect(0, 0, self.width(), self.height())

        self.point_zoom_widget.setGeometry(origin_rect)
        self.point_zoom_widget.show()
        self.point_zoom_widget.raise_()

        if hasattr(self, "zoom_anim") and self.zoom_anim.state() == QPropertyAnimation.Running:
            self.zoom_anim.stop()

        self.zoom_anim = QPropertyAnimation(self.point_zoom_widget, b"geometry", self)
        self.zoom_anim.setDuration(max(100, int(self.zoom_duration_ms)))
        self.zoom_anim.setStartValue(origin_rect)
        self.zoom_anim.setEndValue(target_rect)
        self.zoom_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.zoom_anim.finished.connect(self._on_zoom_animation_finished)
        self.zoom_anim.start()

    def _on_zoom_animation_finished(self):
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
            self.point_zoom_widget.setGeometry(0, 0, self.width(), self.height())
            self.point_zoom_widget.show()
            self.point_zoom_widget.raise_()

    # --- STEP 2: REVEAL CLUE & 3D FLIP (REQ #8) ---
    @Slot()
    def handle_clue_reveal(self):
        if not self.pending_clue_payload:
            return

        is_dd = (
            self.stack.currentIndex() == self.INDEX_DAILY_DOUBLE
            or bool(self.pending_clue_payload.get("is_daily_double"))
        )
        if is_dd and self.enable_dd_flip:
            self._trigger_daily_double_flip_transition()
        else:
            self.show_question(self.pending_clue_payload)

    def _trigger_daily_double_flip_transition(self):
        """Requirement #8: Executes 3D horizontal flip:
        Daily Double Splash -> Solid #000000 Black Void -> Clean Blue Card -> Clue Question text!
        Never renders the question text into the background behind the flip or twice during the flip.
        """
        self.point_zoom_widget.hide()
        w, h = max(400, self.width()), max(300, self.height())

        # Front face: Daily Double splash
        front_pix = QPixmap(w, h)
        front_pix.fill(QColor("#000000"))
        self.dd_splash_widget.resize(w, h)
        self.dd_splash_widget.render(front_pix)

        # Back face: Clean Blue Card background WITHOUT question text (so flip goes DD -> Black -> Card -> Question)
        back_pix = QPixmap(w, h)
        back_pix.fill(QColor("#000000"))
        self.clue_screen_widget.resize(w, h)
        self.clue_screen_widget.render_background_only(back_pix)

        self.card_flip_widget.setGeometry(0, 0, w, h)

        def _on_flip_done():
            self.show_question(self.pending_clue_payload)

        # Called exactly ONCE (fixing the duplicate start_flip bug!)
        self.card_flip_widget.start_flip(
            front_pix,
            back_pix,
            duration=self.flip_duration_ms,
            finished_callback=_on_flip_done,
        )

    handle_clue_zoom = handle_request_clue_zoom

    @Slot(str)
    def show_daily_double_splash(self, splash_path: str):
        if splash_path and os.path.exists(splash_path):
            pix = QPixmap(splash_path)
            self.dd_splash_widget.set_pixmap(pix)
        else:
            def_splash = PROJECT_ROOT / "ui" / "assets" / "images" / "daily_double.png"
            pix = QPixmap(str(def_splash)) if def_splash.exists() else None
            self.dd_splash_widget.set_pixmap(pix)
        self.stack.setCurrentIndex(self.INDEX_DAILY_DOUBLE)

    @Slot(dict)
    def show_question(self, question_data: dict = None):
        # If 3D flip is currently running, let it finish and call show_question on completion
        if hasattr(self, "card_flip_widget") and self.card_flip_widget.isVisible():
            if question_data is not None:
                self.pending_clue_payload = dict(question_data)
            return

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
        self.card_flip_widget.hide()
        self.clue_screen_widget.set_answer_overlay(False)
        self.final_screen_widget.set_answer_overlay(False)
        if self.current_opened_coords:
            cell = self.cells.get(self.current_opened_coords)
            if cell:
                cell.set_state(TVClueCell.STATE_USED)
        # Requirement #4: Check if any column now has all 5 clues used -> revert its header to logo!
        self._update_exhausted_categories()
        self.stack.setCurrentIndex(self.INDEX_BOARD)

    @Slot(bool, str)
    def handle_toggle_tv_answer(self, is_visible: bool, answer_text: str = ""):
        curr = self.stack.currentIndex()
        if curr == self.INDEX_QUESTION:
            self.clue_screen_widget.set_answer_overlay(is_visible, answer_text)
        elif curr == self.INDEX_FINAL:
            self.final_screen_widget.set_answer_overlay(is_visible, answer_text)

    handle_toggle_answer = handle_toggle_tv_answer

    # --- STANDBY ENGINE, INTRO VIDEO MERGE & OUTRO MUSIC (REQ #5 & #7) ---
    @Slot(str)
    def handle_standby_mode(self, mode: str):
        mode = (mode or "").lower()
        if mode == "normal":
            self._set_mosaic_mode(False)
            self.standby_normal_widget.show_static_standby()
            self.stack.setCurrentIndex(self.INDEX_STANDBY_NORMAL)
        elif mode == "mosaic":
            self.standby_normal_widget.stop_video()
            self._set_mosaic_mode(True)
            self.stack.setCurrentIndex(self.INDEX_BOARD)
        else:  # "off"
            self.standby_normal_widget.stop_video()
            self._set_mosaic_mode(False)
            self.stack.setCurrentIndex(self.INDEX_BOARD)
            self._update_exhausted_categories()

    @Slot(dict)
    def handle_standby_intro_video(self, config: dict):
        """Plays Intro Video on TV Display and cross-fades into Static Standby Wallpaper after N seconds."""
        self.audio_manager.stop_all()
        self._set_mosaic_mode(False)
        self.stack.setCurrentIndex(self.INDEX_STANDBY_NORMAL)

        anim_cfg = self.theme.get("animations", {})
        video_path = config.get("video_path") or anim_cfg.get("intro_video_path", "")
        merge_sec = float(config.get("merge_seconds", anim_cfg.get("intro_merge_seconds", 5.0)))
        fade_ms = int(config.get("fade_duration_ms", anim_cfg.get("intro_fade_duration_ms", 1500)))

        self.standby_normal_widget.start_intro_video(video_path, merge_seconds=merge_sec, fade_duration_ms=fade_ms)

    @Slot(str)
    def handle_standby_outro_music(self, music_path: str = ""):
        """Displays Static Standby Wallpaper and plays Outro Music track only (Requirement #7)."""
        self.standby_normal_widget.show_static_standby()
        self._set_mosaic_mode(False)
        self.stack.setCurrentIndex(self.INDEX_STANDBY_NORMAL)

        outro_file = (
            music_path
            or self.theme.get("animations", {}).get("outro_music_path", "")
            or self.theme.get("sounds", {}).get("outro_music", "")
        )
        if outro_file and os.path.isfile(outro_file):
            self.audio_manager.play_file(outro_file)
        else:
            event_bus.play_sound_event.emit("outro_music")

    @Slot()
    def handle_stop_standby_media(self):
        self.standby_normal_widget.show_static_standby()
        self.audio_manager.stop_all()

    def _set_mosaic_mode(self, enabled: bool):
        pix = self.standby_pixmap if enabled else None
        for cell in self.cat_cells:
            cell.set_mosaic(enabled, pix)
        for cell in self.cells.values():
            cell.set_mosaic(enabled, pix)

    @Slot()
    def handle_reset_game_state(self):
        self.close_question()
        self._setup_default_board()
        for cell in self.cat_cells:
            cell.set_revealed(False)

    # --- FINAL JEOPARDY TRANSITIONS ---
    @Slot(int, dict)
    def handle_final_step(self, step: int, data: dict):
        if step == 2:
            # Requirement #7: Use final_category_intro (distinct from round_category_intro and no wager_music)
            event_bus.play_sound_event.emit("final_category_intro")
        if step in (1, 2, 3):
            # Nếu TV đang ở màn hình chờ (Standby Normal) và chưa vào vòng cuối (round 3)
            # thì giữ nguyên màn hình chờ, chỉ nạp dữ liệu bước vào widget
            if self.stack.currentIndex() == self.INDEX_STANDBY_NORMAL and getattr(self, "current_round", 1) != 3:
                self.final_screen_widget.set_step(step, data)
                return
            self.stack.setCurrentIndex(self.INDEX_FINAL)
            self.final_screen_widget.set_step(step, data)

    @Slot()
    def handle_final_crossfade(self):
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
        AssetRenderer.clear_cache()
        self.theme = ThemeConfigManager.load_theme_xml()
        self.apply_theme_config(self.theme)

    @Slot(dict)
    def apply_theme_config(self, theme_data: dict):
        AssetRenderer.clear_cache()
        self.theme = theme_data

        # 0. Performance & OpenGL Profile
        prof = theme_data.get("performance_profile", "ultra")
        self.apply_performance_profile(prof)

        # 1. Bezel
        bw = int(theme_data.get("bezel_width", 8))
        bc = str(theme_data.get("bezel_color", "#000000"))
        self.bezel_width = bw
        self.bezel_color = QColor(bc)

        self.board_container.setStyleSheet(f"background-color: {bc};")
        self.board_grid.setContentsMargins(bw, bw, bw, bw)
        self.board_grid.setSpacing(bw)

        # 2. Category Headers & Shared Typography
        ch_data = theme_data.get("category_headers", {})
        unrev_p = ch_data.get("unrevealed_image", "")
        rev_p = ch_data.get("revealed_image", "")
        fit_m = ch_data.get("fit_mode", "stretch")
        auto_crop_logo = bool(ch_data.get("auto_crop_logo", True))
        f_info = ch_data.get("font", {"family": "ITC Korinna", "size": 28, "bold": True, "color": "#FFFFFF", "mode": "dynamic"})

        cs_data = theme_data.get("clue_screen", {})
        cs_font = cs_data.get("font", {})
        shared_family = cs_font.get("family") or f_info.get("family", "ITC Korinna")
        shared_bold = bool(cs_font.get("bold", f_info.get("bold", True)))
        shared_color = cs_font.get("color") or f_info.get("color", "#FFFFFF")
        shared_mode = cs_font.get("mode") or f_info.get("mode", "dynamic")
        header_pt_size = int(cs_font.get("header_size", f_info.get("size", 28)))
        clue_pt_size = int(cs_font.get("size", 48))
        ans_pt_size = int(cs_font.get("answer_size", 30))

        for cell in self.cat_cells:
            cell.set_images(unrev_p, rev_p, fit_m, auto_crop_logo=auto_crop_logo)
            cell.set_font_config(shared_family, header_pt_size, shared_bold, shared_color, mode=shared_mode)

        # 3. Point Grid
        pg_data = theme_data.get("point_grid", {})
        use_img = pg_data.get("use_image", True)
        tile_p = pg_data.get("tile_image", "")
        sol_col = pg_data.get("solid_color", "#060CE9")
        pg_fit = pg_data.get("fit_mode", "zoom")
        pg_font = pg_data.get("font", {"family": "Impact", "size": 48, "bold": True, "color": "#FFA500", "mode": "dynamic"})

        for cell in self.cells.values():
            cell.set_visual_config(use_img, tile_p, sol_col, pg_fit)
            cell.set_font_config(
                pg_font.get("family", "Impact"),
                int(pg_font.get("size", 48)),
                bool(pg_font.get("bold", True)),
                pg_font.get("color", "#FFA500"),
                mode=pg_font.get("mode", "dynamic"),
            )

        # 4. Clue Screen Card & Shadow
        std_card = cs_data.get("standard_card", {})
        std_img = std_card.get("image_path", "")
        std_col = std_card.get("color", "#060CE9")
        std_use = std_card.get("use_image", True)
        sh_data = cs_data.get("shadow", {})
        sh_dx = int(sh_data.get("dx", 3))
        sh_dy = int(sh_data.get("dy", 3))
        sh_blur = int(sh_data.get("blur", 2))

        self.clue_screen_widget.set_card_visuals(std_use, std_img, std_col)
        self.clue_screen_widget.set_font_config(
            shared_family,
            clue_pt_size,
            bold=shared_bold,
            color=shared_color,
            mode=shared_mode,
            answer_size=ans_pt_size,
            shadow_dx=sh_dx,
            shadow_dy=sh_dy,
            shadow_blur=sh_blur,
        )

        # 5. Final Jeopardy Visuals & Synchronized Typography (Requirement #6)
        fin_card = cs_data.get("final_card", {})
        fin_img = fin_card.get("image_path", "")
        fin_col = fin_card.get("color", "#8B0000")
        vfx = theme_data.get("visual_fx", {})
        splash_p = vfx.get("final_logo_splash", "")
        self.final_screen_widget.set_visuals(splash_p, std_img, std_col, fin_img, fin_col)
        self.final_screen_widget.set_font_config(
            shared_family,
            clue_pt_size,
            bold=shared_bold,
            color=shared_color,
            mode=shared_mode,
            answer_size=ans_pt_size,
            header_size=header_pt_size,
            shadow_dx=sh_dx,
            shadow_dy=sh_dy,
            shadow_blur=sh_blur,
        )

        # 6. Category Reveal Logo & Style
        logo_cand = unrev_p if unrev_p and os.path.exists(unrev_p) else theme_data.get("logo_path", "")
        self.cat_reveal_widget.set_logo_path(logo_cand, auto_crop=auto_crop_logo)
        self.cat_reveal_widget.set_card_style(rev_p, std_col)
        self.cat_reveal_widget.set_font_config(shared_family, header_pt_size, shared_bold, shared_color, mode=shared_mode)

        # 7. Standby Screen Wallpaper (Static & Mosaic 36)
        sb_img = theme_data.get("standby_screen", {}).get("image_path", "")
        if sb_img and os.path.exists(sb_img):
            self.standby_pixmap = QPixmap(sb_img)
        else:
            def_sb = PROJECT_ROOT / "ui" / "assets" / "images" / "standby_static.png"
            self.standby_pixmap = QPixmap(str(def_sb)) if def_sb.exists() else None
        self.standby_normal_widget.set_pixmap(self.standby_pixmap)

        # 8. Animations Config
        anim_cfg = theme_data.get("animations", {})
        self.enable_point_zoom = bool(anim_cfg.get("enable_point_zoom", True))
        self.zoom_duration_ms = int(anim_cfg.get("zoom_duration_ms", 400))
        self.enable_dd_flip = bool(anim_cfg.get("enable_dd_flip", True))
        self.flip_duration_ms = int(anim_cfg.get("flip_duration_ms", 900))

        # 9. Audio Manager Sync
        sounds_dict = theme_data.get("sounds", {})
        if isinstance(sounds_dict, dict):
            self.audio_manager.load_from_dict(sounds_dict)

        self.update()

    # -------------------------------------------------------------------------
    # PERFORMANCE PROFILES & OPENGL GPU PIPELINE (REQ #9)
    # -------------------------------------------------------------------------

    @Slot(str)
    def apply_performance_profile(self, profile_mode: str):
        """Integrates OpenGL hardware context, VSync frame pacing, and smooth texture transforms."""
        self.performance_profile = (profile_mode or "ultra").lower()
        if self.performance_profile == "ultra":
            if HAS_QOPENGL:
                try:
                    if not hasattr(self, "_gl_surface") or self._gl_surface is None:
                        self._gl_surface = OpenGLHardwareSurface(self)
                        self._gl_surface.lower()
                        self._gl_surface.setGeometry(0, 0, self.width(), self.height())
                        self._gl_surface.show()
                except Exception as e:
                    print(f"[TVDisplay] OpenGL surface notice: {e}")
            self.animation_fps = 120
            self.smooth_transform = True
            self.fill_timer.setInterval(45)
        elif self.performance_profile == "smooth":
            if hasattr(self, "_gl_surface") and self._gl_surface is not None:
                self._gl_surface.hide()
            self.animation_fps = 60
            self.smooth_transform = True
            self.fill_timer.setInterval(55)
        else:  # "basic"
            if hasattr(self, "_gl_surface") and self._gl_surface is not None:
                self._gl_surface.hide()
            self.animation_fps = 30
            self.smooth_transform = False
            self.fill_timer.setInterval(75)

        # Propagate transform quality to all rendering widgets
        for cell in self.cat_cells:
            cell.smooth_transform = self.smooth_transform
        for cell in self.cells.values():
            cell.smooth_transform = self.smooth_transform
        if hasattr(self, "point_zoom_widget"):
            self.point_zoom_widget.smooth_transform = self.smooth_transform
        if hasattr(self, "card_flip_widget"):
            self.card_flip_widget.smooth_transform = self.smooth_transform
        if hasattr(self, "clue_screen_widget"):
            self.clue_screen_widget.smooth_transform = self.smooth_transform
        if hasattr(self, "standby_normal_widget"):
            self.standby_normal_widget.smooth_transform = self.smooth_transform
        if hasattr(self, "cat_reveal_widget"):
            self.cat_reveal_widget.card_a.inner_box.smooth_transform = self.smooth_transform
            self.cat_reveal_widget.card_b.inner_box.smooth_transform = self.smooth_transform
        self.update()

    @Slot(list)
    def handle_sync_categories(self, categories: list):
        self.category_names = list(categories)
        while len(self.category_names) < 6:
            self.category_names.append(f"CATEGORY {len(self.category_names)+1}")
        for i in range(6):
            if i < len(self.cat_cells):
                self.cat_cells[i].set_title(self.category_names[i])
        self._update_exhausted_categories()
        if hasattr(self, "cat_reveal_widget"):
            self.cat_reveal_widget.set_categories(self.category_names)

    @Slot(list)
    def handle_sync_board_state(self, board_items: list):
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
        # Requirement #4: Update category header state if any column is fully exhausted
        self._update_exhausted_categories()

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
        event_bus.trigger_standby_intro_video.connect(self.handle_standby_intro_video)
        event_bus.trigger_standby_outro_music.connect(self.handle_standby_outro_music)
        event_bus.stop_standby_media.connect(self.handle_stop_standby_media)
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


def main():
    app = QApplication(sys.argv)
    window = TVDisplayWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
