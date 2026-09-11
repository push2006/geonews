"""Web entry point for Render deployment.

This does NOT change any collection, scoring, or filtering logic — it just
exposes your existing app.py functions over HTTP so Google Apps Script can
trigger them on a schedule (since Render's free tier has no built-in cron
and sleeps without traffic).

Routes (all require ?key=TRIGGER_SECRET, except /health):
  GET  /health          -> 200 OK, used to keep the free instance awake
  POST /collect         -> runs RSS + (optional) Google News + events
                            collection. Full records are backed up to
                            Telegram as part of this step if
                            ENABLE_TELEGRAM_BACKUP=true.
  POST /send-digest     -> builds the digest and emails it via SMTP directly
  GET  /digest-data     -> returns the digest as JSON (for Apps Script to
                            build and send the email itself via Gmail,
                            avoiding Render's outbound SMTP issues)
  POST /critical        -> checks + sends the instant critical alert
  POST /weekly          -> sends the weekly trend summary
  GET  /dashboard       -> full browser dashboard: every saved article
                            (full record, not just metadata), events
                            calendar, and stats (open in a browser with
                            ?key=YOUR_TRIGGER_SECRET on the end)
  GET  /export.csv      -> downloads every article as a CSV file
  POST /cleanup-old     -> deletes MongoDB metadata older than
                            METADATA_CLEANUP_AFTER_DAYS. Nothing is lost --
                            the full record already lives permanently in
                            the Telegram backup channel from collection time.
"""
import os
import io
import csv
import threading
import logging
from datetime import datetime, timezone
from flask import Flask, request, jsonify, Response

from config import (ENABLE_GNEWS, EXTRA_RSS_FEEDS, TRIGGER_SECRET,
                     UPCOMING_DAYS, ACTIVE_CATEGORIES,
                     ENABLE_CRITICAL_ALERTS, ENABLE_WEEKLY_REPORT,
                     ENABLE_METADATA_CLEANUP)
from config_check import check_config
from database import init_db, recent_articles, upcoming_events
from collectors.rss import collect as collect_rss
from collectors.gnews_search import collect as collect_gnews
from collectors.events import seed_events
from reports.email_report import send as send_email_smtp, build_html, build_digest, mark_sent
from reports.critical_alert import send_if_critical
from reports.weekly_report import send as send_weekly
from reports.dashboard import build_dashboard_html
from reports.metadata_cleanup import cleanup as cleanup_old_metadata

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


# Background job state for /collect. Collection (RSS + Google News +
# Telegram backup) can take longer than gunicorn's/Render's request
# timeout, so /collect now kicks the work off in a background thread and
# returns immediately instead of blocking the HTTP request until it's
# done. Poll /collect-status to see progress and the final result.
_collect_status = {
    "running": False,
    "last_started": None,
    "last_finished": None,
    "last_result": None,
}
_collect_lock = threading.Lock()


def _run_collect_job():
    try:
        new_rss = collect_rss(EXTRA_RSS_FEEDS)
        new_gnews = collect_gnews() if ENABLE_GNEWS else 0
        new_events = seed_events()
        _collect_status["last_result"] = {
            "new_rss_articles": new_rss,
            "new_gnews_articles": new_gnews,
            "new_events": new_events,
            "error": None,
        }
    except Exception as exc:
        log.exception("Background /collect job failed")
        _collect_status["last_result"] = {"error": str(exc)}
    finally:
        _collect_status["running"] = False
        _collect_status["last_finished"] = datetime.now(timezone.utc).isoformat()


@app.route("/health")
def health():
    return jsonify(status="ok")


@app.route("/collect", methods=["GET", "POST"])
def collect():
    if not _authorized():
        return jsonify(error="unauthorized"), 401
    if (err := _db_check()):
        return err
    with _collect_lock:
        if _collect_status["running"]:
            return jsonify(status="already_running",
                            started=_collect_status["last_started"]), 202
        _collect_status["running"] = True
        _collect_status["last_started"] = datetime.now(timezone.utc).isoformat()
    threading.Thread(target=_run_collect_job, daemon=True).start()
    return jsonify(status="started",
                    note="Collection runs in the background now -- poll /collect-status for the result."), 202


@app.route("/collect-status")
def collect_status():
    if not _authorized():
        return jsonify(error="unauthorized"), 401
    return jsonify(_collect_status)


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
    """Returns the digest as raw HTML, for Apps Script to send via GmailApp
    instead of Render's SMTP. Does NOT mark articles as sent here -- that
    only happens once Apps Script confirms GmailApp.sendEmail actually
    succeeded, via a follow-up call to /mark-emailed. This is what stops
    articles disappearing from every future digest if the Gmail send fails
    after this call (e.g. Gmail daily quota, bad EMAIL_TO address)."""
    if not _authorized():
        return jsonify(error="unauthorized"), 401
    if (err := _db_check()):
        return err
    html_content, critical_count, article_ids = build_digest()
    return jsonify(html=html_content, critical_count=critical_count,
                    article_ids=[str(i) for i in article_ids])


@app.route("/mark-emailed", methods=["POST"])
def mark_emailed_route():
    """Apps Script calls this right after GmailApp.sendEmail succeeds,
    passing back the article_ids it got from /digest-data. Only then do
    those articles stop appearing in future digests."""
    if not _authorized():
        return jsonify(error="unauthorized"), 401
    if (err := _db_check()):
        return err
    from bson import ObjectId
    ids = request.get_json(silent=True) or {}
    raw_ids = ids.get("article_ids", [])
    try:
        object_ids = [ObjectId(i) for i in raw_ids]
    except Exception:
        return jsonify(error="invalid article_ids"), 400
    mark_sent(object_ids)
    return jsonify(marked=len(object_ids))


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
    limit = request.args.get("limit", default=100000, type=int)
    category = request.args.get("category") or None
    sort_by = request.args.get("sort_by", default="score")
    html_out = build_dashboard_html(limit=limit, category=category, trigger_key=TRIGGER_SECRET, sort_by=sort_by)
    return Response(html_out, mimetype="text/html")


@app.route("/export.csv")
def export_csv():
    """Downloads every article in MongoDB as a CSV file -- a portable full
    backup you can keep locally, independent of both the dashboard view
    and the Telegram archive. Pass &category=X to export just one category."""
    if not _authorized():
        return jsonify(error="unauthorized"), 401
    if (err := _db_check()):
        return err
    category = request.args.get("category") or None
    articles = recent_articles(limit=1000000)
    if category:
        articles = [a for a in articles if (a.get("category") or "GENERAL") == category]
    buf = io.StringIO()
    fields = ["title", "source", "category", "risk_level", "score", "credibility",
              "country", "corroboration", "published", "created_at", "url", "summary"]
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for a in articles:
        writer.writerow(a)
    fname = f"geonews_export{'_' + category if category else ''}.csv"
    return Response(buf.getvalue(), mimetype="text/csv",
                     headers={"Content-Disposition": f"attachment; filename={fname}"})


@app.route("/cleanup-old", methods=["GET", "POST"])
def cleanup_old():
    """Deletes MongoDB metadata older than METADATA_CLEANUP_AFTER_DAYS.
    Nothing is lost: the full record for every article already lives
    permanently in the Telegram backup channel from collection time."""
    if not _authorized():
        return jsonify(error="unauthorized"), 401
    if (err := _db_check()):
        return err
    if not ENABLE_METADATA_CLEANUP:
        return jsonify(skipped="ENABLE_METADATA_CLEANUP is false")
    result = cleanup_old_metadata()
    return jsonify(result)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
