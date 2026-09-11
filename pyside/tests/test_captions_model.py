import json

from app.models.captions import (
    CaptionSegment,
    CaptionsFile,
    PositionOverride,
    ProjectState,
    WordSpan,
)


def test_captions_file_roundtrip():
    seg1 = CaptionSegment(
        start_ms=1000,
        end_ms=2500,
        text="Hello world",
        words=[
            WordSpan(start_ms=1000, end_ms=1700, text="Hello"),
            WordSpan(start_ms=1700, end_ms=2500, text=" world"),
        ],
    )
    seg2 = CaptionSegment(start_ms=2600, end_ms=4000, text="Second line")
    ov = PositionOverride(start_ms=900, end_ms=3000, y_pct=42.5)

    file_data = CaptionsFile(segments=[seg1, seg2], position_overrides=[ov])
    d = file_data.to_dict()

    assert "segments" in d
    assert "positionOverrides" in d
    assert len(d["segments"]) == 2
    assert d["segments"][0]["startMs"] == 1000
    assert d["segments"][0]["words"][0]["text"] == "Hello"
    assert d["positionOverrides"][0]["yPct"] == 42.5

    # Roundtrip from dict
    restored = CaptionsFile.from_dict(d)
    assert len(restored.segments) == 2
    assert restored.segments[0].text == "Hello world"
    assert len(restored.position_overrides) == 1
    assert restored.position_overrides[0].y_pct == 42.5


def test_load_legacy_bare_array_sidecar():
    legacy_json = json.dumps([{"startMs": 0, "endMs": 1500, "text": "Legacy cue"}])
    loaded = CaptionsFile.from_json_str(legacy_json)
    assert len(loaded.segments) == 1
    assert loaded.segments[0].text == "Legacy cue"
    assert loaded.position_overrides == []


def test_project_state_get_active_segment():
    seg1 = CaptionSegment(start_ms=1000, end_ms=2000, text="First")
    seg2 = CaptionSegment(start_ms=2500, end_ms=3500, text="Second")
    proj = ProjectState(segments=[seg1, seg2])

    assert proj.get_active_segment(500) is None
    assert proj.get_active_segment(1000) == seg1
    assert proj.get_active_segment(1500) == seg1
    assert proj.get_active_segment(2000) == seg1
    assert proj.get_active_segment(2200) is None
    assert proj.get_active_segment(3000) == seg2


def test_position_override_for_segment():
    seg = CaptionSegment(start_ms=1000, end_ms=2000, text="Midpoint is 1500")
    ov1 = PositionOverride(
        start_ms=500, end_ms=1200, y_pct=20.0
    )  # does not cover midpoint 1500
    ov2 = PositionOverride(
        start_ms=1200, end_ms=1800, y_pct=75.0
    )  # covers midpoint 1500

    proj = ProjectState(segments=[seg], position_overrides=[ov1, ov2])
    # Default is 80.0
    assert proj.get_anchor_y_for_segment(seg, default_y=80.0) == 75.0

    # Without matching override
    proj.position_overrides = [ov1]
    assert proj.get_anchor_y_for_segment(seg, default_y=80.0) == 80.0


def test_set_override_for_active_segment():
    seg = CaptionSegment(start_ms=1000, end_ms=2000, text="Test")
    proj = ProjectState(segments=[seg])
    assert proj.is_dirty is False

    proj.set_segment_position_override(seg, 35.0)
    assert proj.is_dirty is True
    assert len(proj.position_overrides) == 1
    assert proj.position_overrides[0].y_pct == 35.0
    assert proj.position_overrides[0].start_ms == 1000
    assert proj.position_overrides[0].end_ms == 2000
