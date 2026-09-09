import html
import smtplib
import ssl
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import (SMTP_HOST, SMTP_PORT, EMAIL_FROM, EMAIL_TO, EMAIL_APP_PASSWORD,
                     UPCOMING_DAYS, ARCHIVE_DIGESTS, ARCHIVE_DIR, ACTIVE_CATEGORIES)
from database import recent_articles, unemailed_articles, mark_emailed, upcoming_events

CATEGORY_LABELS = {
    "GEOPOLITICS": "🌍 Geopolitics",
    "CONFERENCE": "🗓️ Conferences & Meetings",
    "TRADE": "📦 Trade Activity",
    "SANCTIONS": "🚫 Sanctions & Circulars",
    "RISK": "⚠️ Risk Signals",
    "RESEARCH": "📄 Research Papers & Documents",
    "GENERAL": "📰 Other",
}
RISK_COLORS = {"CRITICAL": "#c53030", "HIGH": "#dd6b20", "MODERATE": "#d69e2e", "LOW": "#718096"}
MIN_SCORE = 4  # only include articles at/above this relevance score


def _group_articles(articles):
    grouped = defaultdict(list)
    for a in articles:
        if a["score"] < MIN_SCORE:
            continue
        grouped[a["category"] or "GENERAL"].append(a)
    return grouped


def _section_html(category, items):
    label = CATEGORY_LABELS.get(category, category.title())
    rows = [f"<h2 style='margin:28px 0 12px;font-size:19px;color:#1a365d;"
            f"border-bottom:2px solid #e2e8f0;padding-bottom:6px'>{html.escape(label)} "
            f"<span style='font-size:13px;color:#718096;font-weight:normal'>({len(items)})</span></h2>"]
    for a in items:
        color = RISK_COLORS.get(a["risk_level"], "#718096")
        credibility = a.get("credibility", "MEDIUM")
        cred_color = {"HIGH": "#2f855a", "MEDIUM": "#b7791f", "LOW": "#a0aec0"}.get(credibility, "#a0aec0")
        corroboration = a.get("corroboration", 1)
        rows.append(f"""
        <div style="margin-bottom:18px;padding:14px 16px;border-left:4px solid {color};background:#f7fafc;border-radius:4px">
            <div style="font-size:11px;color:#718096;font-weight:600;text-transform:uppercase;margin-bottom:4px">
                {html.escape(a['source'] or '')} &middot;
                <span style="color:{cred_color}">{html.escape(credibility)} credibility</span> &middot;
                <span style="color:{color}">{html.escape(a['risk_level'])}</span> &middot; score {a['score']}/100
                {f" &middot; {html.escape(a['country'])}" if a['country'] else ""}
                {f" &middot; confirmed by {corroboration} sources" if corroboration > 1 else ""}
            </div>
            <h3 style="margin:0 0 6px;font-size:15px;line-height:1.4">
                <a href="{html.escape(a['url'])}" style="color:#1a365d;text-decoration:none">{html.escape(a['title'])}</a>
            </h3>
            <p style="margin:0;font-size:13px;color:#2d3748;line-height:1.5">{html.escape((a['summary'] or '')[:600])}</p>
        </div>""")
    return "".join(rows)


def build_html(mark_as_sent=True):
    """Builds the digest HTML from articles not yet included in a previous
    digest. By default also marks them as sent, so the next call (the next
    scheduled digest) won't repeat the same stories. Pass
    mark_as_sent=False to preview without consuming the queue."""
    articles = unemailed_articles()
    events = upcoming_events(UPCOMING_DAYS)
    grouped = _group_articles(articles)
    total_relevant = sum(len(v) for v in grouped.values())
    critical_count = sum(1 for a in articles if a["risk_level"] == "CRITICAL")
    today = datetime.now().strftime("%d %B %Y")

    body = [f"""<html><body style="margin:0;padding:0;background:#f4f6f8;font-family:Segoe UI,Arial,sans-serif">
    <table width="100%" cellpadding="0" cellspacing="0" style="padding:20px 0"><tr><td align="center">
    <table width="700" style="background:#ffffff;border-radius:10px;overflow:hidden">
    <tr><td style="background:linear-gradient(135deg,#1a365d,#2b6cb0);padding:26px 30px;color:white">
        <h1 style="margin:0;font-size:22px">🌍 Global Geopolitical Intelligence — Daily Brief</h1>
        <p style="margin:8px 0 0;font-size:13px;opacity:0.9">{today}</p>
    </td></tr>
    <tr><td style="padding:18px 30px;background:#edf2f7;font-size:13px;color:#2d3748">
        <b>{total_relevant}</b> relevant items &middot;
        <b style="color:#c53030">{critical_count}</b> critical &middot;
        <b>{len(events)}</b> upcoming events in next {UPCOMING_DAYS} days
    </td></tr>
    <tr><td style="padding:10px 30px 25px">"""]

    if events:
        body.append("<h2 style='margin:20px 0 12px;font-size:19px;color:#1a365d;"
                     "border-bottom:2px solid #e2e8f0;padding-bottom:6px'>🗓️ Upcoming Events</h2>")
        for e in events:
            body.append(f"""<div style="margin-bottom:12px;padding:10px 14px;background:#f7fafc;border-radius:4px">
                <b>{html.escape(e['name'])}</b><br>
                <span style="font-size:12px;color:#718096">{html.escape(e['event_date'])} &middot;
                {html.escape(e['category'] or '')} &middot; {html.escape(e['confidence'] or '')}</span>
                <p style="margin:6px 0 0;font-size:13px">{html.escape(e['description'] or '')}</p>
                <a href="{html.escape(e['source_url'] or '')}" style="font-size:12px;color:#2b6cb0">Source →</a>
            </div>""")

    if total_relevant == 0:
        body.append("<p style='color:#718096'>No items scored above the relevance threshold this cycle.</p>")
    else:
        order = ACTIVE_CATEGORIES + [c for c in grouped if c not in ACTIVE_CATEGORIES]
        for category in order:
            if grouped.get(category):
                items = sorted(grouped[category], key=lambda a: a["score"], reverse=True)
                body.append(_section_html(category, items))

    body.append("""</td></tr>
    <tr><td style="background:#f7fafc;padding:16px 30px;text-align:center;font-size:12px;color:#718096">
        Auto-generated briefing. Verify important information with the original source.
    </td></tr>
    </table></td></tr></table></body></html>""")

    if mark_as_sent and articles:
        mark_emailed([a["_id"] for a in articles])

    return "".join(body)


def _archive(html_content):
    if not ARCHIVE_DIGESTS:
        return
    try:
        Path(ARCHIVE_DIR).mkdir(parents=True, exist_ok=True)
        filename = datetime.now().strftime("%Y-%m-%d") + ".html"
        (Path(ARCHIVE_DIR) / filename).write_text(html_content, encoding="utf-8")
    except Exception as exc:
        print(f"[ARCHIVE] Could not save digest: {exc}")


def send():
    if not all([EMAIL_FROM, EMAIL_TO, EMAIL_APP_PASSWORD]):
        raise RuntimeError("Set EMAIL_FROM, EMAIL_TO and EMAIL_APP_PASSWORD in .env")

    html_content = build_html()
    _archive(html_content)

    today = datetime.now().strftime("%d %b %Y")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🌍 Geo Intel Daily Brief — {today}"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
        server.login(EMAIL_FROM, EMAIL_APP_PASSWORD)
        server.sendmail(EMAIL_FROM, [addr.strip() for addr in EMAIL_TO.split(",")], msg.as_string())
