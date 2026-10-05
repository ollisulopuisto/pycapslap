"""Compose the reel: the episode audio as a waveform, accepted footage over it,
a credit while each piece is on screen and every credit again on an end card.

Text goes through `textfile=` and the files are named relative to the working
directory ffmpeg runs in, so no credit or path ever needs filtergraph escaping.
"""

import functools
import json
import math
import os
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass, replace
from pathlib import Path

from app.services.broll import credits, looks
from app.services.broll.looks import FPS
from app.services.broll.picks import Choice

CREDIT_SECONDS = 4.0
_FONT_NAME = "Roboto Bold.ttf"

# How long each way of arriving takes. A whip is the quickest: it is meant to
# be felt rather than seen.
TRANSITION_SECONDS = {"cut": 0.0, "fade": 0.4, "slide": 0.35, "whip": 0.25}
# Never longer than this share of either shot it joins.
TRANSITION_SHARE = 0.4
# Shots this close count as one after the other, with no waveform between.
ADJACENT_MS = 50
# Mixed: no two neighbours arrive the same way.
MIXED = ("fade", "whip", "fade", "slide")
# The whip's blur, sideways only so it reads as speed.
WHIP_BLUR_SIGMA = 24
# A stack is two half-frame pictures; credits for both show together.


class ReelError(RuntimeError):
    pass


@dataclass(frozen=True)
class Part:
    """The second picture of a stack."""

    path: Path
    kind: str  # "image" | "video"
    credit: str
    size: tuple[int, int] | None = None
    motion: str = "zoom_out"


@dataclass(frozen=True)
class Shot:
    start_ms: int
    end_ms: int
    path: Path
    kind: str  # "image" | "video"
    credit: str
    size: tuple[int, int] | None = None  # of a video; lets the GPU scale it
    layout: str = "fill"  # "fill" | "blur" | "stack"
    motion: str = "zoom_in"  # of a still: see looks.MOTIONS
    transition: str = "cut"  # how it arrives
    second: Part | None = None

    @property
    def seconds(self) -> float:
        return (self.end_ms - self.start_ms) / 1000

    @property
    def parts(self) -> list[Part]:
        first = Part(self.path, self.kind, self.credit, self.size, self.motion)
        return [first] + ([self.second] if self.second else [])

    @property
    def credit_lines(self) -> list[str]:
        """One credit per picture on screen."""
        return [p.credit for p in self.parts]


def _size(a) -> tuple[int, int] | None:
    return (a.width, a.height) if a.width > 0 and a.height > 0 else None


def shots(
    choices: list[Choice], files: dict[str, Path], transition: str = "mixed"
) -> list[Shot]:
    """One shot per accepted window, ending where the next one begins."""
    out: list[Shot] = []
    for i, ch in enumerate(choices):
        end = ch.window["endMs"]
        if i + 1 < len(choices):
            end = min(end, choices[i + 1].window["startMs"])
        a = ch.assets[0]
        motion = looks.auto_motion(i)
        credit = credits.line(a)
        layout = looks.auto_layout(_size(a))
        second = None
        if len(ch.assets) == 2:
            b = ch.assets[1]
            second = Part(
                files[b.title],
                b.kind,
                credits.line(b),
                _size(b),
                looks.opposite(motion),
            )
            layout = "stack"
        elif ch.layout in ("fill", "blur"):
            layout = ch.layout
        out.append(
            Shot(
                ch.window["startMs"],
                end,
                files[a.title],
                a.kind,
                credit,
                _size(a),
                layout,
                motion,
                "cut",
                second,
            )
        )
    return assign_transitions(out, transition)


def assign_transitions(shots_: list[Shot], style: str) -> list[Shot]:
    """Give each shot the way it arrives: one style for all, or a mix."""
    out = []
    for i, s in enumerate(shots_):
        kind = MIXED[i % len(MIXED)] if style == "mixed" else style
        out.append(replace(s, transition=kind))
    return out


def adjacent(prev: Shot, shot: Shot) -> bool:
    return shot.start_ms - prev.end_ms <= ADJACENT_MS


def transition_seconds(kind: str, prev: Shot | None, shot: Shot) -> float:
    """How long `shot` takes to arrive after `prev` by `kind`."""
    base = TRANSITION_SECONDS[kind]
    shortest = min(shot.seconds, prev.seconds if prev else shot.seconds)
    return min(base, TRANSITION_SHARE * shortest)


def arrival(shots_: list[Shot], i: int) -> float:
    prev = shots_[i - 1] if i > 0 else None
    return transition_seconds(shots_[i].transition, prev, shots_[i])


def extension(shots_: list[Shot], i: int) -> float:
    """How long shot i stays on after its end: the next one arrives over it."""
    if i + 1 >= len(shots_) or not adjacent(shots_[i], shots_[i + 1]):
        return 0.0
    return arrival(shots_, i + 1)


def _smooth(t0: float, d: float) -> str:
    u = f"clip((t-{t0:g})/{d:g},0,1)"
    return f"({u}*{u}*(3-2*{u}))"


def overlay_x(shots_: list[Shot], i: int, width: int) -> str:
    """Where shot i's left edge is, as an ffmpeg expression in t.

    A slide or whip arrives from the right; a whip also pushes the shot before
    it out to the left, so both move together."""
    s = shots_[i]
    a, b = s.start_ms / 1000, s.end_ms / 1000
    terms: list[tuple[str, str]] = []  # (condition, value), tried in order
    if s.transition in ("slide", "whip"):
        d = arrival(shots_, i)
        if d > 0:
            terms.append((f"lt(t,{a + d:g})", f"{width}*(1-{_smooth(a, d)})"))
    if i + 1 < len(shots_) and shots_[i + 1].transition == "whip":
        n = shots_[i + 1]
        if adjacent(s, n):
            d = arrival(shots_, i + 1)
            if d > 0:
                terms.append((f"gte(t,{b:g})", f"-{width}*{_smooth(b, d)}"))
    expr = "0"
    for cond, value in reversed(terms):
        expr = f"if({cond},{value},{expr})"
    return expr


def blur_enable(shots_: list[Shot], i: int) -> str | None:
    """When shot i is in the middle of a whip, as an `enable` expression."""
    s = shots_[i]
    a, b = s.start_ms / 1000, s.end_ms / 1000
    windows = []
    if s.transition == "whip":
        d = arrival(shots_, i)
        if d > 0:
            windows.append(f"between(t,{a:g},{a + d:g})")
    if i + 1 < len(shots_) and shots_[i + 1].transition == "whip":
        if adjacent(s, shots_[i + 1]):
            d = arrival(shots_, i + 1)
            if d > 0:
                windows.append(f"between(t,{b:g},{b + d:g})")
    return "+".join(windows) or None


def ffmpeg_path() -> str:
    return os.environ.get("FFMPEG_PATH") or shutil.which("ffmpeg") or "ffmpeg"


@functools.lru_cache(maxsize=1)
def vt_available() -> bool:
    """A Mac whose ffmpeg has the VideoToolbox H.264 encoder."""
    if sys.platform != "darwin":
        return False
    r = subprocess.run(
        [ffmpeg_path(), "-hide_banner", "-encoders"], capture_output=True, text=True
    )
    return "h264_videotoolbox" in r.stdout


def cover_dims(src: tuple[int, int], target: tuple[int, int]) -> tuple[int, int]:
    """The size to scale `src` to so it covers `target`, both sides even; the
    crop that follows then only cuts. Mirrors `gpu_scale_dims` in rust/src/video.rs."""
    (sw, sh), (tw, th) = src, target
    s = max(tw / sw, th / sh)

    def up(v: float) -> int:
        return (math.ceil(v - 1e-9) + 1) // 2 * 2

    return max(up(sw * s), tw), max(up(sh * s), th)


def ffprobe_path() -> str:
    return os.environ.get("FFPROBE_PATH") or shutil.which("ffprobe") or "ffprobe"


def default_font() -> Path:
    for folder in (
        os.environ.get("CAPSLAP_FONTS_DIR"),
        Path(__file__).resolve().parents[4] / "rust" / "src" / "fonts",
    ):
        if folder and (Path(folder) / _FONT_NAME).is_file():
            return Path(folder) / _FONT_NAME
    raise ReelError(f"font {_FONT_NAME} not found; set CAPSLAP_FONTS_DIR")


def probe_duration(path: Path) -> float:
    r = subprocess.run(
        [
            ffprobe_path(),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    try:
        return float(json.loads(r.stdout)["format"]["duration"])
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        raise ReelError(f"cannot read the length of {path}: {r.stderr.strip()}") from e


def _wrap(text: str, width: int, chars: int) -> str:
    return "\n".join(textwrap.wrap(text, max(10, chars), break_long_words=True))


def _chars(width: int, fontsize: int) -> int:
    # Roboto Bold averages ~0.58 em per character; keep 10 % margins.
    return int(width * 0.8 / (fontsize * 0.58))


def _end_card(lines: list[str], size: tuple[int, int]) -> tuple[str, int]:
    w, h = size
    fs = int(h * 0.03)
    floor = max(8, int(h * 0.012))
    while True:
        body = "\n\n".join(_wrap(t, w, _chars(w, fs)) for t in lines)
        if body.count("\n") + 1 <= h * 0.8 / (fs * 1.3) or fs <= floor:
            return body, fs
        fs -= 1


def command(
    audio: Path,
    shots_: list[Shot],
    out: Path,
    duration_s: float,
    work: Path,
    size: tuple[int, int] = (1080, 1920),
    end_card_s: float = 5.0,
    font: Path | None = None,
    hw: bool | None = None,
) -> list[str]:
    if hw is None:
        hw = vt_available()
    w, h = size
    work.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(font or default_font(), work / "font.ttf")
    total = duration_s + end_card_s

    cmd = [ffmpeg_path(), "-y", "-v", "error", "-i", str(Path(audio).resolve())]
    g = [
        f"[0:a]apad=whole_dur={total:.3f},asplit[a1][a2]",
        f"[a1]showwaves=s={w}x{h}:mode=cline:rate={FPS}:colors=white,"
        "format=yuv420p[bg0]",
    ]
    fs = int(h * 0.028)
    n_inputs = 0  # the audio is input 0
    for i, s in enumerate(shots_):
        a, b = s.start_ms / 1000, s.end_ms / 1000
        ext = extension(shots_, i)
        shown = s.seconds + ext
        frames = max(1, round(shown * FPS))
        stacked = s.layout == "stack"
        th = h // 2 if stacked else h
        region_layout = "blur" if s.layout == "blur" else "fill"
        labels = []
        for j, part in enumerate(s.parts):
            n_inputs += 1
            src = str(Path(part.path).resolve())
            gpu_scale = None
            if part.kind == "image":
                cmd += ["-loop", "1", "-framerate", str(FPS), "-t", f"{shown:.3f}"]
                cmd += ["-i", src]
            else:
                # VideoToolbox decodes the clip; with its size known (and the
                # picture to fill) the frames stay on the GPU for scale_vt,
                # otherwise they come back to system memory.
                gpu: list[str] = []
                if hw:
                    gpu = ["-hwaccel", "videotoolbox"]
                    if part.size and region_layout == "fill":
                        gpu += ["-hwaccel_output_format", "videotoolbox_vld"]
                        gpu_scale = cover_dims(part.size, (w, th))
                cmd += ["-stream_loop", "-1", "-t", f"{shown:.3f}", *gpu, "-i", src]
            tag = f"s{i}{'ab'[j]}"
            label = tag if stacked else f"s{i}"
            labels.append(label)
            if part.kind == "image":
                g += looks.still_filters(
                    f"{n_inputs}:v",
                    label,
                    part.motion,
                    frames,
                    w,
                    th,
                    region_layout,
                    tag,
                )
            else:
                g += looks.video_filters(
                    f"{n_inputs}:v", label, w, th, region_layout, tag, gpu_scale
                )
        if stacked:
            g.append(f"[{labels[0]}][{labels[1]}]vstack=inputs=2[s{i}]")
        fade = s.transition == "fade" and arrival(shots_, i) > 0
        chain = [
            "setsar=1",
            f"format={'yuva420p' if fade else 'yuv420p'}",
            f"setpts=PTS-STARTPTS+{a:.3f}/TB",
        ]
        if fade:
            chain.append(f"fade=t=in:st={a:.3f}:d={arrival(shots_, i):.3f}:alpha=1")
        blur = blur_enable(shots_, i)
        if blur:
            chain.append(f"gblur=sigma={WHIP_BLUR_SIGMA}:sigmaV=0:enable='{blur}'")
        g.append(f"[s{i}]{','.join(chain)}[v{i}]")
        g.append(
            f"[bg{i}][v{i}]overlay=x='{overlay_x(shots_, i, w)}':y=0:"
            f"enable='between(t,{a:.3f},{b + ext:.3f})':eof_action=pass[o{i}]"
        )
        name = f"credit{i}.txt"
        wrapped = "\n".join(_wrap(line, w, _chars(w, fs)) for line in s.credit_lines)
        (work / name).write_text(wrapped, encoding="utf-8")
        g.append(
            f"[o{i}]drawtext=fontfile=font.ttf:textfile={name}:expansion=none:"
            f"fontsize={fs}:fontcolor=white:box=1:boxcolor=black@0.55:"
            f"boxborderw={fs // 2}:x=(w-text_w)/2:y=h*0.84:"
            f"enable='between(t,{a:.3f},{min(b, a + CREDIT_SECONDS):.3f})'[bg{i + 1}]"
        )
    last = f"bg{len(shots_)}"
    if end_card_s > 0:
        lines = ["Images and footage"]
        seen: set[str] = set()
        for s in shots_:
            for line in s.credit_lines:
                if line not in seen:
                    seen.add(line)
                    lines.append(line)
        body, cfs = _end_card(lines, size)
        (work / "endcard.txt").write_text(body, encoding="utf-8")
        t0 = duration_s
        g.append(
            f"[{last}]drawbox=x=0:y=0:w=iw:h=ih:color=black@0.9:t=fill:"
            f"enable='gte(t,{t0:.3f})',"
            f"drawtext=fontfile=font.ttf:textfile=endcard.txt:expansion=none:"
            f"fontsize={cfs}:fontcolor=white:line_spacing={cfs // 3}:"
            f"x=(w-text_w)/2:y=(h-text_h)/2:enable='gte(t,{t0:.3f})'[vout]"
        )
    else:
        g.append(f"[{last}]null[vout]")

    cmd += [
        "-filter_complex",
        ";".join(g),
        "-map",
        "[vout]",
        "-map",
        "[a2]",
        *(
            # 12M is the bitrate the app's own VideoToolbox renders use.
            ["-c:v", "h264_videotoolbox", "-b:v", "12M", "-allow_sw", "1"]
            if hw
            else ["-c:v", "libx264", "-preset", "medium", "-crf", "20"]
        ),
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        "-t",
        f"{total:.3f}",
        str(Path(out).resolve()),
    ]
    return cmd


def render(
    audio: Path,
    shots_: list[Shot],
    out: Path,
    work: Path,
    size: tuple[int, int] = (1080, 1920),
    end_card_s: float = 5.0,
    duration_s: float | None = None,
    hw: bool | None = None,
) -> Path:
    duration = duration_s if duration_s is not None else probe_duration(audio)
    if hw is None:
        hw = vt_available()
    # The GPU run may refuse a clip (10-bit, an odd codec) or lack a filter; it
    # fails at start-up, and the software run takes over.
    for use_hw in (True, False) if hw else (False,):
        cmd = command(audio, shots_, out, duration, work, size, end_card_s, hw=use_hw)
        r = subprocess.run(cmd, cwd=work, capture_output=True, text=True)
        if r.returncode == 0:
            return Path(out)
        error = r.stderr.strip()[-800:] or f"ffmpeg exited {r.returncode}"
    raise ReelError(error)
