"""Open-J: Scoring Engine & Wager Validation Subsystem.
Computes real-time scores, validates Daily Double & Final Jeopardy wagers,
enforces question phrasing rules (warning in Round 1 vs automatic penalty in Round 2),
tracks action history for host undo, and calculates official prize payouts ($3,000 for 2nd, $2,000 for 3rd).
"""

from typing import Dict, List, Optional, Tuple, Any
from PySide6.QtCore import QObject, Signal


class ScoreEngine(QObject):
    """Real-time score computation, wager validation, and rule enforcement engine."""

    # Qt Signals for UI and event bus decoupling
    score_updated = Signal(dict)                      # {player_id: current_score}
    score_delta_applied = Signal(str, int, bool)     # (player_id, delta, is_correct)
    wager_validated = Signal(str, int, str)          # (player_id, wager_amount, wager_type)
    phrasing_warning_issued = Signal(str, str)       # (player_id, warning_message)
    player_eliminated = Signal(str, int)             # (player_id, final_score)

    def __init__(self, player_names: Optional[List[str]] = None):
        super().__init__()
        if player_names is None:
            player_names = ["Ken Jennings", "Gold Ship", "Agnes Tachyon"]

        # Contestant dictionary: "p1": {"name": ..., "score": ...}
        self.players: Dict[str, Dict[str, Any]] = {}
        for idx, name in enumerate(player_names):
            p_id = f"p{idx+1}"
            self.players[p_id] = {
                "name": name,
                "score": 0
            }

        # Phrasing warnings per player (for Round 1 grace period)
        self.phrasing_warnings: Dict[str, int] = {p_id: 0 for p_id in self.players}
        # Wagers stored for Daily Double or Final Jeopardy: {p_id: wager}
        self.wagers: Dict[str, int] = {p_id: 0 for p_id in self.players}
        # History stack for undo support
        self.history: List[Dict[str, Any]] = []
        # Eliminated players list
        self.eliminated_players: List[str] = []

    def _resolve_pid(self, player_id_or_name: str) -> Optional[str]:
        """Resolves either 'p1' or player name to the canonical player id ('p1', 'p2', ...)."""
        if player_id_or_name in self.players:
            return player_id_or_name
        for p_id, data in self.players.items():
            if data["name"].strip().lower() == player_id_or_name.strip().lower():
                return p_id
        return None

    def get_all_scores(self) -> Dict[str, int]:
        """Returns summary dictionary of all contestants' current scores: {p_id: score}."""
        return {p_id: data["score"] for p_id, data in self.players.items()}

    def get_scores(self) -> Dict[str, int]:
        """Returns summary dictionary of current scores."""
        return self.get_all_scores()

    def get_score(self, player_id: str) -> int:
        """Returns current score for a specific player."""
        pid = self._resolve_pid(player_id)
        if pid and pid in self.players:
            return self.players[pid]["score"]
        return 0

    def get_player_info(self, player_id: str) -> Optional[Dict[str, Any]]:
        pid = self._resolve_pid(player_id)
        return self.players.get(pid) if pid else None

    def set_score(self, player_id: str, new_score: int):
        """Directly sets player score and emits update signal."""
        pid = self._resolve_pid(player_id)
        if pid and pid in self.players:
            old_score = self.players[pid]["score"]
            delta = new_score - old_score
            self.players[pid]["score"] = new_score
            self.history.append({"action": "SET", "player_id": pid, "old_score": old_score, "new_score": new_score})
            self.score_delta_applied.emit(pid, delta, delta >= 0)
            self.score_updated.emit(self.get_all_scores())

    def add_correct(self, player_id: str, points: int) -> Optional[int]:
        """Adds points for a correct response and records undo history."""
        pid = self._resolve_pid(player_id)
        if pid and pid in self.players:
            self.players[pid]["score"] += points
            self.history.append({"action": "CORRECT", "player_id": pid, "points": points})
            self.score_delta_applied.emit(pid, points, True)
            self.score_updated.emit(self.get_all_scores())
            return self.players[pid]["score"]
        return None

    def add_incorrect(self, player_id: str, points: int) -> Optional[int]:
        """Deducts points for an incorrect response / timeout and records undo history."""
        pid = self._resolve_pid(player_id)
        if pid and pid in self.players:
            self.players[pid]["score"] -= points
            self.history.append({"action": "INCORRECT", "player_id": pid, "points": points})
            self.score_delta_applied.emit(pid, -points, False)
            self.score_updated.emit(self.get_all_scores())
            return self.players[pid]["score"]
        return None

    def apply_wager(self, player_id: str, wager_amount: int, is_correct: bool) -> Optional[int]:
        """Processes wager payout for Daily Double or Final Jeopardy."""
        if is_correct:
            return self.add_correct(player_id, wager_amount)
        else:
            return self.add_incorrect(player_id, wager_amount)

    def undo_last_action(self) -> bool:
        """Reverts the most recent scoring action."""
        if not self.history:
            return False

        last = self.history.pop()
        pid = last["player_id"]
        action = last["action"]

        if action == "CORRECT":
            self.players[pid]["score"] -= last["points"]
        elif action == "INCORRECT":
            self.players[pid]["score"] += last["points"]
        elif action == "SET":
            self.players[pid]["score"] = last["old_score"]

        self.score_updated.emit(self.get_all_scores())
        return True

    def reset_scores(self, initial_score: int = 0):
        """Resets all contestant balances and history."""
        for p_id in self.players:
            self.players[p_id]["score"] = initial_score
        self.phrasing_warnings = {p_id: 0 for p_id in self.players}
        self.wagers = {p_id: 0 for p_id in self.players}
        self.history.clear()
        self.eliminated_players.clear()
        self.score_updated.emit(self.get_all_scores())

    def validate_phrasing(self, response_text: str, round_id: int, is_daily_double: bool, player_id: str) -> Tuple[bool, bool, str]:
        """Validates if contestant response is properly phrased in the form of a question.
        Returns:
            (is_phrased_as_question, should_penalize, message)
        Rules:
            - Must start with or contain question phrasing: "What is", "Who is", etc.
            - Round 1 (Jeopardy): First offense gets a warning without score penalty. Subsequent offenses penalized.
            - Round 2 (Double Jeopardy) or Daily Double: Automatic penalty (no warning).
        """
        pid = self._resolve_pid(player_id) or player_id
        cleaned = response_text.strip().lower()
        question_starters = (
            "what is", "what are", "who is", "who are",
            "where is", "where are", "when was", "when is",
            "what's", "who's", "where's", "which is"
        )
        is_question = any(cleaned.startswith(qs) for qs in question_starters) or cleaned.endswith("?")

        if is_question:
            return True, False, "Valid question phrasing."

        # Improper phrasing handling
        if round_id == 1 and not is_daily_double:
            if self.phrasing_warnings.get(pid, 0) == 0:
                self.phrasing_warnings[pid] = 1
                msg = "Host warning: Response must be in the form of a question! First offense in Round 1 (No penalty)."
                self.phrasing_warning_issued.emit(pid, msg)
                return False, False, msg
            else:
                msg = "Improper phrasing: Repeat offense in Round 1. Automatic penalty applied."
                return False, True, msg
        else:
            msg = f"Improper phrasing: Automatic penalty in Round {round_id} / Daily Double (No warning permitted)."
            return False, True, msg

    def validate_dd_wager(self, player_id: str, wager: int, round_id: int) -> Tuple[bool, str]:
        """Validates Daily Double wager according to official Jeopardy rules (rules.md).
        Round 1: min=5, max=max(score, 1000)
        Round 2: min=5, max=max(score, 2000)
        Supports True Daily Double.
        """
        pid = self._resolve_pid(player_id)
        if not pid or pid not in self.players:
            return False, f"Unknown player: {player_id}"

        score = self.players[pid]["score"]
        min_wager = 5
        ceiling = 1000 if round_id == 1 else 2000
        max_wager = max(score, ceiling)

        if wager < min_wager:
            return False, f"Minimum wager is ${min_wager}. You entered: ${wager}."
        if wager > max_wager:
            return False, f"Maximum wager is ${max_wager:,} (current score=${score:,}, tier ceiling=${ceiling:,}). You entered: ${wager:,}."

        self.wagers[pid] = wager
        self.wager_validated.emit(pid, wager, "Daily Double")
        return True, ""

    def validate_daily_double_wager(self, player_id: str, wager: int, round_id: int) -> Tuple[bool, str]:
        """Alias for validate_dd_wager."""
        return self.validate_dd_wager(player_id, wager, round_id)

    def validate_final_wager(self, player_id: str, wager: int) -> Tuple[bool, str]:
        """Validates Final Jeopardy secret wager according to official rules (rules.md).
        min=0, max=player's entire current score.
        """
        pid = self._resolve_pid(player_id)
        if not pid or pid not in self.players:
            return False, f"Unknown player: {player_id}"

        score = self.players[pid]["score"]
        if score <= 0:
            return False, f"Contestant has ${score} and is eliminated before Final Jeopardy."

        if wager < 0:
            return False, f"Wager cannot be negative. You entered: ${wager}."
        if wager > score:
            return False, f"Maximum wager is the player's available score: ${score:,}. You entered: ${wager:,}."

        self.wagers[pid] = wager
        self.wager_validated.emit(pid, wager, "Final Jeopardy")
        return True, ""

    def validate_final_jeopardy_wager(self, player_id: str, wager: int) -> Tuple[bool, str]:
        """Alias for validate_final_wager."""
        return self.validate_final_wager(player_id, wager)

    def get_final_eligible_players(self) -> List[str]:
        """Filter contestants eligible for Round 3 (score > 0).
        According to official rules: only contestants with positive scores qualify for Final Jeopardy.
        Returns list of player_ids (e.g. ['p1', 'p3']).
        """
        eligible = []
        for p_id, data in self.players.items():
            if data["score"] > 0:
                eligible.append(p_id)
            else:
                self.eliminated_players.append(p_id)
                self.player_eliminated.emit(p_id, data["score"])
        return eligible

    def filter_final_jeopardy_qualifiers(self) -> List[str]:
        """Alias for get_final_eligible_players."""
        return self.get_final_eligible_players()

    def get_lowest_scorer(self) -> str:
        """Returns the contestant ID with the lowest score at the end of Round 1.
        Under Jeopardy rules, this player selects the first clue in Double Jeopardy.
        """
        if not self.players:
            return "p1"
        return min(self.players.items(), key=lambda item: item[1]["score"])[0]

    def calculate_final_payouts(self) -> Dict[str, Dict[str, Any]]:
        """Calculates final game prizes according to official Jeopardy rules:
        - 1st Place: Retains 100% of accumulated cash total.
        - 2nd Place: Fixed consolation prize of $3,000.
        - 3rd Place: Fixed consolation prize of $2,000.
        """
        sorted_players = sorted(self.players.items(), key=lambda item: item[1]["score"], reverse=True)
        results = {}

        for rank, (p_id, data) in enumerate(sorted_players, start=1):
            score = data["score"]
            name = data["name"]

            if rank == 1:
                payout = max(0, score)
                title = "Champion"
            elif rank == 2:
                payout = 3000
                title = "2nd Place"
            else:
                payout = 2000
                title = "3rd Place"

            results[p_id] = {
                "rank": rank,
                "name": name,
                "title": title,
                "final_score": score,
                "payout": payout
            }

        return results
