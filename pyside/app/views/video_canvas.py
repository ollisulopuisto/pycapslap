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
from app.models.captions import CaptionSegment, CaptionStyle, WordSpan


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
        anchor_y = video_rect.top() + (
            video_rect.height() * (self.anchor_y_pct / 100.0)
        )
        if self.is_dragging:
            pen = QPen(QColor(99, 102, 241, 230), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawLine(
                int(video_rect.left()),
                int(anchor_y),
                int(video_rect.right()),
                int(anchor_y),
            )

            badge_text = f"{self.anchor_y_pct:.1f}%"
            badge_font = QFont("Helvetica Neue", 10, QFont.Weight.Bold)
            painter.setFont(badge_font)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(99, 102, 241, 220))
            badge_rect = QRectF(
                video_rect.left() + 16, max(video_rect.top() + 8, anchor_y - 22), 52, 20
            )
            painter.drawRoundedRect(badge_rect, 4, 4)

            painter.setPen(QColor(255, 255, 255))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

        # 4. Render Active Subtitle
        if self.current_segment and self.current_segment.text.strip():
            self._paint_caption(painter, video_rect, anchor_y)

    @staticmethod
    def _word_display_text(word: WordSpan, is_first: bool) -> str:
        txt = word.text
        if is_first:
            return txt.lstrip()
        if not txt.startswith(" ") and not word.glue_to_previous:
            return " " + txt
        return txt

    def _measure_word_span_line(
        self, line: list[WordSpan], metrics: QFontMetrics
    ) -> float:
        total = 0.0
        for i, w in enumerate(line):
            display_t = self._word_display_text(w, is_first=(i == 0))
            total += metrics.horizontalAdvance(display_t)
        return total

    def _wrap_karaoke_words(
        self, words: list[WordSpan], metrics: QFontMetrics, max_width: float
    ) -> list[list[WordSpan]]:
        lines: list[list[WordSpan]] = []
        cur_line: list[WordSpan] = []

        for w in words:
            if not cur_line:
                cur_line.append(w)
            else:
                candidate = cur_line + [w]
                if self._measure_word_span_line(candidate, metrics) <= max_width:
                    cur_line.append(w)
                else:
                    lines.append(cur_line)
                    cur_line = [w]

        if cur_line:
            lines.append(cur_line)
        return lines

    @staticmethod
    def _wrap_plain_tokens(
        tokens: list[str], metrics: QFontMetrics, max_width: float
    ) -> list[str]:
        lines: list[str] = []
        cur_line: list[str] = []

        for t in tokens:
            if not cur_line:
                cur_line.append(t)
            else:
                candidate = " ".join(cur_line + [t])
                if metrics.horizontalAdvance(candidate) <= max_width:
                    cur_line.append(t)
                else:
                    lines.append(" ".join(cur_line))
                    cur_line = [t]

        if cur_line:
            lines.append(" ".join(cur_line))
        return lines

    def _paint_caption(
        self, painter: QPainter, video_rect: QRectF, anchor_y: float
    ) -> None:
        text = self.current_segment.text.strip()
        if not text:
            return

        # 1. Resolve font family
        font_family = (
            self.style.font_name.split()[0] if self.style.font_name else "Montserrat"
        )

        # 2. Proportional font sizing relative to video width and aspect ratio
        vw = video_rect.width()
        vh = video_rect.height()
        if vw <= 0 or vh <= 0:
            return

        aspect = vw / vh
        # Portrait (e.g. 9:16) uses 1080 reference width, landscape (16:9) uses 1920
        ref_w = 1080.0 if aspect < 1.0 else 1920.0
        base_size = float(self.style.font_size or 60)
        start_font_size = max(12, int(base_size * (vw / ref_w)))

        # Safe area: captions must never exceed 85% of video width
        max_caption_width = max(40.0, vw * 0.85)

        words = self.current_segment.words or []
        has_words = bool(words) and self.style.karaoke
        plain_tokens = text.split() if not has_words else []

        # 3. Dynamic fitting loop: ensure lines wrap and fit within max_caption_width
        font_size = start_font_size
        final_font = None
        final_metrics = None
        karaoke_lines: list[list[WordSpan]] = []
        plain_lines: list[str] = []

        while font_size >= 10:
            test_font = QFont(font_family, font_size, QFont.Weight.Black)
            test_metrics = QFontMetrics(test_font)

            if has_words:
                k_lines = self._wrap_karaoke_words(
                    words, test_metrics, max_caption_width
                )
                max_w = max(
                    (
                        self._measure_word_span_line(line, test_metrics)
                        for line in k_lines
                    ),
                    default=0.0,
                )
                if (
                    max_w <= max_caption_width and len(k_lines) <= 3
                ) or font_size == 10:
                    final_font = test_font
                    final_metrics = test_metrics
                    karaoke_lines = k_lines
                    break
            else:
                p_lines = self._wrap_plain_tokens(
                    plain_tokens, test_metrics, max_caption_width
                )
                max_w = max(
                    (test_metrics.horizontalAdvance(line) for line in p_lines),
                    default=0.0,
                )
                if (
                    max_w <= max_caption_width and len(p_lines) <= 3
                ) or font_size == 10:
                    final_font = test_font
                    final_metrics = test_metrics
                    plain_lines = p_lines
                    break

            font_size -= 1

        if not final_font or not final_metrics:
            return

        font = final_font
        metrics = final_metrics
        line_h = metrics.height()
        line_spacing = max(2, int(line_h * 0.12))
        num_lines = len(karaoke_lines) if has_words else len(plain_lines)
        total_block_h = num_lines * line_h + (num_lines - 1) * line_spacing

        # Keep caption block vertically inside video_rect
        block_top = anchor_y - (total_block_h / 2.0)
        min_top = video_rect.top() + 8.0
        max_top = video_rect.bottom() - total_block_h - 8.0
        if min_top < max_top:
            block_top = max(min_top, min(max_top, block_top))

        # Pens & Colors
        outline_width = max(1, int(self.style.outline_width * (font_size / 24.0)))
        outline_pen = QPen(
            QColor(self.style.outline_color or "#000000"), outline_width * 2
        )
        outline_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        text_color = QColor(self.style.text_color or "#ffffff")
        highlight_color = QColor(self.style.highlight_color or "#ffff00")

        pill_pad_x = max(8, int(font_size * 0.35))
        pill_pad_y = max(4, int(font_size * 0.15))

        # 4. Render lines
        for idx in range(num_lines):
            line_y = block_top + idx * (line_h + line_spacing)
            baseline_y = line_y + metrics.ascent()

            if has_words:
                k_line = karaoke_lines[idx]
                line_w = self._measure_word_span_line(k_line, metrics)
                line_x = video_rect.left() + (video_rect.width() - line_w) / 2.0
                line_x = max(video_rect.left() + 4.0, line_x)

                pill_rect = QRectF(
                    line_x - pill_pad_x,
                    line_y - pill_pad_y,
                    line_w + pill_pad_x * 2,
                    line_h + pill_pad_y * 2,
                )
                pill_path = QPainterPath()
                pill_path.addRoundedRect(pill_rect, 6, 6)
                painter.fillPath(pill_path, QColor(0, 0, 0, 180))

                if self.is_dragging:
                    painter.setPen(QPen(QColor(99, 102, 241, 255), 1.5))
                    painter.drawPath(pill_path)

                cur_x = line_x
                for w_idx, word in enumerate(k_line):
                    display_text = self._word_display_text(word, is_first=(w_idx == 0))
                    w_advance = metrics.horizontalAdvance(display_text)
                    is_active = word.start_ms <= self.current_pos_ms < word.end_ms
                    fill_color = highlight_color if is_active else text_color

                    wpath = QPainterPath()
                    wpath.addText(cur_x, baseline_y, font, display_text)
                    painter.strokePath(wpath, outline_pen)
                    painter.fillPath(wpath, fill_color)

                    cur_x += w_advance

            else:
                p_line = plain_lines[idx]
                line_w = metrics.horizontalAdvance(p_line)
                line_x = video_rect.left() + (video_rect.width() - line_w) / 2.0
                line_x = max(video_rect.left() + 4.0, line_x)

                pill_rect = QRectF(
                    line_x - pill_pad_x,
                    line_y - pill_pad_y,
                    line_w + pill_pad_x * 2,
                    line_h + pill_pad_y * 2,
                )
                pill_path = QPainterPath()
                pill_path.addRoundedRect(pill_rect, 6, 6)
                painter.fillPath(pill_path, QColor(0, 0, 0, 180))

                if self.is_dragging:
                    painter.setPen(QPen(QColor(99, 102, 241, 255), 1.5))
                    painter.drawPath(pill_path)

                tpath = QPainterPath()
                tpath.addText(line_x, baseline_y, font, p_line)
                painter.strokePath(tpath, outline_pen)
                painter.fillPath(tpath, text_color)
