from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage, QPixmap
from app.models.captions import CaptionSegment, CaptionStyle, WordSpan
from app.views.video_canvas import VideoCanvasWidget


def test_video_canvas_init(qapp):
    canvas = VideoCanvasWidget()
    assert canvas.sink is not None
    assert canvas.anchor_y_pct == 80.0
    assert canvas.is_dragging is False


def test_video_canvas_set_segment(qapp):
    canvas = VideoCanvasWidget()
    seg = CaptionSegment(start_ms=0, end_ms=1000, text="Hello world")
    canvas.set_segment(seg, anchor_y_pct=60.0, current_pos_ms=500)
    assert canvas.current_segment == seg
    assert canvas.anchor_y_pct == 60.0
    assert canvas.current_pos_ms == 500


def test_video_canvas_drag_anchor(qtbot):
    canvas = VideoCanvasWidget()
    qtbot.addWidget(canvas)
    canvas.resize(800, 600)
    canvas.show()

    emitted = []
    canvas.anchor_changed.connect(emitted.append)

    # Simulate mouse press at y = 300 (50%)
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QPoint(400, 300))
    assert canvas.is_dragging is True
    assert len(emitted) > 0
    assert 45.0 <= emitted[-1] <= 55.0

    # Release
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(400, 300))
    assert canvas.is_dragging is False


def test_video_canvas_paint_with_caption(qtbot):
    canvas = VideoCanvasWidget()
    qtbot.addWidget(canvas)
    canvas.resize(640, 360)

    # Provide fallback pixmap
    img = QImage(640, 360, QImage.Format.Format_ARGB32)
    img.fill(QColor(100, 100, 100))
    canvas.set_fallback_pixmap(QPixmap.fromImage(img))

    seg = CaptionSegment(
        start_ms=0,
        end_ms=2000,
        text="Sample caption",
        words=[
            WordSpan(start_ms=0, end_ms=1000, text="Sample"),
            WordSpan(start_ms=1000, end_ms=2000, text=" caption"),
        ],
    )
    style = CaptionStyle(template_id="karaoke", highlight_color="#00ff00", karaoke=True)
    canvas.set_style(style)
    canvas.set_segment(seg, anchor_y_pct=75.0, current_pos_ms=500)

    canvas.show()
    # Grab should paint without error
    pix = canvas.grab()
    assert not pix.isNull()
    assert pix.width() > 0
