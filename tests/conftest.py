"""
Shared fixtures and environment setup for all tests.

Environment variables must be set at module level so they are present
before any src.web.app import (which reads them at module load time).
"""

import os
import sqlite3
import time

import pytest

# Must be set before src.web.app is imported
os.environ.setdefault("ETSY_API_KEY", "test_api_key")
os.environ.setdefault("ETSY_SHARED_SECRET", "test_shared_secret")
os.environ.setdefault("ETSY_WEB_REDIRECT_URI", "http://localhost/callback/etsy")
os.environ.setdefault("DISCORD_CLIENT_ID", "123456789")
os.environ.setdefault("WEB_BASE_URL", "http://localhost:8080")
# Prevent init_pkce_table() (called at app import time) from writing to ./shopkeep.db
os.environ.setdefault("DB_PATH", "/tmp/shopkeep_pytest_init.db")


def _create_web_schema(path: str) -> None:
    """Create the tables that the web server reads/writes."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS guilds (
            guild_id         INTEGER PRIMARY KEY,
            guild_name       TEXT,
            etsy_shop_id     INTEGER,
            order_channel_id INTEGER,
            setup_token      TEXT UNIQUE,
            setup_token_exp  INTEGER,
            connected_at     INTEGER,
            created_at       INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS etsy_tokens (
            guild_id      INTEGER PRIMARY KEY,
            access_token  TEXT    NOT NULL,
            refresh_token TEXT    NOT NULL,
            expires_at    INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pkce_state (
            state         TEXT    PRIMARY KEY,
            code_verifier TEXT    NOT NULL,
            setup_token   TEXT    NOT NULL,
            guild_id      INTEGER NOT NULL,
            expires_at    INTEGER NOT NULL
        );
    """)
    conn.commit()
    conn.close()


@pytest.fixture()
def web_db(tmp_path, monkeypatch):
    """Isolated SQLite DB with full web schema; patches src.web.db.DB_PATH."""
    db_file = str(tmp_path / "test.db")
    import src.web.db as webdb

    monkeypatch.setattr(webdb, "DB_PATH", db_file)
    _create_web_schema(db_file)
    return db_file


@pytest.fixture()
def flask_client(web_db):
    """Flask test client backed by an isolated DB."""
    from src.web.app import app

    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client, web_db


def insert_guild(
    db_path: str,
    guild_id: int = 1,
    guild_name: str = "Test Guild",
    setup_token: str = "valid_token",
    setup_token_exp: int | None = None,
    etsy_shop_id: int | None = None,
) -> None:
    """Helper: insert a guild row for web route tests."""
    if setup_token_exp is None:
        setup_token_exp = int(time.time()) + 3600
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO guilds (guild_id, guild_name, setup_token, setup_token_exp, etsy_shop_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (guild_id, guild_name, setup_token, setup_token_exp, etsy_shop_id, int(time.time())),
    )
    conn.commit()
    conn.close()
