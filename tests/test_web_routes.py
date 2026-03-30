"""Basic tests for Flask routes."""

import time
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import insert_guild


def test_health(flask_client):
    client, _ = flask_client
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"


def test_index_renders(flask_client):
    client, _ = flask_client
    resp = client.get("/")
    assert resp.status_code == 200


def test_connect_invalid_token_shows_error(flask_client):
    client, _ = flask_client
    resp = client.get("/connect/no_such_token")
    assert b"invalid" in resp.data.lower()


def test_connect_valid_token_shows_guild_name(flask_client):
    client, db_path = flask_client
    insert_guild(db_path, guild_name="Cool Server", setup_token="good_tok")
    resp = client.get("/connect/good_tok")
    assert resp.status_code == 200
    assert b"Cool Server" in resp.data


def test_connect_post_redirects_to_etsy(flask_client):
    client, db_path = flask_client
    insert_guild(db_path, setup_token="post_tok")
    resp = client.post("/connect/post_tok")
    assert resp.status_code == 302
    assert "etsy.com/oauth/connect" in resp.headers["Location"]


def test_callback_with_error_shows_message(flask_client):
    client, _ = flask_client
    resp = client.get("/callback/etsy?error=access_denied")
    assert b"access_denied" in resp.data
