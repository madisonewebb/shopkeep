# Shopkeep Setup & Deployment Guide

## What's Been Done

### 1. Real Etsy API Migration (`migrate-etsy` branch → merged to `multi-tenant`)
- Rewrote `src/etsy/client.py` as `EtsyClient` targeting the real Etsy API v3
- OAuth 2.0 PKCE flow, auto token refresh, 429 rate limit handling
- Added `tokens` table to SQLite DB for token persistence
- Created `scripts/etsy_auth.py` — one-time setup script for non-developers

### 2. Multi-Tenant Support (`multi-tenant` branch)
- **DB**: Added `guilds` and `etsy_tokens` tables for per-guild shop connections
- **Bot**: Refactored to manage N guilds; per-guild `EtsyClient` registry; poll loop iterates all connected guilds
- **on_guild_join**: Bot DMs the server owner with a unique setup link
- **New commands**: `!setchannel`, `!status`; `!shop` and `!orders` now scoped per guild
- **Web server** (`src/web/`): Flask app with landing page, Etsy PKCE OAuth connect flow, success/error pages
- **Docker**: Added `Dockerfile.web`
- **k8s**: Added `manifests/web-deployment.yaml` (Deployment + ClusterIP Service)
- **Domain**: `shopkeepbot.com` purchased
- **Etsy developer portal**: `https://shopkeepbot.com/callback/etsy` added as allowed redirect URI
- **Discord**: `DISCORD_CLIENT_ID` obtained

---

## User Flow (how it works when live)

1. Etsy seller visits `https://shopkeepbot.com`
2. Clicks **"Add to Discord"** → bot joins their server
3. Bot DMs the server owner: `shopkeepbot.com/connect/<token>`
4. Owner enters their Etsy shop name → authorizes with Etsy
5. Tokens + shop ID saved to DB
6. Owner types `!setchannel` in Discord to choose the notifications channel
7. New orders post automatically every 60 seconds

---

## Still To Do

### When back on home network

#### 1. DNS
Point `shopkeepbot.com` to your k3s cluster's external IP.
- Add an `A` record: `shopkeepbot.com` → `<cluster-ip>`
- Add an `A` record: `www.shopkeepbot.com` → `<cluster-ip>` (optional redirect)

#### 2. Ingress manifest
Create `manifests/ingress.yaml` (nginx ingress + cert-manager for TLS).
Ask Claude to write this — just confirm your ingress controller (`nginx` assumed).

Example structure:
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: shopkeep-web
  namespace: shopkeep
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  tls:
  - hosts:
    - shopkeepbot.com
    secretName: shopkeep-tls
  rules:
  - host: shopkeepbot.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: shopkeep-web
            port:
              number: 80
```

#### 3. Add secrets to k8s
The following need to be added to the `shopkeep-secrets` Secret in the cluster:

```
DISCORD_CLIENT_ID=<your Discord application ID>
WEB_BASE_URL=https://shopkeepbot.com
ETSY_WEB_REDIRECT_URI=https://shopkeepbot.com/callback/etsy
ETSY_API_KEY=<already set>
ETSY_SHARED_SECRET=<already set>
```

Update via:
```bash
kubectl create secret generic shopkeep-secrets \
  --namespace shopkeep \
  --from-env-file=.env \
  --dry-run=client -o yaml | kubectl apply -f -
```

#### 4. Build & push web Docker image
A second image needs to be built and pushed for the web server.

Option A — add to your existing GitHub Actions workflow:
```yaml
- name: Build and push web image
  uses: docker/build-push-action@v5
  with:
    context: .
    file: docker/Dockerfile.web
    push: true
    tags: ghcr.io/madisonewebb/shopkeep-web:latest
```

Option B — build manually:
```bash
docker build -f docker/Dockerfile.web -t ghcr.io/madisonewebb/shopkeep-web:latest .
docker push ghcr.io/madisonewebb/shopkeep-web:latest
```

#### 5. Deploy
```bash
kubectl apply -k manifests/
```

---

## New Environment Variables (reference)

| Variable | Used by | Description |
|---|---|---|
| `DISCORD_BOT_TOKEN` | bot | Discord bot token |
| `DISCORD_CLIENT_ID` | bot, web | Discord application ID |
| `ETSY_API_KEY` | bot, web | Etsy keystring |
| `ETSY_SHARED_SECRET` | bot, web | Etsy shared secret |
| `WEB_BASE_URL` | bot, web | `https://shopkeepbot.com` |
| `ETSY_WEB_REDIRECT_URI` | web | `https://shopkeepbot.com/callback/etsy` |
| `POLL_INTERVAL_SECS` | bot | Default: 60 |
| `DB_PATH` | bot, web | Path to SQLite file |

---

## Branch History

| Branch | Status | Description |
|---|---|---|
| `main` | Stable | Original single-tenant mock API bot |
| `migrate-etsy` | Merged into multi-tenant | Real Etsy API v3 integration |
| `multi-tenant` | In progress | Multi-tenant + website onboarding |
