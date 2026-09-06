"""Imoova — læses via deres GraphQL-API (samme kald som deres egen hjemmeside laver).

Fordelen frem for at parse HTML'en: vi får ALLE opslag på ruten (siden viser kun 18 ad gangen),
og inklusioner (gratis tank, brændstofrefusion, obligatoriske gebyrer) kommer struktureret.
"""
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common import fetch, assess, save_image, slug

SOURCE = "imoova-auto"
LABEL = "Imoova"
API = "https://api.imoova.com/graphql"
DEPARTURES = ["brisbane", "gold-coast", "sunshine-coast"]  # Brisbane først, de to andre er nær-alternativer
DELIVERY = "sydney"

QUERY = """
query R($page:Int,$first:Int,$dep:Mixed!,$del:Mixed!){
 relocations(first:$first,page:$page,status:[READY],type:[RELOCATION,GAP_RENTAL],relevanceOrder:true,
   whereDepartureCity:{AND:[{column:SLUG,operator:EQ,value:$dep}]},
   whereDeliveryCity:{AND:[{column:SLUG,operator:EQ,value:$del}]}){
  paginatorInfo{ total lastPage currentPage hasMorePages }
  data{ id reference name status type count currency
    available_from_date available_to_date earliest_departure_date latest_departure_date
    hire_unit_type hire_unit_rate hire_units_allowed extra_hire_units_allowed extra_hire_unit_rate
    booking_fee_amount retail_rate distance_allowed
    images{ url conversions{ type url } }
    inclusions{ type description value has_free_tank }
    departureCity{ name slug } deliveryCity{ name slug }
    vehicle{ type name brand seatbelts sleeps transmission minimum_age }
  } } }"""

TYPE_MAP = {"CAR": "sedan", "SUV": "suv", "UTE": "suv", "FOUR_WHEEL_DRIVE": "suv",
            "CAMPER_VAN": "campervan", "MOTOR_HOME": "campervan", "FOUR_WHEEL_DRIVE_CAMPER": "campervan",
            "CARAVAN": "campervan", "MINI_VAN": "van", "VAN": "van", "BOX_TRUCK": "truck", "MINI_BUS": "minibus"}
TYPE_DA = {"sedan": "personbil", "suv": "SUV", "campervan": "campervan", "van": "varevogn",
           "truck": "lastbil", "minibus": "minibus"}


def gql(variables):
    body = json.dumps({"query": QUERY, "variables": variables}).encode()
    raw = fetch(API, data=body, referer="https://www.imoova.com/",
                headers={"Content-Type": "application/json", "Accept": "application/json",
                         "Origin": "https://www.imoova.com"})
    r = json.loads(raw)
    if "errors" in r:
        raise RuntimeError("Imoova GraphQL: " + r["errors"][0].get("message", "ukendt fejl"))
    return r["data"]["relocations"]


def rows():
    for dep in DEPARTURES:
        page = 1
        while True:
            res = gql({"page": page, "first": 50, "dep": dep, "del": DELIVERY})
            for r in res["data"]:
                yield dep, r
            if not res["paginatorInfo"]["hasMorePages"]:
                break
            page += 1


def build(dep, r, w, now):
    v = r.get("vehicle") or {}
    ref = r["reference"]
    rate = (r["hire_unit_rate"] or 0) / 100
    days = r["hire_units_allowed"] or 0
    fee = (r["booking_fee_amount"] or 0) / 100
    inc = r.get("inclusions") or []
    charges = sum((i["value"] or 0) for i in inc if i["type"] == "CHARGE") / 100
    charge_txt = "; ".join(f"{i['description']} {(i['value'] or 0)/100:.0f} AUD" for i in inc if i["type"] == "CHARGE")
    fuel_inc = [i for i in inc if i["type"] == "FUEL" or i["has_free_tank"]]
    if any(i["has_free_tank"] for i in inc):
        fuel = "1 gratis tank"
    elif fuel_inc:
        i = fuel_inc[0]
        fuel = (f"{(i['value'] or 0)/100:.0f} AUD brændstof refunderes" if i["value"] else "brændstoftilskud") + \
               (f" ({i['description']})" if i.get("description") else "")
    else:
        fuel = "ikke inkluderet"
    other = [i["description"] for i in inc if i["type"] in ("OTHER", "FERRY") and i.get("description")]

    origin = (r.get("departureCity") or {}).get("name") or dep.replace("-", " ").title()
    a = assess(w, r.get("earliest_departure_date") or r["available_from_date"],
               r.get("latest_departure_date") or r["available_to_date"], days, rate, origin, r.get("count"))

    vtype = TYPE_MAP.get(v.get("type"), "sedan")
    sleeps = v.get("sleeps")
    can_sleep = vtype == "campervan" or bool(sleeps)
    img = None
    if r.get("images"):
        m = r["images"][0]
        img = next((c["url"] for c in (m.get("conversions") or []) if c["type"] == "SMALL"), m.get("url"))

    extra = ""
    if r["extra_hire_units_allowed"]:
        n = r['extra_hire_units_allowed']
        extra = f" · op til {n} ekstra dag{'e' if n != 1 else ''} à {(r['extra_hire_unit_rate'] or 0)/100:.0f} AUD"
    total = rate * days + fee + charges
    total_txt = f"{total:.0f} AUD" + (" + brændstof" if fuel == "ikke inkluderet" else "")

    veh = " ".join(x for x in [v.get("brand"), v.get("name")] if x and x.lower() != "none") or TYPE_DA[vtype]
    bits = [veh]
    if sleeps:
        bits.append(f"sover {sleeps}")
    if v.get("seatbelts"):
        bits.append(f"{v['seatbelts']} sæder")
    if v.get("transmission") == "AUTOMATIC":
        bits.append("automatgear")
    elif v.get("transmission") == "MANUAL":
        bits.append("manuelt gear")

    notes = [f"Automatisk aflæst fra Imoova. Reference {ref}."]
    if charge_txt:
        notes.append(f"Obligatorisk gebyr hos udlejer: {charge_txt}.")
    if other:
        notes.append("Inkluderet: " + ", ".join(other) + ".")
    if r.get("type") == "GAP_RENTAL":
        notes.append("Dette er en rabatteret almindelig leje (gap rental), ikke en ægte relocation.")

    return {
        "id": f"imoova-{ref.lower()}",
        "source": SOURCE,
        "provider": "Imoova",
        "platform": "Imoova",
        "url": f"https://www.imoova.com/relocations/australia/{slug(origin)}-to-{DELIVERY}/{ref}",
        "vehicle": " · ".join(bits),
        "vehicleType": vtype,
        "sleeps": sleeps,
        "canSleepIn": can_sleep,
        "imageUrl": f"img/{ref.lower()}.webp" if img else None,
        "imageCredit": "Foto: Imoova" if img else None,
        "_imageSrc": img,
        "route": f"{origin} → Sydney",
        "pickupCity": origin,
        "days": days,
        "price": f"{rate:.0f} AUD/dag · {fee:.0f} AUD bookinggebyr{extra}",
        "pricePerDay": rate,
        "totalCost": total_txt,
        "fuel": fuel,
        "kmLimit": f"{r['distance_allowed']} km" if r.get("distance_allowed") else None,
        "minAge": v.get("minimum_age"),
        "bond": None,
        "availability": {
            "state": a["state"],
            "from": r.get("earliest_departure_date") or r["available_from_date"],
            "to": r.get("latest_departure_date") or r["available_to_date"],
            "spaces": f"{r['count']} køretøj{'er' if (r['count'] or 0) != 1 else ''}" if r.get("count") else "Ukendt",
            "detail": (f"Afhentning mulig {r.get('earliest_departure_date') or r['available_from_date']} til "
                       f"{r.get('latest_departure_date') or r['available_to_date']} med {days} dage til turen."),
            "checkedAt": now,
            "confidence": "direkte",
        },
        "yourPlan": a["yourPlan"],
        "fit": a["fit"],
        "fitReason": a["fitReason"],
        "notes": " ".join(notes),
    }


def fetch_deals(w, now):
    out = []
    for dep, r in rows():
        if (r.get("deliveryCity") or {}).get("slug", DELIVERY) != DELIVERY:
            continue
        deal = build(dep, r, w, now)
        src = deal.pop("_imageSrc")
        if src and not save_image(src, deal["imageUrl"], referer="https://www.imoova.com/"):
            deal["imageUrl"] = deal["imageCredit"] = None
        out.append(deal)
    return out


if __name__ == "__main__":
    import datetime
    w = {"pickupFrom": "2026-09-30", "pickupTo": "2026-10-03", "origin": "Brisbane", "maxPricePerDayAUD": 50}
    for d in fetch_deals(w, datetime.datetime.now().isoformat()):
        print(d["fit"], "|", d["route"], "|", d["vehicle"], "|", d["days"], "d |", d["price"], "|", d["totalCost"], "|", d["fuel"], "|", d["yourPlan"], "|", d["imageUrl"])
