# Shopkeep

[![Deploy](https://github.com/madisonewebb/shopkeep/actions/workflows/deploy.yml/badge.svg)](https://github.com/madisonewebb/shopkeep/actions/workflows/deploy.yml)

A Discord bot that posts Etsy order notifications to your server.

---

## What it does

- Polls your Etsy shop every 60 seconds for new orders
- Posts order notifications to a Discord channel as embeds
- Persists shop, listing, and order data in SQLite

## Bot commands

| Command | Description |
|---|---|
| `!shop` | Shows your shop name, location, total sales, and rating |
| `!orders` | Lists open orders with buyer, total, and shipping status |

See [`src/bot/COMMANDS.md`](src/bot/COMMANDS.md) for details.

---

## Getting started

### Prerequisites

- Docker & [Tilt](https://tilt.dev/)
- Discord bot token ([create one here](https://discord.com/developers/applications))

### Run locally

1. Clone the repo:

   ```bash
   git clone https://github.com/madisonewebb/shopkeep.git
   cd shopkeep
   ```

2. Set up your environment:

   ```bash
   cp .env.example .env
   # Fill in DISCORD_BOT_TOKEN and ORDER_CHANNEL_ID
   ```

3. Start everything:

   ```bash
   tilt up
   ```

   This builds the Docker images, starts the mock Etsy API and the bot, and watches for file changes with auto-reload.

4. To stop:

   ```bash
   tilt down
   ```

### Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DISCORD_BOT_TOKEN` | Yes | — | Discord bot token |
| `ORDER_CHANNEL_ID` | Yes | — | Discord channel ID for notifications |
| `ETSY_API_URL` | No | `http://localhost:5000` | Etsy API base URL |
| `ETSY_SHOP_ID` | No | `12345678` | Shop ID to monitor |
| `POLL_INTERVAL_SECS` | No | `60` | Polling frequency in seconds |
| `DB_PATH` | No | `./shopkeep.db` | SQLite database path |

---

## Mock Etsy API

A mock Etsy API is included so you can develop without real credentials.

Tilt starts it automatically, or you can run it manually:

```bash
task mock-api   # runs on http://localhost:5000
```

See [`MOCK_ETSY_API.md`](MOCK_ETSY_API.md) for full documentation.

---

## Deployment

Pushes to `main` trigger a GitHub Actions deploy to a k3s cluster.

- Docker images are published to GHCR: `ghcr.io/madisonewebb/shopkeep`
- Manifests are applied via Kustomize from `manifests/`
- Before the first deploy, apply the SQLite PVC manually:

  ```bash
  kubectl apply -f manifests/pvc.yaml
  ```

---

## Disclaimer

Shopkeep is not affiliated with or endorsed by Etsy or Discord. This project is for educational use.

---

**Madison Webb**
