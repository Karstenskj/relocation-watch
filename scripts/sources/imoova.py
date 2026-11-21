"""Imoova i Europa, læst fra hjemmesidens by-sider.

api.imoova.com er lukket for alle robotter i sin robots.txt, så API'et bruges ikke. By-siderne
www.imoova.com/deals/europe/<by> og /to-<by> er tilladte og server-renderede. Data ligger
indlejret i HTML'en som et JavaScript-objekt (seroval, $R[n]={__typename:"Relocation",...}).
Hver side viser højst de første 18 opslag (paginatoren siger, hvor mange der er i alt).

Sådan dækkes zonen med færrest kald:
1. Europa-siden. Har den alle opslag (i alt højst 18), er vi færdige med ét kald.
2. Ellers lande-siderne /<land> (afhentning i landet) og /to-<land> (aflevering i landet) for
   hvert land med steder i zonen: Danmark, Tyskland, Sverige, Norge, Holland og Polen (12 kald).
3. Er en lande-side afkortet (flere end 18 opslag), læses by-siderne for de største byer i zonen i
   det land, så længe der er kald tilbage (højst MAX_CALLS i alt). Kildekortet skriver så, at
   listen kan være afkortet.
"""
import re, sys, time, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common import fetch, assess, build_deal, ends, money, to_dkk, places

SOURCE = "imoova-auto"
LABEL = "Imoova"
BASE = "https://www.imoova.com/deals/europe/"
COUNTRY_SLUG = {"DK": "denmark", "DE": "germany", "SE": "sweden", "NO": "norway", "NL": "netherlands",
                "PL": "poland"}
# By-sider i zonen (fra Imoovas sitemap), kun brugt hvis en lande-side er afkortet. Største først.
CITY_SLUGS = {"DE": ["hamburg", "berlin", "bremen", "rostock", "kiel", "lubeck", "flensburg"],
              "SE": ["goteborg", "vastra-frolunda", "malmo"], "NO": ["oslo"], "DK": ["copenhagen"]}
MAX_CALLS = 20
PAUSE = 3
LAST_OTHER = None   # antal opslag i hele Europa, som ikke rører Danmark eller zonen
PARTIAL = None      # sider der ikke kunne læses, eller som var afkortet, i sidste kørsel

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
    seen, failed, short, calls = {}, [], [], 0

    def read(slug_):
        nonlocal calls
        if calls:
            time.sleep(PAUSE)
        calls += 1
        try:
            rows, total = parse(get(BASE + slug_ if slug_ else BASE.rstrip("/")))
        except Exception as e:
            failed.append(slug_ or "europe")
            return None, e
        for r in rows:
            if r.get("reference"):
                seen[r["reference"]] = r
        return (len(rows), total), None

    res, err = read("")
    europe_total = res[1] if res else None
    complete = res is not None and res[1] is not None and res[1] <= res[0]
    if not complete:
        for cc in [c for c in places()["zoneCountries"] if c in COUNTRY_SLUG]:
            for pre in ("", "to-"):
                res, e = read(pre + COUNTRY_SLUG[cc])
                err = e or err
                if res and res[1] is not None and res[1] > res[0]:
                    short.append((cc, pre))
        if len(failed) == calls:
            raise err   # ingen side kunne læses: kilden tæller som fejlet, og gamle opslag beholdes
        # Afkortede lande-sider: læs by-siderne i zonen, så længe der er kald tilbage. Mindre
        # steder i zonen kan stadig mangle, så siden står som afkortet på kildekortet.
        for cc, pre in short:
            for city in CITY_SLUGS.get(cc, []):
                if calls < MAX_CALLS:
                    read(pre + city)
        PARTIAL = (failed + [f"{pre}{COUNTRY_SLUG[cc]} afkortet" for cc, pre in short]) or None
    else:
        PARTIAL = None
    out = []
    for ref, r in seen.items():
        fc, tc = r.get("from") or {}, r.get("to") or {}
        e = ends(w, fc.get("name"), tc.get("name"), fc.get("state"), tc.get("state"))
        dirn = e["direction"]
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
        a = assess(w, pf, pt, units, rate, cur, dirn, min_age=min_age, count=r.get("count"), zone=e["zone"])
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
            notes=f"Automatisk aflæst fra Imoovas sider (tilbud {ref}).",
        ))
    LAST_OTHER = (europe_total - len(out)) if europe_total is not None else None
    return out


if __name__ == "__main__":
    import json
    w = json.load(open(pathlib.Path(__file__).resolve().parents[2] / "data.json"))["window"]
    for x in fetch_deals(w, "test"):
        print(x["fit"], "|", x["route"], "|", x["vehicle"], "|", x["price"], "|", x["fitReason"])
    print("andre opslag i Europa:", LAST_OTHER)
