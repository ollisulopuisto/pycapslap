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

    # Lines are wrapped against the same caption box the renderer uses.
    from PySide6.QtGui import QFont, QFontMetrics

    from app.views.video_canvas import CAPTION_SIDE_MARGIN_PCT, _join_words, _wrap_words

    font = QFont("Montserrat")
    font.setPixelSize(20)
    metrics = QFontMetrics(font)
    max_w = v_rect.width() * (1.0 - 2.0 * CAPTION_SIDE_MARGIN_PCT / 100.0)

    layout_words = [
        {"text": w.upper(), "isHighlighted": False} for w in long_text.split()
    ]
    lines = _wrap_words(layout_words, metrics, max_w)
    assert len(lines) > 1, "long text should wrap on a 9:16 frame"
    for line in lines:
        # A single word wider than the box is the only allowed overflow.
        assert len(line) == 1 or metrics.horizontalAdvance(_join_words(line)) <= max_w


def test_video_canvas_wraps_like_the_renderer(qtbot):
    from PySide6.QtGui import QFont, QFontMetrics

    from app.views.video_canvas import _join_words, _wrap_words

    canvas = VideoCanvasWidget()
    qtbot.addWidget(canvas)

    font = QFont("Montserrat")
    font.setPixelSize(18)
    metrics = QFontMetrics(font)

    words = [
        {"text": t, "isHighlighted": False}
        for t in "WELCOME TO PYCAPSLAP HIGH PERFORMANCE NATIVE VIDEO CAPTIONS".split()
    ]
    lines = _wrap_words(words, metrics, 200.0)

    assert len(lines) >= 2
    for line in lines:
        assert len(line) == 1 or metrics.horizontalAdvance(_join_words(line)) <= 200.0
    # Wrapping only ever moves whole words between lines.
    assert sum(len(line) for line in lines) == len(words)


def test_video_canvas_draws_the_renderers_layout(qtbot):
    canvas = VideoCanvasWidget()
    qtbot.addWidget(canvas)
    canvas.resize(400, 700)

    img = QImage(1080, 1920, QImage.Format.Format_ARGB32)
    img.fill(QColor(40, 40, 40))
    canvas.set_fallback_pixmap(QPixmap.fromImage(img))

    seg = CaptionSegment(
        start_ms=0,
        end_ms=2000,
        text="vähän niinku huonosta miesvalinnasta",
        words=[WordSpan(0, 2000, "vähän niinku huonosta miesvalinnasta")],
    )
    canvas.set_segment(seg, anchor_y_pct=80.0, current_pos_ms=500)

    # A justified cue: two lines, each with its own size, as captions.rs emits.
    canvas.set_layout_cue(
        {
            "lines": [
                {
                    "words": [
                        {"text": "VÄHÄN", "isHighlighted": False},
                        {"text": "NIINKU", "isHighlighted": False},
                    ],
                    "fontSizePx": 114,
                },
                {
                    "words": [
                        {"text": "HUONOSTA", "isHighlighted": False},
                        {"text": "MIESVALINNASTA", "isHighlighted": True},
                    ],
                    "fontSizePx": 57,
                },
            ],
            "yPct": 80.0,
            "anchor": "bottom",
        },
        (1080, 1920),
    )
    canvas.show()

    assert not canvas.grab().isNull()
    assert canvas.layout_cue is not None
    assert canvas.layout_frame_size == (1080, 1920)


def test_video_canvas_fallback_cue_matches_the_renderer(qtbot):
    canvas = VideoCanvasWidget()
    qtbot.addWidget(canvas)

    seg = CaptionSegment(
        start_ms=0,
        end_ms=1000,
        text="pieni testi",
        words=[WordSpan(0, 500, "pieni"), WordSpan(500, 1000, "testi")],
    )
    canvas.set_segment(seg, anchor_y_pct=80.0, current_pos_ms=100)
    canvas.layout_frame_size = (1080, 1920)

    cue = canvas._fallback_cue()
    assert cue is not None
    # The burn uppercases every caption, so the stand-in has to as well.
    assert [w["text"] for w in cue["lines"][0]["words"]] == ["PIENI", "TESTI"]
    # ...and use the renderer's proportional size, not the raw style size.
    from app.views.video_canvas import proportional_font_size

    assert cue["lines"][0]["fontSizePx"] == proportional_font_size(
        1080, 1920, canvas.style.font_size
    )


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


def test_canvas_draws_the_renderers_layer_instead_of_its_own_text(qtbot):
    """A layer from the renderer wins over the canvas's own painting.

    The painted version can only approximate libass; whenever the real pixels
    are available they are the preview, so the editor shows what the burn
    produces rather than a lookalike.
    """
    from PySide6.QtGui import QColor, QPixmap

    canvas = VideoCanvasWidget()
    qtbot.addWidget(canvas)
    canvas.resize(360, 640)
    canvas.set_segment(
        CaptionSegment(start_ms=0, end_ms=1000, text="Ja sitten"), anchor_y_pct=80.0
    )
    canvas.set_layout_cue(
        {
            "lines": [
                {"words": [{"text": "JA", "isHighlighted": False}], "fontSizePx": 40}
            ],
            "yPct": 80.0,
            "anchor": "bottom",
        },
        (1080, 1920),
    )

    layer = QPixmap(1080, 1920)
    layer.fill(QColor(0, 255, 0, 255))
    canvas.set_caption_layer(layer)
    assert canvas.caption_layer is layer

    painted = QPixmap(canvas.size())
    canvas.render(painted)
    image = painted.toImage()
    # The layer covers the whole frame, so any pixel inside the video
    # rectangle is the layer's if it was drawn at all.
    center = image.pixelColor(image.width() // 2, image.height() // 2)
    assert (center.red(), center.green(), center.blue()) == (0, 255, 0)

    # Dragging goes back to the painted version, which follows the pointer.
    canvas.is_dragging = True
    painted2 = QPixmap(canvas.size())
    canvas.render(painted2)
    center2 = painted2.toImage().pixelColor(image.width() // 2, image.height() // 2)
    assert (center2.red(), center2.green(), center2.blue()) != (0, 255, 0)


def test_layer_height_is_quantized(qtbot):
    canvas = VideoCanvasWidget()
    qtbot.addWidget(canvas)
    canvas.resize(360, 640)
    first = canvas.layer_height()
    canvas.resize(362, 643)
    assert canvas.layer_height() == first
    assert first % 120 == 0


def test_export_canvas_pads_the_video_and_carries_the_captions(qtbot):
    """A 9:16 export of a 16:9 source is a taller frame with the video inside.

    The captions are laid out against that taller frame, so the editor has to
    show it — otherwise it previews a frame the render never produces.
    """
    from PySide6.QtGui import QPixmap

    canvas = VideoCanvasWidget()
    qtbot.addWidget(canvas)
    canvas.resize(400, 800)
    # A 16:9 source, via the thumbnail fallback.
    source = QPixmap(1920, 1080)
    source.fill()
    canvas.set_fallback_pixmap(source)

    # No export canvas: the video fills what the canvas draws.
    assert canvas._get_canvas_rect() == canvas._get_video_rect()

    canvas.set_export_canvas((1920, 3414))
    canvas_rect = canvas._get_canvas_rect()
    video_rect = canvas._get_video_rect()
    assert canvas_rect.height() > video_rect.height()
    assert abs(canvas_rect.width() - video_rect.width()) < 1.0
    # Padding above and below, video centred.
    assert video_rect.top() > canvas_rect.top()
    assert video_rect.bottom() < canvas_rect.bottom()
    assert abs(canvas_rect.height() / canvas_rect.width() - 3414 / 1920) < 0.01


def test_anchor_is_read_against_the_export_canvas(qtbot):
    """yPct is a fraction of the exported frame, padding included."""
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QPixmap

    canvas = VideoCanvasWidget()
    qtbot.addWidget(canvas)
    canvas.resize(400, 800)
    source = QPixmap(1920, 1080)
    source.fill()
    canvas.set_fallback_pixmap(source)
    canvas.set_export_canvas((1080, 1920))

    rect = canvas._get_canvas_rect()
    midpoint = QPoint(int(rect.center().x()), int(rect.top() + rect.height() * 0.5))
    canvas._update_anchor_from_pos(midpoint)
    assert abs(canvas.anchor_y_pct - 50.0) < 1.0
