"""Optional WhatsApp digest via CallMeBot, used only when ENABLE_WHATSAPP=true.

CallMeBot setup (one-time, per phone number):
  1. Save +34 644 59 71 88 as a contact on the sending WhatsApp account.
  2. Message it: "I allow callmebot to send me messages"
  3. It replies with your personal apikey -> put it in .env as WHATSAPP_APIKEY.
Docs: https://www.callmebot.com/blog/free-api-whatsapp-messages/
"""
import requests
from config import WHATSAPP_PHONE, WHATSAPP_APIKEY, UPCOMING_DAYS
from database import recent_articles, upcoming_events


def build_message(limit=6):
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
        lines.append(f"   _{a['source']}_")
    if not articles:
        lines.append("No high-relevance items this cycle.")

    msg = "\n".join(lines)
    return msg[:3900] + "\n\n...(truncated)" if len(msg) > 3900 else msg


def send():
    if not all([WHATSAPP_PHONE, WHATSAPP_APIKEY]):
        raise RuntimeError("Set WHATSAPP_PHONE and WHATSAPP_APIKEY in .env")
    message = build_message()
    url = "https://api.callmebot.com/whatsapp.php"
    params = {"phone": WHATSAPP_PHONE, "text": message, "apikey": WHATSAPP_APIKEY}
    r = requests.get(url, params=params, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"CallMeBot error: {r.text}")
