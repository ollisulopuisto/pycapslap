"""Local Orukeet model installation and status."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core_client import CoreClient


def get_transcription_params() -> dict:
    """Transcription is always local Orukeet; no provider parameters are needed."""
    return {}


class OrukeetSettingsDialog(QDialog):
    def __init__(
        self, core_client: CoreClient | None = None, parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.setWindowTitle("Orukeet Settings")
        self.setMinimumWidth(420)
        self.core = core_client

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Orukeet transcribes audio on this computer. The verified Q8 model and "
                "native runtime are downloaded once, then transcription works offline."
            )
        )
        self.status = QLabel("Checking local model…")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.install_button = QPushButton("Install / Verify Orukeet")
        self.install_button.clicked.connect(self._install)
        layout.addWidget(self.install_button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
        self._check()

    def _check(self) -> None:
        if not self.core:
            self.status.setText("The transcription core is unavailable.")
            self.install_button.setEnabled(False)
            return
        future = self.core.call("checkOrukeetInstalled", {})
        future.add_done_callback(self._check_done)

    def _check_done(self, future) -> None:
        try:
            installed = bool(future.result())
            message = (
                "Orukeet is ready for offline transcription."
                if installed
                else "Orukeet has not been downloaded yet."
            )
        except (RuntimeError, ValueError, OSError) as error:
            message = f"Could not check Orukeet: {error}"
        QTimer.singleShot(0, self, lambda: self.status.setText(message))

    def _install(self) -> None:
        if not self.core:
            return
        self.install_button.setEnabled(False)
        self.status.setText("Downloading and verifying the model and native runtime…")
        future = self.core.call("installOrukeet", {})
        future.add_done_callback(self._install_done)

    def _install_done(self, future) -> None:
        try:
            future.result()
            message = "Orukeet is ready for offline transcription."
        except (RuntimeError, ValueError, OSError) as error:
            message = f"Orukeet installation failed: {error}"

        def update() -> None:
            self.status.setText(message)
            self.install_button.setEnabled(True)

        QTimer.singleShot(0, self, update)
