# Geo Intel Monitor V2

Python + MongoDB monitor for trade activity, sanctions/circulars, and
research papers, with automated HTML email, a browser dashboard, and
24/7 cloud deployment (Render + MongoDB Atlas + Google Apps Script).

## Two ways to run this

| | Local (`scheduler.py`) | Cloud (Render + Apps Script) |
|---|---|---|
| Use when | Testing on your own PC | 24/7 always-on deployment |
| Storage | Still needs `MONGODB_URI` (no more SQLite) | MongoDB Atlas |
| Timing controlled by | `DAILY_RUN_TIME`/`SEND_TIMES` in `.env` | Apps Script Script Properties (see "Deploying" section) |
| Email sent via | Direct SMTP from your PC | Apps Script/GmailApp (Render blocks outbound SMTP) |
| Entry point | `python scheduler.py` | `web.py` (via `Procfile`/gunicorn) |

If you're deploying to Render, skip straight to "Deploying" below —
`scheduler.py` and its `DAILY_RUN_TIME` setting are not used there at all.

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
- **Browser dashboard** (`/dashboard?key=...` on the Render URL) — live
  view of recent articles, upcoming events, risk/credibility breakdowns,
  and a search box, reusing the exact same MongoDB data as the email.
- **Source credibility + corroboration** — each source is tagged HIGH/
  MEDIUM/LOW credibility, and when the same story is confirmed by multiple
  outlets in one cycle, the digest shows "confirmed by N sources".
- **Two digests a day, no repeats** — articles are marked as sent after
  each digest, so the 10pm email only contains what's new since 10am.
- **Long-term Telegram archive** (`ENABLE_TELEGRAM_ARCHIVE=true`) — old
  articles get posted to a Telegram channel and removed from MongoDB, so
  the free 512MB Atlas tier doesn't fill up over months of continuous
  collection.

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

| Feature | Enable with | What it adds |
|---|---|---|
| Full-article text | `ENABLE_FULL_TEXT=true` | Extracts full article text instead of the short RSS summary. Slower; some sites block scraping. (`trafilatura` is already in `requirements.txt` — just flip the flag.) |
| Google News keyword search | `ENABLE_GNEWS=true` | Adds keyword-driven search (geopolitics, summits/conferences, sanctions & trade terms) on top of the fixed RSS list. Keyword groups live in `config.GNEWS_QUERY_GROUPS`, joined with `OR`. (`gnews` is already in `requirements.txt` — just flip the flag.) |
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

## Local daily scheduling (only if NOT deploying to Render)

    python scheduler.py --now      # sends one digest now, then runs daily
    python scheduler.py            # just runs daily, at DAILY_RUN_TIME in .env

Leave this running in a terminal, `screen`/`tmux` session, or as a background
service. It logs every run to `logs/app.log` and the console, and if a
source fails or the email send fails, it retries the email up to 3 times and
then logs the failure and continues to the next day — it never crashes the
whole scheduler.

**Alternative for local use: cron / Task Scheduler**, if you'd rather the OS
handle timing:

Windows Task Scheduler: run `run_daily.bat` once per day.

Linux cron example:

    0 7 * * * /path/to/geo_intel_monitor_v2/run_daily.sh

For 24/7 always-on operation with twice-daily email, skip this section
entirely and use the "Deploying: Render" section below instead.

## Important

This is a monitoring/aggregation tool, not legal, sanctions-compliance,
investment or intelligence advice. Verify important facts at primary sources.
Some RSS feed URLs occasionally change or go offline upstream — each source
fails independently (logged, not fatal) so one broken feed never stops a run.

## Deploying: Render (free) + MongoDB Atlas (free) + Telegram + Google Apps Script

This replaces local SQLite + `scheduler.py` with continuous cloud
collection, full-data storage on Telegram, and scheduled emails at
whatever times you choose — without changing any collection, scoring, or
filtering logic. Follow these steps in order.

**1. MongoDB Atlas (metadata storage) — free M0 cluster**
1. Sign up at https://www.mongodb.com/cloud/atlas, create a free M0 cluster
2. Database Access → create a username + password (save these)
3. Network Access → Add IP Address → Allow access from anywhere (`0.0.0.0/0`)
   — Render's IP isn't fixed on the free tier, so this is required
4. Connect → Drivers → Python → copy the connection string. This is your
   `MONGODB_URI` (looks like `mongodb+srv://user:pass@cluster0.xxxxx.mongodb.net/`)

**2. Telegram (full data storage) — optional but recommended**
1. Message **@BotFather** on Telegram → `/newbot` → follow prompts → copy
   the bot token it gives you → this is `TELEGRAM_BACKUP_BOT_TOKEN`
   (you can reuse the same bot/token as `TELEGRAM_BOT_TOKEN` if you also
   want the separate Telegram-digest feature — they don't have to differ)
2. Create a Telegram channel (private is fine — this is your database, not
   something to share)
3. Add your bot as an **admin** of that channel, with "Post Messages"
   permission
4. Get the channel's numeric chat id: forward any message from the channel
   to **@userinfobot**, or send a test message in the channel then visit
   `https://api.telegram.org/bot<token>/getUpdates` in a browser and read
   the chat id from the JSON (it looks like `-1001234567890`) — this is
   `TELEGRAM_BACKUP_CHAT_ID`

Once this is on (`ENABLE_TELEGRAM_BACKUP=true` in step 4 below), every
article collected gets its full record (full summary, all fields) posted
to this channel — that's your permanent full-data store. MongoDB only
keeps a short preview plus a link to the matching Telegram message. The
dashboard shows both: the metadata list from MongoDB, and a "📦 Full
record on Telegram ↗" link per article that jumps straight to the
complete data.

**3. Push this code to GitHub**
Render deploys from a GitHub repo. Create one and push everything in this
zip into it (all folders and files, including `Procfile`, `runtime.txt`,
and the hidden-looking `apps_script/` folder).

**4. Render (runs the app)**
1. https://render.com → New → Web Service → connect your GitHub repo
2. Build Command: `pip install -r requirements.txt`
3. Start Command: leave default — it reads from `Procfile` automatically
4. Instance type: Free
5. Environment tab → add every variable from `.env.example`, with your
   real values: `MONGODB_URI` from step 1, a made-up `TRIGGER_SECRET`,
   your Gmail address for `EMAIL_FROM`/`EMAIL_TO`, a Gmail **App
   Password** (not your real password) for `EMAIL_APP_PASSWORD` generated
   at https://myaccount.google.com/apppasswords, and — if using Telegram
   backup — `ENABLE_TELEGRAM_BACKUP=true` plus the two values from step 2
6. Also add `PYTHON_VERSION` = `3.11.9` (avoids a known SSL bug between
   very new Python versions and MongoDB Atlas)
7. Deploy. Once live, open `https://your-app.onrender.com/health` —
   it should show `{"status":"ok"}`. Save this URL for the next step.

**5. Google Apps Script (scheduler + mailer + optional dashboard page)**
1. https://script.google.com → New project
2. Paste `apps_script/Code.gs`'s contents in as the main file
3. Click the gear icon (Project Settings) → check "Show appsscript.json
   manifest file in editor" → open that new file → replace its contents
   with `apps_script/appsscript.json` from this zip (this pins the
   script's timezone to `Asia/Kolkata` so whatever times you set below
   mean Indian time, not whatever timezone the script defaults to —
   change this in the manifest if you're in a different timezone)
4. Still in Project Settings, scroll to **Script Properties**, add:
   - `RENDER_BASE_URL` → your Render URL from step 4 (no trailing slash)
   - `TRIGGER_SECRET` → same value as Render's `TRIGGER_SECRET`
   - `EMAIL_TO` → your Gmail address (comma-separate for multiple people)
   - **`DIGEST_TIMES`** → set this to whatever times YOU want the digest
     sent, comma-separated, any number of them — e.g. `08:00,20:00` or
     `09:00,14:00,19:00,23:00`. If you skip this property entirely, it
     defaults to `10:00,22:00`. **This is the setting you control
     yourself — just edit this property to change your schedule, no
     code changes needed.**
5. Function dropdown (top toolbar) → select `setupTriggers` → click Run →
   approve the permissions it asks for
6. Click the clock icon (Triggers) on the left — confirm one `sendDigest`
   trigger exists for each time you put in `DIGEST_TIMES`, plus
   `keepAlive`, `runCollect`, `checkCritical`, `sendWeekly`, `cleanupOld`
7. **To change your send times later**: just edit the `DIGEST_TIMES`
   Script Property, then run `setupTriggers` again — it always rebuilds
   everything from scratch, so this is safe to re-run any time.

**6. Optional: dashboard as an Apps Script web page**
If you'd rather open your dashboard at a `script.google.com` link than
remember your Render URL:
1. In the Apps Script editor: **Deploy → New deployment**
2. Select type **Web app**
3. Execute as: **Me**. Who has access: **Only myself** (or "Anyone with
   the link" if you want to share it with others)
4. Click **Deploy**, copy the Web App URL it gives you
5. Open that URL in a browser — it shows your live dashboard, fetched
   fresh from Render/MongoDB/Telegram each time you load it

**7. Test it**
- Function dropdown → `sendDigest` → Run → check your inbox
- Wait ~10 min → check MongoDB Atlas → Collections → `articles` should be
  growing
- If Telegram backup is on, check your backup channel — you should see
  batched messages with full article records appearing
- Next day, check the Triggers page — "Last run" should show real
  timestamps instead of "-"

**Notes on how the scheduling works:**
- `keepAlive` pings `/health` every 10 min just to stop Render's free tier
  from sleeping — it's cheap and doesn't run collection
- `runCollect` does the actual (heavier) collection job every 30 min —
  that's what "24/7 collecting" means here, not collecting every few
  minutes. This is also when Telegram backup posting happens.
- Each digest only includes articles not already sent in a previous
  digest, so your 2nd/3rd/4th digest of the day won't repeat what an
  earlier one already sent — this holds no matter how many times you've
  set in `DIGEST_TIMES`
- Critical alerts and the weekly report are independent of the digest —
  they can still mention an item even if it already appeared in a digest,
  since they serve a different purpose (immediate alert / weekly recap)
- `cleanupOld` (monthly) only ever deletes MongoDB metadata, never
  Telegram messages — the full data stays on Telegram permanently

## Summary of env var changes from the previous version

If you had already deployed an earlier version of this project, here's
exactly what changed:

| Old variable | New variable | Why |
|---|---|---|
| `ENABLE_TELEGRAM_ARCHIVE` | `ENABLE_METADATA_CLEANUP` | Renamed: it no longer archives-then-deletes, it just deletes (data's already been on Telegram since collection time) |
| `TELEGRAM_ARCHIVE_CHAT_ID` | *(removed)* | No longer needed — cleanup doesn't post anywhere |
| `ARCHIVE_AFTER_DAYS` | `METADATA_CLEANUP_AFTER_DAYS` | Renamed to match the new behavior |
| *(new)* | `ENABLE_TELEGRAM_BACKUP` | Turns on full-data storage to Telegram |
| *(new)* | `TELEGRAM_BACKUP_BOT_TOKEN` | Bot token for the backup channel (can reuse `TELEGRAM_BOT_TOKEN`) |
| *(new)* | `TELEGRAM_BACKUP_CHAT_ID` | Chat id of your backup channel |
| Apps Script: `DIGEST_TIME_1` / `DIGEST_TIME_2` | Apps Script: `DIGEST_TIMES` | One comma-separated property instead of two fixed slots — set any number of times yourself |
| Apps Script: `ARCHIVE_DAY_OF_MONTH` / `ARCHIVE_TIME` | Apps Script: `CLEANUP_DAY_OF_MONTH` / `CLEANUP_TIME` | Renamed to match |
| Route `/archive-old` | Route `/cleanup-old` | Renamed to match |

If you're deploying fresh, none of this matters — just follow the steps
above with the current names.

## V3 ideas

Dedicated official calendars, better event extraction, PDF/document
collection, sanctions-list versioning, full-text search, 7/30/90-day
calendar view, stronger source/deduplication scoring.
