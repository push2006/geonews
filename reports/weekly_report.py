"""Weekly trend summary, used only when ENABLE_WEEKLY_REPORT=true.

Sent once a week (config.WEEKLY_REPORT_DAY) alongside the normal daily
digest. Gives a 7-day view: top stories by score, which categories were
busiest, and which countries came up most -- useful for spotting a building
trend that no single day's digest would show on its own.
"""
import html
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import SMTP_HOST, SMTP_PORT, EMAIL_FROM, EMAIL_TO, EMAIL_APP_PASSWORD
from database import weekly_top_articles, category_counts, top_countries

CATEGORY_LABELS = {
    "GEOPOLITICS": "Geopolitics", "CONFERENCE": "Conferences & Meetings",
    "TRADE": "Trade Activity", "SANCTIONS": "Sanctions & Circulars",
    "RISK": "Risk Signals", "RESEARCH": "Research Papers & Documents",
    "GENERAL": "Other",
}


def build_html(days=7):
    top = weekly_top_articles(days=days, limit=20)
    cats = category_counts(days=days)
    countries = top_countries(days=days)

    body = [f"""<html><body style="margin:0;padding:0;background:#f4f6f8;font-family:Segoe UI,Arial,sans-serif">
    <table width="100%" cellpadding="0" cellspacing="0" style="padding:20px 0"><tr><td align="center">
    <table width="680" style="background:white;border-radius:10px;overflow:hidden">
    <tr><td style="background:linear-gradient(135deg,#2d3748,#4a5568);color:white;padding:24px 28px">
        <h1 style="margin:0;font-size:20px">📊 Weekly Geo Intel Summary</h1>
        <p style="margin:6px 0 0;font-size:12px;opacity:0.9">Last {days} days, as of {datetime.now().strftime('%d %b %Y')}</p>
    </td></tr>
    <tr><td style="padding:22px 28px">"""]

    if cats:
        body.append("<h2 style='font-size:16px;color:#1a365d'>Volume by category</h2><table style='width:100%;font-size:13px;margin-bottom:20px'>")
        for c in cats:
            label = CATEGORY_LABELS.get(c["category"], c["category"] or "Other")
            body.append(f"<tr><td style='padding:3px 0'>{html.escape(label)}</td><td style='text-align:right;color:#2b6cb0;font-weight:600'>{c['cnt']}</td></tr>")
        body.append("</table>")

    if countries:
        body.append("<h2 style='font-size:16px;color:#1a365d'>Most-mentioned countries</h2><p style='font-size:13px;color:#2d3748;margin-bottom:20px'>")
        body.append(" &nbsp;&middot;&nbsp; ".join(f"{html.escape(c['country'])} ({c['cnt']})" for c in countries))
        body.append("</p>")

    body.append("<h2 style='font-size:16px;color:#1a365d'>Top stories this week</h2>")
    for a in top:
        body.append(f"""
        <div style="margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid #e2e8f0">
            <div style="font-size:11px;color:#718096;text-transform:uppercase">{html.escape(a['source'] or '')} &middot; {a['risk_level']} &middot; {a['score']}/100</div>
            <a href="{html.escape(a['url'])}" style="font-size:14px;color:#1a365d;text-decoration:none;font-weight:600">{html.escape(a['title'])}</a>
        </div>""")

    body.append("""</td></tr>
    <tr><td style="background:#f7fafc;padding:14px 28px;text-align:center;font-size:12px;color:#718096">
        Auto-generated weekly rollup.
    </td></tr></table></td></tr></table></body></html>""")
    return "".join(body)


def send(days=7):
    if not all([EMAIL_FROM, EMAIL_TO, EMAIL_APP_PASSWORD]):
        raise RuntimeError("Set EMAIL_FROM, EMAIL_TO and EMAIL_APP_PASSWORD in .env")

    today = datetime.now().strftime("%d %b %Y")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📊 Geo Intel Weekly Summary — {today}"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(build_html(days), "html", "utf-8"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
        server.login(EMAIL_FROM, EMAIL_APP_PASSWORD)
        server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
