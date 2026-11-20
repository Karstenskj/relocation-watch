"""Imoova i Europa, læst fra hjemmesidens by-sider.

api.imoova.com er lukket for alle robotter i sin robots.txt, så API'et bruges ikke. By-siderne
www.imoova.com/deals/europe/<by> og /to-<by> er tilladte og server-renderede. Data ligger
indlejret i HTML'en som et JavaScript-objekt (seroval, $R[n]={__typename:"Relocation",...}).
Hver side viser højst de første 18 opslag. By-siderne for Danmark og nærbyerne har langt færre.
"""
import re, sys, time, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common import fetch, assess, build_deal, direction, money, to_dkk

SOURCE = "imoova-auto"
LABEL = "Imoova"
BASE = "https://www.imoova.com/deals/europe/"
SLUGS = ["denmark", "copenhagen", "to-copenhagen", "malmo", "to-malmo", "hamburg", "to-hamburg",
         "flensburg", "to-flensburg", "kiel", "to-kiel", "lubeck", "to-lubeck", "rostock", "to-rostock"]
PAUSE = 3
LAST_OTHER = None
PARTIAL = None    # by-sider der ikke kunne læses i sidste kørsel   # antal opslag i hele Europa, som ikke rører Danmark eller en nærby

FIELD = re.compile(r'(\w+):("(?:[^"\\]|\\.)*"|\$R\[\d+\]|[^,{}\[\]]*)')
VTYPE = {"MOTOR_HOME": "campervan", "CAMPER_VAN": "campervan", "CAR": "sedan", "SUV": "suv",
         "VAN": "van", "MINIBUS": "van", "TRUCK": "van"}


def fields(s):
    out = {}
    for k, v in FIELD.findall(s):
        if v.startswith('"'):
            out[k] = v[1:-1]
        elif v == "!0":
            out[k] = True
        elif v == "!1":
            out[k] = False
        elif v == "null":
            out[k] = None
        else:
            try:
                out[k] = float(v) if "." in v else int(v)
            except ValueError:
                out[k] = v
    return out


def objects(html, typename):
    """Alle $R[n]={__typename:"X",...} uden indlejrede objekter, så backreferencer kan slås op."""
    pat = re.compile(r'\$R\[(\d+)\]=\{__typename:"' + typename + r'",([^{}]*)\}')
    return {m.group(1): fields(m.group(2)) for m in pat.finditer(html)}


def parse(html):
    cities, vehicles = objects(html, "City"), objects(html, "Vehicle")
    total = re.search(r'__typename:"PaginatorInfo",total:(\d+)', html)
    rows = []
    for chunk in html.split('__typename:"Relocation",')[1:]:
        head = chunk.split("rental_units:")[0]
        r = fields(head)
        rest = chunk[len(head):]
        for k in ("latest_departure_date", "earliest_departure_date", "booking_fee_amount",
                  "distance_allowed", "measurement"):
            m = re.search(k + r':("[^"]*"|[^,}]*)', rest)
            if m:
                r.update(fields(f"{k}:{m.group(1)}"))
        for key, table, name in (("deliveryCity", cities, "to"), ("departureCity", cities, "from"),
                                 ("vehicle", vehicles, "vehicle")):
            m = re.search(key + r':\$R\[(\d+)\]', rest)
            r[name] = table.get(m.group(1)) if m else None
        img = re.search(r'type:"SMALL",url:"([^"]+)"', rest.split('__typename:"Vehicle"')[0])
        r["image"] = img.group(1) if img else None
        rows.append(r)
    return rows, int(total.group(1)) if total else None


def get(url):
    """Én side, med ét nyt forsøg efter 5 sekunder, hvis forbindelsen svigter."""
    try:
        return fetch(url, timeout=45).decode("utf-8", "replace")
    except Exception:
        time.sleep(5)
        return fetch(url, timeout=45).decode("utf-8", "replace")


def fetch_deals(w, now):
    global LAST_OTHER
    global PARTIAL
    europe_total, err = None, None
    try:
        _, europe_total = parse(get(BASE.rstrip("/")))
    except Exception as e:
        err = e
    europe_failed = err is not None
    seen, out, failed = {}, [], []
    for s in SLUGS:
        time.sleep(PAUSE)
        try:
            rows, _ = parse(get(BASE + s))
        except Exception as e:
            failed.append(s)
            err = e
            continue
        for r in rows:
            if r.get("reference"):
                seen[r["reference"]] = r
    if len(failed) == len(SLUGS):
        raise err   # ingen by-side kunne læses: kilden tæller som fejlet, og gamle opslag beholdes
    PARTIAL = (failed + (["europe"] if europe_failed else [])) or None
    for ref, r in seen.items():
        fc, tc = r.get("from") or {}, r.get("to") or {}
        dirn = direction(w, fc.get("state"), tc.get("state"), fc.get("name"), tc.get("name"))
        if not dirn:
            continue
        v = r.get("vehicle") or {}
        cur = r.get("currency") or "EUR"
        rate = (r.get("hire_unit_rate") or 0) / 100
        units = int(r.get("hire_units_allowed") or 1)
        fee = (r.get("booking_fee_amount") or 0) / 100
        unit = "nat" if r.get("hire_unit_type") == "NIGHT" else "dag"
        pf = r.get("earliest_departure_date") or r.get("available_from_date")
        pt = r.get("latest_departure_date") or r.get("available_to_date")
        min_age = v.get("minimum_age")
        a = assess(w, pf, pt, units, rate, cur, dirn, min_age=min_age, count=r.get("count"))
        young = None
        if v.get("age_surcharge_amount") and v.get("minimum_no_surcharge_age"):
            young = (f"{money(v['age_surcharge_amount'] / 100, cur)} for førere under "
                     f"{v['minimum_no_surcharge_age']} år (Imoovas felt, enhed ikke oplyst)")
        extra = r.get("extra_hire_units_allowed")
        extra_txt = (f", op til {extra} ekstra à {money((r.get('extra_hire_unit_rate') or 0) / 100, cur)}"
                     if extra else "")
        total = rate * units + fee
        out.append(build_deal(
            w, now, a,
            id=f"imoova-{ref}", source=SOURCE, provider=LABEL, platform="Imoova",
            url=f"https://www.imoova.com/relocations/europe/{fc.get('slug')}-to-{tc.get('slug')}/{ref}",
            vehicle=v.get("name") or "Køretøj", vehicleType=VTYPE.get(v.get("type"), "sedan"),
            sleeps=v.get("sleeps"), canSleepIn=bool(v.get("sleeps")), imageUrl=r.get("image"),
            route=f"{fc.get('name')} → {tc.get('name')}",
            pickupCity=fc.get("name"), dropoffCity=tc.get("name"),
            pickupCountry=fc.get("state"), dropoffCountry=tc.get("state"),
            days=units, price=f"{money(rate, cur)} pr. {unit} i {units} {unit}e{extra_txt} · bookinggebyr {money(fee, cur)}",
            pricePerDay=rate, currency=cur,
            totalCost=f"{money(total, cur)} (ca. {to_dkk(w, total, cur) or 0:.0f} kr.) + brændstof, bro og færge",
            fuel="ikke inkluderet" if not r.get("has_free_tank") else "første tank med",
            kmLimit=(f"{r['distance_allowed']} km" if r.get("distance_allowed") else None),
            minAge=min_age, youngDriverFee=young,
            availability={"from": pf, "to": pt, "spaces": f"{r.get('count')} køretøj(er)",
                          "detail": f"Afhentning mulig {pf} til {pt}, {units} {unit}e."},
            notes=f"Automatisk aflæst fra Imoovas by-sider (tilbud {ref}).",
        ))
    LAST_OTHER = (europe_total - len(out)) if europe_total is not None else None
    return out


if __name__ == "__main__":
    import json
    w = json.load(open(pathlib.Path(__file__).resolve().parents[2] / "data.json"))["window"]
    for x in fetch_deals(w, "test"):
        print(x["fit"], "|", x["route"], "|", x["vehicle"], "|", x["price"], "|", x["fitReason"])
    print("andre opslag i Europa:", LAST_OTHER)
