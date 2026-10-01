"""Open-J: Question Management Engine Facade & Compatibility Layer.
Exports QuestionEngine from core.questions for backward compatibility.
"""

from core.questions import QuestionEngine

__all__ = ["QuestionEngine"]