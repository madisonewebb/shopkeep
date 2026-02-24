"""
Mock Etsy API Client Helper
Provides easy access to the mock Etsy API for testing
"""

import requests
from typing import Optional, Dict, Any


class MockEtsyClient:
    """Client for interacting with the Mock Etsy API"""
    
    def __init__(self, api_key: str = "mock-api-key", base_url: str = "http://localhost:5000"):
        self.api_key = api_key
        self.base_url = base_url
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
    
    def get_access_token(self, 
                        authorization_code: str = "mock-auth-code",
                        client_id: str = "mock-client-id",
                        redirect_uri: str = "http://localhost:8000/callback",
                        code_verifier: str = "mock-verifier") -> Dict[str, Any]:
        """
        Get an access token using authorization code grant
        
        Args:
            authorization_code: The authorization code (mock value)
            client_id: Your app's client ID (mock value)
            redirect_uri: Your registered redirect URI
            code_verifier: PKCE code verifier (mock value)
        
        Returns:
            Token response with access_token, refresh_token, etc.
        """
        response = requests.post(
            f"{self.base_url}/v3/public/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": authorization_code,
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier
            }
        )
        response.raise_for_status()
        
        token_data = response.json()
        self.access_token = token_data.get("access_token")
        self.refresh_token = token_data.get("refresh_token")
        
        return token_data
    
    def refresh_access_token(self) -> Dict[str, Any]:
        """
        Refresh the access token using the refresh token
        
        Returns:
            New token response
        """
        if not self.refresh_token:
            raise ValueError("No refresh token available. Call get_access_token first.")
        
        response = requests.post(
            f"{self.base_url}/v3/public/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token
            }
        )
        response.raise_for_status()
        
        token_data = response.json()
        self.access_token = token_data.get("access_token")
        self.refresh_token = token_data.get("refresh_token")
        
        return token_data
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for authenticated requests"""
        if not self.access_token:
            raise ValueError("No access token. Call get_access_token first.")
        
        return {
            "x-api-key": self.api_key,
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
    
    def ping(self) -> Dict[str, Any]:
        """Health check endpoint"""
        response = requests.get(f"{self.base_url}/v3/application/openapi-ping")
        response.raise_for_status()
        return response.json()
    
    # Shop endpoints
    
    def get_shop(self, shop_id: int) -> Dict[str, Any]:
        """Get shop by ID"""
        response = requests.get(
            f"{self.base_url}/v3/application/shops/{shop_id}",
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()
    
    def get_shops_by_user(self, user_id: int) -> Dict[str, Any]:
        """Get shops by user ID"""
        response = requests.get(
            f"{self.base_url}/v3/application/users/{user_id}/shops",
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()
    
    # Receipt (Order) endpoints
    
    def get_shop_receipts(self, 
                         shop_id: int,
                         limit: int = 25,
                         offset: int = 0,
                         min_created: Optional[int] = None,
                         max_created: Optional[int] = None,
                         was_paid: Optional[bool] = None,
                         was_shipped: Optional[bool] = None) -> Dict[str, Any]:
        """
        Get shop receipts (orders)
        
        Args:
            shop_id: The shop ID
            limit: Number of results to return (default 25)
            offset: Offset for pagination (default 0)
            min_created: Minimum creation timestamp
            max_created: Maximum creation timestamp
            was_paid: Filter by payment status
            was_shipped: Filter by shipping status
        
        Returns:
            Receipts response with count and results
        """
        params = {
            "limit": limit,
            "offset": offset
        }
        
        if min_created is not None:
            params["min_created"] = min_created
        if max_created is not None:
            params["max_created"] = max_created
        if was_paid is not None:
            params["was_paid"] = str(was_paid).lower()
        if was_shipped is not None:
            params["was_shipped"] = str(was_shipped).lower()
        
        response = requests.get(
            f"{self.base_url}/v3/application/shops/{shop_id}/receipts",
            headers=self._get_headers(),
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    def get_shop_receipt(self, shop_id: int, receipt_id: int) -> Dict[str, Any]:
        """Get a specific receipt"""
        response = requests.get(
            f"{self.base_url}/v3/application/shops/{shop_id}/receipts/{receipt_id}",
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()
    
    def update_receipt(self, 
                      shop_id: int, 
                      receipt_id: int,
                      was_shipped: Optional[bool] = None,
                      was_paid: Optional[bool] = None) -> Dict[str, Any]:
        """Update a receipt"""
        data = {}
        if was_shipped is not None:
            data["was_shipped"] = was_shipped
        if was_paid is not None:
            data["was_paid"] = was_paid
        
        response = requests.put(
            f"{self.base_url}/v3/application/shops/{shop_id}/receipts/{receipt_id}",
            headers=self._get_headers(),
            json=data
        )
        response.raise_for_status()
        return response.json()
    
    # Listing endpoints
    
    def get_shop_listings(self,
                         shop_id: int,
                         limit: int = 25,
                         offset: int = 0,
                         state: str = "active") -> Dict[str, Any]:
        """
        Get shop listings
        
        Args:
            shop_id: The shop ID
            limit: Number of results to return (default 25)
            offset: Offset for pagination (default 0)
            state: Listing state filter (default "active")
        
        Returns:
            Listings response with count and results
        """
        params = {
            "limit": limit,
            "offset": offset,
            "state": state
        }
        
        response = requests.get(
            f"{self.base_url}/v3/application/shops/{shop_id}/listings",
            headers=self._get_headers(),
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    def get_listing(self, listing_id: int) -> Dict[str, Any]:
        """Get a specific listing"""
        response = requests.get(
            f"{self.base_url}/v3/application/listings/{listing_id}",
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()
    
    def create_listing(self,
                      shop_id: int,
                      title: str,
                      description: str,
                      price: Dict[str, Any],
                      quantity: int,
                      who_made: str = "i_did",
                      when_made: str = "made_to_order",
                      taxonomy_id: int = 1,
                      **kwargs) -> Dict[str, Any]:
        """
        Create a new listing
        
        Args:
            shop_id: The shop ID
            title: Listing title
            description: Listing description
            price: Price object with amount, divisor, currency_code
            quantity: Available quantity
            who_made: Who made the item
            when_made: When the item was made
            taxonomy_id: Etsy taxonomy ID
            **kwargs: Additional listing fields
        
        Returns:
            Created listing
        """
        data = {
            "title": title,
            "description": description,
            "price": price,
            "quantity": quantity,
            "who_made": who_made,
            "when_made": when_made,
            "taxonomy_id": taxonomy_id,
            **kwargs
        }
        
        response = requests.post(
            f"{self.base_url}/v3/application/shops/{shop_id}/listings",
            headers=self._get_headers(),
            json=data
        )
        response.raise_for_status()
        return response.json()
    
    def update_listing(self,
                      shop_id: int,
                      listing_id: int,
                      **kwargs) -> Dict[str, Any]:
        """
        Update a listing
        
        Args:
            shop_id: The shop ID
            listing_id: The listing ID
            **kwargs: Fields to update
        
        Returns:
            Updated listing
        """
        response = requests.put(
            f"{self.base_url}/v3/application/shops/{shop_id}/listings/{listing_id}",
            headers=self._get_headers(),
            json=kwargs
        )
        response.raise_for_status()
        return response.json()


# Example usage
if __name__ == "__main__":
    # Initialize client
    client = MockEtsyClient()
    
    print("Mock Etsy API Client Example")
    print("=" * 60)
    
    # Test ping
    print("\n1. Testing ping endpoint...")
    ping_response = client.ping()
    print(f"   ✓ Ping successful: {ping_response}")
    
    # Get access token
    print("\n2. Getting access token...")
    token_response = client.get_access_token()
    print(f"   ✓ Access token: {token_response['access_token'][:20]}...")
    
    # Get shop
    print("\n3. Getting shop info...")
    shop = client.get_shop(12345678)
    print(f"   ✓ Shop: {shop['shop_name']} (ID: {shop['shop_id']})")
    
    # Get receipts
    print("\n4. Getting shop receipts...")
    receipts = client.get_shop_receipts(12345678)
    print(f"   ✓ Found {receipts['count']} receipts")
    for receipt in receipts['results'][:3]:
        print(f"      - Receipt #{receipt['receipt_id']}: ${receipt['grandtotal']['amount']/100:.2f} ({receipt['status']})")
    
    # Get listings
    print("\n5. Getting shop listings...")
    listings = client.get_shop_listings(12345678)
    print(f"   ✓ Found {listings['count']} listings")
    for listing in listings['results'][:3]:
        print(f"      - {listing['title']}: ${listing['price']['amount']/100:.2f}")
    
    print("\n" + "=" * 60)
    print("All tests passed! ✓")
