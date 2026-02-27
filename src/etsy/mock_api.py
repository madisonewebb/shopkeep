"""
Mock Etsy API v3 Server
Mimics the real Etsy API v3 for development and testing purposes.
Based on: https://developer.etsy.com/documentation/
"""

from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import secrets
import hashlib
import base64
from functools import wraps

app = Flask(__name__)

# Mock data storage
mock_tokens = {}
mock_shops = {}
mock_receipts = {}
mock_listings = {}

# Initialize sample data
def init_sample_data():
    """Initialize sample shop, receipts, and listings data"""

    # Sample shop
    mock_shops[12345678] = {
        "shopId": 12345678,
        "shopName": "TestShopName",
        "userId": 87654321,
        "createDate": 1234567890,
        "title": "My Awesome Test Shop",
        "announcement": "Welcome to my shop!",
        "currencyCode": "USD",
        "isVacation": False,
        "vacationMessage": None,
        "saleMessage": "Thank you for your purchase!",
        "digitalSaleMessage": "Thank you for your digital purchase!",
        "updateDate": int(datetime.now().timestamp()),
        "listingActiveCount": 5,
        "digitalListingCount": 2,
        "loginName": "testshopowner",
        "acceptsCustomRequests": True,
        "policyWelcome": "Welcome to my shop!",
        "policyPayment": "We accept all major payment methods.",
        "policyShipping": "Items ship within 1-3 business days.",
        "policyRefunds": "Returns accepted within 30 days.",
        "policyAdditional": "Please contact us with any questions.",
        "policyPrivacy": "Your privacy is important to us.",
        "vacationAutoreply": None,
        "url": "https://www.etsy.com/shop/TestShopName",
        "imageUrl760x100": "https://example.com/shop-banner.jpg",
        "numFavorers": 150,
        "languages": ["en-US"],
        "iconUrlFullxfull": "https://example.com/shop-icon.jpg",
        "isUsingStructuredPolicies": True,
        "hasOnboardedStructuredPolicies": True,
        "hasUnstructuredPolicies": False,
        "policyUpdateDate": int(datetime.now().timestamp()),
        "shopLocationCountryIso": "US",
    }

    # Sample receipts (orders)
    for i in range(1, 4):
        receipt_id = 1000000000 + i
        mock_receipts[receipt_id] = {
            "receiptId": receipt_id,
            "shopId": 12345678,
            "receiptType": 0,
            "sellerUserId": 87654321,
            "sellerEmail": "seller@example.com",
            "buyerUserId": 99999999 + i,
            "buyerEmail": f"buyer{i}@example.com",
            "name": f"Test Buyer {i}",
            "firstLine": f"{100 + i} Main Street",
            "secondLine": f"Apt {i}",
            "city": "New York",
            "state": "NY",
            "zip": "10001",
            "status": "paid" if i < 3 else "processing",
            "formattedAddress": f"{100 + i} Main Street\nApt {i}\nNew York, NY 10001\nUnited States",
            "countryIso": "US",
            "paymentMethod": "paypal",
            "paymentEmail": f"buyer{i}@example.com",
            "messageFromSeller": None,
            "messageFromBuyer": f"Please ship quickly! - Buyer {i}",
            "messageFromPayment": None,
            "isPaid": True,
            "isShipped": i == 1,
            "createTimestamp": int((datetime.now() - timedelta(days=i)).timestamp()),
            "createdTimestamp": int((datetime.now() - timedelta(days=i)).timestamp()),
            "updateTimestamp": int(datetime.now().timestamp()),
            "updatedTimestamp": int(datetime.now().timestamp()),
            "isGift": False,
            "giftMessage": None,
            "grandtotal": {
                "amount": 2500 + (i * 500),
                "divisor": 100,
                "currencyCode": "USD",
            },
            "subtotal": {
                "amount": 2000 + (i * 500),
                "divisor": 100,
                "currencyCode": "USD",
            },
            "totalPrice": {
                "amount": 2500 + (i * 500),
                "divisor": 100,
                "currencyCode": "USD",
            },
            "totalShippingCost": {
                "amount": 500,
                "divisor": 100,
                "currencyCode": "USD",
            },
            "totalTaxCost": {
                "amount": 0,
                "divisor": 100,
                "currencyCode": "USD",
            },
            "totalVatCost": {
                "amount": 0,
                "divisor": 100,
                "currencyCode": "USD",
            },
            "discountAmt": {
                "amount": 0,
                "divisor": 100,
                "currencyCode": "USD",
            },
            "giftWrapPrice": {
                "amount": 0,
                "divisor": 100,
                "currencyCode": "USD",
            },
            "shipments": [],
            "transactions": [],
        }

    # Sample listings
    for i in range(1, 6):
        listing_id = 2000000000 + i
        mock_listings[listing_id] = {
            "listingId": listing_id,
            "userId": 87654321,
            "shopId": 12345678,
            "title": f"Handmade Test Product {i}",
            "description": f"This is a beautiful handmade product number {i}. Made with love and care.",
            "state": "active",
            "creationTimestamp": int((datetime.now() - timedelta(days=30)).timestamp()),
            "createdTimestamp": int((datetime.now() - timedelta(days=30)).timestamp()),
            "endingTimestamp": int((datetime.now() + timedelta(days=90)).timestamp()),
            "originalCreationTimestamp": int((datetime.now() - timedelta(days=30)).timestamp()),
            "lastModifiedTimestamp": int(datetime.now().timestamp()),
            "updatedTimestamp": int(datetime.now().timestamp()),
            "stateTimestamp": int(datetime.now().timestamp()),
            "quantity": 10 + i,
            "shopSectionId": 30000000 + i,
            "featuredRank": -1,
            "url": f"https://www.etsy.com/listing/{listing_id}/handmade-test-product-{i}",
            "numFavorers": 10 + (i * 5),
            "nonTaxable": False,
            "isTaxable": True,
            "isCustomizable": i % 2 == 0,
            "isPersonalizable": i % 2 == 0,
            "personalizationIsRequired": False,
            "personalizationCharCountMax": 50 if i % 2 == 0 else None,
            "personalizationInstructions": "Please provide personalization details" if i % 2 == 0 else None,
            "listingType": "physical",
            "tags": ["handmade", "gift", f"product{i}"],
            "materials": ["wood", "fabric", "metal"],
            "shippingProfileId": 40000000 + i,
            "returnPolicyId": 50000000,
            "processingMin": 1,
            "processingMax": 3,
            "whoMade": "i_did",
            "whenMade": "made_to_order",
            "isSupply": False,
            "itemWeight": 100 + (i * 10),
            "itemWeightUnit": "oz",
            "itemLength": 5.0 + i,
            "itemWidth": 3.0 + i,
            "itemHeight": 2.0 + i,
            "itemDimensionsUnit": "in",
            "isPrivate": False,
            "style": ["Minimalist", "Modern"],
            "fileData": "",
            "hasVariations": False,
            "shouldAutoRenew": True,
            "language": "en-US",
            "price": {
                "amount": 1500 + (i * 500),
                "divisor": 100,
                "currencyCode": "USD",
            },
            "taxonomyId": 1000 + i,
            "productionPartners": [],
            "skus": [],
            "views": 100 + (i * 50),
            "isDigital": i > 3,
        }


init_sample_data()


# Authentication decorator
def require_auth(f):
    """Decorator to require valid OAuth token"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check for x-api-key header
        api_key = request.headers.get('x-api-key')
        if not api_key:
            return jsonify({"error": "Missing x-api-key header"}), 401

        # Check for Authorization header (for endpoints requiring OAuth)
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401

        token = auth_header.replace('Bearer ', '')
        if token not in mock_tokens:
            return jsonify({"error": "Invalid access token"}), 401

        # Add token info to request context
        request.token_info = mock_tokens[token]
        return f(*args, **kwargs)
    return decorated_function


# OAuth2 Endpoints
@app.route('/v3/public/oauth/token', methods=['POST'])
def oauth_token():
    """
    Mock OAuth2 token endpoint
    POST /v3/public/oauth/token
    """
    grant_type = request.form.get('grant_type')

    if grant_type == 'authorization_code':
        code = request.form.get('code')
        client_id = request.form.get('client_id')
        redirect_uri = request.form.get('redirect_uri')
        code_verifier = request.form.get('code_verifier')

        # Generate mock access token
        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(32)

        # Store token with metadata
        mock_tokens[access_token] = {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": refresh_token,
            "user_id": 87654321,
            "shop_id": 12345678,
            "scopes": ["shops_r", "shops_w", "transactions_r", "transactions_w", "listings_r", "listings_w"],
        }

        return jsonify({
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": refresh_token,
        })

    elif grant_type == 'refresh_token':
        refresh_token = request.form.get('refresh_token')

        # Find existing token by refresh token
        old_token_info = None
        for token, info in mock_tokens.items():
            if info.get('refresh_token') == refresh_token:
                old_token_info = info
                break

        if not old_token_info:
            return jsonify({"error": "Invalid refresh token"}), 401

        # Generate new access token
        new_access_token = secrets.token_urlsafe(32)
        new_refresh_token = secrets.token_urlsafe(32)

        mock_tokens[new_access_token] = {
            "access_token": new_access_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": new_refresh_token,
            "user_id": old_token_info["user_id"],
            "shop_id": old_token_info["shop_id"],
            "scopes": old_token_info["scopes"],
        }

        return jsonify({
            "access_token": new_access_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": new_refresh_token,
        })

    return jsonify({"error": "Unsupported grant_type"}), 400


# Shop Endpoints
@app.route('/v3/application/shops/<int:shop_id>', methods=['GET'])
@require_auth
def get_shop(shop_id):
    """
    Get shop by ID
    GET /v3/application/shops/{shop_id}
    Requires: shops_r scope
    """
    if shop_id not in mock_shops:
        return jsonify({"error": "Shop not found"}), 404

    return jsonify(mock_shops[shop_id])


@app.route('/v3/application/users/<int:user_id>/shops', methods=['GET'])
@require_auth
def get_shops_by_user(user_id):
    """
    Get shops by user ID
    GET /v3/application/users/{user_id}/shops
    Requires: shops_r scope
    """
    user_shops = [shop for shop in mock_shops.values() if shop['userId'] == user_id]

    return jsonify({
        "count": len(user_shops),
        "results": user_shops,
    })


# Receipt (Order) Endpoints
@app.route('/v3/application/shops/<int:shop_id>/receipts', methods=['GET'])
@require_auth
def get_shop_receipts(shop_id):
    """
    Get shop receipts (orders)
    GET /v3/application/shops/{shop_id}/receipts
    Requires: transactions_r scope
    """
    if shop_id not in mock_shops:
        return jsonify({"error": "Shop not found"}), 404

    # Filter receipts by shop
    shop_receipts = [r for r in mock_receipts.values() if r.get('shopId') == shop_id]

    # Handle pagination
    limit = int(request.args.get('limit', 25))
    offset = int(request.args.get('offset', 0))

    # Handle filtering
    min_created = request.args.get('min_created')
    max_created = request.args.get('max_created')
    was_paid = request.args.get('was_paid')
    was_shipped = request.args.get('was_shipped')

    filtered_receipts = shop_receipts

    if min_created:
        filtered_receipts = [r for r in filtered_receipts if r['createTimestamp'] >= int(min_created)]
    if max_created:
        filtered_receipts = [r for r in filtered_receipts if r['createTimestamp'] <= int(max_created)]
    if was_paid is not None:
        filtered_receipts = [r for r in filtered_receipts if r['isPaid'] == (was_paid.lower() == 'true')]
    if was_shipped is not None:
        filtered_receipts = [r for r in filtered_receipts if r['isShipped'] == (was_shipped.lower() == 'true')]

    # Sort by createTimestamp descending
    filtered_receipts.sort(key=lambda x: x['createTimestamp'], reverse=True)

    # Apply pagination
    paginated_receipts = filtered_receipts[offset:offset + limit]

    return jsonify({
        "count": len(filtered_receipts),
        "results": paginated_receipts,
    })


@app.route('/v3/application/shops/<int:shop_id>/receipts/<int:receipt_id>', methods=['GET'])
@require_auth
def get_shop_receipt(shop_id, receipt_id):
    """
    Get a specific receipt
    GET /v3/application/shops/{shop_id}/receipts/{receipt_id}
    Requires: transactions_r scope
    """
    if shop_id not in mock_shops:
        return jsonify({"error": "Shop not found"}), 404

    if receipt_id not in mock_receipts:
        return jsonify({"error": "Receipt not found"}), 404

    return jsonify(mock_receipts[receipt_id])


@app.route('/v3/application/shops/<int:shop_id>/receipts/<int:receipt_id>', methods=['PUT'])
@require_auth
def update_receipt(shop_id, receipt_id):
    """
    Update a receipt
    PUT /v3/application/shops/{shop_id}/receipts/{receipt_id}
    Requires: transactions_w scope
    """
    if shop_id not in mock_shops:
        return jsonify({"error": "Shop not found"}), 404

    if receipt_id not in mock_receipts:
        return jsonify({"error": "Receipt not found"}), 404

    data = request.get_json()
    receipt = mock_receipts[receipt_id]

    # Update allowed fields (request body uses snake_case query-style names)
    if 'was_shipped' in data:
        receipt['isShipped'] = data['was_shipped']
    if 'was_paid' in data:
        receipt['isPaid'] = data['was_paid']

    receipt['updateTimestamp'] = int(datetime.now().timestamp())
    receipt['updatedTimestamp'] = int(datetime.now().timestamp())

    return jsonify(receipt)


# Listing Endpoints
@app.route('/v3/application/shops/<int:shop_id>/listings', methods=['GET'])
@require_auth
def get_shop_listings(shop_id):
    """
    Get shop listings
    GET /v3/application/shops/{shop_id}/listings
    Requires: listings_r scope
    """
    if shop_id not in mock_shops:
        return jsonify({"error": "Shop not found"}), 404

    # Filter listings by shopId
    shop_listings = [listing for listing in mock_listings.values() if listing['shopId'] == shop_id]

    # Handle pagination
    limit = int(request.args.get('limit', 25))
    offset = int(request.args.get('offset', 0))

    # Handle state filter
    state = request.args.get('state', 'active')
    if state:
        shop_listings = [l for l in shop_listings if l['state'] == state]

    # Sort by listingId
    shop_listings.sort(key=lambda x: x['listingId'], reverse=True)

    # Apply pagination
    paginated_listings = shop_listings[offset:offset + limit]

    return jsonify({
        "count": len(shop_listings),
        "results": paginated_listings,
    })


@app.route('/v3/application/shops/<int:shop_id>/listings/active', methods=['GET'])
@require_auth
def get_shop_active_listings(shop_id):
    """
    Get active shop listings
    GET /v3/application/shops/{shop_id}/listings/active
    Requires: listings_r scope
    """
    return get_shop_listings(shop_id)


@app.route('/v3/application/listings/<int:listing_id>', methods=['GET'])
@require_auth
def get_listing(listing_id):
    """
    Get a specific listing
    GET /v3/application/listings/{listing_id}
    Requires: listings_r scope
    """
    if listing_id not in mock_listings:
        return jsonify({"error": "Listing not found"}), 404

    return jsonify(mock_listings[listing_id])


@app.route('/v3/application/shops/<int:shop_id>/listings', methods=['POST'])
@require_auth
def create_listing(shop_id):
    """
    Create a new listing
    POST /v3/application/shops/{shop_id}/listings
    Requires: listings_w scope
    """
    if shop_id not in mock_shops:
        return jsonify({"error": "Shop not found"}), 404

    data = request.get_json()

    # Generate new listing ID
    new_listing_id = max(mock_listings.keys()) + 1 if mock_listings else 2000000001

    new_listing = {
        "listingId": new_listing_id,
        "userId": request.token_info['user_id'],
        "shopId": shop_id,
        "title": data.get('title', 'New Listing'),
        "description": data.get('description', ''),
        "state": "active",
        "creationTimestamp": int(datetime.now().timestamp()),
        "createdTimestamp": int(datetime.now().timestamp()),
        "quantity": data.get('quantity', 1),
        "price": data.get('price', {"amount": 1000, "divisor": 100, "currencyCode": "USD"}),
        "whoMade": data.get('who_made', 'i_did'),
        "whenMade": data.get('when_made', 'made_to_order'),
        "isSupply": data.get('is_supply', False),
        "taxonomyId": data.get('taxonomy_id', 1),
        "shippingProfileId": data.get('shipping_profile_id'),
        "returnPolicyId": data.get('return_policy_id'),
        "processingMin": data.get('processing_min', 1),
        "processingMax": data.get('processing_max', 3),
        "tags": data.get('tags', []),
        "materials": data.get('materials', []),
        "isCustomizable": data.get('is_customizable', False),
        "isPersonalizable": data.get('is_personalizable', False),
        "listingType": data.get('type', 'physical'),
        "shouldAutoRenew": data.get('should_auto_renew', True),
        "isTaxable": data.get('is_taxable', True),
        "url": f"https://www.etsy.com/listing/{new_listing_id}/",
    }

    mock_listings[new_listing_id] = new_listing

    return jsonify(new_listing), 201


@app.route('/v3/application/shops/<int:shop_id>/listings/<int:listing_id>', methods=['PUT', 'PATCH'])
@require_auth
def update_listing(shop_id, listing_id):
    """
    Update a listing
    PUT/PATCH /v3/application/shops/{shop_id}/listings/{listing_id}
    Requires: listings_w scope
    """
    if shop_id not in mock_shops:
        return jsonify({"error": "Shop not found"}), 404

    if listing_id not in mock_listings:
        return jsonify({"error": "Listing not found"}), 404

    data = request.get_json()
    listing = mock_listings[listing_id]

    # Map snake_case request body fields to camelCase listing fields
    field_map = {
        'title': 'title',
        'description': 'description',
        'quantity': 'quantity',
        'price': 'price',
        'state': 'state',
        'tags': 'tags',
        'materials': 'materials',
        'is_customizable': 'isCustomizable',
        'is_personalizable': 'isPersonalizable',
        'processing_min': 'processingMin',
        'processing_max': 'processingMax',
        'taxonomy_id': 'taxonomyId',
        'shipping_profile_id': 'shippingProfileId',
    }

    for src, dst in field_map.items():
        if src in data:
            listing[dst] = data[src]

    listing['lastModifiedTimestamp'] = int(datetime.now().timestamp())
    listing['updatedTimestamp'] = int(datetime.now().timestamp())

    return jsonify(listing)


# Ping endpoint
@app.route('/v3/application/openapi-ping', methods=['GET'])
def ping():
    """
    Health check endpoint
    GET /v3/application/openapi-ping
    """
    return jsonify({
        "application": "mock-etsy-api",
        "version": "3.0.0",
        "timestamp": int(datetime.now().timestamp()),
    })


# Root endpoint
@app.route('/', methods=['GET'])
def root():
    """Root endpoint with API information"""
    return jsonify({
        "name": "Mock Etsy API v3",
        "version": "3.0.0",
        "description": "Mock Etsy API server for development and testing",
        "documentation": "https://developer.etsy.com/documentation/",
        "endpoints": {
            "oauth": "/v3/public/oauth/token",
            "ping": "/v3/application/openapi-ping",
            "shops": "/v3/application/shops/{shop_id}",
            "receipts": "/v3/application/shops/{shop_id}/receipts",
            "listings": "/v3/application/shops/{shop_id}/listings",
        },
    })


if __name__ == '__main__':
    print("=" * 60)
    print("Mock Etsy API v3 Server")
    print("=" * 60)
    print("\nServer starting on http://localhost:5000")
    print("\nSample Data:")
    print(f"  Shop ID: 12345678")
    print(f"  User ID: 87654321")
    print(f"  Receipts: {len(mock_receipts)}")
    print(f"  Listings: {len(mock_listings)}")
    print("\nTo get an access token, POST to:")
    print("  /v3/public/oauth/token")
    print("\nExample headers for authenticated requests:")
    print("  x-api-key: your-api-key")
    print("  Authorization: Bearer <access_token>")
    print("=" * 60)
    print()

    app.run(debug=True, host='0.0.0.0', port=5000)
