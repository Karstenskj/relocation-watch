"""Fælles hjælpefunktioner: HTTP, datoer, vinduesberegning og fit-vurdering.

Alt her er ren standardbibliotek, så GitHub Actions kan køre det uden installation.
"""
import datetime, json, pathlib, re, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
# Brisbane har ingen sommertid: altid UTC+10.
BNE = datetime.timezone(datetime.timedelta(hours=10))
DA_MONTHS = ["jan", "feb", "mar", "apr", "maj", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]


def now_iso():
    return datetime.datetime.now(BNE).replace(microsecond=0).isoformat()


def fetch(url, referer=None, data=None, headers=None, timeout=60):
    h = {"User-Agent": UA, "Accept-Language": "en-AU,en;q=0.9", "Accept": "*/*"}
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
    """'2026-09-30' eller '2026-09-30T00:00:00.000+00:00' -> date."""
    if not s:
        return None
    return datetime.date.fromisoformat(str(s)[:10])


def da(date):
    """Dansk kort dato: 30. sep."""
    return f"{date.day}. {DA_MONTHS[date.month - 1]}"


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def assess(window, pickup_from, pickup_to, days, price_per_day, origin, count=None):
    """Vurdér et tilbud mod Karstens vindue.

    pickup_from/pickup_to: udbyderens tidligste og seneste afhentningsdato.
    Returnerer dict med state, fit, fitReason, yourPlan og plan (tuple af datoer).
    """
    w_from, w_to = d(window["pickupFrom"]), d(window["pickupTo"])
    near = window.get("nearMissDays", 7)
    cap = window["maxPricePerDayAUD"]
    alt_origin = slug(origin) != slug(window["origin"])

    pf, pt = d(pickup_from), d(pickup_to) or d(pickup_from)
    if not pf:
        return {"state": "ukendt", "fit": "nej", "plan": None,
                "yourPlan": "Ingen datoer oplyst",
                "fitReason": "Udbyderen oplyser ingen afhentningsdatoer."}

    lo, hi = max(pf, w_from), min(pt, w_to)
    dates_ok = lo <= hi
    overlap = (hi - lo).days + 1 if dates_ok else 0
    price_ok = price_per_day is not None and price_per_day <= cap

    # Nær-miss: vinduet lukker op til `near` dage før dit, eller åbner op til `near` dage efter.
    near_before = (not dates_ok) and pt < w_from and (w_from - pt).days <= near
    near_after = (not dates_ok) and pf > w_to and (pf - w_to).days <= near

    plan = None
    if dates_ok:
        drop = lo + datetime.timedelta(days=days or 1)
        plan = (lo, drop)

    if dates_ok and price_ok and not alt_origin:
        fit = "passer"
        reason = "Afhentning i dit vindue, prisen er under grænsen."
        if count == 1:
            reason += " Kun ét køretøj, så book hurtigt."
    elif dates_ok and price_ok and alt_origin:
        fit = "naesten"
        reason = f"Prisen og datoerne passer, men afhentning er i {origin}, ikke Brisbane."
    elif price_ok and (near_before or near_after) and not alt_origin:
        fit = "naesten"
        gap = (w_from - pt).days if near_before else (pf - w_to).days
        reason = (f"Prisen passer, men seneste afhentning er {da(pt)}, {gap} dag(e) før dit vindue. "
                  "Udbyderne forlænger ofte, så den overvåges." if near_before else
                  f"Prisen passer, men tidligste afhentning er {da(pf)}, {gap} dag(e) efter dit vindue.")
    elif dates_ok and not price_ok:
        fit = "nej"
        reason = f"Datoerne passer, men {price_per_day:.0f} AUD/dag er over din grænse på {cap}."
    elif alt_origin and not dates_ok:
        fit = "nej"
        reason = f"Afhentning i {origin} og ingen dato i dit vindue."
    else:
        fit = "nej"
        reason = "Ingen afhentningsdato lander i dit vindue."

    if dates_ok:
        state = "ledig-snaevert" if overlap <= 1 else "ledig"
    else:
        state = "ikke-i-vindue"

    if plan:
        your = f"Hent {da(plan[0])} → aflever {da(plan[1])}"
        if overlap > 1:
            your += f" (afhentning mulig {da(lo)}–{da(hi)})"
    elif near_before:
        your = f"Seneste afhentning {da(pt)}, {(w_from - pt).days} dag(e) for tidligt"
    elif near_after:
        your = f"Tidligste afhentning {da(pf)}, {(pf - w_to).days} dag(e) for sent"
    else:
        your = "Ingen dato lander i dit vindue"

    return {"state": state, "fit": fit, "fitReason": reason, "yourPlan": your, "plan": plan,
            "overlap": overlap}


def save_image(url, dest, referer=None):
    """Hent et billede ned lokalt hvis det ikke allerede findes. Returnerer True ved succes."""
    p = ROOT / dest
    if p.exists():
        return True
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(fetch(url, referer=referer))
        return True
    except Exception:
        return False
