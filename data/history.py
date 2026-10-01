"""Open-J: Player History, Statistics & Match Archiving Engine.
Persists contestant profiles, career win/loss records, total earnings,
match logs with official consolation prizes ($3,000 2nd, $2,000 3rd), and clue analytics.
"""

import json
from datetime import datetime
from typing import Dict, List, Any, Optional

from data.db import DatabaseManager
from data.models import PlayerModel, MatchRecordModel, ClueEventModel


class HistoryManager:
    """Manages player statistics, match records, and career analytics."""

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db if db else DatabaseManager()

    def get_or_create_player(self, name: str, conn: Optional[Any] = None) -> PlayerModel:
        """Retrieves an existing contestant record or creates a new one."""
        name = name.strip()
        should_close = False
        if conn is None:
            conn = self.db.get_connection()
            should_close = True

        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM players WHERE name = ?", (name,))
            row = cur.fetchone()
            if row:
                return PlayerModel(
                    id=row["id"],
                    name=row["name"],
                    total_matches=row["total_matches"],
                    wins=row["wins"],
                    losses=row["losses"],
                    total_earnings=row["total_earnings"],
                    highest_score=row["highest_score"],
                    created_at=row["created_at"]
                )

            # Create new player
            now_iso = datetime.now().isoformat()
            cur.execute("""
            INSERT INTO players (name, total_matches, wins, losses, total_earnings, highest_score, created_at)
            VALUES (?, 0, 0, 0, 0, 0, ?)
            """, (name, now_iso))
            conn.commit()
            new_id = cur.lastrowid
            return PlayerModel(
                id=new_id,
                name=name,
                total_matches=0,
                wins=0,
                losses=0,
                total_earnings=0,
                highest_score=0,
                created_at=now_iso
            )
        finally:
            if should_close:
                conn.close()

    def record_match_completion(
        self,
        final_scores: Dict[str, int],
        winner_name: Optional[str] = None,
        player_names_map: Optional[Dict[str, str]] = None,
        round_reached: int = 3,
        notes: str = ""
    ) -> int:
        """Records final match outcome, applies prize payouts, and updates player career stats.
        Official Jeopardy Payout Rules:
        - 1st place: keeps 100% of accumulated cash total.
        - 2nd place: receives fixed consolation prize of $3,000.
        - 3rd place: receives fixed consolation prize of $2,000.
        """
        # Determine rankings based on final scores
        sorted_scores = sorted(final_scores.items(), key=lambda item: item[1], reverse=True)

        if not winner_name and sorted_scores:
            top_key = sorted_scores[0][0]
            winner_name = player_names_map.get(top_key, top_key) if player_names_map else top_key

        now_iso = datetime.now().isoformat()
        scores_json = json.dumps(final_scores)

        with self.db.get_connection() as conn:
            cur = conn.cursor()

            # Find winner player ID
            winner_id = None
            if winner_name:
                p_win = self.get_or_create_player(winner_name, conn=conn)
                winner_id = p_win.id

            # Insert match record
            cur.execute("""
            INSERT INTO matches (played_at, round_reached, winner_id, winner_name, final_scores_json, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (now_iso, round_reached, winner_id, winner_name, scores_json, notes))
            match_id = cur.lastrowid

            # Update contestant career statistics
            for rank, (player_key, score) in enumerate(sorted_scores, start=1):
                actual_name = player_key
                if player_names_map and player_key in player_names_map:
                    actual_name = player_names_map[player_key]
                elif rank == 1 and winner_name:
                    actual_name = winner_name

                p = self.get_or_create_player(actual_name, conn=conn)
                is_winner = (rank == 1)

                # Consolation payout calculation
                if rank == 1:
                    earnings = max(0, score)  # Winner retains cash total
                elif rank == 2:
                    earnings = 3000          # 2nd Place fixed prize
                else:
                    earnings = 2000          # 3rd Place fixed prize

                new_matches = p.total_matches + 1
                new_wins = p.wins + (1 if is_winner else 0)
                new_losses = p.losses + (0 if is_winner else 1)
                new_earnings = p.total_earnings + earnings
                new_high = max(p.highest_score, score)

                cur.execute("""
                UPDATE players
                SET total_matches = ?, wins = ?, losses = ?, total_earnings = ?, highest_score = ?
                WHERE id = ?
                """, (new_matches, new_wins, new_losses, new_earnings, new_high, p.id))

            conn.commit()
            print(f"[History] Recorded match #{match_id}. Winner: {winner_name}, scores: {final_scores}")
            return match_id

    def record_clue_event(
        self,
        match_id: int,
        clue_id: int,
        player_id: str,
        wager: int,
        points_awarded: int,
        is_correct: bool
    ):
        """Logs an individual clue response/wager event during gameplay."""
        now_iso = datetime.now().isoformat()
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO clue_events (match_id, clue_id, player_id, wager, points_awarded, is_correct, answered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (match_id, clue_id, player_id, wager, points_awarded, 1 if is_correct else 0, now_iso))
            conn.commit()

    def get_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Returns top players by total earnings and win counts."""
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT name, total_matches, wins, losses, total_earnings, highest_score
            FROM players
            ORDER BY wins DESC, total_earnings DESC
            LIMIT ?
            """, (limit,))
            return [dict(r) for r in cur.fetchall()]

    def get_player_stats(self, name: str) -> Optional[Dict[str, Any]]:
        """Returns comprehensive stats for a specific contestant."""
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM players WHERE name = ?", (name.strip(),))
            row = cur.fetchone()
            return dict(row) if row else None
