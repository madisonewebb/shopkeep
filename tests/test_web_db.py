"""Basic tests for the sync web SQLite helpers."""

import time

from src.web.db import delete_pkce_state, get_pkce_state, save_pkce_state


def test_save_and_get_pkce_state(web_db):
    save_pkce_state("state1", "verifier1", "setup_tok", 42, int(time.time()) + 600)
    row = get_pkce_state("state1")
    assert row is not None
    assert row["code_verifier"] == "verifier1"
    assert row["guild_id"] == 42


def test_expired_state_not_returned(web_db):
    save_pkce_state("old", "v", "t", 1, int(time.time()) - 1)
    assert get_pkce_state("old") is None


def test_delete_pkce_state(web_db):
    save_pkce_state("del_me", "v", "t", 1, int(time.time()) + 600)
    delete_pkce_state("del_me")
    assert get_pkce_state("del_me") is None
