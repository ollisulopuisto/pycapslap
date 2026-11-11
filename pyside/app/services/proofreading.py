"""Local proofreading, computed away from painting and the GUI thread.

Offsets are Python code points. A result belongs to the exact immutable cue
snapshot that produced it; callers must discard results after any edit.
"""

import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Cue:
    text: str
    glued: bool = False


@dataclass(frozen=True)
class Issue:
    start: int
    end: int
    message: str
    replacements: tuple[str, ...]
    category: str


def configure_bundle():
    if getattr(sys, "frozen", False):
        root = Path(sys._MEIPASS) / "voikko"
        # Frozen builds must never silently fall back to the build machine's brew.
        if not (root / "lib" / "libvoikko.1.dylib").is_file():
            raise RuntimeError("Bundled Finnish proofreading library is missing")
        os.environ["PUNAKYNA_LIBVOIKKO_PATH"] = str(root / "lib")
        os.environ["PUNAKYNA_VOIKKO_DICTIONARY_PATH"] = str(root / "voikko")


def context(cues: tuple[Cue, ...], row: int):
    """Join neighbouring cues, reassembling explicitly split words.

    Return the current cue's range in the joined text. Cross-cue issues are
    deliberately not replaceable: a correction must never destroy cue timing.
    """
    text = ""
    start = end = 0
    for i in range(max(0, row - 1), min(len(cues), row + 2)):
        cue = cues[i]
        if text:
            if cue.glued or text.endswith("-"):
                text = text.removesuffix("-")
            else:
                text += " "
        if i == row:
            start = len(text)
        text += cue.text
        if i == row:
            end = len(text)
    return text, start, end


@lru_cache(maxsize=4096)
def _check(text: str, style: bool):
    from punakyna.pipeline import check_text
    from punakyna.voikko_gc import (
        _resolve_libfile,
        discover_libfile,
        load_voikko_library,
    )

    # Fail cleanly before the pip wrapper constructs a half-initialized object.
    load_voikko_library(
        _resolve_libfile(os.environ.get("PUNAKYNA_LIBVOIKKO_PATH"))
        if os.environ.get("PUNAKYNA_LIBVOIKKO_PATH")
        else discover_libfile()
    )

    return tuple(
        check_text(
            text,
            style_profile={
                "prefer_active": style,
                "max_sentence_words": 15 if style else 0,
            },
        )
    )


def check_snapshot(cues: tuple[Cue, ...], mode: str):
    """Return per-row issues, or raise for a visible unavailable status."""
    if mode == "off":
        return tuple(() for _ in cues)
    configure_bundle()
    rows = []
    for row, cue in enumerate(cues):
        text, offset, end = context(cues, row)
        issues = []
        for finding in _check(text, mode == "style"):
            if mode != "style" and finding.severity not in ("error", "warning"):
                continue
            if not (offset <= finding.start < finding.end <= end):
                continue
            s, e = finding.start - offset, finding.end - offset
            # Preserve the old split-syllable exclusions at context boundaries.
            if cue.glued and s <= len(cue.text) - len(cue.text.lstrip()):
                continue
            if cue.text.rstrip().endswith("-") and e >= len(cue.text.rstrip()) - 1:
                continue
            category = (
                "style"
                if finding.severity in ("style", "info")
                else ("spelling" if finding.category == "spelling" else "grammar")
            )
            issues.append(
                Issue(s, e, finding.message, tuple(finding.replacements), category)
            )
        rows.append(tuple(issues))
    return tuple(rows)
