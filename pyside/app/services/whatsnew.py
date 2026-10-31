# What's New: turns CHANGELOG.md into dialog entries and decides when the
# dialog should open by itself. The changelog is the release history (the
# release workflow and version bumping both treat its first heading as the
# running build's version), so it is the one place this app documents what
# changed; the dialog surfaces it instead of inventing a second source.
from __future__ import annotations

import re
from pathlib import Path

_HEADING = re.compile(r"^## (?:\[)?(\d{4}\.\d{2}\.\d{2})(?:\])?[^\n]*$")

# Remembered between launches so the dialog opens only when a version the
# user has not been shown yet appears (first launch of the current version
# also counts: they have never been shown any entry).
QSETTINGS_KEY = "whatsnew/lastSeen"


def changelog_path() -> Path | None:
    """Where CHANGELOG.md lives: beside the package in the PyInstaller
    bundle (added to the spec's datas), else at the repo root next to
    `pyside/`."""
    package = Path(__file__).resolve().parents[2]  # services/ -> app/ -> pyside
    for candidate in (package / "CHANGELOG.md", package.parent / "CHANGELOG.md"):
        if candidate.is_file():
            return candidate
    return None


def parse_changelog(text: str) -> list[tuple[str, list[str]]]:
    """[(version, [change, ...])] newest first, from `## YYYY.MM.DD`
    headings. Bullets are kept, nested bullets flattened; non-bullet lines
    are skipped."""
    entries: list[tuple[str, list[str]]] = []
    version: str | None = None
    items: list[str] = []
    for line in text.splitlines():
        heading = _HEADING.match(line)
        if heading:
            if version:
                entries.append((version, items))
            version, items = heading.group(1), []
        elif version:
            stripped = line.strip()
            if stripped.startswith("- "):
                items.append(stripped[2:])
    if version:
        entries.append((version, items))
    return entries


def current_version(entries: list[tuple[str, list[str]]]) -> str | None:
    """The running build's version: the newest changelog heading, the same
    source the release workflow uses."""
    return entries[0][0] if entries else None


def unseen_entries(
    entries: list[tuple[str, list[str]]], last_seen: str
) -> list[tuple[str, list[str]]]:
    """Entries newer than `last_seen`; an empty `last_seen` returns
    everything. Empty sections are dropped so the dialog never shows a bare
    heading."""
    unseen = [(v, items) for v, items in entries if v > last_seen and items]
    return unseen
