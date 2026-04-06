import os
import sqlite3

from JsonPreprocessor import CJsonPreprocessor
from flask import g
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, "betting.db")
APP_TIMEZONE = timezone(timedelta(hours=7))

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
                handicap_ratio1_line REAL NOT NULL DEFAULT 0.5,
                handicap_ratio1_home_odds REAL NOT NULL DEFAULT 1.95,
                handicap_ratio1_away_odds REAL NOT NULL DEFAULT 1.95,
                handicap_ratio2_line REAL NOT NULL DEFAULT 0.75,
                handicap_ratio2_home_odds REAL NOT NULL DEFAULT 2.10,
                handicap_ratio2_away_odds REAL NOT NULL DEFAULT 1.75,
                handicap1_side TEXT NOT NULL DEFAULT 'home',
                handicap1_line REAL NOT NULL DEFAULT -0.5,
                handicap1_odds REAL NOT NULL DEFAULT 1.95,
                handicap2_side TEXT NOT NULL DEFAULT 'away',
                handicap2_line REAL NOT NULL DEFAULT 0.5,
                handicap2_odds REAL NOT NULL DEFAULT 1.95,
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
                bet_type TEXT NOT NULL DEFAULT 'result',
                outcome TEXT NOT NULL,
                handicap_side TEXT,
                handicap_line REAL,
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
        self._ensure_matches_columns(connection)
        self._ensure_bets_columns(connection)
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

    def _ensure_matches_columns(self, connection: sqlite3.Connection) -> None:
        if not self._column_exists(connection, "matches", "handicap_ratio1_line"):
            connection.execute("ALTER TABLE matches ADD COLUMN handicap_ratio1_line REAL NOT NULL DEFAULT 0.5")

        if not self._column_exists(connection, "matches", "handicap_ratio1_home_odds"):
            connection.execute("ALTER TABLE matches ADD COLUMN handicap_ratio1_home_odds REAL NOT NULL DEFAULT 1.95")

        if not self._column_exists(connection, "matches", "handicap_ratio1_away_odds"):
            connection.execute("ALTER TABLE matches ADD COLUMN handicap_ratio1_away_odds REAL NOT NULL DEFAULT 1.95")

        if not self._column_exists(connection, "matches", "handicap_ratio2_line"):
            connection.execute("ALTER TABLE matches ADD COLUMN handicap_ratio2_line REAL NOT NULL DEFAULT 0.75")

        if not self._column_exists(connection, "matches", "handicap_ratio2_home_odds"):
            connection.execute("ALTER TABLE matches ADD COLUMN handicap_ratio2_home_odds REAL NOT NULL DEFAULT 2.10")

        if not self._column_exists(connection, "matches", "handicap_ratio2_away_odds"):
            connection.execute("ALTER TABLE matches ADD COLUMN handicap_ratio2_away_odds REAL NOT NULL DEFAULT 1.75")

        if not self._column_exists(connection, "matches", "handicap1_side"):
            connection.execute("ALTER TABLE matches ADD COLUMN handicap1_side TEXT NOT NULL DEFAULT 'home'")

        if not self._column_exists(connection, "matches", "handicap1_line"):
            connection.execute("ALTER TABLE matches ADD COLUMN handicap1_line REAL NOT NULL DEFAULT -0.5")

        if not self._column_exists(connection, "matches", "handicap1_odds"):
            connection.execute("ALTER TABLE matches ADD COLUMN handicap1_odds REAL NOT NULL DEFAULT 1.95")

        if not self._column_exists(connection, "matches", "handicap2_side"):
            connection.execute("ALTER TABLE matches ADD COLUMN handicap2_side TEXT NOT NULL DEFAULT 'away'")

        if not self._column_exists(connection, "matches", "handicap2_line"):
            connection.execute("ALTER TABLE matches ADD COLUMN handicap2_line REAL NOT NULL DEFAULT 0.5")

        if not self._column_exists(connection, "matches", "handicap2_odds"):
            connection.execute("ALTER TABLE matches ADD COLUMN handicap2_odds REAL NOT NULL DEFAULT 1.95")

    def _ensure_bets_columns(self, connection: sqlite3.Connection) -> None:
        if not self._column_exists(connection, "bets", "bet_type"):
            connection.execute("ALTER TABLE bets ADD COLUMN bet_type TEXT NOT NULL DEFAULT 'result'")

        if not self._column_exists(connection, "bets", "handicap_side"):
            connection.execute("ALTER TABLE bets ADD COLUMN handicap_side TEXT")

        if not self._column_exists(connection, "bets", "handicap_line"):
            connection.execute("ALTER TABLE bets ADD COLUMN handicap_line REAL")

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

        now = datetime.now(APP_TIMEZONE).replace(microsecond=0)
        fixtures = [
            ("Arsenal", "Liverpool", now - timedelta(hours=6), "North Bank Arena", 2.15, 3.35, 2.95, 0.5, 1.95, 1.95, 0.75, 2.35, 1.55),
            ("Barcelona", "Atletico Madrid", now + timedelta(hours=18), "Catalunya Dome", 1.92, 3.45, 3.8, 0.5, 1.96, 1.94, 0.75, 2.28, 1.60),
            ("Bayern Munich", "Borussia Dortmund", now + timedelta(days=1, hours=4), "Bavaria Park", 1.88, 3.7, 4.05, 1.0, 1.93, 1.97, 1.25, 2.18, 1.67),
            ("Inter Milan", "Juventus", now + timedelta(days=2, hours=2), "San Siro District", 2.32, 3.15, 3.0, 0.25, 1.91, 1.99, 0.5, 2.08, 1.76),
            ("PSG", "Monaco", now + timedelta(days=3), "Paris Lights Stadium", 1.7, 3.9, 4.75, 1.25, 1.95, 1.95, 1.5, 2.24, 1.62),
        ]

        cursor.executemany(
            """
            INSERT INTO matches (
                home_team, away_team, kickoff_at, stadium, home_odds, draw_odds, away_odds,
                handicap_ratio1_line, handicap_ratio1_home_odds, handicap_ratio1_away_odds,
                handicap_ratio2_line, handicap_ratio2_home_odds, handicap_ratio2_away_odds,
                handicap1_side, handicap1_line, handicap1_odds,
                handicap2_side, handicap2_line, handicap2_odds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    handicap_ratio1_line,
                    handicap_ratio1_home_odds,
                    handicap_ratio1_away_odds,
                    handicap_ratio2_line,
                    handicap_ratio2_home_odds,
                    handicap_ratio2_away_odds,
                    "home",
                    -float(handicap_ratio1_line),
                    handicap_ratio1_home_odds,
                    "away",
                    float(handicap_ratio1_line),
                    handicap_ratio1_away_odds,
                )
                for (
                    home_team,
                    away_team,
                    kickoff_at,
                    stadium,
                    home_odds,
                    draw_odds,
                    away_odds,
                    handicap_ratio1_line,
                    handicap_ratio1_home_odds,
                    handicap_ratio1_away_odds,
                    handicap_ratio2_line,
                    handicap_ratio2_home_odds,
                    handicap_ratio2_away_odds,
                ) in fixtures
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
            (datetime.now(APP_TIMEZONE).isoformat(),),
        ).fetchall()

        settled_count = 0
        settled_at = datetime.now(APP_TIMEZONE).replace(microsecond=0).isoformat()
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
                SELECT bets.id, bets.user_id, bets.bet_type, bets.outcome, bets.handicap_side, bets.handicap_line,
                       bets.odds, bets.stake,
                       matches.home_team, matches.away_team
                FROM bets
                JOIN matches ON matches.id = bets.match_id
                WHERE bets.match_id = ? AND bets.status = 'open'
                """,
                (match["id"],),
            ).fetchall()

            for bet in bets:
                if bet["bet_type"] == "result":
                    won = bet["outcome"] == result
                else:
                    if bet["handicap_side"] == "home":
                        won = (home_score + float(bet["handicap_line"])) > away_score
                    else:
                        won = (away_score + float(bet["handicap_line"])) > home_score
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