"""Long-term archive: moves old articles out of MongoDB and into a Telegram
channel, used only when ENABLE_TELEGRAM_ARCHIVE=true.

Why: MongoDB's free tier caps at 512MB. Rather than deleting old articles
outright (losing history) or paying for more storage, this posts them as
readable text to a Telegram channel (free, effectively unlimited), pins a
summary message so the archive is easy to find, and only deletes from
MongoDB once the Telegram post is confirmed sent — so a failed send never
loses data.

One-time setup (same bot as ENABLE_TELEGRAM, or a separate one):
  1. Create a Telegram channel (can be private).
  2. Add your bot as an admin of that channel (needed to post + pin).
  3. Get the channel's chat id (forward a message from it to
     @userinfobot, or use getUpdates like the digest bot setup) ->
     TELEGRAM_ARCHIVE_CHAT_ID in .env.
"""
import json
import requests
from datetime import datetime
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_ARCHIVE_CHAT_ID, ARCHIVE_AFTER_DAYS
from database import get_articles_older_than, delete_articles

TELEGRAM_MSG_LIMIT = 3500  # stay under Telegram's 4096 char hard limit, leaves margin


def _api(method):
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"


def _send_message(text, disable_preview=True):
    r = requests.post(_api("sendMessage"), data={
        "chat_id": TELEGRAM_ARCHIVE_CHAT_ID,
        "text": text,
        "disable_web_page_preview": disable_preview,
    }, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"Telegram sendMessage failed: {r.text}")
    return r.json()["result"]["message_id"]


def _pin_message(message_id):
    r = requests.post(_api("pinChatMessage"), data={
        "chat_id": TELEGRAM_ARCHIVE_CHAT_ID,
        "message_id": message_id,
        "disable_notification": True,
    }, timeout=20)
    # Pinning is a nice-to-have; don't fail the whole archive job if it
    # doesn't work (e.g. bot isn't admin) — the data is still safely posted.
    if r.status_code != 200:
        print(f"[ARCHIVE] Pin failed (non-fatal): {r.text}")


def _format_article_line(a):
    return (f"• [{a.get('risk_level','')}] {a.get('title','')[:120]}\n"
            f"  {a.get('source','')} · {a.get('category','')} · {a.get('published','')[:10]}\n"
            f"  {a.get('url','')}")


def _build_batches(articles):
    """Splits the article list into Telegram-message-sized text chunks."""
    batches, current = [], []
    current_len = 0
    for a in articles:
        line = _format_article_line(a)
        if current_len + len(line) + 2 > TELEGRAM_MSG_LIMIT and current:
            batches.append("\n\n".join(current))
            current, current_len = [], 0
        current.append(line)
        current_len += len(line) + 2
    if current:
        batches.append("\n\n".join(current))
    return batches


def archive_and_purge(days=None):
    """Main entry point. Returns a dict summary of what happened."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ARCHIVE_CHAT_ID:
        return {"error": "TELEGRAM_BOT_TOKEN or TELEGRAM_ARCHIVE_CHAT_ID not set"}

    days = days if days is not None else ARCHIVE_AFTER_DAYS
    old_articles = get_articles_older_than(days)
    if not old_articles:
        return {"archived": 0, "message": "Nothing older than the archive window."}

    date_from = old_articles[0].get("created_at", "")[:10]
    date_to = old_articles[-1].get("created_at", "")[:10]
    batches = _build_batches(old_articles)

    summary_text = (f"📦 Geo Intel Archive\n"
                     f"{len(old_articles)} articles, {date_from} to {date_to}\n"
                     f"Posted in {len(batches)} message(s) below.\n"
                     f"Archived {datetime.now().strftime('%d %b %Y %H:%M')}")

    try:
        summary_id = _send_message(summary_text)
        for batch in batches:
            _send_message(batch)
    except Exception as exc:
        # Nothing gets deleted from MongoDB unless every message sent
        # successfully — a failed archive attempt never loses data.
        return {"error": f"Telegram send failed, nothing deleted from MongoDB: {exc}"}

    _pin_message(summary_id)

    deleted = delete_articles([a["_id"] for a in old_articles])
    return {"archived": deleted, "batches_sent": len(batches), "date_range": f"{date_from} to {date_to}"}
