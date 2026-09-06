"""Midlertidig: kan en rigtig browser på GitHubs server nå DriveNows liste?"""
import json
from playwright.sync_api import sync_playwright

BASE = "https://www.drivenow.com.au/onewayrentals.jspc"
API = "https://www.drivenow.com.au/rest/relocation-deal/list/AU"

with sync_playwright() as pw:
    b = pw.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
    ctx = b.new_context(
        user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
        locale="en-AU", timezone_id="Australia/Brisbane", viewport={"width": 1400, "height": 1200})
    p = ctx.new_page()
    seen, grabbed = [], {}

    def on_resp(r):
        seen.append((r.status, r.url[:120]))
        if "relocation-deal/list" in r.url:
            try:
                grabbed["data"] = r.json()
            except Exception as e:
                grabbed["err"] = str(e)[:120]
    p.on("response", on_resp)

    p.goto(BASE, wait_until="domcontentloaded", timeout=90000)
    for i in range(16):
        p.wait_for_timeout(2500)
        if "Just a moment" not in p.inner_text("body"):
            print(f"forbi spærringen efter ca. {(i+1)*2.5:.0f} sek")
            break
    try:
        p.wait_for_load_state("networkidle", timeout=45000)
    except Exception:
        pass
    p.goto(BASE + "#/relocations/AU", wait_until="domcontentloaded", timeout=60000)
    p.wait_for_timeout(12000)
    print("tekstlængde:", len(p.inner_text("body")))
    print("svar siden hentede:")
    for s, u in seen[-25:]:
        print(f"   {s} {u}")
    if "data" not in grabbed:
        try:
            grabbed["data"] = p.evaluate(
                """async u => { const r = await fetch(u, {headers:{'X-Requested-With':'XMLHttpRequest','Accept':'application/json'}, credentials:'include'});
                                return r.ok ? await r.json() : {__status: r.status}; }""", API)
        except Exception as e:
            print("fetch i browseren fejlede:", str(e)[:160])
    d = grabbed.get("data")
    if isinstance(d, dict) and d.get("deals") is not None:
        print(f"HENTEDE {len(d['deals'])} tilbud")
        for x in d["deals"][:3]:
            print("   ", x.get("fromLocation"), "->", x.get("toLocation"), x.get("dateAvail"), x.get("price"))
    else:
        print("ingen data:", json.dumps(d)[:200] if d else None, grabbed.get("err"))
    b.close()
