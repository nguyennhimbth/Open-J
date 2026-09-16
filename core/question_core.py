import sqlite3
import os
from pathlib import Path

class QuestionEngine:
    def __init__(self, db_path="data/questions.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Khởi tạo bảng dữ liệu nếu chưa có"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                round_id INTEGER NOT NULL,          -- 1: Normal, 2: Double, 3: Final
                col_index INTEGER NOT NULL,         -- Cột 0 -> 5 (6 chủ đề)
                row_index INTEGER NOT NULL,         -- Hàng 0 -> 5 (6 mức điểm)
                category_name TEXT NOT NULL,       -- Tên chủ đề
                points INTEGER NOT NULL,            -- Giá trị điểm (200, 400,...)
                question_text TEXT NOT NULL,        -- Nội dung câu hỏi
                answer_text TEXT NOT NULL,          -- Đáp án đúng (Chỉ Host thấy)
                asset_filename TEXT DEFAULT '',     -- Tên file ảnh (VD: 'cat1_200.png')
                is_daily_double BOOLEAN DEFAULT 0,  -- 1 nếu là ô cược đôi
                is_used BOOLEAN DEFAULT 0           -- 1 nếu câu hỏi này đã được mở
            )
            """)
            conn.commit()

    def seed_sample_data(self, force_reset=False):
        """Bơm dữ liệu mẫu cho cả 3 vòng chơi. Nếu force_reset=True sẽ làm mới toàn bộ."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if force_reset:
                cursor.execute("DELETE FROM questions")
                conn.commit()

            cursor.execute("SELECT COUNT(*) FROM questions")
            if cursor.fetchone()[0] == 0:
                print("-> Đang nạp dữ liệu mẫu 3 vòng vào DB...")
                sample = [
                    # ROUND 1: Jeopardy (Điểm: 200, 400,...)
                    (1, 0, 0, "Lịch Sử", 200, "Vị vua đầu tiên của nhà Tiền Lý?", "Lý Nam Đế", "ly_nam_de.png", 0),
                    (1, 0, 1, "Lịch Sử", 400, "Chiến thắng Bạch Đằng năm 938 do ai lãnh đạo?", "Ngô Quyền", "", 0),
                    (1, 1, 0, "Khoa Học", 200, "Công thức hóa học của nước là gì?", "H2O", "", 0),
                    (1, 1, 1, "Khoa Học", 400, "Hành tinh nào gần Mặt Trời nhất?", "Sao Thủy (Mercury)", "mercury.png", 1),
                    
                    # ROUND 2: Double Jeopardy (Điểm nhân đôi | 2 ô Daily Double)
                    (2, 0, 0, "Vũ Trụ", 400, "Hành tinh lớn nhất trong Hệ Mặt Trời?", "Sao Mộc (Jupiter)", "", 0),
                    (2, 0, 1, "Vũ Trụ", 800, "Hiện tượng các thiên hà đang dãn nở do ai phát hiện?", "Edwin Hubble", "hubble.png", 1),
                    (2, 1, 0, "Văn Học", 400, "Tác giả của 'Truyện Kiều' là ai?", "Nguyễn Du", "", 0),
                    (2, 1, 1, "Văn Học", 800, "Ai là tác giả của 'Lão Hạc'?", "Nam Cao", "", 1),
                    
                    # ROUND 3: Final Jeopardy (Chỉ 1 chủ đề, 1 manh mối duy nhất)
                    (3, 0, 0, "Toán Học Đỉnh Cao", 0, "1 + 1 bằng mấy?", "2 (nhưng bằng 3 nếu là Haru Urara)", "final_clue.png", 0),
                ]
                cursor.executemany("""
                INSERT INTO questions 
                (round_id, col_index, row_index, category_name, points, question_text, answer_text, asset_filename, is_daily_double)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, sample)
                conn.commit()
                print("-> Nạp dữ liệu 3 vòng thành công!")

    def get_question(self, round_id, col_index, row_index):
        """Lấy thông tin chi tiết câu hỏi theo toạ độ ma trận"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT * FROM questions 
            WHERE round_id = ? AND col_index = ? AND row_index = ?
            """, (round_id, col_index, row_index))
            row = cursor.fetchone()

            if not row:
                return None

            data = dict(row)
            
            # KIỂM TRA FALLBACK ASSET
            asset_file = data.get("asset_filename", "")
            asset_full_path = Path("ui/assets/image") / asset_file if asset_file else None
            
            has_asset = bool(asset_file and asset_full_path.exists())
            data["has_asset"] = has_asset
            data["asset_path"] = str(asset_full_path.resolve()) if has_asset else ""

            return data

    def get_board_by_round(self, round_id):
        """Lấy toàn bộ ma trận câu hỏi của vòng (Dành cho Round 1 và Round 2)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT id, round_id, col_index, row_index, category_name, points, is_used 
            FROM questions 
            WHERE round_id = ? 
            ORDER BY col_index, row_index
            """, (round_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_final_jeopardy(self):
        """Lấy câu hỏi duy nhất của vòng Final Jeopardy (round_id = 3)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT * FROM questions 
            WHERE round_id = 3 
            LIMIT 1
            """)
            row = cursor.fetchone()
            if not row:
                return None
            
            data = dict(row)
            asset_file = data.get("asset_filename", "")
            asset_full_path = Path("ui/assets/image") / asset_file if asset_file else None
            has_asset = bool(asset_file and asset_full_path.exists())
            data["has_asset"] = has_asset
            data["asset_path"] = str(asset_full_path.resolve()) if has_asset else ""
            return data

    def mark_as_used(self, question_id):
        """Đánh dấu câu hỏi đã mở xong"""
        with self._get_connection() as conn:
            conn.cursor().execute("UPDATE questions SET is_used = 1 WHERE id = ?", (question_id,))
            conn.commit()

    def reset_all_used(self):
        """Đặt lại is_used = 0 cho toàn bộ câu hỏi trong CSDL"""
        with self._get_connection() as conn:
            conn.cursor().execute("UPDATE questions SET is_used = 0")
            conn.commit()

# TEST ĐỘC LẬP TẠI TERMINAL
if __name__ == "__main__":
    print("=== DANG CHAY TEST QUESTION CORE (CA 3 VONG) ===")
    engine = QuestionEngine()
    engine.seed_sample_data(force_reset=True)

    # Test Round 1
    q1 = engine.get_question(round_id=1, col_index=0, row_index=0)
    print("\n[Round 1 - Jeopardy]:")
    print(f"- {q1['category_name']} (${q1['points']}): {q1['question_text']}")

    # Test Round 2
    q2 = engine.get_question(round_id=2, col_index=0, row_index=1)
    print("\n[Round 2 - Double Jeopardy]:")
    print(f"- {q2['category_name']} (${q2['points']}) | Daily Double: {bool(q2['is_daily_double'])}")

    # Test Round 3
    q3 = engine.get_final_jeopardy()
    print("\n[Round 3 - Final Jeopardy]:")
    print(f"- Chủ đề: {q3['category_name']}")
    print(f"- Manh mối: {q3['question_text']}")
    print(f"- Đáp án Host: {q3['answer_text']}")