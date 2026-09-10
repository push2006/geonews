"""MongoDB-backed storage layer.

Same function names/signatures as the original SQLite version, so nothing
in collectors/, processing/, or reports/ needs to change — they just call
save_article(), recent_articles(), etc. as before. Records behave like
dicts (a["title"], a["score"], ...) exactly like the old sqlite3.Row did.
"""
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError, BulkWriteError
from config import MONGODB_URI, MONGODB_DB_NAME

_client = None
_db = None


def connect():
    global _client, _db
    if _db is None:
        # Explicit timeouts: without these, a bad/unreachable MONGODB_URI
        # (wrong password, IP not allow-listed in Atlas, typo'd cluster
        # host) hangs the request for minutes instead of failing fast with
        # a clear error.
        _client = MongoClient(
            MONGODB_URI,
            serverSelectionTimeoutMS=8000,
            connectTimeoutMS=8000,
        )
        _db = _client[MONGODB_DB_NAME]
    return _db


def init_db():
    db = connect()
    db.articles.create_index([("url", ASCENDING)], unique=True)
    db.articles.create_index([("score", DESCENDING)])
    db.events.create_index([("name", ASCENDING), ("event_date", ASCENDING)], unique=True)
    db.events.create_index([("event_date", ASCENDING)])


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def save_article(a):
    db = connect()
    doc = dict(a)
    doc.setdefault("created_at", _now_iso())
    try:
        db.articles.insert_one(doc)
        return True
    except DuplicateKeyError:
        return False


def save_articles_bulk(articles):
    """Inserts many articles in ONE round-trip to MongoDB instead of one
    insert_one() call per article -- this is what collectors/rss.py uses
    now, since sequential per-article round-trips were the slowest step in
    a collection cycle once feed fetching was already threaded (each
    round-trip pays full network latency to Atlas). ordered=False means
    Mongo keeps inserting the rest of the batch even after hitting a
    duplicate url, instead of stopping at the first one -- so a batch of
    30 articles where 5 are already-seen duplicates still saves the other
    25 in this same single call. Returns the count of articles actually
    inserted (duplicates don't count, same semantics as calling
    save_article() in a loop)."""
    if not articles:
        return 0
    db = connect()
    for doc in articles:
        doc.setdefault("created_at", _now_iso())
    try:
        result = db.articles.insert_many(articles, ordered=False)
        return len(result.inserted_ids)
    except BulkWriteError as bwe:
        # Some documents inserted, some failed (almost always duplicate
        # urls colliding with the unique index) -- count is total attempted
        # minus how many actually errored out.
        return len(articles) - len(bwe.details.get("writeErrors", []))


def save_event(e):
    db = connect()
    doc = dict(e)
    doc.setdefault("created_at", _now_iso())
    try:
        db.events.insert_one(doc)
        return True
    except DuplicateKeyError:
        return False


def recent_articles(limit=60):
    db = connect()
    cur = db.articles.find().sort([("score", DESCENDING), ("published", DESCENDING)]).limit(limit)
    return list(cur)


def unemailed_articles(limit=60):
    """Same as recent_articles(), but excludes anything already included in
    a previous digest — this is what stops the 10pm email repeating the
    same stories the 10am one already sent."""
    db = connect()
    cur = db.articles.find({"emailed": {"$ne": True}}) \
        .sort([("score", DESCENDING), ("published", DESCENDING)]).limit(limit)
    return list(cur)


def mark_emailed(article_ids):
    """Flags the given articles (by their MongoDB _id) as already sent in
    a digest, so the next digest won't repeat them."""
    if not article_ids:
        return
    db = connect()
    db.articles.update_many({"_id": {"$in": list(article_ids)}}, {"$set": {"emailed": True}})


def get_articles_older_than(days):
    """Articles older than N days (by created_at), oldest first — used by
    the Telegram archive/purge job to keep MongoDB from filling up over a
    long deployment lifetime."""
    db = connect()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    cur = db.articles.find({"created_at": {"$lt": cutoff}}).sort("created_at", ASCENDING)
    return list(cur)


def delete_articles(article_ids):
    """Deletes the given articles by _id. Only ever called AFTER they've
    been successfully archived to Telegram — never deletes unarchived
    data."""
    if not article_ids:
        return 0
    db = connect()
    result = db.articles.delete_many({"_id": {"$in": list(article_ids)}})
    return result.deleted_count


def upcoming_events(days=90):
    db = connect()
    today = datetime.now(timezone.utc).date()
    end = today + timedelta(days=days)
    cur = db.events.find({
        "event_date": {"$gte": today.isoformat(), "$lte": end.isoformat()}
    }).sort("event_date", ASCENDING)
    return list(cur)


def critical_since(hours=6):
    db = connect()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    cur = db.articles.find({
        "risk_level": "CRITICAL",
        "created_at": {"$gte": cutoff}
    }).sort("score", DESCENDING)
    return list(cur)


def weekly_top_articles(days=7, limit=20):
    db = connect()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    cur = db.articles.find({
        "created_at": {"$gte": cutoff}
    }).sort("score", DESCENDING).limit(limit)
    return list(cur)


def category_counts(days=7):
    db = connect()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    pipeline = [
        {"$match": {"created_at": {"$gte": cutoff}}},
        {"$group": {"_id": "$category", "cnt": {"$sum": 1}}},
        {"$sort": {"cnt": -1}},
    ]
    return [{"category": r["_id"], "cnt": r["cnt"]} for r in db.articles.aggregate(pipeline)]


def top_countries(days=7, limit=8):
    db = connect()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    pipeline = [
        {"$match": {"created_at": {"$gte": cutoff}, "country": {"$nin": [None, ""]}}},
        {"$group": {"_id": "$country", "cnt": {"$sum": 1}}},
        {"$sort": {"cnt": -1}},
        {"$limit": limit},
    ]
    return [{"country": r["_id"], "cnt": r["cnt"]} for r in db.articles.aggregate(pipeline)]
