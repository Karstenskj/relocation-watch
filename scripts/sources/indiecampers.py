"""Indie Specials fra sidernes offentlige, serverleverede Next.js-data.

Ingen scriptudførelse eller interne API'er. Pris er en fra-pris, og datospændet
slutter ved seneste AFLEVERING. Det er ikke en sammenhængende afhentningsperiode.
Derfor kræves manuel bekræftelse af datoer og pris, også når spændet rammer vinduet.
"""
import json
import pathlib
import re
import sys
from urllib.parse import urlencode

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common import assess, build_deal, ends, money
from source_reader import SourceReader

SOURCE = "indiecampers-auto"
LABEL = "Indie Campers"
PAGE = "https://indiecampers.com/discover/en-gb/deals/europe"
LAST_OTHER = None
PARTIAL = None
LAST_CALLS = 0


def parse(page):
    # JSON-strengene i script-tags afkodes, men køres aldrig som JavaScript.
    stream = []
    for match in re.finditer(r'self\.__next_f\.push\((\[.*?\])\)</script>', page, re.S):
        chunk = json.loads(match[1])
        if len(chunk) > 1 and isinstance(chunk[1], str):
            stream.append(chunk[1])
    for line in "".join(stream).splitlines():
        _, sep, payload = line.partition(":")
        if sep and payload.startswith("[") and '"initialSearch"' in payload:
            node = json.loads(payload)
            if isinstance(node, list) and len(node) == 4 and isinstance(node[3], dict):
                props = node[3]
                if "initialSearch" in props and "serverQuery" in props:
                    return props
    raise ValueError("Indies tilbudsdata blev ikke fundet i HTML")


def fetch_deals(w, now):
    global LAST_OTHER, PARTIAL, LAST_CALLS
    LAST_OTHER, PARTIAL, LAST_CALLS = None, None, 0
    reader = SourceReader()
    first = parse(reader.read(PAGE))
    initial = first["initialSearch"]
    if initial.get("kind") != "loaded":
        raise ValueError("Indies tilbudsliste er ikke indlæst")
    pages = initial["pagination"]["total_pages"]
    batches = [first]
    partial = []
    for number in range(2, min(pages, 19) + 1):
        props = parse(reader.read(PAGE + "?" + urlencode({"page": number})))
        if props["serverQuery"].get("page") != number:
            raise ValueError("Indie gentog en side i stedet for næste side")
        if props["initialSearch"].get("kind") != "loaded":
            raise ValueError("Indies næste tilbudsside er ikke indlæst")
        batches.append(props)
    if pages > 19:
        partial.append("listen har flere end 19 sider")

    out, seen, total = [], set(), 0
    for props in batches:
        names, cards = props["cityNames"], props["vanCards"]
        for row in props["initialSearch"]["results"]["listings"]:
            frm, to = row["pick_up_location"], row["drop_off_location"]
            fname, tname = names.get(frm), names.get(to)
            if not fname or not tname:
                raise ValueError("Indie mangler bynavn til en rute")
            e = ends(w, fname, tname)
            for deal in row["deals"]:
                category = deal["van_category"]
                dates = deal["date_range"]
                pf, checkout = dates["earliest_checkin"], dates["latest_checkout"]
                key = (frm, to, category, pf, checkout)
                if key in seen:
                    continue
                seen.add(key)
                total += 1
                if not e["direction"]:
                    continue
                days = deal.get("max_nights")
                # Valuta står ikke i disse data. Gæt hverken valuta eller dagspris.
                amount = (deal.get("price_range") or {}).get("min")
                a = assess(w, pf, None, None, None, None, e["direction"], zone=e["zone"],
                           blocker="Konkrete datoer og pris skal bekræftes hos Indie Campers")
                a.update(state="ukendt", plan=None,
                         yourPlan="Bekræft afhentning, lejelængde og pris hos Indie Campers")
                card = cards.get(category) or {}
                out.append(build_deal(
                    w, now, a, id="indie-" + "-".join(key), source=SOURCE,
                    provider=LABEL, platform=LABEL,
                    url=PAGE + "?" + urlencode({"pick_up_location": frm, "drop_off_location": to}),
                    vehicle=card.get("categoryName") or "Camper", vehicleType="campervan",
                    canSleepIn=True, imageUrl=(card.get("image") or {}).get("url"),
                    route=f"{fname} → {tname}", pickupCity=fname, dropoffCity=tname,
                    pickupCountry=e["fromCountry"], dropoffCountry=e["toCountry"], days=None,
                    price=(f"Fra {money(amount, '').strip()} pr. nat, valuta ikke oplyst i data"
                           if amount is not None else "Pris ikke oplyst"),
                    pricePerDay=None, currency=None, minAge=None,
                    totalCost="Samlet pris og gebyrer skal tjekkes hos udlejeren",
                    youngDriverFee="ikke bekræftet",
                    availability={"from": pf, "to": None, "spaces": "Ukendt",
                                  "confidence": "liste, konkrete datoer skal bekræftes",
                                  "detail": f"Tidligste afhentning {pf}. Seneste aflevering {checkout}. "
                                            + (f"Højst {days} nætter. " if days else "")
                                            + "Kun udvalgte datoer er ledige. Seneste afhentning er ikke oplyst."},
                    notes="Automatisk aflæst fra den offentlige tilbudsside. Fra-prisen har ingen "
                          "valuta i data. Tilbuddet tæller først som relevant efter bekræftelse af datoer og pris.",
                ))
    LAST_OTHER = total - len(out)
    LAST_CALLS = reader.calls
    PARTIAL = partial or None
    return out


if __name__ == "__main__":
    from common import ROOT
    w = json.loads((ROOT / "data.json").read_text())["window"]
    for deal in fetch_deals(w, "test"):
        print(deal["fit"], "|", deal["route"], "|", deal["availability"]["from"], "|", deal["price"])
    print("andre", LAST_OTHER, "| HTTP-kald", LAST_CALLS, "| delvist", PARTIAL)
