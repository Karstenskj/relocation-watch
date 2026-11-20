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
    s = unicodedata.normalize("NFKD", (s or "").lower().replace("ø", "o").replace("æ", "ae").replace("å", "a"))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def near_city(window, name):
    """Navnet på nærbyen, hvis `name` er en af nærbyerne (Malmö, Hamburg osv.), ellers None."""
    s = slug(name)
    for c in window["nearCities"]:
        if slug(c["name"]) in s or any(a in s for a in c.get("aliases", [])):
            return c["name"]
    return None


def near_country(window, name):
    n = near_city(window, name)
    return next((c["country"] for c in window["nearCities"] if c["name"] == n), None) if n else None


def is_dk_city(name):
    s = slug(name)
    return any(re.search(rf"(^|-){c}($|-)", s) for c in DK_CITIES)


def direction(window, from_country, to_country, from_city="", to_city=""):
    """fra-dk, til-dk, indenrigs, naer eller None (ingen ende i Danmark eller en nærby)."""
    home = window["homeCountry"]
    f_dk, t_dk = from_country == home, to_country == home
    if f_dk and t_dk:
        return "indenrigs"
    if f_dk:
        return "fra-dk"
    if t_dk:
        return "til-dk"
    if near_city(window, from_city) or near_city(window, to_city):
        return "naer"
    return None


def to_dkk(window, amount, currency):
    if amount is None:
        return None
    rate = window["fx"].get((currency or "DKK").upper())
    return None if rate is None else round(amount * rate, 2)


def assess(window, pickup_from, pickup_to, days, price_per_day, currency, direction_,
           min_age=None, license_years=None, blocker=None, count=None):
    """Vurdér et tilbud mod vinduet.

    pickup_from/pickup_to: udbyderens tidligste og seneste afhentningsdato.
    price_per_day: dagspris for selve bilen i `currency`. Gebyrer regnes ikke med her.
    min_age: udbyderens laveste tilladte alder for føreren, None hvis ukendt.
    blocker: tekst hvis tilbuddet af en anden grund ikke kan bookes (fx kræver svensk personnummer).
    """
    w_from, w_to = d(window["pickupFrom"]), d(window["pickupTo"])
    near = window.get("nearMissDays", 5)
    cap = window["maxPricePerDayDKK"]
    max_age = window.get("maxMinAge")
    dkk = to_dkk(window, price_per_day, currency)

    pf, pt = d(pickup_from), d(pickup_to) or d(pickup_from)
    base = {"pricePerDayDKK": dkk, "direction": direction_}
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
    real_dir = direction_ in ("fra-dk", "til-dk")
    end_off = direction_ in ("naer", "indenrigs")

    end_txt = {"naer": "Den ene ende er en nærby, ikke Danmark.",
               "indenrigs": "Turen går inden for Danmark."}.get(direction_, "")
    price_txt = (f"ca. {dkk:.0f} kr./dag" if dkk is not None else "prisen er ikke oplyst")

    if min_age is not None and max_age is not None and min_age > max_age:
        fit, reason = "nej", f"Kræver fører på mindst {min_age} år."
    elif blocker:
        fit, reason = "nej", blocker
    elif dates_ok and price_ok and real_dir:
        fit, reason = "passer", f"En ende i Danmark, afhentning i vinduet og {price_txt}."
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
                  if dkk is not None else "Datoerne passer, men prisen er ikke oplyst.")
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
