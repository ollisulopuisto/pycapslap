from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models.captions import CaptionSegment


def format_timestamp(ms: int) -> str:
    total_sec = ms // 1000
    m = total_sec // 60
    s = total_sec % 60
    tenth = (ms % 1000) // 100
    return f"{m:02d}:{s:02d}.{tenth}"


class CaptionPanelWidget(QWidget):
    segment_selected = Signal(object)
    segment_updated = Signal(object)
    position_override_changed = Signal(object, float)
    auto_place_requested = Signal()
    save_requested = Signal()
    transcribe_requested = Signal()
    add_cue_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.segments: list[CaptionSegment] = []
        self.selected_segment: CaptionSegment | None = None
        self.active_anchor_pct: float = 80.0
        self._block_signals: bool = False

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Header with actions
        header_layout = QHBoxLayout()
        self.lbl_title = QLabel("Captions")
        self.lbl_title.setStyleSheet("font-weight: bold; font-size: 14px; color: #f4f4f5;")
        header_layout.addWidget(self.lbl_title)
        header_layout.addStretch()

        self.btn_add_cue = QPushButton("+ Add")
        self.btn_add_cue.setToolTip("Add a new caption cue at the current playback position")
        self.btn_add_cue.clicked.connect(self.add_cue_requested.emit)
        header_layout.addWidget(self.btn_add_cue)

        self.btn_transcribe = QPushButton("Transcribe")
        self.btn_transcribe.setToolTip("Run AI Whisper transcription on video audio")
        self.btn_transcribe.clicked.connect(self.transcribe_requested.emit)
        header_layout.addWidget(self.btn_transcribe)

        self.btn_autoplace = QPushButton("Auto Dodge")
        self.btn_autoplace.setToolTip("Analyze video frame activity and automatically dodge faces/busy areas")
        self.btn_autoplace.clicked.connect(self.auto_place_requested.emit)
        header_layout.addWidget(self.btn_autoplace)

        self.btn_save = QPushButton("Save")
        self.btn_save.setToolTip("Save captions to sidecar file (.capslap.json)")
        self.btn_save.clicked.connect(self.save_requested.emit)
        header_layout.addWidget(self.btn_save)

        layout.addLayout(header_layout)

        # Table of cues
        self.cue_table = QTableWidget(0, 3)
        self.cue_table.setHorizontalHeaderLabels(["Start", "End", "Text"])
        self.cue_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.cue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.cue_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.cue_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.cue_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.cue_table.verticalHeader().setVisible(False)
        self.cue_table.setStyleSheet("""
            QTableWidget {
                background-color: #18181b;
                gridline-color: #27272a;
                border: 1px solid #27272a;
                border-radius: 4px;
                color: #f4f4f5;
            }
            QTableWidget::item:selected {
                background-color: #312e81;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #27272a;
                color: #a1a1aa;
                padding: 4px;
                border: none;
                font-size: 11px;
            }
        """)
        self.cue_table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self.cue_table.itemChanged.connect(self._on_table_item_changed)
        layout.addWidget(self.cue_table, stretch=1)

        # Position inspector controls
        pos_container = QWidget()
        pos_container.setStyleSheet("background-color: #27272a; border-radius: 6px; padding: 6px;")
        pos_layout = QVBoxLayout(pos_container)
        pos_layout.setContentsMargins(8, 8, 8, 8)
        pos_layout.setSpacing(6)

        pos_header = QHBoxLayout()
        pos_lbl = QLabel("Caption Position (Y Anchor)")
        pos_lbl.setStyleSheet("font-weight: 600; font-size: 12px; color: #e4e4e7;")
        self.lbl_anchor_value = QLabel("80.0%")
        self.lbl_anchor_value.setStyleSheet("font-weight: bold; color: #818cf8;")
        pos_header.addWidget(pos_lbl)
        pos_header.addStretch()
        pos_header.addWidget(self.lbl_anchor_value)
        pos_layout.addLayout(pos_header)

        # Preset buttons: Top (15%), Middle (50%), Bottom (80%)
        presets_layout = QHBoxLayout()
        self.btn_top = QPushButton("Top (15%)")
        self.btn_top.clicked.connect(lambda: self.set_anchor_pct(15.0, user_action=True))
        presets_layout.addWidget(self.btn_top)

        self.btn_middle = QPushButton("Middle (50%)")
        self.btn_middle.clicked.connect(lambda: self.set_anchor_pct(50.0, user_action=True))
        presets_layout.addWidget(self.btn_middle)

        self.btn_bottom = QPushButton("Bottom (80%)")
        self.btn_bottom.clicked.connect(lambda: self.set_anchor_pct(80.0, user_action=True))
        presets_layout.addWidget(self.btn_bottom)
        pos_layout.addLayout(presets_layout)

        # Precision slider
        self.slider_anchor = QSlider(Qt.Orientation.Horizontal)
        self.slider_anchor.setRange(5, 95)
        self.slider_anchor.setValue(80)
        self.slider_anchor.valueChanged.connect(self._on_slider_changed)
        pos_layout.addWidget(self.slider_anchor)

        layout.addWidget(pos_container)

    def set_segments(self, segments: list[CaptionSegment]) -> None:
        self._block_signals = True
        self.segments = list(segments)
        self.cue_table.setRowCount(len(self.segments))

        for row, seg in enumerate(self.segments):
            item_start = QTableWidgetItem(format_timestamp(seg.start_ms))
            item_start.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

            item_end = QTableWidgetItem(format_timestamp(seg.end_ms))
            item_end.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

            item_text = QTableWidgetItem(seg.text)
            item_text.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable)

            self.cue_table.setItem(row, 0, item_start)
            self.cue_table.setItem(row, 1, item_end)
            self.cue_table.setItem(row, 2, item_text)

        self._block_signals = False

    def select_segment(self, segment: CaptionSegment | None, anchor_y_pct: float = 80.0) -> None:
        self.selected_segment = segment
        self.set_anchor_pct(anchor_y_pct, user_action=False)

        if not segment:
            self.cue_table.clearSelection()
            return

        for row, seg in enumerate(self.segments):
            if seg == segment:
                self._block_signals = True
                self.cue_table.selectRow(row)
                self._block_signals = False
                break

    def set_anchor_pct(self, pct: float, user_action: bool = False) -> None:
        self.active_anchor_pct = float(pct)
        self.lbl_anchor_value.setText(f"{self.active_anchor_pct:.1f}%")

        self.slider_anchor.blockSignals(True)
        self.slider_anchor.setValue(round(self.active_anchor_pct))
        self.slider_anchor.blockSignals(False)

        if user_action and self.selected_segment:
            self.position_override_changed.emit(self.selected_segment, self.active_anchor_pct)

    def _on_slider_changed(self, val: int) -> None:
        self.set_anchor_pct(float(val), user_action=True)

    def _on_table_selection_changed(self) -> None:
        if self._block_signals:
            return
        selected_rows = self.cue_table.selectionModel().selectedRows()
        if selected_rows:
            row = selected_rows[0].row()
            if 0 <= row < len(self.segments):
                seg = self.segments[row]
                self.selected_segment = seg
                self.segment_selected.emit(seg)

    def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
        if self._block_signals:
            return
        row = item.row()
        col = item.column()
        if 0 <= row < len(self.segments) and col == 2:
            seg = self.segments[row]
            seg.text = item.text()
            self.segment_updated.emit(seg)
