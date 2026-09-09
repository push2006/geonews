import argparse
from config import ENABLE_GNEWS, ENABLE_WHATSAPP, ENABLE_TELEGRAM, EXTRA_RSS_FEEDS
from config_check import check_config
from database import init_db
from collectors.rss import collect as collect_rss
from collectors.gnews_search import collect as collect_gnews
from collectors.events import seed_events
from reports.email_report import send as send_email
from reports.whatsapp_report import send as send_whatsapp
from reports.telegram_report import send as send_telegram
from reports.critical_alert import send_if_critical
from reports.weekly_report import send as send_weekly


def main():
    p = argparse.ArgumentParser(description="Geo Intel Monitor V2")
    p.add_argument("command", nargs="?",
                    choices=["init", "collect", "gnews", "events", "email",
                             "whatsapp", "telegram", "critical", "weekly", "run"],
                    default="run")
    args = p.parse_args()
    init_db()

    if not check_config(require_email=(args.command not in ("init", "collect", "gnews", "events"))):
        return

    if args.command in ("collect", "run"):
        print("New articles (RSS):", collect_rss(EXTRA_RSS_FEEDS))

    if args.command == "gnews" or (args.command == "run" and ENABLE_GNEWS):
        print("New articles (Google News):", collect_gnews())

    if args.command in ("events", "run"):
        print("New events:", seed_events())

    if args.command in ("email", "run"):
        send_email()
        print("Email sent.")

    if args.command == "critical":
        n = send_if_critical()
        print(f"Critical alert sent: {n} item(s)." if n else "No critical items — nothing sent.")

    if args.command == "weekly":
        send_weekly()
        print("Weekly summary sent.")

    if args.command == "whatsapp" or (args.command == "run" and ENABLE_WHATSAPP):
        send_whatsapp()
        print("WhatsApp sent.")

    if args.command == "telegram" or (args.command == "run" and ENABLE_TELEGRAM):
        send_telegram()
        print("Telegram sent.")


if __name__ == "__main__":
    main()
