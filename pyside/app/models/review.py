"""Client review: sending captions out and taking the corrections back in.

The review page (review/ at the repo root) opens a sidecar, lets a client fix the
text and times and sends back the same file with a `review` section. The file
stays a valid sidecar; importing it here applies only the captions, cue by cue,
so the local style, positions and word timings stay authoritative.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.models.captions import (
    CaptionsFile,
    CaptionSegment,
    ProjectState,
    set_segment_time,
)

REVIEW_FORMAT = "capslap-review"


def review_export_dict(project: ProjectState) -> dict[str, Any]:
    """The file to send to a client: the sidecar plus which video it belongs to."""
    data = CaptionsFile(
        segments=project.segments,
        position_overrides=project.position_overrides,
        style=project.style,
    ).to_dict()
    if project.video:
        data["video"] = {
            "name": Path(project.video.path).name,
            "durationMs": int(round(project.video.duration_sec * 1000)),
        }
    return data


@dataclass
class ReviewResult:
    status: str = ""
    reviewer: str = ""
    text_changes: int = 0
    time_changes: int = 0
    # (caption number from 1, the caption's text, the comment)
    comments: list[tuple[int, str, str]] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.text_changes or self.time_changes)

    def summary(self) -> str:
        who = f" from {self.reviewer}" if self.reviewer else ""
        if not self.changed and not self.comments:
            return f"Review{who}: approved, no changes."
        parts = []
        if self.text_changes:
            parts.append(f"{self.text_changes} text change(s)")
        if self.time_changes:
            parts.append(f"{self.time_changes} timing change(s)")
        if self.comments:
            parts.append(f"{len(self.comments)} comment(s)")
        return f"Review{who}: " + ", ".join(parts) + "."


class ReviewMismatch(ValueError):
    """The reviewed file doesn't match the captions it would replace."""


def apply_review(segments: list[CaptionSegment], data: dict[str, Any]) -> ReviewResult:
    """Apply a reviewed file's captions to `segments`, in place.

    The review page edits captions but never adds or removes one, so the files
    line up cue by cue; a different count means it was made from other captions
    and nothing is changed.
    """
    reviewed = CaptionsFile.from_dict(data).segments
    if len(reviewed) != len(segments):
        raise ReviewMismatch(
            f"The reviewed file has {len(reviewed)} captions, the project "
            f"{len(segments)}. It was made from different captions."
        )
    review = data.get("review") or {}
    result = ReviewResult(
        status=str(review.get("status", "")),
        reviewer=str(review.get("reviewer", "")).strip(),
    )
    for seg, new in zip(segments, reviewed):
        if (new.start_ms, new.end_ms) != (seg.start_ms, seg.end_ms):
            set_segment_time(seg, new.start_ms, new.end_ms)
            result.time_changes += 1
        if new.text != seg.text:
            # Rebuilds the word timings from ours, not the page's approximation.
            seg.update_text(new.text)
            result.text_changes += 1
    for comment in review.get("comments") or []:
        index = int(comment.get("index", -1))
        if 0 <= index < len(segments):
            text = str(comment.get("text", "")).strip()
            if text:
                result.comments.append((index + 1, segments[index].text, text))
    return result
