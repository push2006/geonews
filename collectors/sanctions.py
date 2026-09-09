import csv, io, requests
from config import REQUEST_TIMEOUT

OFAC_SDN = "https://www.treasury.gov/ofac/downloads/sdn.csv"

def update_ofac_names():
    try:
        r = requests.get(OFAC_SDN, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return [row[0].strip() for row in csv.reader(io.StringIO(r.text)) if row and row[0].strip()]
    except Exception as exc:
        print("[SANCTIONS] OFAC download failed:", exc)
        return []

def screen_text(text, names):
    t = text.lower()
    return [n for n in names if n.lower() in t][:20]
