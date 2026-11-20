"""Hertz Freerider (Sverige og Norge), læst fra den åbne JSON-adresse, som siden selv bruger.

Der er ingen robots.txt (404) og ingen nøgle. Danmark findes ikke længere (country=DENMARK
giver en tom liste), men mange ture ender i Malmö, Lund og Helsingborg. Freerider kræver
svensk personnummer i profilen. Kørekort fra EØS-lande accepteres ifølge FAQ'en, men uden
personnummer kan turene ikke bookes. De vises derfor kun, så man kan se mønstret, og mærkes
altid "nej". Kilde: https://www.hertzfreerider.se/page-data/faq/sv-se/page-data.json
"""
import sys, time, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common import fetch_json, assess, build_deal, direction

SOURCE = "freerider-auto"
LABEL = "Hertz Freerider"
API = "https://www.hertzfreerider.se/api/transport-routes/?country="
PAGE = "https://www.hertzfreerider.se/sv-se/"
BLOCKER = ("Kræver svensk personnummer i profilen. Dansk kørekort (EØS) accepteres ifølge "
           "FAQ'en, men uden personnummer kan turen ikke bookes.")
LAST_OTHER = None


def fetch_deals(w, now):
    global LAST_OTHER
    out, total = [], 0
    for i, c in enumerate(("SWEDEN", "NORWAY")):
        if i:
            time.sleep(1.5)
        for g in fetch_json(API + c):
            for r in g.get("routes") or []:
                total += 1
                p, q = r.get("pickupLocation") or {}, r.get("returnLocation") or {}
                fc, tc = (p.get("country") or "").upper(), (q.get("country") or "").upper()
                dirn = direction(w, fc, tc, p.get("city"), q.get("city"))
                if not dirn:
                    continue
                pf, pt = (r.get("availableAt") or "")[:10], (r.get("latestReturn") or "")[:10]
                a = assess(w, pf, pt, 1, 0, "SEK", dirn, blocker=BLOCKER)
                out.append(build_deal(
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
                ))
    LAST_OTHER = total - len(out)
    return out


if __name__ == "__main__":
    import json
    w = json.load(open(pathlib.Path(__file__).resolve().parents[2] / "data.json"))["window"]
    for x in fetch_deals(w, "test"):
        print(x["fit"], "|", x["route"], "|", x["vehicle"], "|", x["fitReason"])
    print("andre:", LAST_OTHER)
