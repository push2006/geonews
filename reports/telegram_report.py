"""Optional Telegram digest, used only when ENABLE_TELEGRAM=true.

More reliable than CallMeBot/WhatsApp: official Bot API, no rate-limited
free-tier quirks, no per-message re-verification.

One-time setup:
  1. Message @BotFather on Telegram, send /newbot, follow prompts.
     It gives you a token -> TELEGRAM_BOT_TOKEN in .env.
  2. Message your new bot once (anything).
  3. Visit https://api.telegram.org/bot<token>/getUpdates in a browser and
     read your chat id from the JSON -> TELEGRAM_CHAT_ID in .env.
"""
import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, UPCOMING_DAYS
from database import recent_articles, upcoming_events


def build_message(limit=8):
    articles = [a for a in recent_articles() if a["score"] >= 4][:limit]
    events = upcoming_events(UPCOMING_DAYS)[:3]

    lines = ["*Global Geopolitical Intelligence*", ""]
    if events:
        lines.append("*Upcoming:*")
        for e in events:
            lines.append(f"- {e['name'][:70]} ({e['event_date']})")
        lines.append("")

    lines.append("*Top developments:*")
    for i, a in enumerate(articles, 1):
        lines.append(f"{i}. [{a['risk_level']}] {a['title'][:80]}")
        lines.append(f"   _{a['source']}_ - {a['url']}")
    if not articles:
        lines.append("No high-relevance items this cycle.")

    msg = "\n".join(lines)
    return msg[:4000] + "\n\n...(truncated)" if len(msg) > 4000 else msg


def send():
    if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    params = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": build_message(),
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    r = requests.post(url, data=params, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"Telegram error: {r.text}")
