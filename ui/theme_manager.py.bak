"""Open-J: Theme Package Engine, Asset Renderer & XML Manager.
Handles full-fidelity asset rendering with aspect ratio zoom/tile fitting,
exporting/importing .zip packages, and XML configuration.
"""

import os
import zipfile
import shutil
import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path
from typing import Dict, Any, Optional

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QPixmap, QBrush, QColor, QFont


# Project Root Anchor
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ASSETS_DIR = PROJECT_ROOT / "ui" / "assets"
DEFAULT_XML_PATH = DEFAULT_ASSETS_DIR / "theme.xml"


# =============================================================================
# 1. ASSET RENDERER (DUAL FITTING ENGINE: ZOOM CROP VS TILE REPEAT)
# =============================================================================

class AssetRenderer:
    """Standard graphic rendering engine for TV Studio Broadcast Display."""

    @staticmethod
    def render_background(painter: QPainter, target_rect: QRect, pixmap: Optional[QPixmap], fit_mode: str = "zoom"):
        """
        fit_mode:
          - 'zoom': Scale preserving aspect ratio and crop overflow margins (KeepAspectRatioByExpanding)
          - 'tile': Repeat texture pattern (Texture Pattern Tiling)
        """
        if pixmap is None or pixmap.isNull():
            return

        if fit_mode == "tile":
            # Pattern Tiling Mode
            brush = QBrush(pixmap)
            painter.fillRect(target_rect, brush)
        else:
            # Full Zoom Crop Mode (KeepAspectRatioByExpanding - Default)
            scaled = pixmap.scaled(
                target_rect.size(),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation
            )
            # Center and crop excess
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
            # Write theme.xml at the root of the zip
            if xml_p.exists():
                zip_file.write(str(xml_p), arcname="theme.xml")

            # Write all assets (images, sounds, etc.)
            if assets_p.exists():
                for item in assets_p.rglob("*"):
                    if item.is_file() and item.name != "theme.xml":
                        # arcname = assets/...
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
            # Check subdirectories
            found = list(target_dir.rglob("theme.xml"))
            if found:
                extracted_xml = found[0]

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
        # Direct join test
        for base in search_bases:
            if base:
                cand = (base / raw_path).resolve()
                if cand.exists():
                    return str(cand)
                # If raw_path has 'assets/images/...' and base is 'ui/assets'
                if raw_path.startswith("assets/"):
                    cand2 = (base.parent / raw_path).resolve()
                    if cand2.exists():
                        return str(cand2)
                    cand3 = (DEFAULT_ASSETS_DIR / raw_path.replace("assets/", "")).resolve()
                    if cand3.exists():
                        return str(cand3)
                # Fallback search by filename in images/sounds
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
            "bezel_color": "#000000",
            "bezel_width": 8,
            "standby_screen": {
                "image_path": cls.resolve_path("images/standby_static.png"),
            },
            "category_headers": {
                "fit_mode": "zoom",
                "unrevealed_image": cls.resolve_path("images/header_logo.png"),
                "revealed_image": cls.resolve_path("images/header_revealed_bg.png"),
                "font": {"family": "Georgia", "size": 28, "bold": True, "color": "#FFFFFF"},
            },
            "point_grid": {
                "fit_mode": "zoom",
                "use_image": True,
                "solid_color": "#060CE9",
                "tile_image": cls.resolve_path("images/tile_texture.png"),
                "font": {"family": "Impact", "size": 48, "bold": True, "color": "#FFA500"},
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
                "font": {"family": "Georgia", "size": 48, "bold": True, "color": "#FFFFFF"},
                "shadow": {"blur": 2, "dx": 3, "dy": 3, "color": "#000000"},
            },
            "visual_fx": {
                "daily_double_splash": cls.resolve_path("images/daily_double.png"),
                "final_logo_splash": cls.resolve_path("images/final_jeopardy_logo.png"),
            },
            "sounds": {
                "fill": cls.resolve_path("sounds/fill.mp3"),
                "board_fill": cls.resolve_path("sounds/fill.mp3"),
                "daily_double": cls.resolve_path("sounds/daily_double.wav"),
                "think_music": cls.resolve_path("sounds/think_30s.wav"),
                "think_30s": cls.resolve_path("sounds/think_30s.wav"),
                "time_out": cls.resolve_path("sounds/timeout.wav"),
                "timeout": cls.resolve_path("sounds/timeout.wav"),
                "correct": cls.resolve_path("sounds/correct.wav"),
                "wrong": cls.resolve_path("sounds/wrong.wav"),
                "category_intro": cls.resolve_path("sounds/category_intro.wav"),
            }
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

            # Bezel
            bezel_node = root.find("Bezel")
            if bezel_node is not None:
                theme["bezel_color"] = bezel_node.attrib.get("color", theme["bezel_color"])
                theme["bezel_width"] = int(bezel_node.attrib.get("width", theme["bezel_width"]))

            # StandbyMosaicZone (Part 3) & StandbyScreen
            smz_node = root.find("StandbyMosaicZone")
            if smz_node is not None:
                mi_node = smz_node.find("MosaicImage")
                if mi_node is not None:
                    p_val = mi_node.attrib.get("path", "")
                    theme["standby_screen"]["image_path"] = cls.resolve_path(p_val, base_dir)
            sb_node = root.find("StandbyScreen")
            if sb_node is not None:
                p_val = sb_node.attrib.get("image_path", "")
                if p_val:
                    theme["standby_screen"]["image_path"] = cls.resolve_path(p_val, base_dir)

            # HeaderZone (Part 3)
            hz_node = root.find("HeaderZone")
            if hz_node is not None:
                unrev = hz_node.find("UnrevealedLogo")
                if unrev is not None:
                    p_val = unrev.attrib.get("path") or unrev.attrib.get("image_path", "")
                    theme["category_headers"]["unrevealed_image"] = cls.resolve_path(p_val, base_dir)
                rev = hz_node.find("RevealedBackground")
                if rev is not None:
                    p_val = rev.attrib.get("path") or rev.attrib.get("image_path", "")
                    theme["category_headers"]["revealed_image"] = cls.resolve_path(p_val, base_dir)
                f_node = hz_node.find("Font")
                if f_node is not None:
                    theme["category_headers"]["font"]["family"] = f_node.attrib.get("family", "Georgia")
                    theme["category_headers"]["font"]["size"] = int(f_node.attrib.get("size", 28))
                    theme["category_headers"]["font"]["bold"] = f_node.attrib.get("bold", "true").lower() == "true"
                    theme["category_headers"]["font"]["color"] = f_node.attrib.get("color", "#FFFFFF")

            # CategoryHeaders (Backward Compatibility)
            ch_node = root.find("CategoryHeaders")
            if ch_node is not None:
                theme["category_headers"]["fit_mode"] = ch_node.attrib.get("fit_mode", "zoom")
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
                    theme["category_headers"]["font"]["family"] = f_node.attrib.get("family", "Georgia")
                    theme["category_headers"]["font"]["size"] = int(f_node.attrib.get("size", 28))
                    theme["category_headers"]["font"]["bold"] = f_node.attrib.get("bold", "true").lower() == "true"
                    theme["category_headers"]["font"]["color"] = f_node.attrib.get("color", "#FFFFFF")

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
                    theme["clue_screen"]["font"]["family"] = cf_node.attrib.get("family", "Georgia")
                    theme["clue_screen"]["font"]["size"] = int(cf_node.attrib.get("size", 48))
                    theme["clue_screen"]["font"]["bold"] = cf_node.attrib.get("bold", "true").lower() == "true"
                    theme["clue_screen"]["font"]["color"] = cf_node.attrib.get("color", "#FFFFFF")

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

            # Sounds
            snd_node = root.find("Sounds")
            if snd_node is not None:
                for s in snd_node.findall("Sound"):
                    k = s.attrib.get("key")
                    path_val = s.attrib.get("path", "").strip()
                    if k and path_val:
                        theme["sounds"][k] = cls.resolve_path(path_val, base_dir)

            # Part 3 / Master Spec aliases
            theme["header_zone"] = {
                "unrevealed_logo": theme["category_headers"].get("unrevealed_image", ""),
                "revealed_background": theme["category_headers"].get("revealed_image", ""),
                "font": dict(theme["category_headers"].get("font", {}))
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

        root = ET.Element("JeopardyTheme", attrib={"name": theme.get("name", "Custom_Broadcast_Package")})

        # Bezel
        ET.SubElement(root, "Bezel", attrib={
            "color": str(theme.get("bezel_color", "#000000")),
            "width": str(theme.get("bezel_width", 8))
        })

        # StandbyScreen & StandbyMosaicZone (Part 3)
        sb_data = theme.get("standby_screen", {})
        sb_rel_path = cls._to_relative_assets_path(sb_data.get("image_path", ""))
        ET.SubElement(root, "StandbyScreen", attrib={
            "image_path": sb_rel_path
        })
        smz_node = ET.SubElement(root, "StandbyMosaicZone")
        ET.SubElement(smz_node, "MosaicImage", attrib={
            "path": sb_rel_path
        })

        # HeaderZone (Part 3 Red Zone) & CategoryHeaders
        ch_data = theme.get("category_headers", {})
        unrev_path = cls._to_relative_assets_path(ch_data.get("unrevealed_image", ""))
        rev_path = cls._to_relative_assets_path(ch_data.get("revealed_image", ""))
        ch_font = ch_data.get("font", {})

        hz_node = ET.SubElement(root, "HeaderZone")
        ET.SubElement(hz_node, "UnrevealedLogo", attrib={"path": unrev_path})
        ET.SubElement(hz_node, "RevealedBackground", attrib={"path": rev_path})
        ET.SubElement(hz_node, "Font", attrib={
            "family": str(ch_font.get("family", "Georgia")),
            "size": str(ch_font.get("size", 28)),
            "bold": str(ch_font.get("bold", True)).lower(),
            "color": str(ch_font.get("color", "#FFFFFF"))
        })

        ch_node = ET.SubElement(root, "CategoryHeaders", attrib={
            "fit_mode": ch_data.get("fit_mode", "zoom")
        })
        ET.SubElement(ch_node, "StateUnrevealed", attrib={
            "image_path": unrev_path
        })
        ET.SubElement(ch_node, "StateRevealed", attrib={
            "image_path": rev_path
        })
        ET.SubElement(ch_node, "Font", attrib={
            "family": str(ch_font.get("family", "Georgia")),
            "size": str(ch_font.get("size", 28)),
            "bold": str(ch_font.get("bold", True)).lower(),
            "color": str(ch_font.get("color", "#FFFFFF"))
        })

        # PointGrid
        pg_data = theme.get("point_grid", {})
        pg_node = ET.SubElement(root, "PointGrid", attrib={
            "fit_mode": pg_data.get("fit_mode", "zoom")
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
            "color": str(pg_font.get("color", "#FFA500"))
        })

        # ClueScreen
        cs_data = theme.get("clue_screen", {})
        cs_node = ET.SubElement(root, "ClueScreen", attrib={
            "fit_mode": cs_data.get("fit_mode", "zoom")
        })
        ET.SubElement(cs_node, "OuterBackground", attrib={
            "color": str(cs_data.get("outer_bg_color", "#000000"))
        })
        std_card = cs_data.get("standard_card", {})
        ET.SubElement(cs_node, "StandardCard", attrib={
            "color": str(std_card.get("color", "#060CE9")),
            "image_path": cls._to_relative_assets_path(std_card.get("image_path", "")),
            "use_image": str(std_card.get("use_image", True)).lower()
        })
        fin_card = cs_data.get("final_card", {})
        ET.SubElement(cs_node, "FinalCard", attrib={
            "color": str(fin_card.get("color", "#8B0000")),
            "image_path": cls._to_relative_assets_path(fin_card.get("image_path", "")),
            "use_image": str(fin_card.get("use_image", True)).lower()
        })
        cs_font = cs_data.get("font", {})
        ET.SubElement(cs_node, "Font", attrib={
            "family": str(cs_font.get("family", "Georgia")),
            "size": str(cs_font.get("size", 48)),
            "bold": str(cs_font.get("bold", True)).lower(),
            "color": str(cs_font.get("color", "#FFFFFF"))
        })
        sh_data = cs_data.get("shadow", {})
        ET.SubElement(cs_node, "Shadow", attrib={
            "blur": str(sh_data.get("blur", 2)),
            "dx": str(sh_data.get("dx", 3)),
            "dy": str(sh_data.get("dy", 3)),
            "color": str(sh_data.get("color", "#000000"))
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

        # Sounds
        snd_node = ET.SubElement(root, "Sounds")
        sounds_dict = theme.get("sounds", {})
        for key, p in sounds_dict.items():
            if p and os.path.exists(p):
                ET.SubElement(snd_node, "Sound", attrib={
                    "key": key,
                    "path": cls._to_relative_assets_path(p)
                })

        # Format pretty XML
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

