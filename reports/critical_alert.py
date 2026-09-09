"""Instant critical-risk alert, used only when ENABLE_CRITICAL_ALERTS=true.

Fires right after each collection cycle if anything scored CRITICAL was
saved in the last CRITICAL_ALERT_LOOKBACK_HOURS -- so you find out about a
major sanctions package or escalation the same cycle it's detected, rather
than waiting for the next scheduled daily digest.
"""
import html
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import (SMTP_HOST, SMTP_PORT, EMAIL_FROM, EMAIL_TO,
                     EMAIL_APP_PASSWORD, CRITICAL_ALERT_LOOKBACK_HOURS)
from database import critical_since


def build_html(items):
    rows = [f"""<html><body style="font-family:Segoe UI,Arial,sans-serif;background:#fff5f5;padding:20px">
    <div style="max-width:640px;margin:auto;background:white;border:2px solid #c53030;border-radius:8px;overflow:hidden">
    <div style="background:#c53030;color:white;padding:18px 24px">
        <h1 style="margin:0;font-size:19px">🚨 Critical Geo Intel Alert</h1>
        <p style="margin:6px 0 0;font-size:12px;opacity:0.9">{datetime.now().strftime('%d %b %Y | %H:%M')}</p>
    </div>
    <div style="padding:20px 24px">"""]
    for a in items:
        rows.append(f"""
        <div style="margin-bottom:16px;padding-bottom:14px;border-bottom:1px solid #fed7d7">
            <div style="font-size:11px;color:#718096;font-weight:600;text-transform:uppercase">
                {html.escape(a['source'] or '')} &middot; score {a['score']}/100
                {f" &middot; {html.escape(a['country'])}" if a['country'] else ""}
            </div>
            <h3 style="margin:4px 0 6px;font-size:15px">
                <a href="{html.escape(a['url'])}" style="color:#c53030;text-decoration:none">{html.escape(a['title'])}</a>
            </h3>
            <p style="margin:0;font-size:13px;color:#2d3748">{html.escape((a['summary'] or '')[:400])}</p>
        </div>""")
    rows.append("</div></div></body></html>")
    return "".join(rows)


def send_if_critical():
    """Returns the number of critical items alerted on (0 if none / nothing sent)."""
    items = critical_since(CRITICAL_ALERT_LOOKBACK_HOURS)
    if not items:
        return 0
    if not all([EMAIL_FROM, EMAIL_TO, EMAIL_APP_PASSWORD]):
        raise RuntimeError("Set EMAIL_FROM, EMAIL_TO and EMAIL_APP_PASSWORD in .env")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🚨 CRITICAL Geo Intel Alert — {len(items)} item(s)"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(build_html(items), "html", "utf-8"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
        server.login(EMAIL_FROM, EMAIL_APP_PASSWORD)
        server.sendmail(EMAIL_FROM, [addr.strip() for addr in EMAIL_TO.split(",")], msg.as_string())
    return len(items)
