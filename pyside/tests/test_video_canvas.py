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


def test_video_canvas_portrait_video_caption_fit(qtbot):
    canvas = VideoCanvasWidget()
    qtbot.addWidget(canvas)
    canvas.resize(400, 700)

    # 9:16 portrait video frame (1080x1920 aspect)
    img = QImage(1080, 1920, QImage.Format.Format_ARGB32)
    img.fill(QColor(40, 40, 40))
    canvas.set_fallback_pixmap(QPixmap.fromImage(img))

    long_text = "This is a very long caption text that definitely exceeds the width of a narrow vertical video"
    words = [
        WordSpan(start_ms=i * 300, end_ms=(i + 1) * 300, text=f" {w}" if i > 0 else w)
        for i, w in enumerate(long_text.split())
    ]
    seg = CaptionSegment(start_ms=0, end_ms=5000, text=long_text, words=words)
    canvas.set_segment(seg, anchor_y_pct=80.0, current_pos_ms=1000)

    canvas.show()
    v_rect = canvas._get_video_rect()
    assert v_rect.width() > 0
    # Aspect ratio should be 9:16
    assert abs((v_rect.width() / v_rect.height()) - (1080 / 1920)) < 0.05

    # Test that grab renders cleanly and wrapped lines fit inside video_rect
    pix = canvas.grab()
    assert not pix.isNull()

    # Verify wrapping logic on karaoke words
    from PySide6.QtGui import QFont, QFontMetrics

    font = QFont("Montserrat", 16, QFont.Weight.Black)
    metrics = QFontMetrics(font)
    max_w = v_rect.width() * 0.85
    wrapped_lines = canvas._wrap_karaoke_words(words, metrics, max_w)
    assert len(wrapped_lines) > 1, (
        "Long text should wrap into multiple lines on 9:16 video"
    )
    for line in wrapped_lines:
        line_w = canvas._measure_word_span_line(line, metrics)
        assert line_w <= max_w


def test_video_canvas_plain_text_wrapping(qtbot):
    canvas = VideoCanvasWidget()
    qtbot.addWidget(canvas)
    canvas.resize(600, 400)

    from PySide6.QtGui import QFont, QFontMetrics

    font = QFont("Montserrat", 18, QFont.Weight.Black)
    metrics = QFontMetrics(font)

    tokens = "Welcome to PyCapSlap high performance native video captions".split()
    max_w = 200.0  # Narrow width constraint
    lines = canvas._wrap_plain_tokens(tokens, metrics, max_w)
    assert len(lines) >= 2
    for line in lines:
        assert metrics.horizontalAdvance(line) <= max_w


def test_video_canvas_karaoke_wrapping_keeps_syllables_together(qtbot):
    canvas = VideoCanvasWidget()
    qtbot.addWidget(canvas)

    from PySide6.QtGui import QFont, QFontMetrics

    font = QFont("Montserrat", 18, QFont.Weight.Black)
    metrics = QFontMetrics(font)

    words = [
        WordSpan(start_ms=0, end_ms=500, text="Lyhyt"),
        WordSpan(start_ms=500, end_ms=1000, text=" alku"),
        WordSpan(start_ms=1000, end_ms=1500, text=" pitkä"),
        WordSpan(start_ms=1500, end_ms=2000, text="sana", glue_to_previous=True),
    ]
    adv_prefix = metrics.horizontalAdvance("Lyhyt alku")
    adv_pitka = metrics.horizontalAdvance(" pitkä")
    max_w = adv_prefix + adv_pitka - 5

    lines = canvas._wrap_karaoke_words(words, metrics, max_w)
    assert len(lines) == 2
    # Second line must hold both parts of the glued word together
    assert len(lines[1]) == 2
    assert lines[1][0].text == " pitkä"
    assert lines[1][1].text == "sana"


def test_video_canvas_safe_platforms(qtbot):
    canvas = VideoCanvasWidget()
    qtbot.addWidget(canvas)
    canvas.resize(360, 640)
    canvas.show()

    assert hasattr(canvas, "set_active_safe_platforms")
    # On by default: all three platforms' safe zones are respected unless
    # explicitly turned off.
    assert canvas.active_safe_platforms == {"tiktok", "reels", "shorts"}

    canvas.set_active_safe_platforms(set())
    assert canvas.active_safe_platforms == set()

    canvas.set_active_safe_platforms({"tiktok", "reels", "shorts"})
    assert canvas.active_safe_platforms == {"tiktok", "reels", "shorts"}

    # Paint event with safe platforms enabled
    canvas.repaint()
