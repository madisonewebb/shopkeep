"""
USPS Address API v3 client.

Handles OAuth 2.0 client credentials flow and address verification.
"""

import time
from typing import Optional

import requests


class USPSAddressVerificationError(Exception):
    pass


class USPSClient:
    TOKEN_URL = "https://api.usps.com/oauth2/v3/token"
    ADDRESS_URL = "https://api.usps.com/addresses/v3/address"

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.session = requests.Session()
        self._access_token: Optional[str] = None
        self._expires_at: int = 0

    def _ensure_token(self) -> None:
        if self._access_token and time.time() < self._expires_at - 30:
            return
        resp = self.session.post(
            self.TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access_token"]
        self._expires_at = int(time.time()) + int(data.get("expires_in", 3600))

    def verify_address(
        self,
        street_address: str,
        city: str,
        state: str,
        zip_code: str,
    ) -> dict:
        """
        Verify an address against the USPS database.

        Returns the API response dict. Raises USPSAddressVerificationError if
        the address cannot be validated (not found, ambiguous, etc.).

        DPVConfirmation values:
          Y — full match
          S — matched without secondary (apartment/unit)
          D — matched but secondary required
          N — no match
        """
        self._ensure_token()
        resp = self.session.get(
            self.ADDRESS_URL,
            headers={"Authorization": f"Bearer {self._access_token}"},
            params={
                "streetAddress": street_address,
                "city": city,
                "state": state,
                "ZIPCode": zip_code,
            },
        )
        if resp.status_code == 404:
            raise USPSAddressVerificationError("Address not found in USPS database")
        resp.raise_for_status()
        data = resp.json()
        dpv = data.get("address", {}).get("DPVConfirmation") or data.get("DPVConfirmation")
        if dpv == "N":
            raise USPSAddressVerificationError("Address could not be confirmed by USPS")
        return data
