import sys
from PySide6.QtCore import QCoreApplication
from core.question_core import QuestionEngine
from core.score_core import ScoreEngine
from core.core_eventbus import event_bus

# 1. Hàm khởi tạo các Engine lõi
def setup_engines():
    """Khởi tạo các thành phần Core và nạp dữ liệu mẫu"""
    q_engine = QuestionEngine()
    q_engine.seed_sample_data(force_reset=False)
    
    s_engine = ScoreEngine(["Ken Jennings", "Gold Ship", "Agnes Tachyon"])
    return q_engine, s_engine

# 2. Hàm đăng ký và xử lý các luồng sự kiện (Signal Handlers)
def register_event_handlers(q_engine, s_engine):
    """Liên kết tín hiệu từ EventBus tới logic tương ứng của các Engine"""

    def handle_open_question(round_id, col_index, row_index):
        # Lấy câu hỏi từ Database
        question_data = q_engine.get_question(round_id, col_index, row_index)
        if question_data:
            print(f"\n[MAIN ORCHESTRATOR] Bắn câu hỏi sang màn Studio:")
            print(f"- {question_data['category_name']} (${question_data['points']}): {question_data['question_text']}")
            # Phát tín hiệu mang dữ liệu câu hỏi đi
            event_bus.display_question.emit(question_data)
        else:
            print("[MAIN ORCHESTRATOR] Không tìm thấy câu hỏi!")

    def handle_modify_score(player_id, points, is_correct):
        # Tính toán điểm
        if is_correct:
            new_score = s_engine.add_correct(player_id, points)
        else:
            new_score = s_engine.add_incorrect(player_id, points)
        
        # Bắn cập nhật bảng điểm toàn bộ hệ thống
        all_scores = s_engine.get_all_scores()
        print(f"\n[MAIN ORCHESTRATOR] Điểm số cập nhật: {all_scores}")
        event_bus.score_updated.emit(all_scores)

    # Đăng ký hàm xử lý vào EventBus
    event_bus.request_open_question.connect(handle_open_question)
    event_bus.modify_score.connect(handle_modify_score)

# 3. Hàm chạy kịch bản thử nghiệm (Test Script)
def run_simulation():
    """Giả lập luồng hoạt động mà chưa cần bật UI"""
    print("=== CHẠY MÔ PHỎNG GAMEPLAY QUA MAIN.PY ===")
    
    # Giả lập: Host chọn câu hỏi Round 1, Cột 0, Hàng 0
    event_bus.request_open_question.emit(1, 0, 0)

    # Giả lập: Ken Jennings (p1) trả lời đúng câu 200 điểm
    event_bus.modify_score.emit("p1", 200, True)

    # Giả lập: Gold Ship (p2) bấm chuông trả lời sai câu 400 điểm
    event_bus.modify_score.emit("p2", 400, False)

# 4. Hàm chính khởi chạy ứng dụng
def main():
    # Khởi tạo QCoreApplication (chưa cần GUI) để EventBus xử lý Signal/Slot
    app = QCoreApplication(sys.argv)

    # Khởi tạo lõi
    q_engine, s_engine = setup_engines()

    # Nối dây các hàm sự kiện
    register_event_handlers(q_engine, s_engine)

    # Chạy thử luồng nghiệp vụ
    run_simulation()

if __name__ == "__main__":
    main()