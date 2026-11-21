"""Hertz Freerider (Sverige og Norge), læst fra den åbne JSON-adresse, som siden selv bruger.

Der er ingen robots.txt (404) og ingen nøgle. Danmark findes ikke længere (country=DENMARK
giver en tom liste), men mange ture ender i Malmö, Lund og Helsingborg. Freerider kræver
svensk personnummer i profilen. Kørekort fra EØS-lande accepteres ifølge FAQ'en, men uden
personnummer kan turene ikke bookes. De vises derfor kun, så man kan se mønstret, og mærkes
altid "nej". Kilde: https://www.hertzfreerider.se/page-data/faq/sv-se/page-data.json

Med zonen på 300 km rører næsten alle svenske ture zonen. Vi gemmer derfor kun de MAX_KEEP ture,
hvis afhentning ligger tættest på vinduet, og skriver resten som et tal (HIDDEN).
"""
import sys, time, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common import fetch_json, assess, build_deal, ends, d

SOURCE = "freerider-auto"
LABEL = "Hertz Freerider"
API = "https://www.hertzfreerider.se/api/transport-routes/?country="
PAGE = "https://www.hertzfreerider.se/sv-se/"
BLOCKER = ("Kræver svensk personnummer i profilen. Dansk kørekort (EØS) accepteres ifølge "
           "FAQ'en, men uden personnummer kan turen ikke bookes.")
LAST_OTHER = None
HIDDEN = None
MAX_KEEP = 5
CC = {"SWEDEN": "SE", "NORWAY": "NO", "DENMARK": "DK", "FINLAND": "FI", "GERMANY": "DE"}


def cc(x):
    x = (x or "").upper()
    return x if len(x) == 2 else CC.get(x)


def gap_days(w, pf, pt):
    """Dage mellem turens afhentningsperiode og vinduet (0 hvis de overlapper)."""
    a, b = d(pf), d(pt) or d(pf)
    lo, hi = d(w["pickupFrom"]), d(w["pickupTo"])
    if not a:
        return 9999
    return 0 if a <= hi and b >= lo else min(abs((lo - b).days), abs((a - hi).days))


def fetch_deals(w, now):
    global LAST_OTHER, HIDDEN
    out, total = [], 0
    for i, c in enumerate(("SWEDEN", "NORWAY")):
        if i:
            time.sleep(1.5)
        for g in fetch_json(API + c):
            for r in g.get("routes") or []:
                total += 1
                p, q = r.get("pickupLocation") or {}, r.get("returnLocation") or {}
                e = ends(w, p.get("city"), q.get("city"), cc(p.get("country")), cc(q.get("country")))
                dirn, fc, tc = e["direction"], e["fromCountry"], e["toCountry"]
                if not dirn:
                    continue
                pf, pt = (r.get("availableAt") or "")[:10], (r.get("latestReturn") or "")[:10]
                a = assess(w, pf, pt, 1, 0, "SEK", dirn, blocker=BLOCKER, zone=e["zone"])
                out.append((gap_days(w, pf, pt), pf, str(r.get("id")), build_deal(
                    w, now, a,
                    id=f"freerider-{r.get('id')}", source=SOURCE, provider="Hertz", platform=LABEL,
                    url=PAGE, vehicle=(r.get("carModel") or "Bil").title(),
                    route=f"{p.get('city')} → {q.get('city')}", pickupCity=p.get("city"),
                    dropoffCity=q.get("city"), pickupCountry=fc, dropoffCountry=tc, days=1,
                    price="Gratis (0 kr.), første tank med", pricePerDay=0, currency="SEK",
                    totalCost="0 kr. + bro og afgifter, som føreren betaler",
                    fuel="første tank med", kmLimit=(f"{r['distance']:.0f} km" if r.get("distance") else None),
                    minAgeNote="ikke bekræftet", youngDriverFee="ikke bekræftet", bond="500 SEK reserveres på kortet",
                    availability={"from": pf, "to": pt, "spaces": "1 bil",
                                  "detail": f"Afhentning fra {r.get('availableAt')}, fremme senest {r.get('latestReturn')}."},
                    notes="Automatisk aflæst fra Hertz Freeriders åbne liste. Kun til at se mønstret.",
                )))
    LAST_OTHER = total - len(out)
    out.sort(key=lambda x: x[:3])
    HIDDEN = max(0, len(out) - MAX_KEEP)
    return [x[3] for x in out[:MAX_KEEP]]


if __name__ == "__main__":
    import json
    w = json.load(open(pathlib.Path(__file__).resolve().parents[2] / "data.json"))["window"]
    for x in fetch_deals(w, "test"):
        print(x["fit"], "|", x["route"], "|", x["vehicle"], "|", x["fitReason"])
    print("andre:", LAST_OTHER)
