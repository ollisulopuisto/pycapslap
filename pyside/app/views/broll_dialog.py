"""Pick footage for each stretch of the episode: accept one candidate, or reject."""

import threading
from collections.abc import Callable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.broll import net
from app.services.broll.picks import Picks

_MARK = {"pending": "·", "accepted": "✓", "rejected": "✗"}
_THUMB = QSize(160, 120)


def _clock(ms: int) -> str:
    s = ms // 1000
    return f"{s // 60}:{s % 60:02d}"


class BrollDialog(QDialog):
    _thumb_ready = Signal(int, int, bytes)  # window, candidate, image data

    def __init__(
        self,
        picks: Picks,
        load_thumb: Callable[[str], bytes] = net.get,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.picks = picks
        self._load_thumb = load_thumb
        self._requested: set[int] = set()
        self.setWindowTitle("B-roll")
        self.setMinimumSize(900, 520)

        self.windows = QListWidget()
        self.windows.setFixedWidth(280)
        self.windows.currentRowChanged.connect(self._show_window)
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.candidates = QListWidget()
        self.candidates.setViewMode(QListView.ViewMode.IconMode)
        self.candidates.setIconSize(_THUMB)
        self.candidates.setResizeMode(QListView.ResizeMode.Adjust)
        self.candidates.setMovement(QListView.Movement.Static)
        self.candidates.setWordWrap(True)
        self.candidates.setGridSize(QSize(190, 190))
        self.candidates.currentRowChanged.connect(self._sync)
        self.candidates.itemDoubleClicked.connect(lambda _: self.accept_btn.click())

        self.accept_btn = QPushButton("Accept")
        self.accept_btn.clicked.connect(self._accept)
        self.reject_btn = QPushButton("Reject window")
        self.reject_btn.clicked.connect(self._reject)
        self.build_btn = QPushButton("Build reel")
        self.build_btn.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addWidget(self.accept_btn)
        buttons.addWidget(self.reject_btn)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(self.build_btn)
        right = QVBoxLayout()
        right.addWidget(self.text)
        right.addWidget(self.candidates, 1)
        right.addLayout(buttons)
        root = QHBoxLayout(self)
        root.addWidget(self.windows)
        root.addLayout(right, 1)

        self._thumb_ready.connect(self._set_thumb)
        for i, w in enumerate(picks.data()):
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.windows.addItem(item)
            self._label(i, w)
        if self.windows.count():
            self.windows.setCurrentRow(0)
        self._sync()

    def _label(self, i: int, w: dict) -> None:
        item = self.windows.item(i)
        n = len(w["candidates"])
        item.setText(
            f"{_MARK[self.picks.status[i]]}  {_clock(w['startMs'])}  {w['query']}  ({n})"
        )

    def _refresh_row(self, i: int) -> None:
        self._label(i, self.picks.data()[i])

    def _show_window(self, row: int) -> None:
        self.candidates.clear()
        if row < 0:
            self.text.clear()
            self._sync()
            return
        w = self.picks.data()[row]
        self.text.setText(f"{_clock(w['startMs'])}–{_clock(w['endMs'])}: {w['text']}")
        for j, c in enumerate(w["candidates"]):
            author = c.get("author") or "unknown author"
            item = QListWidgetItem(f"{c['title']}\n{author}, {c['license']}")
            item.setToolTip(f"{c['kind']}  {c['page_url']}")
            self.candidates.addItem(item)
            if w.get("chosen") == j:
                self.candidates.setCurrentRow(j)
            self._fetch_thumb(row, j, c.get("thumb_url"))
        self._sync()

    def _fetch_thumb(self, row: int, j: int, url: str | None) -> None:
        if not url:
            return

        def work() -> None:
            try:
                data = self._load_thumb(url)
            except Exception:  # a missing picture must not stop the picking
                return
            try:
                self._thumb_ready.emit(row, j, data)
            except RuntimeError:  # the dialog closed first
                pass

        threading.Thread(target=work, daemon=True).start()

    def _set_thumb(self, row: int, j: int, data: bytes) -> None:
        if row != self.windows.currentRow() or j >= self.candidates.count():
            return
        pix = QPixmap()
        if pix.loadFromData(data):
            self.candidates.item(j).setIcon(QIcon(pix))

    def _sync(self, *_: object) -> None:
        self.accept_btn.setEnabled(self.candidates.currentRow() >= 0)
        self.reject_btn.setEnabled(self.windows.currentRow() >= 0)
        self.build_btn.setEnabled(bool(self.picks.accepted()))

    def _accept(self) -> None:
        row, j = self.windows.currentRow(), self.candidates.currentRow()
        if row < 0 or j < 0:
            return
        self.picks.accept(row, j)
        self._refresh_row(row)
        self._next_pending(row)

    def _reject(self) -> None:
        row = self.windows.currentRow()
        if row < 0:
            return
        self.picks.reject(row)
        self._refresh_row(row)
        self._next_pending(row)

    def _next_pending(self, after: int) -> None:
        waiting = [i for i in self.picks.pending() if i > after] or self.picks.pending()
        if waiting:
            self.windows.setCurrentRow(waiting[0])
        self._sync()
