"""Open-J: Score Engine Facade & Compatibility Layer.
Exports ScoreEngine from core.scoring for backward compatibility.
"""

from core.scoring import ScoreEngine

__all__ = ["ScoreEngine"]