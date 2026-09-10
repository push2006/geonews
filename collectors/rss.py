import feedparser
import requests
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
from config import (MAX_ITEMS_PER_FEED, LOOKBACK_HOURS, ENABLE_FULL_TEXT,
                     FULL_TEXT_MAX_CHARS, FULL_TEXT_WORKERS, DEDUPE_THRESHOLD,
                     ACTIVE_CATEGORIES, ENABLE_TELEGRAM_BACKUP, REQUEST_TIMEOUT)
from processing.classifier import classify, parse_date, strip_html
from processing.extract import extract_full_text
from processing.dedupe import dedupe_articles
from reports.telegram_backup import attach_backup_refs
from database import save_articles_bulk, update_telegram_refs
import threading

# Deduplicated source list: major news, official/multilateral bodies,
# think-tank & academic research feeds, and sanctions/trade-law trackers.
DEFAULT_FEEDS = [
    # --- major news --- (name, url, credibility)
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml", "HIGH"),
    ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml", "HIGH"),
    ("Reuters World", "https://www.reutersagency.com/feed/", "HIGH"),
    ("NYT World", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "HIGH"),
    ("The Guardian World", "https://www.theguardian.com/world/rss", "HIGH"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", "HIGH"),
    ("The Hindu", "https://www.thehindu.com/feeder/default.rss", "HIGH"),
    ("Indian Express", "https://indianexpress.com/section/india/feed/", "HIGH"),
    ("Mint", "https://www.livemint.com/rss/news", "HIGH"),

    # --- official / multilateral sources ---
    ("WTO News", "https://www.wto.org/english/news_e/news_e.rss", "HIGH"),
    ("UN News", "https://news.un.org/feed/subscribe/en/news/topic/world/feed/rss.xml", "HIGH"),
    ("UNCTAD", "https://unctad.org/rss.xml", "HIGH"),
    ("PIB India", "https://pib.gov.in/RssMain.aspx?ModId=8&Lang=1&Regid=1", "HIGH"),

    # --- research papers / think tanks / academic ---
    ("arXiv Economics", "https://export.arxiv.org/rss/econ.GN", "HIGH"),
    ("BIS Research", "https://www.bis.org/rss/research.rss", "HIGH"),
    ("NBER Working Papers", "https://www.nber.org/rss/new.xml", "HIGH"),
    ("CEPR / VoxEU", "https://cepr.org/rss/vox-content", "HIGH"),
    ("Peterson Institute (PIIE)", "https://www.piie.com/rss/update.xml", "HIGH"),
    ("Foreign Policy", "https://foreignpolicy.com/feed/", "MEDIUM"),

    # --- sanctions & trade law trackers ---
    ("Baker McKenzie Sanctions", "https://sanctionsnews.bakermckenzie.com/feed/", "HIGH"),
    ("Global Trade & Sanctions Law", "https://www.globaltradeandsanctionslaw.com/feed/", "MEDIUM"),

    # --- user-requested additional sources ---
    # NOTE: these feed URLs use each site's standard RSS path but weren't
    # live-verified (no network access at build time). If a source below
    # shows 0 items after running, its RSS path may need updating.
    ("Devdiscourse", "https://www.devdiscourse.com/rss", "MEDIUM"),
    ("Amnesty International", "https://www.amnesty.org/en/feed/", "HIGH"),
    ("InsiderNJ", "https://www.insidernj.com/feed/", "LOW"),
    ("Australian Institute of International Affairs", "https://www.internationalaffairs.org.au/feed/", "HIGH"),
]


def _enrich_with_full_text(articles):
    """Optionally replace short RSS summaries with extracted article text."""
    if not ENABLE_FULL_TEXT or not articles:
        return articles

    def process(art):
        if len(art["summary"]) < 200:
            full = extract_full_text(art["url"], max_chars=FULL_TEXT_MAX_CHARS)
            if full:
                art["summary"] = full
        return art

    with ThreadPoolExecutor(max_workers=FULL_TEXT_WORKERS) as executor:
        return list(executor.map(process, articles))


_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; GeoIntelMonitor/2.0; +https://render.com)"}


def _fetch_feed(feed_spec, cutoff):
    """Fetch + parse one feed. Isolated so it can run in a worker thread and
    a single slow/broken source never blocks the others.

    Uses requests.get(timeout=REQUEST_TIMEOUT) instead of
    feedparser.parse(url) directly -- feedparser's own URL fetching does NOT
    respect REQUEST_TIMEOUT (or any timeout, by default), so a single slow
    or hanging feed could previously stall its worker thread far longer
    than the configured timeout, slowing down the whole collection cycle
    even though fetching is threaded. Fetching with requests first and
    handing feedparser the already-downloaded bytes fixes that -- this feed
    now genuinely gives up after REQUEST_TIMEOUT seconds like every other
    HTTP call in this project."""
    source, url, credibility = feed_spec
    out = []
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers=_HEADERS)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        for entry in feed.entries[:MAX_ITEMS_PER_FEED]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            summary = strip_html(entry.get("summary", entry.get("description", "")))
            if not title or not link:
                continue
            published = parse_date(entry.get("published", entry.get("updated", "")))
            if published < cutoff:
                continue
            out.append({
                "title": title, "url": link, "source": source,
                "credibility": credibility,
                "summary": summary, "published": published,
            })
    except Exception as exc:
        print(f"[RSS] {source}: {exc}")
    return out


def collect(extra_feeds=None):
    feeds = DEFAULT_FEEDS + [("Custom", u, "MEDIUM") for u in (extra_feeds or [])]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)

    # Feeds are fetched concurrently, not one-by-one. With ~28 sources and a
    # REQUEST_TIMEOUT-driven worst case per feed, a sequential loop could
    # take several minutes and blow past gunicorn's request timeout when
    # this runs behind /collect on Render. Threaded fetch keeps a full
    # collection cycle to roughly the slowest single feed instead of the
    # sum of all of them. Cap raised from 12 to 20 -- fetching is I/O-bound
    # (waiting on network, not CPU), so more concurrent threads than feeds
    # up to a point costs nothing and shortens the worst-case tail when a
    # few sources are slow.
    candidates = []
    with ThreadPoolExecutor(max_workers=min(20, len(feeds) or 1)) as executor:
        for result in executor.map(lambda f: _fetch_feed(f, cutoff), feeds):
            candidates.extend(result)

    candidates = _enrich_with_full_text(candidates)

    # Classify BEFORE dedupe (not after) so that when the same story is
    # reported by multiple sources, dedupe can keep the highest-scoring
    # version instead of arbitrarily keeping whichever source happened to
    # be listed first in DEFAULT_FEEDS.
    for art in candidates:
        category, score, level, country = classify(art["title"], art["summary"])
        art["category"], art["score"], art["risk_level"], art["country"] = category, score, level, country

    candidates = dedupe_articles(candidates, threshold=DEDUPE_THRESHOLD, score_key="score")
    candidates = [a for a in candidates if a["category"] in ACTIVE_CATEGORIES]

    # MongoDB write happens FIRST and is what /collect waits for -- this is
    # the fast path (one bulk round-trip). Telegram backup used to run
    # synchronously right here before this fix, which could push a single
    # /collect request past Render's own reverse-proxy timeout (separate
    # from and not fixable via gunicorn's --timeout) whenever several
    # message batches were needed or Telegram was slow to respond -- that
    # was causing 502 Bad Gateway on every /collect call. Telegram backup
    # now happens in a background thread AFTER this function has already
    # returned its result to the caller, so /collect's response time is no
    # longer coupled to Telegram's latency at all.
    docs = [{
        "title": art["title"], "url": art["url"], "source": art["source"],
        "credibility": art.get("credibility", "MEDIUM"),
        "corroboration": art.get("corroboration", 1),
        "category": art["category"],
        # Short preview only -- full text lives in the Telegram backup
        # message (telegram_url below, filled in later by the background
        # thread), not duplicated here.
        "summary": art["summary"][:300],
        "telegram_message_id": None,
        "telegram_url": "",
        "published": art["published"].isoformat(), "score": art["score"],
        "risk_level": art["risk_level"], "country": art["country"],
    } for art in candidates]

    saved_count = save_articles_bulk(docs)

    if ENABLE_TELEGRAM_BACKUP and candidates:
        def _backup_in_background(arts):
            try:
                backed_up = attach_backup_refs(arts)
                update_telegram_refs(backed_up)
            except Exception as exc:
                print(f"[TELEGRAM BACKUP] background thread error: {exc}")

        threading.Thread(target=_backup_in_background, args=(candidates,), daemon=True).start()

    return saved_count
