"""
Synchronous SQLite helpers for the web server.
The web server runs in Flask (sync), so it uses the standard sqlite3 module
rather than aiosqlite. Both processes share the same WAL-mode SQLite file.
"""

import sqlite3
import time
import os

DB_PATH: str = os.getenv("DB_PATH", "./shopkeep.db")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_guild_by_setup_token(setup_token: str) -> sqlite3.Row | None:
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM guilds WHERE setup_token = ?", (setup_token,)
        ).fetchone()


def update_guild_etsy(guild_id: int, etsy_shop_id: int) -> None:
    with get_db() as conn:
        conn.execute(
            """
            UPDATE guilds
            SET etsy_shop_id = ?, connected_at = ?, setup_token = NULL, setup_token_exp = NULL
            WHERE guild_id = ?
            """,
            (etsy_shop_id, int(time.time()), guild_id),
        )
        conn.commit()


def save_guild_tokens(
    guild_id: int, access_token: str, refresh_token: str, expires_at: int
) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO etsy_tokens (guild_id, access_token, refresh_token, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (guild_id, access_token, refresh_token, expires_at),
        )
        conn.commit()
