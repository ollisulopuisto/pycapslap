"""Accepted picks in, reel out: download, render, and leave the captions and
the credits text beside it."""

import shutil
from collections.abc import Callable
from pathlib import Path

from app.services import media
from app.services.broll import credits, download, reel, control
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
    transition: str = "mixed",
    cancel=None,
    progress=None,
) -> Path:
    accepted = picks.accepted()
    if not accepted:
        raise NothingAccepted("accept at least one picture or clip first")
    work = out.parent / f".{out.stem}-work"
    assets = [a for ch in accepted for a in ch.assets]
    # Keyed by URL: two sources can have a picture with the same title.
    files = {}
    for asset in assets:
        control.check(cancel)
        if asset.url not in files:
            files[asset.url] = (
                fetch(asset, work / "assets", cancel=cancel, progress=progress)
                if cancel is not None
                else fetch(asset, work / "assets")
            )
    # NASA and the Internet Archive do not say how big a file is until it is
    # here; the shape decides how the shot is laid out (fitted or filled).
    sizes = {}
    for a in assets:
        if a.width <= 0 or a.height <= 0:
            found = media.size(files[a.url])
            if found:
                sizes[a.url] = found
    shots = reel.shots(accepted, files, transition, sizes)
    control.check(cancel)
    options = {"cancel": cancel} if cancel is not None else {}
    render(audio, shots, out, work=work, size=size, end_card_s=end_card_s, **options)
    control.check(cancel)
    # The reel starts with the episode's first second, so the cue times still
    # fit: the app can load the reel and burn the captions as for any video.
    if sidecar and sidecar.exists():
        shutil.copyfile(sidecar, out.parent / f"{out.name}.capslap.json")
    (out.parent / f"{out.stem}.credits.txt").write_text(
        credits.description(assets) + "\n", encoding="utf-8"
    )
    shutil.rmtree(work, ignore_errors=True)
    return out
