"""Midlertidig: kan en rigtig browser på GitHubs server nå DriveNow?"""
import json
from playwright.sync_api import sync_playwright

URL = "https://www.drivenow.com.au/onewayrentals.jspc#/relocations/AU"
API = "https://www.drivenow.com.au/rest/relocation-deal/list/AU"

with sync_playwright() as pw:
    b = pw.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
    ctx = b.new_context(
        user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
        locale="en-AU", timezone_id="Australia/Brisbane", viewport={"width": 1400, "height": 1000})
    p = ctx.new_page()
    grabbed = {}
    def on_resp(r):
        if "relocation-deal/list" in r.url:
            try:
                grabbed["data"] = r.json()
            except Exception:
                pass
    p.on("response", on_resp)
    r = p.goto(URL, wait_until="domcontentloaded", timeout=90000)
    print("første svar:", r.status if r else "?")
    for i in range(14):
        p.wait_for_timeout(2500)
        t = p.inner_text("body")
        if "Just a moment" not in t and "security verification" not in t:
            print(f"kom igennem efter ca. {(i+1)*2.5:.0f} sekunder")
            break
    else:
        print("stadig blokeret efter 35 sekunder")
    t = p.inner_text("body")
    print("blokeret:", "Just a moment" in t, "| tekstlængde:", len(t))
    if "data" not in grabbed:
        try:
            grabbed["data"] = p.evaluate(
                "async u => (await fetch(u, {headers:{'X-Requested-With':'XMLHttpRequest'}})).json()", API)
        except Exception as e:
            print("fetch i browseren fejlede:", str(e)[:200])
    d = grabbed.get("data")
    if d:
        deals = d.get("deals") or []
        print(f"HENTEDE {len(deals)} tilbud")
        for x in deals[:3]:
            print("  ", x.get("fromLocation"), "->", x.get("toLocation"), x.get("dateAvail"), x.get("price"))
    else:
        print("ingen data")
    b.close()
