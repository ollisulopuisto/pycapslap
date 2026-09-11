import time

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)


class VideoPlayerWidget(QWidget):
    """
    Native hardware-accelerated video player with seek latency instrumentation.
    """
    seek_latency_measured = Signal(float)  # Latency in ms
    position_changed = Signal(int)         # Position in ms
    duration_changed = Signal(int)         # Duration in ms

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self._pending_seek_time: float | None = None
        self._pending_target_ms: int | None = None
        self._is_scrubbing = False

        self._setup_player()
        self._setup_ui()

    def _setup_player(self) -> None:
        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.media_player.setAudioOutput(self.audio_output)

        self.video_widget = QVideoWidget(self)
        self.media_player.setVideoOutput(self.video_widget)

        self.media_player.positionChanged.connect(self._on_position_changed)
        self.media_player.durationChanged.connect(self._on_duration_changed)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Video Surface
        layout.addWidget(self.video_widget, stretch=1)

        # Controls Bar
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(8, 4, 8, 8)
        controls_layout.setSpacing(8)

        # Play/Pause button
        self.play_btn = QPushButton("Play")
        self.play_btn.setFixedWidth(65)
        self.play_btn.clicked.connect(self.toggle_play_pause)
        controls_layout.addWidget(self.play_btn)

        # Time label (current)
        self.time_lbl = QLabel("00:00")
        controls_layout.addWidget(self.time_lbl)

        # Timeline Slider (Scrubber)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderPressed.connect(self._on_slider_pressed)
        self.slider.sliderMoved.connect(self._on_slider_moved)
        self.slider.sliderReleased.connect(self._on_slider_released)
        controls_layout.addWidget(self.slider, stretch=1)

        # Duration label
        self.duration_lbl = QLabel("00:00")
        controls_layout.addWidget(self.duration_lbl)

        # Seek latency indicator
        self.latency_lbl = QLabel("Seek: -- ms")
        self.latency_lbl.setStyleSheet("color: #888888; font-size: 11px;")
        controls_layout.addWidget(self.latency_lbl)

        layout.addLayout(controls_layout)

        # Keyboard shortcuts: Space = Play/Pause, Left/Right = Seek 1 sec
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, activated=self.toggle_play_pause)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, activated=lambda: self.seek_relative(-1000))
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, activated=lambda: self.seek_relative(1000))

    def load_video(self, file_path: str) -> None:
        url = QUrl.fromLocalFile(file_path)
        self.media_player.setSource(url)
        self.play_btn.setText("Play")

    def toggle_play_pause(self) -> None:
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            self.play_btn.setText("Play")
        else:
            self.media_player.play()
            self.play_btn.setText("Pause")

    def seek_to_ms(self, pos_ms: int) -> None:
        self._pending_seek_time = time.perf_counter()
        self._pending_target_ms = pos_ms
        self.media_player.setPosition(pos_ms)

    def seek_relative(self, delta_ms: int) -> None:
        current = self.media_player.position()
        target = max(0, min(self.media_player.duration(), current + delta_ms))
        self.seek_to_ms(target)

    def _on_slider_pressed(self) -> None:
        self._is_scrubbing = True

    def _on_slider_moved(self, val: int) -> None:
        self.time_lbl.setText(self._format_time(val))
        self.seek_to_ms(val)

    def _on_slider_released(self) -> None:
        self._is_scrubbing = False
        self.seek_to_ms(self.slider.value())

    def _on_position_changed(self, pos_ms: int) -> None:
        if not self._is_scrubbing:
            self.slider.setValue(pos_ms)
            self.time_lbl.setText(self._format_time(pos_ms))

        # Check seek latency if a seek was pending
        if self._pending_seek_time is not None:
            # Measure time from request to position response
            latency_ms = (time.perf_counter() - self._pending_seek_time) * 1000.0
            self._pending_seek_time = None
            self._pending_target_ms = None
            self.latency_lbl.setText(f"Seek: {latency_ms:.1f} ms")
            self.seek_latency_measured.emit(latency_ms)

        self.position_changed.emit(pos_ms)

    def _on_duration_changed(self, dur_ms: int) -> None:
        self.slider.setRange(0, dur_ms)
        self.duration_lbl.setText(self._format_time(dur_ms))
        self.duration_changed.emit(dur_ms)

    @staticmethod
    def _format_time(ms: int) -> str:
        s = ms // 1000
        m = s // 60
        s = s % 60
        return f"{m:02d}:{s:02d}"
