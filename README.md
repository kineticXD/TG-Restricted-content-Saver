# TG-Restricted-content-Saver

A modern Telegram bot for downloading restricted Telegram post content using a clean button-first interface.

The bot can download media and text from Telegram post links, supports batch ranges, and includes safe confirmation steps for destructive actions.

## Features

- Button-first Telegram UI (no need to memorize commands)
- Single post download (photo, video, audio, document, text/caption)
- Batch range download using start and end links
- Live progress for downloads/uploads
- Optional auto-forward to a target chat/channel
- Built-in stats, logs, cleanup, and stop-active-jobs actions
- Confirmation prompts for cleanup and stop-active-jobs

## Requirements

- Docker Desktop (or Docker Engine + Compose plugin)
- Telegram Bot Token (`BOT_TOKEN`)
- Telegram API ID and API Hash (`API_ID`, `API_HASH`)
- Telegram user `SESSION_STRING`

## Configuration

Edit `config.env` and set your values:

```env
API_ID=123456
API_HASH=your_api_hash
BOT_TOKEN=123456:ABCDEF...
SESSION_STRING=your_session_string

MAX_CONCURRENT_DOWNLOADS=1
BATCH_SIZE=1
FLOOD_WAIT_DELAY=10

# Optional auto-forward target
FORWARD_CHAT_ID=
```

Auto-forward notes:

- If `FORWARD_CHAT_ID` is set, the bot must have permission to post there.
- If forwarding is misconfigured, the bot continues by sending output to your private chat.

## Run With Docker

From project root:

```bash
docker compose up -d --build --remove-orphans
```

Check status:

```bash
docker compose ps
```

View logs:

```bash
docker compose logs -f
```

Stop:

```bash
docker compose down
```

## Telegram Usage

1. Send `/start` to open the main menu.
2. Use buttons:
   - `Download One Post`
   - `Batch Download`
   - `Examples`
   - `How It Works`
   - `Stats`
   - `Logs`
   - `Cleanup` (with confirmation)
   - `Stop Active Jobs` (with confirmation)

### General Link Examples

Single post:

```text
https://t.me/username/547
https://t.me/c/123456789/10
https://t.me/c/123456789/120/122
```

Batch range (send both links in one message):

```text
https://t.me/username/100 https://t.me/username/120
https://t.me/c/123456789/300 https://t.me/c/123456789/360
```

## Optional Command Fallback

Commands are still supported:

```text
/dl <post_link>
/bdl <start_link> <end_link>
/stats
/logs
/cleanup
/killall
```

## Troubleshooting

- `Access denied` or `PeerIdInvalid`:
  - Make sure the user session account can access that source chat.
- `FloodWait`:
  - Keep low concurrency and process smaller ranges.
- No output in Docker:
  - Check `docker compose logs -f`.

## Security

- Do not commit your real `config.env` values.
- Keep tokens/session strings private.

## Project Structure

```text
RestrictedContentDL/
  config.env
  config.py
  Dockerfile
  docker-compose.yml
  main.py
  helpers/
```
