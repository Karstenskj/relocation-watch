"""DriveNow — deres relocation-liste hentes fra det REST-endpoint deres egen side kalder.

Selve hjemmesiden ligger bag Cloudflare og bygger listen med JavaScript, så den kan ikke læses
direkte. Men den underliggende adresse (/rest/relocation-deal/list/AU) svarer på et helt
almindeligt kald. Alle opslag kommer fra THL, altså Britz, Maui, Mighty og Apollo.
"""
import datetime, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common import fetch_json, assess, d as to_date

SOURCE = "drivenow-auto"
LABEL = "DriveNow"
API = "https://www.drivenow.com.au/rest/relocation-deal/list/AU"
PAGE = "https://www.drivenow.com.au/onewayrentals.jspc"
ORIGINS = ["brisbane", "gold coast", "sunshine coast"]
SUPPLIERS = {"thl-au": "THL (Britz, Maui, Mighty eller Apollo)"}


def vehicle(code):
    """THL-koder: førstetallet er antal sovepladser, 4WD betyder firehjulstrækker.

    Bekræftet mod Coseats, hvor de samme koder (2RE, 4RE, 6RE) står med 2, 4 og 6 personer.
    """
    code = (code or "").upper()
    berths = int(code[0]) if code[:1].isdigit() else None
    four_wd = "4WD" in code
    name = "Firehjulstrukket camper" if four_wd else "Campervan"
    if berths:
        name = f"{name}, {berths} sovepladser"
    return f"{name} (THL-kode {code})" if code else name, berths


def fetch_deals(w, now):
    data = fetch_json(API, referer=PAGE,
                      headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"})
    out = []
    for r in (data.get("deals") or []):
        origin, dest = (r.get("fromLocation") or ""), (r.get("toLocation") or "")
        if "sydney" not in dest.lower() or not any(o in origin.lower() for o in ORIGINS):
            continue
        pick_from = to_date(r.get("dateAvail"))
        arrive_by = to_date(r.get("arriveBy"))
        days = int(r.get("minDays") or 1)
        maxd = int(r.get("maxDays") or days)
        # Deres feed har af og til et forkert årstal i arriveBy. Er datoen før afhentning,
        # regner vi afleveringsfristen ud fra det maksimale antal dage i stedet.
        if arrive_by and pick_from and arrive_by < pick_from:
            arrive_by = pick_from + datetime.timedelta(days=maxd)
        pick_to = (arrive_by - datetime.timedelta(days=days)) if (arrive_by and pick_from) else pick_from
        if pick_to and pick_from and pick_to < pick_from:
            pick_to = pick_from
        rate = float(r.get("price") or 0)
        a = assess(w, pick_from.isoformat() if pick_from else None,
                   pick_to.isoformat() if pick_to else None, days, rate, origin)
        veh, berths = vehicle(r.get("vehicleCode"))
        fuel_amt = float(r.get("freeFuel") or 0)
        fuel = f"{fuel_amt:.0f} AUD brændstof inkluderet" if fuel_amt else "ikke inkluderet"
        extra = f" · kan forlænges til {maxd} dage" if maxd > days else ""
        out.append({
            "id": f"drivenow-{r['id'][:8].lower()}",
            "source": SOURCE,
            "provider": SUPPLIERS.get(r.get("supplier"), r.get("supplier") or "DriveNow"),
            "platform": "DriveNow",
            "url": PAGE + "#/relocations/AU",
            "vehicle": veh,
            "vehicleType": "campervan",
            "sleeps": berths,
            "canSleepIn": True,
            "imageUrl": None, "imageCredit": None,
            "route": f"{origin} → {dest}",
            "pickupCity": origin,
            "days": days,
            "price": f"{rate:.0f} AUD/dag i {days} dage{extra}",
            "pricePerDay": rate,
            "totalCost": f"{rate * days:.0f} AUD" + ("" if fuel_amt else " + brændstof"),
            "fuel": fuel,
            "kmLimit": f"{r['freeKms']} km" if r.get("freeKms") else None,
            "minAge": 21,
            "bond": "1000 AUD",
            "availability": {
                "state": a["state"],
                "from": pick_from.isoformat() if pick_from else None,
                "to": pick_to.isoformat() if pick_to else None,
                "spaces": f"{r['quantity']} køretøjer" if r.get("quantity") else "Ukendt",
                "detail": (f"Afhentning fra {r.get('dateAvail')}, skal være i {dest} senest "
                           f"{arrive_by.isoformat() if arrive_by else 'ukendt'}, {days} dage inkluderet."),
                "checkedAt": now, "confidence": "direkte",
            },
            "yourPlan": a["yourPlan"], "fit": a["fit"], "fitReason": a["fitReason"],
            "notes": ("Automatisk aflæst fra DriveNow. Listen fornys hver morgen for afrejse op til 30 dage frem. "
                      "1000 AUD sikkerhedsstillelse og 21 års aldersgrænse. DriveNow gør selv opmærksom på at "
                      "en flytning i sjældne tilfælde kan blive aflyst med kort varsel, hvis udlejeren får brug for bilen."),
        })
    return out


if __name__ == "__main__":
    w = {"pickupFrom": "2026-09-30", "pickupTo": "2026-10-03", "origin": "Brisbane", "maxPricePerDayAUD": 50}
    data = fetch_json(API, referer=PAGE, headers={"X-Requested-With": "XMLHttpRequest"})
    deals = data.get("deals") or []
    print(f"{len(deals)} australske tilbud i alt")
    import collections
    for k, v in sorted(collections.Counter((x["fromLocation"], x["toLocation"]) for x in deals).items()):
        print(f"   {k[0]} → {k[1]}: {v}")
    print("\npå din rute:")
    for x in fetch_deals(w, "2026-09-07T09:30:00+10:00"):
        print(" ", x["fit"], "|", x["route"], "|", x["vehicle"], "|", x["price"], "|", x["fuel"], "|", x["yourPlan"])
