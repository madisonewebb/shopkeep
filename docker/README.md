# Docker Configuration

This directory contains all Dockerfiles for the Shopkeep project.

## Files

### `Dockerfile.bot`
Discord bot container configuration.

**Base Image:** `python:3.10-slim`

**What it runs:** Discord bot from `src/bot/discord_bot.py`

**Build:**
```bash
docker-compose build bot
```

### `Dockerfile.etsy`
Mock Etsy API server container configuration.

**Base Image:** `python:3.12-slim`

**What it runs:** Mock Etsy API from `src/etsy/mock_api.py`

**Exposed Port:** 5000

**Build:**
```bash
docker-compose build mock-etsy-api
```

## Usage

All Dockerfiles are referenced in `docker-compose.yml` at the project root.

**Build all services:**
```bash
docker-compose build
```

**Start services:**
```bash
docker-compose up -d
```

**Or use Tilt for development:**
```bash
wsl tilt up
```

## Notes

- Both Dockerfiles use the project root (`.`) as build context
- Source code is mounted as volumes for live reload during development
- Non-root users are created in containers for security
