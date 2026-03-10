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
- **`on_ready`**: Detects guilds the bot is already in but hasn't registered yet — creates their record and DMs the owner automatically
- **New commands**: `!setchannel`, `!status`; `!shop` and `!orders` scoped per guild
- **Web server** (`src/web/`): Flask app — landing page, Etsy PKCE OAuth connect flow, success/error pages
- **Docker**: Added `Dockerfile.web`; image built as multi-arch (`linux/amd64` + `linux/arm64`)
- **k8s**: Added `manifests/web-deployment.yaml` (Deployment + ClusterIP Service)

### 3. Infrastructure (complete)
- **Domain**: `shopkeepbot.com` purchased
- **DNS**: `@` and `www` A records pointing to home public IP
- **Reverse proxy**: Nginx Proxy Manager on NAS (`10.0.0.28`) routes `shopkeepbot.com` → `shopkeep-web.shopkeep.svc.cluster.local:80`
- **TLS**: Let's Encrypt cert issued via NPM
- **k8s secrets**: All env vars loaded into `shopkeep-secrets`
- **Etsy developer portal**: `https://shopkeepbot.com/callback/etsy` registered as redirect URI
- **Discord**: `DISCORD_CLIENT_ID` set; bot is public
- **Images**: Both `shopkeep` (bot) and `shopkeep-web` pushed to GHCR
- **Deployed**: `shopkeep-bot` and `shopkeep-web` running on k3s cluster

### 4. Cluster details
- Control plane: `k3s-control-plane` at `10.0.0.3` (Ubuntu)
- Worker node: `castillo-nas` at `10.0.0.28` (Debian, also runs NPM + Jellyfin)
- Nginx ingress controller installed but not used — NPM routes directly to the k3s service DNS name
- cert-manager installed with `letsencrypt-prod` ClusterIssuer (NPM handles certs instead)

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

## User Flow (live at shopkeepbot.com)

1. Etsy seller visits `https://shopkeepbot.com`
2. Clicks **"Add to Discord"** → bot joins their server
3. Bot DMs the server owner: `https://shopkeepbot.com/connect/<token>`
4. Owner enters their Etsy shop name → clicks "Authorize with Etsy"
5. Etsy OAuth completes → tokens + shop ID saved to DB
6. Owner types `!setchannel` in Discord to choose the notifications channel
7. New orders post automatically every 60 seconds

---

## Still To Do

### 1. Add web image to GitHub Actions CI
Currently the web image must be built and pushed manually. Add it to the existing workflow so it builds automatically on push:

```yaml
- name: Build and push web image
  uses: docker/build-push-action@v5
  with:
    context: .
    file: docker/Dockerfile.web
    push: true
    platforms: linux/amd64,linux/arm64
    tags: ghcr.io/madisonewebb/shopkeep-web:latest
```

### 2. Test the full onboarding flow end to end
- Add bot to a fresh Discord server
- Confirm DM is received with setup link
- Complete Etsy OAuth on the website
- Run `!setchannel` and confirm orders post

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
| `multi-tenant` | Complete | Multi-tenant + website onboarding — **current production branch** |
