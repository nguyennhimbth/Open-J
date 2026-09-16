class ScoreEngine:
    def __init__(self, player_names=None):
        if player_names is None:
            player_names = ["Người chơi 1", "Người chơi 2", "Người chơi 3"]
        
        self.players = {}
        for idx, name in enumerate(player_names):
            p_id = f"p{idx+1}"
            self.players[p_id] = {
                "name": name,
                "score": 0
            }
        self.history = [] # Lưu lịch sử để Undo nếu cần

    def get_all_scores(self):
        """Lấy bảng điểm tổng kết hiện tại"""
        return {p_id: data["score"] for p_id, data in self.players.items()}

    def get_player_info(self, player_id):
        return self.players.get(player_id)

    def add_correct(self, player_id, points):
        """Cộng điểm khi trả lời ĐÚNG"""
        if player_id in self.players:
            self.players[player_id]["score"] += points
            self.history.append({"action": "CORRECT", "player_id": player_id, "points": points})
            return self.players[player_id]["score"]
        return None

    def add_incorrect(self, player_id, points):
        """Trừ điểm khi trả lời SAI (chuẩn luật show, điểm có thể âm)"""
        if player_id in self.players:
            self.players[player_id]["score"] -= points
            self.history.append({"action": "INCORRECT", "player_id": player_id, "points": points})
            return self.players[player_id]["score"]
        return None

    def apply_wager(self, player_id, wager_amount, is_correct):
        """Xử lý điểm cược (Dành cho Daily Double & Final Jeopardy)"""
        if player_id not in self.players:
            return None
        
        if is_correct:
            return self.add_correct(player_id, wager_amount)
        else:
            return self.add_incorrect(player_id, wager_amount)

    def undo_last_action(self):
        """Hoàn tác thao tác cộng/trừ điểm gần nhất nếu Host bấm nhầm"""
        if not self.history:
            return False
        
        last = self.history.pop()
        p_id = last["player_id"]
        pts = last["points"]
        
        if last["action"] == "CORRECT":
            self.players[p_id]["score"] -= pts
        elif last["action"] == "INCORRECT":
            self.players[p_id]["score"] += pts
        return True

    def reset_scores(self):
        """Đặt lại toàn bộ điểm số về 0 và xóa lịch sử undo."""
        for p_id in self.players:
            self.players[p_id]["score"] = 0
        self.history.clear()

# TEST ĐỘC LẬP TẠI TERMINAL
if __name__ == "__main__":
    print("=== TEST NHÂN TÍNH ĐIỂM ===")
    scoring = ScoreEngine(["Ken Jennings", "Gold Ship", "Agnes Tachyon"])
    print("Điểm ban đầu:", scoring.get_all_scores())

    # Ken trả lời đúng câu 400
    scoring.add_correct("p1", 400)
    # Gold Ship bấm chuông trả lời sai câu 600
    scoring.add_incorrect("p2", 600)
    # Tachyon cược Daily Double 1000 điểm và đúng
    scoring.apply_wager("p3", 1000, is_correct=True)

    print("\nĐiểm sau 3 lượt đấu:")
    for p_id, p_data in scoring.players.items():
        print(f"- {p_data['name']}: {p_data['score']} điểm")

    print("\nThử Undo thao tác cuối của Tachyon:")
    scoring.undo_last_action()
    print("Điểm sau khi Undo:", scoring.get_all_scores())