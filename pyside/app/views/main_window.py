import base64
import json
import os
from pathlib import Path

import psutil
from PySide6.QtCore import QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QImage,
    QKeySequence,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from app.core_client import CoreClient
from app.models.captions import (
    CaptionSegment,
    CaptionStyle,
    ProjectState,
    apply_orphan_rules,
    combine_separated_syllables,
)
from app.models.review import ReviewMismatch, apply_review, review_export_dict
from app.views.caption_panel import CaptionPanelWidget
from app.views.settings_dialog import WhisperSettingsDialog, get_transcription_params
from app.views.timeline import VisualTimelineWidget
from app.views.video_canvas import SAFE_PLATFORMS
from app.views.video_player import VideoPlayerWidget


# What the export format dropdown offers, and the aspect each one asks the
# renderer for. "Source" keeps the video's own frame.
EXPORT_FORMATS: list[tuple[str, str]] = [
    ("Export: Source", "source"),
    ("Export: 9:16 Portrait", "9:16"),
    ("Export: 16:9 Landscape", "16:9"),
    ("Export: 1:1 Square", "1:1"),
    ("Export: 4:5 Vertical", "4:5"),
]

# Proof copy next to the full-size render: label, short side in pixels (0 = none).
PROOF_COPIES = [
    ("No proof copy", 0),
    ("+ 720p proof", 720),
    ("+ 540p proof", 540),
]

# Where the review page (review/ in this repo) is published by GitHub Pages.
REVIEW_PAGE_URL = "https://ollisulopuisto.github.io/pycapslap/"

# How many rendered cues to keep. Each is a full-frame ARGB pixmap, so this
# is a memory budget, not a hit-rate tuning knob.
LAYER_CACHE_SIZE = 24

# Renders allowed in flight at once. Each is two ffmpeg processes.
MAX_LAYER_RENDERS = 3


class MainWindow(QMainWindow):
    # Core replies arrive on the core client's reader thread. They reach the GUI
    # through this signal, queued onto the window's thread. QTimer.singleShot called
    # from that thread makes a timer object there and hands it to the GUI thread's
    # timer list, and the macOS test run crashed inside that list
    # (QTimerInfoList::activateTimers) with such timers pending.
    _gui_call = Signal(object)

    def __init__(
        self, core_client: CoreClient | None = None, parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.setWindowTitle("PyCapSlap — High-Performance Native Video Captions")
        self.resize(1300, 850)
        self.setMinimumSize(1000, 650)
        self.setAcceptDrops(True)

        self.core = core_client or CoreClient(parent=self)
        self._gui_call.connect(self._run_gui_call, Qt.ConnectionType.QueuedConnection)
        self.project = ProjectState()

        self._seek_latencies: list[float] = []

        # Caption layout as the renderer computes it, so the preview draws the
        # same blocks the burn will. Refreshed off a timer because every
        # keystroke in the cue table would otherwise hit the core.
        self._preview_cues: list[dict] = []
        # libass's own rendering of each cue, keyed by the cue's start. The
        # editor draws these instead of painting text itself, so what is on
        # screen is literally what the burn produces. Thrown away whenever
        # anything that feeds the ASS document changes.
        self._layer_cache: dict[int, QPixmap] = {}
        self._layer_pending: set[int] = set()
        self._layer_epoch = 0
        self._layer_wanted: dict | None = None
        self._layer_queue: list[dict] = []
        self._prefetched_block: tuple[int, int] | None = None
        # The canvas the renderer last laid the captions out on — the export
        # canvas, which is the source frame only when the two agree.
        self._canvas_size: tuple[int, int] | None = None
        # Scrubbing crosses a cue every few pixels; rendering each one it
        # passes over would keep two ffmpeg processes busy per cue for
        # nothing. Only the cue the user comes to rest on gets rendered.
        self._layer_timer = QTimer(self)
        self._layer_timer.setSingleShot(True)
        self._layer_timer.setInterval(150)
        self._layer_timer.timeout.connect(self._render_wanted_layer)
        self._layout_timer = QTimer(self)
        self._layout_timer.setSingleShot(True)
        self._layout_timer.setInterval(120)
        self._layout_timer.timeout.connect(self._request_preview_layout)

        self._setup_ui()
        self._setup_connections()
        self._setup_dark_theme()
        self._setup_perf_timer()

    def _setup_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(8)

        # Splitter between Player/Timeline (Left) and Inspector/Captions (Right)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left Column: Action Bar, Video Player + Overlay, Visual Timeline
        left_widget = QWidget()
        left_col = QVBoxLayout(left_widget)
        left_col.setContentsMargins(4, 4, 4, 4)
        left_col.setSpacing(8)

        # Top Action Bar
        action_bar = QHBoxLayout()
        self.open_btn = QPushButton("Open Video...")
        self.open_btn.clicked.connect(self.open_file_dialog)
        action_bar.addWidget(self.open_btn)

        self.save_btn = QPushButton("Save Project")
        self.save_btn.setToolTip(
            "Save captions to sidecar file (.capslap.json) [Cmd+S / Ctrl+S]"
        )
        self.save_btn.clicked.connect(self._on_save_requested)
        self.save_btn.setEnabled(False)
        action_bar.addWidget(self.save_btn)

        # Client review: send the captions to a client's browser, take the fixes back
        self.review_btn = QPushButton("Client Review")
        self.review_btn.setToolTip(
            "Send captions to a client to check and correct on the review page, "
            "then import what they send back"
        )
        review_menu = QMenu(self.review_btn)
        review_menu.addAction("Export for Review…", self._on_export_for_review)
        review_menu.addAction("Import Reviewed Captions…", self._on_import_review)
        review_menu.addSeparator()
        review_menu.addAction(
            "Open Review Page",
            lambda: QDesktopServices.openUrl(QUrl(REVIEW_PAGE_URL)),
        )
        self.review_btn.setMenu(review_menu)
        self.review_btn.setEnabled(False)
        action_bar.addWidget(self.review_btn)

        # The export format belongs here, not in a dialog at render time: it
        # decides the canvas the captions are laid out on, so the preview
        # cannot be honest about anything until it knows which one it is.
        self.format_combo = QComboBox()
        for label, value in EXPORT_FORMATS:
            self.format_combo.addItem(label, value)
        self.format_combo.setToolTip(
            "Aspect ratio of the exported video. The preview shows this frame."
        )
        self.format_combo.currentIndexChanged.connect(self._on_export_format_changed)
        action_bar.addWidget(self.format_combo)

        # A smaller copy from the same encode: small for clients to proof, the
        # full-size one for publishing.
        self.proof_combo = QComboBox()
        for label, side in PROOF_COPIES:
            self.proof_combo.addItem(label, side)
        self.proof_combo.setCurrentIndex(1)
        self.proof_combo.setToolTip(
            "Also render a smaller proof copy, in the same pass as the full-size video"
        )
        action_bar.addWidget(self.proof_combo)

        self.render_btn = QPushButton("Render Video")
        self.render_btn.setToolTip("Render and export video with burned-in captions")
        self.render_btn.setStyleSheet(
            "background-color: #4f46e5; color: #ffffff; font-weight: bold; padding: 5px 14px;"
        )
        self.render_btn.clicked.connect(self._on_render_video_requested)
        self.render_btn.setEnabled(False)
        action_bar.addWidget(self.render_btn)

        self.thumb_btn = QPushButton("Extract Thumbnail")
        self.thumb_btn.clicked.connect(self.trigger_extract_thumbnail)
        self.thumb_btn.setEnabled(False)
        action_bar.addWidget(self.thumb_btn)

        action_bar.addStretch()
        left_col.addLayout(action_bar)

        # Cmd+S / Ctrl+S shortcut for Save
        # I / O set the trim's start / end at the playhead, as in video editors: stop
        # playback on the right frame and mark it. Text fields keep their letters,
        # since a line edit claims plain keys before shortcuts see them.
        QShortcut(QKeySequence(Qt.Key.Key_I), self, activated=self._set_trim_start_here)
        QShortcut(QKeySequence(Qt.Key.Key_O), self, activated=self._set_trim_end_here)
        QShortcut(
            QKeySequence.StandardKey.Save, self, activated=self._on_save_requested
        )

        # Video Player Widget with embedded Caption Overlay
        self.player = VideoPlayerWidget(self)
        self.player.seek_latency_measured.connect(self._on_seek_latency)
        self.overlay = self.player.overlay
        left_col.addWidget(self.player, stretch=1)

        # Visual Timeline Widget
        self.timeline = VisualTimelineWidget(self)
        left_col.addWidget(self.timeline)

        splitter.addWidget(left_widget)

        # Right Column: Captions Panel (takes maximum space for caption text editing)
        right_widget = QWidget()
        right_col = QVBoxLayout(right_widget)
        right_col.setContentsMargins(4, 4, 4, 4)
        right_col.setSpacing(4)

        # Caption Editor & Inspector Panel
        self.caption_panel = CaptionPanelWidget(self)
        right_col.addWidget(self.caption_panel, stretch=1)

        # Internal labels retained for telemetry & unit tests without cluttering UI
        self.meta_lbl = QLabel("No video loaded\nDrop a file or click Open Video.")
        self.thumb_lbl = QLabel("No thumbnail generated yet")
        self.perf_lbl = QLabel("Measuring...")

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root_layout.addWidget(splitter)

        # Status Bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(14)
        self.progress_bar.setFixedWidth(160)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #27272a;
                border: 1px solid #3f3f46;
                border-radius: 4px;
                text-align: center;
                color: #e4e4e7;
                font-size: 10px;
                font-weight: 600;
            }
            QProgressBar::chunk {
                background-color: #6366f1;
                border-radius: 3px;
            }
        """)
        self.progress_bar.setVisible(False)
        self.status.addPermanentWidget(self.progress_bar)

        self.status.showMessage("Ready. Drop a 1080p video or click Open Video.")

    def _setup_connections(self) -> None:
        # Player signals
        self.player.position_changed.connect(self._on_position_changed)
        self.player.duration_changed.connect(self._on_duration_changed)
        # Pausing stops position updates, so the moment the user settles on a
        # frame is the moment to fetch the renderer's version of it.
        self.player.media_player.playbackStateChanged.connect(
            self._on_playback_state_changed
        )

        # Timeline signals
        self.timeline.seek_requested.connect(self.player.seek_to_ms)
        self.timeline.trim_range_changed.connect(self.player.set_play_range)
        self.player.mark_in_requested.connect(self._set_trim_start_here)
        self.player.mark_out_requested.connect(self._set_trim_end_here)
        self.timeline.segment_selected.connect(self._on_segment_selected)

        # Overlay signals
        self.overlay.anchor_changed.connect(self._on_overlay_anchor_changed)
        # Until a frame has been decoded the frame size is a guess, and every
        # layout computed from it is a guess too. Redo them once it is known.
        self.player.canvas.video_size_changed.connect(self._on_video_size_changed)

        # Caption Panel signals
        self.caption_panel.segment_selected.connect(self._on_segment_selected)
        self.caption_panel.position_override_changed.connect(
            self._on_panel_override_changed
        )
        self.caption_panel.apply_position_to_all_requested.connect(
            self._on_apply_position_to_all_requested
        )
        self.caption_panel.segment_updated.connect(self._on_segment_text_updated)
        self.caption_panel.segments_updated.connect(self._on_segments_updated)
        self.caption_panel.style_changed.connect(self._on_style_changed)
        self.caption_panel.save_requested.connect(self._on_save_requested)
        self.caption_panel.auto_place_requested.connect(self._on_auto_place_requested)
        self.caption_panel.transcribe_requested.connect(self._on_transcribe_requested)
        self.caption_panel.whisper_settings_requested.connect(
            self._on_whisper_settings_requested
        )
        self.caption_panel.add_cue_requested.connect(self._on_add_cue_requested)
        self.caption_panel.safe_platforms_changed.connect(
            self.player.canvas.set_active_safe_platforms
        )

        # Core signals
        self.core.progress.connect(self._on_core_progress)

    def _setup_dark_theme(self) -> None:
        self.setStyleSheet("""
            QMainWindow { background-color: #0f0f11; color: #f4f4f5; }
            QWidget { color: #f4f4f5; }
            QGroupBox { font-weight: bold; border: 1px solid #27272a; border-radius: 6px; margin-top: 10px; padding-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #a1a1aa; }
            QPushButton { background-color: #27272a; border: 1px solid #3f3f46; border-radius: 6px; padding: 5px 12px; font-weight: 500; }
            QPushButton:hover { background-color: #3f3f46; }
            QPushButton:pressed { background-color: #52525b; }
            QPushButton:disabled { background-color: #18181b; color: #52525b; border-color: #27272a; }
            QSlider::groove:horizontal { height: 6px; background: #27272a; border-radius: 3px; }
            QSlider::sub-page:horizontal { background: #6366f1; border-radius: 3px; }
            QSlider::handle:horizontal { background: #ffffff; width: 14px; margin: -4px 0; border-radius: 7px; }
            QStatusBar { background-color: #18181b; border-top: 1px solid #27272a; color: #a1a1aa; }
            QSplitter::handle { background-color: #27272a; }
        """)

    def _setup_perf_timer(self) -> None:
        self.perf_timer = QTimer(self)
        self.perf_timer.setInterval(1000)  # Update every 1s
        self.perf_timer.timeout.connect(self._update_telemetry)
        self.perf_timer.start()

    def set_caption_segments(self, segments: list[CaptionSegment]) -> None:
        self.project.segments = list(segments)
        self.timeline.set_segments(self.project.segments)
        self.caption_panel.set_segments(self.project.segments)
        self.schedule_preview_layout()

    def _on_style_changed(self, style: CaptionStyle) -> None:
        self.project.style = style
        self.project.is_dirty = True
        self.player.canvas.set_style(style)
        self.schedule_preview_layout()

    def schedule_preview_layout(self) -> None:
        """Ask the renderer for a fresh layout once the edits settle."""
        self._invalidate_caption_layers()
        self._layout_timer.start()

    def _invalidate_caption_layers(self) -> None:
        """Drop every rendered cue; the ASS document they came from is stale.

        The epoch bump makes in-flight renders land on nothing instead of
        overwriting the cache with pixels from the previous style.
        """
        self._layer_epoch += 1
        self._layer_cache.clear()
        self._layer_pending.clear()
        self._layer_wanted = None
        self._layer_queue.clear()
        self._prefetched_block = None
        self.overlay.set_caption_layer(None)

    def _preview_frame_size(self) -> tuple[int, int]:
        size = self.player.canvas.get_video_size()
        return size or (1080, 1920)

    def _export_format(self) -> str:
        return self.format_combo.currentData() or "source"

    def _canvas_frame_size(self) -> tuple[int, int]:
        """The frame the captions were laid out on, as the renderer sized it."""
        return self._canvas_size or self._preview_frame_size()

    def _on_video_size_changed(self, _w: int, _h: int) -> None:
        self.schedule_preview_layout()

    def _on_export_format_changed(self, _index: int) -> None:
        # Another canvas means another layout and other pixels: everything
        # rendered for the previous one is wrong.
        self.schedule_preview_layout()

    def _request_preview_layout(self) -> None:
        if not self.project.segments:
            self._preview_cues = []
            self._apply_preview_layout()
            return

        source_size = self._preview_frame_size()
        frame_w, frame_h = source_size
        style = self.project.style
        params = {
            "segments": [s.to_dict() for s in self.project.segments],
            "width": frame_w,
            "height": frame_h,
            "fontName": style.font_name,
            "fontSize": style.font_size,
            "textColor": style.text_color,
            "highlightWordColor": style.highlight_color,
            "outlineColor": style.outline_color,
            "outlineWidth": style.outline_width,
            "backgroundBox": style.background_box,
            "position": None,
            "karaoke": style.karaoke,
            "multiline": style.multiline,
            "justifyLines": style.justify_lines,
            "glowEffect": style.glow_effect,
            "positionOverrides": [o.to_dict() for o in self.project.position_overrides],
            "blockedBands": [],
            "exportFormat": self._export_format(),
        }

        try:
            fut = self.core.call("previewLayout", params)
        except Exception:
            return

        def on_done(f) -> None:
            try:
                result = f.result()
            except Exception:
                # No core, or it refused: the canvas keeps drawing its own
                # stand-in layout rather than going blank.
                return
            cues = (result or {}).get("cues", [])
            canvas = (
                int((result or {}).get("frameWidth", 0)),
                int((result or {}).get("frameHeight", 0)),
            )

            def apply(cues=cues, canvas=canvas, source=source_size) -> None:
                self._preview_cues = cues
                if canvas[0] > 0 and canvas[1] > 0:
                    self._canvas_size = canvas
                    # Padding only exists when the export canvas differs from
                    # the frame this layout was computed against.
                    self.player.canvas.set_export_canvas(
                        None if canvas == source else canvas
                    )
                self._apply_preview_layout()

            # Three-argument form: this runs on the core client's reader
            # thread, which has no event loop, so a timer created there would
            # never fire. Passing `self` as the context object queues the call
            # onto the GUI thread instead.
            self._in_gui(apply)

        fut.add_done_callback(on_done)

    # ---- Caption layers ---------------------------------------------------
    #
    # The editor's own painting can only ever approximate libass: it has to
    # guess at the same font, the same wrapping, the same outline geometry.
    # So for anything that stands still — paused, scrubbed, restyled — the
    # renderer is asked for the cue as pixels, on a transparent canvas the
    # size of the video frame, from the same ASS document the burn writes.
    # Dragging keeps the painted approximation, which follows the pointer for
    # free. Playback keeps whatever the block prefetch has already rendered.

    def _sync_caption_layer(self, cue: dict | None) -> None:
        if cue is None:
            self.overlay.set_caption_layer(None)
            return

        key = int(cue.get("startMs", 0))
        cached = self._layer_cache.get(key)
        self.overlay.set_caption_layer(cached)
        if cached is None:
            self._layer_wanted = cue
            self._layer_timer.start()

        # Karaoke cuts a caption into one cue per word, and the reader sees
        # all of them in a couple of seconds. Rendering the whole block as
        # soon as one of its windows comes up is what lets playback show the
        # real thing instead of the approximation.
        block = (int(cue.get("groupStartMs", key)), int(cue.get("groupEndMs", key)))
        if block != self._prefetched_block:
            self._prefetched_block = block
            self._prefetch_block(cue)

    def _prefetch_block(self, cue: dict) -> None:
        group = (
            int(cue.get("groupStartMs", -1)),
            int(cue.get("groupEndMs", -1)),
        )
        if group == (-1, -1):
            return
        for other in self._preview_cues:
            same_block = (
                int(other.get("groupStartMs", -2)),
                int(other.get("groupEndMs", -2)),
            ) == group
            if same_block:
                self._queue_caption_layer(other)
        self._pump_layer_queue()

    def _render_wanted_layer(self) -> None:
        cue = self._layer_wanted
        self._layer_wanted = None
        if cue is None:
            return
        pos_ms = self.player.media_player.position()
        current = self._cue_for_position(pos_ms)
        # Only render what the user actually stopped on.
        if current is None or int(current.get("startMs", 0)) != int(
            cue.get("startMs", 0)
        ):
            return
        # Straight to the front: this is the cue on screen right now.
        self._queue_caption_layer(cue, front=True)
        self._pump_layer_queue()

    def _layer_source_video(self) -> str:
        path = self.player.media_player.source().toLocalFile()
        return path or (self.project.video_path or "")

    def _queue_caption_layer(self, cue: dict, front: bool = False) -> None:
        key = int(cue.get("startMs", 0))
        if key in self._layer_cache or key in self._layer_pending:
            return
        self._layer_queue = [
            q for q in self._layer_queue if int(q.get("startMs", 0)) != key
        ]
        if front:
            self._layer_queue.insert(0, cue)
        else:
            self._layer_queue.append(cue)

    def _pump_layer_queue(self) -> None:
        """Keep a few renders in flight, never the whole queue at once.

        Each one is two ffmpeg processes; letting a twelve-word block start
        twelve of them at once would fight the video playback for the same
        cores it is trying to stay ahead of.
        """
        while self._layer_queue and len(self._layer_pending) < MAX_LAYER_RENDERS:
            cue = self._layer_queue.pop(0)
            key = int(cue.get("startMs", 0))
            if key in self._layer_cache or key in self._layer_pending:
                continue
            if not self._request_caption_layer(cue):
                break

    def _request_caption_layer(self, cue: dict) -> bool:
        source_file = self._layer_source_video()
        if not source_file or not self.project.segments:
            return False

        key = int(cue.get("startMs", 0))
        if key in self._layer_pending:
            return False

        # A karaoke window opens with a \fscx pop; render past it so the cue
        # is caught at rest and one render stands for the whole window.
        end_ms = int(cue.get("endMs", key))
        timestamp = min(key + 200, max(key, end_ms - 20))

        style = self.project.style
        params = {
            "inputVideo": str(Path(source_file).resolve()),
            "segments": [s.to_dict() for s in self.project.segments],
            "timestampMs": timestamp,
            # The same canvas the layout was computed on, which is what the
            # editor is now showing, padding and all.
            "exportFormat": self._export_format(),
            "karaoke": style.karaoke,
            "multiline": style.multiline,
            "justifyLines": style.justify_lines,
            "fontName": style.font_name,
            "fontSize": style.font_size,
            "textColor": style.text_color,
            "highlightWordColor": style.highlight_color,
            "outlineColor": style.outline_color,
            "outlineWidth": style.outline_width,
            "backgroundBox": style.background_box,
            "glowEffect": style.glow_effect,
            "positionOverrides": [o.to_dict() for o in self.project.position_overrides],
            "renderMode": "captions",
            "thumbnailHeight": self.player.canvas.layer_height(),
        }

        try:
            fut = self.core.call("generatePreviewFrame", params)
        except Exception:
            return False

        self._layer_pending.add(key)
        epoch = self._layer_epoch

        def release() -> None:
            self._layer_pending.discard(key)
            self._pump_layer_queue()

        def on_done(f) -> None:
            try:
                result = f.result()
            except Exception:
                self._in_gui(release)
                return
            data_uri = (result or {}).get("imageData", "")
            raw = data_uri.split(",", 1)[1] if "," in data_uri else ""
            if not raw:
                self._in_gui(release)
                return
            try:
                image = QImage.fromData(base64.b64decode(raw))
            except (ValueError, TypeError):
                self._in_gui(release)
                return

            def store(image=image) -> None:
                self._layer_pending.discard(key)
                self._pump_layer_queue()
                if epoch != self._layer_epoch or image.isNull():
                    return
                pixmap = QPixmap.fromImage(image)
                self._layer_cache[key] = pixmap
                # A full-frame layer is megabytes; keep only the handful of
                # cues around wherever the user is working.
                while len(self._layer_cache) > LAYER_CACHE_SIZE:
                    self._layer_cache.pop(next(iter(self._layer_cache)))
                pos_ms = self.player.media_player.position()
                current = self._cue_for_position(pos_ms)
                if current is not None and int(current.get("startMs", 0)) == key:
                    self.overlay.set_caption_layer(pixmap)

            self._in_gui(store)

        fut.add_done_callback(on_done)
        return True

    def _cue_for_position(self, pos_ms: int) -> dict | None:
        for cue in self._preview_cues:
            if cue.get("startMs", 0) <= pos_ms < cue.get("endMs", 0):
                return cue
        return None

    def _apply_preview_layout(self) -> None:
        pos_ms = self.player.media_player.position()
        cue = self._cue_for_position(pos_ms)
        self.overlay.set_layout_cue(cue, self._canvas_frame_size())
        self._sync_caption_layer(cue)

    def _on_position_changed(self, pos_ms: int) -> None:
        self.timeline.set_position(pos_ms)
        cue = self._cue_for_position(pos_ms)
        self.overlay.set_layout_cue(cue, self._canvas_frame_size())
        self._sync_caption_layer(cue)
        active = self.project.get_active_segment(pos_ms)
        if active:
            anchor_y = self.project.get_anchor_y_for_segment(active)
            self.overlay.set_segment(active, anchor_y, current_pos_ms=pos_ms)
        else:
            self.overlay.set_segment(None, current_pos_ms=pos_ms)

    def _on_playback_state_changed(self, _state) -> None:
        self._apply_preview_layout()

    def _on_segment_selected(self, seg: CaptionSegment) -> None:
        self.player.seek_to_ms(seg.start_ms)
        anchor_y = self.project.get_anchor_y_for_segment(seg)
        self.overlay.set_segment(seg, anchor_y)
        self.caption_panel.select_segment(seg, anchor_y)
        self.timeline.select_segment(seg)

    def _on_overlay_anchor_changed(self, anchor_pct: float) -> None:
        if self.overlay.current_segment:
            seg = self.overlay.current_segment
            self.project.set_segment_position_override(seg, anchor_pct)
            self.caption_panel.set_anchor_pct(anchor_pct, user_action=False)
            self.schedule_preview_layout()

    def _on_panel_override_changed(
        self, seg: CaptionSegment, anchor_pct: float
    ) -> None:
        self.project.set_segment_position_override(seg, anchor_pct)
        self.schedule_preview_layout()
        if self.overlay.current_segment == seg:
            self.overlay.set_segment(seg, anchor_pct)

    def _on_apply_position_to_all_requested(self, anchor_pct: float) -> None:
        self.project.apply_position_to_all(anchor_pct)
        self.schedule_preview_layout()
        pos_ms = self.player.media_player.position()
        self._on_position_changed(pos_ms)
        self.status.showMessage(
            f"Applied {anchor_pct:.1f}% vertical position to all captions.", 3000
        )

    def _on_segment_text_updated(self, seg: CaptionSegment) -> None:
        self.project.is_dirty = True
        self.timeline.update()
        self.schedule_preview_layout()
        if self.overlay.current_segment == seg:
            pos_ms = self.player.media_player.position()
            anchor_y = self.project.get_anchor_y_for_segment(seg)
            self.overlay.set_segment(seg, anchor_y, current_pos_ms=pos_ms)

    def _on_segments_updated(self, segments: list[CaptionSegment]) -> None:
        self.project.segments = list(segments)
        self.project.is_dirty = True
        self.timeline.set_segments(self.project.segments)
        self.schedule_preview_layout()
        pos_ms = self.player.media_player.position()
        self._on_position_changed(pos_ms)

    def _on_add_cue_requested(self) -> None:
        pos = self.player.media_player.position()
        start_ms = max(0, pos)
        end_ms = start_ms + 2500
        new_cue = CaptionSegment(
            start_ms=start_ms, end_ms=end_ms, text="New caption text"
        )
        self.project.segments.append(new_cue)
        self.project.segments.sort(key=lambda s: s.start_ms)
        self.project.is_dirty = True
        self.set_caption_segments(self.project.segments)
        self._on_segment_selected(new_cue)
        self.status.showMessage("Added new caption cue.", 2500)

    def _on_save_requested(self) -> None:
        self.caption_panel.commit_active_editor()
        self.project.segments = list(self.caption_panel.segments)
        if not self.project.video_path:
            return
        sidecar_path = self.project.get_default_sidecar_path()
        if not sidecar_path:
            return

        success = self.project.save_sidecar(sidecar_path)
        if success:
            self.status.showMessage(
                f"Saved {len(self.project.segments)} captions to sidecar.", 3000
            )
        else:
            self.status.showMessage("Failed to save captions sidecar.", 3000)

    def _in_gui(self, fn) -> None:
        """Run `fn` on the GUI thread, after the current event. Safe from any thread."""
        self._gui_call.emit(fn)

    @staticmethod
    def _run_gui_call(fn) -> None:
        fn()

    def _on_export_for_review(self) -> None:
        self.caption_panel.commit_active_editor()
        self.project.segments = list(self.caption_panel.segments)
        if not self.project.video_path or not self.project.segments:
            QMessageBox.information(
                self, "Client Review", "Load a video with captions first."
            )
            return
        default = f"{self.project.video_path}.review.capslap.json"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export for Review", default, "Captions (*.capslap.json *.json)"
        )
        if not path:
            return
        try:
            Path(path).write_text(
                json.dumps(review_export_dict(self.project), indent=2),
                encoding="utf-8",
            )
        except OSError as err:
            QMessageBox.warning(self, "Client Review", f"Could not save: {err}")
            return
        self.status.showMessage(
            "Exported for review. Send the file and the video to the client; "
            f"they open both on {REVIEW_PAGE_URL}",
            8000,
        )

    def _on_import_review(self) -> None:
        self.caption_panel.commit_active_editor()
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Reviewed Captions",
            os.path.dirname(self.project.video_path or ""),
            "Reviewed captions (*.capslap.json *.json)",
        )
        if path:
            self.import_review_file(path)

    def import_review_file(self, path: str) -> None:
        """Apply a client's reviewed captions and show what they changed and said."""
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("not a captions file")
            segments = list(self.caption_panel.segments)
            result = apply_review(segments, data)
        except (OSError, ValueError) as err:
            reason = (
                str(err)
                if isinstance(err, ReviewMismatch)
                else f"Could not read it: {err}"
            )
            QMessageBox.warning(self, "Import Review", reason)
            return
        if result.changed:
            self.project.segments = segments
            self.project.is_dirty = True
            self.set_caption_segments(segments)
            self._on_position_changed(self.player.media_player.position())
        message = result.summary()
        if result.comments:
            notes = "\n\n".join(
                f"#{n} “{text}”\n→ {comment}" for n, text, comment in result.comments
            )
            message += f"\n\nComments:\n\n{notes}"
        if result.changed:
            message += "\n\nSave the project to keep the changes."
        self.status.showMessage(result.summary(), 8000)
        QMessageBox.information(self, "Import Review", message)

    def _on_render_video_requested(self) -> None:
        self.caption_panel.commit_active_editor()
        self.project.segments = list(self.caption_panel.segments)
        # Keep sidecar file on disk synchronized so output and sidecar never diverge
        if self.project.get_default_sidecar_path():
            self.project.save_sidecar()
        source_file = self.player.media_player.source().toLocalFile()
        if not source_file:
            QMessageBox.information(self, "Render Video", "Please load a video first.")
            return

        if not self.project.segments:
            QMessageBox.information(
                self, "Render Video", "No caption segments available to render."
            )
            return

        # Whatever the editor has been previewing all along.
        export_fmt = self._export_format()

        trim_start_ms = self.timeline.trim_start_ms
        trim_end_ms = max(0, self.timeline.duration_ms - self.timeline.trim_end_ms)

        self.status.showMessage(
            f"Rendering {export_fmt} video with burned-in captions..."
        )
        self.render_btn.setEnabled(False)
        self.render_btn.setText("Rendering...")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

        params = {
            "inputVideo": str(Path(source_file).resolve()),
            "segments": [s.to_dict() for s in self.project.segments],
            "trimStartMs": trim_start_ms,
            "trimEndMs": trim_end_ms,
            "exportFormats": [export_fmt],
            "proofShortSide": self.proof_combo.currentData() or None,
            "karaoke": self.project.style.karaoke,
            "multiline": self.project.style.multiline,
            "justifyLines": self.project.style.justify_lines,
            "fontName": self.project.style.font_name,
            "fontSize": self.project.style.font_size,
            "textColor": self.project.style.text_color,
            "highlightWordColor": self.project.style.highlight_color,
            "outlineColor": self.project.style.outline_color,
            "outlineWidth": self.project.style.outline_width,
            "backgroundBox": self.project.style.background_box,
            "positionOverrides": [o.to_dict() for o in self.project.position_overrides],
        }

        fut = self.core.call("burn", params)

        def on_done(f):
            try:
                res = f.result()
                output_path = ""
                if isinstance(res, list) and res:
                    output_path = res[0].get("captionedVideo", "")
                    proof_path = res[0].get("proofVideo")
                    if proof_path:
                        output_path += f" (proof: {os.path.basename(proof_path)})"
                self._in_gui(lambda: self.render_btn.setEnabled(True))
                self._in_gui(lambda: self.render_btn.setText("Render Video"))
                self._in_gui(lambda: self.progress_bar.setVisible(False))
                self._in_gui(
                    lambda: self.status.showMessage(
                        f"Render complete: {output_path}", 8000
                    ),
                )
            except (RuntimeError, ValueError, OSError) as err:
                err_msg = str(err)
                self._in_gui(lambda: self.render_btn.setEnabled(True))
                self._in_gui(lambda: self.render_btn.setText("Render Video"))
                self._in_gui(lambda: self.progress_bar.setVisible(False))
                self._in_gui(
                    lambda msg=err_msg: QMessageBox.warning(self, "Render Error", msg),
                )

        fut.add_done_callback(on_done)

    def _set_trim_start_here(self) -> None:
        if not self.timeline.duration_ms:
            return
        self.timeline.set_trim_start_at(self.player.media_player.position())
        self.status.showMessage(
            f"Trim start set to {self._format_trim_time(self.timeline.trim_start_ms)}",
            2000,
        )

    def _set_trim_end_here(self) -> None:
        if not self.timeline.duration_ms:
            return
        self.timeline.set_trim_end_at(self.player.media_player.position())
        self.status.showMessage(
            f"Trim end set to {self._format_trim_time(self.timeline.trim_end_ms)}",
            2000,
        )

    @staticmethod
    def _format_trim_time(ms: int) -> str:
        return f"{ms // 60000:02d}:{(ms // 1000) % 60:02d}.{(ms % 1000) // 100}"

    def _sync_play_range(self) -> None:
        """Give the player the timeline's trim, so Stop and playback respect it."""
        self.player.set_play_range(
            self.timeline.trim_start_ms, self.timeline.trim_end_ms
        )

    def _on_duration_changed(self, duration_ms: int) -> None:
        self.timeline.set_duration(duration_ms)
        self._sync_play_range()
        if self.project.video:
            self.project.video.duration_sec = max(0, duration_ms) / 1000.0

    def _on_auto_place_requested(self) -> None:
        if not self.project.segments:
            QMessageBox.information(
                self, "Auto Dodge", "No caption segments available to position."
            )
            return

        source_file = self.player.media_player.source().toLocalFile()
        if not source_file:
            return

        blocked_bands: list[tuple[float, float]] = []
        for plat_id in self.caption_panel.active_safe_platforms:
            plat = SAFE_PLATFORMS.get(plat_id)
            if plat:
                for reg in plat.regions:
                    blocked_bands.append((reg.top, reg.top + reg.height))

        export_fmt = self._export_format()

        self.status.showMessage("Running automatic caption placement via Rust core...")
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)

        params = {
            "inputVideo": str(Path(source_file).resolve()),
            "segments": [s.to_dict() for s in self.project.segments],
            "exportFormat": export_fmt,
            "karaoke": self.project.style.karaoke,
            "multiline": self.project.style.multiline,
            "justifyLines": self.project.style.justify_lines,
            "fontName": self.project.style.font_name,
            "fontSize": self.project.style.font_size,
            "textColor": self.project.style.text_color,
            "highlightWordColor": self.project.style.highlight_color,
            "outlineColor": self.project.style.outline_color,
            "outlineWidth": self.project.style.outline_width,
            "backgroundBox": self.project.style.background_box,
            "blockedBands": blocked_bands,
        }

        fut = self.core.call("autoPlaceCaptions", params)

        def on_done(f):
            try:
                res = f.result()
                overrides_data = res.get("positionOverrides", [])
                moved = res.get("moved", 0)
                from app.models.captions import PositionOverride

                self.project.position_overrides = [
                    PositionOverride.from_dict(o) for o in overrides_data
                ]
                self.project.is_dirty = True
                self._in_gui(lambda: self.progress_bar.setVisible(False))
                self._in_gui(
                    lambda: self.status.showMessage(
                        f"Auto Dodge complete: moved {moved} captions.", 4000
                    ),
                )
                self._in_gui(self.overlay.update)
            except (RuntimeError, ValueError, OSError) as err:
                err_msg = str(err)
                self._in_gui(lambda: self.progress_bar.setVisible(False))
                self._in_gui(
                    lambda msg=err_msg: QMessageBox.warning(
                        self, "Auto Dodge Error", msg
                    ),
                )

        fut.add_done_callback(on_done)

    def _on_whisper_settings_requested(self) -> None:
        dlg = WhisperSettingsDialog(self.core, self)
        dlg.exec()

    def _on_transcribe_requested(self) -> None:
        source_file = self.player.media_player.source().toLocalFile()
        if not source_file:
            QMessageBox.information(self, "Transcribe", "Please load a video first.")
            return

        provider_params = get_transcription_params()
        provider_label = (
            "OpenAI API" if provider_params["model"] == "whisper-1" else "local Whisper"
        )
        self.status.showMessage(
            f"Transcribing audio via Rust core ({provider_label})..."
        )
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)

        params = {
            "inputVideo": str(Path(source_file).resolve()),
            "exportFormats": [self._export_format()],
            "karaoke": self.project.style.karaoke,
            # Never one cue per word: whisper's own phrase segments carry
            # per-word timings in `words`, which is what karaoke highlights
            # from. Splitting the transcript into words instead put a single
            # word on screen at a time, since the burner shows the cues as
            # they are authored.
            "splitByWords": False,
            **provider_params,
        }

        fut = self.core.call("transcribe", params)

        def on_done(f):
            try:
                res = f.result()
                transcription = res.get("transcription", {})
                segments_raw = transcription.get("segments", [])
                new_segs = [CaptionSegment.from_dict(s) for s in segments_raw]
                new_segs = combine_separated_syllables(new_segs)
                new_segs = apply_orphan_rules(new_segs)
                self._in_gui(lambda: self.progress_bar.setVisible(False))
                self._in_gui(lambda: self.set_caption_segments(new_segs))
                self._in_gui(
                    lambda: self.status.showMessage(
                        f"Transcription finished: {len(new_segs)} segments.", 4000
                    ),
                )
            except (RuntimeError, ValueError, OSError) as err:
                err_msg = str(err)
                self._in_gui(lambda: self.progress_bar.setVisible(False))
                self._in_gui(
                    lambda msg=err_msg: QMessageBox.warning(
                        self, "Transcription Error", msg
                    ),
                )

        fut.add_done_callback(on_done)

    def _on_core_progress(self, req_id: str, status: str, progress: float) -> None:
        if isinstance(status, (int, float)) and isinstance(progress, str):
            status, progress = progress, status

        try:
            val = float(progress)
            if 0.0 < val <= 1.0:
                val = val * 100.0
            pct_val = max(0, min(100, int(round(val))))
            pct_str = f"{pct_val}%"
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(pct_val)
            self.progress_bar.setVisible(True)
        except (ValueError, TypeError):
            pct_str = ""

        prefix = f"Core [{req_id[:6]}]" if req_id else "Core"
        if pct_str and pct_str not in str(status):
            display_msg = f"{prefix}: {pct_str} — {status}"
        else:
            display_msg = f"{prefix}: {status}"

        self.status.showMessage(display_msg, 4000)

        if (
            not self.render_btn.isEnabled()
            and "render" in self.render_btn.text().lower()
            and pct_str
        ):
            self.render_btn.setText(f"Rendering ({pct_str})...")

    def _update_telemetry(self) -> None:
        process = psutil.Process(os.getpid())
        gui_rss = process.memory_info().rss / (1024 * 1024)

        core_rss = 0.0
        if self.core.proc and self.core.proc.poll() is None:
            try:
                core_proc = psutil.Process(self.core.proc.pid)
                core_rss = core_proc.memory_info().rss / (1024 * 1024)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        total_rss = gui_rss + core_rss
        avg_seek = (
            sum(self._seek_latencies[-10:]) / len(self._seek_latencies[-10:])
            if self._seek_latencies
            else 0.0
        )

        self.perf_lbl.setText(
            f"PySide6 GUI RSS : {gui_rss:6.2f} MB\n"
            f"Rust Core RSS   : {core_rss:6.2f} MB\n"
            f"Total RSS       : {total_rss:6.2f} MB\n"
            f"Last Seek Lat   : {self._seek_latencies[-1] if self._seek_latencies else 0.0:6.1f} ms\n"
            f"Avg Seek (10)   : {avg_seek:6.1f} ms"
        )

    def _on_seek_latency(self, latency_ms: float) -> None:
        self._seek_latencies.append(latency_ms)
        self.status.showMessage(f"Seek executed in {latency_ms:.1f} ms", 2000)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path and os.path.exists(file_path):
                self.load_video(file_path)
                break

    def open_file_dialog(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Video",
            "",
            "Video Files (*.mp4 *.mov *.mkv *.avi *.webm *.wmv *.m4v *.ts);;All Files (*)",
        )
        if file_path:
            self.load_video(file_path)

    def load_video(self, file_path: str) -> None:
        self.status.showMessage(f"Loading video: {os.path.basename(file_path)}...")
        self.timeline.reset_trim_range()
        self._sync_play_range()
        self.player.load_video(file_path)
        self.thumb_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        self.review_btn.setEnabled(True)
        self.render_btn.setEnabled(True)

        self.project.load_video(file_path, {})
        # Check if sidecar exists
        if self.project.load_sidecar() and self.project.segments:
            self.set_caption_segments(self.project.segments)
            if self.project.style:
                self.caption_panel.set_style(self.project.style)
                self.player.canvas.set_style(self.project.style)
            self.status.showMessage(
                f"Loaded sidecar with {len(self.project.segments)} captions."
            )
        else:
            def_style = self.caption_panel.preset_manager.get_default_style()
            if def_style:
                self.caption_panel.set_style(def_style)
                self.player.canvas.set_style(def_style)
                self.project.style = def_style
            self.set_caption_segments([])
            self.status.showMessage(
                "Video loaded. Click 'Transcribe Audio' or '+ Add' to create captions.",
                5000,
            )

        # Trigger initial position sync
        self._on_position_changed(0)
        self.trigger_extract_thumbnail()

        self.setWindowTitle(f"PyCapSlap — {os.path.basename(file_path)}")
        self.meta_lbl.setText(
            f"File: {os.path.basename(file_path)}\n"
            f"Path: {file_path}\n"
            f"Size: {os.path.getsize(file_path) / (1024 * 1024):.1f} MB"
        )

    def trigger_extract_thumbnail(self) -> None:
        video_path = self.player.media_player.source().toLocalFile()
        if not video_path and self.project.video_path:
            video_path = self.project.video_path
        if not video_path:
            return
        self.status.showMessage("Extracting thumbnail via Rust core...")
        self.thumb_btn.setEnabled(False)
        self.thumb_btn.setText("Extracting...")
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)

        fut = self.core.call(
            "extractFirstFrame", {"videoPath": str(Path(video_path).resolve())}
        )

        def on_done(f):
            try:
                res = f.result()
                data_uri = res.get("imageData", "")
                if "," in data_uri:
                    b64 = data_uri.split(",", 1)[1]
                    raw_bytes = base64.b64decode(b64)
                    qimg = QImage.fromData(raw_bytes)

                    def update_ui(img=qimg):
                        pixmap = QPixmap.fromImage(img)
                        thumb_sz = self.thumb_lbl.size()
                        target_size = (
                            thumb_sz
                            if (thumb_sz.width() > 0 and thumb_sz.height() > 0)
                            else QSize(320, 180)
                        )
                        scaled = pixmap.scaled(
                            target_size,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                        self.thumb_lbl.setPixmap(scaled)
                        self.player.canvas.set_fallback_pixmap(pixmap)
                        self.thumb_btn.setEnabled(True)
                        self.thumb_btn.setText("Extract Thumbnail")
                        self.progress_bar.setRange(0, 100)
                        self.progress_bar.setValue(100)
                        self.progress_bar.setVisible(False)
                        self.status.showMessage("Thumbnail loaded.", 2000)

                    self._in_gui(update_ui)
                else:

                    def reset_no_img():
                        self.thumb_btn.setEnabled(True)
                        self.thumb_btn.setText("Extract Thumbnail")
                        self.progress_bar.setRange(0, 100)
                        self.progress_bar.setVisible(False)

                    self._in_gui(reset_no_img)
            except (RuntimeError, ValueError, OSError) as err:
                err_msg = str(err)

                def reset_err(msg=err_msg):
                    self.thumb_btn.setEnabled(True)
                    self.thumb_btn.setText("Extract Thumbnail")
                    self.progress_bar.setRange(0, 100)
                    self.progress_bar.setVisible(False)
                    QMessageBox.warning(self, "Error", msg)

                self._in_gui(reset_err)

        fut.add_done_callback(on_done)

    def closeEvent(self, event) -> None:
        self.perf_timer.stop()
        self.core.close()
        super().closeEvent(event)
