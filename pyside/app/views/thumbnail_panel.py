"""The thumbnail: a frame from the playhead with the title written over it.

The title is its own field in the sidebar, and the preview shows it as it will
be saved, so the words can be checked before the PNG is written.
"""

from PySide6.QtCore import Qt, Signal
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


def compose(frame: QImage, title: str) -> QImage:
    """A copy of `frame` with `title` set in the lower part, wrapped and centred."""
    out = frame.convertToFormat(QImage.Format.Format_ARGB32)
    title = title.strip()
    if not title or out.isNull():
        return out

    size = max(12, out.height() // 11)
    font = QFont("Helvetica Neue", size, QFont.Weight.Black)
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
    top = out.height() * 0.70 - block_h / 2

    path = QPainterPath()
    for index, text in enumerate(lines):
        width = metrics.horizontalAdvance(text)
        x = (out.width() - width) / 2
        y = top + index * line_h + metrics.ascent()
        path.addText(x, y, font, text)

    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    outline = QPen(QColor("#000000"), max(3, size // 6))
    outline.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(outline)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.fillPath(path, QColor("#ffffff"))
    painter.end()
    return out


class ThumbnailPanel(QWidget):
    capture_requested = Signal()
    save_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.frame: QImage | None = None

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
        self.title_edit.textChanged.connect(lambda _text: self._refresh())
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

    def set_frame(self, frame: QImage) -> None:
        self.frame = frame
        self.save_btn.setEnabled(True)
        self._refresh()

    def rendered(self) -> QImage | None:
        if self.frame is None:
            return None
        return compose(self.frame, self.title_edit.text())

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
