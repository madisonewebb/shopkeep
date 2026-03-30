"""Basic tests for EtsyClient."""

import time
from unittest.mock import MagicMock, patch

from src.etsy.client import EtsyClient


def make_client(**kwargs) -> EtsyClient:
    defaults = {
        "api_key": "key",
        "shared_secret": "secret",
        "access_token": "access",
        "refresh_token": "refresh",
        "expires_at": int(time.time()) + 3600,
    }
    defaults.update(kwargs)
    client = EtsyClient(**defaults)
    client.session = MagicMock()
    return client


def _ok(body: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = body
    resp.raise_for_status = MagicMock()
    return resp


def test_no_refresh_when_token_fresh():
    client = make_client()
    client.session.request.return_value = _ok({"shop_id": 1})
    client.get_shop(1)
    client.session.post.assert_not_called()


def test_proactive_refresh_when_expiring():
    client = make_client(expires_at=int(time.time()) + 30)
    refresh = MagicMock()
    refresh.raise_for_status = MagicMock()
    refresh.json.return_value = {"access_token": "new", "refresh_token": "new_r", "expires_in": 3600}
    client.session.post.return_value = refresh
    client.session.request.return_value = _ok({})

    client.get_shop(1)

    client.session.post.assert_called_once()
    assert client.access_token == "new"


def test_retry_on_429():
    client = make_client()
    rate_limited = MagicMock()
    rate_limited.status_code = 429
    rate_limited.headers = {"Retry-After": "1"}
    client.session.request.side_effect = [rate_limited, _ok({"ok": True})]

    with patch("src.etsy.client.time.sleep") as mock_sleep:
        result = client._request("GET", "/application/shops/1")
        mock_sleep.assert_called_once_with(1)

    assert result == {"ok": True}


def test_401_triggers_refresh_and_retry():
    client = make_client()
    unauthorized = MagicMock()
    unauthorized.status_code = 401
    refresh = MagicMock()
    refresh.raise_for_status = MagicMock()
    refresh.json.return_value = {"access_token": "new", "refresh_token": "new_r", "expires_in": 3600}
    client.session.post.return_value = refresh
    client.session.request.side_effect = [unauthorized, _ok({"data": 1})]

    result = client._request("GET", "/test")

    assert result == {"data": 1}
    client.session.post.assert_called_once()
