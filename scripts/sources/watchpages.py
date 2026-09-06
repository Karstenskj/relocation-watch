"""Holder øje med udlejersider der kan læses, men som ikke har nogen struktureret liste.

Flere udlejere skriver bare «vi har af og til flytninger, ring til os». Der er ikke noget at
hente automatisk i dag, men siden kan sagtens ændre sig. Modulet gemmer et fingeraftryk af den
relevante del af hver side og siger til, når teksten ændrer sig, eller når både Brisbane og
Sydney pludselig optræder tæt på hinanden.

Det giver ingen tilbud på forsiden. Det giver en linje i loggen og en status på kildekortet,
så «disse skal du selv tjekke» bliver til «robotten siger til når der sker noget».
"""
import hashlib, html as H, re, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common import fetch

LABEL = "Sideovervågning"

PAGES = [
    ("Cruisin Motorhomes", "https://www.cruisinmotorhomes.com.au/relocation-offers/"),
    ("Travellers Autobarn", "https://www.travellers-autobarn.com.au/campervan-hire-australia/campervan-relocations"),
    ("Let's Go Motorhomes", "https://www.letsgomotorhomes.com.au/relocations/"),
    ("Camperman Australia", "https://www.campermanaustralia.com/relocation-specials/"),
    ("Awesome Campers", "https://www.awesomecampers.com.au/relocation-specials"),
    ("Wicked Campers", "https://www.wickedcampers.com.au/relocation"),
    ("Spaceships Australia", "https://www.spaceshipsrentals.com.au/deals"),
    ("Star RV Australia", "https://www.starrv.com/au/motorhome-hire-deals-au"),
    ("JUCY Australia", "https://www.jucy.com/au/en/deals/limited-time-deals"),
    ("Britz Australia", "https://www.britz.com/au/en/campervan-hire-deals/campervan-relocations"),
    ("maui Australia", "https://www.maui-rentals.com/motorhome-hire-australia/deals/relocation-vehicles"),
    ("Autosleepers Campervan Hire", "https://www.autosleepers.com.au/relocations"),
]

# Menuer og footere ændrer sig hele tiden uden at betyde noget. Vi kigger kun på afsnit der
# handler om flytninger, og vi fjerner tal der ligner besøgstællere og tidsstempler.
KEYWORDS = re.compile(r"relocat|one[- ]way|\$1\b|one way", re.I)
# Kun en rigtig rute tæller. «Brisbane til Sydney» eller «Brisbane - Sydney», ikke en
# navigationsmenu der bare remser byer op ("Brisbane Cairns Gold Coast Melbourne Sydney").
ROUTE = re.compile(r"brisbane\s*(?:to|til|–|—|-|→|->|>)\s*sydney", re.I)
CITIES = re.compile(r"adelaide|alice springs|brisbane|broome|cairns|darwin|hobart|melbourne|perth|sydney|gold coast", re.I)


def visible(html):
    t = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    t = H.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"\s+", " ", t).strip()


def relevant(text):
    """De sætninger der handler om flytninger. Det er dem vi tager fingeraftryk af.

    Sætninger med en hel stribe bynavne er næsten altid en menu eller en footer, og de
    ændrer sig af sig selv. Dem smider vi væk, så fingeraftrykket kun dækker rigtigt indhold.
    """
    parts = []
    for s in re.split(r"(?<=[.!?])\s+|\n", text):
        s = s.strip()
        if not KEYWORDS.search(s):
            continue
        if len(set(m.group(0).lower() for m in CITIES.finditer(s))) >= 5:
            continue  # bymenu, ikke indhold
        parts.append(s)
    joined = " ".join(parts)
    joined = re.sub(r"\b\d{1,2}:\d{2}\b|\b\d{4}-\d{2}-\d{2}\b", "", joined)  # ur og datoer
    return joined[:8000]


def check(now, previous):
    """Returnér (statusliste, nyt fingeraftryks-kort, log-linjer)."""
    state, notes, out = {}, [], []
    for name, url in PAGES:
        entry = {"name": name, "url": url, "checkedAt": now}
        try:
            text = visible(fetch(url, timeout=45).decode("utf-8", "replace"))
        except Exception as e:
            entry.update({"status": "kunne ikke læses", "detail": type(e).__name__})
            out.append(entry)
            continue
        rel = relevant(text)
        fp = hashlib.sha256(rel.encode("utf-8")).hexdigest()[:16]
        state[url] = fp
        route_hit = ROUTE.search(rel)
        was = (previous or {}).get(url)
        changed = bool(was) and was != fp

        if route_hit:
            entry.update({"status": "nævner Brisbane og Sydney",
                          "detail": re.sub(r"\s+", " ", route_hit.group(0))[:220]})
            notes.append(f"{name} nævner nu Brisbane og Sydney på sin flytningsside — tjek den selv")
        elif changed:
            entry.update({"status": "ændret", "detail": "Teksten om flytninger er ændret siden sidste tjek."})
            notes.append(f"{name} har ændret sin flytningsside")
        elif was:
            entry.update({"status": "uændret", "detail": "Ingen ændring siden sidste tjek."})
        else:
            entry.update({"status": "aflæst", "detail": "Første aflæsning, gemt som udgangspunkt."})
        out.append(entry)
    return out, state, notes
