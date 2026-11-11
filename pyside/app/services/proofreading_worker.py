"""Debounced, single-flight Qt adapter for the local proofreading engine."""

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal

from app.services.proofreading import check_snapshot


class _Signals(QObject):
    done = Signal(int, object, str)


class _Job(QRunnable):
    def __init__(self, generation, cues, mode):
        super().__init__()
        self.generation, self.cues, self.mode = generation, cues, mode
        self.signals = _Signals()

    def run(self):
        try:
            result = check_snapshot(self.cues, self.mode)
            error = ""
        except Exception:
            result = ()
            error = "Finnish proofreading unavailable. Check the bundled Voikko installation."
        self.signals.done.emit(self.generation, result, error)


class Proofreader(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = ()
        self.error = ""
        self.generation = 0
        self.busy = False
        self.pending = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._start)

    def request(self, cues, mode):
        self.generation += 1
        self.rows, self.error = (), ""
        self.pending = (self.generation, cues, mode)
        self.timer.start(200)
        self.changed.emit()

    def _start(self):
        if self.busy or self.pending is None:
            return
        generation, cues, mode = self.pending
        self.pending = None
        self.busy = True
        self.job = _Job(generation, cues, mode)
        self.job.signals.done.connect(self._done)
        QThreadPool.globalInstance().start(self.job)

    def _done(self, generation, rows, error):
        self.busy = False
        if generation == self.generation:
            self.rows, self.error = rows, error
            self.changed.emit()
        self._start()
