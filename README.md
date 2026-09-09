# Geo Intel Monitor V2

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

This replaces local SQLite + `scheduler.py` with continuous cloud
collection and scheduled emails, without changing any collection, scoring,
or filtering logic. Follow these steps in order.

**1. MongoDB Atlas (storage) — free M0 cluster**
1. Sign up at https://www.mongodb.com/cloud/atlas, create a free M0 cluster
2. Database Access → create a username + password (save these)
3. Network Access → Add IP Address → Allow access from anywhere (`0.0.0.0/0`)
   — Render's IP isn't fixed on the free tier, so this is required
4. Connect → Drivers → Python → copy the connection string. This is your
   `MONGODB_URI` (looks like `mongodb+srv://user:pass@cluster0.xxxxx.mongodb.net/`)

**2. Push this code to GitHub**
Render deploys from a GitHub repo. Create one and push everything in this
zip into it (all folders and files, including `Procfile`, `runtime.txt`,
and the hidden-looking `apps_script/` folder).

**3. Render (runs the app)**
1. https://render.com → New → Web Service → connect your GitHub repo
2. Build Command: `pip install -r requirements.txt`
3. Start Command: leave default — it reads from `Procfile` automatically
4. Instance type: Free
5. Environment tab → add every variable from `.env.example`, with your
   real values (`MONGODB_URI` from step 1, a made-up `TRIGGER_SECRET`,
   your Gmail address for `EMAIL_FROM`/`EMAIL_TO`, and a Gmail **App
   Password** — not your real password — for `EMAIL_APP_PASSWORD`,
   generated at https://myaccount.google.com/apppasswords)
6. Also add `PYTHON_VERSION` = `3.11.9` (avoids a known SSL bug between
   very new Python versions and MongoDB Atlas)
7. Deploy. Once live, open `https://your-app.onrender.com/health` —
   it should show `{"status":"ok"}`. Save this URL for step 4.

**4. Google Apps Script (scheduler + mailer)**
1. https://script.google.com → New project
2. Paste `apps_script/Code.gs`'s contents in as the main file
3. Click the gear icon (Project Settings) → check "Show appsscript.json
   manifest file in editor" → open that new file → replace its contents
   with `apps_script/appsscript.json` from this zip (this pins the
   schedule to `Asia/Kolkata` so 10:00/22:00 actually means Indian time,
   not whatever timezone the script defaults to)
4. Still in Project Settings, scroll to **Script Properties**, add 3 rows:
   - `RENDER_BASE_URL` → your Render URL from step 3 (no trailing slash)
   - `TRIGGER_SECRET` → same value as Render's `TRIGGER_SECRET`
   - `EMAIL_TO` → your Gmail address (comma-separate for multiple people)
5. Function dropdown (top toolbar) → select `setupTriggers` → click Run →
   approve the permissions it asks for
6. Click the clock icon (Triggers) on the left — confirm 6 triggers now
   exist: `keepAlive` (10 min), `runCollect` (30 min), `sendDigest` (×2,
   10:00 & 22:00), `checkCritical` (30 min), `sendWeekly` (Monday 9:00)

**5. Test it**
- Function dropdown → `sendDigest` → Run → check your inbox
- Wait ~10 min → check MongoDB Atlas → Collections → `articles` should be
  growing
- Next day, check the Triggers page — "Last run" should show real
  timestamps instead of "-"

**Notes on how the scheduling works:**
- `keepAlive` pings `/health` every 10 min just to stop Render's free tier
  from sleeping — it's cheap and doesn't run collection
- `runCollect` does the actual (heavier) collection job every 30 min —
  that's what "24/7 collecting" means here, not collecting every few minutes
- Each digest only includes articles not already sent in a previous
  digest, so 10pm won't repeat what 10am already sent
- Critical alerts and the weekly report are independent of the digest —
  they can still mention an item even if it already appeared in a digest,
  since they serve a different purpose (immediate alert / weekly recap)

## V3 ideas

Dedicated official calendars, better event extraction, PDF/document
collection, sanctions-list versioning, full-text search, dashboard, critical
alerts, 7/30/90-day calendar, stronger source/deduplication scoring.
