#!/usr/bin/env python3
"""Henter Imoovas Christchurch-relocations og opdaterer data.json.

Imoova serverer sine data som en React-payload direkte i HTML'en. Den er ikke
gyldig JSON (den bruger $R[n]-referencer og !0/!1 for booleans), så felterne
trækkes ud med regex. Objekterne kommer i rækkefølgen: Relocation, derefter det
Vehicle den hører til — det er verificeret mod de faktiske opslag.

Kører uden API-nøgler, så GitHub Actions kan eksekvere den gratis fire gange dagligt.
"""
import json, re, sys, urllib.request, datetime, pathlib

URL = "https://www.imoova.com/en/relocations?region=NZ&departure_city=christchurch"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
ROOT = pathlib.Path(__file__).resolve().parent.parent
NZ = datetime.timezone(datetime.timedelta(hours=12))

VEHICLE_TYPE_MAP = {"CAR": "sedan", "SUV": "sedan", "CAMPER_VAN": "campervan",
                    "MOTOR_HOME": "campervan", "MINI_VAN": "campervan"}


def fetch(url, referer=None):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Language": "en-NZ,en;q=0.9",
        **({"Referer": referer} if referer else {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def field(blob, key, quoted=True):
    # Lookbehind er nødvendigt: `__typename:` slutter på `name:`, og
    # `hire_unit_type:` slutter på `type:`. Uden den læses de forkerte felter.
    b = r'(?<![A-Za-z0-9_])'
    m = re.search(rf'{b}{key}:"([^"]*)"' if quoted else rf'{b}{key}:(-?\d+|null|!0|!1)', blob)
    if not m:
        return None
    v = m.group(1)
    if v in ("null",):
        return None
    if v == "!0":
        return True
    if v == "!1":
        return False
    return v if quoted else int(v)


def card_text(html, ref):
    """Den synlige tekst på opslagets kort — det Karsten selv ser på siden.

    Kortet er sandheden. JS-payloadens inclusions-array kan ikke entydigt
    knyttes til det rigtige opslag, så inklusioner læses herfra i stedet.
    """
    i = html.find(f"/christchurch-to-auckland/{ref}\"")
    if i < 0:
        return ""
    seg = html[i:i + 9000]
    nxt = re.search(r'/relocations/new-zealand/[a-z-]+/RLC\d+"', seg[200:])
    if nxt:
        seg = seg[:200 + nxt.start()]
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", seg)).strip()


def parse(html):
    """Returnér én dict pr. relocation, parret med det Vehicle der følger den.

    Rækkefølgen i payloaden er verificeret: Relocation-objektet kommer først,
    og det tilhørende Vehicle følger umiddelbart efter.
    """
    vehicles = [(m.start(), m.group(0)) for m in
                re.finditer(r'\{__typename:"Vehicle",id:"\d+".{0,600}', html, re.S)]
    out = []
    for m in re.finditer(r'\{__typename:"Relocation",id:"\d+",reference:"RLC\d+".{0,2200}',
                         html, re.S):
        blob, pos = m.group(0), m.start()
        veh = next((v for p, v in vehicles if p > pos), "")
        ref = field(blob, "reference")
        card = card_text(html, ref)
        # Alt efter aldersgrænsen ("18 +") er inklusionsbadges.
        badges = (re.split(r"\d+\s*\+", card, maxsplit=1) + [""])[1].strip()
        out.append({
            "reference": ref,
            "name": field(blob, "name"),
            "status": field(blob, "status"),
            "count": field(blob, "count", False),
            "from": field(blob, "available_from_date"),
            "to": field(blob, "available_to_date"),
            "rate": field(blob, "hire_unit_rate", False),
            "days": field(blob, "hire_units_allowed", False),
            "extraDays": field(blob, "extra_hire_units_allowed", False),
            "extraRate": field(blob, "extra_hire_unit_rate", False),
            "bookingFee": field(blob, "booking_fee_amount", False),
            "image": (re.search(r'conversions:.{0,120}?url:"(https://assets\.imoova\.com[^"]+)"',
                                blob, re.S) or [None, None])[1],
            "vehicle": field(veh, "name"),
            "vehicleType": field(veh, "type"),
            "brand": field(veh, "brand"),
            "sleeps": field(veh, "sleeps", False),
            "transmission": field(veh, "transmission"),
            "minAge": field(veh, "minimum_age", False),
            "badges": badges,
            "freeTank": "free tank" in badges.lower(),
        })
    return out


def d(s):
    return datetime.date.fromisoformat(s)


def window_works(r, w):
    """Findes der en afhentningsdato hvor turen lander i afleveringsvinduet?"""
    if not (r["from"] and r["to"] and r["days"]):
        return False, None
    lo = max(d(r["from"]), d(w["pickupFrom"]))
    hi = d(r["to"])
    p = lo
    while p <= hi:
        drop = p + datetime.timedelta(days=r["days"])
        if d(w["dropoffFrom"]) <= drop <= d(w["dropoffTo"]):
            return True, (p, drop)
        p += datetime.timedelta(days=1)
    return False, None


def build(r, w, now):
    ok, plan = window_works(r, w)
    per_day = (r["rate"] or 0) / 100
    b = r["badges"]
    amount = re.search(r"NZ\$([\d.,]+)", b or "")
    if b and "ferry" in b.lower():
        if amount:
            # Imoova skriver fx «NZ$150.00 Ferry Included». Beløbet kan være et
            # loft snarere end fuld dækning, og en camper koster 280-430 NZD
            # over Cook Strait — så det behandles som tilskud indtil det er bekræftet.
            ferry, fdet = "delvist", (
                f"Imoova skriver «{b}». Beløbet kan være et tilskud frem for fuld "
                f"dækning — en camper koster 280-430 NZD over Cook Strait. "
                f"Ring og få det bekræftet før booking.")
        else:
            ferry, fdet = "inkluderet", f"Imoova skriver «{b}»."
    else:
        ferry, fdet = "ubekræftet", (
            f"Færge ikke nævnt på opslaget{f' (står der: «{b}»)' if b else ''}.")

    if ok and ferry == "inkluderet" and per_day <= w["maxPricePerDayNZD"]:
        fit = "passer"
    elif ok and per_day <= w["maxPricePerDayNZD"]:
        fit = "naesten"
    else:
        fit = "nej"

    extra = ""
    if r["extraDays"]:
        extra = f" + {r['extraDays']} ekstra dage à {(r['extraRate'] or 0)/100:.0f} NZD"
    fee = f" + {(r['bookingFee'] or 0)/100:.0f} NZD bookinggebyr" if r["bookingFee"] else ""

    return {
        "id": "imoova-" + r["reference"].lower(),
        "source": "imoova-auto",
        "provider": "Imoova",
        "platform": "Imoova",
        "url": f"https://www.imoova.com/relocations/new-zealand/christchurch-to-auckland/{r['reference']}",
        "vehicle": " ".join(filter(None, [r["brand"], r["vehicle"]])) +
                   (f" · sover {r['sleeps']}" if r["sleeps"] else "") +
                   (" · automatgear" if r["transmission"] == "AUTOMATIC" else ""),
        "vehicleType": VEHICLE_TYPE_MAP.get(r["vehicleType"], "sedan"),
        "imageUrl": f"img/{r['reference'].lower()}.webp" if r["image"] else None,
        "imageCredit": "Foto: Imoova" if r["image"] else None,
        "route": "Christchurch → Auckland",
        "days": r["days"],
        "price": f"{per_day:.0f} NZD/dag{extra}{fee}",
        "pricePerDay": per_day,
        "totalCost": f"{per_day * (r['days'] or 0) + (r['bookingFee'] or 0)/100:.0f} NZD",
        "ferry": ferry,
        "ferryDetail": fdet,
        "fuel": "1 gratis tank" if r["freeTank"] else "ikke nævnt",
        "minAge": r["minAge"],
        "bond": None,
        "availability": {
            "state": "ledig" if ok else "ikke-i-vindue",
            "from": r["from"], "to": r["to"],
            "spaces": f"{r['count']} køretøjer" if r["count"] else "Ukendt",
            "detail": (f"Afhentning muligt {r['from']} til {r['to']} med {r['days']} dage til turen."
                       + (f" {r['count']} køretøjer ledige." if r["count"] else "")),
            "checkedAt": now, "confidence": "direkte",
        },
        "yourPlan": (f"Hent {plan[0]:%-d. %b} → aflever {plan[1]:%-d. %b}" if plan
                     else "Ingen dato lander i dit vindue"),
        "fit": fit,
        "fitReason": ({
            "passer": "Datoer, pris og betalt færge går alle op.",
            "naesten": "Datoer og pris passer, men færgen er ikke fuldt betalt.",
            "nej": "Ingen afhentningsdato lander i dit afleveringsvindue.",
        })[fit],
        "notes": f"Automatisk aflæst fra Imoova. Reference {r['reference']}.",
    }


def main():
    data = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
    w = data["window"]
    now = datetime.datetime.now(NZ).replace(microsecond=0).isoformat()

    try:
        html = fetch(URL).decode("utf-8", "replace")
    except Exception as e:
        print(f"Kunne ikke hente Imoova: {e}", file=sys.stderr)
        return 1

    rows = [r for r in parse(html)
            if r["name"] == "Christchurch to Auckland" and r["status"] == "READY"]
    if not rows:
        print("Ingen Christchurch→Auckland-opslag fundet — siden kan have ændret struktur.",
              file=sys.stderr)
        return 1

    (ROOT / "img").mkdir(exist_ok=True)
    fresh = []
    for r in rows:
        deal = build(r, w, now)
        if r["image"]:
            p = ROOT / deal["imageUrl"]
            if not p.exists():
                try:
                    p.write_bytes(fetch(r["image"], referer="https://www.imoova.com/"))
                except Exception as e:
                    print(f"  billede fejlede for {r['reference']}: {e}", file=sys.stderr)
                    deal["imageUrl"] = deal["imageCredit"] = None
        fresh.append(deal)

    old = {x["id"]: x for x in data["deals"] if x.get("source") == "imoova-auto"}
    kept = [x for x in data["deals"] if x.get("source") != "imoova-auto"
            and not x["id"].startswith("imoova-")]
    data["deals"] = kept + fresh

    added = [x for x in fresh if x["id"] not in old]
    gone = [x for x in old.values() if x["id"] not in {y["id"] for y in fresh}]
    changed = [x for x in fresh if x["id"] in old and (
        x["availability"]["from"] != old[x["id"]]["availability"]["from"]
        or x["availability"]["to"] != old[x["id"]]["availability"]["to"]
        or x["pricePerDay"] != old[x["id"]]["pricePerDay"]
        or x["fit"] != old[x["id"]]["fit"])]

    bits = []
    for x in added:
        tag = "NYT: " if x["fit"] == "passer" else ""
        bits.append(f"{tag}{x['vehicle']} ({x['days']} dage, {x['price']}, færge {x['ferry']})")
    for x in changed:
        bits.append(f"ændret: {x['vehicle']} — nu {x['fit']}, {x['availability']['from']}–{x['availability']['to']}")
    for x in gone:
        bits.append(f"væk: {x['vehicle']}")

    summary = ("Imoova automatisk tjek: " +
               (" · ".join(bits) if bits else
                f"ingen ændringer, {len(fresh)} opslag på ruten."))
    if bits or not data["log"] or not data["log"][-1]["summary"].startswith("Imoova automatisk"):
        data["log"].append({"ts": now, "summary": summary})
        data["log"] = data["log"][-40:]
    else:
        data["log"][-1] = {"ts": now, "summary": summary}

    data["updated"] = now
    (ROOT / "data.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(summary)
    print(f"{len(fresh)} Imoova-opslag · {sum(1 for x in data['deals'] if x['fit']=='passer')} passer i alt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
