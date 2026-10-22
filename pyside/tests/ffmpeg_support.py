"""What the ffmpeg on PATH can do, for the tests that render a reel."""

import shutil
import subprocess

import pytest


def _has_filter(ffmpeg: str | None, name: str) -> bool:
    if ffmpeg is None:
        return False
    try:
        out = subprocess.run(
            [ffmpeg, "-hide_banner", "-filters"],
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return any(line.split()[1:2] == [name] for line in out.splitlines())


# The reel writes its credits with drawtext, which needs an ffmpeg built with
# freetype; Homebrew's plain `ffmpeg` formula has none (ffmpeg-full does).
needs_drawtext = pytest.mark.skipif(
    not _has_filter(shutil.which("ffmpeg"), "drawtext"),
    reason="needs an ffmpeg with the drawtext filter (freetype)",
)
