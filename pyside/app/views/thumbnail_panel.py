"""The thumbnail: a frame from the playhead with the title written over it.

The title is its own field in the sidebar, and the preview shows it as it will
be saved, so the words can be checked before the PNG is written.
"""

from PySide6.QtCore import Qt, Signal
from app.models.captions import CaptionStyle
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


def compose(frame: QImage, title: str, style: CaptionStyle | None = None) -> QImage:
    """A copy of `frame` with `title` set the way the captions are: the caption
    style's font, colours, outline, glow and background box, at its position."""
    style = style or CaptionStyle()
    out = frame.convertToFormat(QImage.Format.Format_ARGB32)
    title = title.strip()
    if not title or out.isNull():
        return out

    # The style's sizes are for a 1080-line frame, as the captions are.
    scale = out.height() / 1080
    font = QFont(style.font_name)
    font.setPixelSize(max(12, round(style.font_size * scale)))
    metrics = QFontMetrics(font)
    max_width = out.width() * 0.84
    lines: list[str] = []
    line = ""
    for word in title.split():
        candidate = f"{line} {word}".strip()
        if line and metrics.horizontalAdvance(candidate) > max_width:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)

    line_h = metrics.height()
    block_h = line_h * len(lines)
    top = out.height() * style.anchor_pct / 100 - block_h / 2

    path = QPainterPath()
    for index, text in enumerate(lines):
        width = metrics.horizontalAdvance(text)
        x = (out.width() - width) / 2
        y = top + index * line_h + metrics.ascent()
        path.addText(x, y, font, text)

    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    if style.background_box:
        pad = line_h * 0.3
        box = path.boundingRect().adjusted(-pad, -pad, pad, pad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 140))
        painter.drawRoundedRect(box, pad, pad)
    if style.glow_effect:
        glow_colour = QColor(style.text_color)
        glow_colour.setAlpha(90)
        glow = QPen(glow_colour, max(2.0, style.outline_width * scale * 4))
        glow.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(glow)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
    outline = QPen(
        QColor(style.outline_color), max(2.0, style.outline_width * scale * 2)
    )
    outline.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(outline)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.fillPath(path, QColor(style.text_color))
    painter.end()
    return out


class ThumbnailPanel(QWidget):
    capture_requested = Signal()
    save_requested = Signal(object)
    # The title was edited: the project should be saved with the new headline.
    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.frame: QImage | None = None
        self.time_ms: int | None = None
        self.style = CaptionStyle()

        # The preview is a 9:16 tile beside the title and buttons, so the panel
        # stays short and the caption table keeps its height.
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        self.preview = QLabel("No frame")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setFixedSize(96, 171)
        self.preview.setStyleSheet(
            "background-color: #000000; color: #71717a; border-radius: 6px;"
        )
        layout.addWidget(self.preview)

        side = QVBoxLayout()
        side.setSpacing(6)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Thumbnail title")
        self.title_edit.setToolTip("Written over the frame in the thumbnail")
        self.title_edit.setStyleSheet(
            "QLineEdit { background-color: #27272a; color: #f4f4f5; "
            "border: 1px solid #3f3f46; border-radius: 6px; padding: 4px 8px; }"
        )
        palette = self.title_edit.palette()
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#71717a"))
        self.title_edit.setPalette(palette)
        self.title_edit.textChanged.connect(self._on_title_edited)
        side.addWidget(self.title_edit)

        self.capture_btn = QPushButton("Capture frame")
        self.capture_btn.setToolTip("Take the frame under the playhead")
        self.capture_btn.clicked.connect(self.capture_requested.emit)
        self.save_btn = QPushButton("Save thumbnail…")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(lambda: self.save_requested.emit(self.rendered()))
        side.addWidget(self.capture_btn)
        side.addWidget(self.save_btn)
        side.addStretch()
        layout.addLayout(side, stretch=1)

    def set_style(self, style: CaptionStyle) -> None:
        """Follow the caption style: the title is set in the same font and colours."""
        self.style = style
        self._refresh()

    def state(self) -> dict:
        """What the project saves: the frame's time and the headline."""
        if self.time_ms is None and not self.title_edit.text():
            return {}
        return {"timeMs": self.time_ms, "title": self.title_edit.text()}

    def load_state(self, state: dict) -> None:
        """Show a saved headline and remember its frame. The frame itself is
        taken again by the window, so a load does not count as a change."""
        self.title_edit.blockSignals(True)
        self.title_edit.setText(str(state.get("title", "")))
        self.title_edit.blockSignals(False)
        time_ms = state.get("timeMs")
        self.time_ms = None if time_ms is None else int(time_ms)

    def _on_title_edited(self, _text: str) -> None:
        self._refresh()
        self.changed.emit()

    def set_frame(self, frame: QImage, time_ms: int | None = None) -> None:
        self.frame = frame
        self.time_ms = time_ms
        self.save_btn.setEnabled(True)
        self._refresh()

    def rendered(self) -> QImage | None:
        if self.frame is None:
            return None
        return compose(self.frame, self.title_edit.text(), self.style)

    def _refresh(self) -> None:
        image = self.rendered()
        if image is None:
            return
        scaled = QPixmap.fromImage(image).scaled(
            self.preview.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview.setPixmap(scaled)
