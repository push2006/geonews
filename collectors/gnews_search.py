"""Optional Google News keyword collector, used only when ENABLE_GNEWS=true.

Requires: pip install gnews

Google News search treats commas as plain text, not boolean OR. Each keyword
group in config.GNEWS_QUERY_GROUPS is joined with " OR " so the search
actually matches any term in the group, e.g.:

    ["sanctions", "trade order", "FTA"]  ->  "sanctions OR trade order OR FTA"
"""
from datetime import datetime, timezone
from config import (GNEWS_LANGUAGE, GNEWS_COUNTRY, GNEWS_PERIOD,
                     GNEWS_MAX_RESULTS, GNEWS_QUERY_GROUPS, DEDUPE_THRESHOLD,
                     ACTIVE_CATEGORIES)
from processing.classifier import classify, strip_html
from processing.dedupe import dedupe_articles
from database import save_article

try:
    from gnews import GNews
    HAS_GNEWS = True
except ImportError:
    HAS_GNEWS = False


def _build_queries():
    return [" OR ".join(group) for group in GNEWS_QUERY_GROUPS]


def collect():
    if not HAS_GNEWS:
        print("[GNEWS] Skipped: run 'pip install gnews' to enable this collector.")
        return 0

    client = GNews(language=GNEWS_LANGUAGE, country=GNEWS_COUNTRY,
                    max_results=GNEWS_MAX_RESULTS, period=GNEWS_PERIOD)

    seen_titles = set()
    candidates = []
    for query in _build_queries():
        try:
            results = client.get_news(query)
        except Exception as exc:
            print(f"[GNEWS] '{query}': {exc}")
            continue

        for art in results:
            title = (art.get("title") or "").strip()
            link = (art.get("url") or "").strip()
            if not title or not link or title in seen_titles:
                continue
            seen_titles.add(title)

            summary = strip_html(art.get("description") or "")
            source = (art.get("publisher") or {}).get("title", "Google News")
            category, score, level, country = classify(title, summary)
            if category not in ACTIVE_CATEGORIES:
                continue
            candidates.append({
                "title": title, "url": link, "source": source,
                "credibility": "MEDIUM",  # Google News aggregates many publishers; can't rate individually
                "category": category, "summary": summary[:600],
                "published": datetime.now(timezone.utc).isoformat(),
                "score": score, "risk_level": level, "country": country,
            })

    candidates = dedupe_articles(candidates, threshold=DEDUPE_THRESHOLD, score_key="score")

    count = 0
    for art in candidates:
        if save_article(art):
            count += 1
    return count
