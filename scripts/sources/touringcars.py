"""Touring Cars Flash Deals fra HTML-kortenes datafelter og dagspriser.

Oslo er en station i zonen, selv om dagens tilbud kun berører Tromsø og Finland.
Rejsespændet er ikke et løfte om afhentning på alle datoer. Ingen bookingkalender læses.
"""
from html.parser import HTMLParser
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common import assess, build_deal, ends, money
from source_reader import SourceReader

SOURCE = "touringcars-auto"
LABEL = "Touring Cars Flash Deals"
PAGE = "https://www.touringcars.com/en/flash-deals/"
LAST_OTHER = None
LAST_CALLS = 0
COUNTRIES = {"Norway": "NO", "Sweden": "SE", "Finland": "FI", "Germany": "DE",
             "Denmark": "DK", "Iceland": "IS", "Estonia": "EE", "United Kingdom": "GB"}


class Cards(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.current, self.depth = [], None, 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "div" and "flash-deal-card" in attrs.get("class", "").split():
            if self.current is not None:
                raise ValueError("Indlejrede tilbudskort hos Touring Cars")
            self.current = {"attrs": attrs, "text": [], "price": []}
            self.depth = 0
        if self.current is not None:
            if tag == "div":
                self.depth += 1
            if "deal-price" in attrs.get("class", "").split():
                self.current["in_price"] = True

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"].append(data)
            if self.current.get("in_price"):
                self.current["price"].append(data)

    def handle_endtag(self, tag):
        if self.current is not None:
            if tag == "small":
                self.current["in_price"] = False
            if tag == "div":
                self.depth -= 1
                if self.depth == 0:
                    self.rows.append(self.current)
                    self.current = None


def parse(page):
    cards = Cards()
    cards.feed(page)
    if cards.current is not None:
        raise ValueError("Ufuldstændigt tilbudskort hos Touring Cars")
    if not cards.rows and not re.search(r"no (?:flash )?deals|no offers", page, re.I):
        raise ValueError("Touring Cars viste hverken tilbudskort eller en tom liste")
    return cards.rows


def location(value):
    city, sep, country = value.rpartition(",")
    return (city.strip(), COUNTRIES.get(country.strip())) if sep else (value, None)


def fetch_deals(w, now):
    global LAST_OTHER, LAST_CALLS
    LAST_OTHER, LAST_CALLS = None, 0
    reader = SourceReader()
    rows = parse(reader.read(PAGE))
    out, seen = [], set()
    for row in rows:
        attrs = row["attrs"]
        key = attrs["data-deal-id"]
        if key in seen:
            continue
        seen.add(key)
        frm, fc = location(attrs["data-pickup-location"])
        to, tc = location(attrs["data-return-location"])
        e = ends(w, frm, to, fc, tc)
        if not e["direction"]:
            continue
        price_text = " ".join(row["price"])
        match = re.search(r"\d+(?:[.,]\d+)?", price_text)
        rate = float(match[0].replace(",", ".")) if match else None
        currency = attrs.get("data-currency")
        pf, pt = attrs.get("data-date-start"), attrs.get("data-date-end")
        a = assess(w, pf, pt, None, rate, currency, e["direction"], zone=e["zone"],
                   blocker="Rejsedatoer og lejelængde skal bekræftes hos Touring Cars")
        a.update(state="ukendt", plan=None,
                 yourPlan="Bekræft afhentning og lejelængde hos Touring Cars")
        out.append(build_deal(
            w, now, a, id=f"touringcars-{key}", source=SOURCE, provider="Touring Cars",
            platform=LABEL, url=attrs["data-deal-url"], vehicle="Camper", vehicleType="campervan",
            canSleepIn=True, route=f"{frm} → {to}", pickupCity=frm, dropoffCity=to,
            pickupCountry=fc, dropoffCountry=tc, days=None,
            price=f"{money(rate, currency)} pr. dag" if currency else "Pris ikke oplyst",
            pricePerDay=rate, currency=currency,
            totalCost="Dagsleje plus fast stationsgebyr med ukendt beløb, brændstof, bro og færge",
            minAge=None, youngDriverFee="ikke bekræftet",
            availability={"from": pf, "to": pt, "spaces": "Ukendt",
                          "confidence": "liste, konkrete datoer skal bekræftes",
                          "detail": f"Rejseperiode {pf} til {pt}. Lejelængde og mulig afhentning skal bekræftes."},
            notes="Automatisk aflæst fra Flash Deals. Alderskravet fastsættes af den enkelte udlejer. "
                  "Siden oplyser et ekstra stationsgebyr ved betaling, men intet beløb.",
        ))
    LAST_OTHER = len(seen) - len(out)
    LAST_CALLS = reader.calls
    return out


if __name__ == "__main__":
    from common import ROOT
    w = json.loads((ROOT / "data.json").read_text())["window"]
    for deal in fetch_deals(w, "test"):
        print(deal["fit"], "|", deal["route"], "|", deal["price"], "|", deal["fitReason"])
    print("andre", LAST_OTHER, "| HTTP-kald", LAST_CALLS)
