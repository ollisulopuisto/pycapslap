import json

from app.models.captions import (
    CaptionSegment,
    CaptionsFile,
    PositionOverride,
    ProjectState,
    WordSpan,
    combine_separated_syllables,
    shift_word_to_next,
    shift_word_to_prev,
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


def test_caption_segment_update_text_synchronizes_words():
    seg = CaptionSegment(
        start_ms=1000,
        end_ms=3000,
        text="Original words here",
        words=[
            WordSpan(start_ms=1000, end_ms=1600, text="Original"),
            WordSpan(start_ms=1600, end_ms=2300, text=" words"),
            WordSpan(start_ms=2300, end_ms=3000, text=" here"),
        ],
    )

    # 1. Edit with same word count: preserves timings
    seg.update_text("Updated words now")
    assert seg.text == "Updated words now"
    assert len(seg.words) == 3
    assert seg.words[0].text == "Updated"
    assert seg.words[0].start_ms == 1000
    assert seg.words[0].end_ms == 1600
    assert seg.words[2].text == " now"
    assert seg.words[2].end_ms == 3000

    # 2. Edit with different word count: re-interpolates timings
    seg.update_text("Completely rewritten sentence for testing")
    assert seg.text == "Completely rewritten sentence for testing"
    assert len(seg.words) == 5
    assert seg.words[0].text == "Completely"
    assert seg.words[0].start_ms == 1000
    assert seg.words[-1].end_ms == 3000

    # 3. Serialization to_dict includes updated words
    d = seg.to_dict()
    assert d["text"] == "Completely rewritten sentence for testing"
    assert len(d["words"]) == 5
    assert d["words"][0]["text"] == "Completely"


def test_combine_separated_syllables_within_segment():
    # Syllables with trailing hyphens or glue_to_previous should merge into one word
    seg = CaptionSegment(
        start_ms=0,
        end_ms=2000,
        text="sep- a- rat- ed syllables",
        words=[
            WordSpan(start_ms=0, end_ms=300, text="sep-"),
            WordSpan(start_ms=300, end_ms=600, text="a-"),
            WordSpan(start_ms=600, end_ms=900, text="rat-"),
            WordSpan(start_ms=900, end_ms=1300, text="ed"),
            WordSpan(start_ms=1400, end_ms=2000, text="syllables"),
        ],
    )
    result = combine_separated_syllables([seg])
    assert len(result) == 1
    assert len(result[0].words) == 2
    assert result[0].words[0].text == "separated"
    assert result[0].words[0].start_ms == 0
    assert result[0].words[0].end_ms == 1300
    assert result[0].words[1].text == "syllables"
    assert result[0].text == "separated syllables"


def test_combine_separated_syllables_with_glue_to_previous():
    # Finnish word pieces with glue_to_previous
    seg = CaptionSegment(
        start_ms=0,
        end_ms=2000,
        text="kaup pa kes kus",
        words=[
            WordSpan(start_ms=0, end_ms=400, text="kaup"),
            WordSpan(start_ms=400, end_ms=800, text="pa", glue_to_previous=True),
            WordSpan(start_ms=800, end_ms=1200, text="kes", glue_to_previous=True),
            WordSpan(start_ms=1200, end_ms=1800, text="kus", glue_to_previous=True),
        ],
    )
    result = combine_separated_syllables([seg])
    assert len(result) == 1
    assert len(result[0].words) == 1
    assert result[0].words[0].text == "kauppakeskus"
    assert result[0].words[0].start_ms == 0
    assert result[0].words[0].end_ms == 1800
    assert result[0].text == "kauppakeskus"


def test_combine_separated_syllables_across_segment_boundaries():
    # Word broken across segment boundary: seg0 ends with 'korke', seg1 starts with 'alla' (glue)
    seg1 = CaptionSegment(
        start_ms=0,
        end_ms=1000,
        text="tarpeeksi korke",
        words=[
            WordSpan(start_ms=0, end_ms=500, text="tarpeeksi"),
            WordSpan(start_ms=500, end_ms=1000, text="korke"),
        ],
    )
    seg2 = CaptionSegment(
        start_ms=1000,
        end_ms=2500,
        text="alla birtsille",
        words=[
            WordSpan(start_ms=1000, end_ms=1500, text="alla", glue_to_previous=True),
            WordSpan(start_ms=1500, end_ms=2500, text="birtsille"),
        ],
    )
    result = combine_separated_syllables([seg1, seg2])
    assert len(result) == 2
    # seg1 ends with full word 'korkealla'
    assert result[0].text == "tarpeeksi korkealla"
    assert result[0].words[-1].text == "korkealla"
    assert result[0].words[-1].end_ms == 1500
    assert result[0].end_ms == 1500
    # seg2 starts with 'birtsille'
    assert result[1].text == "birtsille"
    assert result[1].words[0].text == "birtsille"
    assert result[1].start_ms == 1500


def test_shift_word_to_prev_and_next():
    seg1 = CaptionSegment(
        start_ms=0,
        end_ms=1000,
        text="Hello",
        words=[WordSpan(start_ms=0, end_ms=1000, text="Hello")],
    )
    seg2 = CaptionSegment(
        start_ms=1100,
        end_ms=2500,
        text="world again",
        words=[
            WordSpan(start_ms=1100, end_ms=1800, text="world"),
            WordSpan(start_ms=1900, end_ms=2500, text="again"),
        ],
    )
    segments = [seg1, seg2]

    # Shift 'world' from seg2 to seg1
    shift_word_to_prev(segments, 1)
    assert len(segments[0].words) == 2
    assert segments[0].text == "Hello world"
    assert segments[0].end_ms == 1800
    assert len(segments[1].words) == 1
    assert segments[1].text == "again"
    assert segments[1].start_ms == 1900

    # Shift 'world' back from seg1 to seg2
    shift_word_to_next(segments, 0)
    assert len(segments[0].words) == 1
    assert segments[0].text == "Hello"
    assert segments[0].end_ms == 1000
    assert len(segments[1].words) == 2
    assert segments[1].text == "world again"
    assert segments[1].start_ms == 1100
