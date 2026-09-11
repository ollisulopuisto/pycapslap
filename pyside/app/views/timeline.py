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
from PySide6.QtWidgets import QWidget

from app.models.captions import CaptionSegment


class VisualTimelineWidget(QWidget):
    seek_requested = Signal(int)
    segment_selected = Signal(object)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(84)
        self.setMouseTracking(True)

        self.duration_ms: int = 0
        self.current_position_ms: int = 0
        self.segments: list[CaptionSegment] = []
        self.selected_segment: CaptionSegment | None = None
        self._is_scrubbing: bool = False

    def set_duration(self, duration_ms: int) -> None:
        self.duration_ms = max(0, int(duration_ms))
        self.update()

    def set_position(self, position_ms: int) -> None:
        if not self._is_scrubbing:
            self.current_position_ms = max(0, min(self.duration_ms, int(position_ms)))
            self.update()

    def set_segments(self, segments: list[CaptionSegment]) -> None:
        self.segments = list(segments)
        self.update()

    def select_segment(self, segment: CaptionSegment | None) -> None:
        self.selected_segment = segment
        self.update()

    def _ms_to_x(self, ms: int) -> float:
        if self.duration_ms <= 0:
            return 0.0
        return (ms / self.duration_ms) * self.width()

    def _x_to_ms(self, x: float) -> int:
        if self.width() <= 0 or self.duration_ms <= 0:
            return 0
        pct = max(0.0, min(1.0, x / self.width()))
        return int(pct * self.duration_ms)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
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
            self.update()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._is_scrubbing:
            target_ms = self._x_to_ms(event.position().x())
            self.current_position_ms = target_ms
            self.seek_requested.emit(target_ms)
            self.update()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._is_scrubbing:
            self._is_scrubbing = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return

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
            step_sec = 5 if self.duration_ms < 60_000 else 10
            total_sec = int(self.duration_ms / 1000)
            for sec in range(0, total_sec + 1, step_sec):
                x = self._ms_to_x(sec * 1000)
                painter.drawLine(int(x), ruler_h - 6, int(x), ruler_h)
                mins = sec // 60
                secs = sec % 60
                label = f"{mins:02d}:{secs:02d}"
                painter.drawText(QRectF(x + 2, 2, 40, 14), Qt.AlignmentFlag.AlignLeft, label)

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

            block_rect = QRectF(x_start, track_y, seg_w, track_h)
            path = QPainterPath()
            path.addRoundedRect(block_rect, 4, 4)

            is_selected = seg == self.selected_segment
            bg_color = QColor(49, 46, 129, 220) if is_selected else QColor(39, 39, 42, 220)
            border_color = QColor(129, 140, 248) if is_selected else QColor(82, 82, 91)

            painter.fillPath(path, bg_color)
            painter.setPen(QPen(border_color, 1.5 if is_selected else 1.0))
            painter.drawPath(path)

            # Draw text inside block with clipping/elision
            if seg_w > 20:
                text = seg.text.strip()
                elided = metrics.elidedText(text, Qt.TextElideMode.ElideRight, int(seg_w - 8))
                painter.setPen(QColor(255, 255, 255) if is_selected else QColor(228, 228, 231))
                text_rect = QRectF(x_start + 4, track_y + (track_h - 16) / 2, seg_w - 8, 16)
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)

        # Playhead scrubber needle
        if self.duration_ms > 0:
            needle_x = self._ms_to_x(self.current_position_ms)
            needle_color = QColor(239, 68, 68)  # Red playhead

            # Vertical needle line
            painter.setPen(QPen(needle_color, 2))
            painter.drawLine(int(needle_x), 0, int(needle_x), h)

            # Triangular scrubber head at the top
            triangle = QPolygonF([
                QPoint(int(needle_x) - 6, 0),
                QPoint(int(needle_x) + 6, 0),
                QPoint(int(needle_x), 10),
            ])
            painter.setBrush(needle_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(triangle)
