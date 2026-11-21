#!/usr/bin/env python3
"""Bygger scripts/places.json: stednavne i Europa med afstanden til Danmark.

Køres kun, når listen skal bygges igen. Trackeren slår op i den færdige fil og kalder aldrig
en geokodningstjeneste.

Kilder (hent dem selv til en tom mappe og giv stierne som argumenter):
- GeoNames cities1000 (alle steder med mindst 1.000 indbyggere), CC BY 4.0:
  https://download.geonames.org/export/dump/cities1000.zip
- Natural Earth, lande i skala 1:10m (public domain):
  https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_0_countries.geojson

Kør:  python3 -I scripts/build_places.py cities1000.txt ne_10m_admin_0_countries.geojson scripts/places.json

Afstanden er luftlinje til det nærmeste punkt på Danmarks kyst eller grænse. Bornholm tæller
ikke med som udgangspunkt (ellers kommer Gdańsk med). Færøerne og Grønland er egne lande hos
Natural Earth og indgår ikke. Et sted i Danmark (også på Bornholm) har afstanden 0.
"""
import json, math, re, sys, unicodedata

ZONE_KM = 300
EUROPE = set("AD AL AT AX BA BE BG BY CH CY CZ DE DK EE ES FI FO FR GB GG GI GR HR HU IE IM IS IT JE "
             "LI LT LU LV MC MD ME MK MT NL NO PL PT RO RS SE SI SK SM UA VA XK".split())
BORNHOLM_LON = 14.5           # polygoner helt øst for denne længde er Bornholm og Ertholmene
BIG_OUT = 250000              # steder uden for zonen med så mange indbyggere får også fremmede navneformer
BIG_IN = 15000                # det samme for steder i zonen
NAME_POP_OUT = 40000          # mindre steder uden for zonen kommer kun med, hvis navnet støder sammen med zonen
# Dansk navn på kortene, hvor det er almindeligt.
DANISH = {"Hamburg": "Hamborg", "Flensburg": "Flensborg", "Gothenburg": "Göteborg", "Copenhagen": "København",
          "Szczecin": "Stettin", "Schleswig": "Slesvig", "Hanover": "Hannover", "Århus": "Aarhus"}
# Lufthavne og fremmede former, som GeoNames ikke har som navn på byen. (alias, by, land)
ALIASES = [("kastrup", "Copenhagen", "DK"), ("kobenhavns-lufthavn", "Copenhagen", "DK"),
           ("sturup", "Malmö", "SE"), ("malmo-sturup", "Malmö", "SE"), ("torp", "Sandefjord", "NO"),
           ("gardermoen", "Oslo", "NO"), ("oslo-gardermoen", "Oslo", "NO"), ("fuhlsbuttel", "Hamburg", "DE"),
           ("schonefeld", "Berlin", "DE"), ("berlin-brandenburg", "Berlin", "DE"), ("tegel", "Berlin", "DE"),
           ("vastra-frolunda", "Gothenburg", "SE"), ("hamburg-harburg", "Hamburg", "DE"),
           ("essen-oldenburg", "Essen", "DE#52.7228"), ("kjevik", "Kristiansand", "NO"),
           ("fornebu", "Oslo", "NO"), ("rygge", "Moss", "NO")]
# Lufthavnskoder, som kun genkendes med store bogstaver i kildens tekst.
CODES = {"CPH": ("Copenhagen", "DK"), "BLL": ("Billund", "DK"), "AAR": ("Århus", "DK"), "AAL": ("Aalborg", "DK"),
         "HAM": ("Hamburg", "DE"), "BER": ("Berlin", "DE"), "BRE": ("Bremen", "DE"), "HAJ": ("Hannover", "DE"),
         "LBC": ("Lübeck", "DE"), "RLG": ("Rostock", "DE"), "KEL": ("Kiel", "DE"), "MMX": ("Malmö", "SE"),
         "GOT": ("Gothenburg", "SE"), "OSL": ("Oslo", "NO"), "TRF": ("Sandefjord", "NO"), "SZZ": ("Szczecin", "PL"),
         "GRQ": ("Groningen", "NL"), "KRS": ("Kristiansand", "NO"), "SVG": ("Stavanger", "NO")}


def slug(s):
    s = unicodedata.normalize("NFKD", (s or "").lower().replace("ø", "o").replace("æ", "ae").replace("å", "a")
                              .replace("ß", "ss").replace("ł", "l").replace("đ", "d"))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def latin(s):
    return bool(s) and all(ord(c) < 0x250 or unicodedata.combining(c) for c in s) and not any(ch.isdigit() for ch in s)


def denmark_segments(geojson_path):
    g = json.load(open(geojson_path, encoding="utf-8"))
    segs = []
    for f in g["features"]:
        if f["properties"]["ADMIN"] != "Denmark":
            continue
        geom = f["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for poly in polys:
            ring = poly[0]
            if min(p[0] for p in ring) > BORNHOLM_LON:
                continue
            for r in poly:
                segs += [(r[i][1], r[i][0], r[i + 1][1], r[i + 1][0]) for i in range(len(r) - 1)]
    return segs


def dist_km(lat, lon, segs):
    """Luftlinje i km fra (lat, lon) til nærmeste punkt på segmenterne (lokal projektion, haversine til sidst)."""
    R = 6371.0
    kx, ky = R * math.radians(1) * math.cos(math.radians(lat)), R * math.radians(1)
    best, bp = None, None
    for a_lat, a_lon, b_lat, b_lon in segs:
        ax, ay = (a_lon - lon) * kx, (a_lat - lat) * ky
        bx, by = (b_lon - lon) * kx, (b_lat - lat) * ky
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy
        t = 0.0 if L == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / L))
        px, py = ax + t * dx, ay + t * dy
        dd = px * px + py * py
        if best is None or dd < best:
            best, bp = dd, (lat + py / ky, lon + px / kx)
    p1, p2 = math.radians(lat), math.radians(bp[0])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(bp[1] - lon) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def main(cities_path, geojson_path, out_path):
    segs = denmark_segments(geojson_path)
    coarse = segs[::15]
    rows = []
    for line in open(cities_path, encoding="utf-8"):
        c = line.rstrip("\n").split("\t")
        if c[8] not in EUROPE or c[7] == "PPLX":
            continue
        lat, lon, pop = float(c[4]), float(c[5]), int(c[14] or 0)
        if c[8] == "DK":
            km = 0
        elif 49 < lat < 64 and 2 < lon < 23:
            rough = dist_km(lat, lon, coarse)
            km = round(dist_km(lat, lon, segs)) if rough < ZONE_KM + 60 else round(rough)
        else:
            km = None   # langt væk: uden for zonen, afstanden regnes ikke ud
        names = {c[1], c[2]}
        alts = {a for a in c[3].split(",") if latin(a) and len(a) <= 30 and not re.fullmatch(r"[A-Z]{2,4}", a)}
        big = pop >= (BIG_IN if km is not None and km <= ZONE_KM else BIG_OUT)
        # keys: navne, der gemmes for stedet. all: alle navneformer, så det største sted med et navn
        # vinder, også når navnet kun er en fremmed form for et stort sted.
        rows.append({"name": c[1], "cc": c[8], "pop": pop, "km": km, "lat": lat,
                     "keys": {slug(n) for n in (names | alts if big else names)} - {""},
                     "all": {slug(n) for n in names | alts} - {""}})
    rows.sort(key=lambda r: -r["pop"])     # største først, så det største sted med et navn vinder

    def find(name, cc):
        if "#" in cc:
            cc, lat = cc.split("#")
            return next(i for i, r in enumerate(rows) if r["name"] == name and r["cc"] == cc and abs(r["lat"] - float(lat)) < 0.01)
        return next(i for i, r in enumerate(rows) if r["name"] == name and r["cc"] == cc)

    wanted = {k for r in rows for k in r["keys"]}
    winner, per_cc, zone_named = {}, {}, set()
    for i, r in enumerate(rows):
        for k in r["all"] & wanted:
            winner.setdefault(k, i)
            per_cc.setdefault((k, r["cc"]), i)
    for alias, name, cc in ALIASES:
        i = find(name, cc)
        winner[alias] = i
        per_cc[(alias, rows[i]["cc"])] = i
    in_zone = lambda i: rows[i]["km"] is not None and rows[i]["km"] <= ZONE_KM
    zone_cc = sorted({r["cc"] for i, r in enumerate(rows) if in_zone(i)})
    for i, r in enumerate(rows):
        if in_zone(i):
            zone_named |= r["keys"]

    keep_names = {}
    for k, i in winner.items():
        touches_zone = in_zone(i) or k in zone_named
        if touches_zone or rows[i]["pop"] >= NAME_POP_OUT or rows[i]["cc"] in ("SE", "NO"):
            keep_names[k] = i
    by_cc = {}
    for (k, cc), i in per_cc.items():
        if cc in zone_cc and k in keep_names and keep_names[k] != i:
            by_cc.setdefault(cc, {})[k] = i
    used = sorted(set(keep_names.values()) | {i for d in by_cc.values() for i in d.values()}
                  | {find(n, cc) for n, cc in CODES.values()})
    new = {old: n for n, old in enumerate(used)}
    places = [[DANISH.get(rows[i]["name"], rows[i]["name"]), rows[i]["cc"], rows[i]["km"]] for i in used]
    out = {
        "about": ("Stednavne i Europa med luftlinje i km til nærmeste punkt i Danmark uden Bornholm "
                  "(0 = i Danmark, null = langt væk). Bygget af scripts/build_places.py."),
        "sources": ["GeoNames cities1000, CC BY 4.0, https://www.geonames.org/",
                    "Natural Earth 1:10m lande, public domain, https://www.naturalearthdata.com/"],
        "zoneKm": ZONE_KM, "zoneCountries": zone_cc,
        "bigFrom": next((n for n, i in enumerate(used) if rows[i]["pop"] < BIG_IN), len(used)),
        "places": places,
        "names": {k: new[i] for k, i in sorted(keep_names.items())},
        "byCountry": {cc: {k: new[i] for k, i in sorted(d.items())} for cc, d in sorted(by_cc.items())},
        "codes": {code: new[find(n, cc)] for code, (n, cc) in sorted(CODES.items())},
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    print(f"{len(places)} steder, {len(out['names'])} navne, zonelande {zone_cc}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
