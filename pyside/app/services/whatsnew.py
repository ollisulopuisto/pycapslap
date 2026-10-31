# What's New: turns CHANGELOG.md into dialog entries and decides when the
# dialog should open by itself. The changelog is the release history (the
# release workflow and bundle_version.py both treat its first `## [v...]`
# heading as the running build's version), so it is the one place this app
# documents what changed; the dialog surfaces it instead of inventing a
# second source.
from __future__ import annotations

import re
from pathlib import Path

# Keep-a-Changelog calver, same shape bundle_version.py validates:
#   ## [v26.10.31.1] - 2026-10-31
_HEADING = re.compile(
    r"^## \[(v\d{2}\.\d{2}\.\d{2}\.\d+)\](?: - (\d{4}-\d{2}-\d{2}))?\s*$"
)

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
    """[(version, [change, ...])] newest first, from `## [vYY.MM.DD.N]`
    headings. [Unreleased] and ### section headers are skipped; bullets are
    kept, nested bullets flattened; non-bullet lines are skipped."""
    entries: list[tuple[str, list[str]]] = []
    version: str | None = None
    items: list[str] = []
    for line in text.splitlines():
        heading = _HEADING.match(line)
        if heading:
            if version:
                entries.append((version, items))
            version, items = heading.group(1), []
        elif line.startswith("## "):
            # [Unreleased] or any other section: stop collecting into a
            # version until the next release heading.
            if version:
                entries.append((version, items))
            version, items = None, []
        elif version:
            stripped = line.strip()
            if stripped.startswith("- "):
                items.append(stripped[2:])
    if version:
        entries.append((version, items))
    return entries


def current_version(entries: list[tuple[str, list[str]]]) -> str | None:
    """The running build's version: the newest changelog heading, the same
    source bundle_version.py uses for local builds."""
    return entries[0][0] if entries else None


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.lstrip("v").split("."))


def unseen_entries(
    entries: list[tuple[str, list[str]]], last_seen: str
) -> list[tuple[str, list[str]]]:
    """Entries newer than `last_seen`, compared numerically per segment so
    v26.10.31.10 sorts after v26.10.31.2. An empty `last_seen` returns
    everything; empty sections are dropped so the dialog never shows a bare
    heading."""
    seen_key = _version_key(last_seen) if last_seen else None
    unseen = [
        (v, items)
        for v, items in entries
        if items and (seen_key is None or _version_key(v) > seen_key)
    ]
    return unseen
