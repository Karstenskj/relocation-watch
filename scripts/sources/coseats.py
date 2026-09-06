"""Coseats — læses via det JSON-API deres app (app.coseats.com) selv bruger.

Alle australske relocations kommer i én liste (typisk 50-100), som vi filtrerer på ruten.
Udlejeren bag de fleste opslag er THL (Britz, Maui, Mighty).
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common import fetch_json, assess, save_image

SOURCE = "coseats-auto"
LABEL = "Coseats"
API = "https://coseats-au.herokuapp.com/trips/search/findRelocations?size=50&page={page}"
PAGE_URL = "https://app.coseats.com/campervan-relocation"
ORIGINS = ["brisbane", "gold coast", "sunshine coast"]
CAMPER = {"2RE": "2-berth campervan", "4RE": "4-berth motorhome", "6RE": "6-berth motorhome",
          "2B": "2-berth campervan", "4B": "4-berth motorhome", "6B": "6-berth motorhome",
          "HT": "Hi-top campervan", "SV": "Sleepervan"}


def trips():
    page = 0
    while True:
        d = fetch_json(API.format(page=page), referer="https://app.coseats.com/",
                       headers={"Origin": "https://app.coseats.com"})
        for t in d.get("_embedded", {}).get("trips", []):
            yield t
        pg = d.get("page", {})
        if pg.get("number", 0) + 1 >= pg.get("totalPages", 1):
            break
        page += 1


def build(t, w, now):
    origin = t["fromLocation"]
    price = float(t.get("price") or 0)
    fee = float(t.get("bookingFee") or 0)
    days = t.get("minDays") or t.get("maxDays") or 1
    maxd = t.get("maxDays") or days
    company = (t.get("company") or (t.get("_embedded", {}).get("user") or {}).get("name") or "").strip()
    provider = "THL (Britz / Maui / Mighty)" if company.upper() == "THL" else (company or "Coseats-udlejer")
    a = assess(w, t.get("date"), t.get("repeatEndDate") or t.get("date"), days, price, origin)
    code = (t.get("camper") or "").upper()
    veh = CAMPER.get(code, f"Campervan ({code})" if code else "Campervan")
    pax = t.get("passengers")
    fuel = f"{int(t['freePetrol'])} AUD brændstof inkluderet" if t.get("freePetrol") else "ikke inkluderet"
    extra = f" · op til {maxd} dage, ekstra dage à {float(t.get('extraDayFee') or 0):.0f} AUD" if maxd > days else ""
    total = price * days + fee
    return {
        "id": f"coseats-{t['id']}",
        "source": SOURCE,
        "provider": provider,
        "platform": "Coseats",
        "url": PAGE_URL,
        "vehicle": " · ".join(x for x in [veh, f"sover {pax}" if pax else None] if x),
        "vehicleType": "campervan",
        "sleeps": pax,
        "canSleepIn": True,
        "imageUrl": f"img/coseats-{code.lower() or t['id']}.jpg" if t.get("imageUrl") else None,
        "imageCredit": "Foto: Coseats" if t.get("imageUrl") else None,
        "_imageSrc": t.get("imageUrl"),
        "route": f"{origin} → {t['toLocation']}",
        "pickupCity": origin,
        "days": days,
        "price": f"{price:.0f} AUD/dag · {fee:.0f} AUD bookinggebyr{extra}",
        "pricePerDay": price,
        "totalCost": f"{total:.0f} AUD" + (" + brændstof" if not t.get("freePetrol") else ""),
        "fuel": fuel,
        "kmLimit": f"{int(t['kmAllowance'])} km" if t.get("kmAllowance") else None,
        "minAge": 21,
        "bond": f"{int(t['bond'])} AUD" if t.get("bond") else None,
        "availability": {
            "state": a["state"],
            "from": str(t.get("date") or "")[:10] or None,
            "to": str(t.get("repeatEndDate") or t.get("date") or "")[:10] or None,
            "spaces": "Ukendt",
            "detail": f"Afhentning mulig {str(t.get('date') or '')[:10]} til {str(t.get('repeatEndDate') or t.get('date') or '')[:10]} med {days} dage til turen.",
            "checkedAt": now,
            "confidence": "direkte",
        },
        "yourPlan": a["yourPlan"],
        "fit": a["fit"],
        "fitReason": a["fitReason"],
        "notes": (f"Automatisk aflæst fra Coseats (opslag {t['id']}). Aldersgrænse 21 år. "
                  + (f"Depositum {int(t['bond'])} AUD. " if t.get("bond") else "")
                  + "Bookes i Coseats-appen, ingen direkte link til det enkelte opslag."),
    }


def fetch_deals(w, now):
    out = []
    for t in trips():
        if t.get("sold") or t.get("expired"):
            continue
        if (t.get("type") or "Relocation") != "Relocation":
            continue
        frm = (t.get("fromLocation") or "").lower()
        to = (t.get("toLocation") or "").lower()
        if "sydney" not in to or not any(o in frm for o in ORIGINS):
            continue
        deal = build(t, w, now)
        src = deal.pop("_imageSrc")
        if src and not save_image(src, deal["imageUrl"], referer="https://app.coseats.com/"):
            deal["imageUrl"] = deal["imageCredit"] = None
        out.append(deal)
    return out


if __name__ == "__main__":
    import datetime, collections
    w = {"pickupFrom": "2026-09-30", "pickupTo": "2026-10-03", "origin": "Brisbane", "maxPricePerDayAUD": 50}
    n = collections.Counter()
    for t in trips():
        n[(t["fromLocation"], t["toLocation"])] += 1
    print(sorted(n.items()))
    for d in fetch_deals(w, datetime.datetime.now().isoformat()):
        print(d)
