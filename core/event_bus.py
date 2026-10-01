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
    """Central decoupled signal dispatcher for the entire system."""

    # --- Điều khiển Gameplay cơ bản ---
    # --- Core Gameplay Control ---
    request_open_question = Signal(int, int, int)       # (round_id, col, row)
    display_question = Signal(dict)                      # Payload câu hỏi chi tiết
    close_question = Signal()                            # Đóng câu hỏi, quay lại bảng
    display_question = Signal(dict)                      # Clue payload
    close_question = Signal()                            # Close clue and return to board
    trigger_daily_double = Signal(str, int)              # (player_id, points)
    modify_score = Signal(str, int, bool)                # (player_id, delta, is_correct)
    score_updated = Signal(dict)                         # {p1: x, p2: y, p3: z}
    change_round = Signal(int)                           # 1: Normal, 2: Double, 3: Final
    change_round = Signal(int)                           # 1: Jeopardy, 2: Double Jeopardy, 3: Final Jeopardy

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
    trigger_category_step = Signal(int, int)      # (action, col_index) 1:Logo, 2:Lộ tên, 3:Trượt tiếp, 4:Về bảng
    toggle_tv_window = Signal(bool)               # True: Mở TV, False: Đóng TV
    set_tv_fullscreen = Signal()                  # Tương đương F11
    set_display_fullscreen_toggle = Signal()             # Tương đương phím F11 (Fullscreen/Windowed toggle)
    # --- Studio Visual FX & Category Intro ---
    trigger_board_blank = Signal()                       # Blank board (bezel and background only)
    trigger_board_fill = Signal()                        # Random board fill reveal animation
    _raw_category_reveal = Signal(dict)                  # Internal signal { "auto": bool, "step": int, "col_index": int }
    trigger_category_next = Signal()                     # Slide left to next column (manual)
    cancel_category_reveal = Signal()                    # Cancel intro and return to board immediately
    trigger_category_reveal_step = Signal(int)           # Step control for category intro (0=Logo, 1=Reveal, 2=NextSlide)
    trigger_category_show_logo = Signal(int)             # Show Logo covering category title (col_index)
    trigger_category_fade_logo = Signal()                # Fade out logo to reveal category title
    trigger_category_slide_next = Signal()               # Slide to next category column
    request_clue_zoom = Signal(dict)                     # Clue payload: trigger point zoom first
    trigger_daily_double_splash = Signal(str)            # Daily Double splash image path
    trigger_category_step = Signal(int, int)             # (action, col_index) 1:Logo, 2:Reveal Title, 3:Next Slide, 4:Return to Board
    toggle_tv_window = Signal(bool)                      # True: Open TV, False: Close TV
    set_tv_fullscreen = Signal()                         # Equivalent to F11
    set_display_fullscreen_toggle = Signal()             # F11 Fullscreen/Windowed toggle

    # --- Final Jeopardy, Sound Engine & Theme ---
    trigger_final_step = Signal(int, dict)               # step: 1 (Logo Splash), 2 (Category), 3 (Clue)
    start_final_crossfade = Signal()                     # Kích hoạt hiệu ứng đổi nền Xanh -> Đỏ sau 15s
    restart_final_timer = Signal()                       # Reset lại 30s Vòng Final, phục hồi nền xanh
    play_sound_event = Signal(str)                       # Key âm thanh: "fill", "daily_double", "think_30s", "timeout", "correct", "wrong", "category_intro"
    update_theme_config = Signal(dict)                   # Đẩy cấu hình XML/Bezel/Texture/Logo sang TV Display
    reload_theme_config = Signal()                       # Buộc TV Display đọc lại toàn bộ config/assets từ disk
    start_final_crossfade = Signal()                     # Trigger Blue -> Red background crossfade at 15s
    restart_final_timer = Signal()                       # Reset 30s Final timer and restore blue background
    play_sound_event = Signal(str)                       # Sound key: "fill", "daily_double", "think_30s", "timeout", "correct", "wrong", "category_intro"
    update_theme_config = Signal(dict)                   # Push XML/Bezel/Texture/Logo config to TV Display
    reload_theme_config = Signal()                       # Force TV Display to reload config/assets from disk

    # --- Tín hiệu Màn hình Chờ (Standby Engine) ---
    # --- Standby Screen Engine ---
    trigger_standby_mode = Signal(str)                   # "normal" | "mosaic" | "off"

    # --- Tín hiệu Chuông & Đếm giờ 5s (Buzzer & Host Timer) ---
    # --- Buzzer & 5s Host Timer ---
    trigger_buzzer_press = Signal(str)                   # player_id ("p1", "p2", "p3")
    trigger_buzzer_reset = Signal()                      # Mở khóa toàn bộ chuông
    trigger_buzzer_reset = Signal()                      # Unlock all buzzers
    trigger_host_timer_5s = Signal(str)                  # "start" | "stop" | "reset"

    # --- Tín hiệu Điều khiển Phát sóng 2 Nhịp & Đáp án ---
    trigger_clue_zoom = Signal(dict)                     # Nhịp 1: Zoom điểm / Daily Double
    trigger_clue_reveal = Signal()                       # Nhịp 2: Mở text câu hỏi
    # --- 2-Stage Broadcast & Answer Reveal ---
    trigger_clue_zoom = Signal(dict)                     # Stage 1: Zoom point tile / Daily Double
    trigger_clue_reveal = Signal()                       # Stage 2: Reveal clue question text
    toggle_tv_answer = Signal(bool, str)                 # (is_visible, answer_text)

    # --- Tín hiệu Quản lý Trận đấu & Reset ---
    reset_game_state = Signal()                          # Xóa sạch điểm và trạng thái câu hỏi về 0
    # --- Match Management & Reset ---
    reset_game_state = Signal()                          # Reset all scores and questions to 0
    submit_final_wagers = Signal(dict)                   # {"p1": int, "p2": int, "p3": int}
    unlock_round = Signal(int)                           # Mở khóa vòng tiếp theo (2 hoặc 3)
    sync_categories_to_tv = Signal(list)                 # Danh sách chính xác 6 chủ đề
    sync_board_state_to_tv = Signal(list)                # Danh sách trạng thái các ô (col, row, points, is_used)
    unlock_round = Signal(int)                           # Unlock next round (2 or 3)
    sync_categories_to_tv = Signal(list)                 # List of active categories
    sync_board_state_to_tv = Signal(list)                # Board grid state (col, row, points, is_used)
    set_performance_profile = Signal(str)                # "basic" | "smooth" | "ultra"
    set_buzzer_lockout = Signal(bool)                    # True: Khóa toàn bộ chuông, False: Mở sẵn sàng
    set_buzzer_lockout = Signal(bool)                    # True: Lock all buzzers, False: Buzzers ready
    trigger_final_contestant_reveal = Signal(str, str, int)  # (player_id, response_text, wager_amount)

    # --- Tương thích ngược (Backward Compatibility) ---
    players_updated = Signal(dict)                       # Cập nhật danh sách người chơi
    start_think_timer = Signal(int)                      # Bắt đầu đếm ngược suy nghĩ (giây)
    undo_score = Signal()                                # Yêu cầu hoàn tác điểm số gần nhất
    winner_announced = Signal(dict)                      # Thông báo kết quả xếp hạng và giải thưởng
    theme_updated = Signal(dict)                         # Alias của update_theme_config
    # --- Backward Compatibility ---
    players_updated = Signal(dict)                       # Player list update
    start_think_timer = Signal(int)                      # Start think countdown (seconds)
    undo_score = Signal()                                # Undo last score modification
    winner_announced = Signal(dict)                      # Winner announcement and standings
    theme_updated = Signal(dict)                         # Alias of update_theme_config

    def __init__(self):
        super().__init__()
        self.trigger_category_reveal = _CategoryRevealSignal(self._raw_category_reveal)


# Global singleton instance
event_bus = EventBus()

# Connect theme_updated and update_theme_config to each other to guarantee interoperability
event_bus.update_theme_config.connect(lambda data: event_bus.theme_updated.emit(data) if data != getattr(event_bus, "_last_theme", None) else None)
event_bus.set_tv_fullscreen.connect(event_bus.set_display_fullscreen_toggle.emit)
event_bus.set_display_fullscreen_toggle.connect(lambda: None)  # Ensure slot exists

__all__ = ["EventBus", "event_bus"]
