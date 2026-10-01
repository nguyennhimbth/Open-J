"""Open-J: Question & Clue Management Engine.
Handles clue selection, category tracking, "Forrest Bounce" non-linear board navigation,
round transitions, Daily Double positions, session snapshot freezing, and tiebreaker handling.
"""

from typing import Dict, List, Optional, Any, Tuple
from PySide6.QtCore import QObject, Signal

from data.db import DatabaseManager
from data.models import ClueModel, CategoryModel


class QuestionEngine(QObject):
    """Manages board state, clue lookups, session snapshots, and round transitions."""

    # Qt Signals
    categories_loaded = Signal(list)                   # List of 6 category titles
    clue_selected = Signal(dict)                       # Clue payload dictionary
    clue_closed = Signal(int, int)                     # (col_index, row_index)
    round_changed = Signal(int)                        # 1: Jeopardy, 2: Double Jeopardy, 3: Final, 4: Tiebreaker
    board_completed = Signal(int)                      # (round_id) when all 30 clues cleared

    def __init__(self, db_path: str = "data/questions.db", db: Optional[DatabaseManager] = None):
        super().__init__()
        self.db = db if db else DatabaseManager(db_path)
        self.current_round_id: int = 1
        self.active_categories: List[str] = []
        self.board_clues: Dict[Tuple[int, int], Dict[str, Any]] = {}  # (col, row) -> clue dict
        self.current_clue: Optional[Dict[str, Any]] = None
        self.final_clue: Optional[Dict[str, Any]] = None
        self.tiebreaker_clue: Optional[Dict[str, Any]] = None

        # Session freezing snapshot storage
        self.session_locked: bool = False
        self.session_data: Dict[int, Dict[str, Any]] = {}

        # Load initial round
        self.load_round(1)

    def load_round(self, round_id: int):
        """Loads categories and clues for the given round (1: Jeopardy, 2: Double, 3: Final, 4: Tiebreaker)."""
        self.current_round_id = round_id
        self.board_clues.clear()
        self.current_clue = None

        if round_id in (1, 2):
            raw_clues = self.db.get_board_clues(round_id)
            self.active_categories = self.db.get_categories_for_round(round_id)

            for c in raw_clues:
                col = c["col_index"]
                row = c["row_index"]
                self.board_clues[(col, row)] = c

            print(f"[QuestionEngine] Loaded Round {round_id} with {len(self.active_categories)} categories and {len(self.board_clues)} clues.")
            self.categories_loaded.emit(self.active_categories)

        elif round_id == 3:
            # Final Jeopardy
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                SELECT cl.id, cl.round_id, 0 as col_index, 0 as row_index,
                       cat.name as category_name, 0 as points,
                       cl.clue_text as question_text, cl.answer_text,
                       cl.asset_filename, 0 as is_daily_double, cl.is_used, 1 as is_ongame
                FROM clues cl
                JOIN categories cat ON cl.category_id = cat.id
                WHERE cl.round_id = 3 AND cl.is_ongame = 1
                LIMIT 1
                """)
                row = cur.fetchone()
                if row:
                    self.final_clue = dict(row)
                    self.active_categories = [self.final_clue["category_name"]]
                    self.current_clue = self.final_clue
                else:
                    self.final_clue = None

            print(f"[QuestionEngine] Loaded Final Jeopardy: {self.active_categories}")
            self.categories_loaded.emit(self.active_categories)

        elif round_id == 4:
            # Tiebreaker
            self.tiebreaker_clue = self.db.get_tiebreaker_clue()
            if self.tiebreaker_clue:
                self.active_categories = [self.tiebreaker_clue["category_name"]]
                self.current_clue = self.tiebreaker_clue
                print(f"[QuestionEngine] Loaded Tiebreaker: {self.tiebreaker_clue['category_name']}")
                self.categories_loaded.emit(self.active_categories)
            else:
                print("[QuestionEngine] No tiebreaker clues found in database.")

        self.round_changed.emit(round_id)

    # =========================================================================
    # BOARD LOOKUP METHODS (HOST CONTROLLER & BROADCAST COMPATIBILITY)
    # =========================================================================

    def get_board_by_round(self, round_id: int) -> List[Dict[str, Any]]:
        """Returns board matrix clues for specified round."""
        if round_id == self.current_round_id and self.board_clues:
            return list(self.board_clues.values())
        return self.db.get_board_clues(round_id)

    def get_categories_for_round(self, round_id: int) -> List[str]:
        """Returns category headers for specified round."""
        if round_id == self.current_round_id and self.active_categories:
            return list(self.active_categories)
        return self.db.get_categories_for_round(round_id)

    def get_question(self, round_id: int, col: int, row: int) -> Optional[Dict[str, Any]]:
        """Retrieves clue payload by round, column, and row index."""
        if round_id == self.current_round_id and (col, row) in self.board_clues:
            return self.board_clues[(col, row)]

        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT cl.id, cl.round_id, cl.col_index, cl.row_index,
                   cat.name as category_name, cl.points,
                   cl.clue_text as question_text, cl.answer_text,
                   cl.asset_filename, cl.is_daily_double, cl.is_used, cl.is_ongame
            FROM clues cl
            JOIN categories cat ON cl.category_id = cat.id
            WHERE cl.round_id = ? AND cl.col_index = ? AND cl.row_index = ? AND cl.is_ongame = 1
            LIMIT 1
            """, (round_id, col, row))
            res = cur.fetchone()
            return dict(res) if res else None

    def mark_as_used(self, round_id: int, col: int, row: int):
        """Marks a clue as used in database and memory."""
        key = (col, row)
        if key in self.board_clues:
            self.board_clues[key]["is_used"] = 1
            clue_id = self.board_clues[key].get("id")
            if clue_id:
                self.db.mark_clue_used(clue_id)
        else:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                UPDATE clues SET is_used = 1
                WHERE round_id = ? AND col_index = ? AND row_index = ? AND is_ongame = 1
                """, (round_id, col, row))
                conn.commit()

        self.clue_closed.emit(col, row)

    def reset_all_used(self):
        """Resets all is_used flags in current round."""
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE clues SET is_used = 0 WHERE is_ongame = 1")
            conn.commit()
        for k in self.board_clues:
            self.board_clues[k]["is_used"] = 0

    def is_round_cleared(self, round_id: int) -> bool:
        """Returns True if all active clues in round are marked as used."""
        return self.is_board_cleared()

    def fetch_round_matrix(self, round_id: int) -> Dict[str, Any]:
        """Snapshots full round matrix (categories, board rows, questions map)."""
        categories = self.get_categories_for_round(round_id)
        board_rows = self.get_board_by_round(round_id)
        questions_map = {}
        for row in board_rows:
            c = row["col_index"]
            r = row["row_index"]
            full_q = self.get_question(round_id, c, r)
            if full_q:
                questions_map[(c, r)] = full_q

        return {
            "categories": categories,
            "board": board_rows,
            "questions": questions_map
        }

    def lock_session_data(self, round_id: Optional[int] = None):
        """Freezes session data for round in memory."""
        r_id = round_id if round_id is not None else self.current_round_id
        self.session_data[r_id] = self.fetch_round_matrix(r_id)
        self.session_locked = True

    def reset_session(self):
        """Resets session locks and re-activates game categories from database."""
        self.session_locked = False
        self.session_data.clear()
        self.db.activate_game_categories()
        self.load_round(1)

    # =========================================================================
    # IN-GAME GAMEPLAY LOGIC (FORREST BOUNCE & CLUE LIFECYCLE)
    # =========================================================================

    def select_clue(self, col_index: int, row_index: int) -> Optional[Dict[str, Any]]:
        """Selects a clue on the board ('Forrest Bounce' allows selecting any available clue)."""
        key = (col_index, row_index)
        clue = self.board_clues.get(key)
        if not clue:
            clue = self.get_question(self.current_round_id, col_index, row_index)
            if clue:
                self.board_clues[key] = clue

        if not clue:
            print(f"[QuestionEngine] No clue at ({col_index}, {row_index})")
            return None

        if clue.get("is_used", False):
            print(f"[QuestionEngine] Clue at ({col_index}, {row_index}) already used.")
            return None

        self.current_clue = clue
        self.clue_selected.emit(clue)
        return clue

    def close_current_clue(self):
        """Marks current clue as used and checks if board is completed."""
        if not self.current_clue:
            return

        clue_id = self.current_clue.get("id")
        col = self.current_clue.get("col_index", 0)
        row = self.current_clue.get("row_index", 0)

        self.mark_as_used(self.current_round_id, col, row)
        self.current_clue = None

        if self.is_board_cleared():
            print(f"[QuestionEngine] Board completed for Round {self.current_round_id}!")
            self.board_completed.emit(self.current_round_id)

    def is_board_cleared(self) -> bool:
        """Returns True if all active clues in current round have been used."""
        if not self.board_clues:
            return False
        return all(bool(clue.get("is_used", 0)) for clue in self.board_clues.values())

    def get_remaining_clues_count(self) -> int:
        """Returns number of unplayed clues remaining on the current board."""
        return sum(1 for clue in self.board_clues.values() if not bool(clue.get("is_used", 0)))

    def advance_to_next_round(self) -> int:
        """Transitions forward: Round 1 -> Round 2 -> Round 3 -> Tiebreaker."""
        next_round = self.current_round_id + 1
        if next_round <= 4:
            self.load_round(next_round)
        return self.current_round_id
