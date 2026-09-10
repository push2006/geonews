"""Startup config validation.

Checks that whichever features are enabled in .env actually have the
credentials they need, and fails fast with a clear message instead of
crashing deep inside a send() call at 7am with no one watching.
"""
import sys
import config as cfg


def check_config(require_email=True):
    problems = []

    if not cfg.MONGODB_URI:
        problems.append(
            "MONGODB_URI is not set in .env — get a free connection string "
            "from MongoDB Atlas (Database > Connect > Drivers)."
        )

    if require_email:
        if not cfg.EMAIL_FROM or not cfg.EMAIL_TO or not cfg.EMAIL_APP_PASSWORD:
            problems.append(
                "Email is not configured: set EMAIL_FROM, EMAIL_TO and "
                "EMAIL_APP_PASSWORD in .env (use a Google App Password, not "
                "your real Gmail password)."
            )

    if cfg.ENABLE_GNEWS:
        try:
            import gnews  # noqa: F401
        except ImportError:
            problems.append(
                "ENABLE_GNEWS=true but the 'gnews' package isn't installed. "
                "Run: pip install gnews"
            )

    if cfg.ENABLE_FULL_TEXT:
        try:
            import trafilatura  # noqa: F401
        except ImportError:
            problems.append(
                "ENABLE_FULL_TEXT=true but 'trafilatura' isn't installed. "
                "Run: pip install trafilatura"
            )

    if cfg.ENABLE_WHATSAPP and (not cfg.WHATSAPP_PHONE or not cfg.WHATSAPP_APIKEY):
        problems.append(
            "ENABLE_WHATSAPP=true but WHATSAPP_PHONE / WHATSAPP_APIKEY are "
            "missing in .env."
        )

    if cfg.ENABLE_TELEGRAM and (not cfg.TELEGRAM_BOT_TOKEN or not cfg.TELEGRAM_CHAT_ID):
        problems.append(
            "ENABLE_TELEGRAM=true but TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID "
            "are missing in .env."
        )

    if cfg.ENABLE_TELEGRAM_BACKUP and (not cfg.TELEGRAM_BACKUP_BOT_TOKEN or not cfg.TELEGRAM_BACKUP_CHAT_ID):
        problems.append(
            "ENABLE_TELEGRAM_BACKUP=true but TELEGRAM_BACKUP_BOT_TOKEN / "
            "TELEGRAM_BACKUP_CHAT_ID are missing in .env. Without these, "
            "collected articles are never backed up to Telegram and "
            "MongoDB metadata cleanup (if enabled) would delete data with "
            "no full copy anywhere."
        )

    if cfg.ENABLE_METADATA_CLEANUP and not cfg.ENABLE_TELEGRAM_BACKUP:
        problems.append(
            "ENABLE_METADATA_CLEANUP=true but ENABLE_TELEGRAM_BACKUP=false — "
            "cleanup permanently deletes MongoDB records on the assumption "
            "a full copy already exists on Telegram. With backup off, "
            "enabling cleanup would destroy data with no copy anywhere. "
            "Turn on ENABLE_TELEGRAM_BACKUP first, or leave cleanup off."
        )

    if problems:
        print("Configuration problem(s) found:\n")
        for p in problems:
            print(f"  - {p}")
        print("\nFix .env and try again.")
        return False
    return True


if __name__ == "__main__":
    ok = check_config()
    sys.exit(0 if ok else 1)
