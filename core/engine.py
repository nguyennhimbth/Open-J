"""Open-J: Central Game Orchestration Engine & Finite State Machine (FSM).
Coordinates all game phases: WAITBOARD, BOARD_REVEAL, CLUE_ACTIVE,
DAILY_DOUBLE, FINAL_JEOPARDY, TIEBREAKER, and GAME_OVER.
"""

from enum import Enum, auto
from typing import Dict, List, Optional, Any
from PySide6.QtCore import QObject, Signal

from core.scoring import ScoreEngine
from core.buzzer import BuzzerCoordinator
from core.questions import QuestionEngine
from data.history import HistoryManager


class GamePhase(Enum):
    """Enumeration of all broadcast game phases and state transitions."""
    WAITBOARD = auto()                 # Static cosmic Earth wallpaper
    WAITBOARD_MOSAIC = auto()          # 64-TV bezel mosaic wall layout
    BOARD_REVEAL = auto()              # Dynamic random tile flipping animation
    CATEGORY_INTRO = auto()            # Category splash cards (90% centered, logo fade & slide)
    BOARD_ACTIVE = auto()              # Main 6x5 matrix interactive selection
    PRE_QUESTION = auto()              # Centered monetary value card ($200-$1,000 / $400-$2,000)
    DAILY_DOUBLE = auto()              # Signature stager graphic with 3D horizontal flip & wager input
    CLUE_ACTIVE = auto()               # In-play clue screen on royal blue with buzzers & 5s timer
    FINAL_JEOPARDY_CATEGORY = auto()   # Final Jeopardy category reveal & secret wager input
    FINAL_JEOPARDY_CLUE = auto()       # Clue on royal blue with 30s timer shifting to crimson at 15s
    FINAL_JEOPARDY_REVEAL = auto()     # Sequential reveal of responses and wagers (3rd -> 1st)
    TIEBREAKER = auto()                # Sudden-death tiebreaker clue if tie for 1st place
    GAME_OVER = auto()                 # Podium results, champion declaration & consolation payouts


class GameEngine(QObject):
    """Central Finite State Machine (FSM) orchestrating the quiz show lifecycle."""

    # Qt Signals for phase changes and UI synchronization
    phase_changed = Signal(object, object)             # (old_phase, new_phase)
    match_completed = Signal(dict)                     # final payout results
    tiebreaker_triggered = Signal(dict)                # tiebreaker clue payload

    def __init__(
        self,
        question_engine: Optional[QuestionEngine] = None,
        score_engine: Optional[ScoreEngine] = None,
        buzzer_coordinator: Optional[BuzzerCoordinator] = None,
        history_manager: Optional[HistoryManager] = None
    ):
        super().__init__()
        self.q_engine = question_engine if question_engine else QuestionEngine()
        self.s_engine = score_engine if score_engine else ScoreEngine()
        self.buzzer = buzzer_coordinator if buzzer_coordinator else BuzzerCoordinator(self.s_engine.players)
        self.history = history_manager if history_manager else HistoryManager()

        self.current_phase: GamePhase = GamePhase.WAITBOARD
        self.is_mosaic_waitboard: bool = False
        self.current_match_id: Optional[int] = None

        # Connect internal coordinators
        self._wire_signals()

    def _wire_signals(self):
        """Connects signals between coordinators."""
        self.buzzer.response_timeout.connect(self._on_buzzer_timeout)
        self.buzzer.all_contestants_exhausted.connect(self._on_all_contestants_failed)

    def transition_to(self, new_phase: GamePhase) -> bool:
        """Executes state transition in the FSM."""
        old_phase = self.current_phase
        if old_phase == new_phase:
            return True

        self.current_phase = new_phase
        print(f"[GameEngine FSM] Phase Transition: {old_phase.name} -> {new_phase.name}")
        self.phase_changed.emit(old_phase, new_phase)
        return True

    # --- Phase Trigger Shortcuts ---

    def start_waitboard(self, mosaic: bool = False):
        """Sets standby waitboard screen (static or 64-TV bezel mosaic)."""
        self.is_mosaic_waitboard = mosaic
        self.transition_to(GamePhase.WAITBOARD_MOSAIC if mosaic else GamePhase.WAITBOARD)

    def trigger_board_reveal(self):
        """Initiates dynamic random tile reveal across the 6x5 matrix."""
        self.transition_to(GamePhase.BOARD_REVEAL)

    def trigger_category_intro(self):
        """Starts 6-category sequential splash introduction."""
        self.transition_to(GamePhase.CATEGORY_INTRO)

    def enter_board_active(self):
        """Activates main board for clue selection."""
        self.transition_to(GamePhase.BOARD_ACTIVE)

    def select_clue(self, col: int, row: int):
        """Processes clue selection from board."""
        clue = self.q_engine.select_clue(col, row)
        if not clue:
            return

        if clue.get("is_daily_double", False):
            self.transition_to(GamePhase.DAILY_DOUBLE)
        else:
            self.transition_to(GamePhase.PRE_QUESTION)

    def show_clue_screen(self):
        """Transitions to in-play clue screen and resets buzzer coordinator."""
        self.buzzer.reset_for_new_clue()
        self.transition_to(GamePhase.CLUE_ACTIVE)

    def unlock_buzzers(self):
        """Host finished reading; activates buzzers for contestants."""
        if self.current_phase == GamePhase.CLUE_ACTIVE:
            self.buzzer.unlock_buzzer()

    def close_clue_and_return_to_board(self):
        """Closes active clue and returns to the main board."""
        self.buzzer.lock_buzzer()
        self.q_engine.close_current_clue()

        # Check if round is over
        if self.q_engine.is_board_cleared():
            current_r = self.q_engine.current_round_id
            if current_r == 1:
                # Advance to Double Jeopardy!
                print("[GameEngine] Round 1 complete. Preparing Double Jeopardy!...")
                self.q_engine.advance_to_next_round()
                # Under official rules, lowest scorer selects first in Double Jeopardy
                first_picker = self.s_engine.get_lowest_scorer()
                print(f"[GameEngine] Double Jeopardy: lowest scorer '{first_picker}' selects first clue.")
                self.transition_to(GamePhase.BOARD_REVEAL)
            elif current_r == 2:
                # Advance to Final Jeopardy!
                print("[GameEngine] Round 2 complete. Qualifying contestants for Final Jeopardy!...")
                self.enter_final_jeopardy()
        else:
            self.transition_to(GamePhase.BOARD_ACTIVE)

    def enter_final_jeopardy(self):
        """Transitions into Final Jeopardy. Filters eligible contestants (score > 0)."""
        qualifiers = self.s_engine.filter_final_jeopardy_qualifiers()
        print(f"[GameEngine] Contestants qualifying for Final Jeopardy: {qualifiers}")
        self.q_engine.load_round(3)
        self.transition_to(GamePhase.FINAL_JEOPARDY_CATEGORY)

    def start_final_jeopardy_clue(self):
        """Reveals Final Jeopardy clue and starts 30s timer."""
        self.transition_to(GamePhase.FINAL_JEOPARDY_CLUE)

    def enter_final_jeopardy_reveal(self):
        """Sequential reveal of contestant wagers and responses."""
        self.transition_to(GamePhase.FINAL_JEOPARDY_REVEAL)

    def complete_match_and_determine_winner(self):
        """Finalizes match, verifies if tiebreaker is required, and applies prize payouts."""
        scores = self.s_engine.get_scores()
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        if not sorted_scores:
            self.transition_to(GamePhase.GAME_OVER)
            return

        top_score = sorted_scores[0][1]
        tied_first_place = [p for p, s in sorted_scores if s == top_score and s > 0]

        # Regular games cannot end in a tie for 1st place!
        if len(tied_first_place) > 1:
            print(f"[GameEngine] Tie for 1st place between: {tied_first_place}! Triggering Tiebreaker Clue...")
            tb_clue = self.q_engine.db.get_tiebreaker_clue()
            if tb_clue:
                self.q_engine.load_round(4)
                self.transition_to(GamePhase.TIEBREAKER)
                self.tiebreaker_triggered.emit(tb_clue)
                return
            else:
                print("[GameEngine] No tiebreaker clue available in database. Proceeding to co-champions payout.")

        # Conclude match and record in database history
        payouts = self.s_engine.calculate_final_payouts()
        winner_name = sorted_scores[0][0]
        match_id = self.history.record_match_completion(scores, winner_name=winner_name)
        self.current_match_id = match_id

        self.transition_to(GamePhase.GAME_OVER)
        self.match_completed.emit(payouts)

    def _on_buzzer_timeout(self, player_id: str):
        """Contestant timed out on 5-second response."""
        clue = self.q_engine.current_clue
        points = clue.get("points", 0) if clue else 0
        self.s_engine.apply_clue_result(player_id, points, is_correct=False)

    def _on_all_contestants_failed(self):
        """All contestants failed or passed on this clue."""
        print("[GameEngine] All contestants failed on this clue. Host reveals correct response.")
