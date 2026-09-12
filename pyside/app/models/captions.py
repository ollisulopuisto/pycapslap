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

    def update_text(self, new_text: str) -> None:
        self.text = new_text
        tokens = new_text.split()
        if not tokens:
            self.words = []
            return

        if not self.words:
            # Populate words from scratch across segment duration
            duration = max(1, self.end_ms - self.start_ms)
            step = duration // len(tokens)
            new_words = []
            for i, tok in enumerate(tokens):
                w_start = self.start_ms + i * step
                w_end = (
                    self.start_ms + (i + 1) * step
                    if i < len(tokens) - 1
                    else self.end_ms
                )
                lead_space = " " if i > 0 else ""
                new_words.append(
                    WordSpan(
                        start_ms=w_start,
                        end_ms=w_end,
                        text=lead_space + tok.strip(),
                        glue_to_previous=False,
                    )
                )
            self.words = new_words
            return

        if len(tokens) == len(self.words):
            # Same word count: preserve exact timings, update token text
            new_words = []
            for i, tok in enumerate(tokens):
                old_w = self.words[i]
                lead_space = (
                    " "
                    if (
                        i > 0
                        and (old_w.text.startswith(" ") or not tok.startswith(" "))
                    )
                    else ""
                )
                clean_tok = tok.strip()
                new_words.append(
                    WordSpan(
                        start_ms=old_w.start_ms,
                        end_ms=old_w.end_ms,
                        text=lead_space + clean_tok,
                        glue_to_previous=(
                            old_w.glue_to_previous
                            if clean_tok == old_w.text.strip()
                            else False
                        ),
                    )
                )
            self.words = new_words
        else:
            # Word count changed: re-interpolate word timings across segment duration
            duration = max(1, self.end_ms - self.start_ms)
            step = duration // len(tokens)
            new_words = []
            for i, tok in enumerate(tokens):
                w_start = self.start_ms + i * step
                w_end = (
                    self.start_ms + (i + 1) * step
                    if i < len(tokens) - 1
                    else self.end_ms
                )
                lead_space = " " if i > 0 else ""
                new_words.append(
                    WordSpan(
                        start_ms=w_start,
                        end_ms=w_end,
                        text=lead_space + tok.strip(),
                        glue_to_previous=False,
                    )
                )
            self.words = new_words

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


def combine_separated_syllables(
    segments: list[CaptionSegment],
) -> list[CaptionSegment]:
    """
    Combines separated syllables into full words both within segments and across segment boundaries.
    Prevents words from being split in the middle.
    """
    if not segments:
        return []

    # 1. Process each segment internally: merge adjacent syllable tokens
    cleaned_segments: list[CaptionSegment] = []
    for seg in segments:
        new_words: list[WordSpan] = []
        for w in seg.words:
            w_clean = w.text.strip()
            if not w_clean:
                continue
            if not new_words:
                new_words.append(
                    WordSpan(
                        start_ms=w.start_ms,
                        end_ms=w.end_ms,
                        text=w_clean,
                        glue_to_previous=w.glue_to_previous,
                    )
                )
            else:
                prev = new_words[-1]
                prev_clean = prev.text.strip()
                should_glue = w.glue_to_previous or prev_clean.endswith("-")
                if should_glue:
                    combined_text = (
                        prev_clean.rstrip("-") + w_clean.lstrip()
                        if prev_clean.endswith("-")
                        else prev_clean + w_clean.lstrip()
                    )
                    prev.text = combined_text
                    prev.end_ms = max(prev.end_ms, w.end_ms)
                else:
                    new_words.append(
                        WordSpan(
                            start_ms=w.start_ms,
                            end_ms=w.end_ms,
                            text=w_clean,
                            glue_to_previous=False,
                        )
                    )

        text_parts = [w.text for w in new_words]
        new_text = " ".join(text_parts) if new_words else seg.text
        cleaned_segments.append(
            CaptionSegment(
                start_ms=seg.start_ms,
                end_ms=seg.end_ms,
                text=new_text,
                words=new_words,
            )
        )

    # 2. Process across segment boundaries:
    i = 0
    while i < len(cleaned_segments) - 1:
        seg_cur = cleaned_segments[i]
        seg_next = cleaned_segments[i + 1]

        if seg_cur.words and seg_next.words:
            first_next = seg_next.words[0]
            last_cur = seg_cur.words[-1]

            if first_next.glue_to_previous or last_cur.text.endswith("-"):
                merged_text = (
                    last_cur.text.rstrip("-") + first_next.text.lstrip()
                    if last_cur.text.endswith("-")
                    else last_cur.text + first_next.text.lstrip()
                )
                last_cur.text = merged_text
                last_cur.end_ms = max(last_cur.end_ms, first_next.end_ms)
                seg_cur.end_ms = max(seg_cur.end_ms, last_cur.end_ms)
                seg_cur.text = " ".join(w.text for w in seg_cur.words)

                seg_next.words.pop(0)
                if seg_next.words:
                    seg_next.start_ms = seg_next.words[0].start_ms
                    seg_next.text = " ".join(w.text for w in seg_next.words)
                else:
                    cleaned_segments.pop(i + 1)
                    continue
        i += 1

    return cleaned_segments


def shift_word_to_prev(segments: list[CaptionSegment], index: int) -> None:
    """Move the first word of segments[index] to the end of segments[index - 1]."""
    if index <= 0 or index >= len(segments):
        return
    prev_seg = segments[index - 1]
    cur_seg = segments[index]
    if not cur_seg.words:
        return

    word = cur_seg.words.pop(0)
    prev_seg.words.append(word)
    prev_seg.end_ms = word.end_ms
    prev_seg.text = " ".join(w.text.strip() for w in prev_seg.words)

    if cur_seg.words:
        cur_seg.start_ms = cur_seg.words[0].start_ms
        cur_seg.text = " ".join(w.text.strip() for w in cur_seg.words)
    else:
        cur_seg.start_ms = cur_seg.end_ms
        cur_seg.text = ""


def shift_word_to_next(segments: list[CaptionSegment], index: int) -> None:
    """Move the last word of segments[index] to the beginning of segments[index + 1]."""
    if index < 0 or index >= len(segments) - 1:
        return
    cur_seg = segments[index]
    next_seg = segments[index + 1]
    if not cur_seg.words:
        return

    word = cur_seg.words.pop()
    word.text = word.text.strip()
    next_seg.words.insert(0, word)
    next_seg.start_ms = word.start_ms
    next_seg.text = " ".join(w.text.strip() for w in next_seg.words)

    if cur_seg.words:
        cur_seg.end_ms = cur_seg.words[-1].end_ms
        cur_seg.text = " ".join(w.text.strip() for w in cur_seg.words)
    else:
        cur_seg.end_ms = cur_seg.start_ms
        cur_seg.text = ""


FINNISH_ORPHAN_WORDS: set[str] = {
    "ja",
    "tai",
    "vai",
    "sekä",
    "eli",
    "mutta",
    "vaan",
    "jotta",
    "koska",
    "kun",
    "jos",
    "vaikka",
    "kuin",
    "niin",
    "että",
}


def apply_orphan_rules(segments: list[CaptionSegment]) -> list[CaptionSegment]:
    """
    Apply orphan prevention rules across caption segments:
    1. Words like 'tai', 'ja' shouldn't be the last word in a caption, but should start a new caption.
    2. After a comma, do not leave just one single word at the end of a caption cue; break that single word off onto the next caption.
    """
    if len(segments) <= 1:
        return segments

    # Ensure all segments have words populated
    for s in segments:
        if not s.words and s.text.strip():
            s.update_text(s.text)

    changed = True
    passes = 0
    max_passes = 10

    while changed and passes < max_passes:
        changed = False
        passes += 1

        for i in range(len(segments) - 1):
            cur_seg = segments[i]

            if len(cur_seg.words) <= 1:
                continue

            last_word_text = cur_seg.words[-1].text.strip()
            clean_last = last_word_text.strip(".,!?:;-\"'\u201d\u201c\u2019").lower()

            # Rule 1: Trailing conjunction / orphan word
            is_orphan = clean_last in FINNISH_ORPHAN_WORDS

            # Rule 2: Post-comma single word
            # If the second-to-last word ends with a comma/semicolon, leaving a single trailing word
            has_trailing_single_after_comma = False
            if len(cur_seg.words) >= 2:
                sec_last_text = cur_seg.words[-2].text.strip()
                if sec_last_text.endswith(",") or sec_last_text.endswith(";"):
                    has_trailing_single_after_comma = True

            if is_orphan or has_trailing_single_after_comma:
                shift_word_to_next(segments, i)
                changed = True

    return segments


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

    @property
    def video_path(self) -> str | None:
        return self.video.path if self.video else None

    def get_default_sidecar_path(self) -> str | None:
        return self.sidecar_path

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

    def get_anchor_y_for_segment(
        self, seg: CaptionSegment, default_y: float = 80.0
    ) -> float:
        midpoint = (seg.start_ms + seg.end_ms) // 2
        for ov in self.position_overrides:
            if ov.start_ms <= midpoint <= ov.end_ms:
                return ov.y_pct
        return default_y

    def set_segment_position_override(self, seg: CaptionSegment, y_pct: float) -> None:
        midpoint = (seg.start_ms + seg.end_ms) // 2
        # Remove any existing override covering this midpoint
        self.position_overrides = [
            ov
            for ov in self.position_overrides
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
        target = (
            Path(path)
            if path
            else (Path(self.sidecar_path) if self.sidecar_path else None)
        )
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
        target = (
            Path(path)
            if path
            else (Path(self.sidecar_path) if self.sidecar_path else None)
        )
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
