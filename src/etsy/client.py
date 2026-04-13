"""
Etsy API v3 Client

Handles OAuth 2.0 token refresh automatically. Retries on 429 rate limits.
"""

import time
from typing import Any, Callable, Dict, Optional

import requests


class EtsyClient:
    BASE_URL = "https://openapi.etsy.com/v3"
    TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"

    def __init__(
        self,
        api_key: str,
        shared_secret: str,
        access_token: str,
        refresh_token: str,
        expires_at: int = 0,
        on_token_refresh: Optional[Callable[[str, str, int], None]] = None,
    ):
        self.api_key = api_key
        self.shared_secret = shared_secret
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = expires_at
        self.on_token_refresh = on_token_refresh
        self.session = requests.Session()

    # ── Auth ──────────────────────────────────────────────────────────────────

    def _ensure_fresh_token(self) -> None:
        """Refresh the access token if it expires within the next 60 seconds."""
        if time.time() >= self.expires_at - 60:
            self._do_refresh()

    def _do_refresh(self) -> None:
        resp = self.session.post(
            self.TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": self.api_key,
                "refresh_token": self.refresh_token,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        self.expires_at = int(time.time()) + data.get("expires_in", 3600)
        if self.on_token_refresh:
            self.on_token_refresh(self.access_token, self.refresh_token, self.expires_at)

    def _headers(self) -> Dict[str, str]:
        return {
            "x-api-key": f"{self.api_key}:{self.shared_secret}",
            "Authorization": f"Bearer {self.access_token}",
        }

    # ── HTTP ──────────────────────────────────────────────────────────────────

    def _request(self, method: str, path: str, **kwargs) -> Any:
        self._ensure_fresh_token()
        url = f"{self.BASE_URL}{path}"

        resp = self.session.request(method, url, headers=self._headers(), **kwargs)

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 10))
            time.sleep(retry_after)
            resp = self.session.request(method, url, headers=self._headers(), **kwargs)

        if resp.status_code == 401:
            # Token may have expired mid-flight; force a refresh and retry once
            self._do_refresh()
            resp = self.session.request(method, url, headers=self._headers(), **kwargs)

        resp.raise_for_status()
        return resp.json()

    # ── Endpoints ─────────────────────────────────────────────────────────────

    def ping(self) -> Dict[str, Any]:
        resp = self.session.get(
            f"{self.BASE_URL}/application/openapi-ping",
            headers={"x-api-key": self.api_key},
        )
        resp.raise_for_status()
        return resp.json()

    def get_shop(self, shop_id: int) -> Dict[str, Any]:
        return self._request("GET", f"/application/shops/{shop_id}")

    def get_shop_receipts(
        self,
        shop_id: int,
        limit: int = 25,
        offset: int = 0,
        min_created: Optional[int] = None,
        max_created: Optional[int] = None,
        was_paid: Optional[bool] = None,
        was_shipped: Optional[bool] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "limit": limit,
            "offset": offset,
            "includes": ["Transactions"],
        }
        if min_created is not None:
            params["min_created"] = min_created
        if max_created is not None:
            params["max_created"] = max_created
        if was_paid is not None:
            params["was_paid"] = str(was_paid).lower()
        if was_shipped is not None:
            params["was_shipped"] = str(was_shipped).lower()
        return self._request("GET", f"/application/shops/{shop_id}/receipts", params=params)

    def get_shop_reviews(
        self,
        shop_id: int,
        limit: int = 25,
        offset: int = 0,
        min_created: Optional[int] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if min_created is not None:
            params["min_created"] = min_created
        return self._request("GET", f"/application/shops/{shop_id}/reviews", params=params)

    def get_shop_listings(
        self,
        shop_id: int,
        limit: int = 25,
        offset: int = 0,
        state: str = "active",
    ) -> Dict[str, Any]:
        params = {"limit": limit, "offset": offset, "state": state, "includes": ["Images"]}
        return self._request("GET", f"/application/shops/{shop_id}/listings", params=params)
