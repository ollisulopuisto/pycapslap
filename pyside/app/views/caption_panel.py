from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMenu,
    QPushButton,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.fonts import get_categorized_fonts, init_app_fonts
from app.models.captions import (
    STYLE_PRESETS,
    CaptionSegment,
    CaptionStyle,
    combine_separated_syllables,
    shift_word_to_next,
    shift_word_to_prev,
)
from app.services.preset_manager import PresetManager


def format_timestamp(ms: int) -> str:
    total_sec = ms // 1000
    m = total_sec // 60
    s = total_sec % 60
    tenth = (ms % 1000) // 100
    return f"{m:02d}:{s:02d}.{tenth}"


class CaptionPanelWidget(QWidget):
    segment_selected = Signal(object)
    segment_updated = Signal(object)
    segments_updated = Signal(object)
    position_override_changed = Signal(object, float)
    style_changed = Signal(object)
    auto_place_requested = Signal()
    save_requested = Signal()
    transcribe_requested = Signal()
    add_cue_requested = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        preset_manager: PresetManager | None = None,
    ):
        if isinstance(parent, PresetManager):
            preset_manager = parent
            parent = None
        super().__init__(parent)
        self.preset_manager = preset_manager or PresetManager()
        self.segments: list[CaptionSegment] = []
        self.selected_segment: CaptionSegment | None = None
        self.active_anchor_pct: float = 80.0
        self.current_style: CaptionStyle = (
            self.preset_manager.get_default_style() or CaptionStyle()
        )
        self._block_signals: bool = False

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Header with actions
        header_layout = QHBoxLayout()
        self.lbl_title = QLabel("Captions")
        self.lbl_title.setStyleSheet(
            "font-weight: bold; font-size: 14px; color: #f4f4f5;"
        )
        header_layout.addWidget(self.lbl_title)
        header_layout.addStretch()

        self.btn_add_cue = QPushButton("+ Add")
        self.btn_add_cue.setToolTip(
            "Add a new caption cue at the current playback position"
        )
        self.btn_add_cue.clicked.connect(self.add_cue_requested.emit)
        header_layout.addWidget(self.btn_add_cue)

        self.btn_transcribe = QPushButton("Transcribe")
        self.btn_transcribe.setToolTip("Run AI Whisper transcription on video audio")
        self.btn_transcribe.clicked.connect(self.transcribe_requested.emit)
        header_layout.addWidget(self.btn_transcribe)

        self.btn_autoplace = QPushButton("Auto Dodge")
        self.btn_autoplace.setToolTip(
            "Analyze video frame activity and automatically dodge faces/busy areas"
        )
        self.btn_autoplace.clicked.connect(self.auto_place_requested.emit)
        header_layout.addWidget(self.btn_autoplace)

        self.btn_combine_syllables = QPushButton("Fix Syllables")
        self.btn_combine_syllables.setToolTip(
            "Combine separated syllables and fix broken words across segments"
        )
        self.btn_combine_syllables.clicked.connect(self._on_combine_syllables_clicked)
        header_layout.addWidget(self.btn_combine_syllables)

        self.btn_save = QPushButton("Save")
        self.btn_save.setToolTip("Save captions to sidecar file (.capslap.json)")
        self.btn_save.clicked.connect(self.save_requested.emit)
        header_layout.addWidget(self.btn_save)

        layout.addLayout(header_layout)

        # Table of cues
        self.cue_table = QTableWidget(0, 3)
        self.cue_table.setHorizontalHeaderLabels(["Start", "End", "Text"])
        self.cue_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.cue_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.cue_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.cue_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
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

        # Row for word-level shifting
        row_shift = QHBoxLayout()
        row_shift.setSpacing(6)
        lbl_shift = QLabel("Adjust words:")
        lbl_shift.setStyleSheet("font-size: 11px; color: #a1a1aa;")
        row_shift.addWidget(lbl_shift)

        self.btn_shift_prev = QPushButton("◀ Shift Start")
        self.btn_shift_prev.setToolTip(
            "Move first word of selected segment to previous segment"
        )
        self.btn_shift_prev.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 2px 8px; }"
        )
        self.btn_shift_prev.clicked.connect(self._on_shift_prev_clicked)
        row_shift.addWidget(self.btn_shift_prev)

        self.btn_shift_next = QPushButton("Shift End ▶")
        self.btn_shift_next.setToolTip(
            "Move last word of selected segment to next segment"
        )
        self.btn_shift_next.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 2px 8px; }"
        )
        self.btn_shift_next.clicked.connect(self._on_shift_next_clicked)
        row_shift.addWidget(self.btn_shift_next)
        row_shift.addStretch()
        layout.addLayout(row_shift)

        # Compact Position controls
        pos_container = QWidget()
        pos_container.setStyleSheet("background-color: #27272a; border-radius: 6px;")
        pos_layout = QVBoxLayout(pos_container)
        pos_layout.setContentsMargins(8, 6, 8, 6)
        pos_layout.setSpacing(4)

        pos_header = QHBoxLayout()
        pos_header.setSpacing(6)
        pos_lbl = QLabel("Position:")
        pos_lbl.setStyleSheet("font-weight: 600; font-size: 11px; color: #a1a1aa;")
        pos_header.addWidget(pos_lbl)

        btn_style = (
            "QPushButton { font-size: 11px; padding: 2px 6px; border-radius: 3px; "
            "background-color: #3f3f46; color: #f4f4f5; } "
            "QPushButton:hover { background-color: #52525b; }"
        )
        self.btn_top = QPushButton("Top (15%)")
        self.btn_top.setStyleSheet(btn_style)
        self.btn_top.setFixedHeight(22)
        self.btn_top.clicked.connect(
            lambda: self.set_anchor_pct(15.0, user_action=True)
        )
        pos_header.addWidget(self.btn_top)

        self.btn_middle = QPushButton("Mid (50%)")
        self.btn_middle.setStyleSheet(btn_style)
        self.btn_middle.setFixedHeight(22)
        self.btn_middle.clicked.connect(
            lambda: self.set_anchor_pct(50.0, user_action=True)
        )
        pos_header.addWidget(self.btn_middle)

        self.btn_bottom = QPushButton("Bot (80%)")
        self.btn_bottom.setStyleSheet(btn_style)
        self.btn_bottom.setFixedHeight(22)
        self.btn_bottom.clicked.connect(
            lambda: self.set_anchor_pct(80.0, user_action=True)
        )
        pos_header.addWidget(self.btn_bottom)

        pos_header.addStretch()

        self.lbl_anchor_value = QLabel("80.0%")
        self.lbl_anchor_value.setStyleSheet(
            "font-weight: bold; font-size: 11px; color: #818cf8;"
        )
        pos_header.addWidget(self.lbl_anchor_value)
        pos_layout.addLayout(pos_header)

        # Precision slider
        self.slider_anchor = QSlider(Qt.Orientation.Horizontal)
        self.slider_anchor.setRange(5, 95)
        self.slider_anchor.setValue(80)
        self.slider_anchor.setFixedHeight(18)
        self.slider_anchor.valueChanged.connect(self._on_slider_changed)
        pos_layout.addWidget(self.slider_anchor)

        layout.addWidget(pos_container)

        # Collapsible Style & Typography section
        style_container = QWidget()
        style_container.setStyleSheet(
            "background-color: #27272a; border-radius: 6px; padding: 4px;"
        )
        style_layout = QVBoxLayout(style_container)
        style_layout.setContentsMargins(6, 4, 6, 6)
        style_layout.setSpacing(4)

        self.btn_toggle_style = QPushButton("▶ Style & Typography")
        self.btn_toggle_style.setCheckable(True)
        self.btn_toggle_style.setChecked(False)
        self.btn_toggle_style.setStyleSheet("""
            QPushButton {
                text-align: left;
                font-weight: 600;
                font-size: 12px;
                color: #e4e4e7;
                background: transparent;
                border: none;
                padding: 4px;
            }
            QPushButton:hover {
                color: #ffffff;
            }
        """)
        style_layout.addWidget(self.btn_toggle_style)

        self.style_content = QWidget()
        content_layout = QVBoxLayout(self.style_content)
        content_layout.setContentsMargins(2, 4, 2, 2)
        content_layout.setSpacing(6)

        # Template preset dropdown and Save Preset button
        row_preset = QHBoxLayout()
        row_preset.addWidget(QLabel("Preset:"))
        self.combo_template = QComboBox()
        self.combo_template.currentIndexChanged.connect(self._on_template_changed)
        row_preset.addWidget(self.combo_template, stretch=1)

        self.btn_save_preset = QPushButton("Save Preset...")
        self.btn_save_preset.setToolTip(
            "Save current style preference (font, color, size, etc.) for this show"
        )
        self.btn_save_preset.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 2px 8px; }"
        )
        self.btn_save_preset.clicked.connect(self._on_save_preset_clicked)
        row_preset.addWidget(self.btn_save_preset)

        self.btn_delete_preset = QPushButton("✕")
        self.btn_delete_preset.setToolTip("Delete selected custom preset")
        self.btn_delete_preset.setFixedWidth(24)
        self.btn_delete_preset.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 2px 4px; }"
        )
        self.btn_delete_preset.clicked.connect(self._on_delete_preset_clicked)
        row_preset.addWidget(self.btn_delete_preset)

        content_layout.addLayout(row_preset)
        self._rebuild_template_combo()

        # Hierarchical Font family dropdown menu
        row_font = QHBoxLayout()
        row_font.addWidget(QLabel("Font:"))

        self.btn_font = QPushButton(f"Font: {self.current_style.font_name} ▾")
        self.btn_font.setStyleSheet(
            "QPushButton { text-align: left; padding: 3px 8px; font-size: 11px; }"
        )
        self.font_menu = QMenu(self)
        self._rebuild_font_menu()
        self.btn_font.setMenu(self.font_menu)
        row_font.addWidget(self.btn_font, stretch=1)

        # Retain combo_font for backward compatibility with existing tests
        self.combo_font = QComboBox()
        self.combo_font.setVisible(False)
        avail_fonts = init_app_fonts()
        for f in avail_fonts or ["Montserrat", "Komika Axis", "Roboto"]:
            self.combo_font.addItem(f, f)
        self.combo_font.currentIndexChanged.connect(self._on_style_field_changed)
        row_font.addWidget(self.combo_font)
        content_layout.addLayout(row_font)

        # Font size slider
        row_size = QHBoxLayout()
        row_size.addWidget(QLabel("Size:"))
        self.lbl_font_size = QLabel(f"{self.current_style.font_size} px")
        self.slider_font_size = QSlider(Qt.Orientation.Horizontal)
        self.slider_font_size.setRange(24, 96)
        self.slider_font_size.setValue(self.current_style.font_size)
        self.slider_font_size.valueChanged.connect(self._on_font_size_changed)
        row_size.addWidget(self.slider_font_size, stretch=1)
        row_size.addWidget(self.lbl_font_size)
        content_layout.addLayout(row_size)

        # Color controls row
        row_colors = QHBoxLayout()
        self.btn_text_color = QPushButton("Text")
        self.btn_text_color.clicked.connect(lambda: self._pick_color("text"))
        row_colors.addWidget(self.btn_text_color)

        self.btn_hi_color = QPushButton("Highlight")
        self.btn_hi_color.clicked.connect(lambda: self._pick_color("highlight"))
        row_colors.addWidget(self.btn_hi_color)

        self.chk_karaoke = QCheckBox("Karaoke")
        self.chk_karaoke.setChecked(self.current_style.karaoke)
        self.chk_karaoke.toggled.connect(self._on_karaoke_toggled)
        row_colors.addWidget(self.chk_karaoke)
        content_layout.addLayout(row_colors)

        # Initially collapsed
        self.style_content.setVisible(False)

        def _on_style_toggle(checked: bool) -> None:
            self.style_content.setVisible(checked)
            self.btn_toggle_style.setText(
                "▼ Style & Typography" if checked else "▶ Style & Typography"
            )

        self.btn_toggle_style.toggled.connect(_on_style_toggle)

        style_layout.addWidget(self.style_content)
        self._update_color_buttons()
        layout.addWidget(style_container)

    def _update_color_buttons(self) -> None:
        tc = self.current_style.text_color
        self.btn_text_color.setStyleSheet(
            f"background-color: {tc}; color: {'#000000' if tc.lower() in ('#ffffff', '#ffff00', '#eaeaea') else '#ffffff'}; font-weight: bold; border-radius: 4px;"
        )
        hc = self.current_style.highlight_color
        self.btn_hi_color.setStyleSheet(
            f"background-color: {hc}; color: {'#000000' if hc.lower() in ('#ffffff', '#ffff00', '#7ef1c5', '#00f924') else '#ffffff'}; font-weight: bold; border-radius: 4px;"
        )

    def _rebuild_template_combo(self) -> None:
        prev_data = self.combo_template.currentData()
        self.combo_template.blockSignals(True)
        self.combo_template.clear()

        self.combo_template.addItem("Oneliner (Modern Yellow)", "oneliner")
        self.combo_template.addItem("Karaoke (Neon Green)", "karaoke")
        self.combo_template.addItem("Vibrant (Mint / Teal)", "vibrant")
        self.combo_template.addItem("Storyteller (Warm Amber)", "storyteller")

        custom_presets = self.preset_manager.list_presets()
        if custom_presets:
            self.combo_template.insertSeparator(self.combo_template.count())
            for name in custom_presets:
                self.combo_template.addItem(f"★ {name}", name)

        self.combo_template.addItem("Custom", "custom")

        if prev_data:
            idx = self.combo_template.findData(prev_data)
            if idx >= 0:
                self.combo_template.setCurrentIndex(idx)
        self.combo_template.blockSignals(False)

    def _rebuild_font_menu(self) -> None:
        self.font_menu.clear()
        categorized = get_categorized_fonts()
        for cat_name, fonts in categorized.items():
            if not fonts:
                continue
            sub_menu = self.font_menu.addMenu(cat_name)
            for f in fonts:
                act = sub_menu.addAction(f)
                act.triggered.connect(
                    lambda checked=False, fname=f: self.set_font_name(fname)
                )

    def set_font_name(self, font_name: str) -> None:
        self.current_style.font_name = font_name
        if hasattr(self, "btn_font"):
            self.btn_font.setText(f"Font: {font_name} ▾")
        if hasattr(self, "combo_font"):
            for i in range(self.combo_font.count()):
                item_txt = self.combo_font.itemText(i)
                if (
                    font_name.lower() in item_txt.lower()
                    or item_txt.lower() in font_name.lower()
                ):
                    self.combo_font.setCurrentIndex(i)
                    break
        self.style_changed.emit(self.current_style)

    def _on_template_changed(self, _idx: int) -> None:
        tpl_id = self.combo_template.currentData()
        if not tpl_id or tpl_id == "custom":
            return
        if tpl_id in STYLE_PRESETS:
            preset = STYLE_PRESETS[tpl_id]
            self.set_style(preset)
        else:
            custom_preset = self.preset_manager.get_preset(tpl_id)
            if custom_preset:
                self.set_style(custom_preset)

    def _on_save_preset_clicked(self) -> None:
        name, ok = QInputDialog.getText(
            self,
            "Save Style Preset",
            "Enter a preset name for this show (e.g. show title):",
            text="My Show Style",
        )
        if ok and name and name.strip():
            preset_name = name.strip()
            self.preset_manager.save_preset(preset_name, self.current_style)
            self.preset_manager.save_default_style(self.current_style)
            self._rebuild_template_combo()
            idx = self.combo_template.findData(preset_name)
            if idx >= 0:
                self.combo_template.setCurrentIndex(idx)

    def _on_delete_preset_clicked(self) -> None:
        tpl_id = self.combo_template.currentData()
        if (
            tpl_id
            and tpl_id not in STYLE_PRESETS
            and tpl_id != "custom"
            and not tpl_id.startswith("__")
        ):
            self.preset_manager.delete_preset(tpl_id)
            self._rebuild_template_combo()

    def _on_style_field_changed(self) -> None:
        font_val = self.combo_font.currentData() or self.combo_font.currentText()
        if font_val:
            self.current_style.font_name = font_val
            if hasattr(self, "btn_font"):
                self.btn_font.setText(f"Font: {font_val} ▾")
        self.style_changed.emit(self.current_style)

    def _on_font_size_changed(self, val: int) -> None:
        self.current_style.font_size = val
        self.lbl_font_size.setText(f"{val} px")
        self.style_changed.emit(self.current_style)

    def _on_karaoke_toggled(self, checked: bool) -> None:
        self.current_style.karaoke = checked
        self.style_changed.emit(self.current_style)

    def _pick_color(self, target: str) -> None:
        current_hex = (
            self.current_style.text_color
            if target == "text"
            else self.current_style.highlight_color
        )
        chosen = QColorDialog.getColor(
            QColor(current_hex), self, f"Pick {target.title()} Color"
        )
        if chosen.isValid():
            hex_val = chosen.name()
            if target == "text":
                self.current_style.text_color = hex_val
            else:
                self.current_style.highlight_color = hex_val
            self._update_color_buttons()
            self.style_changed.emit(self.current_style)

    def get_current_style(self) -> CaptionStyle:
        return self.current_style

    def set_style(self, style: CaptionStyle) -> None:
        self.current_style = style
        self._block_signals = True

        idx = self.combo_template.findData(style.template_id)
        if idx >= 0:
            self.combo_template.setCurrentIndex(idx)
        else:
            self.combo_template.setCurrentIndex(self.combo_template.findData("custom"))

        if hasattr(self, "btn_font"):
            self.btn_font.setText(f"Font: {style.font_name} ▾")

        # Find matching font in combo_font
        for i in range(self.combo_font.count()):
            family = self.combo_font.itemText(i)
            if (
                family.lower() in style.font_name.lower()
                or style.font_name.lower() in family.lower()
            ):
                self.combo_font.setCurrentIndex(i)
                break

        self.slider_font_size.setValue(style.font_size)
        self.lbl_font_size.setText(f"{style.font_size} px")
        self.chk_karaoke.setChecked(style.karaoke)
        self._update_color_buttons()

        self._block_signals = False
        self.style_changed.emit(self.current_style)

    def _on_combine_syllables_clicked(self) -> None:
        self.commit_active_editor()
        self.segments = combine_separated_syllables(self.segments)
        self.set_segments(self.segments)
        self.segments_updated.emit(self.segments)

    def _on_shift_prev_clicked(self) -> None:
        row = self.cue_table.currentRow()
        if row > 0:
            self.commit_active_editor()
            shift_word_to_prev(self.segments, row)
            self.set_segments(self.segments)
            self.cue_table.selectRow(row)
            self.segments_updated.emit(self.segments)

    def _on_shift_next_clicked(self) -> None:
        row = self.cue_table.currentRow()
        if 0 <= row < len(self.segments) - 1:
            self.commit_active_editor()
            shift_word_to_next(self.segments, row)
            self.set_segments(self.segments)
            self.cue_table.selectRow(row)
            self.segments_updated.emit(self.segments)

    def set_segments(self, segments: list[CaptionSegment]) -> None:
        self._block_signals = True
        self.segments = list(segments)
        self.cue_table.setRowCount(len(self.segments))

        for row, seg in enumerate(self.segments):
            item_start = QTableWidgetItem(format_timestamp(seg.start_ms))
            item_start.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            )

            item_end = QTableWidgetItem(format_timestamp(seg.end_ms))
            item_end.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

            item_text = QTableWidgetItem(seg.text)
            item_text.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsEditable
            )

            self.cue_table.setItem(row, 0, item_start)
            self.cue_table.setItem(row, 1, item_end)
            self.cue_table.setItem(row, 2, item_text)

        self._block_signals = False

    def select_segment(
        self, segment: CaptionSegment | None, anchor_y_pct: float = 80.0
    ) -> None:
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
            self.position_override_changed.emit(
                self.selected_segment, self.active_anchor_pct
            )

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

    def commit_active_editor(self) -> None:
        self.cue_table.setCurrentItem(None)

    def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
        if self._block_signals:
            return
        row = item.row()
        col = item.column()
        if 0 <= row < len(self.segments) and col == 2:
            seg = self.segments[row]
            seg.update_text(item.text())
            self.segment_updated.emit(seg)
