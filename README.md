# Telegram Bots

This repository is structured as a package so multiple Telegram bots can live in one codebase. The first bot checks multiple email inboxes over IMAP and sends a Telegram status message twice daily using GitHub Actions.

## Project layout

```text
.github/workflows/
src/telegram_bots/
```

Current bot modules:

- `telegram_bots.email_status_bot`
- `telegram_bots.email_status_runner`

## What it does

- Reads multiple email account credentials from one GitHub secret.
- Connects to each mailbox using IMAP.
- Counts unread emails and includes up to 3 previews per inbox.
- Sends one consolidated Telegram message.
- Runs at 08:00 and 20:00 UTC and can also be started manually from GitHub Actions.

## Required GitHub secrets

Create these repository secrets:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `INBOX_CONFIGS_JSON`

## `INBOX_CONFIGS_JSON` format

Use a JSON array. Example:

```json
[
  {
    "name": "Work",
    "email": "work@example.com",
    "password": "app-password-1",
    "imap_server": "imap.gmail.com",
    "imap_port": 993,
    "mailbox": "INBOX"
  },
  {
    "name": "Personal",
    "email": "personal@example.com",
    "password": "app-password-2",
    "imap_server": "outlook.office365.com",
    "imap_port": 993,
    "mailbox": "INBOX"
  }
]
```

## Telegram setup

1. Create a bot with [@BotFather](https://t.me/BotFather).
2. Copy the bot token into `TELEGRAM_BOT_TOKEN`.
3. Send a message to your bot from the target Telegram account or group.
4. Get the destination chat ID and store it in `TELEGRAM_CHAT_ID`.

## Email provider notes

Many providers require an app password instead of your normal login password.

- Gmail: usually requires IMAP enabled and an app password.
- Outlook / Microsoft 365: app password or mailbox password depending on account policy.
- Custom mail hosting: use the provider's IMAP host and port.

## Local run

```powershell
$env:TELEGRAM_BOT_TOKEN="your-bot-token"
$env:TELEGRAM_CHAT_ID="your-chat-id"
$env:INBOX_CONFIGS_JSON='[{"name":"Work","email":"work@example.com","password":"app-password","imap_server":"imap.gmail.com"}]'
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt .
python -m telegram_bots.email_status_runner
```

## GitHub Actions schedule

The workflow is in `.github/workflows/email-status-bot.yml` and runs with this cron:

```text
0 8,20 * * *
```

GitHub schedules use UTC. That means the job runs daily at 08:00 UTC and 20:00 UTC.
