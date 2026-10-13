# Telegram alerts

DengueSUX has a Telegram bot, **@DengueSUXbot**, so a resident or a town-council officer can follow one
planning area without giving an email address or phone number.

## What a person sees

- Open `https://t.me/DengueSUXbot?start=<AREA CODE>` from the area's **Telegram alerts** link (area detail)
  or the second QR code on the lift-lobby poster. The bot subscribes the chat to that area and replies at once
  with today's numbers: people in active clusters, priority, the two-week outlook, any alert, and a link to
  the field plan.
- Send an area name (`Bedok`, `jurong`) for today's numbers; `/subscribe <area>` to follow it;
  `/status` for your areas; `/areas` for the areas needing attention; `/stop` to delete everything about you.
- A push arrives only on days an area you follow is **High**, has a **new or growing cluster**, or is
  **forecast High** in two weeks. Quiet days send nothing.

## What is stored

One row per subscription in `workspace.denguesux.telegram_subscriptions`: the Telegram chat id, the planning
area code and the time. No names, usernames or phone numbers. `/stop` deletes the rows.

## How it runs on Databricks

| Piece | Where | Notes |
|---|---|---|
| Bot token | Secret scope `denguesux`, key `telegram_bot_token` | Never in code, YAML or logs. |
| Replies | The Databricks App (`denguesux/telegram.py`, long polling in a background thread) | The app resource `telegram-token` (READ) sets `TELEGRAM_BOT_TOKEN`; `TELEGRAM_POLL=0` disables polling, e.g. for a local run while the cloud app is up (Telegram allows one poller). |
| Subscriptions | UC table through the app's SQL warehouse (parameterised statements) | Locally a private JSONL file under `data/private/`. |
| Daily push | `daily_inspection` job → `scripts/daily_inspection.py` → `telegram.push_daily` | The notebook reads the token with `dbutils.secrets.get`; the job logs counts only. |
| Channel digest (optional) | Bundle variable `telegram_chat_id` | Create a channel, add the bot as an admin, deploy with `--var telegram_chat_id=@your_channel`; the existing daily digest is posted there too. |
| Links in messages | Bundle variable `public_url` and app env `DENGUE_PUBLIC_URL` | Point at the app's URL. |

Databricks SQL alerts can also notify Telegram directly: Telegram accepts `chat_id` and `text` as query-string
parameters, so a webhook notification destination with URL
`https://api.telegram.org/bot<token>/sendMessage?chat_id=<chat>&text=<message>` fires a fixed message when an
alert triggers. The daily push is preferred because it carries the area's actual numbers.

## Checks

- `tests/test_telegram.py` covers the commands, the privacy rules and the daily push selection.
- `GET /api/telegram/status` on the app reports `{"available": true, "username": "DengueSUXbot"}` when the
  token is attached; it never returns chat ids or the token.
