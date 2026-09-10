import re
from dateutil import parser as dateparser
from datetime import datetime, timezone

_TAG_RE = re.compile(r"<[^>]+>")
_ENTITY_MAP = {"&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">",
               "&quot;": '"', "&#39;": "'", "&#8230;": "...", "&hellip;": "..."}


def strip_html(text):
    """Strips HTML tags out of RSS/API summary text. Many feeds (WordPress
    sites especially) put full HTML markup in their description field —
    without this, raw tags like <p> and <a href=...> show up as literal
    text in the email/dashboard instead of being invisible formatting."""
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    for entity, replacement in _ENTITY_MAP.items():
        text = text.replace(entity, replacement)
    return re.sub(r"\s+", " ", text).strip()


RULES = {
    "GEOPOLITICS": ["geopolit", "diplomatic", "foreign policy", "war", "conflict", "ceasefire", "military", "alliance", "border", "nato", "brics", "sco"],
    "TRADE": ["tariff", "trade war", "trade agreement", "export control", "import restriction", "export restriction", "customs", "supply chain", "critical mineral", "semiconductor", "trade dispute", "notification", "circular", "gazette", "trade order", "fta", "trade policy", "import ban", "export ban", "trade deal"],
    "SANCTIONS": ["sanction", "embargo", "asset freeze", "designated entity", "secondary sanctions", "export ban", "financial restriction", "circular", "notification", "sanctions list", "ofac", "denied party", "blacklist"],
    "RISK": ["risk", "escalation", "crisis", "instability", "shortage", "disruption", "shock", "volatility", "chokepoint"],
    "CONFERENCE": ["summit", "conference", "forum", "ministerial", "assembly", "meeting", "g20", "brics", "sco", "wto", "imf", "world bank"],
    "RESEARCH": ["working paper", "research paper", "policy brief", "preprint", "white paper", "arxiv", "ssrn", "nber", "peer-reviewed", "journal article"],
}
HIGH_IMPACT = ["breaking", "new sanctions", "sanctions package", "invasion", "ceasefire", "tariff", "export ban", "trade war", "nuclear", "military operation", "emergency"]
COUNTRIES = ["United States","China","India","Russia","Ukraine","Iran","Israel","Türkiye","Turkey","Japan","South Korea","North Korea","Germany","France","United Kingdom","Saudi Arabia","United Arab Emirates","Canada","Mexico","Taiwan","Pakistan","Australia","Indonesia","Brazil","South Africa","European Union"]

def classify(title, summary):
    text = f"{title} {summary}".lower()
    scores = {k: sum(1 for w in words if w in text) for k, words in RULES.items()}
    category = max(scores, key=scores.get) if max(scores.values()) else "GENERAL"
    score = min(100, sum(scores.values()) * 2 + sum(5 for w in HIGH_IMPACT if w in text))
    level = "CRITICAL" if score >= 30 else "HIGH" if score >= 20 else "MODERATE" if score >= 10 else "LOW"
    country = next((c for c in COUNTRIES if c.lower() in text), "")
    return category, score, level, country

def parse_date(value):
    try:
        dt = dateparser.parse(value) if value else datetime.now(timezone.utc)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)
