"""
Synchronous SQLite helpers for the web server.
The web server runs in Flask (sync), so it uses the standard sqlite3 module
rather than aiosqlite. Both processes share the same WAL-mode SQLite file.
"""

import sqlite3
import time
import os

DB_PATH: str = os.getenv("DB_PATH", "./shopkeep.db")

_CREATE_PKCE_STATE = """
CREATE TABLE IF NOT EXISTS pkce_state (
    state         TEXT    PRIMARY KEY,
    code_verifier TEXT    NOT NULL,
    setup_token   TEXT    NOT NULL,
    guild_id      INTEGER NOT NULL,
    expires_at    INTEGER NOT NULL
)
"""


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_pkce_table() -> None:
    with get_db() as conn:
        conn.execute(_CREATE_PKCE_STATE)
        conn.commit()


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


def save_pkce_state(
    state: str, code_verifier: str, setup_token: str, guild_id: int, expires_at: int
) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO pkce_state (state, code_verifier, setup_token, guild_id, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (state, code_verifier, setup_token, guild_id, expires_at),
        )
        conn.execute("DELETE FROM pkce_state WHERE expires_at <= ?", (int(time.time()),))
        conn.commit()


def get_pkce_state(state: str) -> sqlite3.Row | None:
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM pkce_state WHERE state = ? AND expires_at > ?",
            (state, int(time.time())),
        ).fetchone()


def delete_pkce_state(state: str) -> None:
    with get_db() as conn:
        conn.execute("DELETE FROM pkce_state WHERE state = ?", (state,))
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
