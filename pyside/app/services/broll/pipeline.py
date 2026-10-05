"""Accepted picks in, reel out: download, render, and leave the captions and
the credits text beside it."""

import shutil
from collections.abc import Callable
from pathlib import Path

from app.services.broll import credits, download, reel
from app.services.broll.picks import Picks


class NothingAccepted(ValueError):
    pass


def build(
    audio: Path,
    picks: Picks,
    out: Path,
    fetch: Callable = download.fetch,
    render: Callable = reel.render,
    sidecar: Path | None = None,
    size: tuple[int, int] = (1080, 1920),
    end_card_s: float = 5.0,
) -> Path:
    accepted = picks.accepted()
    if not accepted:
        raise NothingAccepted("accept at least one picture or clip first")
    work = out.parent / f".{out.stem}-work"
    files = {a.title: fetch(a, work / "assets") for _, a in accepted}
    shots = reel.shots(accepted, files)
    render(audio, shots, out, work=work, size=size, end_card_s=end_card_s)
    # The reel starts with the episode's first second, so the cue times still
    # fit: the app can load the reel and burn the captions as for any video.
    if sidecar and sidecar.exists():
        shutil.copyfile(sidecar, out.parent / f"{out.name}.capslap.json")
    (out.parent / f"{out.stem}.credits.txt").write_text(
        credits.description([a for _, a in accepted]) + "\n", encoding="utf-8"
    )
    shutil.rmtree(work, ignore_errors=True)
    return out
