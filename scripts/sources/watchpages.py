"""Holder øje med sider, der kan læses, men som ikke har en liste, robotten kan aflæse.

Modulet gemmer et fingeraftryk af den relevante del af hver side og siger til i loggen, når
teksten ændrer sig, eller når en dansk by pludselig står på en side med flytninger.
Det giver ingen tilbud på forsiden, kun en linje i loggen og en status på kortet.
"""
import hashlib, html as H, re, sys, time, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from source_reader import SourceReader

LABEL = "Sideovervågning"

# (navn, adresse, nøgleord for den relevante tekst, kig efter Danmark, meld ændringer)
PAGES = [
    ("Just go, flyttetilbud", "https://www.justgo.uk.com/one-way-relocate.html",
     r"relocation|pick.up|drop.off|available|per night|germany|hamburg|berlin|oslo", True, True),
    ("DriiveMe, første side af listen", "https://www.driiveme.com/en-GB/component/transport-list?page=1",
     r"valid between|departure|arrival", True, False),
    ("returbil.no", "https://returbil.no/", r"retur|tilbake|bil", True, True),
    ("Europcar Danmark, gebyrer", "https://www.europcar.dk/info/en/prices-and-fees",
     r"one-way|cross border|young driver|winter|bridge", False, True),
]

DK = re.compile(r"københavn|kobenhavn|copenhagen|kopenhagen|köpenhamn|kastrup|aarhus|billund|"
                r"odense|aalborg|esbjerg|denmark|dänemark|danmark", re.I)


def visible(html):
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    t = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    t = H.unescape(re.sub(r"<[^>]+>", "\n", t))
    return re.sub(r"[ \t]+", " ", t)


def relevant(text, keywords):
    kw = re.compile(keywords, re.I)
    parts = [s.strip() for s in re.split(r"\n+", text) if s.strip() and kw.search(s)]
    joined = " ".join(parts)
    joined = re.sub(r"\b\d{1,2}:\d{2}\b|\b\d{4}-\d{2}-\d{2}\b", "", joined)  # ur og datoer
    return joined[:8000]


def check(now, previous):
    """Returnér (statusliste, nyt fingeraftryks-kort, log-linjer)."""
    state, notes, out = {}, [], []
    for i, (name, url, keywords, look_dk, report_change) in enumerate(PAGES):
        if i:
            time.sleep(1.5)
        entry = {"name": name, "url": url, "checkedAt": now}
        try:
            text = visible(SourceReader().read(url))
        except Exception as e:
            entry.update({"status": "kunne ikke læses", "detail": type(e).__name__})
            if (previous or {}).get(url):
                state[url] = previous[url]
            out.append(entry)
            continue
        rel = relevant(text, keywords)
        fp = hashlib.sha256(rel.encode("utf-8")).hexdigest()[:16]
        state[url] = fp
        hit = DK.search(rel) if look_dk else None
        was = (previous or {}).get(url)
        changed = bool(was) and was != fp
        if hit:
            ctx = rel[max(0, hit.start() - 80):hit.end() + 80]
            entry.update({"status": "nævner Danmark", "detail": re.sub(r"\s+", " ", ctx)[:220]})
            notes.append(f"{name} nævner nu en dansk by. Tjek siden selv")
        elif changed and report_change:
            entry.update({"status": "ændret", "detail": "Teksten er ændret siden sidste tjek."})
            notes.append(f"{name} har ændret sin side")
        elif was:
            entry.update({"status": "uændret" if report_change else "aflæst",
                          "detail": "Ingen ændring siden sidste tjek." if report_change
                          else "Listen skifter hele tiden. Robotten melder kun, hvis en dansk by dukker op."})
        else:
            entry.update({"status": "aflæst", "detail": "Første aflæsning, gemt som udgangspunkt."})
        out.append(entry)
    return out, state, notes
