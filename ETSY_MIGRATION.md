# Migrating from Mock Etsy API to Real Etsy API v3

## Overview

The project was built against a local mock Etsy API (`src/etsy/mock_api.py`) that deliberately mirrors
the real Etsy OpenAPI v3 field names (snake_case). This makes migration straightforward — the data
shapes are already correct.

## What Stays the Same

- All DB column names (snake_case, matching Etsy v3)
- All method signatures in `src/etsy/client.py`
- `notifier.py` embed building
- `discord_bot.py` poll/bootstrap logic
- Mock API can remain for local dev/testing

## What Needs to Change

### 1. Etsy Client (`src/etsy/client.py`)

| Now | After Migration |
|-----|----------------|
| Class named `MockEtsyClient` | Rename to `EtsyClient` |
| `base_url = "http://localhost:5000"` | `base_url = "https://openapi.etsy.com/v3"` |
| Fake OAuth (`grant_type=authorization_code`, no PKCE) | Real OAuth 2.0 with PKCE |
| No rate limit handling | Add retry/backoff on 429 |
| No auth headers on requests | Add `x-api-key: <keystring>` header |

### 2. Authentication: OAuth 2.0 with PKCE

The real Etsy API does **not** use a client secret. It uses PKCE (Proof Key for Code Exchange).

**Flow summary:**
1. Generate a `code_verifier` (random 32-byte URL-safe string)
2. Derive `code_challenge = base64url(sha256(code_verifier))`
3. Redirect user to Etsy auth URL with `code_challenge`
4. User authorizes → Etsy redirects to your callback with `code`
5. Exchange `code` + `code_verifier` for `access_token` + `refresh_token`
6. Store tokens securely; refresh when expired (access tokens last 3600s)

**Required scopes for this bot:**
- `transactions_r` — read orders/receipts
- `listings_r` — read shop listings
- `shops_r` — read shop info (may be implicit)

**Etsy OAuth endpoints:**
- Auth URL: `https://www.etsy.com/oauth/connect`
- Token URL: `https://api.etsy.com/v3/public/oauth/token`

### 3. Request Authentication Headers

Every request to the real API needs two things:

```
x-api-key: <your_keystring>
Authorization: Bearer <access_token>
```

Public endpoints (no user auth needed) only require `x-api-key`.

### 4. Environment Variables

Add to `.env`:

```env
# Real Etsy API credentials
ETSY_API_KEY=<your_keystring_from_developer_portal>
ETSY_ACCESS_TOKEN=<oauth_access_token>
ETSY_REFRESH_TOKEN=<oauth_refresh_token>
ETSY_SHOP_ID=<your_real_shop_id>

# Keep pointing at real API
ETSY_API_URL=https://openapi.etsy.com/v3
```

Token storage: for a bot that runs continuously, tokens should be persisted to DB or a file so
refresh survives restarts. See "Token Persistence" below.

### 5. Rate Limiting

The real Etsy API enforces rate limits. At minimum, add handling for `HTTP 429`:

```python
import time

def _request(self, method, path, **kwargs):
    resp = self.session.request(method, path, **kwargs)
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", 10))
        time.sleep(retry_after)
        resp = self.session.request(method, path, **kwargs)
    resp.raise_for_status()
    return resp.json()
```

## Token Persistence

The bot runs as a long-lived process. Access tokens expire after 1 hour. Options:

1. **Simple (env/file):** Store tokens in `.env` or a `tokens.json`; reload on startup; refresh when
   a 401 is received.
2. **DB (recommended):** Add a `tokens` table to `db.py`. The bot already uses SQLite — store
   `access_token`, `refresh_token`, and `expires_at` there.

Recommended DB approach (add to `db.py`):
```sql
CREATE TABLE IF NOT EXISTS tokens (
    id INTEGER PRIMARY KEY CHECK (id = 1),  -- singleton row
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at INTEGER NOT NULL             -- unix timestamp
);
```

## Migration Steps (in order)

1. **Get credentials** — Obtain `keystring` from Etsy developer portal.
2. **Run OAuth flow once** — Manually complete PKCE flow to get initial tokens. Can use a small
   helper script or a tool like Postman.
3. **Add token table to DB** — Seed with initial tokens.
4. **Rewrite `EtsyClient`** — Update base URL, add auth headers, add token refresh logic, add
   rate limit handling.
5. **Update `.env`** — Add `ETSY_API_KEY`, real `ETSY_SHOP_ID`.
6. **Update `discord_bot.py`** — Import `EtsyClient` instead of `MockEtsyClient`.
7. **Test against real API** — Run bot pointed at real API with real shop.
8. **Keep mock for CI/local dev** — `ETSY_API_URL=http://localhost:5000` still works with mock.

## Files to Change

| File | Change |
|------|--------|
| `src/etsy/client.py` | Rewrite client class for real auth + rate limits |
| `src/bot/discord_bot.py` | Import `EtsyClient`; load API key from env |
| `src/bot/db.py` | Add `tokens` table |
| `.env.example` | Add `ETSY_API_KEY`, `ETSY_ACCESS_TOKEN`, `ETSY_REFRESH_TOKEN` |
| `requirements.txt` | No new deps needed (requests already present) |

## Files That Do NOT Change

- `src/bot/notifier.py` — field names already match
- `src/bot/db.py` (schema) — column names already match
- `src/etsy/mock_api.py` — keep for local dev
- Kubernetes manifests — only env vars change

## Current Status

- [x] `keystring` (API key) — available
- [x] `shared_secret` — available (used as client_secret in token exchange)
- [x] Scopes — `transactions_r`, `listings_r`, `shops_r`, `profile_r`
- [x] Shop name — `CastilloCurios` (numeric `shop_id` resolved by OAuth helper)
- [ ] OAuth step not yet completed — run `scripts/etsy_auth.py` first
- [ ] `ETSY_REDIRECT_URI` — must match what's registered in Etsy developer portal
- [ ] Token persistence strategy — TBD (DB recommended)

## Running the OAuth Helper

Once you know your registered redirect URI, add it to `.env` and run:

```bash
# .env additions needed before running:
# ETSY_API_KEY=your_keystring
# ETSY_SHARED_SECRET=your_shared_secret
# ETSY_REDIRECT_URI=http://localhost:3000/callback   ← match your registered URI

python scripts/etsy_auth.py
```

This will open a browser, complete the PKCE flow, look up your numeric `shop_id`, and print the
values to add to `.env`.
