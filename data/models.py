"""Open-J: Data Models & Entities.
Defines ORM / Dataclass structures for Categories, Clues, Rounds,
Daily Double locations, Contestant Profiles, and Match History.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime


@dataclass
class RoundModel:
    """Represents a game round (Jeopardy!, Double Jeopardy!, Final Jeopardy!, Tiebreaker)."""
    id: int
    name: str
    round_number: int
    min_value: int
    max_value: int
    value_step: int
    dd_count: int
    is_active: bool = False

    def get_tier_values(self) -> List[int]:
        """Returns standard clue point tier values for this round."""
        if self.value_step <= 0 or self.min_value <= 0:
            return []
        return list(range(self.min_value, self.max_value + 1, self.value_step))


@dataclass
class ClueModel:
    """Represents a single clue / question on the board."""
    id: Optional[int]
    category_id: int
    round_id: int
    col_index: int
    row_index: int
    points: int
    clue_text: str
    answer_text: str
    asset_filename: str = ""
    is_daily_double: bool = False
    is_used: bool = False
    is_ongame: bool = False
    is_tiebreaker: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "category_id": self.category_id,
            "round_id": self.round_id,
            "col_index": self.col_index,
            "row_index": self.row_index,
            "points": self.points,
            "question_text": self.clue_text,
            "clue_text": self.clue_text,
            "answer_text": self.answer_text,
            "asset_filename": self.asset_filename,
            "is_daily_double": self.is_daily_double,
            "is_used": self.is_used,
            "is_ongame": self.is_ongame,
            "is_tiebreaker": self.is_tiebreaker,
        }


@dataclass
class CategoryModel:
    """Represents a category containing multiple clues."""
    id: Optional[int]
    name: str
    round_id: int
    description: str = ""
    is_active: bool = True
    clues: List[ClueModel] = field(default_factory=list)

    @property
    def clue_count(self) -> int:
        return len(self.clues)

    def is_valid_pool(self, min_clues: int = 6) -> bool:
        """Enforces data integrity rule: must contain at least 6 valid clues."""
        return self.clue_count >= min_clues


@dataclass
class PlayerModel:
    """Represents a contestant profile and career records."""
    id: Optional[int]
    name: str
    total_matches: int = 0
    wins: int = 0
    losses: int = 0
    total_earnings: int = 0
    highest_score: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ClueEventModel:
    """Records an in-game buzzing and scoring event for a clue."""
    id: Optional[int]
    match_id: int
    clue_id: int
    player_id: str
    wager: int
    points_awarded: int
    is_correct: bool
    answered_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class MatchRecordModel:
    """Records the outcome of a completed match."""
    id: Optional[int]
    played_at: str
    round_reached: int
    winner_id: Optional[str]
    winner_name: Optional[str]
    final_scores_json: str
    notes: str = ""
