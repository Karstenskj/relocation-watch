"""Fælles hjælpefunktioner: HTTP, datoer, byer og vurderingen af et tilbud.

Alt her er ren standardbibliotek, så GitHub Actions kan køre det uden installation.
"""
import datetime, json, pathlib, re, unicodedata, urllib.request
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
# Ærlig, generisk robot. Vi udgiver os ikke for at være en almindelig browser.
UA = "Mozilla/5.0 (compatible; deal-watcher/2.0)"
CPH = ZoneInfo("Europe/Copenhagen")
DA_MONTHS = ["jan", "feb", "mar", "apr", "maj", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]

# Byer i Danmark, som kilderne kan finde på at skrive (også svenske og tyske stavemåder).
DK_CITIES = ["kobenhavn", "kopenhamn", "kopenhagen", "copenhagen", "kastrup", "billund", "aarhus",
             "arhus", "odense", "aalborg", "esbjerg", "kolding", "vejle", "roskilde", "herning",
             "randers", "horsens", "padborg", "rodby", "gedser", "frederikshavn", "hirtshals",
             "helsingor", "danmark", "denmark", "danemark"]


def now_iso():
    return datetime.datetime.now(CPH).replace(microsecond=0).isoformat()


def today():
    return datetime.datetime.now(CPH).date()


def fetch(url, referer=None, data=None, headers=None, timeout=60):
    h = {"User-Agent": UA, "Accept-Language": "da-DK,da;q=0.9,en;q=0.6", "Accept": "*/*"}
    if referer:
        h["Referer"] = referer
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_json(url, **kw):
    kw.setdefault("headers", {})
    kw["headers"].setdefault("Accept", "application/json")
    return json.loads(fetch(url, **kw).decode("utf-8"))


def d(s):
    """'2026-12-30' eller '2026-12-30T00:00:00.000+00:00' -> date."""
    if not s:
        return None
    return datetime.date.fromisoformat(str(s)[:10])


def utc_to_cph_date(s):
    """'2026-12-30T13:00:00.000Z' -> dato i dansk tid."""
    if not s:
        return None
    t = datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=datetime.timezone.utc)
    return t.astimezone(CPH).date().isoformat()


def da(date):
    """Dansk kort dato: 30. dec."""
    return f"{date.day}. {DA_MONTHS[date.month - 1]}"


def slug(s):
    """Samme nøgle som i scripts/build_places.py: små bogstaver, uden accenter, ord adskilt af -."""
    s = unicodedata.normalize("NFKD", (s or "").lower().replace("ø", "o").replace("æ", "ae").replace("å", "a")
                              .replace("ß", "ss").replace("ł", "l").replace("đ", "d"))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


# Ord, der aldrig alene er et stednavn (lufthavn, station, bydel osv.).
STOP = set("""airport lufthavn flughafen flygplats lufthamn station bahnhof hbf hauptbahnhof centrum center
centre city central centralstation terminal stadt zentrum nord syd sud ost vest west norr sodra ostra vastra
the am an der die das den de la le i in auf bei og und and to from fra til kommune kommun by gare port havn
hafen hamn ferry faerge faergehavn depot parkering parking downtown""".split())
_PLACES = None
UNKNOWN = set()    # navne, stedlisten ikke kender, samlet under en kørsel


def places():
    global _PLACES
    if _PLACES is None:
        _PLACES = json.loads((ROOT / "scripts" / "places.json").read_text(encoding="utf-8"))
    return _PLACES


def locate(name, country=None):
    """Slå et stednavn op i scripts/places.json.

    Returnerer {"name", "country", "km"} eller None, hvis navnet er ukendt. km er luftlinjen til
    nærmeste punkt i Danmark uden Bornholm (0 i Danmark, None langt væk). Opslaget sker på hele
    ord: det længste navn i teksten vinder, og ved lige lange navne det største sted. Oplyser
    kilden landet, bruges det. Et land uden for zonen giver straks "uden for" uden opslag.
    """
    P = places()
    cc = (country or "").upper() or None
    if not name or not str(name).strip():
        return None
    if cc and cc not in P["zoneCountries"]:
        return {"name": str(name).strip(), "country": cc, "km": None}

    def look(k):
        if cc:
            i = P["byCountry"].get(cc, {}).get(k)
            if i is None:
                i = P["names"].get(k)
                if i is not None and P["places"][i][1] != cc:
                    i = None
            return i
        return P["names"].get(k)

    hit = None
    for code in re.findall(r"\b[A-Z]{3}\b", str(name)):
        if code in P["codes"]:
            hit = P["codes"][code]
            break
    if hit is None:
        toks = [t for t in slug(name).split("-") if t]
        for n in range(min(5, len(toks)), 0, -1):
            found = [(look("-".join(toks[i:i + n])), i) for i in range(len(toks) - n + 1)
                     if n > 1 or (toks[i] not in STOP and len(toks[i]) > 2)]
            found = [f for f in found if f[0] is not None]
            if found:
                hit, at = min(found)      # listen er sorteret med de største steder først
                # Dækker navnet kun en del af teksten, skal stedet være stort. Ellers kan et
                # ukendt navn som "Straßburg" ramme en lille by, der hedder "Burg".
                rest = [t for t in toks[:at] + toks[at + n:]
                        if t not in STOP and len(t) > 2 and t not in toks[at:at + n]]
                if rest and hit >= P["bigFrom"]:
                    hit = None
                break
    if hit is None:
        UNKNOWN.add(str(name).strip())
        return None
    pname, pcc, km = P["places"][hit]
    return {"name": pname, "country": pcc, "km": km}


def is_dk_city(name):
    s = slug(name)
    return any(re.search(rf"(^|-){c}($|-)", s) for c in DK_CITIES)


def end_info(window, name, country=None):
    """Én ende af en tur: ("dk" | "zone" | "ude", sted eller None)."""
    home = window["homeCountry"]
    if (country or "").upper() == home or (not country and is_dk_city(name)):
        return "dk", {"name": name, "country": home, "km": 0}
    p = locate(name, country)
    if p and p["country"] == home:
        return "dk", p
    if p and p["km"] is not None and p["km"] <= window["zoneKm"]:
        return "zone", p
    return "ude", p


def ends(window, from_name, to_name, from_country=None, to_country=None):
    """Vurdér begge ender. Returnerer retning, lande og stedet i zonen.

    direction: fra-dk, til-dk, indenrigs, zone (ingen ende i Danmark, men mindst én inden for
    zonen) eller None. zonePlace er fx "Hamborg, ca. 140 km fra Danmark" (den nærmeste, hvis
    begge ender ligger i zonen).
    """
    fk, fp = end_info(window, from_name, from_country)
    tk, tp = end_info(window, to_name, to_country)
    if fk == "dk" and tk == "dk":
        dirn = "indenrigs"
    elif fk == "dk":
        dirn = "fra-dk"
    elif tk == "dk":
        dirn = "til-dk"
    elif "zone" in (fk, tk):
        dirn = "zone"
    else:
        dirn = None
    zp = None
    if dirn == "zone":
        z = min((p for k, p in ((fk, fp), (tk, tp)) if k == "zone"), key=lambda p: p["km"])
        km = max(5, int(round(z["km"] / 5.0)) * 5)
        zp = {"name": z["name"], "km": z["km"], "text": f"{z['name']}, ca. {km} km fra Danmark"}
    return {"direction": dirn, "zone": zp,
            "fromCountry": (from_country or (fp or {}).get("country")),
            "toCountry": (to_country or (tp or {}).get("country"))}


def direction(window, from_country, to_country, from_city="", to_city=""):
    """Kort form af ends(): kun retningen."""
    return ends(window, from_city, to_city, from_country, to_country)["direction"]


def to_dkk(window, amount, currency):
    if amount is None or not currency:
        return None
    rate = window["fx"].get(currency.upper())
    return None if rate is None else round(amount * rate, 2)


def assess(window, pickup_from, pickup_to, days, price_per_day, currency, direction_,
           min_age=None, license_years=None, blocker=None, count=None, zone=None):
    """Vurdér et tilbud mod vinduet.

    pickup_from/pickup_to: udbyderens tidligste og seneste afhentningsdato.
    price_per_day: dagspris for selve bilen i `currency`. Gebyrer regnes ikke med her.
    min_age: udbyderens laveste tilladte alder for føreren, None hvis ukendt.
    zone: stedet i zonen fra ends() (bruges i teksten, når retningen er "zone").
    blocker: tekst hvis tilbuddet af en anden grund ikke kan bookes (fx kræver svensk personnummer).
    """
    w_from, w_to = d(window["pickupFrom"]), d(window["pickupTo"])
    near = window.get("nearMissDays", 5)
    cap = window["maxPricePerDayDKK"]
    max_age = window.get("maxMinAge")
    dkk = to_dkk(window, price_per_day, currency)

    pf, pt = d(pickup_from), d(pickup_to) or d(pickup_from)
    base = {"pricePerDayDKK": dkk, "direction": direction_,
            "zonePlace": zone["text"] if zone and direction_ == "zone" else None,
            "zoneDistanceKm": zone["km"] if zone and direction_ == "zone" else None}
    if not pf:
        return {**base, "state": "ukendt", "fit": "nej", "plan": None, "overlap": 0,
                "yourPlan": "Ingen datoer oplyst",
                "fitReason": "Udbyderen oplyser ingen afhentningsdatoer."}

    lo, hi = max(pf, w_from), min(pt, w_to)
    dates_ok = lo <= hi
    overlap = (hi - lo).days + 1 if dates_ok else 0
    price_ok = dkk is not None and dkk <= cap
    near_before = (not dates_ok) and pt < w_from and (w_from - pt).days <= near
    near_after = (not dates_ok) and pf > w_to and (pf - w_to).days <= near
    gap = (w_from - pt).days if near_before else (pf - w_to).days if near_after else None
    real_dir = direction_ in ("fra-dk", "til-dk", "zone")
    end_off = direction_ == "indenrigs"

    end_txt = "Turen går inden for Danmark." if end_off else ""
    zkm = window.get("zoneKm", 300)
    where = (f"En ende inden for {zkm} km af Danmark ({zone['text']})" if direction_ == "zone" and zone
             else f"En ende inden for {zkm} km af Danmark" if direction_ == "zone" else "En ende i Danmark")
    if dkk is not None:
        price_txt = f"ca. {dkk:.0f} kr./dag"
    elif price_per_day is None:
        price_txt = "prisen er ikke oplyst"
    elif not currency:
        price_txt = "valuta ukendt"
    else:
        price_txt = f"kurs for {currency.upper()} mangler"

    if min_age is not None and max_age is not None and min_age > max_age:
        fit, reason = "nej", f"Kræver fører på mindst {min_age} år."
    elif blocker:
        fit, reason = "nej", blocker
    elif dates_ok and price_ok and real_dir:
        fit, reason = "passer", f"{where}, afhentning i vinduet og {price_txt}."
        if count == 1:
            reason += " Kun ét køretøj, så book hurtigt."
    elif dates_ok and price_ok and end_off:
        fit, reason = "naesten", f"Datoer og pris passer ({price_txt}). {end_txt}"
    elif price_ok and real_dir and (near_before or near_after):
        fit = "naesten"
        reason = (f"Prisen passer, men seneste afhentning er {da(pt)}, {gap} dag(e) før vinduet."
                  if near_before else
                  f"Prisen passer, men tidligste afhentning er {da(pf)}, {gap} dag(e) efter vinduet.")
    elif dates_ok and not price_ok:
        fit = "nej"
        reason = (f"Datoerne passer, men {price_txt} er over loftet på {cap} kr."
                  if dkk is not None else f"Datoerne passer, men {price_txt}.")
    elif not dates_ok:
        fit = "nej"
        if near_before or near_after:
            reason = (f"Afhentning {gap} dag(e) {'før' if near_before else 'efter'} vinduet"
                      + (f", og {end_txt[0].lower()}{end_txt[1:]}" if end_txt else ".")
                      + ("" if price_ok or end_txt else f" Og {price_txt} er over loftet."))
        else:
            reason = "Ingen afhentningsdato lander i vinduet."
    else:
        fit, reason = "nej", f"Flere krav passer ikke. {end_txt}".strip()

    if fit != "nej":
        if min_age is None:
            reason += " Tjek aldersgrænsen."
        if license_years:
            reason += f" Kræver kørekort i mindst {license_years} år."

    state = ("ledig-snaevert" if overlap <= 1 else "ledig") if dates_ok else "ikke-i-vindue"
    plan = None
    if dates_ok:
        plan = (lo, lo + datetime.timedelta(days=max(days or 1, 1)))
        your = f"Hent {da(plan[0])}, aflever senest {da(plan[1])}"
        if overlap > 1:
            your += f" (afhentning mulig {da(lo)} til {da(hi)})"
    elif near_before:
        your = f"Seneste afhentning {da(pt)}, {gap} dag(e) for tidligt"
    elif near_after:
        your = f"Tidligste afhentning {da(pf)}, {gap} dag(e) for sent"
    else:
        your = "Ingen dato lander i vinduet"

    return {**base, "state": state, "fit": fit, "fitReason": reason, "yourPlan": your,
            "plan": plan, "overlap": overlap}


def past_cutoff(window):
    """Er sidste brugsdag passeret? Datoen står i data.json som window.stopAfter.

    Vi regner i dansk tid. Overvågningen kører til og med den dato og slukker derefter
    sig selv, både i skyen og lokalt.
    """
    stop = window.get("stopAfter")
    if not stop:
        return False
    return today() > datetime.date.fromisoformat(stop)


def money(amount, currency):
    if amount is None:
        return "ikke oplyst"
    s = f"{amount:,.2f}".rstrip("0").rstrip(".").replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} {currency}"


def build_deal(w, now, a, **kw):
    """Samler et opslag i det format siden læser. `a` er resultatet af assess()."""
    av = kw.pop("availability", {})
    out = {
        "id": None, "source": None, "provider": None, "platform": None, "url": None,
        "vehicle": None, "vehicleType": "sedan", "sleeps": None, "canSleepIn": False,
        "imageUrl": None, "route": None, "direction": a["direction"],
        "zonePlace": a.get("zonePlace"), "zoneDistanceKm": a.get("zoneDistanceKm"),
        "pickupCity": None, "dropoffCity": None, "pickupCountry": None, "dropoffCountry": None,
        "days": None, "price": None, "pricePerDay": None, "currency": None,
        "pricePerDayDKK": a["pricePerDayDKK"], "totalCost": None, "fuel": None, "kmLimit": None,
        "minAge": None, "minAgeNote": None, "licenseYears": None, "youngDriverFee": None,
        "bond": None, "notes": None,
    }
    out.update(kw)
    out["availability"] = {"state": a["state"], "from": av.get("from"), "to": av.get("to"),
                           "spaces": av.get("spaces"), "detail": av.get("detail"),
                           "checkedAt": now, "confidence": av.get("confidence", "direkte")}
    out.update({"yourPlan": a["yourPlan"], "fit": a["fit"], "fitReason": a["fitReason"]})
    return out
