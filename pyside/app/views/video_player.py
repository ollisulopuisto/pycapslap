import time

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.views.caption_panel import format_timestamp
from app.views.tile_buttons import SMALL_QSS, icon
from app.views.video_canvas import VideoCanvasWidget


class Scrubber(QWidget):
    """The playback scrubber, laid out like the timeline: 0 at the left edge and
    the end at the right, so its playhead sits where the timeline's does."""

    sliderPressed = Signal()
    sliderMoved = Signal(int)
    sliderReleased = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._min = 0
        self._max = 0
        self._value = 0
        self._dragging = False
        self.setFixedHeight(18)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def setRange(self, low: int, high: int) -> None:
        self._min = low
        self._max = max(low, high)
        self._value = min(max(self._value, self._min), self._max)
        self.update()

    def value(self) -> int:
        return self._value

    def setValue(self, value: int) -> None:
        self._value = min(max(int(value), self._min), self._max)
        self.update()

    def _x_for(self, ms: int) -> float:
        if self._max <= self._min:
            return 0.0
        return (ms - self._min) / (self._max - self._min) * max(1, self.width() - 1)

    def _ms_at(self, x: float) -> int:
        fraction = min(1.0, max(0.0, x / max(1, self.width() - 1)))
        return int(self._min + fraction * (self._max - self._min))

    def _move_to(self, x: float) -> None:
        self._value = self._ms_at(x)
        self.update()
        self.sliderMoved.emit(self._value)

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        centre = self.height() / 2
        x = self._x_for(self._value)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#3f3f46"))
        painter.drawRoundedRect(QRectF(0, centre - 2, self.width(), 4), 2, 2)
        painter.setBrush(QColor("#6366f1"))
        painter.drawRoundedRect(QRectF(0, centre - 2, x, 4), 2, 2)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QPointF(x, centre), 6, 6)
        painter.end()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self.sliderPressed.emit()
            self._move_to(event.position().x())

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._dragging:
            self._move_to(event.position().x())

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.sliderReleased.emit()


class VideoPlayerWidget(QWidget):
    """
    Native hardware-accelerated video player with seek latency instrumentation
    and direct QVideoSink unified subtitle compositing.
    """

    seek_latency_measured = Signal(float)  # Latency in ms
    position_changed = Signal(int)  # Position in ms
    duration_changed = Signal(int)  # Duration in ms
    # "Set the trim's start / end here" — the window owns the trim, the player the buttons
    mark_in_requested = Signal()
    mark_out_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self._pending_seek_time: float | None = None
        self._pending_target_ms: int | None = None
        self._is_scrubbing = False
        # The trimmed part of the video. Stop returns to its start and playback stops at
        # its end; None means the video's own end.
        self._range_start_ms = 0
        self._range_end_ms: int | None = None
        self._frame_duration_ms = 1000 / 30

        self._setup_player()
        self._setup_ui()

    def _setup_player(self) -> None:
        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.media_player.setAudioOutput(self.audio_output)

        self.canvas = VideoCanvasWidget(self)
        self.overlay = self.canvas  # Alias for backward-compatible overlay access
        self.media_player.setVideoSink(self.canvas.sink)

        self.media_player.positionChanged.connect(self._on_position_changed)
        self.media_player.durationChanged.connect(self._on_duration_changed)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Video Canvas with direct subtitle rendering
        layout.addWidget(self.canvas, stretch=1)

        # Controls Bar
        # Two rows: the transport buttons, then the scrubber with its times. A
        # single row runs out of width on a narrow (vertical-video) window.
        self.setStyleSheet(SMALL_QSS)
        controls_layout = QVBoxLayout()
        controls_layout.setContentsMargins(0, 2, 0, 4)
        controls_layout.setSpacing(4)
        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(4)
        seek_row = QHBoxLayout()
        seek_row.setSpacing(8)

        # Play/Pause button
        self.play_btn = QPushButton("Play")
        self.play_btn.setIcon(icon("play"))
        self.play_btn.setIconSize(QSize(12, 12))
        self.play_btn.setFixedWidth(74)
        self.play_btn.clicked.connect(self.toggle_play_pause)
        buttons_row.addWidget(self.play_btn)

        # Stop: back to the start of the trim, to check where playback begins
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setIcon(icon("stop"))
        self.stop_btn.setIconSize(QSize(12, 12))
        self.stop_btn.setFixedWidth(68)
        self.stop_btn.setToolTip("Stop and go back to the start of the trim")
        self.stop_btn.clicked.connect(self.stop)
        buttons_row.addWidget(self.stop_btn)

        # Mark the trim's start / end at the playhead (also the I and O keys)
        self.mark_in_btn = QPushButton("I")
        self.mark_in_btn.setToolTip("Set the trim's start here (I)")
        self.mark_in_btn.clicked.connect(self.mark_in_requested)
        self.mark_out_btn = QPushButton("O")
        self.mark_out_btn.setToolTip("Set the trim's end here (O)")
        self.mark_out_btn.clicked.connect(self.mark_out_requested)
        for btn in (self.mark_in_btn, self.mark_out_btn):
            btn.setFixedWidth(32)
            # Clicking must not take focus, or Space would press the button
            # instead of playing and pausing.
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            buttons_row.addWidget(btn)

        # Scrubber, full width: it sits between the buttons and the times below
        self.slider = Scrubber()
        self.slider.setRange(0, 0)
        self.slider.sliderPressed.connect(self._on_slider_pressed)
        self.slider.sliderMoved.connect(self._on_slider_moved)
        self.slider.sliderReleased.connect(self._on_slider_released)

        # Times under the scrubber: the playhead on the left, the length on the right
        self.time_lbl = QLabel("00:00.000")
        seek_row.addWidget(self.time_lbl)
        seek_row.addStretch()
        self.duration_lbl = QLabel("00:00.000")
        seek_row.addWidget(self.duration_lbl)

        # Playback speed button (e.g. 1.0x, 1.25x, 1.5x, 2.0x)
        self.playback_rate: float = 1.0
        self.speed_btn = QPushButton("1.0x")
        self.speed_btn.setFixedWidth(52)
        self.speed_btn.setToolTip(
            "Playback speed: click to cycle (1.0x, 1.25x, 1.5x, 2.0x)"
        )
        self.speed_btn.clicked.connect(self._cycle_playback_speed)
        buttons_row.addStretch()
        buttons_row.addWidget(self.speed_btn)
        for btn in (
            self.play_btn,
            self.stop_btn,
            self.mark_in_btn,
            self.mark_out_btn,
            self.speed_btn,
        ):
            btn.setFixedHeight(24)

        # Seek latency indicator
        self.latency_lbl = QLabel("Seek: -- ms")
        self.latency_lbl.setStyleSheet("color: #888888; font-size: 11px;")
        seek_row.addWidget(self.latency_lbl)

        controls_layout.addLayout(buttons_row)
        controls_layout.addLayout(seek_row)
        # The scrubber sits last, right above the timeline it lines up with.
        controls_layout.addWidget(self.slider)
        layout.addLayout(controls_layout)

        # Keyboard shortcuts: + / - step one source frame.
        QShortcut(
            QKeySequence(Qt.Key.Key_Space), self, activated=self.toggle_play_pause
        )
        QShortcut(
            QKeySequence(Qt.Key.Key_Left),
            self,
            activated=lambda: self.seek_relative(-1000),
        )
        QShortcut(
            QKeySequence(Qt.Key.Key_Right),
            self,
            activated=lambda: self.seek_relative(1000),
        )
        QShortcut(
            QKeySequence(Qt.Key.Key_BracketRight),
            self,
            activated=self._increase_playback_speed,
        )
        QShortcut(
            QKeySequence(Qt.Key.Key_BracketLeft),
            self,
            activated=self._decrease_playback_speed,
        )
        QShortcut(
            QKeySequence(Qt.Key.Key_Plus), self, activated=lambda: self.step_frame(1)
        )
        QShortcut(
            QKeySequence(Qt.Key.Key_Minus), self, activated=lambda: self.step_frame(-1)
        )

    def set_frame_rate(self, fps: float) -> None:
        if fps > 0:
            self._frame_duration_ms = 1000.0 / fps

    def step_frame(self, direction: int) -> None:
        """Seek by exactly one frame at the loaded video's frame rate."""
        self.media_player.pause()
        self.seek_to_ms(
            round(self.media_player.position() + direction * self._frame_duration_ms)
        )

    def set_playback_rate(self, rate: float) -> None:
        """Set the media player playback rate (e.g. 1.0, 1.25, 1.5, 2.0)."""
        self.playback_rate = float(rate)
        self.media_player.setPlaybackRate(self.playback_rate)
        self.speed_btn.setText(f"{self.playback_rate}x")

    def _cycle_playback_speed(self) -> None:
        """Cycle through common playback speeds: 1.0x -> 1.25x -> 1.5x -> 2.0x -> 1.0x."""
        cycle_rates = [1.0, 1.25, 1.5, 2.0]
        try:
            cur_idx = cycle_rates.index(self.playback_rate)
            next_idx = (cur_idx + 1) % len(cycle_rates)
            self.set_playback_rate(cycle_rates[next_idx])
        except ValueError:
            self.set_playback_rate(1.0)

    def _increase_playback_speed(self) -> None:
        """Increase playback speed to next preset step."""
        presets = [0.75, 1.0, 1.25, 1.5, 1.75, 2.0]
        for p in presets:
            if p > self.playback_rate + 0.01:
                self.set_playback_rate(p)
                return

    def _decrease_playback_speed(self) -> None:
        """Decrease playback speed to previous preset step."""
        presets = [0.75, 1.0, 1.25, 1.5, 1.75, 2.0]
        for p in reversed(presets):
            if p < self.playback_rate - 0.01:
                self.set_playback_rate(p)
                return

    def load_video(self, file_path: str) -> None:
        url = QUrl.fromLocalFile(file_path)
        self.media_player.setSource(url)
        self._show_playing(False)

    def release(self) -> None:
        """Let go of the media before the widget goes away.

        The macOS backend keeps loading and seeking on its own timers; a player
        destroyed with a source still open left those firing into freed
        memory (a segfault in QTimerInfoList::activateTimers).
        """
        self.media_player.stop()
        self.media_player.setVideoSink(None)
        self.media_player.setSource(QUrl())

    def set_play_range(self, start_ms: int, end_ms: int | None) -> None:
        """The trimmed part of the video: Stop goes to its start, playback stops at its end."""
        self._range_start_ms = max(0, int(start_ms))
        self._range_end_ms = (
            None if end_ms is None else max(self._range_start_ms, int(end_ms))
        )

    def _at_or_past_range_end(self, pos_ms: int) -> bool:
        # Within one position update (~50 ms) of the end counts as there, or Play would
        # stop again at once after an auto-stop.
        return self._range_end_ms is not None and pos_ms >= self._range_end_ms - 50

    def _show_playing(self, playing: bool) -> None:
        if playing:
            self.play_btn.setText("Pause")
            self.play_btn.setIcon(icon("pause"))
        else:
            self.play_btn.setText("Play")
            self.play_btn.setIcon(icon("play"))

    def toggle_play_pause(self) -> None:
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            self._show_playing(False)
        else:
            # Past the trim's end there is nothing left to play: start the trim over.
            if self._at_or_past_range_end(self.media_player.position()):
                self.seek_to_ms(self._range_start_ms)
            self.media_player.play()
            self._show_playing(True)

    def stop(self) -> None:
        """Pause and go back to the start of the trim."""
        self.media_player.pause()
        self._show_playing(False)
        self.seek_to_ms(self._range_start_ms)

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
        # Playback stops at the trim's end and shows its last frame.
        if (
            not self._is_scrubbing
            and self._range_end_ms is not None
            and pos_ms >= self._range_end_ms
            and self.media_player.playbackState()
            == QMediaPlayer.PlaybackState.PlayingState
        ):
            self.media_player.pause()
            self._show_playing(False)
            if pos_ms > self._range_end_ms:
                self.seek_to_ms(self._range_end_ms)
                return
        self.canvas.current_pos_ms = pos_ms
        self.canvas.update()
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
        # The same mm:ss.mmm as the caption table, so the two can be compared.
        return format_timestamp(ms)
