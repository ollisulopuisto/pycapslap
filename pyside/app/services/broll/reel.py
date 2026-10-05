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
from dataclasses import dataclass
from pathlib import Path

from app.services.broll import credits
from app.services.broll.assets import Asset

FPS = 30
# Ken Burns on stills: zoom in 0.06 % per frame to a ceiling of 20 %, so a 5 s
# still ends 20 % closer. Chosen by eye on 9:16; a faster push reads as a jump.
ZOOM_STEP = 0.0006
ZOOM_MAX = 1.2
CREDIT_SECONDS = 4.0
_FONT_NAME = "Roboto Bold.ttf"


class ReelError(RuntimeError):
    pass


@dataclass(frozen=True)
class Shot:
    start_ms: int
    end_ms: int
    path: Path
    kind: str  # "image" | "video"
    credit: str
    size: tuple[int, int] | None = None  # of a video; lets the GPU scale it

    @property
    def seconds(self) -> float:
        return (self.end_ms - self.start_ms) / 1000


def shots(accepted: list[tuple[dict, Asset]], files: dict[str, Path]) -> list[Shot]:
    """One shot per accepted window, ending where the next one begins."""
    out: list[Shot] = []
    for i, (win, a) in enumerate(accepted):
        end = win["endMs"]
        if i + 1 < len(accepted):
            end = min(end, accepted[i + 1][0]["startMs"])
        size = (a.width, a.height) if a.width > 0 and a.height > 0 else None
        out.append(
            Shot(win["startMs"], end, files[a.title], a.kind, credits.line(a), size)
        )
    return out


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
    for s in shots_:
        src = str(Path(s.path).resolve())
        if s.kind == "image":
            cmd += [
                "-loop",
                "1",
                "-framerate",
                str(FPS),
                "-t",
                f"{s.seconds:.3f}",
                "-i",
                src,
            ]
        else:
            # VideoToolbox decodes the clip; with its size known the frames stay
            # on the GPU for scale_vt, otherwise they come back to system memory.
            gpu = []
            if hw:
                gpu = ["-hwaccel", "videotoolbox"]
                if s.size:
                    gpu += ["-hwaccel_output_format", "videotoolbox_vld"]
            cmd += ["-stream_loop", "-1", "-t", f"{s.seconds:.3f}", *gpu, "-i", src]

    g = [
        f"[0:a]apad=whole_dur={total:.3f},asplit[a1][a2]",
        f"[a1]showwaves=s={w}x{h}:mode=cline:rate={FPS}:colors=white,"
        "format=yuv420p[bg0]",
    ]
    fs = int(h * 0.028)
    for i, s in enumerate(shots_):
        a, b = s.start_ms / 1000, s.end_ms / 1000
        if s.kind == "image":
            motion = (
                f"scale={2 * w}:{2 * h}:force_original_aspect_ratio=increase,"
                f"crop={2 * w}:{2 * h},"
                f"zoompan=z='min(1+{ZOOM_STEP}*on,{ZOOM_MAX})':"
                "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d=1:s={w}x{h}:fps={FPS}"
            )
        elif hw and s.size:
            cw, ch = cover_dims(s.size, (w, h))
            motion = (
                f"scale_vt=w={cw}:h={ch},hwdownload,format=nv12,crop={w}:{h},fps={FPS}"
            )
        else:
            motion = (
                f"scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h},fps={FPS}"
            )
        g.append(
            f"[{i + 1}:v]{motion},setsar=1,format=yuv420p,"
            f"setpts=PTS-STARTPTS+{a:.3f}/TB[v{i}]"
        )
        g.append(
            f"[bg{i}][v{i}]overlay=enable='between(t,{a:.3f},{b:.3f})':"
            f"eof_action=pass[o{i}]"
        )
        name = f"credit{i}.txt"
        (work / name).write_text(_wrap(s.credit, w, _chars(w, fs)), encoding="utf-8")
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
            if s.credit not in seen:
                seen.add(s.credit)
                lines.append(s.credit)
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
