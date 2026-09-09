import feedparser
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
from config import (MAX_ITEMS_PER_FEED, LOOKBACK_HOURS, ENABLE_FULL_TEXT,
                     FULL_TEXT_MAX_CHARS, FULL_TEXT_WORKERS, DEDUPE_THRESHOLD,
                     ACTIVE_CATEGORIES)
from processing.classifier import classify, parse_date
from processing.extract import extract_full_text
from processing.dedupe import dedupe_articles
from database import save_article

# Deduplicated source list: major news, official/multilateral bodies,
# think-tank & academic research feeds, and sanctions/trade-law trackers.
DEFAULT_FEEDS = [
    # --- major news ---
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("Reuters World", "https://www.reutersagency.com/feed/"),
    ("NYT World", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"),
    ("The Guardian World", "https://www.theguardian.com/world/rss"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("The Hindu", "https://www.thehindu.com/feeder/default.rss"),
    ("Indian Express", "https://indianexpress.com/section/india/feed/"),
    ("Mint", "https://www.livemint.com/rss/news"),

    # --- official / multilateral sources ---
    ("WTO News", "https://www.wto.org/english/news_e/news_e.rss"),
    ("UN News", "https://news.un.org/feed/subscribe/en/news/topic/world/feed/rss.xml"),
    ("UNCTAD", "https://unctad.org/rss.xml"),
    ("PIB India", "https://pib.gov.in/RssMain.aspx?ModId=8&Lang=1&Regid=1"),

    # --- research papers / think tanks / academic ---
    ("arXiv Economics", "https://export.arxiv.org/rss/econ.GN"),
    ("BIS Research", "https://www.bis.org/rss/research.rss"),
    ("NBER Working Papers", "https://www.nber.org/rss/new.xml"),
    ("CEPR / VoxEU", "https://cepr.org/rss/vox-content"),
    ("Peterson Institute (PIIE)", "https://www.piie.com/rss/update.xml"),
    ("Foreign Policy", "https://foreignpolicy.com/feed/"),

    # --- sanctions & trade law trackers ---
    ("Baker McKenzie Sanctions", "https://sanctionsnews.bakermckenzie.com/feed/"),
    ("Global Trade & Sanctions Law", "https://www.globaltradeandsanctionslaw.com/feed/"),

    # --- user-requested additional sources ---
    # NOTE: these feed URLs use each site's standard RSS path but weren't
    # live-verified (no network access at build time). If a source below
    # shows 0 items after running, its RSS path may need updating.
    ("Devdiscourse", "https://www.devdiscourse.com/rss"),
    ("Amnesty International", "https://www.amnesty.org/en/feed/"),
    ("InsiderNJ", "https://www.insidernj.com/feed/"),
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


def collect(extra_feeds=None):
    feeds = DEFAULT_FEEDS + [("Custom", u) for u in (extra_feeds or [])]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)

    candidates = []
    for source, url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:MAX_ITEMS_PER_FEED]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                summary = entry.get("summary", entry.get("description", "")).strip()
                if not title or not link:
                    continue
                published = parse_date(entry.get("published", entry.get("updated", "")))
                if published < cutoff:
                    continue
                candidates.append({
                    "title": title, "url": link, "source": source,
                    "summary": summary, "published": published,
                })
        except Exception as exc:
            print(f"[RSS] {source}: {exc}")

    candidates = _enrich_with_full_text(candidates)
    candidates = dedupe_articles(candidates, threshold=DEDUPE_THRESHOLD)

    count = 0
    for art in candidates:
        category, score, level, country = classify(art["title"], art["summary"])
        if category not in ACTIVE_CATEGORIES:
            continue
        if save_article({
            "title": art["title"], "url": art["url"], "source": art["source"],
            "category": category, "summary": art["summary"][:2000],
            "published": art["published"].isoformat(), "score": score,
            "risk_level": level, "country": country,
        }):
            count += 1
    return count
