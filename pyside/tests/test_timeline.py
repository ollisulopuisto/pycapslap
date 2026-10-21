from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QWidget

from app.models.captions import CaptionSegment
from app.views.timeline import MAX_ZOOM, VisualTimelineWidget


def test_timeline_initial_state(qtbot):
    parent = QWidget()
    timeline = VisualTimelineWidget(parent)
    qtbot.addWidget(timeline)

    assert timeline.duration_ms == 0
    assert timeline.current_position_ms == 0
    assert timeline.segments == []
    assert timeline.selected_segment is None


def test_timeline_seek_on_click(qtbot):
    timeline = VisualTimelineWidget()
    timeline.resize(1000, 80)
    timeline.set_duration(10000)  # 10.0 seconds
    qtbot.addWidget(timeline)
    timeline.show()

    emitted_seeks = []
    timeline.seek_requested.connect(emitted_seeks.append)

    # Click in the middle (x = 500 out of 1000 -> 5000 ms)
    qtbot.mousePress(timeline, Qt.MouseButton.LeftButton, pos=QPoint(500, 40))
    qtbot.mouseRelease(timeline, Qt.MouseButton.LeftButton, pos=QPoint(500, 40))

    assert len(emitted_seeks) > 0
    # Should seek to approx 5000 ms (+/- 100ms)
    assert 4900 <= emitted_seeks[-1] <= 5100


def test_timeline_select_segment(qtbot):
    timeline = VisualTimelineWidget()
    timeline.resize(1000, 80)
    timeline.set_duration(10000)  # 10.0 seconds

    seg1 = CaptionSegment(start_ms=1000, end_ms=3000, text="First segment")
    seg2 = CaptionSegment(start_ms=5000, end_ms=8000, text="Second segment")
    timeline.set_segments([seg1, seg2])
    qtbot.addWidget(timeline)
    timeline.show()

    selected = []
    timeline.segment_selected.connect(selected.append)

    # Click inside seg1 (start: 100px, end: 300px -> click at x = 200)
    qtbot.mousePress(timeline, Qt.MouseButton.LeftButton, pos=QPoint(200, 40))
    qtbot.mouseRelease(timeline, Qt.MouseButton.LeftButton, pos=QPoint(200, 40))

    assert len(selected) > 0
    assert selected[-1] == seg1
    assert timeline.selected_segment == seg1


def _trimmed_timeline(qtbot, start_ms=2000, end_ms=8000):
    timeline = VisualTimelineWidget()
    qtbot.addWidget(timeline)
    timeline.set_duration(10000)
    timeline.set_trim_range(start_ms, end_ms)
    emitted = []
    timeline.trim_range_changed.connect(lambda s, e: emitted.append((s, e)))
    return timeline, emitted


def test_set_trim_start_at_playhead(qtbot):
    timeline, emitted = _trimmed_timeline(qtbot)
    timeline.set_trim_start_at(3500)
    assert (timeline.trim_start_ms, timeline.trim_end_ms) == (3500, 8000)
    assert emitted == [(3500, 8000)]


def test_set_trim_end_at_playhead(qtbot):
    timeline, emitted = _trimmed_timeline(qtbot)
    timeline.set_trim_end_at(6200)
    assert (timeline.trim_start_ms, timeline.trim_end_ms) == (2000, 6200)
    assert emitted == [(2000, 6200)]


def test_trim_start_past_the_end_releases_the_end(qtbot):
    timeline, emitted = _trimmed_timeline(qtbot)
    timeline.set_trim_start_at(9000)
    assert (timeline.trim_start_ms, timeline.trim_end_ms) == (9000, 10000)
    assert emitted == [(9000, 10000)]


def test_trim_end_before_the_start_releases_the_start(qtbot):
    timeline, emitted = _trimmed_timeline(qtbot)
    timeline.set_trim_end_at(1000)
    assert (timeline.trim_start_ms, timeline.trim_end_ms) == (0, 1000)
    assert emitted == [(0, 1000)]


def _cue_timeline(qtbot):
    timeline = VisualTimelineWidget()
    timeline.resize(1000, 80)
    timeline.set_duration(10000)  # 1 px is about 10 ms
    qtbot.addWidget(timeline)
    timeline.show()
    seg1 = CaptionSegment(start_ms=1000, end_ms=3000, text="First")
    seg2 = CaptionSegment(start_ms=5000, end_ms=8000, text="Second")
    timeline.set_segments([seg1, seg2])
    return timeline, seg1, seg2


def _drag(qtbot, timeline, start_x, end_x, y=50):
    qtbot.mousePress(timeline, Qt.MouseButton.LeftButton, pos=QPoint(start_x, y))
    qtbot.mouseMove(timeline, pos=QPoint(end_x, y))
    qtbot.mouseRelease(timeline, Qt.MouseButton.LeftButton, pos=QPoint(end_x, y))


def test_dragging_a_caption_body_moves_it_and_keeps_its_length(qtbot):
    timeline, seg1, _ = _cue_timeline(qtbot)
    retimed = []
    timeline.cue_retimed.connect(retimed.append)

    # seg1 spans x = 100..300; press in its body and drag 100 px right (~1 s).
    _drag(qtbot, timeline, 200, 300)

    assert retimed == [seg1]
    assert abs(seg1.start_ms - 2000) <= 20
    assert seg1.end_ms - seg1.start_ms == 2000


def test_dragging_the_start_edge_stops_at_the_previous_caption(qtbot):
    timeline, seg1, seg2 = _cue_timeline(qtbot)

    # seg2 starts at x = 500. Drag its start far left, into seg1.
    _drag(qtbot, timeline, 500, 50)

    assert seg2.start_ms == seg1.end_ms == 3000
    assert seg2.end_ms == 8000


def test_dragging_the_end_edge_stops_at_the_next_caption(qtbot):
    timeline, seg1, seg2 = _cue_timeline(qtbot)

    # seg1 ends at x = 300. Drag its end far right, into seg2.
    _drag(qtbot, timeline, 300, 900)

    assert seg1.end_ms == seg2.start_ms == 5000
    assert seg1.start_ms == 1000


def test_a_click_on_a_caption_selects_and_seeks_without_retiming(qtbot):
    timeline, seg1, _ = _cue_timeline(qtbot)
    retimed, selected = [], []
    timeline.cue_retimed.connect(retimed.append)
    timeline.segment_selected.connect(selected.append)

    _drag(qtbot, timeline, 200, 201)  # under the drag threshold

    assert retimed == []
    assert selected[-1] is seg1
    assert (seg1.start_ms, seg1.end_ms) == (1000, 3000)


def _touching_timeline(qtbot):
    timeline = VisualTimelineWidget()
    timeline.resize(1000, 80)
    timeline.set_duration(10000)
    qtbot.addWidget(timeline)
    timeline.show()
    seg1 = CaptionSegment(start_ms=1000, end_ms=3000, text="First")
    seg2 = CaptionSegment(start_ms=3000, end_ms=8000, text="Second")
    timeline.set_segments([seg1, seg2])
    return timeline, seg1, seg2


def test_rolling_edit_moves_the_splice_and_both_captions_follow(qtbot):
    timeline, seg1, seg2 = _touching_timeline(qtbot)
    timeline.set_edit_mode("rolling")
    retimed = []
    timeline.cue_retimed.connect(retimed.append)

    # The splice sits at x = 300. Drag it about 1 s to the left.
    _drag(qtbot, timeline, 300, 200)

    assert seg1.end_ms == seg2.start_ms
    assert seg1.end_ms < 2500
    assert seg1.start_ms == 1000
    assert seg2.end_ms == 8000
    assert {id(s) for s in retimed} == {id(seg1), id(seg2)}


def test_regular_edit_changes_only_the_caption_whose_edge_is_dragged(qtbot):
    timeline, seg1, seg2 = _touching_timeline(qtbot)
    timeline.set_edit_mode("regular")

    _drag(qtbot, timeline, 300, 200)

    assert seg1.end_ms < 2500
    assert (seg2.start_ms, seg2.end_ms) == (3000, 8000)


def test_zoom_widens_the_timeline_and_is_limited(qtbot):
    timeline = VisualTimelineWidget()
    qtbot.addWidget(timeline)
    timeline.set_duration(10000)
    timeline.set_fit_width(800)
    assert timeline.width() == 800

    timeline.set_zoom(4)
    assert timeline.width() == 3200

    timeline.set_zoom(1000)
    assert timeline.zoom == MAX_ZOOM
    timeline.set_zoom(0.1)
    assert timeline.zoom == 1.0
