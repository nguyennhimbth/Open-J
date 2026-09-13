from PySide6.QtCore import QObject, Signal

class EventBus(QObject):
    """Trạm trung chuyển tín hiệu toàn hệ thống (Decoupled Event Bus)"""

    # Tín hiệu điều khiển câu hỏi
    request_open_question = Signal(int, int, int)
    display_question = Signal(dict)
    close_question = Signal()
    trigger_daily_double = Signal(str, int)

    # Tín hiệu điểm số
    modify_score = Signal(str, int, bool)
    score_updated = Signal(dict)

    # Tín hiệu chuyển vòng
    change_round = Signal(int)

# Khởi tạo instance dùng chung
event_bus = EventBus()