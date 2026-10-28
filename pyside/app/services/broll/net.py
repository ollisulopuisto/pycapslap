import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# Wikimedia identifies clients by User-Agent and asks them to say who they are.
USER_AGENT = "PyCapSlap-broll/0.1 (https://github.com/ollisulopuisto/pycapslap)"
# Wikimedia answers 429 with Retry-After when a client is busy; three tries.
ATTEMPTS = 3


def get(url: str, params: dict[str, Any] | None = None, *, cancel=None) -> bytes:
    # A list value repeats the key, as `fl[]=a&fl[]=b` needs.
    query = urllib.parse.urlencode(params, doseq=True) if params else ""
    full = f"{url}?{query}" if query else url
    req = urllib.request.Request(full, headers={"User-Agent": USER_AGENT})
    from app.services.broll.control import check

    for attempt in range(1, ATTEMPTS + 1):
        check(cancel)
        try:
            with urllib.request.urlopen(
                req, timeout=10 if cancel is not None else 60
            ) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == ATTEMPTS:
                raise
            delay = min(60, max(0, int(e.headers.get("Retry-After", 5))))
            if cancel is not None:
                cancel.wait(delay)
                check(cancel)
            else:
                time.sleep(delay)
    raise AssertionError("unreachable")


def get_json(url: str, params: dict[str, Any] | None = None) -> Any:
    return json.loads(get(url, params))


def download(url, destination, *, cancel=None, progress=None):
    """Stream media in bounded chunks. Metadata JSON keeps using get()."""
    from app.services.broll.control import check

    check(cancel)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    # One stalled read is bounded; cancellation is checked between chunks.
    with urllib.request.urlopen(request, timeout=10) as response:
        total = int(response.headers.get("Content-Length", 0)) or None
        received = 0
        with open(destination, "wb") as stream:
            while True:
                check(cancel)
                block = response.read(256 * 1024)
                if not block:
                    break
                stream.write(block)
                received += len(block)
                if progress:
                    progress(received, total)
            if total is not None and received != total:
                raise OSError(
                    "Incomplete media download; finished file was not replaced"
                )
        check(cancel)
