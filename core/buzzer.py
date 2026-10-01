"""Open-J: Buzzer Signaling Coordinator Subsystem.
Enforces the mandatory 0.25-second early ring lockout penalty,
tracks contestant signaling states, and coordinates the 5-second response countdown.
"""

import time
from typing import Dict, List, Optional, Set
from PySide6.QtCore import QObject, Signal, QTimer


class BuzzerCoordinator(QObject):
    """Coordinates contestant buzzers, lockout penalties, and response timers."""

    # Qt Signals for UI and network synchronization
    buzzer_unlocked = Signal()                             # Host finished reading; buzzers active
    buzzer_locked = Signal()                               # Buzzers disabled
    contestant_buzzed = Signal(str, float)                 # (player_id, reaction_timestamp)
    early_buzz_penalty = Signal(str, float)                # (player_id, lockout_duration_seconds)
    response_countdown_tick = Signal(int)                  # Remaining response seconds (5 -> 0)
    response_timeout = Signal(str)                         # (player_id) failed to respond in 5s
    all_contestants_exhausted = Signal()                   # All contestants attempted and failed

    EARLY_LOCKOUT_PENALTY_SEC: float = 0.25                # Mandatory 0.25s penalty
    RESPONSE_TIME_LIMIT_SEC: int = 5                       # 5-second response window

    def __init__(self, contestants: Optional[List[str]] = None):
        super().__init__()
        self.contestants = contestants if contestants else ["Contestant 1", "Contestant 2", "Contestant 3"]
        
        # State flags
        self.is_unlocked: bool = False
        self.active_buzzed_player: Optional[str] = None
        self.unlock_timestamp: float = 0.0

        # Lockout penalties: player -> timestamp until which they cannot buzz
        self.lockouts: Dict[str, float] = {p: 0.0 for p in self.contestants}

        # Contestants who have already attempted this clue and failed
        self.failed_contestants: Set[str] = set()

        # 5-second countdown timer
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_timer_tick)
        self._remaining_seconds: int = self.RESPONSE_TIME_LIMIT_SEC

    def reset_for_new_clue(self):
        """Prepares buzzer coordinator for a fresh clue."""
        self._timer.stop()
        self.is_unlocked = False
        self.active_buzzed_player = None
        self.unlock_timestamp = 0.0
        self.lockouts = {p: 0.0 for p in self.contestants}
        self.failed_contestants.clear()
        self._remaining_seconds = self.RESPONSE_TIME_LIMIT_SEC
        self.buzzer_locked.emit()

    def unlock_buzzer(self):
        """Called by host when clue reading is complete. Enables contestant signaling."""
        self.is_unlocked = True
        self.unlock_timestamp = time.time()
        self.active_buzzed_player = None
        self._remaining_seconds = self.RESPONSE_TIME_LIMIT_SEC

        # Any player who buzzed early during reading gets penalized 0.25s starting NOW
        for p in self.contestants:
            if self.lockouts.get(p, 0.0) > 0.0:
                # Extend penalty 0.25s into the active window
                self.lockouts[p] = self.unlock_timestamp + self.EARLY_LOCKOUT_PENALTY_SEC
                self.early_buzz_penalty.emit(p, self.EARLY_LOCKOUT_PENALTY_SEC)

        self.buzzer_unlocked.emit()

    def lock_buzzer(self):
        """Immediately locks signaling for all contestants."""
        self.is_unlocked = False
        self._timer.stop()
        self.buzzer_locked.emit()

    def attempt_buzz(self, player_id: str) -> bool:
        """Processes a ring-in attempt from a contestant.
        Returns:
            True if buzz was accepted; False if locked or penalized.
        """
        now = time.time()

        # Check if player already failed this clue
        if player_id in self.failed_contestants:
            return False

        # If a contestant is already recognized and answering, ignore others
        if self.active_buzzed_player is not None:
            return False

        # Early Ring Rule: If buzzers are NOT unlocked, penalize 0.25 seconds!
        if not self.is_unlocked:
            self.lockouts[player_id] = now + self.EARLY_LOCKOUT_PENALTY_SEC
            self.early_buzz_penalty.emit(player_id, self.EARLY_LOCKOUT_PENALTY_SEC)
            print(f"[Buzzer] Early ring by {player_id}! 0.25s lockout penalty applied.")
            return False

        # Check if player is currently serving an early ring lockout penalty
        if now < self.lockouts.get(player_id, 0.0):
            penalty_left = round(self.lockouts[player_id] - now, 3)
            print(f"[Buzzer] Ring rejected for {player_id}: serving lockout penalty ({penalty_left}s remaining).")
            return False

        # Accepted buzz!
        self.active_buzzed_player = player_id
        self._remaining_seconds = self.RESPONSE_TIME_LIMIT_SEC
        self._timer.start()

        self.contestant_buzzed.emit(player_id, now)
        self.response_countdown_tick.emit(self._remaining_seconds)
        print(f"[Buzzer] Accepted buzz from {player_id}! Starting 5s countdown.")
        return True

    def mark_response_incorrect(self, player_id: str):
        """Called when recognized contestant answers incorrectly or host rules against."""
        self._timer.stop()
        self.failed_contestants.add(player_id)
        self.active_buzzed_player = None

        # Check if any eligible contestants remain
        eligible = [p for p in self.contestants if p not in self.failed_contestants]
        if not eligible:
            print("[Buzzer] All contestants failed or attempted. Clue exhausted.")
            self.lock_buzzer()
            self.all_contestants_exhausted.emit()
        else:
            # Reopen buzzer for remaining contestants
            print(f"[Buzzer] Reopening buzzer for remaining contestants: {eligible}")
            self.unlock_buzzer()

    def mark_response_correct(self, player_id: str):
        """Called when contestant responds correctly. Closes clue interaction."""
        self._timer.stop()
        self.lock_buzzer()

    def _on_timer_tick(self):
        """Fires every 1 second during active contestant response window."""
        self._remaining_seconds -= 1
        self.response_countdown_tick.emit(self._remaining_seconds)

        if self._remaining_seconds <= 0:
            self._timer.stop()
            player = self.active_buzzed_player
            if player:
                print(f"[Buzzer] Response timed out for {player}!")
                self.response_timeout.emit(player)
                self.mark_response_incorrect(player)
