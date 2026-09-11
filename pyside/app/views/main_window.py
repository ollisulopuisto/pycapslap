import base64
import os
from pathlib import Path

import psutil
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import (
    QDragEnterEvent,
    QDropEvent,
    QImage,
    QKeySequence,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from app.core_client import CoreClient
from app.models.captions import CaptionSegment, ProjectState
from app.views.caption_panel import CaptionPanelWidget
from app.views.timeline import VisualTimelineWidget
from app.views.video_player import VideoPlayerWidget


class MainWindow(QMainWindow):
    def __init__(self, core_client: CoreClient | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("PyCapSlap — High-Performance Native Video Captions")
        self.resize(1300, 850)
        self.setMinimumSize(1000, 650)
        self.setAcceptDrops(True)

        self.core = core_client or CoreClient(parent=self)
        self.project = ProjectState()

        self._seek_latencies: list[float] = []

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
        self.save_btn.setToolTip("Save captions to sidecar file (.capslap.json) [Cmd+S / Ctrl+S]")
        self.save_btn.clicked.connect(self._on_save_requested)
        self.save_btn.setEnabled(False)
        action_bar.addWidget(self.save_btn)

        self.render_btn = QPushButton("Render Video")
        self.render_btn.setToolTip("Render and export video with burned-in captions")
        self.render_btn.setStyleSheet("background-color: #4f46e5; color: #ffffff; font-weight: bold; padding: 5px 14px;")
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
        QShortcut(QKeySequence.StandardKey.Save, self, activated=self._on_save_requested)

        # Video Player Widget with embedded Caption Overlay
        self.player = VideoPlayerWidget(self)
        self.player.seek_latency_measured.connect(self._on_seek_latency)
        self.overlay = self.player.overlay
        left_col.addWidget(self.player, stretch=1)

        # Visual Timeline Widget
        self.timeline = VisualTimelineWidget(self)
        left_col.addWidget(self.timeline)

        splitter.addWidget(left_widget)

        # Right Column: Captions Panel + Metadata & Telemetry
        right_widget = QWidget()
        right_col = QVBoxLayout(right_widget)
        right_col.setContentsMargins(4, 4, 4, 4)
        right_col.setSpacing(8)

        # Caption Editor & Inspector Panel
        self.caption_panel = CaptionPanelWidget(self)
        right_col.addWidget(self.caption_panel, stretch=2)

        # Video Metadata Box
        meta_box = QGroupBox("Video Metadata")
        meta_layout = QVBoxLayout(meta_box)
        self.meta_lbl = QLabel("No video loaded\nDrop a file or click Open Video.")
        self.meta_lbl.setWordWrap(True)
        meta_layout.addWidget(self.meta_lbl)
        right_col.addWidget(meta_box)

        # Thumbnail Preview Box
        thumb_box = QGroupBox("Rust Thumbnail Preview")
        thumb_layout = QVBoxLayout(thumb_box)
        self.thumb_lbl = QLabel("No thumbnail generated yet")
        self.thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_lbl.setMinimumHeight(120)
        self.thumb_lbl.setStyleSheet("background-color: #1a1a1a; border-radius: 4px;")
        thumb_layout.addWidget(self.thumb_lbl)
        right_col.addWidget(thumb_box)

        # Live Performance Telemetry
        perf_box = QGroupBox("Live Memory & Latency Telemetry")
        perf_layout = QVBoxLayout(perf_box)
        self.perf_lbl = QLabel("Measuring...")
        self.perf_lbl.setStyleSheet("font-family: monospace; font-size: 11px; color: #4ade80;")
        perf_layout.addWidget(self.perf_lbl)
        right_col.addWidget(perf_box)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root_layout.addWidget(splitter)

        # Status Bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Ready. Drop a 1080p video or click Open Video.")

    def _setup_connections(self) -> None:
        # Player signals
        self.player.position_changed.connect(self._on_position_changed)
        self.player.duration_changed.connect(self.timeline.set_duration)

        # Timeline signals
        self.timeline.seek_requested.connect(self.player.seek_to_ms)
        self.timeline.segment_selected.connect(self._on_segment_selected)

        # Overlay signals
        self.overlay.anchor_changed.connect(self._on_overlay_anchor_changed)

        # Caption Panel signals
        self.caption_panel.segment_selected.connect(self._on_segment_selected)
        self.caption_panel.position_override_changed.connect(self._on_panel_override_changed)
        self.caption_panel.segment_updated.connect(self._on_segment_text_updated)
        self.caption_panel.save_requested.connect(self._on_save_requested)
        self.caption_panel.auto_place_requested.connect(self._on_auto_place_requested)
        self.caption_panel.transcribe_requested.connect(self._on_transcribe_requested)
        self.caption_panel.add_cue_requested.connect(self._on_add_cue_requested)

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

    def _on_position_changed(self, pos_ms: int) -> None:
        self.timeline.set_position(pos_ms)
        active = self.project.get_active_segment(pos_ms)
        if active:
            anchor_y = self.project.get_anchor_y_for_segment(active)
            self.overlay.set_segment(active, anchor_y)
        else:
            self.overlay.set_segment(None)

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

    def _on_panel_override_changed(self, seg: CaptionSegment, anchor_pct: float) -> None:
        self.project.set_segment_position_override(seg, anchor_pct)
        if self.overlay.current_segment == seg:
            self.overlay.set_segment(seg, anchor_pct)

    def _on_segment_text_updated(self, seg: CaptionSegment) -> None:
        self.project.is_dirty = True
        self.timeline.update()
        if self.overlay.current_segment == seg:
            self.overlay.update()

    def _on_add_cue_requested(self) -> None:
        pos = self.player.media_player.position()
        start_ms = max(0, pos)
        end_ms = start_ms + 2500
        new_cue = CaptionSegment(start_ms=start_ms, end_ms=end_ms, text="New caption text")
        self.project.segments.append(new_cue)
        self.project.segments.sort(key=lambda s: s.start_ms)
        self.project.is_dirty = True
        self.set_caption_segments(self.project.segments)
        self._on_segment_selected(new_cue)
        self.status.showMessage("Added new caption cue.", 2500)

    def _on_save_requested(self) -> None:
        success = self.project.save_sidecar()
        if success:
            self.status.showMessage("Captions saved successfully to sidecar (.capslap.json).", 3000)
        else:
            self.status.showMessage("Failed to save captions sidecar.", 3000)

    def _on_render_video_requested(self) -> None:
        source_file = self.player.media_player.source().toLocalFile()
        if not source_file:
            QMessageBox.information(self, "Render Video", "Please load a video first.")
            return

        if not self.project.segments:
            QMessageBox.information(self, "Render Video", "No caption segments available to render.")
            return

        # Choose export aspect ratio format
        default_fmt = "16:9"
        if (
            self.project.video
            and self.project.video.width > 0
            and self.project.video.height > self.project.video.width
        ):
            default_fmt = "9:16"

        format_options = [
            "16:9 (Landscape / YouTube)",
            "9:16 (Portrait / TikTok / Reels)",
            "1:1 (Square / Instagram)",
            "4:5 (Vertical Feed)",
        ]
        default_idx = 0 if default_fmt == "16:9" else 1

        chosen, ok = QInputDialog.getItem(
            self,
            "Render Video",
            "Choose export format:",
            format_options,
            default_idx,
            False,
        )
        if not ok or not chosen:
            return

        export_fmt = chosen.split()[0]

        self.status.showMessage(f"Rendering {export_fmt} video with burned-in captions...")
        self.render_btn.setEnabled(False)
        self.render_btn.setText("Rendering...")

        params = {
            "inputVideo": str(Path(source_file).resolve()),
            "segments": [s.to_dict() for s in self.project.segments],
            "exportFormats": [export_fmt],
            "karaoke": False,
            "positionOverrides": [o.to_dict() for o in self.project.position_overrides],
        }

        fut = self.core.call("burn", params)

        def on_done(f):
            try:
                res = f.result()
                output_path = ""
                if isinstance(res, list) and res:
                    output_path = res[0].get("captionedVideo", "")
                QTimer.singleShot(0, lambda: self.render_btn.setEnabled(True))
                QTimer.singleShot(0, lambda: self.render_btn.setText("Render Video"))
                QTimer.singleShot(0, lambda: self.status.showMessage(f"Render complete: {output_path}", 6000))
                QTimer.singleShot(0, lambda: QMessageBox.information(
                    self,
                    "Export Complete",
                    f"Video rendered successfully!\n\nOutput saved to:\n{output_path}",
                ))
            except (RuntimeError, ValueError, OSError) as err:
                err_msg = str(err)
                QTimer.singleShot(0, lambda: self.render_btn.setEnabled(True))
                QTimer.singleShot(0, lambda: self.render_btn.setText("Render Video"))
                QTimer.singleShot(0, lambda msg=err_msg: QMessageBox.warning(self, "Render Error", msg))

        fut.add_done_callback(on_done)

    def _on_auto_place_requested(self) -> None:
        if not self.project.segments:
            QMessageBox.information(self, "Auto Dodge", "No caption segments available to position.")
            return

        source_file = self.player.media_player.source().toLocalFile()
        if not source_file:
            return

        self.status.showMessage("Running automatic caption placement via Rust core...")
        params = {
            "videoPath": str(Path(source_file).resolve()),
            "segments": [s.to_dict() for s in self.project.segments],
            "positionOverrides": [o.to_dict() for o in self.project.position_overrides],
        }

        fut = self.core.call("autoPlaceCaptions", params)

        def on_done(f):
            try:
                res = f.result()
                overrides_data = res.get("positionOverrides", [])
                moved = res.get("moved", 0)
                from app.models.captions import PositionOverride
                self.project.position_overrides = [PositionOverride.from_dict(o) for o in overrides_data]
                self.project.is_dirty = True
                QTimer.singleShot(0, lambda: self.status.showMessage(f"Auto Dodge complete: moved {moved} captions.", 4000))
                QTimer.singleShot(0, self.overlay.update)
            except (RuntimeError, ValueError, OSError) as err:
                err_msg = str(err)
                QTimer.singleShot(0, lambda msg=err_msg: QMessageBox.warning(self, "Auto Dodge Error", msg))

        fut.add_done_callback(on_done)

    def _on_transcribe_requested(self) -> None:
        source_file = self.player.media_player.source().toLocalFile()
        if not source_file:
            QMessageBox.information(self, "Transcribe", "Please load a video first.")
            return

        self.status.showMessage("Transcribing audio via Rust core...")
        params = {
            "inputVideo": str(Path(source_file).resolve()),
            "splitByWords": True,
            "model": "tiny",
            "language": None,
        }

        fut = self.core.call("transcribe", params)

        def on_done(f):
            try:
                res = f.result()
                transcription = res.get("transcription", {})
                segments_raw = transcription.get("segments", [])
                new_segs = [CaptionSegment.from_dict(s) for s in segments_raw]
                QTimer.singleShot(0, lambda: self.set_caption_segments(new_segs))
                QTimer.singleShot(0, lambda: self.status.showMessage(f"Transcription finished: {len(new_segs)} segments.", 4000))
            except (RuntimeError, ValueError, OSError) as err:
                err_msg = str(err)
                QTimer.singleShot(0, lambda msg=err_msg: QMessageBox.warning(self, "Transcription Error", msg))

        fut.add_done_callback(on_done)

    def _on_core_progress(self, req_id: str, pct: float, msg: str) -> None:
        self.status.showMessage(f"Core [{req_id[:6]}]: {pct:.0f}% — {msg}")

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
        self.player.load_video(file_path)
        self.thumb_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        self.render_btn.setEnabled(True)

        self.project.load_video(file_path, {})
        # Check if sidecar exists
        if self.project.load_sidecar() and self.project.segments:
            self.set_caption_segments(self.project.segments)
            self.status.showMessage(f"Loaded sidecar with {len(self.project.segments)} captions.")
        else:
            starter_cues = [
                CaptionSegment(start_ms=0, end_ms=3000, text="Welcome to PyCapSlap ⚡"),
                CaptionSegment(start_ms=3500, end_ms=6500, text="Drag this caption vertically to position it"),
                CaptionSegment(start_ms=7000, end_ms=9500, text="High-performance native video captions"),
            ]
            self.set_caption_segments(starter_cues)
            self.status.showMessage("Loaded video with starter captions. Drag on video or click + Add to edit.", 4000)

        # Trigger initial position sync
        self._on_position_changed(0)

        self.meta_lbl.setText(
            f"File: {os.path.basename(file_path)}\n"
            f"Path: {file_path}\n"
            f"Size: {os.path.getsize(file_path) / (1024*1024):.1f} MB"
        )

    def trigger_extract_thumbnail(self) -> None:
        video_path = self.player.media_player.source().toLocalFile()
        if not video_path:
            return
        self.status.showMessage("Extracting thumbnail via Rust core...")

        fut = self.core.call("extractFirstFrame", {"videoPath": str(Path(video_path).resolve())})

        def on_done(f):
            try:
                res = f.result()
                data_uri = res.get("imageData", "")
                if "," in data_uri:
                    b64 = data_uri.split(",", 1)[1]
                    raw_bytes = base64.b64decode(b64)
                    qimg = QImage.fromData(raw_bytes)
                    pixmap = QPixmap.fromImage(qimg)
                    scaled = pixmap.scaled(
                        self.thumb_lbl.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    QTimer.singleShot(0, lambda: self.thumb_lbl.setPixmap(scaled))
                    QTimer.singleShot(0, lambda: self.status.showMessage("Thumbnail loaded.", 2000))
            except (RuntimeError, ValueError, OSError) as err:
                err_msg = str(err)
                QTimer.singleShot(0, lambda msg=err_msg: QMessageBox.warning(self, "Error", msg))

        fut.add_done_callback(on_done)

    def closeEvent(self, event) -> None:
        self.perf_timer.stop()
        self.core.close()
        super().closeEvent(event)
