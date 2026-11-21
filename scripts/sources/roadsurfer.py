"""Roadsurfer Rally, læst fra roadsurfer.com/de/camper-mieten/rallye/.

Siden er server-renderet WordPress, og alle ture står i HTML'en. Adressen bruges uden
query-streng, fordi robots.txt forbyder /*?. booking.roadsurfer.com er lukket for robotter,
så bookinglinkene vises kun som links og hentes aldrig.
Roadsurfer har ingen station i Danmark. Begge ender slås op i stedlisten (scripts/places.json),
så ture med en ende inden for zonen omkring Danmark kommer med.
"""
import datetime, html as H, re, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common import fetch, assess, build_deal, ends, money, to_dkk, da, d

SOURCE = "roadsurfer-auto"
LABEL = "Roadsurfer Rally"
PAGE = "https://roadsurfer.com/de/camper-mieten/rallye/"
LAST_OTHER = None

CARD = re.compile(r'<a\s+href="(https://booking\.roadsurfer\.com/rally/pick\?[^"]+)"[^>]*'
                  r'class="card-deal-link"[^>]*aria-label="([^"]+)"', re.S)


def text_after(page, start):
    t = page[start:start + 4000]
    t = H.unescape(re.sub(r"<[^>]+>", "|", t))
    return [p.strip() for p in t.split("|") if p.strip()]


def fetch_deals(w, now):
    global LAST_OTHER
    page = fetch(PAGE, timeout=60).decode("utf-8", "replace")
    seen, total = set(), set()
    out = []
    for m in CARD.finditer(page):
        href = H.unescape(m.group(1))
        if href in total:
            continue
        total.add(href)
        label = H.unescape(m.group(2))
        if "→" not in label:
            continue
        frm, to = [s.strip() for s in label.split("→", 1)]
        q = dict(re.findall(r"(\w+)=([^&]+)", href))
        pick, ret = q.get("pickup_date"), q.get("return_date")
        e = ends(w, frm, to)
        dirn, fc, tc = e["direction"], e["fromCountry"], e["toCountry"]
        if not dirn or href in seen:
            continue
        seen.add(href)
        parts = text_after(page, m.end())
        vehicle = next((p for p in parts[1:6] if p not in (label, "One-Way") and "→" not in p), "Camper")
        pm = re.search(r"(\d+(?:[.,]\d+)?)\s*€", " ".join(parts[:15]))
        price = float(pm.group(1).replace(",", ".")) if pm else None
        days = (datetime.date.fromisoformat(ret) - datetime.date.fromisoformat(pick)).days if pick and ret else 7
        per_day = round(price / days, 2) if price is not None and days else None
        a = assess(w, pick, pick, days, per_day, "EUR", dirn, zone=e["zone"])
        out.append(build_deal(
            w, now, a,
            id=f"roadsurfer-{q.get('station')}-{q.get('end_station')}-{pick}",
            source=SOURCE, provider="Roadsurfer", platform=LABEL, url=href,
            vehicle=vehicle, vehicleType="campervan", canSleepIn=True,
            route=f"{frm} → {to}", pickupCity=frm, dropoffCity=to, pickupCountry=fc, dropoffCountry=tc,
            days=days, price=f"{money(price, 'EUR')} for hele turen, op til {days} dage",
            pricePerDay=per_day, currency="EUR",
            totalCost=(f"{money(price, 'EUR')} (ca. {to_dkk(w, price, 'EUR'):.0f} kr.) + brændstof, vejafgift og færge"
                       if price is not None else None),
            fuel="ikke inkluderet",
            kmLimit="transferafstand + 25 % eller 200 km/dag, derefter 0,50 €/km",
            minAgeNote="18 år i de fleste europæiske lande ifølge Roadsurfer, ikke bekræftet for afhentningslandet",
            youngDriverFee="ikke bekræftet", bond="depositum før turen, beløb ikke bekræftet",
            availability={"from": pick, "to": pick, "spaces": "Ukendt",
                          "detail": f"Fast afhentning {da(d(pick)) if pick else 'ikke oplyst'}, aflevering senest {da(d(ret)) if ret else 'ikke oplyst'}.",
                          "confidence": "liste, ledighed ikke bekræftet"},
            notes=("Automatisk aflæst fra Roadsurfers rally-side. Om turen stadig er ledig, kan kun ses "
                   "på bookingsiden. Op til 4 personer, anden fører gratis."),
        ))
    LAST_OTHER = len(total) - len(out)
    return out


if __name__ == "__main__":
    import json
    w = json.load(open(pathlib.Path(__file__).resolve().parents[2] / "data.json"))["window"]
    for x in fetch_deals(w, "test"):
        print(x["fit"], "|", x["route"], "|", x["vehicle"], "|", x["price"], "|", x["fitReason"])
    print("andre:", LAST_OTHER)
