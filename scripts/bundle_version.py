"""Resolve the macOS bundle version from the release tag, or the changelog."""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Mapping


_PATTERN = r"v(\d{2}\.\d{2}\.\d{2}\.[1-9]\d*)"


def _validate(tag: str) -> str:
    match = re.fullmatch(_PATTERN, tag)
    if not match:
        raise ValueError(f"Expected a vYY.MM.DD.N release tag, got {tag!r}")
    version = match[1]
    datetime.strptime(version.rsplit(".", 1)[0], "%y.%m.%d")
    return version


def bundle_version(repo_root: Path, environ: Mapping[str, str] | None = None) -> str:
    """Use the exact tag in release CI; local builds use the latest release notes."""
    env = os.environ if environ is None else environ
    if env.get("GITHUB_REF_TYPE") == "tag":
        return _validate(env.get("GITHUB_REF_NAME", ""))
    changelog = (repo_root / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(r"^## \[(v[^\]]+)\]", changelog, re.MULTILINE)
    if not match:
        raise ValueError("CHANGELOG.md has no released version")
    return _validate(match[1])
