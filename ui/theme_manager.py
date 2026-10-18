"""Open-J: Theme Package Engine, Asset Renderer & XML Manager.
Handles full-fidelity asset rendering with auto-cropped border removal,
GPU/RAM pixmap caching, dynamic/custom font modes, animation settings,
individual sound bindings, and XML configuration.
"""

import os
import zipfile
import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QPixmap, QImage, QBrush, QColor, QFont


# Project Root Anchor
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ASSETS_DIR = PROJECT_ROOT / "ui" / "assets"
DEFAULT_XML_PATH = DEFAULT_ASSETS_DIR / "theme.xml"


# =============================================================================
# 1. ASSET RENDERER (AUTO-CROP BORDER + CACHED SCALING: STRETCH / ZOOM / TILE)
# =============================================================================

class AssetRenderer:
    """High-performance graphic rendering engine for TV Studio Broadcast Display.
    Includes automatic uniform border trimming (fixing padded logos like image2.png)
    and an LRU scaled-pixmap cache to eliminate per-frame CPU scaling bottlenecks.
    """

    _CROP_CACHE: Dict[int, QPixmap] = {}
    _SCALED_CACHE: Dict[Tuple[int, int, int, str, bool], QPixmap] = {}
    _MAX_CACHE_SIZE = 128

    @classmethod
    def clear_cache(cls):
        cls._CROP_CACHE.clear()
        cls._SCALED_CACHE.clear()

    @classmethod
    def auto_crop_border(cls, pixmap: Optional[QPixmap], tolerance: int = 26) -> Optional[QPixmap]:
        """Automatically detects and removes uniform solid-color or transparent padding borders
        around an image (e.g., removing the dark blue margin around the Jeopardy! globe in image2.png)
        so the logo fills 100% of the yellow category cell edge-to-edge.
        """
        if pixmap is None or pixmap.isNull():
            return pixmap

        key = pixmap.cacheKey()
        if key in cls._CROP_CACHE:
            return cls._CROP_CACHE[key]

        try:
            img = pixmap.toImage().convertToFormat(QImage.Format_RGBA8888)
            w, h = img.width(), img.height()
            if w < 16 or h < 16:
                cls._CROP_CACHE[key] = pixmap
                return pixmap

            # Use PIL/numpy if available for sub-millisecond border detection, else QImage scan
            try:
                import numpy as np
                ptr = img.constBits()
                arr = np.frombuffer(ptr, dtype=np.uint8).reshape((h, w, 4))

                # Reference corner colors (top-left, top-right, bottom-left, bottom-right)
                corners = [arr[0, 0], arr[0, w - 1], arr[h - 1, 0], arr[h - 1, w - 1]]
                ref = corners[0].astype(np.int16)

                # A pixel is considered border if it is nearly transparent OR close to corner color
                alpha_mask = arr[:, :, 3] > 20
                diff = np.max(np.abs(arr[:, :, :3].astype(np.int16) - ref[:3]), axis=2)
                content_mask = alpha_mask & (diff > tolerance)

                # Require at least a small fraction of pixels in a row/col to differ from border
                row_has_content = np.mean(content_mask, axis=1) > 0.04
                col_has_content = np.mean(content_mask, axis=0) > 0.04

                if np.any(row_has_content) and np.any(col_has_content):
                    y_indices = np.where(row_has_content)[0]
                    x_indices = np.where(col_has_content)[0]
                    top, bottom = int(y_indices[0]), int(y_indices[-1])
                    left, right = int(x_indices[0]), int(x_indices[-1])

                    crop_w = right - left + 1
                    crop_h = bottom - top + 1
                    # Only apply crop if inner region is at least 40% of original dimensions
                    if crop_w >= int(w * 0.40) and crop_h >= int(h * 0.40) and (crop_w < w - 4 or crop_h < h - 4):
                        cropped = pixmap.copy(QRect(left, top, crop_w, crop_h))
                        cls._CROP_CACHE[key] = cropped
                        return cropped
            except Exception:
                # Pure Qt fallback scan
                c0 = img.pixelColor(0, 0)
                r0, g0, b0, a0 = c0.red(), c0.green(), c0.blue(), c0.alpha()

                def is_border_px(x_idx: int, y_idx: int) -> bool:
                    c = img.pixelColor(x_idx, y_idx)
                    if c.alpha() <= 20:
                        return True
                    return max(abs(c.red() - r0), abs(c.green() - g0), abs(c.blue() - b0)) <= tolerance

                top = 0
                while top < h // 3 and all(is_border_px(x, top) for x in range(0, w, max(1, w // 32))):
                    top += 1
                bottom = h - 1
                while bottom > (h * 2) // 3 and all(is_border_px(x, bottom) for x in range(0, w, max(1, w // 32))):
                    bottom -= 1
                left = 0
                while left < w // 3 and all(is_border_px(left, y) for y in range(0, h, max(1, h // 32))):
                    left += 1
                right = w - 1
                while right > (w * 2) // 3 and all(is_border_px(right, y) for y in range(0, h, max(1, h // 32))):
                    right -= 1

                crop_w = right - left + 1
                crop_h = bottom - top + 1
                if crop_w >= int(w * 0.40) and crop_h >= int(h * 0.40) and (crop_w < w - 4 or crop_h < h - 4):
                    cropped = pixmap.copy(QRect(left, top, crop_w, crop_h))
                    cls._CROP_CACHE[key] = cropped
                    return cropped
        except Exception as e:
            print(f"[AssetRenderer] auto_crop_border notice: {e}")

        cls._CROP_CACHE[key] = pixmap
        return pixmap

    @classmethod
    def get_scaled_pixmap(
        cls,
        pixmap: QPixmap,
        width: int,
        height: int,
        fit_mode: str = "zoom",
        smooth: bool = True,
        auto_crop: bool = False
    ) -> QPixmap:
        """Returns a cached scaled QPixmap so animations never stall on CPU scaling."""
        if pixmap is None or pixmap.isNull() or width <= 0 or height <= 0:
            return pixmap

        src = cls.auto_crop_border(pixmap) if auto_crop else pixmap
        cache_key = (src.cacheKey(), width, height, fit_mode, smooth)
        cached = cls._SCALED_CACHE.get(cache_key)
        if cached is not None:
            return cached

        if len(cls._SCALED_CACHE) >= cls._MAX_CACHE_SIZE:
            # Evict oldest half
            keys = list(cls._SCALED_CACHE.keys())[: cls._MAX_CACHE_SIZE // 2]
            for k in keys:
                cls._SCALED_CACHE.pop(k, None)

        transform = Qt.SmoothTransformation if smooth else Qt.FastTransformation
        if fit_mode in ("stretch", "fill"):
            scaled = src.scaled(width, height, Qt.IgnoreAspectRatio, transform)
        elif fit_mode == "contain":
            scaled = src.scaled(width, height, Qt.KeepAspectRatio, transform)
        else:
            scaled = src.scaled(width, height, Qt.KeepAspectRatioByExpanding, transform)

        cls._SCALED_CACHE[cache_key] = scaled
        return scaled

    @classmethod
    def render_background(
        cls,
        painter: QPainter,
        target_rect: QRect,
        pixmap: Optional[QPixmap],
        fit_mode: str = "zoom",
        smooth: bool = True,
        auto_crop: bool = False
    ):
        """
        fit_mode:
          - 'stretch' / 'fill': Fill 100% of target_rect edge-to-edge (Qt.IgnoreAspectRatio)
          - 'zoom': Scale preserving aspect ratio and crop overflow margins (KeepAspectRatioByExpanding)
          - 'tile': Repeat texture pattern (Texture Pattern Tiling)
        """
        if pixmap is None or pixmap.isNull() or target_rect.width() <= 0 or target_rect.height() <= 0:
            return

        src = cls.auto_crop_border(pixmap) if auto_crop else pixmap

        if fit_mode == "tile":
            brush = QBrush(src)
            painter.fillRect(target_rect, brush)
        elif fit_mode in ("stretch", "fill"):
            scaled = cls.get_scaled_pixmap(src, target_rect.width(), target_rect.height(), "stretch", smooth=smooth)
            painter.drawPixmap(target_rect.topLeft(), scaled)
        else:
            scaled = cls.get_scaled_pixmap(src, target_rect.width(), target_rect.height(), "zoom", smooth=smooth)
            x = target_rect.x() + (target_rect.width() - scaled.width()) // 2
            y = target_rect.y() + (target_rect.height() - scaled.height()) // 2
            painter.save()
            painter.setClipRect(target_rect)
            painter.drawPixmap(x, y, scaled)
            painter.restore()


# =============================================================================
# 2. THEME PACKAGE ENGINE (ZIP EXPORTER / IMPORTER)
# =============================================================================

class ThemePackageEngine:
    """Manages compression/extraction of theme packages into .zip or .openj-theme packages."""

    @staticmethod
    def export_theme_to_zip(xml_path: str, assets_dir: str, output_zip_path: str):
        """Packs the XML file and all images/sounds into a single .zip archive."""
        xml_p = Path(xml_path).resolve()
        assets_p = Path(assets_dir).resolve()
        out_p = Path(output_zip_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(str(out_p), 'w', zipfile.ZIP_DEFLATED) as zip_file:
            if xml_p.exists():
                zip_file.write(str(xml_p), arcname="theme.xml")

            if assets_p.exists():
                for item in assets_p.rglob("*"):
                    if item.is_file() and item.name != "theme.xml":
                        rel_path = item.relative_to(assets_p)
                        arcname = f"assets/{rel_path.as_posix()}"
                        zip_file.write(str(item), arcname=arcname)
        return str(out_p)

    @staticmethod
    def import_theme_from_zip(zip_path: str, extract_to: str) -> Path:
        """Extracts a theme package into target directory and returns the extracted XML path."""
        z_p = Path(zip_path).resolve()
        target_dir = Path(extract_to).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(str(z_p), 'r') as zip_file:
            zip_file.extractall(str(target_dir))

        extracted_xml = target_dir / "theme.xml"
        if not extracted_xml.exists():
            found = list(target_dir.rglob("theme.xml"))
            if found:
                extracted_xml = found[0]

        AssetRenderer.clear_cache()
        return extracted_xml


# =============================================================================
# 3. THEME XML CONFIGURATION MANAGER
# =============================================================================

class ThemeConfigManager:
    """Broadcast-standard theme XML configuration reader, writer, and synchronizer."""

    @staticmethod
    def resolve_path(raw_path: str, base_dir: Optional[Path] = None) -> str:
        """Converts relative asset paths into absolute paths safely."""
        if not raw_path:
            return ""
        p = Path(raw_path)
        if p.is_absolute() and p.exists():
            return str(p)

        search_bases = [
            base_dir,
            DEFAULT_ASSETS_DIR,
            PROJECT_ROOT / "ui",
            PROJECT_ROOT,
        ]
        for base in search_bases:
            if base:
                cand = (base / raw_path).resolve()
                if cand.exists():
                    return str(cand)
                if raw_path.startswith("assets/"):
                    cand2 = (base.parent / raw_path).resolve()
                    if cand2.exists():
                        return str(cand2)
                    cand3 = (DEFAULT_ASSETS_DIR / raw_path.replace("assets/", "")).resolve()
                    if cand3.exists():
                        return str(cand3)
                cand_img = DEFAULT_ASSETS_DIR / "images" / p.name
                if cand_img.exists():
                    return str(cand_img)
                cand_img_alt = DEFAULT_ASSETS_DIR / "image" / p.name
                if cand_img_alt.exists():
                    return str(cand_img_alt)
                cand_snd = DEFAULT_ASSETS_DIR / "sounds" / p.name
                if cand_snd.exists():
                    return str(cand_snd)

        return raw_path

    @classmethod
    def get_default_theme(cls) -> Dict[str, Any]:
        """Generates default theme configuration matching reference broadcast standard."""
        return {
            "name": "Custom_Broadcast_Package",
            "performance_profile": "ultra",
            "bezel_color": "#000000",
            "bezel_width": 8,
            "standby_screen": {
                "image_path": cls.resolve_path("images/standby_static.png"),
            },
            "category_headers": {
                "fit_mode": "stretch",
                "auto_crop_logo": True,
                "unrevealed_image": cls.resolve_path("images/header_logo.png"),
                "revealed_image": cls.resolve_path("images/header_revealed_bg.png"),
                "font": {
                    "family": "ITC Korinna",
                    "size": 28,
                    "bold": True,
                    "color": "#FFFFFF",
                    "mode": "dynamic",
                },
            },
            "point_grid": {
                "fit_mode": "zoom",
                "use_image": True,
                "solid_color": "#060CE9",
                "tile_image": cls.resolve_path("images/tile_texture.png"),
                "font": {
                    "family": "Impact",
                    "size": 48,
                    "bold": True,
                    "color": "#FFA500",
                    "mode": "dynamic",
                },
            },
            "clue_screen": {
                "fit_mode": "zoom",
                "outer_bg_color": "#000000",
                "standard_card": {
                    "color": "#060CE9",
                    "image_path": cls.resolve_path("images/clue_blue.png"),
                    "use_image": True,
                },
                "final_card": {
                    "color": "#8B0000",
                    "image_path": cls.resolve_path("images/clue_red.png"),
                    "use_image": True,
                },
                "font": {
                    "family": "ITC Korinna",
                    "size": 48,
                    "answer_size": 30,
                    "header_size": 28,
                    "bold": True,
                    "color": "#FFFFFF",
                    "mode": "dynamic",
                },
                "shadow": {"blur": 2, "dx": 3, "dy": 3, "color": "#000000"},
            },
            "visual_fx": {
                "daily_double_splash": cls.resolve_path("images/daily_double.png"),
                "final_logo_splash": cls.resolve_path("images/final_jeopardy_logo.png"),
            },
            "animations": {
                "enable_point_zoom": True,
                "zoom_duration_ms": 400,
                "enable_dd_flip": True,
                "flip_duration_ms": 900,
                "intro_video_path": "",
                "intro_merge_seconds": 5.0,
                "intro_fade_duration_ms": 1500,
                "outro_music_path": "",
            },
            "sounds": {
                "board_fill": cls.resolve_path("sounds/fill.mp3"),
                "round_category_intro": cls.resolve_path("sounds/category_intro.wav"),
                "daily_double": cls.resolve_path("sounds/daily_double.wav"),
                "timeout": cls.resolve_path("sounds/timeout.wav"),
                "correct": cls.resolve_path("sounds/correct.wav"),
                "wrong": cls.resolve_path("sounds/wrong.wav"),
                "final_category_intro": cls.resolve_path("sounds/category_intro.wav"),
                "think_30s": cls.resolve_path("sounds/think_30s.wav"),
                "outro_music": "",
            },
        }

    @classmethod
    def load_theme_xml(cls, xml_path: Optional[str] = None) -> Dict[str, Any]:
        """Reads and parses theme.xml, returning a complete configuration dictionary."""
        if xml_path is None or not Path(xml_path).exists():
            xml_path = str(DEFAULT_XML_PATH)

        theme = cls.get_default_theme()
        p = Path(xml_path)
        if not p.exists():
            return theme

        base_dir = p.parent
        try:
            tree = ET.parse(str(p))
            root = tree.getroot()
            theme["name"] = root.attrib.get("name", theme["name"])
            theme["performance_profile"] = root.attrib.get("performance_profile", theme.get("performance_profile", "ultra"))

            # Bezel
            bezel_node = root.find("Bezel")
            if bezel_node is not None:
                theme["bezel_color"] = bezel_node.attrib.get("color", theme["bezel_color"])
                theme["bezel_width"] = int(bezel_node.attrib.get("width", theme["bezel_width"]))

            # StandbyMosaicZone & StandbyScreen
            smz_node = root.find("StandbyMosaicZone")
            if smz_node is not None:
                mi_node = smz_node.find("MosaicImage")
                if mi_node is not None:
                    p_val = mi_node.attrib.get("path", "")
                    if p_val:
                        theme["standby_screen"]["image_path"] = cls.resolve_path(p_val, base_dir)
            sb_node = root.find("StandbyScreen")
            if sb_node is not None:
                p_val = sb_node.attrib.get("image_path", "")
                if p_val:
                    theme["standby_screen"]["image_path"] = cls.resolve_path(p_val, base_dir)

            # HeaderZone
            hz_node = root.find("HeaderZone")
            if hz_node is not None:
                unrev = hz_node.find("UnrevealedLogo")
                if unrev is not None:
                    p_val = unrev.attrib.get("path") or unrev.attrib.get("image_path", "")
                    if p_val:
                        theme["category_headers"]["unrevealed_image"] = cls.resolve_path(p_val, base_dir)
                rev = hz_node.find("RevealedBackground")
                if rev is not None:
                    p_val = rev.attrib.get("path") or rev.attrib.get("image_path", "")
                    if p_val:
                        theme["category_headers"]["revealed_image"] = cls.resolve_path(p_val, base_dir)
                f_node = hz_node.find("Font")
                if f_node is not None:
                    theme["category_headers"]["font"]["family"] = f_node.attrib.get("family", "ITC Korinna")
                    theme["category_headers"]["font"]["size"] = int(f_node.attrib.get("size", 28))
                    theme["category_headers"]["font"]["bold"] = f_node.attrib.get("bold", "true").lower() == "true"
                    theme["category_headers"]["font"]["color"] = f_node.attrib.get("color", "#FFFFFF")
                    theme["category_headers"]["font"]["mode"] = f_node.attrib.get("mode", "dynamic")

            # CategoryHeaders
            ch_node = root.find("CategoryHeaders")
            if ch_node is not None:
                theme["category_headers"]["fit_mode"] = ch_node.attrib.get("fit_mode", "stretch")
                theme["category_headers"]["auto_crop_logo"] = ch_node.attrib.get("auto_crop_logo", "true").lower() == "true"
                unrev = ch_node.find("StateUnrevealed")
                if unrev is not None:
                    p_val = unrev.attrib.get("image_path") or unrev.attrib.get("path", "")
                    if p_val:
                        theme["category_headers"]["unrevealed_image"] = cls.resolve_path(p_val, base_dir)
                rev = ch_node.find("StateRevealed")
                if rev is not None:
                    p_val = rev.attrib.get("image_path") or rev.attrib.get("path", "")
                    if p_val:
                        theme["category_headers"]["revealed_image"] = cls.resolve_path(p_val, base_dir)
                f_node = ch_node.find("Font")
                if f_node is not None:
                    theme["category_headers"]["font"]["family"] = f_node.attrib.get("family", "ITC Korinna")
                    theme["category_headers"]["font"]["size"] = int(f_node.attrib.get("size", 28))
                    theme["category_headers"]["font"]["bold"] = f_node.attrib.get("bold", "true").lower() == "true"
                    theme["category_headers"]["font"]["color"] = f_node.attrib.get("color", "#FFFFFF")
                    theme["category_headers"]["font"]["mode"] = f_node.attrib.get("mode", "dynamic")

            # PointGrid
            pg_node = root.find("PointGrid")
            if pg_node is not None:
                theme["point_grid"]["fit_mode"] = pg_node.attrib.get("fit_mode", "zoom")
                m_node = pg_node.find("Mode")
                if m_node is not None:
                    theme["point_grid"]["use_image"] = m_node.attrib.get("use_image", "true").lower() == "true"
                col_node = pg_node.find("SolidColor")
                if col_node is not None:
                    theme["point_grid"]["solid_color"] = col_node.attrib.get("value", "#060CE9")
                tile_node = pg_node.find("TileImage")
                if tile_node is not None:
                    theme["point_grid"]["tile_image"] = cls.resolve_path(tile_node.attrib.get("path", ""), base_dir)
                pf_node = pg_node.find("PointFont")
                if pf_node is not None:
                    theme["point_grid"]["font"]["family"] = pf_node.attrib.get("family", "Impact")
                    theme["point_grid"]["font"]["size"] = int(pf_node.attrib.get("size", 48))
                    theme["point_grid"]["font"]["bold"] = pf_node.attrib.get("bold", "true").lower() == "true"
                    theme["point_grid"]["font"]["color"] = pf_node.attrib.get("color", "#FFA500")
                    theme["point_grid"]["font"]["mode"] = pf_node.attrib.get("mode", "dynamic")

            # ClueScreen
            cs_node = root.find("ClueScreen")
            if cs_node is not None:
                theme["clue_screen"]["fit_mode"] = cs_node.attrib.get("fit_mode", "zoom")
                obg = cs_node.find("OuterBackground")
                if obg is not None:
                    theme["clue_screen"]["outer_bg_color"] = obg.attrib.get("color", "#000000")

                std_card = cs_node.find("StandardCard")
                if std_card is not None:
                    theme["clue_screen"]["standard_card"]["color"] = std_card.attrib.get("color", "#060CE9")
                    theme["clue_screen"]["standard_card"]["image_path"] = cls.resolve_path(std_card.attrib.get("image_path", ""), base_dir)
                    theme["clue_screen"]["standard_card"]["use_image"] = std_card.attrib.get("use_image", "true").lower() == "true"

                fin_card = cs_node.find("FinalCard")
                if fin_card is not None:
                    theme["clue_screen"]["final_card"]["color"] = fin_card.attrib.get("color", "#8B0000")
                    theme["clue_screen"]["final_card"]["image_path"] = cls.resolve_path(fin_card.attrib.get("image_path", ""), base_dir)
                    theme["clue_screen"]["final_card"]["use_image"] = fin_card.attrib.get("use_image", "true").lower() == "true"

                cf_node = cs_node.find("Font")
                if cf_node is not None:
                    theme["clue_screen"]["font"]["family"] = cf_node.attrib.get("family", "ITC Korinna")
                    theme["clue_screen"]["font"]["size"] = int(cf_node.attrib.get("size", 48))
                    theme["clue_screen"]["font"]["answer_size"] = int(cf_node.attrib.get("answer_size", 30))
                    theme["clue_screen"]["font"]["header_size"] = int(cf_node.attrib.get("header_size", theme["category_headers"]["font"]["size"]))
                    theme["clue_screen"]["font"]["bold"] = cf_node.attrib.get("bold", "true").lower() == "true"
                    theme["clue_screen"]["font"]["color"] = cf_node.attrib.get("color", "#FFFFFF")
                    theme["clue_screen"]["font"]["mode"] = cf_node.attrib.get("mode", "dynamic")

                sh_node = cs_node.find("Shadow")
                if sh_node is not None:
                    theme["clue_screen"]["shadow"]["blur"] = int(sh_node.attrib.get("blur", 2))
                    theme["clue_screen"]["shadow"]["dx"] = int(sh_node.attrib.get("dx", 3))
                    theme["clue_screen"]["shadow"]["dy"] = int(sh_node.attrib.get("dy", 3))
                    theme["clue_screen"]["shadow"]["color"] = sh_node.attrib.get("color", "#000000")

            # VisualFX
            vfx_node = root.find("VisualFX")
            if vfx_node is not None:
                dd = vfx_node.find("DailyDoubleSplash")
                if dd is not None:
                    theme["visual_fx"]["daily_double_splash"] = cls.resolve_path(dd.attrib.get("path", ""), base_dir)
                fl = vfx_node.find("FinalLogoSplash")
                if fl is not None:
                    theme["visual_fx"]["final_logo_splash"] = cls.resolve_path(fl.attrib.get("path", ""), base_dir)

            # Animations
            anim_node = root.find("Animations")
            if anim_node is not None:
                anim_cfg = theme["animations"]
                anim_cfg["enable_point_zoom"] = anim_node.attrib.get("enable_point_zoom", "true").lower() == "true"
                anim_cfg["zoom_duration_ms"] = int(anim_node.attrib.get("zoom_duration_ms", 400))
                anim_cfg["enable_dd_flip"] = anim_node.attrib.get("enable_dd_flip", "true").lower() == "true"
                anim_cfg["flip_duration_ms"] = int(anim_node.attrib.get("flip_duration_ms", 900))
                iv_path = anim_node.attrib.get("intro_video_path", "").strip()
                anim_cfg["intro_video_path"] = cls.resolve_path(iv_path, base_dir) if iv_path else ""
                anim_cfg["intro_merge_seconds"] = float(anim_node.attrib.get("intro_merge_seconds", 5.0))
                anim_cfg["intro_fade_duration_ms"] = int(anim_node.attrib.get("intro_fade_duration_ms", 1500))
                om_path = anim_node.attrib.get("outro_music_path", "").strip()
                anim_cfg["outro_music_path"] = cls.resolve_path(om_path, base_dir) if om_path else ""

            # Sounds (individual event bindings only, no folder override, no wager_music)
            snd_node = root.find("Sounds")
            if snd_node is not None:
                # If XML explicitly has <Sounds>, load exact per-item bindings
                raw_sounds = {}
                for s in snd_node.findall("Sound"):
                    k = s.attrib.get("key", "").strip()
                    path_val = s.attrib.get("path", "").strip()
                    if not k or k == "wager_music":
                        continue
                    raw_sounds[k] = cls.resolve_path(path_val, base_dir) if path_val else ""

                # Normalize legacy keys cleanly without cross-contaminating unrelated events
                if "board_fill" in raw_sounds:
                    theme["sounds"]["board_fill"] = raw_sounds["board_fill"]
                elif "fill" in raw_sounds:
                    theme["sounds"]["board_fill"] = raw_sounds["fill"]

                if "round_category_intro" in raw_sounds:
                    theme["sounds"]["round_category_intro"] = raw_sounds["round_category_intro"]

                if "daily_double" in raw_sounds:
                    theme["sounds"]["daily_double"] = raw_sounds["daily_double"]

                if "timeout" in raw_sounds:
                    theme["sounds"]["timeout"] = raw_sounds["timeout"]
                elif "time_out" in raw_sounds:
                    theme["sounds"]["timeout"] = raw_sounds["time_out"]

                if "correct" in raw_sounds:
                    theme["sounds"]["correct"] = raw_sounds["correct"]

                if "wrong" in raw_sounds:
                    theme["sounds"]["wrong"] = raw_sounds["wrong"]

                if "final_category_intro" in raw_sounds:
                    theme["sounds"]["final_category_intro"] = raw_sounds["final_category_intro"]
                elif "category_intro" in raw_sounds:
                    theme["sounds"]["final_category_intro"] = raw_sounds["category_intro"]

                if "think_30s" in raw_sounds:
                    theme["sounds"]["think_30s"] = raw_sounds["think_30s"]
                elif "think_music" in raw_sounds:
                    theme["sounds"]["think_30s"] = raw_sounds["think_music"]

                if "outro_music" in raw_sounds:
                    theme["sounds"]["outro_music"] = raw_sounds["outro_music"]
                    if not theme["animations"].get("outro_music_path"):
                        theme["animations"]["outro_music_path"] = raw_sounds["outro_music"]

            if theme["animations"].get("outro_music_path") and not theme["sounds"].get("outro_music"):
                theme["sounds"]["outro_music"] = theme["animations"]["outro_music_path"]

            # Backward-compatible aliases
            theme["header_zone"] = {
                "unrevealed_logo": theme["category_headers"].get("unrevealed_image", ""),
                "revealed_background": theme["category_headers"].get("revealed_image", ""),
                "font": dict(theme["category_headers"].get("font", {})),
            }
            theme["standby_mosaic_zone"] = {
                "mosaic_image": theme["standby_screen"].get("image_path", "")
            }

        except Exception as e:
            print(f"[ThemeConfigManager] Warning reading XML: {e}")

        return theme

    @classmethod
    def save_theme_xml(cls, theme: Dict[str, Any], xml_path: Optional[str] = None):
        """Saves theme dictionary configuration into broadcast-standard theme.xml."""
        if xml_path is None:
            xml_path = str(DEFAULT_XML_PATH)

        out_p = Path(xml_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        root = ET.Element("JeopardyTheme", attrib={
            "name": str(theme.get("name", "Custom_Broadcast_Package")),
            "performance_profile": str(theme.get("performance_profile", "ultra")),
        })

        # Bezel
        ET.SubElement(root, "Bezel", attrib={
            "color": str(theme.get("bezel_color", "#000000")),
            "width": str(theme.get("bezel_width", 8)),
        })

        # StandbyScreen & StandbyMosaicZone
        sb_data = theme.get("standby_screen", {})
        sb_rel_path = cls._to_relative_assets_path(sb_data.get("image_path", ""))
        ET.SubElement(root, "StandbyScreen", attrib={"image_path": sb_rel_path})
        smz_node = ET.SubElement(root, "StandbyMosaicZone")
        ET.SubElement(smz_node, "MosaicImage", attrib={"path": sb_rel_path})

        # HeaderZone & CategoryHeaders
        ch_data = theme.get("category_headers", {})
        unrev_path = cls._to_relative_assets_path(ch_data.get("unrevealed_image", ""))
        rev_path = cls._to_relative_assets_path(ch_data.get("revealed_image", ""))
        ch_font = ch_data.get("font", {})

        hz_node = ET.SubElement(root, "HeaderZone")
        ET.SubElement(hz_node, "UnrevealedLogo", attrib={"path": unrev_path})
        ET.SubElement(hz_node, "RevealedBackground", attrib={"path": rev_path})
        ET.SubElement(hz_node, "Font", attrib={
            "family": str(ch_font.get("family", "ITC Korinna")),
            "size": str(ch_font.get("size", 28)),
            "bold": str(ch_font.get("bold", True)).lower(),
            "color": str(ch_font.get("color", "#FFFFFF")),
            "mode": str(ch_font.get("mode", "dynamic")),
        })

        ch_node = ET.SubElement(root, "CategoryHeaders", attrib={
            "fit_mode": str(ch_data.get("fit_mode", "stretch")),
            "auto_crop_logo": str(ch_data.get("auto_crop_logo", True)).lower(),
        })
        ET.SubElement(ch_node, "StateUnrevealed", attrib={"image_path": unrev_path})
        ET.SubElement(ch_node, "StateRevealed", attrib={"image_path": rev_path})
        ET.SubElement(ch_node, "Font", attrib={
            "family": str(ch_font.get("family", "ITC Korinna")),
            "size": str(ch_font.get("size", 28)),
            "bold": str(ch_font.get("bold", True)).lower(),
            "color": str(ch_font.get("color", "#FFFFFF")),
            "mode": str(ch_font.get("mode", "dynamic")),
        })

        # PointGrid
        pg_data = theme.get("point_grid", {})
        pg_node = ET.SubElement(root, "PointGrid", attrib={
            "fit_mode": str(pg_data.get("fit_mode", "zoom"))
        })
        ET.SubElement(pg_node, "Mode", attrib={
            "use_image": str(pg_data.get("use_image", True)).lower()
        })
        ET.SubElement(pg_node, "SolidColor", attrib={
            "value": str(pg_data.get("solid_color", "#060CE9"))
        })
        ET.SubElement(pg_node, "TileImage", attrib={
            "path": cls._to_relative_assets_path(pg_data.get("tile_image", ""))
        })
        pg_font = pg_data.get("font", {})
        ET.SubElement(pg_node, "PointFont", attrib={
            "family": str(pg_font.get("family", "Impact")),
            "size": str(pg_font.get("size", 48)),
            "bold": str(pg_font.get("bold", True)).lower(),
            "color": str(pg_font.get("color", "#FFA500")),
            "mode": str(pg_font.get("mode", "dynamic")),
        })

        # ClueScreen
        cs_data = theme.get("clue_screen", {})
        cs_node = ET.SubElement(root, "ClueScreen", attrib={
            "fit_mode": str(cs_data.get("fit_mode", "zoom"))
        })
        ET.SubElement(cs_node, "OuterBackground", attrib={
            "color": str(cs_data.get("outer_bg_color", "#000000"))
        })
        std_card = cs_data.get("standard_card", {})
        ET.SubElement(cs_node, "StandardCard", attrib={
            "color": str(std_card.get("color", "#060CE9")),
            "image_path": cls._to_relative_assets_path(std_card.get("image_path", "")),
            "use_image": str(std_card.get("use_image", True)).lower(),
        })
        fin_card = cs_data.get("final_card", {})
        ET.SubElement(cs_node, "FinalCard", attrib={
            "color": str(fin_card.get("color", "#8B0000")),
            "image_path": cls._to_relative_assets_path(fin_card.get("image_path", "")),
            "use_image": str(fin_card.get("use_image", True)).lower(),
        })
        cs_font = cs_data.get("font", {})
        ET.SubElement(cs_node, "Font", attrib={
            "family": str(cs_font.get("family", "ITC Korinna")),
            "size": str(cs_font.get("size", 48)),
            "answer_size": str(cs_font.get("answer_size", 30)),
            "header_size": str(cs_font.get("header_size", ch_font.get("size", 28))),
            "bold": str(cs_font.get("bold", True)).lower(),
            "color": str(cs_font.get("color", "#FFFFFF")),
            "mode": str(cs_font.get("mode", "dynamic")),
        })
        sh_data = cs_data.get("shadow", {})
        ET.SubElement(cs_node, "Shadow", attrib={
            "blur": str(sh_data.get("blur", 2)),
            "dx": str(sh_data.get("dx", 3)),
            "dy": str(sh_data.get("dy", 3)),
            "color": str(sh_data.get("color", "#000000")),
        })

        # VisualFX
        vfx_data = theme.get("visual_fx", {})
        vfx_node = ET.SubElement(root, "VisualFX")
        ET.SubElement(vfx_node, "DailyDoubleSplash", attrib={
            "path": cls._to_relative_assets_path(vfx_data.get("daily_double_splash", ""))
        })
        ET.SubElement(vfx_node, "FinalLogoSplash", attrib={
            "path": cls._to_relative_assets_path(vfx_data.get("final_logo_splash", ""))
        })

        # Animations
        anim_data = theme.get("animations", {})
        ET.SubElement(root, "Animations", attrib={
            "enable_point_zoom": str(anim_data.get("enable_point_zoom", True)).lower(),
            "zoom_duration_ms": str(int(anim_data.get("zoom_duration_ms", 400))),
            "enable_dd_flip": str(anim_data.get("enable_dd_flip", True)).lower(),
            "flip_duration_ms": str(int(anim_data.get("flip_duration_ms", 900))),
            "intro_video_path": cls._to_relative_assets_path(anim_data.get("intro_video_path", "")),
            "intro_merge_seconds": str(float(anim_data.get("intro_merge_seconds", 5.0))),
            "intro_fade_duration_ms": str(int(anim_data.get("intro_fade_duration_ms", 1500))),
            "outro_music_path": cls._to_relative_assets_path(anim_data.get("outro_music_path", "")),
        })

        # Sounds
        snd_node = ET.SubElement(root, "Sounds")
        sounds_dict = theme.get("sounds", {})
        canonical_keys = [
            "board_fill",
            "round_category_intro",
            "daily_double",
            "timeout",
            "correct",
            "wrong",
            "final_category_intro",
            "think_30s",
            "outro_music",
        ]
        for key in canonical_keys:
            p = sounds_dict.get(key, "")
            ET.SubElement(snd_node, "Sound", attrib={
                "key": key,
                "path": cls._to_relative_assets_path(p) if p else "",
            })

        AssetRenderer.clear_cache()

        raw_xml = ET.tostring(root, encoding="utf-8")
        parsed = minidom.parseString(raw_xml)
        pretty_xml = parsed.toprettyxml(indent="    ")

        with open(out_p, "w", encoding="utf-8") as f:
            f.write(pretty_xml)

    @staticmethod
    def _to_relative_assets_path(full_path: str) -> str:
        if not full_path:
            return ""
        p = Path(full_path)
        try:
            rel = p.relative_to(DEFAULT_ASSETS_DIR)
            return f"assets/{rel.as_posix()}"
        except ValueError:
            return p.as_posix()
