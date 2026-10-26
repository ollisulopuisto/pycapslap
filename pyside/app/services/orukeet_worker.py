"""Persistent JSON-lines adapter around Orukeet's verified local runtime."""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

from orukeet import Orukeet
from orukeet.install import fetch, install_runtime, resolve_device


def _cache_dir() -> Path:
    configured = os.environ.get("CAPSLAP_ORUKEET_CACHE")
    if configured:
        return Path(configured)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "PyCapSlap" / "orukeet"
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PyCapSlap" / "orukeet"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "pycapslap" / "orukeet"


def _load_model() -> Orukeet:
    cache = _cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    receipt = cache / "installation.json"
    if not receipt.is_file():
        device = resolve_device("auto")
        runtime = install_runtime(device, cache / "runtime-cache")
        model = fetch("q8", cache / "model-cache")
        receipt.write_text(
            json.dumps({"model": str(model.resolve()), "runtime": str(runtime.resolve()), "device": device}),
            encoding="utf-8",
        )
    config = json.loads(receipt.read_text(encoding="utf-8-sig"))
    return Orukeet(config["model"], config["runtime"], device=config["device"])


def main() -> int:
    model = None
    try:
        for line in sys.stdin:
            if not line.strip():
                continue
            request = json.loads(line)
            request_id = request.get("id")
            try:
                if model is None:
                    model = _load_model()
                if request.get("action") == "install":
                    result = {"ready": True}
                else:
                    result = model.transcribe(request["audio"])
                response = {"id": request_id, "result": result}
            except Exception as exc:  # return failures without killing the worker
                traceback.print_exc(file=sys.stderr)
                response = {"id": request_id, "error": str(exc)}
            print(json.dumps(response, ensure_ascii=False), flush=True)
    finally:
        if model is not None:
            model.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
