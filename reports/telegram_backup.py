"""Telegram = full data storage, used when ENABLE_TELEGRAM_BACKUP=true.

Every article collected gets its COMPLETE record (title, url, source,
category, full summary/extracted text, score, risk level, country,
credibility, corroboration, published date) posted as text to a dedicated
Telegram channel via your bot. MongoDB then only keeps a lightweight
metadata copy (short preview, not the full text) plus a link back to the
Telegram message -- Telegram is the actual full-content database, MongoDB
is an index/cache on top of it for fast dashboard queries.

Why batched, not one message per article: Telegram rate-limits a bot to
roughly 20 messages/minute into the same chat. A collection cycle can
easily find 10-30 new articles at once, so this groups them into as few
messages as fit under Telegram's 4096-character limit and sends those,
instead of one API call per article. Every article in a given batch shares
that batch's message_id/permalink -- good enough to jump straight to the
full data, even though it's not one-message-per-article granularity.
"""
import requests
from config import TELEGRAM_BACKUP_BOT_TOKEN, TELEGRAM_BACKUP_CHAT_ID

TELEGRAM_MSG_LIMIT = 3500  # stay under Telegram's 4096 hard limit, leaves margin


def _api(method):
    return f"https://api.telegram.org/bot{TELEGRAM_BACKUP_BOT_TOKEN}/{method}"


def _permalink(message_id):
    """Builds a jump-to-message link. Works for public channels (@username)
    and private channels (numeric -100xxxxxxxxxx chat id)."""
    chat = TELEGRAM_BACKUP_CHAT_ID
    if chat.startswith("@"):
        return f"https://t.me/{chat.lstrip('@')}/{message_id}"
    if chat.startswith("-100"):
        return f"https://t.me/c/{chat[4:]}/{message_id}"
    return ""  # unrecognized chat id format -- link omitted, data is still backed up


def _format_full_record(a):
    return (
        f"📌 {a.get('title','')}\n"
        f"Source: {a.get('source','')} | Credibility: {a.get('credibility','MEDIUM')}\n"
        f"Category: {a.get('category','')} | Risk: {a.get('risk_level','')} | Score: {a.get('score',0)}/100\n"
        f"Country: {a.get('country','') or '—'} | Corroborated by: {a.get('corroboration',1)} source(s)\n"
        f"Published: {a.get('published','')}\n"
        f"URL: {a.get('url','')}\n"
        f"--\n"
        f"{a.get('summary','')}"
    )


def _split_into_batches(articles):
    """Groups articles into batches that fit Telegram's message length
    limit. Returns a list of (article_index_span, batch_text) so the
    caller can map each sent message back to exactly which articles it
    covers -- single source of truth, used for both sending and mapping."""
    batches = []
    current_records, current_indices, current_len = [], [], 0
    start_idx = 0

    for i, a in enumerate(articles):
        record = _format_full_record(a)
        record_len = len(record) + 2
        if current_len + record_len > TELEGRAM_MSG_LIMIT and current_records:
            batches.append(((start_idx, i), "\n\n====\n\n".join(current_records)))
            current_records, current_indices, current_len = [], [], 0
            start_idx = i
        current_records.append(record)
        current_len += record_len

    if current_records:
        batches.append(((start_idx, len(articles)), "\n\n====\n\n".join(current_records)))
    return batches


def attach_backup_refs(articles):
    """Backs up all `articles` to Telegram and mutates each dict in place
    with telegram_message_id / telegram_url. Returns the same list.
    On any failure for a given batch, the articles in that batch simply get
    telegram_url="" -- collection still proceeds and nothing else is lost."""
    for a in articles:
        a.setdefault("telegram_message_id", None)
        a.setdefault("telegram_url", "")

    if not articles or not TELEGRAM_BACKUP_BOT_TOKEN or not TELEGRAM_BACKUP_CHAT_ID:
        return articles

    for (start, end), batch_text in _split_into_batches(articles):
        try:
            r = requests.post(_api("sendMessage"), data={
                "chat_id": TELEGRAM_BACKUP_CHAT_ID,
                "text": batch_text,
                "disable_web_page_preview": True,
            }, timeout=20)
            if r.status_code != 200:
                print(f"[TELEGRAM BACKUP] sendMessage failed: {r.text[:300]}")
                continue
            message_id = r.json()["result"]["message_id"]
            link = _permalink(message_id)
            for a in articles[start:end]:
                a["telegram_message_id"] = message_id
                a["telegram_url"] = link
        except Exception as exc:
            print(f"[TELEGRAM BACKUP] error: {exc}")

    return articles
