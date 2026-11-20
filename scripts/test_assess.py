"""Små test af assess() og direction(). Kør med: python3 scripts/test_assess.py"""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import assess, direction, is_dk_city, near_city, to_dkk

W = json.loads((pathlib.Path(__file__).resolve().parent.parent / "data.json").read_text(encoding="utf-8"))["window"]
IN = ("2026-12-28", "2026-12-30")


def fit(*a, **kw):
    return assess(W, *a, **kw)


# Retning
assert direction(W, "DK", "DE") == "fra-dk"
assert direction(W, "SE", "DK") == "til-dk"
assert direction(W, "DK", "DK") == "indenrigs"
assert direction(W, "BE", "DE", "Antwerpen", "Hamburg") == "naer"
assert direction(W, "SE", "SE", "Uppsala", "Malmö/Sturup") == "naer"
assert direction(W, "FR", "ES", "Paris", "Madrid") is None
assert is_dk_city("Kastrup") and is_dk_city("Köpenhamn") and is_dk_city("København V")
assert not is_dk_city("Göteborg")
assert near_city(W, "Lübeck") == "Lübeck" and near_city(W, "Hamburg Flughafen") == "Hamburg"

# Begge retninger passer
assert fit(*IN, 3, 1, "EUR", "fra-dk", min_age=21)["fit"] == "passer"
assert fit(*IN, 3, 1, "EUR", "til-dk", min_age=21)["fit"] == "passer"

# Nærby og indenrigs giver tæt på
assert fit(*IN, 3, 1, "EUR", "naer", min_age=18)["fit"] == "naesten"
assert fit(*IN, 3, 1, "EUR", "indenrigs", min_age=18)["fit"] == "naesten"

# Dato ved siden af: op til 5 dage giver tæt på, mere giver nej
assert fit("2027-01-06", "2027-01-08", 3, 1, "EUR", "fra-dk", min_age=18)["fit"] == "naesten"
assert fit("2026-12-15", "2026-12-21", 3, 1, "EUR", "til-dk", min_age=18)["fit"] == "naesten"
assert fit("2027-01-12", "2027-01-14", 3, 1, "EUR", "fra-dk", min_age=18)["fit"] == "nej"
# To afvigelser på én gang (nærby og dato ved siden af) er nej
assert fit("2027-01-05", "2027-01-05", 7, 18, "EUR", "naer", min_age=18)["fit"] == "nej"

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
r = fit(*IN, 3, 1, "EUR", "naer", min_age=25)
assert r["fit"] == "nej" and "mindst 25 år" in r["fitReason"], r
r = fit(*IN, 3, 1, "EUR", "fra-dk", min_age=None)
assert r["fit"] == "passer" and "Tjek aldersgrænsen" in r["fitReason"], r
assert "Tjek aldersgrænsen" not in fit(*IN, 3, 1, "EUR", "fra-dk", min_age=21)["fitReason"]
assert "mindst 3 år" in fit(*IN, 1, 0, "SEK", "fra-dk", min_age=21, license_years=3)["fitReason"]

# Noget der ikke kan bookes af en anden grund
assert fit(*IN, 1, 0, "SEK", "naer", min_age=18, blocker="Kræver svensk personnummer.")["fit"] == "nej"

print("Alle test bestod.")
