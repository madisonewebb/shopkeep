# Shopkeep

[![Deploy](https://github.com/madisonewebb/shopkeep/actions/workflows/deploy.yml/badge.svg)](https://github.com/madisonewebb/shopkeep/actions/workflows/deploy.yml)

A multi-tenant Discord bot that posts Etsy order notifications to your server. Each Discord server connects to its own Etsy shop via OAuth.

**Website:** [shopkeepbot.com](https://shopkeepbot.com)

---

![Capstone Poster](assets/poster.png)

*Sal (Shopkeep's mascot) artwork by Katie Castillo*

---

## What it does

- Guild owners authenticate their Etsy shop through a web onboarding flow
- Polls each connected shop every 60 seconds for new orders
- Posts order notifications to a configured Discord channel as embeds
- Persists shop, listing, and order data in SQLite

## How it works

1. Add the bot to your Discord server
2. The bot DMs the server owner a link to the setup page
3. The owner logs in with Etsy and authorizes the bot
4. The bot starts polling for new orders and posts notifications

Each Discord server is independent — different servers can monitor different Etsy shops.

---

## Getting started

### Add to your server

Visit [shopkeepbot.com](https://shopkeepbot.com) to add Shopkeep to your Discord server. Full command reference is at [shopkeepbot.com/commands](https://shopkeepbot.com/commands).

### Prerequisites (self-hosting)

- Docker & [Tilt](https://tilt.dev/)
- A Discord bot token ([create one here](https://discord.com/developers/applications))
- An Etsy API key ([apply here](https://www.etsy.com/developers/register))

### Run locally

1. Clone the repo:

   ```bash
   git clone https://github.com/madisonewebb/shopkeep.git
   cd shopkeep
   ```

2. Set up your environment:

   ```bash
   cp .env.example .env
   # Fill in the required values (see Environment variables below)
   ```

3. Start everything:

   ```bash
   tilt up
   ```

   This builds the Docker images, starts the bot and web server, and watches for file changes with auto-reload.

4. To stop:

   ```bash
   tilt down
   ```

### Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DISCORD_BOT_TOKEN` | Yes | — | Discord bot token |
| `DISCORD_CLIENT_ID` | Yes | — | Discord application client ID |
| `ETSY_API_KEY` | Yes | — | Etsy keystring from developer.etsy.com |
| `ETSY_SHARED_SECRET` | Yes | — | Etsy shared secret |
| `WEB_BASE_URL` | Yes | — | Public URL of the web server (no trailing slash) |
| `ETSY_WEB_REDIRECT_URI` | Yes | — | Etsy OAuth callback URL (e.g. `{WEB_BASE_URL}/callback/etsy`) |
| `POLL_INTERVAL_SECS` | No | `60` | Polling frequency in seconds |
| `DB_PATH` | No | `./shopkeep.db` | SQLite database path |

---

## Deployment

Merging a Release Please PR triggers a versioned release and deploy to k3s.

- Docker images are published to GHCR: `ghcr.io/madisonewebb/shopkeep`
- Manifests are applied via Kustomize from `manifests/`
- The cluster is updated to run the specific release version (e.g. `v1.0.0`)

### First-time setup

1. Apply the SQLite PVC:

   ```bash
   kubectl apply -f manifests/pvc.yaml
   ```

2. Create the `shopkeep-secrets` Kubernetes secret with all required env vars:

   ```bash
   kubectl create secret generic shopkeep-secrets \
     --namespace shopkeep \
     --from-literal=DISCORD_BOT_TOKEN=... \
     --from-literal=DISCORD_CLIENT_ID=... \
     --from-literal=ETSY_API_KEY=... \
     --from-literal=ETSY_SHARED_SECRET=... \
     --from-literal=WEB_BASE_URL=... \
     --from-literal=ETSY_WEB_REDIRECT_URI=...
   ```

---

## Disclaimer

Shopkeep is not affiliated with or endorsed by Etsy or Discord. This project is for educational use.

---

**Madison Webb**
