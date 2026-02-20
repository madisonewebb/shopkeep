# Mock Etsy API v3

A development server that mimics the real Etsy API v3 for testing and development purposes while waiting for your Etsy API key activation.

## Features

- ✅ **OAuth2 Authentication** - Mock token generation and refresh
- ✅ **Shop Endpoints** - Get shop information
- ✅ **Receipt (Order) Endpoints** - List, get, and update orders
- ✅ **Listing Endpoints** - Create, read, update listings
- ✅ **Realistic Data** - Pre-populated with sample shops, orders, and listings
- ✅ **API-Compatible** - Matches real Etsy API v3 structure and responses

## Quick Start

### 1. Start the Mock API Server

```bash
python mock_etsy_api.py
```

The server will start on `http://localhost:5000`

### 2. Test with the Client Helper

```bash
python mock_etsy_client.py
```

This will run through example API calls and display results.

## Sample Data

The mock API comes pre-loaded with:

- **Shop ID**: `12345678`
- **User ID**: `87654321`
- **3 Sample Receipts** (orders) with varying statuses
- **5 Sample Listings** (products)

## API Endpoints

### Authentication

#### Get Access Token
```http
POST /v3/public/oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=mock-auth-code&client_id=mock-client-id&redirect_uri=http://localhost:8000/callback&code_verifier=mock-verifier
```

**Response:**
```json
{
  "access_token": "...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "..."
}
```

#### Refresh Token
```http
POST /v3/public/oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<your_refresh_token>
```

### Shop Endpoints

#### Get Shop
```http
GET /v3/application/shops/{shop_id}
x-api-key: your-api-key
Authorization: Bearer <access_token>
```

#### Get Shops by User
```http
GET /v3/application/users/{user_id}/shops
x-api-key: your-api-key
Authorization: Bearer <access_token>
```

### Receipt (Order) Endpoints

#### List Shop Receipts
```http
GET /v3/application/shops/{shop_id}/receipts?limit=25&offset=0
x-api-key: your-api-key
Authorization: Bearer <access_token>
```

**Query Parameters:**
- `limit` - Number of results (default: 25)
- `offset` - Pagination offset (default: 0)
- `min_created` - Minimum creation timestamp
- `max_created` - Maximum creation timestamp
- `was_paid` - Filter by payment status (true/false)
- `was_shipped` - Filter by shipping status (true/false)

#### Get Specific Receipt
```http
GET /v3/application/shops/{shop_id}/receipts/{receipt_id}
x-api-key: your-api-key
Authorization: Bearer <access_token>
```

#### Update Receipt
```http
PUT /v3/application/shops/{shop_id}/receipts/{receipt_id}
x-api-key: your-api-key
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "was_shipped": true,
  "was_paid": true
}
```

### Listing Endpoints

#### List Shop Listings
```http
GET /v3/application/shops/{shop_id}/listings?state=active&limit=25&offset=0
x-api-key: your-api-key
Authorization: Bearer <access_token>
```

**Query Parameters:**
- `state` - Listing state (default: "active")
- `limit` - Number of results (default: 25)
- `offset` - Pagination offset (default: 0)

#### Get Specific Listing
```http
GET /v3/application/listings/{listing_id}
x-api-key: your-api-key
Authorization: Bearer <access_token>
```

#### Create Listing
```http
POST /v3/application/shops/{shop_id}/listings
x-api-key: your-api-key
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "title": "New Product",
  "description": "Product description",
  "price": {
    "amount": 2000,
    "divisor": 100,
    "currency_code": "USD"
  },
  "quantity": 10,
  "who_made": "i_did",
  "when_made": "made_to_order",
  "taxonomy_id": 1
}
```

#### Update Listing
```http
PUT /v3/application/shops/{shop_id}/listings/{listing_id}
x-api-key: your-api-key
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "title": "Updated Title",
  "quantity": 5
}
```

### Utility Endpoints

#### Health Check
```http
GET /v3/application/openapi-ping
```

## Using the Python Client

```python
from mock_etsy_client import MockEtsyClient

# Initialize client
client = MockEtsyClient(api_key="your-api-key")

# Get access token
client.get_access_token()

# Get shop info
shop = client.get_shop(12345678)
print(f"Shop: {shop['shop_name']}")

# Get receipts (orders)
receipts = client.get_shop_receipts(12345678, limit=10)
for receipt in receipts['results']:
    print(f"Order #{receipt['receipt_id']}: ${receipt['grandtotal']['amount']/100:.2f}")

# Get listings
listings = client.get_shop_listings(12345678)
for listing in listings['results']:
    print(f"{listing['title']}: ${listing['price']['amount']/100:.2f}")

# Create a new listing
new_listing = client.create_listing(
    shop_id=12345678,
    title="My New Product",
    description="A wonderful handmade item",
    price={"amount": 2500, "divisor": 100, "currency_code": "USD"},
    quantity=5
)

# Update a receipt
client.update_receipt(12345678, 1000000001, was_shipped=True)
```

## Integration with Discord Bot

You can use this mock API with your Discord bot during development:

```python
from mock_etsy_client import MockEtsyClient

# In your Discord bot
etsy_client = MockEtsyClient()
etsy_client.get_access_token()

# Use in commands
@bot.command()
async def orders(ctx):
    receipts = etsy_client.get_shop_receipts(12345678, limit=5)
    for receipt in receipts['results']:
        await ctx.send(f"Order #{receipt['receipt_id']}: ${receipt['grandtotal']['amount']/100:.2f}")
```

## Differences from Real Etsy API

This mock API is designed to be as close to the real Etsy API v3 as possible, but there are some simplifications:

1. **Authentication** - Simplified OAuth flow (no actual authorization page)
2. **Data Persistence** - Data is stored in memory and resets on server restart
3. **Validation** - Less strict validation than the real API
4. **Rate Limiting** - No rate limiting implemented
5. **Webhooks** - Not implemented
6. **Image Upload** - Not implemented

## Switching to Real Etsy API

When your Etsy API key is activated, you can easily switch by:

1. Update the `base_url` in your client:
   ```python
   client = MockEtsyClient(
       api_key="your-real-api-key",
       base_url="https://api.etsy.com"
   )
   ```

2. Implement proper OAuth2 flow with real authorization codes
3. Use your actual shop ID and user ID

## Resources

- [Etsy API v3 Documentation](https://developer.etsy.com/documentation/)
- [Etsy API Reference](https://developer.etsy.com/documentation/reference/)
- [OAuth 2.0 Specification](https://tools.ietf.org/html/rfc6749)

## Troubleshooting

### Server won't start
- Make sure port 5000 is available
- Check that Flask is installed: `pip install -r requirements.txt`

### Authentication errors
- Ensure you're including both `x-api-key` and `Authorization` headers
- Get a fresh access token if expired

### No data returned
- Verify you're using the correct shop ID (12345678)
- Check that the mock server is running on localhost:5000

## License

This mock API is for development and testing purposes only. Not affiliated with Etsy.
