"""Open-J: Database Manager Facade & Compatibility Layer.
Exports DatabaseManager as DBManager from data.db for backward compatibility.
"""

from data.db import DatabaseManager

# Facade alias
DBManager = DatabaseManager

__all__ = ["DBManager", "DatabaseManager"]
