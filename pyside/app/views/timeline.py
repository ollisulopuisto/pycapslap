from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import QFrame, QScrollArea, QWidget

from app.models.captions import (
    MIN_SEGMENT_MS,
    CaptionSegment,
    clamped_segment_time,
    set_segment_time,
)

# Caption blocks start below the time ruler.
_TRACK_TOP = 24
# A press this close to a block's edge takes hold of that edge, not the body.
_CUE_EDGE_PX = 6
# Less movement than this is a click, not a drag.
_CUE_DRAG_THRESHOLD_PX = 3
# Two captions whose edges are this close (about a frame) share a splice.
_ADJACENT_MS = 40
MAX_ZOOM = 40.0
# Seconds between ruler ticks; the first one that leaves room for a label.
_TICK_STEPS = (1, 2, 5, 10, 15, 30, 60, 120, 300, 600)
_MIN_TICK_PX = 70


@dataclass
class _CueDrag:
    seg: CaptionSegment
    mode: str  # "start", "end" or "move"
    press_x: float
    start_ms: int
    end_ms: int
    moved: bool = False
    # The caption sharing the edge being dragged, when rolling; it moves too.
    partner: "CaptionSegment | None" = None


class VisualTimelineWidget(QWidget):
    seek_requested = Signal(int)
    segment_selected = Signal(object)
    trim_range_changed = Signal(int, int)
    # A caption block was dragged to a new time; the cue already holds it.
    cue_retimed = Signal(object)
    # Ctrl + wheel: a zoom factor and the x it should keep in place.
    zoom_requested = Signal(float, float)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(84)
        self.setMouseTracking(True)

        self.duration_ms: int = 0
        self.current_position_ms: int = 0
        self.segments: list[CaptionSegment] = []
        self.selected_segment: CaptionSegment | None = None
        self._is_scrubbing: bool = False
        self.trim_start_ms = 0
        self.trim_end_ms = 0
        self._trim_drag_handle: str | None = None
        self._cue_drag: _CueDrag | None = None
        self.edit_mode = "regular"
        self.zoom = 1.0
        self._fit_width = 0
        self._trim_min_gap_ms = 100
        self.setToolTip(
            "Drag the blue trim handles to shorten the beginning or end,\n"
            "or press I / O to set the start / end at the playhead.\n"
            "Drag a caption's edges to retime it, or its body to move it.\n"
            "Ctrl + scroll zooms the timeline"
        )

    def set_edit_mode(self, mode: str) -> None:
        """'regular': an edge changes only its own caption. 'rolling': an edge
        shared with the next or previous caption moves the splice, so one grows
        as the other shrinks."""
        if mode not in ("regular", "rolling"):
            raise ValueError(f"unknown edit mode: {mode}")
        self.edit_mode = mode

    def set_fit_width(self, width: int) -> None:
        """The width that shows the whole video at zoom 1."""
        self._fit_width = max(0, int(width))
        self._apply_width()

    def set_zoom(self, zoom: float) -> None:
        self.zoom = min(MAX_ZOOM, max(1.0, zoom))
        self._apply_width()

    def _apply_width(self) -> None:
        if self._fit_width > 0:
            self.setFixedWidth(max(1, int(self._fit_width * self.zoom)))
        self.update()

    def _tick_step_sec(self) -> int:
        seconds = max(1e-9, self.duration_ms / 1000)
        px_per_sec = self.width() / seconds
        for step in _TICK_STEPS:
            if step * px_per_sec >= _MIN_TICK_PX:
                return step
        return _TICK_STEPS[-1]

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and self.duration_ms:
            factor = 1.25 if event.angleDelta().y() > 0 else 0.8
            self.zoom_requested.emit(factor, event.position().x())
            event.accept()
        else:
            super().wheelEvent(event)

    def set_duration(self, duration_ms: int) -> None:
        old_duration = self.duration_ms
        self.duration_ms = max(0, int(duration_ms))
        if old_duration == 0 or self.trim_end_ms == old_duration:
            self.trim_end_ms = self.duration_ms
        self.trim_start_ms = min(
            self.trim_start_ms, max(0, self.duration_ms - self._trim_min_gap_ms)
        )
        self.trim_end_ms = max(
            self.trim_start_ms + min(self._trim_min_gap_ms, self.duration_ms),
            min(self.trim_end_ms, self.duration_ms),
        )
        self.update()

    def set_trim_range(self, start_ms: int, end_ms: int) -> None:
        gap = min(self._trim_min_gap_ms, self.duration_ms)
        start = max(0, min(int(start_ms), max(0, self.duration_ms - gap)))
        end = max(start + gap, min(int(end_ms), self.duration_ms))
        self.trim_start_ms, self.trim_end_ms = start, end
        self.update()

    def set_trim_start_at(self, pos_ms: int) -> None:
        """Start the trim at `pos_ms` (the I key). Past the current end, the end goes back
        to the video's end rather than dragging along."""
        gap = min(self._trim_min_gap_ms, self.duration_ms)
        end = self.trim_end_ms if pos_ms < self.trim_end_ms - gap else self.duration_ms
        self.set_trim_range(pos_ms, end)
        self.trim_range_changed.emit(self.trim_start_ms, self.trim_end_ms)

    def set_trim_end_at(self, pos_ms: int) -> None:
        """End the trim at `pos_ms` (the O key). Before the current start, the start goes
        back to the video's start."""
        gap = min(self._trim_min_gap_ms, self.duration_ms)
        start = self.trim_start_ms if pos_ms > self.trim_start_ms + gap else 0
        self.set_trim_range(start, pos_ms)
        self.trim_range_changed.emit(self.trim_start_ms, self.trim_end_ms)

    def reset_trim_range(self) -> None:
        self.set_trim_range(0, self.duration_ms)

    def set_position(self, position_ms: int) -> None:
        if not self._is_scrubbing:
            old_x = self._ms_to_x(self.current_position_ms)
            self.current_position_ms = max(0, min(self.duration_ms, int(position_ms)))
            new_x = self._ms_to_x(self.current_position_ms)
            if int(old_x) == int(new_x):
                return
            # Only the needle moves; repainting every cue block for it is the
            # lag during playback.
            for x in (old_x, new_x):
                self.update(int(x) - 8, 0, 17, self.height())

    def set_segments(self, segments: list[CaptionSegment]) -> None:
        self.segments = list(segments)
        self.update()

    def select_segment(self, segment: CaptionSegment | None) -> None:
        self.selected_segment = segment
        self.update()

    def _ms_to_x(self, ms: int) -> float:
        if self.duration_ms <= 0:
            return 0.0
        return (ms / self.duration_ms) * max(0, self.width() - 1)

    def _x_to_ms(self, x: float) -> int:
        if self.width() <= 0 or self.duration_ms <= 0:
            return 0
        pct = max(0.0, min(1.0, x / max(1, self.width() - 1)))
        return int(pct * self.duration_ms)

    def _trim_handle_at(self, x: float) -> str | None:
        if self.duration_ms <= 0:
            return None
        distances = {
            "start": abs(x - self._ms_to_x(self.trim_start_ms)),
            "end": abs(x - self._ms_to_x(self.trim_end_ms)),
        }
        handle = min(distances, key=distances.get)
        return handle if distances[handle] <= 10 else None

    def _cue_at(self, x: float, y: float) -> tuple[CaptionSegment, str] | None:
        """The caption block under a point, and which part of it: an edge or the body."""
        if self.duration_ms <= 0 or y < _TRACK_TOP:
            return None
        for seg in self.segments:
            x_start = self._ms_to_x(seg.start_ms)
            x_end = x_start + max(6.0, self._ms_to_x(seg.end_ms) - x_start)
            if abs(x - x_start) <= _CUE_EDGE_PX:
                return seg, "start"
            if abs(x - x_end) <= _CUE_EDGE_PX:
                return seg, "end"
            if x_start <= x <= x_end:
                return seg, "move"
        return None

    def _index_of(self, seg: CaptionSegment) -> int:
        for i, other in enumerate(self.segments):
            if other is seg:
                return i
        return -1

    def _drag_cue_to(self, x: float) -> None:
        drag = self._cue_drag
        if not drag.moved and abs(x - drag.press_x) < _CUE_DRAG_THRESHOLD_PX:
            return
        drag.moved = True
        idx = self._index_of(drag.seg)
        if idx < 0:
            return
        ms_per_px = self.duration_ms / max(1, self.width() - 1)
        dx = round((x - drag.press_x) * ms_per_px)
        if drag.partner is not None:
            self._roll(drag, dx)
            self.update()
            return
        prev_end = self.segments[idx - 1].end_ms if idx > 0 else 0
        next_start = (
            self.segments[idx + 1].start_ms
            if idx + 1 < len(self.segments)
            else self.duration_ms
        )
        if drag.mode == "move":
            # Moving keeps the length; the neighbours stop it.
            length = drag.end_ms - drag.start_ms
            start = max(prev_end, min(drag.start_ms + dx, next_start - length))
            end = start + length
        elif drag.mode == "start":
            start, end = clamped_segment_time(
                self.segments, idx, drag.start_ms + dx, drag.end_ms
            )
        else:
            start, end = clamped_segment_time(
                self.segments,
                idx,
                drag.start_ms,
                min(drag.end_ms + dx, self.duration_ms),
            )
        set_segment_time(drag.seg, start, end)
        self.update()

    def _roll_partner(self, seg: CaptionSegment, mode: str) -> CaptionSegment | None:
        """The caption on the other side of an edge that is shared with it."""
        if self.edit_mode != "rolling" or mode not in ("start", "end"):
            return None
        idx = self._index_of(seg)
        if mode == "start" and idx > 0:
            prev = self.segments[idx - 1]
            if abs(prev.end_ms - seg.start_ms) <= _ADJACENT_MS:
                return prev
        if mode == "end" and idx + 1 < len(self.segments):
            nxt = self.segments[idx + 1]
            if abs(nxt.start_ms - seg.end_ms) <= _ADJACENT_MS:
                return nxt
        return None

    def _roll(self, drag: _CueDrag, dx: int) -> None:
        """Move the splice: the dragged caption and its partner share the new edge."""
        if drag.mode == "start":
            # The partner comes before the dragged caption and ends at its start.
            lo = drag.partner.start_ms + MIN_SEGMENT_MS
            hi = drag.end_ms - MIN_SEGMENT_MS
            edge = min(hi, max(lo, drag.start_ms + dx))
            set_segment_time(drag.partner, drag.partner.start_ms, edge)
            set_segment_time(drag.seg, edge, drag.end_ms)
        else:
            lo = drag.start_ms + MIN_SEGMENT_MS
            hi = drag.partner.end_ms - MIN_SEGMENT_MS
            edge = min(hi, max(lo, drag.end_ms + dx))
            set_segment_time(drag.seg, drag.start_ms, edge)
            set_segment_time(drag.partner, edge, drag.partner.end_ms)

    def _finish_cue_drag(self) -> None:
        drag = self._cue_drag
        self._cue_drag = None
        if drag and drag.moved:
            self.cue_retimed.emit(drag.seg)
            if drag.partner is not None:
                self.cue_retimed.emit(drag.partner)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._trim_drag_handle = self._trim_handle_at(event.position().x())
            if self._trim_drag_handle:
                self.setCursor(Qt.CursorShape.SizeHorCursor)
                event.accept()
                return
            self._is_scrubbing = True
            target_ms = self._x_to_ms(event.position().x())
            self.current_position_ms = target_ms

            # Check if clicked inside a segment
            clicked_seg = None
            for seg in self.segments:
                if seg.start_ms <= target_ms <= seg.end_ms:
                    clicked_seg = seg
                    break

            self.selected_segment = clicked_seg
            if clicked_seg:
                self.segment_selected.emit(clicked_seg)

            self.seek_requested.emit(target_ms)
            hit = self._cue_at(event.position().x(), event.position().y())
            if hit:
                seg, mode = hit
                self._cue_drag = _CueDrag(
                    seg,
                    mode,
                    event.position().x(),
                    seg.start_ms,
                    seg.end_ms,
                    partner=self._roll_partner(seg, mode),
                )
            self.update()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._trim_drag_handle:
            target_ms = self._x_to_ms(event.position().x())
            gap = min(self._trim_min_gap_ms, self.duration_ms)
            if self._trim_drag_handle == "start":
                self.trim_start_ms = min(target_ms, self.trim_end_ms - gap)
            else:
                self.trim_end_ms = max(target_ms, self.trim_start_ms + gap)
            self.trim_range_changed.emit(self.trim_start_ms, self.trim_end_ms)
            self.update()
            event.accept()
        elif self._cue_drag is not None:
            self._drag_cue_to(event.position().x())
            event.accept()
        elif self._is_scrubbing:
            target_ms = self._x_to_ms(event.position().x())
            self.current_position_ms = target_ms
            self.seek_requested.emit(target_ms)
            self.update()
            event.accept()
        else:
            x, y = event.position().x(), event.position().y()
            hit = self._cue_at(x, y)
            if self._trim_handle_at(x) or (hit and hit[1] != "move"):
                cursor = Qt.CursorShape.SizeHorCursor
            elif hit:
                cursor = Qt.CursorShape.SizeAllCursor
            else:
                cursor = Qt.CursorShape.ArrowCursor
            self.setCursor(cursor)
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._trim_drag_handle:
            self._trim_drag_handle = None
            self.unsetCursor()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._cue_drag is not None:
            self._finish_cue_drag()
        if event.button() == Qt.MouseButton.LeftButton and self._is_scrubbing:
            self._is_scrubbing = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return
        clip_left = event.rect().left() - 1
        clip_right = event.rect().right() + 1

        # Background
        painter.fillRect(0, 0, w, h, QColor(24, 24, 27))

        # Ruler section (top 20px)
        ruler_h = 20
        painter.fillRect(0, 0, w, ruler_h, QColor(18, 18, 20))
        painter.setPen(QColor(63, 63, 70))
        painter.drawLine(0, ruler_h, w, ruler_h)

        # Draw time ruler tick marks
        if self.duration_ms > 0:
            font = QFont("Helvetica Neue", 8)
            painter.setFont(font)
            painter.setPen(QColor(161, 161, 170))

            # Intervals: 1s ticks, 5s labels if duration < 60s, else 10s
            step_sec = self._tick_step_sec()
            total_sec = int(self.duration_ms / 1000)
            for sec in range(0, total_sec + 1, step_sec):
                x = self._ms_to_x(sec * 1000)
                if x < clip_left - 44 or x > clip_right:
                    continue
                painter.drawLine(int(x), ruler_h - 6, int(x), ruler_h)
                mins = sec // 60
                secs = sec % 60
                label = f"{mins:02d}:{secs:02d}"
                painter.drawText(
                    QRectF(x + 2, 2, 40, 14), Qt.AlignmentFlag.AlignLeft, label
                )

        # Caption track section (from y=24 to y=h-6)
        track_y = ruler_h + 4
        track_h = h - track_y - 4

        font_cue = QFont("Helvetica Neue", 10, QFont.Weight.Medium)
        metrics = QFontMetrics(font_cue)
        painter.setFont(font_cue)

        for seg in self.segments:
            x_start = self._ms_to_x(seg.start_ms)
            x_end = self._ms_to_x(seg.end_ms)
            seg_w = max(6.0, x_end - x_start)
            if x_start > clip_right or x_start + seg_w < clip_left:
                continue

            block_rect = QRectF(x_start, track_y, seg_w, track_h)
            path = QPainterPath()
            path.addRoundedRect(block_rect, 4, 4)

            is_selected = seg == self.selected_segment
            bg_color = (
                QColor(49, 46, 129, 220) if is_selected else QColor(39, 39, 42, 220)
            )
            border_color = QColor(129, 140, 248) if is_selected else QColor(82, 82, 91)

            painter.fillPath(path, bg_color)
            painter.setPen(QPen(border_color, 1.5 if is_selected else 1.0))
            painter.drawPath(path)

            # Draw text inside block with clipping/elision
            if seg_w > 20:
                text = seg.text.strip()
                elided = metrics.elidedText(
                    text, Qt.TextElideMode.ElideRight, int(seg_w - 8)
                )
                painter.setPen(
                    QColor(255, 255, 255) if is_selected else QColor(228, 228, 231)
                )
                text_rect = QRectF(
                    x_start + 4, track_y + (track_h - 16) / 2, seg_w - 8, 16
                )
                painter.drawText(
                    text_rect,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    elided,
                )

        # Dim the portions that will be removed, leaving the selected range clear.
        if self.duration_ms > 0:
            start_x = self._ms_to_x(self.trim_start_ms)
            end_x = self._ms_to_x(self.trim_end_ms)
            painter.fillRect(QRectF(0, 0, start_x, h), QColor(0, 0, 0, 105))
            painter.fillRect(
                QRectF(end_x, 0, max(0.0, w - end_x), h), QColor(0, 0, 0, 105)
            )
            painter.setPen(QPen(QColor(96, 165, 250), 3))
            painter.drawLine(int(start_x), 0, int(start_x), h)
            painter.drawLine(int(end_x), 0, int(end_x), h)
            painter.setBrush(QColor(96, 165, 250))
            painter.setPen(Qt.PenStyle.NoPen)
            for handle_x in (start_x, end_x):
                painter.drawRoundedRect(QRectF(handle_x - 4, 14, 8, h - 20), 3, 3)

        # Playhead scrubber needle
        if self.duration_ms > 0:
            needle_x = self._ms_to_x(self.current_position_ms)
            needle_color = QColor(239, 68, 68)  # Red playhead

            # Vertical needle line
            painter.setPen(QPen(needle_color, 2))
            painter.drawLine(int(needle_x), 0, int(needle_x), h)

            # Triangular scrubber head at the top
            triangle = QPolygonF(
                [
                    QPoint(int(needle_x) - 6, 0),
                    QPoint(int(needle_x) + 6, 0),
                    QPoint(int(needle_x), 10),
                ]
            )
            painter.setBrush(needle_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(triangle)


class TimelineScroll(QScrollArea):
    """Scrolls the timeline sideways once zoomed in past the window's width."""

    def __init__(self, timeline: VisualTimelineWidget, parent: QWidget | None = None):
        super().__init__(parent)
        self.timeline = timeline
        self.setWidget(timeline)
        self.setWidgetResizable(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setFixedHeight(
            timeline.height() + self.horizontalScrollBar().sizeHint().height()
        )
        timeline.zoom_requested.connect(self.zoom_by)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self.timeline.set_fit_width(self.viewport().width())

    def zoom_by(self, factor: float, anchor_x: float | None = None) -> None:
        """Zoom by `factor`, keeping `anchor_x` (timeline pixels) where it is on screen.
        Without an anchor the middle of the view is kept."""
        bar = self.horizontalScrollBar()
        old_width = max(1, self.timeline.width())
        if anchor_x is None:
            anchor_x = bar.value() + self.viewport().width() / 2
        offset = anchor_x - bar.value()
        self.timeline.set_zoom(self.timeline.zoom * factor)
        ratio = self.timeline.width() / old_width
        bar.setValue(int(anchor_x * ratio - offset))

    def fit(self) -> None:
        self.timeline.set_zoom(1.0)
        self.horizontalScrollBar().setValue(0)
