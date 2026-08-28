# Nullcraft Bot

Nullcraft sends Telegram alerts for large Polymarket trades. Each chat can set a separate USD threshold.

This repository is a refactored version of an older scrappy monitor I used to use. It uses the current public Polymarket Data API and needs no wallet key.

## Features

- Polls the current Polymarket `/trades` endpoint.
- Filters large trades through the Data API.
- Sends market, trader, and transaction links.
- Stores subscriptions and thresholds in SQLite.
- Prevents duplicate alerts across process restarts.
- Uses an overlap window to handle delayed API records.
- Retries temporary Telegram network failures.
- Stops cleanly after `SIGINT` or `SIGTERM`.

## Requirements

- Python 3.11 or later
- A Telegram bot token from [BotFather](https://t.me/BotFather)
- [uv](https://docs.astral.sh/uv/)

A Polymarket private key or API credential is not required.

## Install the bot

1. Clone the repository.

   ```bash
   git clone https://github.com/0xf3dz/nullcraft-bot.git
   cd nullcraft-bot
   ```

2. Install the locked dependencies.

   ```bash
   uv sync
   ```

3. Create the local environment file.

   ```bash
   cp .env.example .env
   ```

4. Put the Telegram bot token in `.env`.

   ```dotenv
   TELEGRAM_BOT_TOKEN=replace-with-your-bot-token
   ```

5. Check SQLite and Polymarket access.

   ```bash
   uv run nullcraft --check
   ```

6. Start the bot.

   ```bash
   uv run nullcraft
   ```

## Telegram commands

| Command | Result |
| --- | --- |
| `/start` | Activate alerts with the default threshold |
| `/stop` | Disable alerts for the chat |
| `/setthreshold <amount>` | Set and activate a new threshold |
| `/showthreshold` | Show the current threshold |
| `/debug` | Show safe status data for the bot |
| `/apitest` | Check the Polymarket Data API |
| `/help` | Show the command list |

For example, `/setthreshold 25000` sends alerts for trades worth at least $25,000.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | None | Telegram bot token |
| `NULLCRAFT_DATABASE_PATH` | `data/nullcraft.db` | SQLite database path |
| `NULLCRAFT_DEFAULT_THRESHOLD_USD` | `10000` | Threshold for a new subscription |
| `NULLCRAFT_MINIMUM_THRESHOLD_USD` | `100` | Lowest accepted chat threshold |
| `NULLCRAFT_POLL_INTERVAL_SECONDS` | `2` | Delay between successful polls |
| `NULLCRAFT_STARTUP_LOOKBACK_SECONDS` | `30` | Initial trade lookback window |
| `NULLCRAFT_OVERLAP_SECONDS` | `10` | Overlap between poll windows |
| `NULLCRAFT_REQUEST_TIMEOUT_SECONDS` | `15` | Data API request timeout |
| `NULLCRAFT_PROCESSED_RETENTION_SECONDS` | `86400` | Alert deduplication duration |
| `NULLCRAFT_DATA_API_URL` | `https://data-api.polymarket.com` | Data API base URL |
| `NULLCRAFT_LOG_LEVEL` | `INFO` | Python log level |

The default trade threshold limits the Data API result size. If the API returns 1,000 trades in one window, Nullcraft stops that poll and asks you to increase the threshold.

## Architecture

```text
Telegram commands -> SQLite subscriptions
                           |
Polymarket Data API -> trade monitor -> Telegram alerts
                           |
                     SQLite deliveries
```

The monitor requests taker trades once per poll window. It sorts records by timestamp and validates each record before use.

A delivery record contains a trade identity and a chat identifier. Nullcraft writes the record only after Telegram accepts the alert.

## Test the bot

Run the contract tests.

```bash
uv run python -m unittest discover -s tests -v
```

Check the source with Ruff.

```bash
uvx ruff check .
```

Audit the locked dependencies.

```bash
uv export --locked --no-dev --no-emit-project \
  --format requirements-txt --output-file /tmp/nullcraft-requirements.txt
uvx pip-audit --requirement /tmp/nullcraft-requirements.txt
```

## Data sources

- [Polymarket Data API trade reference](https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets)
- [Telegram Bot API](https://core.telegram.org/bots/api)

Nullcraft is an independent project. It has no affiliation with Polymarket or Telegram. Public trade data can arrive late or change after publication.
