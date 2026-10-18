"""Open-J Studio Audio Subsystem.
Manages SFX and background music playback decoupled via EventBus.
Fixes triple-instance playback bug via Singleton pattern, supports both .wav (QSoundEffect)
and compressed .mp3/.m4a/.aac/.ogg (QMediaPlayer), removes folder-level alias hijacking,
and adds play_file() for Settings preview.
"""

import os
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import QObject, Slot, QUrl
from PySide6.QtMultimedia import QSoundEffect, QMediaPlayer, QAudioOutput, QMediaDevices

from core.event_bus import event_bus


class AudioManager(QObject):
    """Singleton broadcast audio manager.
    Guarantees:
    - Only ONE instance connects to event_bus.play_sound_event (preventing overlapping multi-playback).
    - No hidden folder-level alias substitution or hardcoded fallback audio.
    - Supports both .wav (via QSoundEffect) and .mp3/.m4a/.aac/.ogg (via QMediaPlayer).
    """

    _instance: Optional["AudioManager"] = None
    _initialized: bool = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, sounds_dir=None, parent=None):
        if self.__class__._initialized:
            return
        super().__init__(parent)
        self.__class__._initialized = True

        if sounds_dir is None:
            self.sounds_dir = Path(__file__).resolve().parent / "assets" / "sounds"
        else:
            self.sounds_dir = Path(sounds_dir).resolve()

        self.sound_files: Dict[str, str] = {}
        self.effects: Dict[str, QSoundEffect] = {}
        self.sfx_effects: Dict[str, QSoundEffect] = self.effects

        # Long BGM Player (think_30s, outro_music)
        self.bgm_output = QAudioOutput(self)
        self.bgm_output.setVolume(0.85)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.bgm_output)

        # Short compressed SFX Player (for .mp3 / .m4a / .ogg SFX files & Settings preview)
        self.sfx_output = QAudioOutput(self)
        self.sfx_output.setVolume(0.85)
        self.sfx_player = QMediaPlayer(self)
        self.sfx_player.setAudioOutput(self.sfx_output)

        # Listen for OS audio endpoint changes
        try:
            self.devices = QMediaDevices(self)
            self.devices.audioOutputsChanged.connect(self._on_audio_device_changed)
        except Exception as e:
            print(f"[AudioManager] Warning connecting QMediaDevices: {e}")

        # Connect to EventBus (exactly once via singleton)
        event_bus.play_sound_event.connect(self.play_sound)
        event_bus.update_theme_config.connect(self._on_theme_updated)

    @Slot(dict)
    def _on_theme_updated(self, theme_data: dict):
        if isinstance(theme_data, dict):
            sounds_dict = theme_data.get("sounds", {})
            if isinstance(sounds_dict, dict):
                self.load_from_dict(sounds_dict)

    def _resolve_sound_path(self, file_or_path: str) -> Optional[Path]:
        """Resolves an explicitly assigned sound file path without substituting unrelated sounds."""
        if not file_or_path:
            return None
        p = Path(file_or_path)
        if p.is_absolute() and p.is_file():
            return p

        # Relative to project root or assets
        project_root = Path(__file__).resolve().parent.parent
        for base in (project_root, project_root / "ui", self.sounds_dir.parent, self.sounds_dir):
            cand = (base / file_or_path).resolve()
            if cand.is_file():
                return cand

        cand_name = self.sounds_dir / p.name
        if cand_name.is_file():
            return cand_name

        return None

    def _on_audio_device_changed(self):
        try:
            default_dev = QMediaDevices.defaultAudioOutput()
            self.bgm_output.setDevice(default_dev)
            self.sfx_output.setDevice(default_dev)
        except Exception as e:
            print(f"[AudioManager] Audio device update notice: {e}")

    def load_sound(self, key: str, path: str):
        self.set_sound_file(key, path)

    def set_sound_file(self, event_key: str, file_path: str):
        """Assigns an audio file to a specific event key (or clears it if empty)."""
        file_path = (file_path or "").strip()
        if not file_path:
            self.sound_files.pop(event_key, None)
            self.sfx_effects.pop(event_key, None)
            return

        p = self._resolve_sound_path(file_path)
        if p and p.is_file():
            self.sound_files[event_key] = str(p)
            # Only cache uncompressed .wav in QSoundEffect; .mp3/.m4a use sfx_player
            if event_key not in ("think_30s", "think_music", "outro_music") and p.suffix.lower() == ".wav":
                try:
                    effect = QSoundEffect(self)
                    effect.setSource(QUrl.fromLocalFile(str(p)))
                    effect.setVolume(0.85)
                    self.sfx_effects[event_key] = effect
                except Exception as e:
                    print(f"[AudioManager] Error caching WAV '{event_key}': {e}")
            else:
                self.sfx_effects.pop(event_key, None)
        else:
            self.sound_files.pop(event_key, None)
            self.sfx_effects.pop(event_key, None)

    def load_from_dict(self, sounds_dict: Dict[str, str]):
        """Synchronizes all sound bindings from theme dictionary (clearing removed ones)."""
        self.sound_files.clear()
        self.sfx_effects.clear()
        for k, v in sounds_dict.items():
            if k == "wager_music":
                continue
            self.set_sound_file(k, v)

    def play_file(self, file_path: str):
        """Directly plays any audio file path (used by Settings 'Play' preview button and Outro music)."""
        p = self._resolve_sound_path(file_path)
        if not p or not p.is_file():
            return
        self.stop_all()
        try:
            self.sfx_player.setSource(QUrl.fromLocalFile(str(p)))
            self.sfx_player.play()
        except Exception as e:
            print(f"[AudioManager] Preview play_file error: {e}")

    def play(self, key: str):
        self.play_sound(key)

    @Slot(str)
    def play_sound(self, sound_key: str):
        """Plays the exact sound assigned to sound_key. Strictly silent if unassigned."""
        if not sound_key or sound_key == "wager_music":
            return

        # Canonicalize legacy callers without cross-mixing distinct events
        canonical_map = {
            "fill": "board_fill",
            "think_music": "think_30s",
            "time_out": "timeout",
            "category_intro": "final_category_intro",
        }
        mapped_key = sound_key if sound_key in self.sound_files else canonical_map.get(sound_key, sound_key)

        file_path = self.sound_files.get(mapped_key, "")
        if not file_path:
            return

        full_path = self._resolve_sound_path(file_path)
        if not full_path or not full_path.is_file():
            return

        try:
            # Long tracks (think_30s, outro_music) use self.player
            if mapped_key in ("think_30s", "outro_music"):
                self.player.stop()
                self.player.setSource(QUrl.fromLocalFile(str(full_path)))
                self.player.play()
                return

            # WAV SFX cached in QSoundEffect
            if full_path.suffix.lower() == ".wav":
                if mapped_key not in self.sfx_effects:
                    eff = QSoundEffect(self)
                    eff.setSource(QUrl.fromLocalFile(str(full_path)))
                    eff.setVolume(0.85)
                    self.sfx_effects[mapped_key] = eff
                eff = self.sfx_effects[mapped_key]
                eff.stop()
                eff.play()
                return

            # Compressed SFX (.mp3, .m4a, .aac, .ogg) use self.sfx_player
            self.sfx_player.stop()
            self.sfx_player.setSource(QUrl.fromLocalFile(str(full_path)))
            self.sfx_player.play()
        except Exception as ex:
            print(f"[AudioManager] Audio playback error for '{sound_key}': {ex}")

    def stop_music(self):
        try:
            self.player.stop()
        except Exception:
            pass

    def stop_all(self):
        self.stop_music()
        try:
            self.sfx_player.stop()
        except Exception:
            pass
        for effect in list(self.sfx_effects.values()):
            try:
                effect.stop()
            except Exception:
                pass


# Backward compatibility alias
SoundManager = AudioManager
__all__ = ["AudioManager", "SoundManager"]
