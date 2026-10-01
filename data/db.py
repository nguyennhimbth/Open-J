"""Open-J: Database Connection Manager & Persistence Engine.
Manages SQLite schemas, migrations, game category activations,
data integrity validation (>=6 clues per category), and seed ingestion.
"""

import os
import json
import sqlite3
import random
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from data.models import RoundModel, CategoryModel, ClueModel, PlayerModel, MatchRecordModel, ClueEventModel

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "questions.db"
DEFAULT_SEED_PATH = PROJECT_ROOT / "data" / "seeds" / "sample_questions.json"
MIN_CLUES_PER_CATEGORY = 6


class DatabaseManager:
    """Enterprise SQLite Database Connection and Query Manager for Project Open-J."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        """Returns a connection configured with Row factory, foreign keys, and WAL mode."""
        conn = sqlite3.connect(str(self.db_path), timeout=20.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            conn.execute("PRAGMA journal_mode = WAL")
        except Exception:
            pass
        return conn

    def init_db(self):
        """Initializes tables and runs automated schema migrations."""
        with self.get_connection() as conn:
            cur = conn.cursor()

            # 1. Rounds Table
            cur.execute("""
            CREATE TABLE IF NOT EXISTS rounds (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                round_number INTEGER NOT NULL UNIQUE,
                min_value INTEGER NOT NULL,
                max_value INTEGER NOT NULL,
                value_step INTEGER NOT NULL,
                dd_count INTEGER NOT NULL DEFAULT 1
            )
            """)

            # 2. Categories Table
            cur.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                round_id INTEGER NOT NULL,
                description TEXT DEFAULT '',
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY(round_id) REFERENCES rounds(id) ON DELETE CASCADE
            )
            """)

            # 3. Clues Table
            cur.execute("""
            CREATE TABLE IF NOT EXISTS clues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL,
                round_id INTEGER NOT NULL,
                col_index INTEGER DEFAULT 0,
                row_index INTEGER DEFAULT 0,
                points INTEGER NOT NULL,
                clue_text TEXT NOT NULL,
                answer_text TEXT NOT NULL,
                asset_filename TEXT DEFAULT '',
                is_daily_double BOOLEAN DEFAULT 0,
                is_used BOOLEAN DEFAULT 0,
                is_ongame BOOLEAN DEFAULT 0,
                is_tiebreaker BOOLEAN DEFAULT 0,
                FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE CASCADE,
                FOREIGN KEY(round_id) REFERENCES rounds(id) ON DELETE CASCADE
            )
            """)

            # 4. Players Table
            cur.execute("""
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                total_matches INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                total_earnings INTEGER DEFAULT 0,
                highest_score INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """)

            # 5. Matches Table
            cur.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                played_at TEXT NOT NULL,
                round_reached INTEGER NOT NULL,
                winner_id INTEGER,
                winner_name TEXT,
                final_scores_json TEXT NOT NULL,
                notes TEXT DEFAULT '',
                FOREIGN KEY(winner_id) REFERENCES players(id)
            )
            """)

            # 6. Clue Events Table
            cur.execute("""
            CREATE TABLE IF NOT EXISTS clue_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER NOT NULL,
                clue_id INTEGER NOT NULL,
                player_id TEXT NOT NULL,
                wager INTEGER DEFAULT 0,
                points_awarded INTEGER NOT NULL,
                is_correct BOOLEAN NOT NULL,
                answered_at TEXT NOT NULL,
                FOREIGN KEY(match_id) REFERENCES matches(id) ON DELETE CASCADE,
                FOREIGN KEY(clue_id) REFERENCES clues(id) ON DELETE CASCADE
            )
            """)

            # Legacy compatibility view: 'questions' view mapping to clues and categories
            cur.execute("""
            CREATE VIEW IF NOT EXISTS questions AS
            SELECT 
                c.id AS id,
                c.round_id AS round_id,
                c.col_index AS col_index,
                c.row_index AS row_index,
                cat.name AS category_name,
                c.points AS points,
                c.clue_text AS question_text,
                c.answer_text AS answer_text,
                c.asset_filename AS asset_filename,
                c.is_daily_double AS is_daily_double,
                c.is_used AS is_used,
                c.is_ongame AS is_ongame
            FROM clues c
            JOIN categories cat ON c.category_id = cat.id
            """)

            conn.commit()

        # Seed initial dataset if database is newly initialized
        self._check_and_seed()

    def _check_and_seed(self):
        """Verifies if categories exist; if empty, loads sample fixture."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM categories")
            count = cur.fetchone()[0]
            if count == 0:
                print(f"[DB] Database is empty. Loading default seed dataset from {DEFAULT_SEED_PATH}...")
                self.load_seed_file(str(DEFAULT_SEED_PATH))

    def load_seed_file(self, seed_path: str):
        """Loads categories and clues from JSON fixture enforcing the >=6 clues validation rule."""
        p = Path(seed_path)
        if not p.exists():
            print(f"[DB Error] Seed file not found: {seed_path}")
            return

        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)

        with self.get_connection() as conn:
            cur = conn.cursor()

            # Seed rounds
            for r in data.get("rounds", []):
                cur.execute("""
                INSERT OR REPLACE INTO rounds (id, name, round_number, min_value, max_value, value_step, dd_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (r["id"], r["name"], r["round_number"], r["min_value"], r["max_value"], r["value_step"], r["dd_count"]))

            # Seed categories & clues
            for cat in data.get("categories", []):
                round_id = cat["round_id"]
                clues = cat.get("clues", [])

                # Verify integrity: Round 1 & 2 must have >= 6 clues
                if round_id in (1, 2) and len(clues) < MIN_CLUES_PER_CATEGORY:
                    print(f"[DB Warning] Category '{cat['name']}' has only {len(clues)} clues (requires >= {MIN_CLUES_PER_CATEGORY}). SKIPPING per integrity rule.")
                    continue

                cur.execute("""
                INSERT INTO categories (name, round_id, description, is_active)
                VALUES (?, ?, ?, 1)
                """, (cat["name"], round_id, cat.get("description", "")))
                cat_id = cur.lastrowid

                is_tiebreaker = (round_id == 4)
                for i, clue in enumerate(clues):
                    row_idx = min(i, 4)
                    cur.execute("""
                    INSERT INTO clues (category_id, round_id, col_index, row_index, points, clue_text, answer_text, asset_filename, is_daily_double, is_used, is_ongame, is_tiebreaker)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?)
                    """, (
                        cat_id,
                        round_id,
                        0,
                        row_idx,
                        clue.get("points", 0),
                        clue.get("clue", ""),
                        clue.get("response", ""),
                        clue.get("asset_filename", ""),
                        1 if is_tiebreaker else 0
                    ))

            conn.commit()
            print(f"[DB] Successfully loaded seed fixture from {seed_path}.")

    def reset_ongame(self):
        """Resets all clue runtime flags (`is_ongame`, `is_used`, `is_daily_double`)."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE clues SET is_ongame = 0, is_used = 0, is_daily_double = 0")
            conn.commit()

    def activate_game_categories(self, round_1_count: int = 6, round_2_count: int = 6) -> Dict[str, Any]:
        """Activates 6 categories for Round 1, 6 categories for Round 2, and 1 for Final Jeopardy.
        Strictly enforces the rule that only categories with >= 6 clues can be activated.
        Dynamically positions Daily Doubles:
        - 1 Daily Double in Round 1 (rows 1-4)
        - 2 Daily Doubles in Round 2 (distinct categories, rows 1-4)
        """
        self.reset_ongame()

        activated = {"round_1": [], "round_2": [], "final": None, "tiebreaker": None}

        with self.get_connection() as conn:
            cur = conn.cursor()

            # --- ROUND 1 ACTIVATION ---
            cur.execute("""
            SELECT c.id, c.name, COUNT(cl.id) as clue_count
            FROM categories c
            JOIN clues cl ON c.id = cl.category_id
            WHERE c.round_id = 1 AND c.is_active = 1
            GROUP BY c.id
            HAVING clue_count >= ?
            """, (MIN_CLUES_PER_CATEGORY,))
            r1_cats = cur.fetchall()

            if len(r1_cats) < round_1_count:
                raise ValueError(f"Not enough valid Round 1 categories with >= {MIN_CLUES_PER_CATEGORY} clues! Found {len(r1_cats)}, need {round_1_count}.")

            selected_r1 = random.sample(r1_cats, round_1_count)
            # Pick 1 random cell for Daily Double in Round 1 (prefer rows 1-4)
            r1_dd_col = random.randint(0, round_1_count - 1)
            r1_dd_row = random.choice([1, 2, 3, 4])

            for col_idx, cat in enumerate(selected_r1):
                cat_id = cat["id"]
                activated["round_1"].append(cat["name"])
                # Fetch top 5 clues ordered by points
                cur.execute("""
                SELECT id, points FROM clues
                WHERE category_id = ?
                ORDER BY points ASC, id ASC
                LIMIT 5
                """, (cat_id,))
                clues = cur.fetchall()
                for row_idx, clue in enumerate(clues):
                    clue_id = clue["id"]
                    is_dd = 1 if (col_idx == r1_dd_col and row_idx == r1_dd_row) else 0
                    cur.execute("""
                    UPDATE clues
                    SET col_index = ?, row_index = ?, is_ongame = 1, is_used = 0, is_daily_double = ?
                    WHERE id = ?
                    """, (col_idx, row_idx, is_dd, clue_id))

            # --- ROUND 2 ACTIVATION ---
            cur.execute("""
            SELECT c.id, c.name, COUNT(cl.id) as clue_count
            FROM categories c
            JOIN clues cl ON c.id = cl.category_id
            WHERE c.round_id = 2 AND c.is_active = 1
            GROUP BY c.id
            HAVING clue_count >= ?
            """, (MIN_CLUES_PER_CATEGORY,))
            r2_cats = cur.fetchall()

            if len(r2_cats) < round_2_count:
                raise ValueError(f"Not enough valid Round 2 categories with >= {MIN_CLUES_PER_CATEGORY} clues! Found {len(r2_cats)}, need {round_2_count}.")

            selected_r2 = random.sample(r2_cats, round_2_count)
            # Pick 2 distinct columns for Daily Doubles in Round 2
            r2_dd_cols = random.sample(range(round_2_count), 2)
            r2_dd_rows = [random.choice([1, 2, 3, 4]), random.choice([1, 2, 3, 4])]

            for col_idx, cat in enumerate(selected_r2):
                cat_id = cat["id"]
                activated["round_2"].append(cat["name"])
                cur.execute("""
                SELECT id, points FROM clues
                WHERE category_id = ?
                ORDER BY points ASC, id ASC
                LIMIT 5
                """, (cat_id,))
                clues = cur.fetchall()
                for row_idx, clue in enumerate(clues):
                    clue_id = clue["id"]
                    is_dd = 0
                    if col_idx == r2_dd_cols[0] and row_idx == r2_dd_rows[0]:
                        is_dd = 1
                    elif col_idx == r2_dd_cols[1] and row_idx == r2_dd_rows[1]:
                        is_dd = 1

                    cur.execute("""
                    UPDATE clues
                    SET col_index = ?, row_index = ?, is_ongame = 1, is_used = 0, is_daily_double = ?
                    WHERE id = ?
                    """, (col_idx, row_idx, is_dd, clue_id))

            # --- ROUND 3 (FINAL JEOPARDY) ACTIVATION ---
            cur.execute("""
            SELECT c.id, c.name FROM categories c
            WHERE c.round_id = 3 AND c.is_active = 1
            """)
            r3_cats = cur.fetchall()
            if r3_cats:
                selected_r3 = random.choice(r3_cats)
                activated["final"] = selected_r3["name"]
                cur.execute("""
                UPDATE clues
                SET is_ongame = 1, is_used = 0, is_daily_double = 0
                WHERE category_id = ?
                """, (selected_r3["id"],))

            # --- TIEBREAKER CANDIDATE ---
            cur.execute("""
            SELECT cl.id, cl.clue_text, cl.answer_text, cat.name
            FROM clues cl
            JOIN categories cat ON cl.category_id = cat.id
            WHERE cl.is_tiebreaker = 1 OR cl.round_id = 4
            LIMIT 1
            """)
            tb = cur.fetchone()
            if tb:
                activated["tiebreaker"] = {
                    "id": tb["id"],
                    "clue": tb["clue_text"],
                    "response": tb["answer_text"],
                    "category": tb["name"]
                }

            conn.commit()

        print(f"[DB] Match initialized. R1: {len(activated['round_1'])} cats, R2: {len(activated['round_2'])} cats, Final: {activated['final']}")
        return activated

    def get_board_clues(self, round_id: int) -> List[Dict[str, Any]]:
        """Fetches active on-game clues for the specified round."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT 
                cl.id, cl.round_id, cl.col_index, cl.row_index,
                cat.name AS category_name, cl.points,
                cl.clue_text AS question_text, cl.answer_text,
                cl.asset_filename, cl.is_daily_double, cl.is_used, cl.is_ongame
            FROM clues cl
            JOIN categories cat ON cl.category_id = cat.id
            WHERE cl.round_id = ? AND cl.is_ongame = 1
            ORDER BY cl.col_index ASC, cl.row_index ASC
            """, (round_id,))
            rows = cur.fetchall()
            return [dict(r) for r in rows]

    def get_categories_for_round(self, round_id: int) -> List[str]:
        """Returns ordered list of active category titles for a round."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT DISTINCT cl.col_index, cat.name
            FROM clues cl
            JOIN categories cat ON cl.category_id = cat.id
            WHERE cl.round_id = ? AND cl.is_ongame = 1
            ORDER BY cl.col_index ASC
            """, (round_id,))
            return [r["name"] for r in cur.fetchall()]

    def mark_clue_used(self, clue_id: int):
        """Marks a clue as used."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE clues SET is_used = 1 WHERE id = ?", (clue_id,))
            conn.commit()

    def get_tiebreaker_clue(self) -> Optional[Dict[str, Any]]:
        """Retrieves an available tiebreaker clue, or None if not available."""
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT 
                cl.id, cl.round_id, 0 as col_index, 0 as row_index,
                cat.name AS category_name, 0 as points,
                cl.clue_text AS question_text, cl.answer_text,
                cl.asset_filename, 0 as is_daily_double, cl.is_used, 1 as is_ongame
            FROM clues cl
            JOIN categories cat ON cl.category_id = cat.id
            WHERE cl.is_tiebreaker = 1 OR cl.round_id = 4
            ORDER BY cl.is_used ASC, cl.id ASC
            LIMIT 1
            """)
            row = cur.fetchone()
            return dict(row) if row else None
