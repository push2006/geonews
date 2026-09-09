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
"""
import os
from flask import Flask, request, jsonify

from config import (ENABLE_GNEWS, EXTRA_RSS_FEEDS, TRIGGER_SECRET,
                     UPCOMING_DAYS, ACTIVE_CATEGORIES)
from database import init_db, recent_articles, upcoming_events
from collectors.rss import collect as collect_rss
from collectors.gnews_search import collect as collect_gnews
from collectors.events import seed_events
from reports.email_report import send as send_email_smtp, build_html
from reports.critical_alert import send_if_critical
from reports.weekly_report import send as send_weekly

app = Flask(__name__)
init_db()


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
    send_email_smtp()
    return jsonify(status="sent")


@app.route("/digest-data")
def digest_data():
    """Returns the same digest as raw HTML, for Apps Script to send via
    GmailApp instead of Render's SMTP."""
    if not _authorized():
        return jsonify(error="unauthorized"), 401
    html_content = build_html()
    articles = recent_articles()
    critical_count = sum(1 for a in articles if a.get("risk_level") == "CRITICAL")
    return jsonify(html=html_content, critical_count=critical_count)


@app.route("/critical", methods=["GET", "POST"])
def critical():
    if not _authorized():
        return jsonify(error="unauthorized"), 401
    n = send_if_critical()
    return jsonify(sent=bool(n), count=n or 0)


@app.route("/weekly", methods=["GET", "POST"])
def weekly():
    if not _authorized():
        return jsonify(error="unauthorized"), 401
    send_weekly()
    return jsonify(status="sent")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
