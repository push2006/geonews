"""Optional full-article-text extraction, used only when ENABLE_FULL_TEXT=true.

Kept isolated so the rest of the app works fine even if `trafilatura` is not
installed, and so a scraping failure on one site never breaks a collection run.
"""
try:
    import trafilatura
    HAS_TRAFILATURA = True
except ImportError:
    HAS_TRAFILATURA = False


def extract_full_text(url, max_chars=700):
    if not HAS_TRAFILATURA:
        return ""
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return ""
        text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
        if not text:
            return ""
        text = text.strip()
        return text[:max_chars] + "..." if len(text) > max_chars else text
    except Exception:
        return ""
