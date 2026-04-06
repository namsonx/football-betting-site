import os
import sqlite3

from JsonPreprocessor import CJsonPreprocessor
from flask import g
from datetime import UTC, datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, "betting.db")

languages_path = os.path.join(BASE_DIR, "../config", "languages.jsonp")
json_preprocessor = CJsonPreprocessor(syntax="python")
try:
    translations_data = json_preprocessor.jsonLoad(languages_path)
    SUPPORTED_LANGS = set(translations_data.translations.keys())
    TRANSLATIONS = translations_data.translations
except Exception as e:
    print(f"Error loading translations: {e}")

class BettingDB():
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path

    def connect(self):
        return sqlite3.connect(self.db_path)

    def init_db(self) -> None:
        connection = sqlite3.connect(self.db_path)
        cursor = connection.cursor()
        cursor.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                balance REAL NOT NULL DEFAULT 1000,
                created_at TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                full_name TEXT,
                email TEXT,
                phone TEXT
            );

            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,
                kickoff_at TEXT NOT NULL,
                stadium TEXT NOT NULL,
                home_odds REAL NOT NULL,
                draw_odds REAL NOT NULL,
                away_odds REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'scheduled',
                score_home INTEGER,
                score_away INTEGER,
                result TEXT,
                settled_at TEXT
            );

            CREATE TABLE IF NOT EXISTS bets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                match_id INTEGER NOT NULL,
                outcome TEXT NOT NULL,
                odds REAL NOT NULL,
                stake REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                payout REAL,
                placed_at TEXT NOT NULL,
                settled_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(match_id) REFERENCES matches(id)
            );

            CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                activity_type TEXT NOT NULL,
                title TEXT NOT NULL,
                details TEXT,
                related_bet_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(related_bet_id) REFERENCES bets(id)
            );
            """
        )
        self._ensure_users_columns(connection)
        connection.commit()
        connection.close()

    def _column_exists(self, connection: sqlite3.Connection, table: str, column: str) -> bool:
        rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
        for row in rows:
            if row[1] == column:
                return True
        return False

    def _ensure_users_columns(self, connection: sqlite3.Connection) -> None:
        if not self._column_exists(connection, "users", "role"):
            connection.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")

        if not self._column_exists(connection, "users", "full_name"):
            connection.execute("ALTER TABLE users ADD COLUMN full_name TEXT")

        if not self._column_exists(connection, "users", "email"):
            connection.execute("ALTER TABLE users ADD COLUMN email TEXT")

        if not self._column_exists(connection, "users", "phone"):
            connection.execute("ALTER TABLE users ADD COLUMN phone TEXT")

    def get_db(self) -> sqlite3.Connection:
        if "db" not in g:
            g.db = sqlite3.connect(self.db_path)
            g.db.row_factory = sqlite3.Row
        return g.db
    
    def close_db(self, e=None) -> None:
        db = g.pop("db", None)
        if db is not None:
            db.close()

    def seed_matches(self) -> None:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        existing_match = cursor.execute("SELECT id FROM matches LIMIT 1").fetchone()
        if existing_match:
            connection.close()
            return

        now = datetime.now(UTC).replace(microsecond=0)
        fixtures = [
            ("Arsenal", "Liverpool", now - timedelta(hours=6), "North Bank Arena", 2.15, 3.35, 2.95),
            ("Barcelona", "Atletico Madrid", now + timedelta(hours=18), "Catalunya Dome", 1.92, 3.45, 3.8),
            ("Bayern Munich", "Borussia Dortmund", now + timedelta(days=1, hours=4), "Bavaria Park", 1.88, 3.7, 4.05),
            ("Inter Milan", "Juventus", now + timedelta(days=2, hours=2), "San Siro District", 2.32, 3.15, 3.0),
            ("PSG", "Monaco", now + timedelta(days=3), "Paris Lights Stadium", 1.7, 3.9, 4.75),
        ]

        cursor.executemany(
            """
            INSERT INTO matches (
                home_team, away_team, kickoff_at, stadium, home_odds, draw_odds, away_odds
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    home_team,
                    away_team,
                    kickoff_at.isoformat(),
                    stadium,
                    home_odds,
                    draw_odds,
                    away_odds,
                )
                for home_team, away_team, kickoff_at, stadium, home_odds, draw_odds, away_odds in fixtures
            ],
        )
        connection.commit()
        connection.close()

    def settle_due_matches(self, collect_events: bool = False):
        db = self.get_db()
        due_matches = db.execute(
            """
            SELECT *
            FROM matches
            WHERE status = 'scheduled' AND kickoff_at <= ?
            ORDER BY kickoff_at ASC
            """,
            (datetime.now(UTC).isoformat(),),
        ).fetchall()

        settled_count = 0
        settled_at = datetime.now(UTC).replace(microsecond=0).isoformat()
        settlement_events = []

        for match in due_matches:
            kickoff = datetime.fromisoformat(match["kickoff_at"])
            home_score = (match["id"] + kickoff.day + kickoff.hour) % 4
            away_score = (match["id"] * 2 + kickoff.month + kickoff.minute) % 4

            if home_score > away_score:
                result = "home"
            elif away_score > home_score:
                result = "away"
            else:
                result = "draw"

            db.execute(
                """
                UPDATE matches
                SET status = 'settled', score_home = ?, score_away = ?, result = ?, settled_at = ?
                WHERE id = ?
                """,
                (home_score, away_score, result, settled_at, match["id"]),
            )

            bets = db.execute(
                """
                SELECT bets.id, bets.user_id, bets.outcome, bets.odds, bets.stake,
                       matches.home_team, matches.away_team
                FROM bets
                JOIN matches ON matches.id = bets.match_id
                WHERE bets.match_id = ? AND bets.status = 'open'
                """,
                (match["id"],),
            ).fetchall()

            for bet in bets:
                won = bet["outcome"] == result
                payout = round(bet["stake"] * bet["odds"], 2) if won else 0.0
                bet_status = "won" if won else "lost"

                db.execute(
                    "UPDATE bets SET status = ?, payout = ?, settled_at = ? WHERE id = ?",
                    (bet_status, payout, settled_at, bet["id"]),
                )

                if won:
                    db.execute(
                        "UPDATE users SET balance = balance + ? WHERE id = ?",
                        (payout, bet["user_id"]),
                    )

                if collect_events:
                    settlement_events.append(
                        {
                            "user_id": bet["user_id"],
                            "bet_id": bet["id"],
                            "fixture": f"{bet['home_team']} vs {bet['away_team']}",
                            "status": bet_status,
                            "payout": payout,
                            "stake": bet["stake"],
                            "settled_at": settled_at,
                        }
                    )

            settled_count += 1

        db.commit()
        if collect_events:
            return settled_count, settlement_events
        return settled_count