import math
from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtMultimedia import QVideoFrame, QVideoSink
from PySide6.QtWidgets import QWidget

from app.fonts import init_app_fonts
from app.models.captions import CaptionSegment, CaptionStyle


# Mirrors captions.rs: the renderer keeps this much of the frame width free on
# each side, and libass wraps lines against what is left.
CAPTION_SIDE_MARGIN_PCT = 7.0

# The reference frame the renderer scales its font size against
# (captions.rs::calculate_proportional_font_size).
FONT_REFERENCE_W = 608.0
FONT_REFERENCE_H = 1080.0
MIN_RENDER_FONT_PX = 18


def proportional_font_size(frame_w: int, frame_h: int, base_size: int) -> int:
    """The font size the burner would use for this frame — same formula."""
    if frame_w <= 0 or frame_h <= 0:
        return max(MIN_RENDER_FONT_PX, base_size)
    scale = math.sqrt((frame_w * frame_h) / (FONT_REFERENCE_W * FONT_REFERENCE_H))
    return max(MIN_RENDER_FONT_PX, round(base_size * scale))


@dataclass
class SafeAreaRegion:
    label: str
    top: float
    left: float
    width: float
    height: float


@dataclass
class PlatformSafeArea:
    id: str
    name: str
    color: str
    regions: list[SafeAreaRegion]


SAFE_PLATFORMS: dict[str, PlatformSafeArea] = {
    "tiktok": PlatformSafeArea(
        id="tiktok",
        name="TikTok",
        color="#22d3ee",
        regions=[
            SafeAreaRegion("Tabs", top=0.0, left=0.0, width=100.0, height=8.0),
            SafeAreaRegion("Actions", top=42.0, left=84.0, width=16.0, height=46.0),
            SafeAreaRegion("Caption", top=78.0, left=0.0, width=80.0, height=17.0),
            SafeAreaRegion("Nav", top=95.0, left=0.0, width=100.0, height=5.0),
        ],
    ),
    "reels": PlatformSafeArea(
        id="reels",
        name="Instagram Reels",
        color="#e879f9",
        regions=[
            SafeAreaRegion("Header", top=0.0, left=0.0, width=100.0, height=8.0),
            SafeAreaRegion("Actions", top=45.0, left=84.0, width=16.0, height=40.0),
            SafeAreaRegion("Caption", top=80.0, left=0.0, width=82.0, height=12.0),
            SafeAreaRegion("Nav", top=92.0, left=0.0, width=100.0, height=8.0),
        ],
    ),
    "shorts": PlatformSafeArea(
        id="shorts",
        name="YouTube Shorts",
        color="#fb923c",
        regions=[
            SafeAreaRegion("Search", top=0.0, left=0.0, width=100.0, height=7.0),
            SafeAreaRegion("Actions", top=40.0, left=85.0, width=15.0, height=48.0),
            SafeAreaRegion("Title", top=82.0, left=0.0, width=84.0, height=11.0),
            SafeAreaRegion("Nav", top=93.0, left=0.0, width=100.0, height=7.0),
        ],
    ),
}


class VideoCanvasWidget(QWidget):
    """
    Unified, hardware-composited video display and interactive subtitle canvas.
    Renders video frames via QVideoSink and paints subtitles directly onto the
    same surface, eliminating native Cocoa/Metal layer occlusion on macOS.
    """

    anchor_changed = Signal(float)
    # The video's true pixel size, the first time it is known and whenever it
    # changes. Everything about caption layout is measured against it, and it
    # is not known until a frame has actually been decoded.
    video_size_changed = Signal(int, int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setMouseTracking(True)

        self.sink = QVideoSink(self)
        self.sink.videoFrameChanged.connect(self._on_video_frame_changed)

        self._current_frame: QVideoFrame | None = None
        self._paint_opts = QVideoFrame.PaintOptions()
        self._fallback_pixmap: QPixmap | None = None
        self._known_video_size: tuple[int, int] | None = None

        self.current_segment: CaptionSegment | None = None
        self.current_pos_ms: int = 0
        self.anchor_y_pct: float = 80.0
        self.is_dragging: bool = False
        self.style: CaptionStyle = CaptionStyle()
        # The renderer's own pixels for the current cue: libass drawing the
        # same ASS document the burn uses, on a transparent canvas the size of
        # the video frame. When one is present it IS the preview; the vector
        # drawing below is only for the moments there isn't one (playback,
        # dragging, the wait for the first answer).
        self.caption_layer: QPixmap | None = None
        # Layout handed down by the renderer for the current playback position,
        # and the frame size it was computed for.
        self.layout_cue: dict | None = None
        self.layout_frame_size: tuple[int, int] = (1080, 1920)
        # The canvas the export will be burned onto. A format the source does
        # not already have pads it — and the captions are laid out against the
        # padded canvas, not the video — so the editor has to show that canvas
        # or it is previewing a frame the render never produces.
        self.export_canvas_size: tuple[int, int] | None = None
        self.active_safe_platforms: set[str] = {"tiktok", "reels", "shorts"}

        # Initialize fonts database
        init_app_fonts()

    def set_active_safe_platforms(self, platforms: set[str]) -> None:
        self.active_safe_platforms = set(platforms)
        self.update()

    def set_style(self, style: CaptionStyle) -> None:
        self.style = style
        self.update()

    def set_export_canvas(self, size: tuple[int, int] | None) -> None:
        """The frame the render will produce, or None for the video's own."""
        if size and size[0] > 0 and size[1] > 0:
            self.export_canvas_size = (int(size[0]), int(size[1]))
        else:
            self.export_canvas_size = None
        self.update()

    def set_caption_layer(self, pixmap: QPixmap | None) -> None:
        """Hand the canvas libass's own rendering of the current cue."""
        self.caption_layer = pixmap
        self.update()

    def layer_height(self) -> int:
        """Height to ask the renderer for the caption layer in, in pixels.

        The layer only ever gets scaled into the video rectangle, so rendering
        it much larger than that is wasted work — but rounding to a step keeps
        a slow drag of the window edge from invalidating the cache on every
        pixel.
        """
        rect = self._get_canvas_rect()
        px = rect.height() * self.devicePixelRatioF()
        step = 120
        return max(step, int(math.ceil(px / step) * step))

    def set_fallback_pixmap(self, pixmap: QPixmap | None) -> None:
        self._fallback_pixmap = pixmap
        self._announce_video_size()
        self.update()

    def _announce_video_size(self) -> None:
        size = self.get_video_size()
        if size and size != self._known_video_size:
            self._known_video_size = size
            self.video_size_changed.emit(size[0], size[1])

    def get_video_size(self) -> tuple[int, int] | None:
        """The source video's pixel dimensions, if known yet.

        Prefers the live decoded frame. The extracted thumbnail stands in
        while no frame has arrived, but it is scaled to fit 1080 on its long
        edge, so it carries the video's aspect rather than its true size —
        enough for laying captions out, which is proportional to the frame,
        but not a pixel count to trust. Returns None before either arrives.
        """
        if self._current_frame and self._current_frame.isValid():
            sz = self._current_frame.size()
            if sz.width() > 0 and sz.height() > 0:
                return (sz.width(), sz.height())
        if self._fallback_pixmap and not self._fallback_pixmap.isNull():
            sz = self._fallback_pixmap.size()
            if sz.width() > 0 and sz.height() > 0:
                return (sz.width(), sz.height())
        return None

    def set_segment(
        self,
        segment: CaptionSegment | None,
        anchor_y_pct: float = 80.0,
        current_pos_ms: int = 0,
    ) -> None:
        self.current_segment = segment
        self.anchor_y_pct = float(anchor_y_pct)
        self.current_pos_ms = int(current_pos_ms)
        self.update()

    def _on_video_frame_changed(self, frame: QVideoFrame) -> None:
        self._current_frame = frame
        self._announce_video_size()
        self.update()

    def _source_aspect(self) -> float:
        if self._current_frame and self._current_frame.isValid():
            sz = self._current_frame.size()
            if sz.width() > 0 and sz.height() > 0:
                return sz.width() / sz.height()
        if self._fallback_pixmap and not self._fallback_pixmap.isNull():
            sz = self._fallback_pixmap.size()
            if sz.width() > 0 and sz.height() > 0:
                return sz.width() / sz.height()
        return 16.0 / 9.0

    @staticmethod
    def _fit(outer: QRectF, aspect: float) -> QRectF:
        """Largest rectangle of `aspect` centred inside `outer`."""
        if outer.width() <= 0 or outer.height() <= 0 or aspect <= 0:
            return QRectF(0, 0, 0, 0)
        if (outer.width() / outer.height()) > aspect:
            h = outer.height()
            w = h * aspect
        else:
            w = outer.width()
            h = w / aspect
        return QRectF(
            outer.left() + (outer.width() - w) / 2.0,
            outer.top() + (outer.height() - h) / 2.0,
            w,
            h,
        )

    def _get_canvas_rect(self) -> QRectF:
        """Where the exported frame sits on screen."""
        w = float(self.width())
        h = float(self.height())
        if w <= 0 or h <= 0:
            return QRectF(0, 0, 0, 0)

        aspect = self._source_aspect()
        if self.export_canvas_size:
            cw, ch = self.export_canvas_size
            aspect = cw / ch
        return self._fit(QRectF(0, 0, w, h), aspect)

    def _get_video_rect(self) -> QRectF:
        """Where the video itself sits, fitted into the export canvas.

        Mirrors the renderer's "fit" strategy: the source is scaled to fit
        whole and the rest of the canvas is padding.
        """
        canvas = self._get_canvas_rect()
        if self.export_canvas_size is None:
            return canvas
        return self._fit(canvas, self._source_aspect())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self._update_anchor_from_pos(event.position().toPoint())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.is_dragging:
            self._update_anchor_from_pos(event.position().toPoint())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.is_dragging:
            self.is_dragging = False
            self._update_anchor_from_pos(event.position().toPoint())
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _update_anchor_from_pos(self, pos: QPoint) -> None:
        # The renderer's yPct is a fraction of the exported frame, so the
        # pointer has to be read against that frame too, padding included.
        canvas_rect = self._get_canvas_rect()
        if canvas_rect.height() <= 0:
            return
        rel_y = pos.y() - canvas_rect.top()
        pct = (rel_y / canvas_rect.height()) * 100.0
        pct = max(5.0, min(95.0, pct))
        self.anchor_y_pct = round(pct, 1)
        self.anchor_changed.emit(self.anchor_y_pct)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # 1. Background fill for entire widget
        painter.fillRect(self.rect(), QColor(10, 10, 12))

        # Everything about captions — safe zones, the anchor, the layer — is
        # measured against the exported frame. The video is just what happens
        # to be inside it.
        canvas_rect = self._get_canvas_rect()
        video_rect = self._get_video_rect()
        if canvas_rect.width() <= 0 or canvas_rect.height() <= 0:
            return

        # 2. The export canvas: the video, and the padding around it
        painter.fillRect(canvas_rect, QColor(0, 0, 0))
        if self._current_frame and self._current_frame.isValid():
            self._current_frame.paint(painter, video_rect, self._paint_opts)
        elif self._fallback_pixmap and not self._fallback_pixmap.isNull():
            painter.drawPixmap(video_rect.toRect(), self._fallback_pixmap)

        # 3. Render Platform UI Safe Areas (TikTok, Reels, Shorts)
        if self.active_safe_platforms:
            self._paint_safe_areas(painter, canvas_rect)

        # 4. Dragging guidelines
        anchor_y = canvas_rect.top() + (
            canvas_rect.height() * (self.anchor_y_pct / 100.0)
        )
        if self.is_dragging:
            pen = QPen(QColor(99, 102, 241, 230), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawLine(
                int(canvas_rect.left()),
                int(anchor_y),
                int(canvas_rect.right()),
                int(anchor_y),
            )

            badge_text = f"{self.anchor_y_pct:.1f}%"
            badge_font = QFont("Helvetica Neue", 10, QFont.Weight.Bold)
            painter.setFont(badge_font)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(99, 102, 241, 220))
            badge_rect = QRectF(
                canvas_rect.left() + 16,
                max(canvas_rect.top() + 8, anchor_y - 22),
                52,
                20,
            )
            painter.drawRoundedRect(badge_rect, 4, 4)

            painter.setPen(QColor(255, 255, 255))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

        # 5. Render Active Subtitle — the renderer's own pixels when we have
        # them, our approximation of them when we don't.
        if (
            self.caption_layer is not None
            and not self.caption_layer.isNull()
            and not self.is_dragging
        ):
            painter.drawPixmap(
                canvas_rect,
                self.caption_layer,
                QRectF(self.caption_layer.rect()),
            )
        elif self.current_segment and self.current_segment.text.strip():
            self._paint_caption(painter, canvas_rect, anchor_y)

    def _paint_safe_areas(self, painter: QPainter, canvas_rect: QRectF) -> None:
        """Paint the platforms' own interface over the frame that gets exported."""
        painter.save()
        for plat_id in self.active_safe_platforms:
            platform = SAFE_PLATFORMS.get(plat_id)
            if not platform:
                continue

            base_color = QColor(platform.color)
            fill_color = QColor(
                base_color.red(), base_color.green(), base_color.blue(), 35
            )
            pen_color = QColor(
                base_color.red(), base_color.green(), base_color.blue(), 220
            )

            pen = QPen(pen_color, 1.5, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(QBrush(fill_color))

            font = QFont("Helvetica Neue", 8, QFont.Weight.Bold)
            painter.setFont(font)

            for region in platform.regions:
                rx = canvas_rect.left() + canvas_rect.width() * (region.left / 100.0)
                ry = canvas_rect.top() + canvas_rect.height() * (region.top / 100.0)
                rw = canvas_rect.width() * (region.width / 100.0)
                rh = canvas_rect.height() * (region.height / 100.0)
                r_rect = QRectF(rx, ry, rw, rh)

                painter.drawRect(r_rect)

                badge_w = min(rw, 56.0)
                badge_h = 15.0
                badge_rect = QRectF(rx, ry, badge_w, badge_h)
                painter.fillRect(badge_rect, base_color)
                painter.setPen(QColor(0, 0, 0))
                painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, region.label)
                painter.setPen(pen)

        painter.restore()

    # ---- Caption painting -------------------------------------------------
    #
    # Everything below draws the layout the RENDERER produced (the Rust
    # `previewLayout` call), not a second layout of its own. That is the whole
    # point: line breaks, per-line font size, uppercasing, which word is
    # highlighted and the anchor all come from the same code that writes the
    # ASS document, so the preview and the burn agree. Only the drawing —
    # pixels, outline, box — happens here, scaled from frame pixels into the
    # on-screen video rectangle.

    def set_layout_cue(
        self,
        cue: dict | None,
        frame_size: tuple[int, int] | None = None,
    ) -> None:
        """Hand the canvas the renderer's layout for the current position."""
        self.layout_cue = cue
        if frame_size and frame_size[0] > 0 and frame_size[1] > 0:
            self.layout_frame_size = frame_size
        self.update()

    def _fallback_cue(self) -> dict | None:
        """A stand-in layout for before the renderer has answered.

        Mirrors what the burner does with a cue it is not justifying: one
        flowing, uppercased line at the style's proportional size.
        """
        seg = self.current_segment
        if not seg or not seg.text.strip():
            return None
        frame_w, frame_h = self.layout_frame_size
        font_px = proportional_font_size(frame_w, frame_h, self.style.font_size)
        words = [w.text.strip() for w in (seg.words or []) if w.text.strip()]
        if not words:
            words = seg.text.split()
        return {
            "lines": [
                {
                    "words": [
                        {"text": w.upper(), "isHighlighted": False} for w in words
                    ],
                    "fontSizePx": font_px,
                }
            ],
            "yPct": self.anchor_y_pct,
            "anchor": "bottom",
        }

    def _paint_caption(
        self, painter: QPainter, canvas_rect: QRectF, anchor_y: float
    ) -> None:
        cue = self.layout_cue or self._fallback_cue()
        if not cue:
            return

        frame_w, frame_h = self.layout_frame_size
        if frame_w <= 0 or frame_h <= 0:
            return
        scale = canvas_rect.width() / float(frame_w)
        if scale <= 0:
            return

        font_family = self.style.font_name or "Montserrat Black"
        max_width = canvas_rect.width() * (1.0 - 2.0 * CAPTION_SIDE_MARGIN_PCT / 100.0)

        # Lay the cue out line by line. A layout line may still be wider than
        # the box when the renderer left the wrapping to libass (\q0), so wrap
        # it here the same way: greedily, at the same margins.
        drawn_lines: list[tuple[list[dict], QFont, QFontMetrics]] = []
        for line in cue.get("lines", []):
            font_px = max(1.0, float(line.get("fontSizePx", 0)) * scale)
            font = QFont(font_family)
            font.setPixelSize(max(1, round(font_px)))
            metrics = QFontMetrics(font)
            words = line.get("words", [])
            for chunk in _wrap_words(words, metrics, max_width):
                drawn_lines.append((chunk, font, metrics))

        if not drawn_lines:
            return

        line_heights = [metrics.height() for _, _, metrics in drawn_lines]
        total_h = sum(line_heights)

        # The renderer anchors a bottom-aligned block by its bottom edge
        # (\an2), a centered one by its middle (\an5); while dragging, the
        # pointer wins so the caption follows the mouse.
        y_pct = float(cue.get("yPct", self.anchor_y_pct))
        anchor_kind = str(cue.get("anchor", "bottom"))
        if self.is_dragging:
            block_y = anchor_y
            anchor_kind = "center"
        else:
            block_y = canvas_rect.top() + canvas_rect.height() * (y_pct / 100.0)

        if anchor_kind == "center":
            block_top = block_y - total_h / 2.0
        elif anchor_kind == "top":
            block_top = block_y
        else:
            block_top = block_y - total_h

        outline_px = max(1.0, self.style.outline_width * scale)
        outline_pen = QPen(
            QColor(self.style.outline_color or "#000000"), outline_px * 2
        )
        outline_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        text_color = QColor(self.style.text_color or "#ffffff")
        highlight_color = QColor(self.style.highlight_color or "#ffff00")

        y = block_top
        for words, font, metrics in drawn_lines:
            line_text = _join_words(words)
            line_w = metrics.horizontalAdvance(line_text)
            x = canvas_rect.left() + (canvas_rect.width() - line_w) / 2.0
            baseline = y + metrics.ascent()

            if self.style.background_box:
                # BorderStyle 3: an opaque, square-cornered box the height of
                # the line, padded proportionally to the font — libass has no
                # rounded corners, so neither does this.
                pad = max(6.0, round(metrics.height() * 0.22))
                painter.fillRect(
                    QRectF(
                        x - pad,
                        y,
                        line_w + pad * 2,
                        metrics.height(),
                    ),
                    QColor(self.style.outline_color or "#000000"),
                )

            if self.is_dragging:
                painter.setPen(QPen(QColor(99, 102, 241, 255), 1.5))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(QRectF(x - 6, y, line_w + 12, metrics.height()))

            cursor_x = x
            for i, word in enumerate(words):
                text = str(word.get("text", ""))
                if i > 0:
                    text = " " + text
                path = QPainterPath()
                path.addText(cursor_x, baseline, font, text)
                if not self.style.background_box:
                    painter.strokePath(path, outline_pen)
                painter.fillPath(
                    path,
                    highlight_color if word.get("isHighlighted") else text_color,
                )
                cursor_x += metrics.horizontalAdvance(text)

            y += metrics.height()


def _join_words(words: list[dict]) -> str:
    return " ".join(str(w.get("text", "")) for w in words)


def _wrap_words(
    words: list[dict], metrics: QFontMetrics, max_width: float
) -> list[list[dict]]:
    r"""Greedy wrap, mirroring libass \q0 against the same caption box."""
    if not words:
        return []
    lines: list[list[dict]] = []
    current: list[dict] = []
    for word in words:
        candidate = current + [word]
        if current and metrics.horizontalAdvance(_join_words(candidate)) > max_width:
            lines.append(current)
            current = [word]
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines
