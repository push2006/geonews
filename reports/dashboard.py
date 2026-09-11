"""Read-only web dashboard: articles feed + events calendar + stats.

Reuses the exact same database functions as the email digest — no new
collection, scoring, or filtering logic. This is purely a browser view of
data that already exists in MongoDB.
"""
import html
from collections import defaultdict
from datetime import datetime

from database import recent_articles, upcoming_events, critical_since, category_counts, top_countries, total_article_count, latest_collection_time
from config import METADATA_CLEANUP_AFTER_DAYS, ENABLE_METADATA_CLEANUP, ENABLE_TELEGRAM_BACKUP

CATEGORY_LABELS = {
    "GEOPOLITICS": "🌍 Geopolitics", "CONFERENCE": "🗓️ Conferences & Meetings",
    "TRADE": "📦 Trade Activity", "SANCTIONS": "🚫 Sanctions & Circulars",
    "RISK": "⚠️ Risk Signals", "RESEARCH": "📄 Research Papers & Documents",
    "GENERAL": "📰 Other",
}
RISK_COLORS = {"CRITICAL": "#c53030", "HIGH": "#dd6b20", "MODERATE": "#d69e2e", "LOW": "#718096"}
CRED_COLORS = {"HIGH": "#2f855a", "MEDIUM": "#b7791f", "LOW": "#a0aec0"}

BASE_CSS = """
body{margin:0;background:#f4f6f8;font-family:-apple-system,Segoe UI,Arial,sans-serif;color:#1a202c}
.wrap{max-width:1100px;margin:0 auto;padding:24px}
header{background:linear-gradient(135deg,#1a365d,#2b6cb0);color:white;padding:28px 32px;border-radius:12px;margin-bottom:20px}
header h1{margin:0;font-size:24px}
header p{margin:8px 0 0;font-size:13px;opacity:0.85}
.stats{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:24px}
.stat{background:white;border-radius:10px;padding:16px 20px;flex:1;min-width:130px;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.stat .num{font-size:26px;font-weight:700;color:#1a365d}
.stat .lbl{font-size:12px;color:#718096;text-transform:uppercase;margin-top:2px}
.tabs{display:flex;gap:8px;margin-bottom:18px;border-bottom:2px solid #e2e8f0}
.tab{padding:10px 18px;font-size:14px;font-weight:600;color:#718096;text-decoration:none;border-bottom:3px solid transparent}
.tab.active{color:#1a365d;border-bottom-color:#2b6cb0}
.card{background:white;border-radius:10px;padding:20px 24px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.card h2{margin:0 0 14px;font-size:17px;color:#1a365d}
.item{margin-bottom:14px;padding:12px 14px;background:#f7fafc;border-radius:6px;border-left:4px solid #cbd5e0}
.item .meta{font-size:11px;color:#718096;text-transform:uppercase;font-weight:600;margin-bottom:4px}
.item a{color:#1a365d;font-weight:600;text-decoration:none;font-size:14px}
.item a:hover{text-decoration:underline}
.item .summary{font-size:13px;color:#4a5568;margin-top:4px}
.badge{display:inline-block;padding:1px 7px;border-radius:10px;font-size:10px;font-weight:700;color:white;margin-left:4px}
.barrow{display:flex;align-items:center;gap:10px;margin-bottom:8px;font-size:13px}
.barrow .name{width:190px;flex-shrink:0}
.barrow .bar{background:#e2e8f0;border-radius:4px;height:10px;flex:1;overflow:hidden}
.barrow .fill{background:#2b6cb0;height:100%}
.barrow .cnt{width:30px;text-align:right;color:#718096}
.event-date{display:inline-block;background:#2b6cb0;color:white;font-size:11px;font-weight:700;padding:2px 8px;border-radius:4px;margin-right:8px}
.searchbox{width:100%;padding:10px 14px;font-size:14px;border:1px solid #cbd5e0;border-radius:8px;margin-bottom:16px;box-sizing:border-box}
.footer-note{text-align:center;font-size:12px;color:#a0aec0;margin:20px 0}
"""


def _stat(num, label):
    return f'<div class="stat"><div class="num">{num}</div><div class="lbl">{html.escape(label)}</div></div>'


def _bar_section(title, rows, max_val):
    out = [f'<div class="card"><h2>{title}</h2>']
    for label, cnt, color in rows:
        pct = int((cnt / max_val) * 100) if max_val else 0
        out.append(f"""<div class="barrow"><div class="name">{html.escape(label)}</div>
            <div class="bar"><div class="fill" style="width:{pct}%;background:{color}"></div></div>
            <div class="cnt">{cnt}</div></div>""")
    if not rows:
        out.append("<p style='color:#718096;font-size:13px'>No data yet.</p>")
    out.append("</div>")
    return "".join(out)


def build_dashboard_html(limit=100000, category=None, trigger_key=None, sort_by="score"):
    total_in_db = total_article_count()
    last_collected = latest_collection_time()
    articles = recent_articles(limit=limit, sort_by=sort_by)
    if category:
        articles = [a for a in articles if (a.get("category") or "GENERAL") == category]
    events = upcoming_events(120)
    critical = critical_since(24)
    cats = category_counts(7)
    countries = top_countries(7)

    max_cat = max((c["cnt"] for c in cats), default=1)
    now = datetime.now().strftime("%d %b %Y, %H:%M")
    key_param = f"&key={trigger_key}" if trigger_key else ""

    # Risk-level breakdown (from the currently loaded article set)
    risk_counts = defaultdict(int)
    cred_counts = defaultdict(int)
    for a in articles:
        risk_counts[a.get("risk_level") or "LOW"] += 1
        cred_counts[a.get("credibility") or "MEDIUM"] += 1
    risk_rows = [(lvl, risk_counts.get(lvl, 0), RISK_COLORS[lvl])
                 for lvl in ("CRITICAL", "HIGH", "MODERATE", "LOW") if risk_counts.get(lvl)]
    cred_rows = [(lvl, cred_counts.get(lvl, 0), CRED_COLORS[lvl])
                 for lvl in ("HIGH", "MEDIUM", "LOW") if cred_counts.get(lvl)]
    max_risk = max((r[1] for r in risk_rows), default=1)
    max_cred = max((r[1] for r in cred_rows), default=1)

    body = [f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Geo Intel Dashboard</title><style>{BASE_CSS}</style></head><body><div class="wrap">
    <header><h1>🌍 Geo Intel Monitor — Dashboard</h1><p>Last refreshed {now} &middot; Last article collected: {html.escape((last_collected or "never")[:16].replace("T", " "))} UTC</p></header>
    <div class="stats">
        {_stat(f"{len(articles)} / {total_in_db}", "Articles shown / total in DB")}
        {_stat(len(critical), "Critical (24h)")}
        {_stat(len(events), "Upcoming events")}
        {_stat(len(cats), "Active categories")}
    </div>

    <input type="text" class="searchbox" id="searchBox" placeholder="🔎 Filter articles by title, source, or country..." onkeyup="filterArticles()">
    <p style="margin:-8px 0 16px;display:flex;justify-content:space-between;align-items:center">
        <a href="/export.csv{('?key=' + trigger_key) if trigger_key else ''}{('&category=' + category) if category else ''}" style="font-size:12px;color:#2b6cb0;font-weight:600">⬇️ Export all articles as CSV</a>
        <span style="font-size:12px;color:#718096">Sort by:
            <a href="?limit={limit}&sort_by=score{key_param}{('&category=' + category) if category else ''}" style="{'font-weight:700;color:#1a365d' if sort_by=='score' else 'color:#2b6cb0'}">Score</a> &middot;
            <a href="?limit={limit}&sort_by=newest{key_param}{('&category=' + category) if category else ''}" style="{'font-weight:700;color:#1a365d' if sort_by=='newest' else 'color:#2b6cb0'}">Newest</a> &middot;
            <a href="?limit={limit}&sort_by=title{key_param}{('&category=' + category) if category else ''}" style="{'font-weight:700;color:#1a365d' if sort_by=='title' else 'color:#2b6cb0'}">Title A-Z</a>
        </span>
    </p>
    """]

    body.append('<div class="tabs">')
    body.append(f'<a class="tab{" active" if not category else ""}" href="?limit={limit}{key_param}">All ({len(articles) if not category else total_in_db})</a>')
    for cat_key, cat_label in CATEGORY_LABELS.items():
        body.append(f'<a class="tab{" active" if category == cat_key else ""}" href="?limit={limit}&category={cat_key}{key_param}">{html.escape(cat_label)}</a>')
    body.append('</div>')

    body.append(_bar_section("📊 Volume by category (7 days)",
                              [(CATEGORY_LABELS.get(c["category"], c["category"] or "Other"), c["cnt"], "#2b6cb0")
                               for c in cats], max_cat))
    body.append(_bar_section("⚠️ Risk level breakdown", risk_rows, max_risk))
    body.append(_bar_section("✅ Source credibility breakdown", cred_rows, max_cred))

    if countries:
        body.append('<div class="card"><h2>🗺️ Most-mentioned countries (7 days)</h2><p style="font-size:13px;color:#4a5568">')
        body.append(" &nbsp;&middot;&nbsp; ".join(f"{html.escape(c['country'])} ({c['cnt']})" for c in countries))
        body.append("</p></div>")

    body.append('<div class="card"><h2>🗓️ Upcoming Events</h2>')
    if events:
        for e in events:
            body.append(f"""<div class="item">
                <span class="event-date">{html.escape(e.get('event_date',''))}</span>
                <a href="{html.escape(e.get('source_url','#'))}">{html.escape(e.get('name',''))}</a>
                <div class="summary">{html.escape(e.get('description','') or '')}</div>
            </div>""")
    else:
        body.append("<p style='color:#718096;font-size:13px'>No upcoming events on file.</p>")
    body.append("</div>")

    body.append('<div class="card"><h2>📰 Recent Articles</h2><div id="articleList">')
    grouped = defaultdict(list)
    for a in articles:
        grouped[a.get("category") or "GENERAL"].append(a)
    for category, items in grouped.items():
        label = CATEGORY_LABELS.get(category, category)
        body.append(f"<h3 style='font-size:14px;color:#2d3748;margin:16px 0 8px'>{html.escape(label)} ({len(items)})</h3>")
        for a in items:
            risk_color = RISK_COLORS.get(a.get("risk_level"), "#718096")
            cred = a.get("credibility", "MEDIUM")
            cred_color = CRED_COLORS.get(cred, "#a0aec0")
            corrob = a.get("corroboration", 1)
            search_key = html.escape(f"{a.get('title','')} {a.get('source','')} {a.get('country','')}".lower())
            body.append(f"""<div class="item" data-search="{search_key}" style="border-left-color:{risk_color}">
                <div class="meta">{html.escape(a.get('source','') or '')} &middot;
                    <span class="badge" style="background:{cred_color}">{html.escape(cred)}</span>
                    <span class="badge" style="background:{risk_color}">{html.escape(a.get('risk_level','') or '')}</span>
                    score {a.get('score',0)}/100
                    {f" &middot; {html.escape(a['country'])}" if a.get('country') else ""}
                    {f" &middot; {corrob} sources" if corrob > 1 else ""}
                    &middot; {html.escape((a.get('published') or '')[:10])}
                </div>
                <a href="{html.escape(a.get('url','#'))}" target="_blank">{html.escape(a.get('title',''))}</a>
                <div class="summary">{html.escape(a.get('summary') or '')}</div>
            </div>""")
    if not articles:
        body.append("<p style='color:#718096;font-size:13px'>No articles collected yet.</p>")
    body.append("</div></div>")

    body.append(f'<p class="footer-note">Showing {len(articles)} of {total_in_db} total articles in MongoDB'
                f'{" for category " + html.escape(category) if category else ""} \u2014 full record shown for each. '
                f'{"A private Telegram channel also keeps an off-site backup copy of every record." if ENABLE_TELEGRAM_BACKUP else "Enable ENABLE_TELEGRAM_BACKUP for an off-site backup copy."} '
                f'{"Metadata older than " + str(METADATA_CLEANUP_AFTER_DAYS) + " days is periodically cleaned up (backup copy stays on Telegram)." if ENABLE_METADATA_CLEANUP else "Metadata cleanup is currently off."}</p>')

    body.append("""<script>
    function filterArticles() {
        const q = document.getElementById('searchBox').value.toLowerCase();
        document.querySelectorAll('#articleList .item').forEach(el => {
            el.style.display = el.getAttribute('data-search').includes(q) ? '' : 'none';
        });
    }
    </script>""")

    body.append("</div></body></html>")
    return "".join(body)
