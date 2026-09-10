"""Periodic MongoDB metadata cleanup, used when ENABLE_METADATA_CLEANUP=true.

The full record for every article already lives permanently in the
Telegram backup channel from the moment it was collected (see
telegram_backup.py) -- so unlike the old design, this does NOT need to
post anything anywhere before deleting. It just removes MongoDB metadata
older than METADATA_CLEANUP_AFTER_DAYS to keep the free 512MB Atlas tier
from filling up over a long-running deployment. Nothing is lost: the
telegram_url on each dashboard/digest entry already points at the full
record, and that record stays on Telegram indefinitely.
"""
from config import METADATA_CLEANUP_AFTER_DAYS
from database import get_articles_older_than, delete_articles


def cleanup(days=None):
    """Main entry point. Returns a dict summary of what happened."""
    days = days if days is not None else METADATA_CLEANUP_AFTER_DAYS
    old_articles = get_articles_older_than(days)
    if not old_articles:
        return {"deleted": 0, "message": "Nothing older than the cleanup window."}

    date_from = old_articles[0].get("created_at", "")[:10]
    date_to = old_articles[-1].get("created_at", "")[:10]
    deleted = delete_articles([a["_id"] for a in old_articles])
    return {
        "deleted": deleted,
        "date_range": f"{date_from} to {date_to}",
        "note": "Full records for these remain permanently in the Telegram backup channel.",
    }
