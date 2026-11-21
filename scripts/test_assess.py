"""Små test af assess() og direction(). Kør med: python3 scripts/test_assess.py"""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import assess, direction, ends, is_dk_city, locate, to_dkk, UNKNOWN

W = json.loads((pathlib.Path(__file__).resolve().parent.parent / "data.json").read_text(encoding="utf-8"))["window"]
IN = ("2026-12-28", "2026-12-30")


def fit(*a, **kw):
    return assess(W, *a, **kw)


# Retning
assert direction(W, "DK", "DE") == "fra-dk"
assert direction(W, "SE", "DK") == "til-dk"
assert direction(W, "DK", "DK") == "indenrigs"
assert direction(W, "FR", "ES", "Paris", "Madrid") is None
assert is_dk_city("Kastrup") and is_dk_city("Köpenhamn") and is_dk_city("København V")
assert not is_dk_city("Göteborg")

# Zonen: højst 300 km i luftlinje fra Danmark (uden Bornholm)
assert W["zoneKm"] == 300 and "nearCities" not in W
km = lambda n, c=None: (locate(n, c) or {}).get("km")
IN_ZONE = ["Flensburg", "Kiel", "Lübeck", "Hamburg", "Rostock", "Bremen", "Hannover", "Berlin", "Szczecin",
           "Malmö", "Göteborg", "Jönköping", "Kalmar", "Oslo", "Kristiansand", "Stavanger", "Groningen"]
OUT = ["Amsterdam", "Münster", "Leipzig", "Stockholm", "Bergen", "Gdańsk"]
for n in IN_ZONE:
    assert km(n) is not None and 0 < km(n) <= 300, (n, locate(n))
for n in OUT:
    assert km(n) is not None and km(n) > 300, (n, locate(n))
# Linköping ligger 288 km fra Læsø i luftlinje, altså lige inden for (Karstens liste gættede på uden for).
assert 280 <= km("Linköping") <= 300, locate("Linköping")
assert 130 <= km("Hamburg") <= 150 and locate("Hamborg")["name"] == "Hamborg"
assert km("Rønne") == 0 and locate("Rønne")["country"] == "DK"          # Bornholm er stadig Danmark

# Fælder: hele ord, navnesammenfald, fremmede navneformer
assert locate("Kielce")["country"] == "PL" and km("Kielce") > 300        # ikke Kiel
assert locate("Lunde") is None or locate("Lunde")["name"] != "Lund"      # ikke Lund
assert km("Bergen") > 300 and km("Bergen", "NO") > 300                   # Bergen i Norge
assert km("Bergen", "DE") <= 300 and km("Bergen auf Rügen") <= 300       # Bergen i Tyskland
assert km("Essen") > 300 and km("Essen (Oldenburg)") <= 300
assert km("Frankfurt") > 300 and km("Frankfurt (Oder)") <= 300
for n in ["Köpenhamn", "Kopenhagen", "Copenhague", "Copenhagen Airport", "København H"]:
    assert locate(n)["country"] == "DK", n
for n, want in [("Göteborg Landvetter", "Göteborg"), ("Gothenburg", "Göteborg"), ("Malmö Sturup", "Malmö"),
                ("Sandefjord Torp", "Sandefjord"), ("Oslo Gardermoen", "Oslo"), ("BER", "Berlin"),
                ("Hamburg Flughafen", "Hamborg"), ("Hamborg", "Hamborg"), ("Lübeck Hbf", "Lübeck")]:
    assert locate(n)["name"] == want, (n, locate(n))
assert locate("Paris", "FR")["km"] is None
assert locate("Straßburg")["country"] == "FR"                            # ikke den lille by Burg
assert locate("Genf-Pays de Gex (Frankreich)") is None
assert locate("Strängnäs Strängnäs")["name"] == "Strängnäs"              # by og område med samme navn                   # del af et ukendt navn tæller ikke                               # land uden for zonen

# Et ukendt navn stiller aldrig tilbuddet bedre og bliver skrevet ned
assert locate("Xyzzyville") is None and "Xyzzyville" in UNKNOWN
assert ends(W, "Xyzzyville", "Paris")["direction"] is None
assert ends(W, "Xyzzyville", "Hamburg")["direction"] == "zone"

# Begge retninger og begge ender i zonen
e = ends(W, "Antwerpen", "Hamburg")
assert e["direction"] == "zone" and e["zone"]["text"] == "Hamborg, ca. 140 km fra Danmark", e
assert ends(W, "Hamburg", "Lisboa")["direction"] == "zone"
e = ends(W, "Malmö", "Hamburg")
assert e["direction"] == "zone" and e["zone"]["name"] == "Malmö", e      # den nærmeste vises
assert ends(W, "Copenhagen", "Hamburg", "DK", "DE")["direction"] == "fra-dk"
assert ends(W, "Berlin", "Köpenhamn")["direction"] == "til-dk"
assert ends(W, "Aarhus", "København")["direction"] == "indenrigs"
assert ends(W, "Amsterdam", "Paris")["direction"] is None
assert ends(W, "Bergen", "Stockholm", "NO", "SE")["direction"] is None

# Begge retninger passer
assert fit(*IN, 3, 1, "EUR", "fra-dk", min_age=21)["fit"] == "passer"
assert fit(*IN, 3, 1, "EUR", "til-dk", min_age=21)["fit"] == "passer"

# Zonen passer, begge retninger. Indenrigs giver stadig tæt på
z = ends(W, "Hamburg", "Lisboa")
r = fit(*IN, 3, 1, "EUR", "zone", min_age=18, zone=z["zone"])
assert r["fit"] == "passer" and "Hamborg, ca. 140 km" in r["fitReason"] and r["zonePlace"], r
assert fit(*IN, 3, 1, "EUR", "zone", min_age=18, zone=ends(W, "Lisboa", "Kiel")["zone"])["fit"] == "passer"
assert fit(*IN, 3, 1, "EUR", "indenrigs", min_age=18)["fit"] == "naesten"

# Dato ved siden af: op til 5 dage giver tæt på, mere giver nej
assert fit("2027-01-06", "2027-01-08", 3, 1, "EUR", "fra-dk", min_age=18)["fit"] == "naesten"
assert fit("2026-12-15", "2026-12-21", 3, 1, "EUR", "til-dk", min_age=18)["fit"] == "naesten"
assert fit("2027-01-12", "2027-01-14", 3, 1, "EUR", "fra-dk", min_age=18)["fit"] == "nej"
assert fit("2027-01-06", "2027-01-08", 3, 1, "EUR", "zone", min_age=18)["fit"] == "naesten"
# To afvigelser på én gang (indenrigs og dato ved siden af) er nej
assert fit("2027-01-05", "2027-01-05", 7, 18, "EUR", "indenrigs", min_age=18)["fit"] == "nej"

# Pris over loftet (250 kr./dag): 40 EUR er ca. 299 kr.
r = fit(*IN, 3, 40, "EUR", "fra-dk", min_age=18)
assert r["fit"] == "nej" and "over loftet" in r["fitReason"], r

# Valutaomregning
assert to_dkk(W, 100, "EUR") == 747.42
assert to_dkk(W, 100, "SEK") == 67.05
assert fit(*IN, 3, 300, "SEK", "til-dk", min_age=18)["fit"] == "passer"   # ca. 201 kr.
assert fit(*IN, 3, 30, "GBP", "til-dk", min_age=18)["fit"] == "nej"        # ca. 268 kr.
assert round(fit(*IN, 3, 1, "EUR", "fra-dk", min_age=18)["pricePerDayDKK"], 2) == 7.47

# Aldersgrænse mod window.maxMinAge
assert W["maxMinAge"] == 22
assert fit(*IN, 3, 1, "EUR", "fra-dk", min_age=21)["fit"] == "passer"
assert fit(*IN, 3, 1, "EUR", "fra-dk", min_age=22)["fit"] == "passer"
r = fit(*IN, 3, 1, "EUR", "fra-dk", min_age=23)
assert r["fit"] == "nej" and r["fitReason"] == "Kræver fører på mindst 23 år.", r
r = fit(*IN, 3, 1, "EUR", "zone", min_age=25)
assert r["fit"] == "nej" and "mindst 25 år" in r["fitReason"], r
r = fit(*IN, 3, 1, "EUR", "fra-dk", min_age=None)
assert r["fit"] == "passer" and "Tjek aldersgrænsen" in r["fitReason"], r
r = fit(*IN, 3, 1, "EUR", "zone", min_age=None)
assert r["fit"] == "passer" and "Tjek aldersgrænsen" in r["fitReason"], r
assert "Tjek aldersgrænsen" not in fit(*IN, 3, 1, "EUR", "fra-dk", min_age=21)["fitReason"]
assert "mindst 3 år" in fit(*IN, 1, 0, "SEK", "fra-dk", min_age=21, license_years=3)["fitReason"]

# Noget der ikke kan bookes af en anden grund
assert fit(*IN, 1, 0, "SEK", "zone", min_age=18, blocker="Kræver svensk personnummer.")["fit"] == "nej"

print("Alle test bestod.")
