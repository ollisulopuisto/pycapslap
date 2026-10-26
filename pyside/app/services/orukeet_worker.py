"""Persistent JSON-lines adapter around Orukeet's verified local runtime."""

from __future__ import annotations

import array
import hashlib
import json
import os
import sys
import traceback
from pathlib import Path

import numpy as np
import orukeet
from orukeet.audio import windows
from orukeet.install import fetch, install_runtime, resolve_device
from orukeet.nvidia import NvidiaRecognizer


class _LocalRecognizer(NvidiaRecognizer):
    """Expose Orukeet's verbatim switch and retain source timestamps."""

    def _options(self, language):
        options = super()._options(language)
        options.verbatim_transcripts = self._keep_fillers
        return options

    def transcribe_file(self, audio: str | Path, keep_fillers: bool = True) -> dict:
        self._keep_fillers = keep_fillers
        texts, segments = [], []
        for offset, samples in windows(str(audio)):
            if not samples.size or np.max(np.abs(samples)) <= .00025:
                continue
            result = self.transcribe(array.array("f", samples), None)
            texts.append(result["text"])
            segments.extend(
                dict(segment, start=offset + segment["start"], end=offset + segment["end"])
                for segment in result["segments"]
            )
        return {"text": " ".join(texts).strip(), "segments": segments, "language": None}


def _cache_dir() -> Path:
    configured = os.environ.get("CAPSLAP_ORUKEET_CACHE")
    if configured:
        return Path(configured)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "PyCapSlap" / "orukeet"
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PyCapSlap" / "orukeet"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "pycapslap" / "orukeet"


def _load_model() -> _LocalRecognizer:
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
    artifacts_path = Path(orukeet.__file__).with_name("artifacts.json")
    artifacts = json.loads(artifacts_path.read_text(encoding="utf-8"))
    with Path(config["model"]).open("rb") as model_file:
        digest = hashlib.file_digest(model_file, "sha256").hexdigest()
    if digest != artifacts["files"]["q8"]["sha256"]:
        raise ValueError("Model SHA-256 differs from the requested artifact")
    return _LocalRecognizer(config["runtime"], config["model"], config["device"])


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
                    result = model.transcribe_file(
                        request["audio"], keep_fillers=request.get("keepFillers", True)
                    )
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
