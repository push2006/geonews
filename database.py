"""MongoDB-backed storage layer.

Same function names/signatures as the original SQLite version, so nothing
in collectors/, processing/, or reports/ needs to change — they just call
save_article(), recent_articles(), etc. as before. Records behave like
dicts (a["title"], a["score"], ...) exactly like the old sqlite3.Row did.
"""
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError
from config import MONGODB_URI, MONGODB_DB_NAME

_client = None
_db = None


def connect():
    global _client, _db
    if _db is None:
        _client = MongoClient(MONGODB_URI)
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
