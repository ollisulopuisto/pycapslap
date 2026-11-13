"""Headless programmatic API for PyCapSlap workflows."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QCoreApplication

from app.core_client import CoreClient
from app.models.captions import (
    STYLE_PRESETS,
    CaptionSegment,
    CaptionStyle,
    CaptionsFile,
    PositionOverride,
    apply_orphan_rules,
    combine_separated_syllables,
    group_words_into_phrases,
)
from app.services import transcribe_range


class CapSlapSession:
    """Manages a headless PyCapSlap session with CoreClient and QCoreApplication."""

    def __init__(self, core_client: CoreClient | None = None) -> None:
        self._app = QCoreApplication.instance()
        if self._app is None:
            self._app = QCoreApplication([])
        self._owns_client = core_client is None
        self.client = core_client or CoreClient()

    def close(self) -> None:
        if self._owns_client and self.client:
            self.client.close()

    def __enter__(self) -> CapSlapSession:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def ping(self, timeout: float = 5.0) -> dict[str, Any]:
        fut = self.client.call("ping", {})
        return fut.result(timeout=timeout)

    def probe(self, video_path: str | Path, timeout: float = 15.0) -> dict[str, Any]:
        """Return media metadata and sidecar status for a video."""
        path_str = str(Path(video_path).resolve())
        if not os.path.exists(path_str):
            raise FileNotFoundError(f"Video file not found: {path_str}")
        metadata = self.client.call("probe", {"input": path_str}).result(
            timeout=timeout
        )
        fut = self.client.call("extractFirstFrame", {"videoPath": path_str})
        res = fut.result(timeout=timeout)
        sidecar = Path(f"{path_str}.capslap.json")
        return {
            **(metadata or {}),
            "path": path_str,
            "hasFirstFrame": bool(res and res.get("imageData")),
            "sidecarExists": sidecar.is_file(),
            "sidecarPath": str(sidecar) if sidecar.is_file() else None,
        }

    def transcribe(
        self,
        video_path: str | Path,
        backend: str = "whisper",
        model: str = "tiny",
        keep_fillers: bool = False,
        start_ms: int | None = None,
        end_ms: int | None = None,
        language: str | None = None,
        clean_syllables: bool = True,
        clean_orphans: bool = True,
        group_phrases: bool = False,
        progress_callback: Callable[[str, float], None] | None = None,
        timeout: float = 600.0,
    ) -> CaptionsFile:
        """Transcribe video audio headless and return CaptionsFile."""
        path_str = str(Path(video_path).resolve())
        if not os.path.exists(path_str):
            raise FileNotFoundError(f"Video file not found: {path_str}")

        params: dict[str, Any] = {
            "inputVideo": path_str,
            "transcriptionBackend": backend,
            "whisperModel": model,
            "exportFormats": ["9:16"],
            "karaoke": False,
        }
        if backend == "orukeet":
            params["keepFillers"] = keep_fillers
        if start_ms is not None:
            params["transcribeStartMs"] = start_ms
        if end_ms is not None:
            params["transcribeEndMs"] = end_ms
        if language:
            params["transcriptionLanguage"] = language

        prog_slot = None
        if progress_callback:

            def _on_progress(_req_id: str, status: str, progress: float) -> None:
                progress_callback(status, progress)

            prog_slot = _on_progress
            self.client.progress.connect(prog_slot)

        try:
            fut = self.client.call("transcribe", params)
            res = fut.result(timeout=timeout)
        finally:
            if prog_slot:
                try:
                    self.client.progress.disconnect(prog_slot)
                except Exception:
                    pass

        transcription = (res or {}).get("transcription", {})
        segments_raw = transcription.get("segments", [])
        segments = [CaptionSegment.from_dict(s) for s in segments_raw]

        if clean_syllables:
            segments = combine_separated_syllables(segments)
        if clean_orphans:
            segments = apply_orphan_rules(segments)
        if group_phrases:
            segments = group_words_into_phrases(segments)

        if start_ms is not None and start_ms > 0:
            segments = transcribe_range.shifted(segments, start_ms)

        return CaptionsFile(segments=segments)

    def render(
        self,
        video_path: str | Path,
        captions: CaptionsFile,
        formats: list[str] | None = None,
        crop_strategy: str = "fill",
        proof_short_side: int | None = None,
        intro_video: str | None = None,
        outro_video: str | None = None,
        watermark: dict[str, Any] | None = None,
        progress_callback: Callable[[str, float], None] | None = None,
        timeout: float = 1200.0,
    ) -> list[dict[str, Any]]:
        """Burn captions into exported videos."""
        path_str = str(Path(video_path).resolve())
        if not os.path.exists(path_str):
            raise FileNotFoundError(f"Video file not found: {path_str}")

        style = captions.style
        export_formats = formats or ["9:16"]
        trim_end_ms = captions.trim_end_ms or 0
        if captions.trim_end_ms is not None:
            metadata = self.client.call("probe", {"input": path_str}).result(
                timeout=15.0
            )
            duration = (metadata or {}).get("duration")
            if duration is None:
                raise ValueError(
                    "Could not determine video duration for the saved trim end"
                )
            duration_ms = round(float(duration) * 1000)
            # CaptionsFile stores the trim end as an absolute timeline mark;
            # the Rust renderer expects the amount to remove from the end.
            trim_end_ms = max(0, duration_ms - captions.trim_end_ms)
        position_overrides = captions.position_overrides or [
            PositionOverride(start_ms=0, end_ms=10**9, y_pct=style.anchor_pct)
        ]

        params: dict[str, Any] = {
            "inputVideo": path_str,
            "segments": [s.to_dict() for s in captions.segments],
            "trimStartMs": captions.trim_start_ms or 0,
            "trimEndMs": trim_end_ms,
            "exportFormats": export_formats,
            "cropStrategy": crop_strategy,
            "proofShortSide": proof_short_side,
            "introVideo": intro_video,
            "outroVideo": outro_video,
            "watermark": watermark,
            "karaoke": style.karaoke,
            "multiline": style.multiline,
            "justifyLines": style.justify_lines,
            "fontName": style.font_name,
            "fontSize": style.font_size,
            "textColor": style.text_color,
            "highlightWordColor": style.highlight_color,
            "outlineColor": style.outline_color,
            "outlineWidth": style.outline_width,
            "backgroundBox": style.background_box,
            "positionOverrides": [o.to_dict() for o in position_overrides],
        }

        prog_slot = None
        if progress_callback:

            def _on_progress(_req_id: str, status: str, progress: float) -> None:
                progress_callback(status, progress)

            prog_slot = _on_progress
            self.client.progress.connect(prog_slot)

        try:
            fut = self.client.call("burn", params)
            res = fut.result(timeout=timeout)
        finally:
            if prog_slot:
                try:
                    self.client.progress.disconnect(prog_slot)
                except Exception:
                    pass

        return res if isinstance(res, list) else [res]

    def render_alpha(
        self,
        captions: CaptionsFile,
        width: int,
        height: int,
        fps: float = 25.0,
        duration_ms: int | None = None,
        output: str | Path = "alpha.mov",
        codec: str = "prores",
        progress_callback: Callable[[str, float], None] | None = None,
        timeout: float = 1200.0,
    ) -> dict[str, Any]:
        """Render captions alone — no input video — as an alpha movie/sequence.

        ProRes 4444 (.mov) or an RGBA PNG sequence, for titles and credits
        composited downstream (Autoraffkat, Final Cut).
        """
        style = captions.style
        params: dict[str, Any] = {
            "segments": [s.to_dict() for s in captions.segments],
            "karaoke": style.karaoke,
            "multiline": style.multiline,
            "justifyLines": style.justify_lines,
            "fontName": style.font_name,
            "fontSize": style.font_size,
            "textColor": style.text_color,
            "highlightWordColor": style.highlight_color,
            "outlineColor": style.outline_color,
            "outlineWidth": style.outline_width,
            "backgroundBox": style.background_box,
            "positionOverrides": [
                o.to_dict()
                for o in (
                    captions.position_overrides
                    or [
                        PositionOverride(
                            start_ms=0, end_ms=10**9, y_pct=style.anchor_pct
                        )
                    ]
                )
            ],
            "glowEffect": style.glow_effect,
            "width": int(width),
            "height": int(height),
            "fps": float(fps),
            "durationMs": duration_ms,
            "output": str(Path(output).expanduser().resolve()),
            "codec": codec,
        }

        prog_slot = None
        if progress_callback:

            def _on_progress(_req_id: str, status: str, progress: float) -> None:
                progress_callback(status, progress)

            prog_slot = _on_progress
            self.client.progress.connect(prog_slot)

        try:
            fut = self.client.call("renderAlpha", params)
            res = fut.result(timeout=timeout)
        finally:
            if prog_slot:
                try:
                    self.client.progress.disconnect(prog_slot)
                except Exception:
                    pass

        return res if isinstance(res, dict) else {}


def load_captions(path_or_video: str | Path) -> CaptionsFile:
    """Load CaptionsFile from a .capslap.json file or a video path with sidecar."""
    target = Path(path_or_video).expanduser().resolve()
    if not target.name.endswith(".capslap.json"):
        target = target.with_name(f"{target.name}.capslap.json")
    if not target.exists():
        raise FileNotFoundError(f"Captions sidecar not found: {target}")
    return CaptionsFile.from_json_str(target.read_text(encoding="utf-8"))


def save_captions(captions: CaptionsFile, path_or_video: str | Path) -> Path:
    """Save CaptionsFile to a .capslap.json file or beside a video path."""
    target = Path(path_or_video).expanduser().resolve()
    if not target.name.endswith(".capslap.json"):
        target = target.with_name(f"{target.name}.capslap.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(captions.to_json_str(), encoding="utf-8")
    return target


def edit_captions(
    captions: CaptionsFile,
    preset: str | None = None,
    style_overrides: dict[str, Any] | None = None,
    position_pct: float | None = None,
    clean_syllables: bool = False,
    clean_orphans: bool = False,
    group_phrases: bool = False,
    trim_start_ms: int | None = None,
    trim_end_ms: int | None = None,
    text_replacements: dict[str, str] | None = None,
    segment_patches: list[dict[str, Any]] | None = None,
) -> CaptionsFile:
    """Apply non-destructive edits, presets, cleanup rules, or text patches to CaptionsFile."""
    if preset:
        if preset not in STYLE_PRESETS:
            valid = ", ".join(STYLE_PRESETS.keys())
            raise ValueError(f"Unknown preset '{preset}'. Available: {valid}")
        base = STYLE_PRESETS[preset]
        captions.style = CaptionStyle.from_dict(base.to_dict())

    if style_overrides:
        d = captions.style.to_dict()
        d.update(style_overrides)
        captions.style = CaptionStyle.from_dict(d)

    if position_pct is not None:
        captions.position_overrides = [
            PositionOverride(start_ms=0, end_ms=10**9, y_pct=float(position_pct))
        ]

    if trim_start_ms is not None:
        captions.trim_start_ms = trim_start_ms
    if trim_end_ms is not None:
        captions.trim_end_ms = trim_end_ms

    if clean_syllables:
        captions.segments = combine_separated_syllables(captions.segments)
    if clean_orphans:
        captions.segments = apply_orphan_rules(captions.segments)
    if group_phrases:
        captions.segments = group_words_into_phrases(captions.segments)

    if text_replacements:
        for seg in captions.segments:
            new_text = seg.text
            for old, new in text_replacements.items():
                new_text = new_text.replace(old, new)
            if new_text != seg.text:
                seg.update_text(new_text)

    if segment_patches:
        for patch in segment_patches:
            idx = int(patch.get("index", -1))
            if 0 <= idx < len(captions.segments):
                target_seg = captions.segments[idx]
                if "text" in patch:
                    target_seg.update_text(str(patch["text"]))
                if "startMs" in patch:
                    target_seg.start_ms = int(patch["startMs"])
                if "endMs" in patch:
                    target_seg.end_ms = int(patch["endMs"])

    return captions
