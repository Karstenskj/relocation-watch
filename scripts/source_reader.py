"""Skånsom læsning til nye kilder, med robotskontrol og et samlet kaldeloft."""
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from common import UA


def robot_rules(text):
    """Saml også gentagne grupper. Understøt robotsmønstrene * og $."""
    groups, agents, rules = [], [], []
    for line in text.splitlines():
        key, sep, value = line.split("#", 1)[0].partition(":")
        if not sep:
            continue
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            if rules:
                groups.append((agents, rules))
                agents, rules = [], []
            agents.append(value.lower())
        elif agents:
            rules.append((key, value))
    groups.append((agents, rules))
    specific = [(a, r) for a, r in groups if any(x != "*" and x in UA.lower() for x in a)]
    chosen = specific or [(a, r) for a, r in groups if "*" in a]
    return [rule for _, group in chosen for rule in group]


def robot_allows(rules, url):
    parts = urllib.parse.urlsplit(url)
    target = parts.path or "/"
    if parts.query:
        target += "?" + parts.query
    matches = []
    for key, value in rules:
        if key not in ("allow", "disallow") or not value:
            continue
        pattern = re.escape(value).replace(r"\*", ".*")
        if value.endswith("$"):
            pattern = pattern[:-2] + "$"
        if re.match(pattern, target):
            matches.append((len(value.replace("*", "").rstrip("$")), key == "allow"))
    return max(matches)[1] if matches else True


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class SourceReader:
    """Robots 404/410 tillader læsning. Andre fejl stopper kilden.

    Omdirigeringer følges ikke automatisk, så et nyt domæne aldrig læses uden
    robotskontrol. Alle HTTP-kald tæller, også robots og fejlede kald.
    """
    def __init__(self, max_calls=20, pause=1.5):
        self.max_calls, self.pause = max_calls, pause
        self.calls, self.policies, self.last = 0, {}, {}
        self.opener = urllib.request.build_opener(NoRedirect())

    def _raw(self, url, delay):
        if self.calls >= self.max_calls:
            raise RuntimeError("Kildens kaldeloft er nået")
        host = urllib.parse.urlsplit(url).netloc
        time.sleep(max(0, self.last.get(host, 0) + delay - time.monotonic()))
        self.calls += 1
        self.last[host] = time.monotonic()
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                     "Accept-Language": "da-DK,da;q=0.9,en;q=0.6"})
        with self.opener.open(req, timeout=45) as response:
            return response.read().decode("utf-8", "replace")

    def read(self, url):
        parts = urllib.parse.urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self.policies:
            try:
                text = self._raw(origin + "/robots.txt", self.pause)
            except urllib.error.HTTPError as exc:
                if exc.code not in (404, 410):
                    raise
                text = ""
            if re.search(r"<!doctype\s+html|<html\b", text, re.I):
                raise ValueError("robots.txt gav HTML i stedet for regler")
            rules = robot_rules(text)
            delay = max([self.pause] + [float(v) for k, v in rules if k == "crawl-delay"])
            self.policies[origin] = rules, delay
        rules, delay = self.policies[origin]
        if not robot_allows(rules, url):
            raise PermissionError("Adressen er spærret i robots.txt")
        try:
            return self._raw(url, delay)
        except urllib.error.HTTPError:
            raise  # Adgangsfejl og omdirigeringer forsøges aldrig igen.
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            # Samme adresse og identitet. Begge forsøg tæller med i kaldeloftet.
            return self._raw(url, max(delay, 5))
