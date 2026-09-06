#!/usr/bin/env python3
"""Kører alle automatiske kilder og opdaterer data.json.

Manuelle tilbud (uden `source`-felt) rører vi ikke. Fejler en kilde, beholder vi dens
gamle opslag og skriver fejlen i loggen, så Karsten kan se at den ikke blev tjekket.
"""
import importlib, json, sys, pathlib, traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import ROOT, now_iso

SOURCES = ["imoova", "transfercar", "coseats", "drivenow", "simba", "autosleepers"]

# Kilder der afviser GitHubs servere (Cloudflare blokerer datacenter-adresser), men som virker fint
# fra en almindelig internetforbindelse. De må fejle uden at det tæller som en rigtig fejl.
RESIDENTIAL_ONLY = {"drivenow"}


def main():
    path = ROOT / "data.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    w = data["window"]
    now = now_iso()

    fresh, ok_sources, failures, skipped, counts = [], set(), [], [], {}
    for name in SOURCES:
        mod = importlib.import_module(f"sources.{name}")
        try:
            deals = mod.fetch_deals(w, now)
            fresh += deals
            ok_sources.add(mod.SOURCE)
            counts[mod.LABEL] = len(deals)
        except Exception as e:
            if name in RESIDENTIAL_ONLY:
                skipped.append(mod.LABEL)
                print(f"{mod.LABEL} sprunget over: afviser denne maskines IP-adresse ({type(e).__name__}).")
            else:
                failures.append(f"{mod.LABEL} kunne ikke læses ({type(e).__name__}: {str(e)[:120]})")
                traceback.print_exc()
        # Status på kildekortet
        for s in data.get("sources", []):
            if s.get("autoKey") == name:
                s["lastCheck"] = {"ts": now, "ok": mod.SOURCE in ok_sources,
                                  "count": counts.get(mod.LABEL),
                                  "skipped": mod.LABEL in skipped}

    old = {x["id"]: x for x in data["deals"] if x.get("source") in ok_sources}
    kept = [x for x in data["deals"] if x.get("source") not in ok_sources]
    data["deals"] = kept + fresh

    added = [x for x in fresh if x["id"] not in old]
    gone = [x for x in old.values() if x["id"] not in {y["id"] for y in fresh}]
    changed = [x for x in fresh if x["id"] in old and (
        x["availability"]["from"] != old[x["id"]]["availability"]["from"]
        or x["availability"]["to"] != old[x["id"]]["availability"]["to"]
        or x["pricePerDay"] != old[x["id"]]["pricePerDay"]
        or x["fit"] != old[x["id"]]["fit"])]

    bits = []
    quiet = 0
    for x in added:
        if x["fit"] == "nej":
            quiet += 1          # nye opslag uden for vinduet nævnes kun som et tal
            continue
        tag = "NYT: " if x["fit"] == "passer" else "tæt på: "
        bits.append(f"{tag}{x['platform']}: {x['vehicle']} ({x['route']}, {x['days']} dage, {x['price']}, "
                    f"afhentning {x['availability']['from']}–{x['availability']['to']})")
    if quiet:
        bits.append(f"{quiet} nye opslag uden for dit vindue")
    for x in changed:
        bits.append(f"ændret: {x['platform']}: {x['vehicle']} — nu {x['fit']}, "
                    f"{x['availability']['from']}–{x['availability']['to']}")
    for x in gone:
        bits.append(f"væk: {x['platform']}: {x['vehicle']} ({x['route']})")
    bits += [f"FEJL: {f}" for f in failures]
    if skipped:
        bits.append(", ".join(skipped) + " kunne ikke læses herfra (kræver almindelig internetforbindelse)")

    n_pass = sum(1 for x in data["deals"] if x["fit"] == "passer")
    head = "Automatisk tjek (" + ", ".join(f"{k} {v} opslag" for k, v in counts.items()) + "): "
    summary = head + (" · ".join(bits) if bits else "ingen ændringer.")

    log = data.setdefault("log", [])
    if bits or not log or not log[-1]["summary"].startswith("Automatisk tjek"):
        log.append({"ts": now, "summary": summary})
        data["log"] = log[-40:]
    else:
        log[-1] = {"ts": now, "summary": summary}

    data["updated"] = now
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(summary)
    print(f"{len(fresh)} automatiske opslag · {n_pass} passer i alt")
    return 1 if failures and not counts else 0


if __name__ == "__main__":
    sys.exit(main())
