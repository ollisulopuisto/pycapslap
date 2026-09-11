from PySide6.QtCore import QEvent, QPoint, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QWidget

from app.models.captions import CaptionSegment


class CaptionOverlayWidget(QWidget):
    anchor_changed = Signal(float)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setMouseTracking(True)

        self.current_segment: CaptionSegment | None = None
        self.anchor_y_pct: float = 80.0
        self.is_dragging: bool = False
        self._hover: bool = False

        if parent is not None:
            self.resize(parent.size())
            parent.installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.parent() and event.type() == QEvent.Type.Resize:
            self.resize(event.size())
        return super().eventFilter(watched, event)

    def set_segment(self, segment: CaptionSegment | None, anchor_y_pct: float = 80.0) -> None:
        self.current_segment = segment
        self.anchor_y_pct = float(anchor_y_pct)
        self.update()

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
        h = self.height()
        if h <= 0:
            return
        pct = (pos.y() / h) * 100.0
        pct = max(5.0, min(95.0, pct))
        self.anchor_y_pct = round(pct, 1)
        self.anchor_changed.emit(self.anchor_y_pct)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        h = self.height()
        w = self.width()
        if h <= 0 or w <= 0:
            return

        anchor_y = int(h * (self.anchor_y_pct / 100.0))

        # Draw guideline when dragging or hovering
        if self.is_dragging:
            pen = QPen(QColor(99, 102, 241, 200), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawLine(0, anchor_y, w, anchor_y)

            # Badge showing current % position
            badge_text = f"{self.anchor_y_pct:.1f}%"
            badge_font = QFont("Helvetica Neue", 10, QFont.Weight.Bold)
            painter.setFont(badge_font)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(99, 102, 241, 220))
            badge_rect = QRectF(16, max(8, anchor_y - 22), 52, 20)
            painter.drawRoundedRect(badge_rect, 4, 4)

            painter.setPen(QColor(255, 255, 255))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

        # Draw active caption text if present
        if self.current_segment and self.current_segment.text.strip():
            text = self.current_segment.text.strip()
            font = QFont("Helvetica Neue", 16, QFont.Weight.Bold)
            painter.setFont(font)
            metrics = QFontMetrics(font)

            text_rect = metrics.boundingRect(text)
            padding_x = 16
            padding_y = 8
            box_w = text_rect.width() + padding_x * 2
            box_h = text_rect.height() + padding_y * 2

            box_x = (w - box_w) / 2
            box_y = anchor_y - (box_h / 2)

            box_rect = QRectF(box_x, box_y, box_w, box_h)

            # Rounded pill background
            path = QPainterPath()
            path.addRoundedRect(box_rect, 8, 8)
            painter.fillPath(path, QColor(0, 0, 0, 180))

            if self.is_dragging:
                painter.setPen(QPen(QColor(99, 102, 241, 255), 2))
                painter.drawPath(path)

            # Draw text
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(box_rect, Qt.AlignmentFlag.AlignCenter, text)
