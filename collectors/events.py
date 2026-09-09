from database import save_event

EVENTS = [
    {
        "name": "G20 Finance Ministers and Central Bank Governors Meeting",
        "event_date": "2026-10-01",
        "category": "CONFERENCE",
        "country": "United States",
        "description": "Event record included as a verify-before-use placeholder. Confirm exact date/program on the official G20 host calendar.",
        "source_url": "https://www.g20.org/",
        "confidence": "VERIFY"
    }
]

def seed_events():
    return sum(1 for e in EVENTS if save_event(e))
