"""Simba Car Hire — deres relocation-liste hentes fra et åbent JSON-endpoint.

Siden er en React-app, men den funktion den kalder svarer uden nøgle, så vi kalder den direkte.
Simba kører almindelige biler (ikke campere), typisk 20-50 AUD/dag med 1 AUD envejsgebyr.
"""
import datetime, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common import fetch_json, assess

SOURCE = "simba-auto"
LABEL = "Simba Car Hire"
API = "https://lrlwqpqeamafcsoegdvh.supabase.co/functions/v1/rcm-fetch-relocations"
PAGE = "https://www.simbacarhire.com.au/relocations"
ORIGINS = ["brisbane", "gold coast", "sunshine coast"]


def au_date(s):
    """'27/09/2026' -> '2026-09-27'."""
    try:
        return datetime.datetime.strptime(s, "%d/%m/%Y").date().isoformat()
    except Exception:
        return None


def city(name):
    return (name or "").replace(" Airport", "").strip()


def vehicle_type(name):
    n = (name or "").lower()
    if any(k in n for k in ("suv", "outlander", "jolion", "hs", "rav", "cx-")):
        return "suv"
    if "van" in n or "carnival" in n:
        return "van"
    if "ute" in n:
        return "suv"
    return "sedan"


def fetch_deals(w, now):
    data = fetch_json(API, referer="https://www.simbacarhire.com.au/",
                      headers={"Origin": "https://www.simbacarhire.com.au"})
    rows = data if isinstance(data, list) else (data.get("relocations") or data.get("data") or [])
    out = []
    for r in rows:
        origin, dest = city(r.get("pickup_location_name")), city(r.get("dropoff_location_name"))
        if dest.lower() != "sydney" or not any(o in origin.lower() for o in ORIGINS):
            continue
        rate = float(r.get("daily_rate") or 0)
        days = int(r.get("max_days") or 1)
        fee = float(r.get("one_way_fee") or 0)
        pf, pt = au_date(r.get("pickup_start_date")), au_date(r.get("pickup_end_date"))
        a = assess(w, pf, pt, days, rate, origin)
        vname = r.get("vehicle_category_name") or "Bil"
        out.append({
            "id": f"simba-{r['relocation_special_id']}",
            "source": SOURCE,
            "provider": "Simba Car Hire",
            "platform": "Simba Car Hire",
            "url": PAGE,
            "vehicle": vname,
            "vehicleType": vehicle_type(vname),
            "sleeps": None,
            "canSleepIn": False,
            "imageUrl": None,
            "imageCredit": None,
            "route": f"{r.get('pickup_location_name')} → {r.get('dropoff_location_name')}",
            "pickupCity": origin,
            "days": days,
            "price": f"{rate:.0f} AUD/dag i op til {days} dage · {fee:.0f} AUD envejsgebyr",
            "pricePerDay": rate,
            "totalCost": f"{rate * days + fee:.0f} AUD hvis du bruger alle {days} dage, + brændstof",
            "fuel": "ikke inkluderet",
            "kmLimit": None,
            "minAge": None,
            "bond": None,
            "availability": {
                "state": a["state"], "from": pf, "to": pt, "spaces": "Ukendt",
                "detail": (f"Afhentning mulig {pf} til {pt}, aflevering senest "
                           f"{au_date(r.get('last_dropoff_date')) or 'ukendt'}, op til {days} dage."),
                "checkedAt": now, "confidence": "direkte",
            },
            "yourPlan": a["yourPlan"], "fit": a["fit"], "fitReason": a["fitReason"],
            "notes": (f"Automatisk aflæst fra Simba Car Hire (tilbud {r['relocation_special_id']}). "
                      "Almindelig personbil, ikke en camper. Bookes på deres relocation-side."),
        })
    return out


if __name__ == "__main__":
    w = {"pickupFrom": "2026-09-30", "pickupTo": "2026-10-03", "origin": "Brisbane", "maxPricePerDayAUD": 50}
    data = fetch_json(API, referer="https://www.simbacarhire.com.au/")
    rows = data if isinstance(data, list) else (data.get("relocations") or [])
    print(len(rows), "listings i alt:", sorted({(r["pickup_location_name"], r["dropoff_location_name"]) for r in rows}))
    for d in fetch_deals(w, "2026-09-07T08:00:00+10:00"):
        print(d["fit"], "|", d["route"], "|", d["vehicle"], "|", d["price"], "|", d["yourPlan"])
