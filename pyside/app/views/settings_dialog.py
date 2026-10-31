"""Install Orukeet and manage the local Whisper model."""

from __future__ import annotations

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core_client import CoreClient


class OrukeetSettingsDialog(QDialog):
    def __init__(
        self, core_client: CoreClient | None = None, parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.setWindowTitle("Transcription Settings")
        self.setMinimumWidth(440)
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
        layout.addWidget(QLabel("Whisper model (local whisper.cpp):"))
        self.whisper_model = QComboBox()
        self.whisper_model.addItems(
            ["tiny", "base", "small", "medium", "large", "turbo"]
        )
        self.whisper_model.setCurrentText(
            str(QSettings().value("transcription/whisper_model", "tiny", type=str))
        )
        self.whisper_model.currentTextChanged.connect(self._check_whisper)
        layout.addWidget(self.whisper_model)
        self.whisper_status = QLabel("Checking Whisper model…")
        self.whisper_status.setWordWrap(True)
        layout.addWidget(self.whisper_status)
        self.download_whisper_button = QPushButton("Download Whisper model")
        self.download_whisper_button.clicked.connect(self._download_whisper)
        layout.addWidget(self.download_whisper_button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
        self._check()
        self._check_whisper()

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

    def _check_whisper(self, _model: str = "") -> None:
        model = self.whisper_model.currentText()
        QSettings().setValue("transcription/whisper_model", model)
        if not self.core:
            self.whisper_status.setText("The transcription core is unavailable.")
            self.download_whisper_button.setEnabled(False)
            return
        future = self.core.call("checkWhisperModel", model)

        def done(completed) -> None:
            try:
                installed = bool(completed.result())
                message = (
                    f"Whisper {model} is ready."
                    if installed
                    else f"Whisper {model} is not downloaded yet."
                )
                can_download = not installed
            except (RuntimeError, ValueError, OSError) as error:
                message = f"Could not check Whisper model: {error}"
                can_download = True

            def update() -> None:
                self.whisper_status.setText(message)
                self.download_whisper_button.setEnabled(can_download)

            QTimer.singleShot(0, self, update)

        future.add_done_callback(done)

    def _download_whisper(self) -> None:
        if not self.core:
            return
        model = self.whisper_model.currentText()
        self.download_whisper_button.setEnabled(False)
        self.whisper_status.setText(f"Downloading Whisper {model}…")
        future = self.core.call("downloadWhisperModel", {"model": model})

        def done(completed) -> None:
            try:
                completed.result()
                message = f"Whisper {model} is ready for offline transcription."
            except (RuntimeError, ValueError, OSError) as error:
                message = f"Whisper download failed: {error}"

            def update() -> None:
                self.whisper_status.setText(message)
                self.download_whisper_button.setEnabled(True)

            QTimer.singleShot(0, self, update)

        future.add_done_callback(done)
