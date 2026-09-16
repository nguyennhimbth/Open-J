"""Open-J Studio Audio Subsystem.
Manages SFX and background music playback decoupled via EventBus.
Uses QSoundEffect for low-latency RAM-cached short sound effects,
round-robin pool for rapid sequential coin fill sounds,
and QMediaPlayer + QAudioOutput for longer theme music (think_music / think_30s).
Handles audio device changes gracefully and guarantees absolute silence if audio files are missing.
"""

import os
import time
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import QObject, Slot, QUrl, QTimer
from PySide6.QtMultimedia import QSoundEffect, QMediaPlayer, QAudioOutput, QMediaDevices

from core.event_bus import event_bus


class AudioManager(QObject):
    """Quản lý toàn bộ hiệu ứng âm thanh và nhạc nền truyền hình.
    Tuân thủ nguyên tắc Im Lặng Tuyệt Đối:
    - Không tự phát còi bíp hệ thống, tone demo hay âm thanh giả lập.
    - Chỉ phát âm thanh khi người dùng đã gán file cụ thể và file đó tồn tại trên đĩa.
    """

    DEFAULT_SOUND_MAP = {}

    def __init__(self, sounds_dir=None, parent=None):
        super().__init__(parent)
        if sounds_dir is None:
            self.sounds_dir = Path(__file__).resolve().parent / "assets" / "sounds"
        else:
            self.sounds_dir = Path(sounds_dir).resolve()

        self.sound_files: Dict[str, str] = {}
        self.effects: Dict[str, QSoundEffect] = {}

        # Audio Output & Media Player for Long Theme Music (think_music)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.85)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)

        # Cache of QSoundEffect objects for low latency SFX
        self.sfx_effects: Dict[str, QSoundEffect] = self.effects

        # Round-robin pool of 4 QSoundEffects specifically for sequential fill ticker (coin drop)
        self.fill_pool = []
        self.fill_pool_index = 0
        self.last_fill_time = 0.0

        self._init_sfx_cache()
        self._init_fill_pool()

        # Listen for OS audio endpoint changes (e.g. HDMI hotplug)
        try:
            self.devices = QMediaDevices(self)
            self.devices.audioOutputsChanged.connect(self._on_audio_device_changed)
        except Exception as e:
            print(f"[AudioManager] Warning connecting QMediaDevices: {e}")

        # Connect to EventBus
        event_bus.play_sound_event.connect(self.play_sound)

    def _resolve_sound_path(self, file_or_path: str) -> Optional[Path]:
        """Kiểm tra sự tồn tại của file âm thanh, trả về Path hoặc None (im lặng tuyệt đối)."""
        if not file_or_path:
            return None
        p = Path(file_or_path)
        if p.is_absolute() and p.exists():
            return p

        # Check in self.sounds_dir
        cand = self.sounds_dir / p.name
        if cand.exists():
            return cand

        # Check aliases
        aliases = {
            "coin_drop.wav": "fill.wav",
            "fill.wav": "coin_drop.wav",
            "board_fill_single.wav": "fill.wav",
            "dd_laser.wav": "daily_double.wav",
            "daily_double.wav": "dd_laser.wav",
            "times_up.wav": "timeout.wav",
            "timeout.wav": "times_up.wav",
            "time_out.wav": "timeout.wav",
            "buzzer.wav": "timeout.wav",
        }
        if p.name in aliases:
            cand_alt = self.sounds_dir / aliases[p.name]
            if cand_alt.exists():
                return cand_alt

        return None

    def _init_sfx_cache(self):
        """Nạp các hiệu ứng âm thanh ngắn vào RAM để phát ngay lập tức."""
        self.sfx_effects.clear()
        for key, file_name in self.sound_files.items():
            if key in ("think_music", "think_30s"):
                continue
            full_path = self._resolve_sound_path(file_name)
            if full_path:
                try:
                    effect = QSoundEffect(self)
                    effect.setSource(QUrl.fromLocalFile(str(full_path)))
                    effect.setVolume(0.85)
                    self.sfx_effects[key] = effect
                except Exception as e:
                    print(f"[AudioManager] Warning loading SFX '{key}': {e}")

    def _init_fill_pool(self):
        """Khởi tạo pool 4 sound effect độc lập cho hiệu ứng lật ô liên tục."""
        self.fill_pool.clear()
        fill_path = self._resolve_sound_path(self.sound_files.get("fill", "coin_drop.wav"))
        if fill_path:
            for _ in range(4):
                try:
                    eff = QSoundEffect(self)
                    eff.setSource(QUrl.fromLocalFile(str(fill_path)))
                    eff.setVolume(0.75)
                    self.fill_pool.append(eff)
                except Exception:
                    pass

    def _on_audio_device_changed(self):
        """Tự động cập nhật audio endpoint khi cắm/rút thiết bị âm thanh."""
        try:
            default_dev = QMediaDevices.defaultAudioOutput()
            self.audio_output.setDevice(default_dev)
            print(f"[AudioManager] Audio output re-routed to: {default_dev.description()}")
        except Exception as e:
            print(f"[AudioManager] Audio device update notice: {e}")

    def load_sound(self, key: str, path: str):
        """Tải âm thanh từ file cụ thể. Nếu không tồn tại -> im lặng 100%."""
        self.set_sound_file(key, path)

    def set_sound_file(self, event_key: str, file_path: str):
        """Gán file âm thanh cho một event key cụ thể."""
        if not file_path:
            self.sound_files.pop(event_key, None)
            self.sfx_effects.pop(event_key, None)
            return

        p = self._resolve_sound_path(file_path)
        if p and os.path.isfile(str(p)):
            self.sound_files[event_key] = str(p)
            if event_key not in ("think_music", "think_30s"):
                try:
                    effect = QSoundEffect(self)
                    effect.setSource(QUrl.fromLocalFile(str(p)))
                    effect.setVolume(0.85)
                    self.sfx_effects[event_key] = effect
                    if event_key in ("fill", "board_fill"):
                        self._init_fill_pool()
                except Exception as e:
                    print(f"[AudioManager] Error updating SFX '{event_key}': {e}")
        else:
            # Nếu file không tồn tại, gỡ bỏ để giữ im lặng tuyệt đối
            self.sound_files.pop(event_key, None)
            self.sfx_effects.pop(event_key, None)

    def load_from_dict(self, sounds_dict: Dict[str, str]):
        """Nạp toàn bộ cấu hình âm thanh từ theme dict."""
        for k, v in sounds_dict.items():
            if v:
                self.set_sound_file(k, v)

    def play(self, key: str):
        """Alias phát âm thanh theo key."""
        self.play_sound(key)

    @Slot(str)
    def play_sound(self, sound_key: str):
        """Phát âm thanh theo key. Nếu không có file hoặc file hỏng -> im lặng tuyệt đối."""
        try:
            # 1. Âm thanh Mở bảng (Phát duy nhất 1 lần hoàn chỉnh khi bắt đầu)
            if sound_key in ("fill", "board_fill"):
                # Ưu tiên key board_fill hoặc fill
                target_key = "board_fill" if "board_fill" in self.sfx_effects else "fill"
                if target_key in self.sfx_effects:
                    eff = self.sfx_effects[target_key]
                    eff.stop()
                    eff.play()
                    return
                elif self.fill_pool:
                    eff = self.fill_pool[0]
                    eff.stop()
                    eff.play()
                    return

            # Map alias keys
            mapped_key = sound_key
            if mapped_key == "time_out" and "time_out" not in self.sfx_effects:
                mapped_key = "timeout"
            elif mapped_key == "timeout" and "timeout" not in self.sfx_effects:
                mapped_key = "time_out"

            # 2. Nhạc nền suy nghĩ 30s (QMediaPlayer)
            if mapped_key in ("think_music", "think_30s"):
                fn = self.sound_files.get(mapped_key, self.sound_files.get("think_music", "think_30s.wav"))
                full_path = self._resolve_sound_path(fn)
                if full_path:
                    self.player.stop()
                    self.player.setSource(QUrl.fromLocalFile(str(full_path)))
                    self.player.play()
                else:
                    self.player.stop()
                    self.player.setSource(QUrl())
                return

            # 3. Các hiệu ứng SFX khác (QSoundEffect cached)
            if mapped_key in self.sfx_effects:
                eff = self.sfx_effects[mapped_key]
                eff.stop()
                eff.play()
                return

            # 4. Fallback nạp lười nếu chưa nạp trước
            fn = self.sound_files.get(mapped_key) or self.sound_files.get(sound_key)
            if fn:
                full_path = self._resolve_sound_path(fn)
                if full_path:
                    effect = QSoundEffect(self)
                    effect.setSource(QUrl.fromLocalFile(str(full_path)))
                    effect.setVolume(0.85)
                    self.sfx_effects[mapped_key] = effect
                    effect.play()
            if fn:
                full_path = self._resolve_sound_path(fn)
                if full_path:
                    effect = QSoundEffect(self)
                    effect.setSource(QUrl.fromLocalFile(str(full_path)))
                    effect.setVolume(0.85)
                    self.sfx_effects[sound_key] = effect
                    effect.play()
            # Nếu không tìm thấy file -> GIỮ IM LẶNG HOÀN TOÀN, không bíp demo
        except Exception as ex:
            print(f"[AudioManager] Audio playback error: {ex}")

    def stop_music(self):
        """Dừng nhạc nền 30s ngay lập tức."""
        try:
            self.player.stop()
        except Exception:
            pass

    def stop_all(self):
        """Dừng ngay lập tức toàn bộ âm thanh (nhạc nền, SFX, fill ticker)."""
        self.stop_music()
        for effect in self.sfx_effects.values():
            try:
                effect.stop()
            except Exception:
                pass
        for effect in self.fill_pool:
            try:
                effect.stop()
            except Exception:
                pass


# Backward compatibility alias
SoundManager = AudioManager
__all__ = ["AudioManager", "SoundManager"]
