import base64
import os
from pathlib import Path

import psutil
from PySide6.QtCore import QSize, Qt, QTimer
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
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
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
from app.views.caption_panel import CaptionPanelWidget
from app.views.settings_dialog import WhisperSettingsDialog, get_transcription_params
from app.views.timeline import VisualTimelineWidget
from app.views.video_canvas import SAFE_PLATFORMS
from app.views.video_player import VideoPlayerWidget


class MainWindow(QMainWindow):
    def __init__(
        self, core_client: CoreClient | None = None, parent: QWidget | None = None
    ):
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
        self.save_btn.setToolTip(
            "Save captions to sidecar file (.capslap.json) [Cmd+S / Ctrl+S]"
        )
        self.save_btn.clicked.connect(self._on_save_requested)
        self.save_btn.setEnabled(False)
        action_bar.addWidget(self.save_btn)

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
        self.player.duration_changed.connect(self.timeline.set_duration)

        # Timeline signals
        self.timeline.seek_requested.connect(self.player.seek_to_ms)
        self.timeline.segment_selected.connect(self._on_segment_selected)

        # Overlay signals
        self.overlay.anchor_changed.connect(self._on_overlay_anchor_changed)

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

    def _on_style_changed(self, style: CaptionStyle) -> None:
        self.project.style = style
        self.project.is_dirty = True
        self.player.canvas.set_style(style)

    def _on_position_changed(self, pos_ms: int) -> None:
        self.timeline.set_position(pos_ms)
        active = self.project.get_active_segment(pos_ms)
        if active:
            anchor_y = self.project.get_anchor_y_for_segment(active)
            self.overlay.set_segment(active, anchor_y, current_pos_ms=pos_ms)
        else:
            self.overlay.set_segment(None, current_pos_ms=pos_ms)

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

    def _on_panel_override_changed(
        self, seg: CaptionSegment, anchor_pct: float
    ) -> None:
        self.project.set_segment_position_override(seg, anchor_pct)
        if self.overlay.current_segment == seg:
            self.overlay.set_segment(seg, anchor_pct)

    def _on_apply_position_to_all_requested(self, anchor_pct: float) -> None:
        self.project.apply_position_to_all(anchor_pct)
        pos_ms = self.player.media_player.position()
        self._on_position_changed(pos_ms)
        self.status.showMessage(
            f"Applied {anchor_pct:.1f}% vertical position to all captions.", 3000
        )

    def _on_segment_text_updated(self, seg: CaptionSegment) -> None:
        self.project.is_dirty = True
        self.timeline.update()
        if self.overlay.current_segment == seg:
            pos_ms = self.player.media_player.position()
            anchor_y = self.project.get_anchor_y_for_segment(seg)
            self.overlay.set_segment(seg, anchor_y, current_pos_ms=pos_ms)

    def _on_segments_updated(self, segments: list[CaptionSegment]) -> None:
        self.project.segments = list(segments)
        self.project.is_dirty = True
        self.timeline.set_segments(self.project.segments)
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

    def _is_portrait_video(self) -> bool:
        """Whether the loaded source is taller than it is wide.

        `project.video.width/height` are never actually populated (`load_video`
        is always called with an empty probe dict), so this reads real pixel
        dimensions from the canvas instead — the decoded video frame, or the
        extracted thumbnail as a fallback while the first frame hasn't
        arrived yet. Both carry the video's true size regardless of how the
        canvas widget itself is currently laid out.
        """
        size = self.player.canvas.get_video_size()
        if size:
            width, height = size
            return height > width
        return bool(
            self.project.video
            and self.project.video.width > 0
            and self.project.video.height > self.project.video.width
        )

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

        # Choose export aspect ratio format
        default_fmt = "9:16" if self._is_portrait_video() else "16:9"

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
            "exportFormats": [export_fmt],
            "karaoke": self.project.style.karaoke,
            "multiline": self.project.style.multiline,
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
                QTimer.singleShot(0, self, lambda: self.render_btn.setEnabled(True))
                QTimer.singleShot(
                    0, self, lambda: self.render_btn.setText("Render Video")
                )
                QTimer.singleShot(0, self, lambda: self.progress_bar.setVisible(False))
                QTimer.singleShot(
                    0,
                    self,
                    lambda: self.status.showMessage(
                        f"Render complete: {output_path}", 8000
                    ),
                )
            except (RuntimeError, ValueError, OSError) as err:
                err_msg = str(err)
                QTimer.singleShot(0, self, lambda: self.render_btn.setEnabled(True))
                QTimer.singleShot(
                    0, self, lambda: self.render_btn.setText("Render Video")
                )
                QTimer.singleShot(0, self, lambda: self.progress_bar.setVisible(False))
                QTimer.singleShot(
                    0,
                    self,
                    lambda msg=err_msg: QMessageBox.warning(self, "Render Error", msg),
                )

        fut.add_done_callback(on_done)

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

        export_fmt = "9:16" if self._is_portrait_video() else "16:9"

        self.status.showMessage("Running automatic caption placement via Rust core...")
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)

        params = {
            "inputVideo": str(Path(source_file).resolve()),
            "segments": [s.to_dict() for s in self.project.segments],
            "exportFormat": export_fmt,
            "karaoke": self.project.style.karaoke,
            "multiline": self.project.style.multiline,
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
                QTimer.singleShot(0, self, lambda: self.progress_bar.setVisible(False))
                QTimer.singleShot(
                    0,
                    self,
                    lambda: self.status.showMessage(
                        f"Auto Dodge complete: moved {moved} captions.", 4000
                    ),
                )
                QTimer.singleShot(0, self, self.overlay.update)
            except (RuntimeError, ValueError, OSError) as err:
                err_msg = str(err)
                QTimer.singleShot(0, self, lambda: self.progress_bar.setVisible(False))
                QTimer.singleShot(
                    0,
                    self,
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

        export_fmt = "9:16" if self._is_portrait_video() else "16:9"

        params = {
            "inputVideo": str(Path(source_file).resolve()),
            "exportFormats": [export_fmt],
            "karaoke": self.project.style.karaoke,
            # Word-per-cue only for karaoke bounce; otherwise keep whisper's
            # own phrase/sentence segments (with per-word timing nested in
            # each segment's `words`, still available for highlighting).
            "splitByWords": self.project.style.karaoke,
            "language": None,
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
                QTimer.singleShot(0, self, lambda: self.progress_bar.setVisible(False))
                QTimer.singleShot(0, self, lambda: self.set_caption_segments(new_segs))
                QTimer.singleShot(
                    0,
                    self,
                    lambda: self.status.showMessage(
                        f"Transcription finished: {len(new_segs)} segments.", 4000
                    ),
                )
            except (RuntimeError, ValueError, OSError) as err:
                err_msg = str(err)
                QTimer.singleShot(0, self, lambda: self.progress_bar.setVisible(False))
                QTimer.singleShot(
                    0,
                    self,
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
        self.player.load_video(file_path)
        self.thumb_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
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

                    QTimer.singleShot(0, self, update_ui)
                else:

                    def reset_no_img():
                        self.thumb_btn.setEnabled(True)
                        self.thumb_btn.setText("Extract Thumbnail")
                        self.progress_bar.setRange(0, 100)
                        self.progress_bar.setVisible(False)

                    QTimer.singleShot(0, self, reset_no_img)
            except (RuntimeError, ValueError, OSError) as err:
                err_msg = str(err)

                def reset_err(msg=err_msg):
                    self.thumb_btn.setEnabled(True)
                    self.thumb_btn.setText("Extract Thumbnail")
                    self.progress_bar.setRange(0, 100)
                    self.progress_bar.setVisible(False)
                    QMessageBox.warning(self, "Error", msg)

                QTimer.singleShot(0, self, reset_err)

        fut.add_done_callback(on_done)

    def closeEvent(self, event) -> None:
        self.perf_timer.stop()
        self.core.close()
        super().closeEvent(event)
