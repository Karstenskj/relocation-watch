"""Midlertidig: afprøver forskellige måder at nå DriveNow fra GitHubs servere."""
import json, subprocess, urllib.request
U = "https://www.drivenow.com.au/rest/relocation-deal/list/AU"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

def show(tag, code, body):
    ok = ""
    if body and body.strip().startswith("{"):
        try:
            ok = f" deals={len(json.loads(body).get('deals') or [])}"
        except Exception:
            ok = " (ikke gyldig JSON)"
    print(f"{tag:28} {code} len={len(body or '')}{ok} :: {(body or '')[:90]!r}")

def try_urllib(tag, headers, url=U):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=45)
        show(tag, r.status, r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        show(tag, e.code, e.read().decode("utf-8", "replace"))
    except Exception as e:
        print(f"{tag:28} ERR {e}")

try_urllib("A minimal", {"User-Agent": UA, "Accept": "application/json",
                         "Referer": "https://www.drivenow.com.au/onewayrentals.jspc",
                         "X-Requested-With": "XMLHttpRequest"})
try_urllib("B fulde browser-headers", {
    "User-Agent": UA, "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-AU,en;q=0.9", "Accept-Encoding": "identity",
    "Referer": "https://www.drivenow.com.au/onewayrentals.jspc",
    "Origin": "https://www.drivenow.com.au", "X-Requested-With": "XMLHttpRequest",
    "sec-ch-ua": '"Chromium";v="126", "Google Chrome";v="126", "Not?A_Brand";v="24"',
    "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"macOS"',
    "Sec-Fetch-Site": "same-origin", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Dest": "empty",
    "Connection": "keep-alive"})
try_urllib("C forside først", {"User-Agent": UA, "Accept": "text/html"},
           url="https://www.drivenow.com.au/onewayrentals.jspc")
for tag, args in [
    ("D curl http1.1", ["curl", "-s", "--http1.1", "-A", UA, "-H", "Accept: application/json",
                        "-H", "Referer: https://www.drivenow.com.au/onewayrentals.jspc",
                        "-H", "X-Requested-With: XMLHttpRequest", "-w", "\n%{http_code}", U]),
    ("E curl m. cookiejar", ["curl", "-sL", "--http1.1", "-A", UA, "-c", "/tmp/cj", "-b", "/tmp/cj",
                             "-H", "Accept: text/html,application/xhtml+xml", "-o", "/dev/null",
                             "https://www.drivenow.com.au/onewayrentals.jspc", "-w", "%{http_code} then ",
                             "--next", "-s", "--http1.1", "-A", UA, "-b", "/tmp/cj", "-c", "/tmp/cj",
                             "-H", "Accept: application/json", "-H", "X-Requested-With: XMLHttpRequest",
                             "-H", "Referer: https://www.drivenow.com.au/onewayrentals.jspc", U, "-w", "\n%{http_code}"]),
    ("F jina-proxy", ["curl", "-s", "--max-time", "60", "-A", UA, "-w", "\n%{http_code}",
                      "https://r.jina.ai/" + U]),
]:
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=90).stdout
        body, _, code = out.rpartition("\n")
        show(tag, code.strip(), body)
    except Exception as e:
        print(f"{tag:28} ERR {e}")
