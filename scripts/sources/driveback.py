"""DriveBack (Sverige), læst fra den åbne JSON-liste på driveback.se/resor.json.

DriveBack er den eneste nordiske gratis-ordning, der har haft en tur fra Danmark
(Kastrup til Göteborg i dec. 2025). robots.txt har ingen regler. Turene er gratis, en tank
er med, og bilen skal afleveres samme dag. Alder og kørekortsår står pr. tur.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common import fetch_json, assess, build_deal, direction, is_dk_city, near_country, utc_to_cph_date

SOURCE = "driveback-auto"
LABEL = "DriveBack"
API = "https://www.driveback.se/resor.json"
LAST_OTHER = None


def place(st):
    loc = (st or {}).get("location") or {}
    city = loc.get("city") or st.get("area") or ""
    area = st.get("area") or ""
    name = city if not area or area == city else f"{area} ({city})"
    return name, city, area


def country(w, city, area):
    if is_dk_city(city) or is_dk_city(area):
        return "DK"
    return near_country(w, city) or near_country(w, area)


def fetch_deals(w, now):
    global LAST_OTHER
    trips = fetch_json(API)
    out, total = [], 0
    for t in trips:
        fname, fcity, farea = place(t.get("from_station") or {})
        fc = country(w, fcity, farea)
        pf, pt = utc_to_cph_date(t.get("first_pickup")), utc_to_cph_date(t.get("last_deliver"))
        v = t.get("vehicle") or {}
        for st in t.get("to_stations") or []:
            total += 1
            tname, tcity, tarea = place(st)
            tc = country(w, tcity, tarea)
            # Ukendt land er i praksis Sverige (eller Norge/Tyskland). Kun Danmark og nærbyer tæller.
            dirn = direction(w, fc or "SE", tc or "SE", f"{fcity} {farea}", f"{tcity} {tarea}")
            if not dirn:
                continue
            a = assess(w, pf, pt, 1, 0, "SEK", dirn, min_age=t.get("min_age"),
                       license_years=t.get("minimum_license_years"))
            ded, dep = t.get("deductible"), t.get("deposition")
            out.append(build_deal(
                w, now, a,
                id=f"driveback-{t['id']}-{st.get('id')}", source=SOURCE, provider="DriveBack",
                platform=LABEL, url=f"https://www.driveback.se/resor/{t['id']}/boka/{st.get('id')}",
                vehicle=" ".join(x for x in (v.get("car_model"), f"({v['car_size']})" if v.get("car_size") else "") if x) or "Bil",
                vehicleType="van" if (v.get("car_size") or "") in ("Skåpbil", "Lätt lastbil", "Minibuss") else "sedan",
                route=f"{fname} → {tname}", pickupCity=fcity, dropoffCity=tcity,
                pickupCountry=fc, dropoffCountry=tc, days=1,
                price="Gratis (0 kr.), en tank brændstof er med", pricePerDay=0, currency="SEK",
                totalCost="0 kr. + bro og færge (ikke bekræftet hvem der betaler)",
                fuel="en tank er med", minAge=t.get("min_age"),
                licenseYears=t.get("minimum_license_years"), youngDriverFee="ikke bekræftet",
                bond=(f"{dep} SEK" if dep else None),
                availability={"from": pf, "to": pt, "spaces": "1 bil",
                              "detail": (f"Afhentning tidligst {pf}, fremme senest {pt}. Bilen skal "
                                         f"afleveres samme dag, som den hentes."
                                         + (f" Selvrisiko {ded} SEK." if ded is not None else ""))},
                notes="Automatisk aflæst fra DriveBacks åbne liste. Booking kræver en gratis konto.",
            ))
    LAST_OTHER = total - len(out)
    return out


if __name__ == "__main__":
    import json
    w = json.load(open(pathlib.Path(__file__).resolve().parents[2] / "data.json"))["window"]
    for x in fetch_deals(w, "test"):
        print(x["fit"], "|", x["route"], "|", x["vehicle"], "|", x["fitReason"])
    print("andre:", LAST_OTHER)
