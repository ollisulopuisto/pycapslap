from app.views.timeline import VisualTimelineWidget
from app.views.video_player import Scrubber


def test_scrubber_and_timeline_put_the_playhead_in_the_same_place(qtbot):
    timeline = VisualTimelineWidget()
    timeline.resize(1000, 80)
    timeline.set_duration(10000)
    qtbot.addWidget(timeline)

    scrubber = Scrubber()
    scrubber.resize(1000, 18)
    scrubber.setRange(0, 10000)
    qtbot.addWidget(scrubber)

    for ms in (0, 2500, 5000, 9999, 10000):
        assert abs(scrubber._x_for(ms) - timeline._ms_to_x(ms)) < 0.01, ms


def test_scrubber_reports_the_position_under_the_pointer(qtbot):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    scrubber = Scrubber()
    scrubber.resize(1000, 18)
    scrubber.setRange(0, 10000)
    qtbot.addWidget(scrubber)
    moved = []
    scrubber.sliderMoved.connect(moved.append)

    QTest.mousePress(scrubber, Qt.MouseButton.LeftButton, pos=QPoint(500, 9))
    assert abs(scrubber.value() - 5000) <= 20
    assert moved and abs(moved[-1] - 5000) <= 20
