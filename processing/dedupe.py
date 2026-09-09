"""Fuzzy near-duplicate filtering.

The same story often runs on BBC, Reuters, Guardian, Al Jazeera etc. with
slightly different headlines within the same collection cycle. Exact-title
matching (used at the database layer) misses these. This does a pairwise
title-similarity pass over one batch before it's saved, keeping the
highest-scoring version of each near-duplicate cluster when scores are
already computed, otherwise the first one seen.
"""
from difflib import SequenceMatcher


def _similar(a, b, threshold):
    return SequenceMatcher(None, a, b).ratio() >= threshold


def dedupe_articles(articles, threshold=0.85, score_key=None):
    """articles: list of dicts with a 'title' key.
    score_key: optional key to prefer the higher-scoring duplicate
               (e.g. 'score'), otherwise first-seen wins.
    """
    kept = []
    for art in articles:
        title = (art.get("title") or "").lower().strip()
        match_idx = None
        for i, k in enumerate(kept):
            if _similar(title, (k.get("title") or "").lower().strip(), threshold):
                match_idx = i
                break
        if match_idx is None:
            kept.append(art)
        elif score_key and art.get(score_key, 0) > kept[match_idx].get(score_key, 0):
            kept[match_idx] = art
    return kept
