"""Open-J: Decoupled Event Bus Module.
Central signal dispatcher for the entire game show engine, host controller,
and TV studio display. Communicates 100% via PySide6 Qt Signals.
"""

from PySide6.QtCore import QObject, Signal


class _CategoryRevealSignal:
    """Wrapper allowing trigger_category_reveal.emit() with 0 or 1 argument."""
    def __init__(self, q_signal):
        self._q_signal = q_signal

    def connect(self, slot):
        return self._q_signal.connect(slot)

    def disconnect(self, *args):
        return self._q_signal.disconnect(*args)

    def emit(self, data=None):
        if data is None:
            data = {"auto": True, "step": 0, "col_index": 0}
        self._q_signal.emit(data)

    def __getitem__(self, item):
        return self._q_signal[item]


class EventBus(QObject):
    """Trạm trung chuyển tín hiệu toàn hệ thống (Decoupled Event Bus)"""

    # --- Điều khiển Gameplay cơ bản ---
    request_open_question = Signal(int, int, int)       # (round_id, col, row)
    display_question = Signal(dict)                      # Payload câu hỏi chi tiết
    close_question = Signal()                            # Đóng câu hỏi, quay lại bảng
    trigger_daily_double = Signal(str, int)              # (player_id, points)
    modify_score = Signal(str, int, bool)                # (player_id, delta, is_correct)
    score_updated = Signal(dict)                         # {p1: x, p2: y, p3: z}
    change_round = Signal(int)                           # 1: Normal, 2: Double, 3: Final

    # --- Hiệu ứng Hoạt cảnh Studio (Studio FX) ---
    trigger_board_blank = Signal()                       # Bảng trống (chỉ hiện bezel và background)
    trigger_board_fill = Signal()                        # Animation lật mở ngẫu nhiên 30 ô điểm
    _raw_category_reveal = Signal(dict)                  # Tín hiệu nội bộ { "auto": bool, "step": int, "col_index": int }
    trigger_category_next = Signal()                     # Lệnh slide sang trái cho cột kế tiếp (thủ công)
    cancel_category_reveal = Signal()                    # Hủy intro, quay về bảng tức thì
    trigger_category_reveal_step = Signal(int)           # Điều khiển từng bước intro chủ đề (step: 0=Logo, 1=Reveal, 2=NextSlide)
    trigger_category_show_logo = Signal(int)             # Hiện Logo che tên chủ đề theo cột (col_index)
    trigger_category_fade_logo = Signal()                # Fade-out logo để mở tên chủ đề
    trigger_category_slide_next = Signal()               # Trượt sang cột tiếp theo
    request_clue_zoom = Signal(dict)                     # Bắn payload câu hỏi: kích hoạt zoom điểm trước
    trigger_daily_double_splash = Signal(str)            # Đường dẫn ảnh Daily Double
    set_display_fullscreen_toggle = Signal()             # Tương đương phím F11 (Fullscreen/Windowed toggle)

    # --- Final Jeopardy, Sound Engine & Theme ---
    trigger_final_step = Signal(int, dict)               # step: 1 (Logo Splash), 2 (Category), 3 (Clue)
    start_final_crossfade = Signal()                     # Kích hoạt hiệu ứng đổi nền Xanh -> Đỏ sau 15s
    play_sound_event = Signal(str)                       # Key âm thanh: "fill", "daily_double", "think_30s", "timeout", "correct", "wrong", "category_intro"
    update_theme_config = Signal(dict)                   # Đẩy cấu hình XML/Bezel/Texture/Logo sang TV Display
    reload_theme_config = Signal()                       # Buộc TV Display đọc lại toàn bộ config/assets từ disk

    # --- Tín hiệu Màn hình Chờ (Standby Engine) ---
    trigger_standby_mode = Signal(str)                   # "normal" | "mosaic" | "off"

    # --- Tín hiệu Chuông & Đếm giờ 5s (Buzzer & Host Timer) ---
    trigger_buzzer_press = Signal(str)                   # player_id ("p1", "p2", "p3")
    trigger_buzzer_reset = Signal()                      # Mở khóa toàn bộ chuông
    trigger_host_timer_5s = Signal(str)                  # "start" | "stop" | "reset"

    # --- Tín hiệu Điều khiển Phát sóng 2 Nhịp & Đáp án ---
    trigger_clue_zoom = Signal(dict)                     # Nhịp 1: Zoom điểm / Daily Double
    trigger_clue_reveal = Signal()                       # Nhịp 2: Mở text câu hỏi
    toggle_tv_answer = Signal(bool, str)                 # (is_visible, answer_text)

    # --- Tín hiệu Quản lý Trận đấu & Reset ---
    reset_game_state = Signal()                          # Xóa sạch điểm và trạng thái câu hỏi về 0

    # --- Tương thích ngược (Backward Compatibility) ---
    players_updated = Signal(dict)                       # Cập nhật danh sách người chơi
    start_think_timer = Signal(int)                      # Bắt đầu đếm ngược suy nghĩ (giây)
    undo_score = Signal()                                # Yêu cầu hoàn tác điểm số gần nhất
    winner_announced = Signal(dict)                      # Thông báo kết quả xếp hạng và giải thưởng
    theme_updated = Signal(dict)                         # Alias của update_theme_config

    def __init__(self):
        super().__init__()
        self.trigger_category_reveal = _CategoryRevealSignal(self._raw_category_reveal)


# Global singleton instance
event_bus = EventBus()

# Connect theme_updated and update_theme_config to each other to guarantee interoperability
event_bus.update_theme_config.connect(lambda data: event_bus.theme_updated.emit(data) if data != getattr(event_bus, "_last_theme", None) else None)

__all__ = ["EventBus", "event_bus"]
