# Shopkeep 🛍️🤖

Shopkeep is a Discord bot that integrates with the Etsy API to deliver shop notifications and shop insights directly into a Discord server.

---

## Features

- 📦 Real-time Etsy order notifications
- 💬 Discord slash commands for shop info
- 📊 Basic shop statistics and metrics
- 🗄️ Optional data storage for orders and shop data

---

## Tech Stack

- **Python** — backend and bot logic
- **discord.py** — Discord API integration
- **Etsy API** — shop, order, and listing data
- **Docker** — containerized development
- **Tilt** — local container orchestration
- **PostgreSQL** — data persistence

---

## Project Status

🚧 Early development
Initial work is focused on Etsy API integration and Discord notifications for the MVP.

---

## Disclaimer

Shopkeep is not affiliated with or endorsed by Etsy or Discord. This project is for educational use.

---

## Getting Started

### Prerequisites

- Python 3.10+
- [Task](https://taskfile.dev/) - Task runner
- Discord Bot Token ([Get one here](https://discord.com/developers/applications))
- **OR** Docker & [Tilt](https://tilt.dev/) (for containerized development)

### Installation

#### Option 1: Tilt (Recommended)

1. **Clone the repository:**

   ```bash
   git clone <your-repo-url>
   cd shopkeep
   ```
2. **Set up environment variables:**
   Create a `.env` file in the project root:

   ```bash
   DISCORD_BOT_TOKEN=your_discord_bot_token_here
   ```
3. **Start Tilt:**

   ```bash
   tilt up
   ```

   This will:

   - Build the Docker image
   - Deploy the bot
   - Watch for file changes and auto-reload
   - Open the Tilt UI in your browser
4. **View logs:**

   - Use the Tilt UI (opens automatically)
   - Or press `space` in the terminal to open the UI
5. **Stop Tilt:**

   - Press `Ctrl+C` in the terminal
   - Or run: `tilt down`

#### Option 2: Local Python Installation

1. **Clone the repository:**

   ```bash
   git clone <your-repo-url>
   cd shopkeep
   ```
2. **Install dependencies:**

   ```bash
   task install-dev
   ```
3. **Set up environment variables:**
   Create a `.env` file in the project root:

   ```bash
   DISCORD_BOT_TOKEN=your_discord_bot_token_here
   ```
4. **Install pre-commit hooks:**

   ```bash
   task setup-hooks
   ```

### Running the Bot

```bash
python -m src.bot.discord_bot
```

Or use the task runner:

```bash
task run
```

---

## Development

### Available Tasks

View all available tasks:

```bash
task help
```

Common commands:

- `task install-dev` - Install all dependencies
- `task format` - Auto-format code (ruff + black)
- `task lint` - Run all linters
- `task pre-commit` - Run pre-commit on all files
- `task run` - Run the Discord bot
- `task clean` - Clean Python cache files

### Code Quality

This project uses:

- **ruff** - Fast Python linter (replaces flake8, isort, and more)
- **black** - Code formatting
- **mypy** - Type checking
- **pre-commit** - Git hooks for automatic checks

Pre-commit hooks run automatically on `git commit`. To run manually:

```bash
task lint
```

---



## Author

**Madison Webb**
