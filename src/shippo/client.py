"""
Shippo shipping API client.

Wraps the Shippo REST API v1 using raw requests, consistent with EtsyClient.
"""

from typing import Any, Dict, List, Optional

import requests


class ShippoClient:
    BASE_URL = "https://api.goshippo.com"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"ShippoToken {api_key}",
            "Content-Type": "application/json",
        })

    def _request(self, method: str, path: str, **kwargs) -> Any:
        resp = self.session.request(method, f"{self.BASE_URL}{path}", **kwargs)
        resp.raise_for_status()
        return resp.json()

    def validate(self) -> None:
        """Raise if the API key is invalid."""
        self._request("GET", "/carrier_accounts")

    def get_rates(
        self,
        address_from: Dict[str, str],
        address_to: Dict[str, str],
        weight_oz: float,
        length_in: float,
        width_in: float,
        height_in: float,
    ) -> List[Dict]:
        """Create a Shippo shipment and return available rates."""
        parcel = {
            "length": str(length_in),
            "width": str(width_in),
            "height": str(height_in),
            "distance_unit": "in",
            "weight": str(weight_oz),
            "mass_unit": "oz",
        }
        data = self._request("POST", "/shipments", json={
            "address_from": address_from,
            "address_to": address_to,
            "parcels": [parcel],
            "async": False,
        })
        return [r for r in data.get("rates", []) if r.get("object_id")]

    def buy_rate(self, rate_object_id: str) -> Dict:
        """Purchase a rate. Returns transaction with label_url and tracking_number."""
        return self._request("POST", "/transactions", json={
            "rate": rate_object_id,
            "label_file_type": "PDF_4x6",
            "async": False,
        })

    @staticmethod
    def find_rate(rates: List[Dict], carrier: str, mail_class: str) -> Optional[Dict]:
        """Find a rate matching carrier + mail class (fuzzy token match)."""
        def norm(s: str) -> str:
            return s.lower().replace("_", "").replace(" ", "")

        cl = norm(carrier)
        ml = norm(mail_class)
        for rate in rates:
            p = norm(rate.get("provider", ""))
            t = norm((rate.get("servicelevel") or {}).get("token", ""))
            if p == cl and (t == ml or ml in t or t in ml):
                return rate
        return None

    @staticmethod
    def fmt_rate(rate: Dict) -> str:
        """Human-readable rate label for Discord select menus (max 100 chars)."""
        provider = rate.get("provider", "?")
        name = (rate.get("servicelevel") or {}).get("name", "?")
        amount = rate.get("amount", "?")
        currency = rate.get("currency", "")
        days = rate.get("estimated_days")
        s = f"{provider} {name} — ${amount} {currency}"
        if days:
            s += f" ({days}d)"
        return s[:100]

    @staticmethod
    def etsy_carrier_name(shippo_provider: str) -> str:
        """Map Shippo provider name to Etsy carrier_name for tracking posts."""
        mapping = {
            "USPS": "usps",
            "FedEx": "fedex",
            "UPS": "ups",
            "DHL Express": "dhl",
            "DHL eCommerce": "dhl",
            "Canada Post": "canada_post",
            "Australia Post": "australia_post",
            "Royal Mail": "royal_mail",
        }
        return mapping.get(shippo_provider, shippo_provider.lower().replace(" ", "_"))
