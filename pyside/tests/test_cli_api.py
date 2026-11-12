"""Unit and integration tests for PyCapSlap headless API and CLI commands."""

import json
from pathlib import Path

from app.api.workflow import (
    CapSlapSession,
    edit_captions,
    load_captions,
    save_captions,
)
from app.cli import run_cli
from app.models.captions import CaptionSegment, CaptionsFile


def test_captions_file_save_and_load(tmp_path: Path):
    seg1 = CaptionSegment(start_ms=0, end_ms=1500, text="First segment")
    seg1.update_text("First segment")
    seg2 = CaptionSegment(start_ms=1600, end_ms=3000, text="Second segment")
    seg2.update_text("Second segment")

    cf = CaptionsFile(segments=[seg1, seg2])
    out_file = tmp_path / "test.mp4.capslap.json"
    saved_path = save_captions(cf, out_file)
    assert saved_path.is_file()

    loaded = load_captions(saved_path)
    assert len(loaded.segments) == 2
    assert loaded.segments[0].text == "First segment"
    assert loaded.segments[1].text == "Second segment"


def test_edit_captions_preset_and_patches():
    seg = CaptionSegment(start_ms=100, end_ms=2000, text="Original text")
    seg.update_text("Original text")
    cf = CaptionsFile(segments=[seg])

    edited = edit_captions(
        cf,
        preset="karaoke",
        position_pct=50.0,
        text_replacements={"Original": "Replaced"},
        segment_patches=[{"index": 0, "startMs": 200, "endMs": 2500}],
    )

    assert edited.style.template_id == "karaoke"
    assert edited.style.karaoke is True
    assert len(edited.position_overrides) == 1
    assert edited.position_overrides[0].y_pct == 50.0
    assert edited.segments[0].text == "Replaced text"
    assert edited.segments[0].start_ms == 200
    assert edited.segments[0].end_ms == 2500


def test_cli_info_command(capsys):
    repo_root = Path(__file__).resolve().parents[2]
    video = str((repo_root / "rust" / "bin" / "test_input.mp4").resolve())

    status = run_cli(["info", video, "--json"])
    assert status == 0

    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert data.get("ok") is True
    assert data.get("hasFirstFrame") is True
    assert "video" in data


def test_cli_info_nonexistent_file(capsys):
    status = run_cli(["info", "/path/to/nonexistent/video.mp4", "--json"])
    assert status == 1

    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert data.get("ok") is False
    assert "error" in data


def test_cli_edit_command(tmp_path: Path, capsys):
    seg = CaptionSegment(start_ms=0, end_ms=1000, text="hello world")
    seg.update_text("hello world")
    cf = CaptionsFile(segments=[seg])
    sidecar = tmp_path / "video.mp4.capslap.json"
    save_captions(cf, sidecar)

    status = run_cli(
        [
            "edit",
            str(sidecar),
            "--preset",
            "justified",
            "--position",
            "85",
            "--replace",
            "hello=hi",
            "--json",
        ]
    )
    assert status == 0

    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert data.get("ok") is True
    assert data.get("style", {}).get("justifyLines") is True
    assert data.get("segments", [])[0]["text"] == "hi world"


def test_session_ping_and_probe():
    repo_root = Path(__file__).resolve().parents[2]
    video = str((repo_root / "rust" / "bin" / "test_input.mp4").resolve())

    with CapSlapSession() as session:
        ping_res = session.ping()
        assert ping_res.get("ok") is True

        probe_res = session.probe(video)
        assert probe_res.get("hasFirstFrame") is True


def test_render_with_cli(tmp_path: Path, capsys):
    repo_root = Path(__file__).resolve().parents[2]
    video = str((repo_root / "rust" / "bin" / "test_input.mp4").resolve())

    # Create dummy sidecar in tmp_path
    seg = CaptionSegment(start_ms=100, end_ms=1500, text="Agent CLI test")
    seg.update_text("Agent CLI test")
    cf = CaptionsFile(segments=[seg])
    sidecar = tmp_path / "test.capslap.json"
    save_captions(cf, sidecar)

    status = run_cli(
        [
            "render",
            video,
            "--captions",
            str(sidecar),
            "--format",
            "9:16",
            "--crop",
            "fill",
            "--json",
        ]
    )
    assert status == 0

    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert data.get("ok") is True
    assert "rendered" in data
    rendered_list = data["rendered"]
    assert len(rendered_list) > 0
    out_video = rendered_list[0].get("captionedVideo")
    assert out_video and Path(out_video).is_file()
    # Clean up generated file
    Path(out_video).unlink(missing_ok=True)


# --- render-alpha: captions-only alpha movies/sequences --------------------

import shutil
import subprocess

import pytest


def _ffmpeg_has(*, filt: str | None = None, encoder: str | None = None) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return False
    try:
        if filt:
            out = subprocess.run(
                [ffmpeg, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=30
            ).stdout
            return any(line.split()[1:2] == [filt] for line in out.splitlines())
        out = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=30
        ).stdout
        return any(line.split()[1:2] == [encoder] for line in out.splitlines())
    except (OSError, subprocess.SubprocessError):
        return False


needs_alpha_stack = pytest.mark.skipif(
    not (_ffmpeg_has(filt="ass") and _ffmpeg_has(encoder="prores_ks")),
    reason="needs ffmpeg with the ass filter and the prores_ks encoder",
)


def _alpha_sidecar(tmp_path: Path) -> Path:
    seg = CaptionSegment(start_ms=0, end_ms=900, text="Title card")
    seg.update_text("Title card")
    sidecar = tmp_path / "title.capslap.json"
    save_captions(CaptionsFile(segments=[seg]), sidecar)
    return sidecar


@needs_alpha_stack
def test_render_alpha_cli_prores(tmp_path: Path, capsys):
    sidecar = _alpha_sidecar(tmp_path)
    out = tmp_path / "title.mov"
    status = run_cli([
        "render-alpha", "--captions", str(sidecar), "--size", "160x90",
        "--fps", "10", "--duration", "1.0", "--out", str(out), "--json",
    ])
    assert status == 0
    data = json.loads(capsys.readouterr().out)
    assert data.get("ok") is True
    assert data["rendered"]["frames"] == 10
    assert data["rendered"]["codec"] == "prores"
    assert out.is_file() and out.stat().st_size > 0


@needs_alpha_stack
def test_render_alpha_cli_png_sequence(tmp_path: Path, capsys):
    sidecar = _alpha_sidecar(tmp_path)
    out_dir = tmp_path / "cards"
    status = run_cli([
        "render-alpha", "--captions", str(sidecar), "--size", "160x90",
        "--fps", "10", "--duration", "1.0", "--codec", "png",
        "--out", str(out_dir), "--json",
    ])
    assert status == 0
    data = json.loads(capsys.readouterr().out)
    assert data.get("ok") is True
    frames = sorted(out_dir.glob("frame_*.png"))
    assert len(frames) == 10


def test_render_alpha_cli_requires_sidecar(tmp_path: Path, capsys):
    status = run_cli([
        "render-alpha", "--captions", str(tmp_path / "none.capslap.json"),
        "--size", "160x90", "--out", str(tmp_path / "x.mov"), "--json",
    ])
    assert status == 1
    data = json.loads(capsys.readouterr().out)
    assert data.get("ok") is False
