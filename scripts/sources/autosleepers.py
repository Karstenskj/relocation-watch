"""Autosleepers Campervan Hire — deres relocation-liste er en almindelig HTML-tabel pr. afhentningsby.

Kolonner: Destination, Vehicle, Pickup From, Dropoff Before, $1 Days, Extra Days, Fuel, Ref #.
Står der «None at the moment» under en by, har de ingen tilbud derfra lige nu.
"""
import datetime, html as H, re, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common import fetch, assess

SOURCE = "autosleepers-auto"
LABEL = "Autosleepers"
PAGE = "https://www.autosleepers.com.au/relocations"
ORIGINS = ["Brisbane", "Gold Coast", "Sunshine Coast"]
DATE_FORMATS = ["%d/%m/%Y", "%d/%m/%y", "%d %b %Y", "%d %B %Y", "%Y-%m-%d", "%d-%m-%Y"]


def parse_date(s):
    s = (s or "").strip()
    for f in DATE_FORMATS:
        try:
            return datetime.datetime.strptime(s, f).date().isoformat()
        except ValueError:
            continue
    return None


def strip(x):
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", x))).strip()


def sections(html):
    """Klip siden op i (by, html-blok) ud fra overskrifterne over hver tabel."""
    heads = [(m.start(), strip(m.group(0))) for m in re.finditer(r"<h[2-4][^>]*>.*?</h[2-4]>", html, re.S)]
    for i, (pos, name) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(html)
        yield name, html[pos:end]


def rows(block):
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", block, re.S):
        cells = [strip(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
        cells = [c for c in cells if c != ""]
        if len(cells) >= 6 and cells[0].lower() not in ("destination",):
            yield cells


def fetch_deals(w, now):
    html = fetch(PAGE).decode("utf-8", "replace")
    out = []
    for name, block in sections(html):
        origin = next((o for o in ORIGINS if o.lower() == name.strip().lower()), None)
        if not origin or "none at the moment" in strip(block).lower():
            continue
        for c in rows(block):
            dest, vehicle, pfrom, dbefore, free_days = c[0], c[1], c[2], c[3], c[4]
            extra, fuel = (c[5] if len(c) > 5 else ""), (c[6] if len(c) > 6 else "")
            ref = c[7] if len(c) > 7 else ""
            if "sydney" not in dest.lower():
                continue
            pf, db = parse_date(pfrom), parse_date(dbefore)
            days = int(re.sub(r"\D", "", free_days) or 1)
            pt = (datetime.date.fromisoformat(db) - datetime.timedelta(days=1)).isoformat() if db else pf
            a = assess(w, pf, pt, days, 1.0, origin)
            fuel_txt = fuel if fuel and fuel.lower() not in ("no", "-", "none") else "ikke inkluderet"
            out.append({
                "id": f"autosleepers-{ref or (pf or '') + dest}".lower().replace(" ", "-"),
                "source": SOURCE, "provider": "Autosleepers Campervan Hire", "platform": "Autosleepers",
                "url": PAGE,
                "vehicle": vehicle, "vehicleType": "campervan", "sleeps": None, "canSleepIn": True,
                "imageUrl": None, "imageCredit": None,
                "route": f"{origin} → {dest}", "pickupCity": origin, "days": days,
                "price": f"1 AUD/dag i {days} dage" + (f" · ekstra dage: {extra}" if extra else ""),
                "pricePerDay": 1.0,
                "totalCost": f"{days} AUD" + (" + brændstof" if fuel_txt == "ikke inkluderet" else ""),
                "fuel": fuel_txt, "kmLimit": None, "minAge": None, "bond": None,
                "availability": {"state": a["state"], "from": pf, "to": pt, "spaces": "Ukendt",
                                 "detail": f"Afhentning fra {pfrom}, aflevering før {dbefore}, {days} dage til 1 AUD.",
                                 "checkedAt": now, "confidence": "direkte"},
                "yourPlan": a["yourPlan"], "fit": a["fit"], "fitReason": a["fitReason"],
                "notes": f"Automatisk aflæst fra Autosleepers{f' (reference {ref})' if ref else ''}. Bookes via knappen på deres side.",
            })
    return out


if __name__ == "__main__":
    w = {"pickupFrom": "2026-09-30", "pickupTo": "2026-10-03", "origin": "Brisbane", "maxPricePerDayAUD": 50}
    html = fetch(PAGE).decode("utf-8", "replace")
    for name, block in sections(html):
        if name.strip() in ORIGINS + ["Adelaide", "Cairns", "Melbourne", "Sydney"]:
            empty = "none at the moment" in strip(block).lower()
            print(f"  {name}: {'tom' if empty else str(len(list(rows(block)))) + ' rækker'}")
    print("deals:", fetch_deals(w, "2026-09-07T08:00:00+10:00"))
