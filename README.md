# Shopkeep

[![Deploy](https://github.com/madisonewebb/shopkeep/actions/workflows/deploy.yml/badge.svg)](https://github.com/madisonewebb/shopkeep/actions/workflows/deploy.yml)

Shopkeep is a Discord bot that integrates with the Etsy API to deliver real-time shop order notifications directly into a Discord server.

---

## Features

- Real-time Etsy order notifications via Discord embeds
- Order polling every 60 seconds (configurable)
- SQLite persistence for orders, shops, and listings
- Mock Etsy API for development without live credentials
- Kubernetes deployment with k3s and Kustomize

---

## Tech Stack

- **Python** — backend and bot logic
- **discord.py** — Discord API integration
- **Etsy API** — shop, order, and listing data
- **SQLite** — async data persistence via aiosqlite
- **Docker** — containerized development and deployment
- **Tilt** — local container orchestration
- **Kubernetes / k3s** — production deployment
- **Kustomize** — Kubernetes manifest management
- **GitHub Actions** — CI/CD

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DISCORD_BOT_TOKEN` | Yes | — | Discord bot token |
| `ORDER_CHANNEL_ID` | Yes | `0` | Discord channel ID for order notifications |
| `ETSY_API_URL` | No | `http://localhost:5000` | Etsy API base URL |
| `ETSY_SHOP_ID` | No | `12345678` | Shop ID to monitor |
| `POLL_INTERVAL_SECS` | No | `60` | Order polling frequency in seconds |
| `DB_PATH` | No | `./shopkeep.db` | SQLite database path |

---

## Getting Started

### Prerequisites

- Python 3.10+
- [Task](https://taskfile.dev/) — task runner
- Discord bot token ([get one here](https://discord.com/developers/applications))
- **OR** Docker & [Tilt](https://tilt.dev/) for containerized development

### Option 1: Tilt (Recommended)

1. **Clone the repository:**

   ```bash
   git clone https://github.com/madisonewebb/shopkeep.git
   cd shopkeep
   ```

2. **Set up environment variables:**

   ```bash
   cp .env.example .env
   # Fill in DISCORD_BOT_TOKEN and ORDER_CHANNEL_ID
   ```

3. **Start Tilt:**

   ```bash
   tilt up
   ```

   This will build the Docker images, start the mock Etsy API and bot, and watch for file changes with auto-reload.

4. **Stop Tilt:**

   ```bash
   tilt down
   ```

### Option 2: Docker Compose

1. **Clone and configure:**

   ```bash
   git clone https://github.com/madisonewebb/shopkeep.git
   cd shopkeep
   cp .env.example .env
   ```

2. **Start services:**

   ```bash
   docker compose up
   ```

### Option 3: Local Python

1. **Install dependencies:**

   ```bash
   task install-dev
   ```

2. **Set up environment variables:**

   ```bash
   cp .env.example .env
   ```

3. **Install pre-commit hooks:**

   ```bash
   task setup-hooks
   ```

4. **Run the bot:**

   ```bash
   task run
   ```

---

## Mock Etsy API

While waiting for your Etsy API key activation, use the included mock Etsy API server for development and testing.

1. **Start the mock API server:**

   ```bash
   task mock-api
   ```

   Server runs on `http://localhost:5000`

2. **Test the mock API:**

   ```bash
   task test-mock-api
   ```

See [`MOCK_ETSY_API.md`](MOCK_ETSY_API.md) for full documentation.

---

## Development

### Available Tasks

```bash
task help
```

| Command | Description |
|---|---|
| `task install` | Install production dependencies |
| `task install-dev` | Install all dependencies |
| `task setup-hooks` | Install pre-commit git hooks |
| `task run` | Run the Discord bot |
| `task mock-api` | Run the mock Etsy API server |
| `task test-mock-api` | Test the mock Etsy API |
| `task format` | Auto-format code (ruff + black) |
| `task lint` | Run all linters |
| `task pre-commit` | Run pre-commit on all files |
| `task clean` | Clean Python cache files |

### Code Quality

- **ruff** — fast Python linter
- **black** — code formatting
- **mypy** — type checking
- **pre-commit** — git hooks for automatic checks

---

## Deployment

The production deployment targets a k3s cluster via GitHub Actions on push to `main`.

- Docker images are published to GHCR: `ghcr.io/madisonewebb/shopkeep`
- Kubernetes manifests are applied via Kustomize from `manifests/`
- The SQLite PVC (`manifests/pvc.yaml`) must be applied manually before first deploy:

  ```bash
  kubectl apply -f manifests/pvc.yaml
  ```

See [`docker/README.md`](docker/README.md) for container-specific documentation.

---

## Disclaimer

Shopkeep is not affiliated with or endorsed by Etsy or Discord. This project is for educational use.

---

## Author

**Madison Webb**
