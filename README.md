                                   <head>propush</head>

# Geo Intel Monitor model 

Python + SQLite monitor for geopolitical news, trade, sanctions, risk signals,
upcoming events, research feeds, and automated HTML email (with optional
Google News keyword search and WhatsApp digest).

## What's new

- **Self-contained daily scheduler** (`scheduler.py`) — no cron/Task Scheduler
  required; runs continuously, retries a failed email send up to 3 times,
  and logs everything to `logs/app.log`.
- **Categorized email digest** — sections for Geopolitics, Conferences &
  Meetings, Trade Activity, Sanctions & Circulars, Risk Signals, and
  Research Papers & Documents, each sorted by relevance score, plus a
  summary bar (total items / critical count / upcoming events).
- **Date-stamped subject line** so digests are easy to find/filter in your
  inbox (`🌍 Geo Intel Daily Brief — 03 Sep 2026`).
- **Instant critical-risk alert** (`ENABLE_CRITICAL_ALERTS=true`) — a
  separate email fires as soon as a CRITICAL item is detected, instead of
  waiting for the next scheduled digest.
- **Weekly trend summary** (`ENABLE_WEEKLY_REPORT=true`) — a 7-day rollup
  (top stories, category volume, most-mentioned countries) on top of the
  daily digest, sent on `WEEKLY_REPORT_DAY`.
- **Fuzzy duplicate filtering** — the same story reported by five outlets in
  one cycle now collapses to one item instead of cluttering the digest
  five times (`DEDUPE_THRESHOLD` in `.env`).
- **Telegram delivery** (`ENABLE_TELEGRAM=true`) — an alternative to
  WhatsApp/CallMeBot that uses the official Bot API (more reliable, no
  manual re-verification).
- **Digest archiving** — every day's HTML digest is saved to `archive/YYYY-MM-DD.html`
  (`ARCHIVE_DIGESTS=true`), so you have a browsable history even without
  digging through email.
- **Startup config validation** (`config_check.py`) — if a feature is
  enabled in `.env` but missing its credentials or dependency, the app
  tells you exactly what's wrong before running, instead of crashing mid-cycle.

## ⚠️ Security first

Never hardcode email passwords, API keys, or phone numbers in the `.py`
files. This project reads all secrets from a local `.env` file (git-ignored),
via `config.py`. If you ever paste code containing a real Gmail app password
or API key into a script, chat, or repo, treat it as compromised and rotate
it immediately at https://myaccount.google.com/apppasswords.

## Install — Windows

    py -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt
    copy .env.example .env

Edit `.env`. For Gmail use a Google App Password, not your normal password
(requires 2-Factor Authentication to be enabled on the account first).

Test:

    python app.py init
    python app.py collect
    python app.py events
    python app.py email

Or run everything in one go:

    python app.py run

## Linux/macOS

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env
    python app.py run

## Optional features (off by default)

All disabled unless you flip the flag in `.env`:

| Feature | Enable with | Extra install | What it adds |
|---|---|---|---|
| Full-article text | `ENABLE_FULL_TEXT=true` | `trafilatura` | Extracts full article text instead of the short RSS summary. Slower; some sites block scraping. |
| Google News keyword search | `ENABLE_GNEWS=true` | `gnews` | Adds keyword-driven search (geopolitics, summits/conferences, sanctions & trade terms) on top of the fixed RSS list. Keyword groups live in `config.GNEWS_QUERY_GROUPS`, joined with `OR`. |
| WhatsApp digest | `ENABLE_WHATSAPP=true` | none | Sends a short digest via [CallMeBot](https://www.callmebot.com/blog/free-api-whatsapp-messages/). |
| Telegram digest | `ENABLE_TELEGRAM=true` | none | Sends a short digest via the official Telegram Bot API — more reliable than CallMeBot. |
| Instant critical alert | `ENABLE_CRITICAL_ALERTS=true` | none | Separate email fired immediately when a CRITICAL item is found. |
| Weekly trend summary | `ENABLE_WEEKLY_REPORT=true` | none | 7-day rollup of top stories, category volume, top countries. |
| Digest archiving | `ARCHIVE_DIGESTS=true` (on by default) | none | Saves each day's HTML digest under `archive/`. |

Run a single piece manually:

    python app.py gnews       # Google News keyword collector only
    python app.py whatsapp    # send WhatsApp digest only
    python app.py telegram    # send Telegram digest only
    python app.py critical    # check for + send a critical alert only
    python app.py weekly      # send the weekly summary only

## What it monitors

- Geopolitics
- Trade / tariffs / export controls
- Sanctions signals (OFAC SDN list screening via `collectors/sanctions.py`)
- Country / risk signals
- Conferences / summits
- Research papers & reports (arXiv, NBER, CEPR/VoxEU, PIIE, BIS Research)
- Official-source feeds (WTO, UN, UNCTAD, PIB India)
- Major news (BBC, Reuters, NYT, Guardian, Al Jazeera, Hindu, Indian
  Express, Mint, Foreign Policy)
- Sanctions & trade-law trackers (Baker McKenzie, Global Trade & Sanctions Law)

## Daily scheduling

**Recommended: built-in scheduler (no cron/Task Scheduler needed).**

    python scheduler.py --now      # sends one digest now, then runs daily
    python scheduler.py            # just runs daily, at DAILY_RUN_TIME in .env

Leave this running in a terminal, `screen`/`tmux` session, or as a background
service. It logs every run to `logs/app.log` and the console, and if a
source fails or the email send fails, it retries the email up to 3 times and
then logs the failure and continues to the next day — it never crashes the
whole scheduler.

**Alternative: cron / Task Scheduler**, if you'd rather the OS handle timing:

Windows Task Scheduler: run `run_daily.bat` once per day.

Linux cron example:

    0 7 * * * /path/to/geo_intel_monitor_v2/run_daily.sh

## Important

This is a monitoring/aggregation tool, not legal, sanctions-compliance,
investment or intelligence advice. Verify important facts at primary sources.
Some RSS feed URLs occasionally change or go offline upstream — each source
fails independently (logged, not fatal) so one broken feed never stops a run.

## Deploying: Render (free) + MongoDB Atlas (free) + Google Apps Script

This setup replaces local SQLite + `scheduler.py` with continuous cloud
collection and twice-daily emails, without changing any collection,
scoring, or filtering logic.

**1. MongoDB Atlas (storage)**
- Create a free M0 cluster at https://www.mongodb.com/cloud/atlas
- Database Access: create a user + password
- Network Access: allow `0.0.0.0/0` (Render's IP isn't fixed on free tier)
- Get the connection string (Connect > Drivers > Python) → this is `MONGODB_URI`

**2. Render (runs the app, 24/7 via Apps Script pings)**
- New Web Service, connect this repo
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn web:app --bind 0.0.0.0:$PORT` (already in `Procfile`)
- Add environment variables from `.env.example`, including `MONGODB_URI`
  and a `TRIGGER_SECRET` you make up
- Note the URL Render gives you, e.g. `https://geo-intel-xxxx.onrender.com`

**3. Google Apps Script (scheduler + mailer)**
- Go to https://script.google.com → New project → paste in `apps_script/Code.gs`
- Project Settings > Script Properties, add:
  - `RENDER_BASE_URL` = your Render URL from step 2
  - `TRIGGER_SECRET` = same value as in Render's env vars
  - `EMAIL_TO` = the Gmail address you want digests sent to
- Run `setupTriggers` once and approve permissions — this installs:
  - a ping every ~12 min to `/collect` (keeps Render awake + collecting continuously)
  - digest emails at 10:00 and 22:00, sent via `GmailApp` (sidesteps Render's
    free-tier SMTP issues — Render only returns JSON, Apps Script sends the email)

If Render's direct SMTP send (`/send-digest`) works fine for you, you can
use that instead and skip the Gmail-sending part of Apps Script — just
point two Apps Script triggers at `/send-digest` instead of `sendDigest()`.

## V3 ideas

Dedicated official calendars, better event extraction, PDF/document
collection, sanctions-list versioning, full-text search, dashboard, critical
alerts, 7/30/90-day calendar, stronger source/deduplication scoring.
