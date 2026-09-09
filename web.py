"""Web entry point for Render deployment.

This does NOT change any collection, scoring, or filtering logic — it just
exposes your existing app.py functions over HTTP so Google Apps Script can
trigger them on a schedule (since Render's free tier has no built-in cron
and sleeps without traffic).

Routes (all require ?key=TRIGGER_SECRET, except /health):
  GET  /health          -> 200 OK, used to keep the free instance awake
  POST /collect         -> runs RSS + (optional) Google News + events collection
  POST /send-digest     -> builds the digest and emails it via SMTP directly
  GET  /digest-data     -> returns the digest as JSON (for Apps Script to
                            build and send the email itself via Gmail,
                            avoiding Render's outbound SMTP issues)
  POST /critical        -> checks + sends the instant critical alert
  POST /weekly          -> sends the weekly trend summary
  GET  /dashboard       -> full browser dashboard: articles, events
                            calendar, and stats (open this in a browser
                            with ?key=YOUR_TRIGGER_SECRET on the end)
"""
import os
import logging
from flask import Flask, request, jsonify, Response

from config import (ENABLE_GNEWS, EXTRA_RSS_FEEDS, TRIGGER_SECRET,
                     UPCOMING_DAYS, ACTIVE_CATEGORIES,
                     ENABLE_CRITICAL_ALERTS, ENABLE_WEEKLY_REPORT)
from config_check import check_config
from database import init_db, recent_articles, upcoming_events
from collectors.rss import collect as collect_rss
from collectors.gnews_search import collect as collect_gnews
from collectors.events import seed_events
from reports.email_report import send as send_email_smtp, build_html
from reports.critical_alert import send_if_critical
from reports.weekly_report import send as send_weekly
from reports.dashboard import build_dashboard_html

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("web")

app = Flask(__name__)

# Log config problems clearly instead of letting a missing MONGODB_URI or
# email var crash the whole app with a confusing raw traceback later. We
# still try to start (so /health works even if something's misconfigured),
# but MongoDB-dependent routes will fail with a clear message.
check_config(require_email=True)

try:
    init_db()
    _db_ready = True
except Exception as exc:
    log.error("MongoDB init failed at startup — check MONGODB_URI. %s", exc)
    _db_ready = False


def _db_check():
    if not _db_ready:
        return jsonify(error="Database not connected — check MONGODB_URI in Render's environment variables."), 500
    return None


def _authorized():
    if not TRIGGER_SECRET:
        return True  # not set -> no auth (only fine for local testing)
    return request.args.get("key") == TRIGGER_SECRET


@app.route("/health")
def health():
    return jsonify(status="ok")


@app.route("/collect", methods=["GET", "POST"])
def collect():
    if not _authorized():
        return jsonify(error="unauthorized"), 401
    if (err := _db_check()):
        return err
    new_rss = collect_rss(EXTRA_RSS_FEEDS)
    new_gnews = collect_gnews() if ENABLE_GNEWS else 0
    new_events = seed_events()
    return jsonify(new_rss_articles=new_rss, new_gnews_articles=new_gnews, new_events=new_events)


@app.route("/send-digest", methods=["GET", "POST"])
def send_digest():
    """Sends the email directly from Render via SMTP (Option B: keep it
    simple). If Render's SMTP keeps failing, use /digest-data instead and
    let Apps Script send it via Gmail."""
    if not _authorized():
        return jsonify(error="unauthorized"), 401
    if (err := _db_check()):
        return err
    send_email_smtp()
    return jsonify(status="sent")


@app.route("/digest-data")
def digest_data():
    """Returns the same digest as raw HTML, for Apps Script to send via
    GmailApp instead of Render's SMTP."""
    if not _authorized():
        return jsonify(error="unauthorized"), 401
    if (err := _db_check()):
        return err
    html_content = build_html()
    articles = recent_articles()
    critical_count = sum(1 for a in articles if a.get("risk_level") == "CRITICAL")
    return jsonify(html=html_content, critical_count=critical_count)


@app.route("/critical", methods=["GET", "POST"])
def critical():
    if not _authorized():
        return jsonify(error="unauthorized"), 401
    if (err := _db_check()):
        return err
    if not ENABLE_CRITICAL_ALERTS:
        return jsonify(skipped="ENABLE_CRITICAL_ALERTS is false")
    n = send_if_critical()
    return jsonify(sent=bool(n), count=n or 0)


@app.route("/weekly", methods=["GET", "POST"])
def weekly():
    if not _authorized():
        return jsonify(error="unauthorized"), 401
    if (err := _db_check()):
        return err
    if not ENABLE_WEEKLY_REPORT:
        return jsonify(skipped="ENABLE_WEEKLY_REPORT is false")
    send_weekly()
    return jsonify(status="sent")


@app.route("/dashboard")
def dashboard():
    if not _authorized():
        return "Unauthorized — add ?key=YOUR_TRIGGER_SECRET to the URL.", 401
    if (err := _db_check()):
        return err
    return Response(build_dashboard_html(), mimetype="text/html")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
