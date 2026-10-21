import re

from PySide6.QtCore import QPointF
from PySide6.QtGui import QFont, QTextLayout, QTextOption

_WORD = re.compile(r"\S+")


class WrappedText:
    """A cell's text laid out the way the table wraps it, so that clicks and
    underlines land on the words the user actually sees, lines and all."""

    def __init__(self, text: str, font: QFont, width: float) -> None:
        self.text = text
        self.layout = QTextLayout(text, font)
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapMode.WordWrap)
        self.layout.setTextOption(option)
        self.layout.beginLayout()
        self.lines = []
        self.height = 0.0
        while True:
            line = self.layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(max(1.0, width))
            line.setPosition(QPointF(0, self.height))
            self.height += line.height()
            self.lines.append(line)
        self.layout.endLayout()

    def char_at(self, x: float, y: float) -> int:
        """The character boundary nearest a point, relative to the text's top left."""
        if not self.lines:
            return 0
        for line in self.lines:
            if y < line.y() + line.height():
                return line.xToCursor(x)
        return self.lines[-1].xToCursor(x)

    def token_index(self, char: int) -> int | None:
        """Index of the word at or just after a character, None past the last word."""
        for index, match in enumerate(_WORD.finditer(self.text)):
            if char <= match.end():
                return index
        return None

    def underlines(self, start: int, end: int) -> list[tuple[float, float, float]]:
        """(x1, x2, baseline) per line for the characters start..end."""
        marks = []
        for line in self.lines:
            line_start = line.textStart()
            line_end = line_start + line.textLength()
            s, e = max(start, line_start), min(end, line_end)
            if s < e:
                marks.append(
                    (
                        line.cursorToX(s),
                        line.cursorToX(e),
                        line.y() + line.ascent(),
                    )
                )
        return marks
