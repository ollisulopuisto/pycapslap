from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import (
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


class VideoCanvasWidget(QWidget):
    """
    Unified, hardware-composited video display and interactive subtitle canvas.
    Renders video frames via QVideoSink and paints subtitles directly onto the
    same surface, eliminating native Cocoa/Metal layer occlusion on macOS.
    """
    anchor_changed = Signal(float)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setMouseTracking(True)

        self.sink = QVideoSink(self)
        self.sink.videoFrameChanged.connect(self._on_video_frame_changed)

        self._current_frame: QVideoFrame | None = None
        self._paint_opts = QVideoFrame.PaintOptions()
        self._fallback_pixmap: QPixmap | None = None

        self.current_segment: CaptionSegment | None = None
        self.current_pos_ms: int = 0
        self.anchor_y_pct: float = 80.0
        self.is_dragging: bool = False
        self.style: CaptionStyle = CaptionStyle()

        # Initialize fonts database
        init_app_fonts()

    def set_style(self, style: CaptionStyle) -> None:
        self.style = style
        self.update()

    def set_fallback_pixmap(self, pixmap: QPixmap | None) -> None:
        self._fallback_pixmap = pixmap
        self.update()

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
        self.update()

    def _get_video_rect(self) -> QRectF:
        w = float(self.width())
        h = float(self.height())
        if w <= 0 or h <= 0:
            return QRectF(0, 0, 0, 0)

        aspect = 16.0 / 9.0
        if self._current_frame and self._current_frame.isValid():
            sz = self._current_frame.size()
            if sz.width() > 0 and sz.height() > 0:
                aspect = sz.width() / sz.height()
        elif self._fallback_pixmap and not self._fallback_pixmap.isNull():
            sz = self._fallback_pixmap.size()
            if sz.width() > 0 and sz.height() > 0:
                aspect = sz.width() / sz.height()

        if (w / h) > aspect:
            vh = h
            vw = h * aspect
            vx = (w - vw) / 2.0
            vy = 0.0
        else:
            vw = w
            vh = w / aspect
            vx = 0.0
            vy = (h - vh) / 2.0

        return QRectF(vx, vy, vw, vh)

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
        video_rect = self._get_video_rect()
        if video_rect.height() <= 0:
            return
        rel_y = pos.y() - video_rect.top()
        pct = (rel_y / video_rect.height()) * 100.0
        pct = max(5.0, min(95.0, pct))
        self.anchor_y_pct = round(pct, 1)
        self.anchor_changed.emit(self.anchor_y_pct)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # 1. Background fill for entire canvas
        painter.fillRect(self.rect(), QColor(10, 10, 12))

        video_rect = self._get_video_rect()
        if video_rect.width() <= 0 or video_rect.height() <= 0:
            return

        # 2. Render Video Frame or Fallback Pixmap
        if self._current_frame and self._current_frame.isValid():
            self._current_frame.paint(painter, video_rect, self._paint_opts)
        elif self._fallback_pixmap and not self._fallback_pixmap.isNull():
            painter.drawPixmap(video_rect.toRect(), self._fallback_pixmap)

        # 3. Dragging guidelines
        anchor_y = video_rect.top() + (video_rect.height() * (self.anchor_y_pct / 100.0))
        if self.is_dragging:
            pen = QPen(QColor(99, 102, 241, 230), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawLine(int(video_rect.left()), int(anchor_y), int(video_rect.right()), int(anchor_y))

            badge_text = f"{self.anchor_y_pct:.1f}%"
            badge_font = QFont("Helvetica Neue", 10, QFont.Weight.Bold)
            painter.setFont(badge_font)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(99, 102, 241, 220))
            badge_rect = QRectF(video_rect.left() + 16, max(video_rect.top() + 8, anchor_y - 22), 52, 20)
            painter.drawRoundedRect(badge_rect, 4, 4)

            painter.setPen(QColor(255, 255, 255))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

        # 4. Render Active Subtitle
        if self.current_segment and self.current_segment.text.strip():
            self._paint_caption(painter, video_rect, anchor_y)

    def _paint_caption(self, painter: QPainter, video_rect: QRectF, anchor_y: float) -> None:
        text = self.current_segment.text.strip()
        if not text:
            return

        # Resolve font family
        font_family = self.style.font_name.split()[0] if self.style.font_name else "Montserrat"
        # Scale font size relative to 1080p reference
        base_size = self.style.font_size or 65
        scaled_size = max(14, int(base_size * (video_rect.height() / 1080.0)))

        font = QFont(font_family, scaled_size, QFont.Weight.Black)
        metrics = QFontMetrics(font)

        words = self.current_segment.words or []
        has_words = bool(words) and self.style.karaoke

        text_w = metrics.horizontalAdvance(text)
        text_h = metrics.height()
        baseline = metrics.ascent()

        box_x = video_rect.left() + (video_rect.width() - text_w) / 2.0
        box_y = anchor_y - (text_h / 2.0)

        # Background pill
        pill_pad_x = max(12, int(scaled_size * 0.5))
        pill_pad_y = max(6, int(scaled_size * 0.25))
        pill_rect = QRectF(
            box_x - pill_pad_x,
            box_y - pill_pad_y,
            text_w + pill_pad_x * 2,
            text_h + pill_pad_y * 2,
        )

        pill_path = QPainterPath()
        pill_path.addRoundedRect(pill_rect, 8, 8)
        painter.fillPath(pill_path, QColor(0, 0, 0, 180))

        if self.is_dragging:
            painter.setPen(QPen(QColor(99, 102, 241, 255), 2))
            painter.drawPath(pill_path)

        outline_width = max(2, int(self.style.outline_width * (scaled_size / 24.0)))
        outline_pen = QPen(QColor(self.style.outline_color or "#000000"), outline_width * 2)
        outline_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        text_color = QColor(self.style.text_color or "#ffffff")
        highlight_color = QColor(self.style.highlight_color or "#ffff00")

        if has_words:
            # Word-by-word karaoke highlighting
            cur_x = box_x
            text_y = box_y + baseline
            for word in words:
                word_w = metrics.horizontalAdvance(word.text)
                is_active = (word.start_ms <= self.current_pos_ms < word.end_ms)
                fill_color = highlight_color if is_active else text_color

                wpath = QPainterPath()
                wpath.addText(cur_x, text_y, font, word.text)
                painter.strokePath(wpath, outline_pen)
                painter.fillPath(wpath, fill_color)

                cur_x += word_w
        else:
            # Single block text
            text_y = box_y + baseline
            tpath = QPainterPath()
            tpath.addText(box_x, text_y, font, text)
            painter.strokePath(tpath, outline_pen)
            painter.fillPath(tpath, text_color)
