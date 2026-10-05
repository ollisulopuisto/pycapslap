import time
import urllib.error
import urllib.parse
import urllib.request

# Wikimedia identifies clients by User-Agent and asks them to say who they are.
USER_AGENT = "PyCapSlap-broll/0.1 (https://github.com/ollisulopuisto/pycapslap)"
# Wikimedia answers 429 with Retry-After when a client is busy; three tries.
ATTEMPTS = 3


def get(url: str, params: dict[str, str] | None = None) -> bytes:
    full = f"{url}?{urllib.parse.urlencode(params)}" if params else url
    req = urllib.request.Request(full, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == ATTEMPTS:
                raise
            time.sleep(int(e.headers.get("Retry-After", 5)))
    raise AssertionError("unreachable")
