# Usage Guide

This guide explains how to run and use TG-Restricted-content-Saver with the new button-first Telegram flow.

## 1. Start the Bot

Run from project folder:

```bash
docker compose up -d --build --remove-orphans
```

Verify:

```bash
docker compose ps
```

## 2. Open the Bot in Telegram

Send:

```text
/start
```

You will see the main button menu.

## 3. Download One Post

1. Tap `Download One Post`
2. Send one Telegram post URL

Example:

```text
https://t.me/username/547
```

The bot downloads and sends the content, then shows quick action buttons.

## 4. Batch Download

1. Tap `Batch Download`
2. Send start and end links in one message

Example:

```text
https://t.me/username/100 https://t.me/username/120
```

Behavior:

- Both links must belong to the same chat/channel.
- Start ID must be less than or equal to end ID.
- Posts with no media/text are skipped.

## 5. Examples Panel

Tap `Examples` to view ready-to-use link formats for:

- Single post links
- Batch range links

## 6. Utility Actions

From menu buttons:

- `Stats`: Shows uptime, disk, memory, CPU, and network usage.
- `Logs`: Sends the latest `logs.txt`.
- `Cleanup`: Removes local downloaded temp files.
- `Stop Active Jobs`: Cancels currently running tasks.

## 7. Safety Confirmations

Destructive actions now require confirmation:

- `Cleanup` -> `Yes, Cleanup` / `No, Go Back`
- `Stop Active Jobs` -> `Yes, Stop Jobs` / `No, Go Back`

## 8. Command Fallback

You can still use commands if needed:

```text
/dl <post_link>
/bdl <start_link> <end_link>
/stats
/logs
/cleanup
/killall
```

## 9. Common Issues

### Access denied

Cause: user session has no access to source chat.

Fix: join the source chat/channel using the user account linked to `SESSION_STRING`.

### FloodWait

Cause: Telegram rate limiting.

Fix:

- Keep `MAX_CONCURRENT_DOWNLOADS=1`
- Keep `BATCH_SIZE=1`
- Keep `FLOOD_WAIT_DELAY=10`
- Use smaller batch ranges

### Docker service not running

If Docker commands fail, start Docker Desktop first, then rerun compose commands.

## 10. Stop and Restart

Stop:

```bash
docker compose down
```

Restart:

```bash
docker compose up -d --build --remove-orphans
```

Live logs:

```bash
docker compose logs -f
```
