"""Self-contained daily (+ optional weekly, + optional instant critical alert)
scheduler.

Unlike run_daily.sh/.bat (which need external cron / Task Scheduler and die
silently on any error), this script:
  - runs continuously and fires the full pipeline once a day at DAILY_RUN_TIME
  - optionally sends a weekly trend rollup on WEEKLY_REPORT_DAY
  - optionally sends an instant alert email as soon as a CRITICAL item shows up
  - catches and logs any exception per-step so one broken source or a failed
    send never kills the scheduler loop
  - retries the daily email send up to 3 times before giving up for that cycle
  - writes everything to logs/app.log as well as the console

Usage:
    python scheduler.py            # loop forever, run at DAILY_RUN_TIME
    python scheduler.py --now      # also run once immediately, then loop
"""
import argparse
import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import schedule

from config import (DAILY_RUN_TIME, WEEKLY_REPORT_DAY, ENABLE_GNEWS,
                     ENABLE_WHATSAPP, ENABLE_TELEGRAM, ENABLE_CRITICAL_ALERTS,
                     ENABLE_WEEKLY_REPORT, EXTRA_RSS_FEEDS)
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

Path("logs").mkdir(exist_ok=True)
logger = logging.getLogger("geo_intel")
logger.setLevel(logging.INFO)
_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
_file_handler = RotatingFileHandler("logs/app.log", maxBytes=2_000_000, backupCount=3)
_file_handler.setFormatter(_fmt)
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_fmt)
logger.addHandler(_file_handler)
logger.addHandler(_console_handler)


def _step(name, fn, *args):
    """Run one pipeline step; log and swallow errors so the cycle continues."""
    try:
        result = fn(*args)
        logger.info(f"{name}: OK ({result})")
        return result
    except Exception:
        logger.exception(f"{name}: FAILED")
        return None


def _send_with_retry(name, fn, attempts=3, delay_seconds=30):
    for attempt in range(1, attempts + 1):
        try:
            fn()
            logger.info(f"{name}: OK (attempt {attempt})")
            return True
        except Exception:
            logger.exception(f"{name}: FAILED (attempt {attempt}/{attempts})")
            if attempt < attempts:
                time.sleep(delay_seconds)
    logger.error(f"{name}: giving up after all retries.")
    return False


def run_daily_cycle():
    logger.info("=== Daily cycle started ===")
    init_db()
    _step("RSS collect", collect_rss, EXTRA_RSS_FEEDS)
    if ENABLE_GNEWS:
        _step("Google News collect", collect_gnews)
    _step("Events seed", seed_events)

    if ENABLE_CRITICAL_ALERTS:
        _step("Critical alert check", send_if_critical)

    _send_with_retry("Daily email", send_email)

    if ENABLE_WHATSAPP:
        _step("WhatsApp send", send_whatsapp)
    if ENABLE_TELEGRAM:
        _step("Telegram send", send_telegram)

    logger.info("=== Daily cycle finished ===")


def run_weekly_cycle():
    logger.info("--- Weekly summary triggered ---")
    _send_with_retry("Weekly email", send_weekly)


def main():
    parser = argparse.ArgumentParser(description="Geo Intel scheduler")
    parser.add_argument("--now", action="store_true", help="Run the daily cycle once immediately, then keep the schedule")
    args = parser.parse_args()

    if not check_config(require_email=True):
        return

    schedule.every().day.at(DAILY_RUN_TIME).do(run_daily_cycle)
    logger.info(f"Daily run scheduled for {DAILY_RUN_TIME} (local time).")

    if ENABLE_WEEKLY_REPORT:
        day_job = getattr(schedule.every(), WEEKLY_REPORT_DAY, schedule.every().monday)
        day_job.at(DAILY_RUN_TIME).do(run_weekly_cycle)
        logger.info(f"Weekly summary scheduled for {WEEKLY_REPORT_DAY} at {DAILY_RUN_TIME}.")

    logger.info("Scheduler started. Ctrl+C to stop.")

    if args.now:
        run_daily_cycle()

    while True:
        try:
            schedule.run_pending()
        except Exception:
            logger.exception("Scheduler loop error (continuing)")
        time.sleep(30)


if __name__ == "__main__":
    main()
