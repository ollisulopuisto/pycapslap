import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.models.project import VideoMetadata


@dataclass
class WordSpan:
    start_ms: int
    end_ms: int
    text: str
    glue_to_previous: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "startMs": self.start_ms,
            "endMs": self.end_ms,
            "text": self.text,
        }
        if self.glue_to_previous:
            d["glueToPrevious"] = True
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "WordSpan":
        return cls(
            start_ms=int(d.get("startMs", 0)),
            end_ms=int(d.get("endMs", 0)),
            text=str(d.get("text", "")),
            glue_to_previous=bool(d.get("glueToPrevious", False)),
        )


@dataclass
class CaptionSegment:
    start_ms: int
    end_ms: int
    text: str
    words: list[WordSpan] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "startMs": self.start_ms,
            "endMs": self.end_ms,
            "text": self.text,
        }
        if self.words:
            d["words"] = [w.to_dict() for w in self.words]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CaptionSegment":
        words_data = d.get("words", [])
        words = [WordSpan.from_dict(w) for w in words_data]
        return cls(
            start_ms=int(d.get("startMs", 0)),
            end_ms=int(d.get("endMs", 0)),
            text=str(d.get("text", "")),
            words=words,
        )


@dataclass
class PositionOverride:
    start_ms: int
    end_ms: int
    y_pct: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "startMs": self.start_ms,
            "endMs": self.end_ms,
            "yPct": float(self.y_pct),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PositionOverride":
        return cls(
            start_ms=int(d.get("startMs", 0)),
            end_ms=int(d.get("endMs", 0)),
            y_pct=float(d.get("yPct", 80.0)),
        )


@dataclass
class CaptionStyle:
    template_id: str = "oneliner"
    font_name: str = "Montserrat Black"
    font_size: int = 65
    text_color: str = "#ffffff"
    highlight_color: str = "#ffff00"
    outline_color: str = "#000000"
    outline_width: int = 3
    karaoke: bool = False
    glow_effect: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "templateId": self.template_id,
            "fontName": self.font_name,
            "fontSize": self.font_size,
            "textColor": self.text_color,
            "highlightColor": self.highlight_color,
            "outlineColor": self.outline_color,
            "outlineWidth": self.outline_width,
            "karaoke": self.karaoke,
            "glowEffect": self.glow_effect,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CaptionStyle":
        return cls(
            template_id=str(d.get("templateId", "oneliner")),
            font_name=str(d.get("fontName", "Montserrat Black")),
            font_size=int(d.get("fontSize", 65)),
            text_color=str(d.get("textColor", "#ffffff")),
            highlight_color=str(d.get("highlightColor", "#ffff00")),
            outline_color=str(d.get("outlineColor", "#000000")),
            outline_width=int(d.get("outlineWidth", 3)),
            karaoke=bool(d.get("karaoke", False)),
            glow_effect=bool(d.get("glowEffect", True)),
        )


STYLE_PRESETS: dict[str, CaptionStyle] = {
    "oneliner": CaptionStyle(
        template_id="oneliner",
        font_name="Montserrat Black",
        font_size=65,
        text_color="#ffffff",
        highlight_color="#ffff00",
        outline_color="#000000",
        outline_width=3,
        karaoke=False,
    ),
    "karaoke": CaptionStyle(
        template_id="karaoke",
        font_name="Komika Axis",
        font_size=65,
        text_color="#ffffff",
        highlight_color="#00f924",
        outline_color="#000000",
        outline_width=3,
        karaoke=True,
    ),
    "vibrant": CaptionStyle(
        template_id="vibrant",
        font_name="Roboto Bold",
        font_size=65,
        text_color="#eaeaea",
        highlight_color="#7ef1c5",
        outline_color="#000000",
        outline_width=3,
        karaoke=False,
    ),
    "storyteller": CaptionStyle(
        template_id="storyteller",
        font_name="Montserrat Black",
        font_size=65,
        text_color="#ffffff",
        highlight_color="#f59e0b",
        outline_color="#000000",
        outline_width=3,
        karaoke=False,
    ),
}


@dataclass
class CaptionsFile:
    segments: list[CaptionSegment] = field(default_factory=list)
    position_overrides: list[PositionOverride] = field(default_factory=list)
    style: CaptionStyle = field(default_factory=CaptionStyle)

    def to_dict(self) -> dict[str, Any]:
        return {
            "segments": [s.to_dict() for s in self.segments],
            "positionOverrides": [o.to_dict() for o in self.position_overrides],
            "style": self.style.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CaptionsFile":
        segments_raw = d.get("segments", [])
        segments = [CaptionSegment.from_dict(s) for s in segments_raw]
        overrides_raw = d.get("positionOverrides", [])
        overrides = [PositionOverride.from_dict(o) for o in overrides_raw]
        style_raw = d.get("style", {})
        style = CaptionStyle.from_dict(style_raw) if style_raw else CaptionStyle()
        return cls(segments=segments, position_overrides=overrides, style=style)

    @classmethod
    def from_json_str(cls, json_str: str) -> "CaptionsFile":
        data = json.loads(json_str)
        if isinstance(data, list):
            # Legacy format: bare array of segments
            segments = [CaptionSegment.from_dict(s) for s in data]
            return cls(segments=segments, position_overrides=[])
        elif isinstance(data, dict):
            return cls.from_dict(data)
        return cls()

    def to_json_str(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


@dataclass
class ProjectState:
    video: VideoMetadata | None = None
    sidecar_path: str | None = None
    segments: list[CaptionSegment] = field(default_factory=list)
    position_overrides: list[PositionOverride] = field(default_factory=list)
    style: CaptionStyle = field(default_factory=CaptionStyle)
    is_dirty: bool = False

    def load_video(self, path: str, probe_dict: dict[str, Any]) -> None:
        self.video = VideoMetadata(
            path=path,
            width=probe_dict.get("width") or 0,
            height=probe_dict.get("height") or 0,
            duration_sec=probe_dict.get("duration") or 0.0,
            fps=probe_dict.get("fps") or 0.0,
            codec=probe_dict.get("codec") or "",
            is_hdr=probe_dict.get("isHdr") or False,
        )
        self.sidecar_path = f"{path}.capslap.json"
        self.is_dirty = False

    def get_active_segment(self, timestamp_ms: int) -> CaptionSegment | None:
        for seg in self.segments:
            if seg.start_ms <= timestamp_ms <= seg.end_ms:
                return seg
        return None

    def get_anchor_y_for_segment(self, seg: CaptionSegment, default_y: float = 80.0) -> float:
        midpoint = (seg.start_ms + seg.end_ms) // 2
        for ov in self.position_overrides:
            if ov.start_ms <= midpoint <= ov.end_ms:
                return ov.y_pct
        return default_y

    def set_segment_position_override(self, seg: CaptionSegment, y_pct: float) -> None:
        midpoint = (seg.start_ms + seg.end_ms) // 2
        # Remove any existing override covering this midpoint
        self.position_overrides = [
            ov for ov in self.position_overrides
            if not (ov.start_ms <= midpoint <= ov.end_ms)
        ]
        # Add new override covering this segment span
        self.position_overrides.append(
            PositionOverride(
                start_ms=seg.start_ms,
                end_ms=seg.end_ms,
                y_pct=round(y_pct, 1),
            )
        )
        self.is_dirty = True

    def load_sidecar(self, path: str | Path | None = None) -> bool:
        target = Path(path) if path else (Path(self.sidecar_path) if self.sidecar_path else None)
        if not target or not target.exists():
            return False
        try:
            content = target.read_text(encoding="utf-8")
            cf = CaptionsFile.from_json_str(content)
            self.segments = cf.segments
            self.position_overrides = cf.position_overrides
            self.style = cf.style
            self.is_dirty = False
            return True
        except (OSError, json.JSONDecodeError):
            return False

    def save_sidecar(self, path: str | Path | None = None) -> bool:
        target = Path(path) if path else (Path(self.sidecar_path) if self.sidecar_path else None)
        if not target:
            return False
        try:
            cf = CaptionsFile(
                segments=self.segments,
                position_overrides=self.position_overrides,
                style=self.style,
            )
            target.write_text(cf.to_json_str(), encoding="utf-8")
            self.is_dirty = False
            return True
        except OSError:
            return False
