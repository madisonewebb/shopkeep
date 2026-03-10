# Shopkeep Setup & Deployment Guide

## What's Been Done

### 1. Real Etsy API Migration (`migrate-etsy` → merged into `multi-tenant`)
- Rewrote `src/etsy/client.py` as `EtsyClient` targeting the real Etsy API v3
- OAuth 2.0 PKCE flow, auto token refresh, 429 rate limit handling
- Tokens persisted in SQLite DB, auto-refreshed by the bot — no manual renewal needed
- `scripts/etsy_auth.py` — CLI helper for local dev only; replaced by the website in production

### 2. Multi-Tenant Support (`multi-tenant` branch)
- **DB**: Added `guilds` and `etsy_tokens` tables for per-guild shop connections
- **Bot**: Per-guild `EtsyClient` registry; poll loop iterates all connected guilds
- **`on_guild_join`**: Creates guild record + DMs server owner a unique setup link
- **`on_ready`**: Detects guilds the bot is already in but hasn't registered yet (e.g. existing servers, or added while bot was offline) — creates their record and DMs the owner automatically
- **New commands**: `!setchannel`, `!status`; `!shop` and `!orders` scoped per guild
- **Web server** (`src/web/`): Flask app — landing page, Etsy PKCE OAuth connect flow, success/error pages
- **Docker**: Added `Dockerfile.web`
- **k8s**: Added `manifests/web-deployment.yaml` (Deployment + ClusterIP Service)
- **Domain**: `shopkeepbot.com` purchased
- **Etsy developer portal**: `https://shopkeepbot.com/callback/etsy` registered as redirect URI
- **Discord**: `DISCORD_CLIENT_ID` obtained

---

## How `scripts/etsy_auth.py` relates to the website

The CLI script and the website do the same thing — Etsy PKCE OAuth → save tokens + shop ID to DB.

| | `scripts/etsy_auth.py` | Website (`/connect/<token>`) |
|---|---|---|
| Intended for | Local dev, testing | End users |
| Triggered by | Running the script manually | Bot DM after joining a server |
| Writes to | `.env` + DB tokens table | DB `etsy_tokens` + `guilds` tables |
| Still needed? | For local dev only | Yes — this is the production flow |

When the bot starts fresh in production and finds a server it's already in, it DMs the server owner a link to `/connect/<token>` automatically.

---

## User Flow (once live)

1. Etsy seller visits `https://shopkeepbot.com`
2. Clicks **"Add to Discord"** → bot joins their server
3. Bot DMs the server owner a link: `https://shopkeepbot.com/connect/<token>`
4. Owner enters their Etsy shop name → clicks "Authorize with Etsy"
5. Etsy OAuth completes → tokens + shop ID saved to DB
6. Owner types `!setchannel` in Discord to choose the notifications channel
7. New orders post automatically every 60 seconds

---

## Still To Do (when home on the network)

### 1. DNS
Point `shopkeepbot.com` to your k3s cluster's external IP.
- `A` record: `shopkeepbot.com` → `<cluster-ip>`
- `A` record: `www.shopkeepbot.com` → `<cluster-ip>` (optional)

### 2. Ingress manifest
Ask Claude to write `manifests/ingress.yaml` — confirm your ingress controller first (`nginx` assumed). Needs cert-manager for automatic TLS via Let's Encrypt.

### 3. Add new secrets to k8s
Add these to the `shopkeep-secrets` Secret:

| Key | Value |
|---|---|
| `DISCORD_CLIENT_ID` | Your Discord application ID |
| `WEB_BASE_URL` | `https://shopkeepbot.com` |
| `ETSY_WEB_REDIRECT_URI` | `https://shopkeepbot.com/callback/etsy` |
| `ETSY_API_KEY` | Already set |
| `ETSY_SHARED_SECRET` | Already set |

```bash
kubectl create secret generic shopkeep-secrets \
  --namespace shopkeep \
  --from-env-file=.env \
  --dry-run=client -o yaml | kubectl apply -f -
```

### 4. Add web image to GitHub Actions CI
A second Docker image (`shopkeep-web`) needs to be built and pushed alongside the bot image. Add to your existing workflow:

```yaml
- name: Build and push web image
  uses: docker/build-push-action@v5
  with:
    context: .
    file: docker/Dockerfile.web
    push: true
    tags: ghcr.io/madisonewebb/shopkeep-web:latest
```

### 5. Deploy
```bash
kubectl apply -k manifests/
```

---

## Environment Variables Reference

| Variable | Used by | Value |
|---|---|---|
| `DISCORD_BOT_TOKEN` | bot | Discord bot token |
| `DISCORD_CLIENT_ID` | bot, web | Discord application ID |
| `ETSY_API_KEY` | bot, web | Etsy keystring |
| `ETSY_SHARED_SECRET` | bot, web | Etsy shared secret |
| `WEB_BASE_URL` | bot, web | `https://shopkeepbot.com` |
| `ETSY_WEB_REDIRECT_URI` | web | `https://shopkeepbot.com/callback/etsy` |
| `POLL_INTERVAL_SECS` | bot | Default: `60` |
| `DB_PATH` | bot, web | `/app/data/shopkeep.db` |

---

## Branch History

| Branch | Status | Description |
|---|---|---|
| `main` | Stable | Original single-tenant mock API bot |
| `migrate-etsy` | Complete, merged | Real Etsy API v3 integration |
| `multi-tenant` | In progress | Multi-tenant + website onboarding |
