"""Transfercar — læses via det API deres egen Next.js-side kalder (api.transfercar.com.au).

Hjemmesiden ligger bag Cloudflare og afviser almindelige kald, men den udleverer selv de to
adgangs-headers (CF-Access-Client-Id/-Secret) som browseren skal sende til API'et. Vi henter dem
fra søgesiden ved hver kørsel (de kan blive roteret) og falder tilbage på de sidst kendte.
"""
import datetime, json, re, sys, pathlib, urllib.parse
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common import fetch, assess, save_image, d as to_date, UA

SOURCE = "transfercar-auto"
LABEL = "Transfercar"
SITE = "https://www.transfercar.com.au"
API = "https://api.transfercar.com.au"
FALLBACK_HEADERS = {"CF-Access-Client-Id": "792832a623bed97848109da5bdde29bc.access",
                    "CF-Access-Client-Secret": "5ca9e9f382f8493ad18eb723a730b273d3f0be04284665473ec6376b26980753"}
BROWSER = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
           "Upgrade-Insecure-Requests": "1", "Sec-Fetch-Mode": "navigate",
           "Sec-Fetch-Dest": "document", "Sec-Fetch-Site": "none"}
QUERIES = [{"pickup": "custom:brisbane", "dropoff": "custom:sydney"},
           {"pickup": "custom:gold coast", "dropoff": "custom:sydney"},
           {"pickup": "custom:sunshine coast", "dropoff": "custom:sydney"}]


def access_headers():
    """Læs CF-Access-headers ud af søgesidens indlejrede konfiguration."""
    try:
        html = fetch(SITE + "/search", headers=BROWSER).decode("utf-8", "replace")
        pairs = re.findall(r'name\\?":\\?"(CF-Access-Client-(?:Id|Secret))\\?",\\?"value\\?":\\?"([^"\\]+)', html)
        found = dict(pairs)
        if "CF-Access-Client-Id" in found and "CF-Access-Client-Secret" in found:
            return found
    except Exception:
        pass
    return dict(FALLBACK_HEADERS)


def api(path, params, hdrs):
    h = {"Accept": "application/json, text/plain, */*", "Origin": SITE, **hdrs}
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    return json.loads(fetch(url, referer=SITE + "/", headers=h).decode("utf-8"))


def listings(hdrs):
    seen = set()
    for q in QUERIES:
        page = 1
        while True:
            res = api("/listings.json", {**q, "sort_col": "dates", "limit": 50, "page": page}, hdrs)
            rows = res.get("listings") or []
            for r in rows:
                if r["id"] in seen:
                    continue
                seen.add(r["id"])
                yield r
            if not rows or len(seen) >= (res.get("count") or 0) or page >= 5:
                break
            page += 1


def city(loc):
    """'Virginia (Brisbane)' -> 'Brisbane', 'Brisbane Airport' -> 'Brisbane'."""
    m = re.search(r"\(([^)]+)\)", loc or "")
    base = m.group(1) if m else (loc or "")
    return re.sub(r"\s+Airport$", "", base).strip()


def vehicle_type(vt):
    v = (vt or "").lower()
    if "motorhome" in v or "campervan" in v or "camper" in v or "berth" in v:
        return "campervan"
    if "truck" in v:
        return "truck"
    if "van" in v:
        return "van"
    if "suv" in v or "4wd" in v or "4x4" in v:
        return "suv"
    return "sedan"


def build(r, det, w, now):
    origin = city(r["pickup_location"])
    dest = city(r["dropoff_location"])
    pick_from = to_date(r["pickup_date"])
    today = to_date(now)
    if pick_from < today:
        pick_from = today
    drop_by = to_date(r["dropoff_date"])
    free_days = r.get("free_days") or 0
    paid_days = r.get("paid_days") or 0
    rate = float(r.get("price_per_free_day") or 0)
    paid_rate = r.get("price_per_paid_day")
    # Seneste afhentning: dagen før sidste afleveringsdag (turen kan køres på én lang dag).
    pick_to = drop_by - datetime.timedelta(days=1)
    lo = max(pick_from, to_date(w["pickupFrom"]))
    if lo > pick_to or not free_days:
        days = free_days or 1
    else:
        days = max(1, min(free_days, (drop_by - lo).days))
    a = assess(w, pick_from.isoformat(), pick_to.isoformat(), days, rate, origin, r.get("nb_listings"))

    pol = (det or {}).get("policies") or {}
    ins = pol.get("insurance_policy") or {}
    bond_m = re.search(r"\$\s?([\d,]+)", ins.get("bond") or "")
    bond = f"{bond_m.group(1).replace(',', '')} AUD" if bond_m else None
    deposit = pol.get("deposit_amount")
    min_age = pol.get("min_age")
    operator = None
    instr = ((det or {}).get("instructions") or {}).get("driver_booking_instructions") or ""
    m = re.search(r"confirmation (?:by|from) ([A-Z][A-Za-z&' ]+?)\s{1,3}(?:within|in|\.)", instr)
    if m:
        operator = m.group(1).strip()
    if not operator:
        comp = ((det or {}).get("operator") or {}).get("company") or ""
        comp = re.sub(r"\b(PTY|LTD|LIMITED|P/L)\b\.?", "", comp, flags=re.I).strip(" .,")
        operator = comp.title() if comp else None
    inc = r.get("inclusions") or (det or {}).get("inclusions") or []
    inc_txt = [i.get("name") or i.get("description") or str(i) for i in inc if i]
    fuel = "ikke inkluderet"
    for t in inc_txt:
        if "fuel" in t.lower() or "petrol" in t.lower() or "tank" in t.lower():
            fuel = t
    vt = r.get("vehicle_type") or "Køretøj"
    dvt = (det or {}).get("vehicle_type")
    if isinstance(dvt, dict) and dvt.get("name"):
        vt = f"{dvt['name'].strip()} ({vt})" if dvt["name"].strip().lower() not in vt.lower() else vt
    vtype = vehicle_type(vt)
    berth = re.search(r"(\d+)\s*berth", vt.lower())
    sleeps = int(berth.group(1)) if berth else None

    price = (f"{rate:.0f} AUD/dag i {free_days} gratis dag{'e' if free_days != 1 else ''}"
             if free_days else "Ingen gratis dage")
    if paid_days and paid_rate is not None:
        price += f" · op til {paid_days} ekstra dag{'e' if paid_days != 1 else ''} à {float(paid_rate):.0f} AUD"
    if deposit:
        price += f" · {deposit} AUD refunderbart depositum til udlejer"
    total = rate * days
    notes = [f"Automatisk aflæst fra Transfercar (opslag {r['id']})."]
    if operator:
        notes.append(f"Udlejer: {operator}.")
    if bond:
        notes.append(f"Sikkerhedsstillelse (bond) {bond} på kreditkort ved afhentning.")
    if ins.get("waiver") and "toll" in ins["waiver"].lower():
        notes.append("Vejafgifter (tolls) er ikke inkluderet.")
    if r.get("nb_pending_requests"):
        notes.append(f"{r['nb_pending_requests']} anden/andre har allerede bedt om den.")
    notes.append(f"Afhentning {r['pickup_location']}, aflevering {r['dropoff_location']}.")

    return {
        "id": f"transfercar-{r['id']}",
        "source": SOURCE,
        "provider": operator or "Transfercar",
        "platform": "Transfercar",
        "url": f"{SITE}/relocation/{urllib.parse.quote(origin)}/{urllib.parse.quote(dest)}/{r['id']}",
        "vehicle": vt + (f" · sover {sleeps}" if sleeps else ""),
        "vehicleType": vtype,
        "sleeps": sleeps,
        "canSleepIn": vtype == "campervan",
        "imageUrl": f"img/tc-{r['id']}.{(r.get('image_path') or 'x.png').rsplit('.', 1)[-1][:4]}" if r.get("image_path") else None,
        "imageCredit": "Foto: Transfercar" if r.get("image_path") else None,
        "_imageSrc": r.get("image_path"),
        "route": f"{origin} → {dest}",
        "pickupCity": origin,
        "days": days,
        "price": price,
        "pricePerDay": rate,
        "totalCost": f"{total:.0f} AUD + brændstof" if fuel == "ikke inkluderet" else f"{total:.0f} AUD",
        "fuel": fuel,
        "kmLimit": None,
        "minAge": min_age,
        "bond": bond,
        "availability": {
            "state": a["state"],
            "from": pick_from.isoformat(),
            "to": pick_to.isoformat(),
            "spaces": f"{r['nb_listings']} køretøj{'er' if r['nb_listings'] != 1 else ''}" if r.get("nb_listings") else "Ukendt",
            "detail": (f"Afhentning mulig {pick_from.isoformat()} til {pick_to.isoformat()}, aflevering senest "
                       f"{drop_by.isoformat()}, {free_days} gratis dag{'e' if free_days != 1 else ''}."),
            "checkedAt": now,
            "confidence": "direkte",
        },
        "yourPlan": a["yourPlan"],
        "fit": a["fit"],
        "fitReason": a["fitReason"],
        "notes": " ".join(notes),
    }


def fetch_deals(w, now):
    hdrs = access_headers()
    out = []
    for r in listings(hdrs):
        if r.get("is_closed") or r.get("status_name") not in (None, "listed"):
            continue
        if "sydney" not in (r.get("dropoff_location") or "").lower():
            continue
        try:
            det = api(f"/listing/{r['id']}", None, hdrs)
        except Exception:
            det = None
        deal = build(r, det, w, now)
        src = deal.pop("_imageSrc")
        if src and not save_image(src, deal["imageUrl"], referer=SITE + "/"):
            deal["imageUrl"] = deal["imageCredit"] = None
        out.append(deal)
    return out


if __name__ == "__main__":
    w = {"pickupFrom": "2026-09-30", "pickupTo": "2026-10-03", "origin": "Brisbane", "maxPricePerDayAUD": 50}
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=10))).isoformat()
    h = access_headers(); print("headers from page:", {k: v[:10] + "…" for k, v in h.items()})
    for x in fetch_deals(w, now):
        print(x["fit"], "|", x["provider"], "|", x["route"], "|", x["vehicle"], "|", x["days"], "d |", x["price"], "|", x["availability"]["detail"], "|", x["bond"], x["minAge"], "|", x["imageUrl"])
