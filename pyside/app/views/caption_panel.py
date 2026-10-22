from dataclasses import replace

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractItemDelegate,
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStyledItemDelegate,
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
    apply_orphan_rules,
    chars_per_second,
    clamped_segment_time,
    combine_separated_syllables,
    delete_segment,
    group_words_into_phrases,
    set_segment_time,
    shift_word_to_next,
    shift_word_to_prev,
    split_segment,
    timing_flag,
)
from app.services.preset_manager import PresetManager
from app.services.spellcheck import get_shared_checker
from app.views.tile_buttons import SMALL_QSS, tile
from app.views.wrapped_text import WrappedText

SPELL_ERROR_COLOR = "#f87171"


NUDGE_MS = 100

COL_START, COL_END, COL_DURATION, COL_TEXT = range(4)
FLAG_COLORS = {"short": "#f87171", "long": "#fbbf24"}
TIMING_NOTES = {
    "short": "too fast for its text: lengthen the cue or shorten the text",
    "long": "too slow for its text: it lingers on the screen",
}


def format_timestamp(ms: int) -> str:
    """mm:ss.mmm, to the millisecond, so a cue shows the exact time it was set to."""
    total_sec = ms // 1000
    m = total_sec // 60
    s = total_sec % 60
    return f"{m:02d}:{s:02d}.{ms % 1000:03d}"


def parse_timestamp(text: str) -> int | None:
    """Parse the timecodes the table shows, plus the shorthands people type.

    Accepts "mm:ss.t", "h:mm:ss.t", "ss.t" and a bare seconds count; returns
    milliseconds, or None when the text is not a time at all.
    """
    text = text.strip().replace(",", ".")
    if not text:
        return None
    parts = text.split(":")
    if len(parts) > 3:
        return None
    try:
        seconds = float(parts[-1])
        minutes = int(parts[-2]) if len(parts) >= 2 else 0
        hours = int(parts[-3]) if len(parts) == 3 else 0
    except ValueError:
        return None
    if seconds < 0 or minutes < 0 or hours < 0:
        return None
    return int(round((hours * 3600 + minutes * 60 + seconds) * 1000))


class SpellCheckDelegate(QStyledItemDelegate):
    """Draws the normal cell, then squiggles under words Voikko rejects."""

    def __init__(self, panel: "CaptionPanelWidget") -> None:
        super().__init__(panel)
        self.panel = panel

    def paint(self, painter, option, index) -> None:  # type: ignore[override]
        super().paint(painter, option, index)
        if index.column() != COL_TEXT:
            return
        spans = self.panel.spell_spans_for_row(index.row())
        if not spans:
            return

        opt = option
        self.initStyleOption(opt, index)
        text = index.data() or ""
        # Mirror the 4px text inset QCommonStyle uses for item text.
        rect = opt.rect.adjusted(4, 0, -4, 0)
        wrapped = WrappedText(text, opt.font, rect.width())
        top = rect.top() + (rect.height() - wrapped.height) / 2

        painter.save()
        pen = QPen(QColor(SPELL_ERROR_COLOR))
        pen.setWidthF(1.4)
        painter.setPen(pen)
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        for start, end, _word in spans:
            for x1, x2, baseline in wrapped.underlines(start, end):
                if x1 >= rect.width():
                    continue
                x2 = min(x2, rect.width())
                painter.drawPath(
                    _squiggle(rect.left() + x1, rect.left() + x2, top + baseline + 3)
                )
        painter.restore()


def _squiggle(x1: float, x2: float, y: float) -> QPainterPath:
    """A small zigzag, the way every spell checker has drawn one since 1995."""
    path = QPainterPath()
    path.moveTo(x1, y)
    period = 4.0
    up = True
    x = x1
    while x < x2:
        x = min(x + period / 2, x2)
        path.lineTo(x, y - 2.0 if up else y)
        up = not up
    return path


class CaptionPanelWidget(QWidget):
    segment_selected = Signal(object)
    segment_updated = Signal(object)
    segments_updated = Signal(object)
    position_override_changed = Signal(object, float)
    apply_position_to_all_requested = Signal(float)
    style_changed = Signal(object)
    auto_place_requested = Signal()
    save_requested = Signal()
    transcribe_requested = Signal()
    whisper_settings_requested = Signal()
    add_cue_requested = Signal()
    mark_start_requested = Signal()
    mark_end_requested = Signal()
    safe_platforms_changed = Signal(object)

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
        self.playhead_segment: CaptionSegment | None = None
        self.active_safe_platforms: set[str] = {"tiktok", "reels", "shorts"}
        self.active_anchor_pct: float = 75.0
        self.current_style: CaptionStyle = (
            self.preset_manager.get_default_style() or CaptionStyle()
        )
        self._block_signals: bool = False
        self.spell_checker = get_shared_checker()
        self._spell_cache: dict[int, list[tuple[int, int, str]]] = {}
        # id(segment) -> row, so the playhead can find its cue without a scan
        # of the whole transcript on every position tick.
        self._row_of: dict[int, int] = {}

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)

        # Header with actions
        header_layout = QGridLayout()
        header_layout.setSpacing(4)
        self.header_layout = header_layout
        self.lbl_title = QLabel("Captions")
        self.lbl_title.setStyleSheet(
            "font-weight: bold; font-size: 14px; color: #f4f4f5;"
        )
        header_layout.addWidget(self.lbl_title, 0, 0, 1, 3)

        self.btn_add_cue = tile("Add", "plus", compact=True)
        self.btn_add_cue.setToolTip(
            "Add a new caption cue at the current playback position"
        )
        self.btn_add_cue.clicked.connect(self.add_cue_requested.emit)
        header_layout.addWidget(self.btn_add_cue, 1, 0)

        self.btn_transcribe = tile("Transcribe", "mic", compact=True)
        self.btn_transcribe.setToolTip("Run AI Whisper transcription on video audio")
        self.btn_transcribe.clicked.connect(self.transcribe_requested.emit)
        header_layout.addWidget(self.btn_transcribe, 1, 1)

        self.btn_whisper_settings = tile("Whisper", "gear", compact=True)
        self.btn_whisper_settings.setToolTip(
            "Choose local (offline) Whisper vs. OpenAI API, and manage models"
        )
        self.btn_whisper_settings.clicked.connect(self.whisper_settings_requested.emit)
        header_layout.addWidget(self.btn_whisper_settings, 3, 1)

        self.btn_autoplace = tile("Auto Dodge", "wand", compact=True)
        self.btn_autoplace.setToolTip(
            "Analyze video frame activity and automatically dodge faces/busy areas"
        )
        self.btn_autoplace.clicked.connect(self.auto_place_requested.emit)
        header_layout.addWidget(self.btn_autoplace, 2, 0)

        self.btn_combine_syllables = tile("Fix Syllables", "text", compact=True)
        self.btn_combine_syllables.setToolTip(
            "Combine separated syllables and fix broken words across segments"
        )
        self.btn_combine_syllables.clicked.connect(self._on_combine_syllables_clicked)
        header_layout.addWidget(self.btn_combine_syllables, 2, 1)

        self.btn_group_words = tile("Group Words", "grid", compact=True)
        self.btn_group_words.setToolTip(
            "Merge a word-per-cue transcript into phrase-sized cues, breaking "
            "on sentence ends, pauses and length — what you need when every "
            "caption holds a single word"
        )
        self.btn_group_words.clicked.connect(self._on_group_words_clicked)
        header_layout.addWidget(self.btn_group_words, 2, 2)

        self.btn_fix_orphans = tile("Fix Orphans", "align", compact=True)
        self.btn_fix_orphans.setToolTip(
            "Prevent trailing conjunctions ('tai', 'ja') and lone words after commas"
        )
        self.btn_fix_orphans.clicked.connect(self._on_fix_orphans_clicked)
        header_layout.addWidget(self.btn_fix_orphans, 3, 0)

        self.btn_save = tile("Save", "save", compact=True)
        self.btn_save.setToolTip("Save captions to sidecar file (.capslap.json)")
        self.btn_save.clicked.connect(self.save_requested.emit)
        header_layout.addWidget(self.btn_save, 1, 2)

        # Three equal columns: every button in a row lines up with the one above.
        for column in range(3):
            header_layout.setColumnStretch(column, 1)
        for button in (
            self.btn_add_cue,
            self.btn_transcribe,
            self.btn_autoplace,
            self.btn_combine_syllables,
            self.btn_group_words,
            self.btn_fix_orphans,
            self.btn_save,
        ):
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addLayout(header_layout)

        # Table of cues
        self.cue_table = QTableWidget(0, 4)
        self.cue_table.setHorizontalHeaderLabels(["Start", "End", "Duration", "Text"])
        for column in (COL_START, COL_END, COL_DURATION):
            self.cue_table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        self.cue_table.horizontalHeader().setSectionResizeMode(
            COL_TEXT, QHeaderView.ResizeMode.Stretch
        )
        self.cue_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.cue_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # Long captions wrap onto more lines instead of running off the column.
        # The rows are sized to their text by hand (_fit_rows) rather than by
        # ResizeToContents: in that mode Qt re-measures every row of the table
        # on every cell change, which with a long transcript turns one edit —
        # five cell writes per row — into seconds of text layout.
        self.cue_table.setWordWrap(True)
        self.cue_table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Fixed
        )
        self.cue_table.horizontalHeader().sectionResized.connect(
            lambda *_args: self.cue_table.resizeRowsToContents()
        )
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
        self.cue_table.setItemDelegateForColumn(COL_TEXT, SpellCheckDelegate(self))
        self.cue_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.cue_table.customContextMenuRequested.connect(self._on_table_context_menu)
        self.cue_table.setToolTip(
            "Start and End are editable (mm:ss.t).\n"
            f"Alt+←/→ nudges the start by {NUDGE_MS} ms, Alt+Shift+←/→ the end, "
            "Alt+Ctrl+←/→ the whole cue.\n"
            "Right-click a word in the text to split the caption before it."
        )
        self.cue_table.installEventFilter(self)
        layout.addWidget(self.cue_table, stretch=1)

        # Row for word-level shifting
        row_shift = QGridLayout()
        row_shift.setSpacing(4)
        lbl_shift = QLabel("Adjust words:")
        lbl_shift.setStyleSheet("font-size: 11px; color: #a1a1aa;")
        row_shift.addWidget(lbl_shift, 0, 0, 1, 3)

        self.btn_mark_start = QPushButton("In")
        self.btn_mark_start.setToolTip(
            "Set the active caption's start to the playback position"
        )
        self.btn_mark_start.setStyleSheet(SMALL_QSS)
        self.btn_mark_start.clicked.connect(self.mark_start_requested.emit)
        row_shift.addWidget(self.btn_mark_start, 1, 0)

        self.btn_mark_end = QPushButton("Out")
        self.btn_mark_end.setToolTip(
            "Set the active caption's end to the playback position"
        )
        self.btn_mark_end.setStyleSheet(SMALL_QSS)
        self.btn_mark_end.clicked.connect(self.mark_end_requested.emit)
        row_shift.addWidget(self.btn_mark_end, 1, 1)

        self.btn_shift_prev = QPushButton("◀ Shift Start")
        self.btn_shift_prev.setToolTip(
            "Move first word of selected segment to previous segment"
        )
        self.btn_shift_prev.setStyleSheet(SMALL_QSS)
        self.btn_shift_prev.clicked.connect(self._on_shift_prev_clicked)
        row_shift.addWidget(self.btn_shift_prev, 2, 0)

        self.btn_shift_next = QPushButton("Shift End ▶")
        self.btn_shift_next.setToolTip(
            "Move last word of selected segment to next segment"
        )
        self.btn_shift_next.setStyleSheet(SMALL_QSS)
        self.btn_shift_next.clicked.connect(self._on_shift_next_clicked)
        row_shift.addWidget(self.btn_shift_next, 2, 1, 1, 2)

        self.btn_delete_empty = QPushButton("🗑 Delete Empty")
        self.btn_delete_empty.setToolTip(
            "Delete the selected caption slot once all its words have been "
            "shifted away and it is empty"
        )
        self.btn_delete_empty.setStyleSheet(SMALL_QSS)
        self.btn_delete_empty.setEnabled(False)
        self.btn_delete_empty.clicked.connect(self._on_delete_empty_clicked)
        row_shift.addWidget(self.btn_delete_empty, 1, 2)
        layout.addLayout(row_shift)

        # Compact Position controls
        pos_container = QWidget()
        pos_container.setStyleSheet("background-color: #27272a; border-radius: 6px;")
        pos_layout = QVBoxLayout(pos_container)
        pos_layout.setContentsMargins(8, 6, 8, 6)
        pos_layout.setSpacing(4)

        pos_header = QGridLayout()
        pos_header.setSpacing(6)
        pos_lbl = QLabel("Position:")
        pos_lbl.setStyleSheet("font-weight: 600; font-size: 11px; color: #a1a1aa;")
        pos_header.addWidget(pos_lbl, 0, 0)

        btn_style = SMALL_QSS
        self.btn_top = QPushButton("Top (15%)")
        self.btn_top.setStyleSheet(btn_style)
        self.btn_top.setFixedHeight(22)
        self.btn_top.clicked.connect(
            lambda: self.set_anchor_pct(15.0, user_action=True)
        )
        pos_header.addWidget(self.btn_top, 1, 0)

        self.btn_middle = QPushButton("Mid (50%)")
        self.btn_middle.setStyleSheet(btn_style)
        self.btn_middle.setFixedHeight(22)
        self.btn_middle.clicked.connect(
            lambda: self.set_anchor_pct(50.0, user_action=True)
        )
        pos_header.addWidget(self.btn_middle, 1, 1)

        self.btn_bottom = QPushButton("Bot (80%)")
        self.btn_bottom.setStyleSheet(btn_style)
        self.btn_bottom.setFixedHeight(22)
        self.btn_bottom.clicked.connect(
            lambda: self.set_anchor_pct(80.0, user_action=True)
        )
        pos_header.addWidget(self.btn_bottom, 1, 2)

        self.btn_apply_all = QPushButton("Apply to All")
        self.btn_apply_all.setToolTip(
            "Set this vertical position for every caption in the video "
            "(replaces all per-caption position overrides with one)"
        )
        self.btn_apply_all.setStyleSheet(btn_style)
        self.btn_apply_all.setFixedHeight(22)
        self.btn_apply_all.clicked.connect(self._on_apply_all_clicked)
        pos_header.addWidget(self.btn_apply_all, 2, 0, 1, 3)

        self.lbl_anchor_value = QLabel("75.0%")
        self.lbl_anchor_value.setStyleSheet(
            "font-weight: bold; font-size: 11px; color: #818cf8;"
        )
        pos_header.addWidget(
            self.lbl_anchor_value, 0, 2, alignment=Qt.AlignmentFlag.AlignRight
        )
        pos_layout.addLayout(pos_header)

        # Precision slider
        self.slider_anchor = QSlider(Qt.Orientation.Horizontal)
        self.slider_anchor.setRange(5, 95)
        self.slider_anchor.setValue(80)
        self.slider_anchor.setFixedHeight(18)
        self.slider_anchor.valueChanged.connect(self._on_slider_changed)
        pos_layout.addWidget(self.slider_anchor)

        # Safe area platform overlays (TikTok, Reels, Shorts)
        safe_row = QHBoxLayout()
        safe_row.setSpacing(6)
        safe_lbl = QLabel("Safe Zones:")
        safe_lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #a1a1aa;")
        safe_row.addWidget(safe_lbl)

        btn_safe_base = (
            "QPushButton { font-size: 11px; padding: 2px 8px; border-radius: 6px; "
            "border: 1px solid #3f3f46; background-color: #27272a; color: #a1a1aa; } "
            "QPushButton:hover { background-color: #3f3f46; color: #ffffff; }"
        )
        self.btn_safe_tiktok = QPushButton("TikTok")
        self.btn_safe_tiktok.setCheckable(True)
        self.btn_safe_tiktok.setFixedHeight(22)
        self.btn_safe_tiktok.setStyleSheet(btn_safe_base)
        self.btn_safe_tiktok.clicked.connect(
            lambda: self._toggle_safe_platform("tiktok")
        )
        safe_row.addWidget(self.btn_safe_tiktok)

        self.btn_safe_reels = QPushButton("Reels")
        self.btn_safe_reels.setCheckable(True)
        self.btn_safe_reels.setFixedHeight(22)
        self.btn_safe_reels.setStyleSheet(btn_safe_base)
        self.btn_safe_reels.clicked.connect(lambda: self._toggle_safe_platform("reels"))
        safe_row.addWidget(self.btn_safe_reels)

        self.btn_safe_shorts = QPushButton("Shorts")
        self.btn_safe_shorts.setCheckable(True)
        self.btn_safe_shorts.setFixedHeight(22)
        self.btn_safe_shorts.setStyleSheet(btn_safe_base)
        self.btn_safe_shorts.clicked.connect(
            lambda: self._toggle_safe_platform("shorts")
        )
        safe_row.addWidget(self.btn_safe_shorts)
        safe_row.addStretch()
        pos_layout.addLayout(safe_row)

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
        self.btn_save_preset.setStyleSheet(SMALL_QSS)
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

        self.chk_multiline = QCheckBox("2-Line")
        self.chk_multiline.setToolTip(
            "Wrap karaoke captions onto two lines instead of one, so more "
            "words stay on screen at once (recommended for large fonts on "
            "portrait video, where one-line karaoke can shrink to ~2 words "
            "per block)"
        )
        self.chk_multiline.setChecked(self.current_style.multiline)
        self.chk_multiline.toggled.connect(self._on_multiline_toggled)
        row_colors.addWidget(self.chk_multiline)

        self.chk_justify = QCheckBox("Justify")
        self.chk_justify.setToolTip(
            "Two lines flush to the same width: each line's font size is "
            "chosen so it fills the caption box, so a short line renders "
            "large and a long one small"
        )
        self.chk_justify.setChecked(self.current_style.justify_lines)
        self.chk_justify.toggled.connect(self._on_justify_toggled)
        row_colors.addWidget(self.chk_justify)

        self.chk_bg_box = QCheckBox("BG Box")
        self.chk_bg_box.setToolTip(
            "Draw a semi-transparent box behind the caption text (square "
            "corners in the actual export — ASS subtitles can't do rounded "
            "corners like the in-app preview's pill)"
        )
        self.chk_bg_box.setChecked(self.current_style.background_box)
        self.chk_bg_box.toggled.connect(self._on_bg_box_toggled)
        row_colors.addWidget(self.chk_bg_box)

        self.chk_glow = QCheckBox("Glow")
        self.chk_glow.setToolTip(
            "A soft halo of the text colour around the letters, in the captions "
            "and in the thumbnail title"
        )
        self.chk_glow.setChecked(self.current_style.glow_effect)
        self.chk_glow.toggled.connect(self._on_glow_toggled)
        row_colors.addWidget(self.chk_glow)
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
        self._update_safe_button_styles()
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
        self.combo_template.addItem("Justified (Two Flush Lines)", "justified")

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
                # Render each entry in its own actual typeface (already loaded
                # into QFontDatabase by init_app_fonts) so the menu is a real
                # preview instead of plain text that looks nothing like what
                # gets applied.
                act.setFont(QFont(f, 13))
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

    def _on_multiline_toggled(self, checked: bool) -> None:
        self.current_style.multiline = checked
        self.style_changed.emit(self.current_style)

    def _on_justify_toggled(self, checked: bool) -> None:
        self.current_style.justify_lines = checked
        self.style_changed.emit(self.current_style)

    def _on_bg_box_toggled(self, checked: bool) -> None:
        self.current_style.background_box = checked
        self.style_changed.emit(self.current_style)

    def _on_glow_toggled(self, checked: bool) -> None:
        self.current_style.glow_effect = checked
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
        self.set_anchor_pct(style.anchor_pct, user_action=False)
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
        self.chk_multiline.setChecked(style.multiline)
        self.chk_justify.setChecked(style.justify_lines)
        self.chk_bg_box.setChecked(style.background_box)
        self.chk_glow.setChecked(style.glow_effect)
        self._update_color_buttons()

        self._block_signals = False
        self.style_changed.emit(self.current_style)

    def _on_combine_syllables_clicked(self) -> None:
        self.commit_active_editor()
        self.segments = combine_separated_syllables(self.segments)
        self.segments = apply_orphan_rules(self.segments)
        self.set_segments(self.segments)
        self.segments_updated.emit(self.segments)

    def _on_group_words_clicked(self) -> None:
        self.commit_active_editor()
        self.segments = group_words_into_phrases(self.segments)
        self.set_segments(self.segments)
        self.segments_updated.emit(self.segments)

    def _on_fix_orphans_clicked(self) -> None:
        self.commit_active_editor()
        self.segments = apply_orphan_rules(self.segments)
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

    def spell_spans_for_row(self, row: int) -> list[tuple[int, int, str]]:
        """Misspelled (start, end, word) spans of a row, cached per repaint."""
        if not self.spell_checker.available or not (0 <= row < len(self.segments)):
            return []
        cached = self._spell_cache.get(row)
        if cached is None:
            cached = self.spell_checker.misspelled_spans(self.segments[row])
            self._spell_cache[row] = cached
        return cached

    def _invalidate_spell_cache(self, row: int | None = None) -> None:
        if row is None:
            self._spell_cache.clear()
        else:
            self._spell_cache.pop(row, None)

    def _char_under(self, row: int, pos: QPoint) -> int | None:
        """The character boundary under a viewport point in a text cell."""
        item = self.cue_table.item(row, COL_TEXT)
        if not item:
            return None
        rect: QRect = self.cue_table.visualItemRect(item).adjusted(4, 0, -4, 0)
        wrapped = WrappedText(item.text(), self.cue_table.font(), rect.width())
        top = rect.top() + (rect.height() - wrapped.height) / 2
        return wrapped.char_at(pos.x() - rect.left(), pos.y() - top)

    def _spell_span_at(self, row: int, pos: QPoint) -> tuple[int, int, str] | None:
        """The misspelled word under a viewport point, if any."""
        spans = self.spell_spans_for_row(row)
        if not spans:
            return None
        char = self._char_under(row, pos)
        if char is None:
            return None
        for start, end, word in spans:
            if start < char <= end:
                return (start, end, word)
        return None

    def _token_under(self, row: int, pos: QPoint) -> int | None:
        """Index of the word at or just after a viewport point in a text cell."""
        char = self._char_under(row, pos)
        if char is None:
            return None
        item = self.cue_table.item(row, COL_TEXT)
        rect: QRect = self.cue_table.visualItemRect(item).adjusted(4, 0, -4, 0)
        wrapped = WrappedText(item.text(), self.cue_table.font(), rect.width())
        return wrapped.token_index(char)

    def _on_table_context_menu(self, pos: QPoint) -> None:
        index = self.cue_table.indexAt(pos)
        if not index.isValid() or index.column() != COL_TEXT:
            return
        row = index.row()
        menu = QMenu(self)

        span = self._spell_span_at(row, pos)
        if span:
            start, end, word = span
            suggestions = self.spell_checker.suggest(word)[:6]
            if suggestions:
                for suggestion in suggestions:
                    action = menu.addAction(suggestion)
                    action.triggered.connect(
                        lambda _checked=False, s=suggestion: self._replace_word(
                            row, start, end, s
                        )
                    )
            else:
                no_hits = menu.addAction(f"No suggestions for “{word}”")
                no_hits.setEnabled(False)

        token = self._token_under(row, pos)
        words = self.segments[row].text.split()
        # The first word has nothing before it to split from.
        if token and token < len(words):
            if not menu.isEmpty():
                menu.addSeparator()
            split = menu.addAction(f"Split caption before “{words[token]}”")
            split.triggered.connect(
                lambda _checked=False, r=row, t=token: self._split_cue(r, t)
            )

        if menu.isEmpty():
            return
        menu.exec(self.cue_table.viewport().mapToGlobal(pos))

    def _split_cue(self, row: int, token_index: int) -> None:
        self.commit_active_editor()
        if not split_segment(self.segments, row, token_index):
            return
        self.set_segments(self.segments)
        self.cue_table.selectRow(row)
        self.segments_updated.emit(self.segments)

    def _replace_word(self, row: int, start: int, end: int, replacement: str) -> None:
        if not (0 <= row < len(self.segments)):
            return
        seg = self.segments[row]
        seg.update_text(seg.text[:start] + replacement + seg.text[end:])
        self._invalidate_spell_cache(row)
        self.set_segments(self.segments)
        self.cue_table.selectRow(row)
        self.segment_updated.emit(seg)
        self.segments_updated.emit(self.segments)

    def _on_delete_empty_clicked(self) -> None:
        row = self.cue_table.currentRow()
        if not (0 <= row < len(self.segments)):
            return
        self.commit_active_editor()
        if row >= len(self.segments) or self.segments[row].text.strip():
            return
        delete_segment(self.segments, row)
        self.set_segments(self.segments)
        if self.segments:
            self.cue_table.selectRow(min(row, len(self.segments) - 1))
        else:
            self.btn_delete_empty.setEnabled(False)
        self.segments_updated.emit(self.segments)

    def set_segments(self, segments: list[CaptionSegment]) -> None:
        """Show `segments` in the table.

        Called after every edit with the whole list, so the cells are written
        in place: a cell whose text is unchanged costs nothing, and only the
        rows whose text did change are measured again.
        """
        self._block_signals = True
        self.segments = list(segments)
        self._row_of = {id(seg): row for row, seg in enumerate(self.segments)}
        self._invalidate_spell_cache()
        old_rows = self.cue_table.rowCount()
        self.cue_table.setRowCount(len(self.segments))

        editable = (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEditable
        )
        changed_rows: list[int] = []
        for row, seg in enumerate(self.segments):
            if row < old_rows and self.cue_table.item(row, COL_TEXT) is not None:
                item_text = self.cue_table.item(row, COL_TEXT)
                if item_text.text() != seg.text:
                    item_text.setText(seg.text)
                    changed_rows.append(row)
                self.cue_table.item(row, COL_START).setText(
                    format_timestamp(seg.start_ms)
                )
                self.cue_table.item(row, COL_END).setText(format_timestamp(seg.end_ms))
                self._refresh_duration_cell(row)
                continue

            item_start = QTableWidgetItem(format_timestamp(seg.start_ms))
            item_start.setFlags(editable)

            item_end = QTableWidgetItem(format_timestamp(seg.end_ms))
            item_end.setFlags(editable)

            item_text = QTableWidgetItem(seg.text)
            item_text.setFlags(editable)

            item_duration = QTableWidgetItem()
            item_duration.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            )

            self.cue_table.setItem(row, COL_START, item_start)
            self.cue_table.setItem(row, COL_END, item_end)
            self.cue_table.setItem(row, COL_DURATION, item_duration)
            self.cue_table.setItem(row, COL_TEXT, item_text)
            self._refresh_duration_cell(row)
            changed_rows.append(row)

        self._fit_rows(changed_rows)
        self._block_signals = False

    def _fit_rows(self, rows: list[int]) -> None:
        """Size the given rows to their (wrapped) text; all rows past a third
        of the table, since then one pass over the table is the cheaper way."""
        if len(rows) > max(1, self.cue_table.rowCount() // 3):
            self.cue_table.resizeRowsToContents()
            return
        for row in rows:
            self.cue_table.resizeRowToContents(row)

    def _row_for(self, segment: CaptionSegment | None) -> int:
        """The row showing `segment`: the same object first, an equal one
        failing that, as before the row map; -1 when it is not in the table."""
        if segment is None:
            return -1
        row = self._row_of.get(id(segment), -1)
        if row >= 0 and self.segments[row] is segment:
            return row
        return next((i for i, seg in enumerate(self.segments) if seg == segment), -1)

    def select_segment(
        self, segment: CaptionSegment | None, anchor_y_pct: float = 75.0
    ) -> None:
        self.selected_segment = segment
        self.set_anchor_pct(anchor_y_pct, user_action=False)

        if not segment:
            self.cue_table.clearSelection()
            self.btn_delete_empty.setEnabled(False)
            return

        row = self._row_for(segment)
        if row >= 0:
            self._block_signals = True
            self.cue_table.selectRow(row)
            self._block_signals = False
            self.btn_delete_empty.setEnabled(not self.segments[row].text.strip())

    def set_playhead_segment(self, segment: CaptionSegment | None) -> None:
        """Highlight and reveal the cue currently under the video playhead."""
        if self.playhead_segment is segment:
            return
        previous = self._row_for(self.playhead_segment)
        self.playhead_segment = segment
        current = self._row_for(segment)
        for row in {previous, current} - {-1}:
            for column in range(self.cue_table.columnCount()):
                item = self.cue_table.item(row, column)
                if item:
                    item.setBackground(QColor())
        if current >= 0:
            # Follow playback with the table's normal blue selection. Suppress
            # the selection callback: it seeks to the selected cue's start.
            self._block_signals = True
            self.cue_table.selectRow(current)
            self._block_signals = False
            self.cue_table.scrollToItem(
                self.cue_table.item(current, 0),
                QAbstractItemView.ScrollHint.EnsureVisible,
            )
        else:
            self._block_signals = True
            self.cue_table.clearSelection()
            self._block_signals = False

    def _on_apply_all_clicked(self) -> None:
        self._set_style_anchor(self.active_anchor_pct)
        self.apply_position_to_all_requested.emit(self.active_anchor_pct)

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
        elif user_action:
            # No caption picked: the position is the style's, so every caption moves.
            self._set_style_anchor(self.active_anchor_pct)

    def _set_style_anchor(self, pct: float) -> None:
        # A new style object, so the listener can tell the position changed.
        self.current_style = replace(self.current_style, anchor_pct=float(pct))
        self.style_changed.emit(self.current_style)

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
                self.btn_delete_empty.setEnabled(not seg.text.strip())
                self.segment_selected.emit(seg)
                return
        self.btn_delete_empty.setEnabled(False)

    def commit_active_editor(self) -> None:
        # Force any active delegate editor to submit its data and close
        for child in self.cue_table.viewport().children():
            if isinstance(child, QWidget):
                self.cue_table.commitData(child)
                self.cue_table.closeEditor(
                    child, QAbstractItemDelegate.EndEditHint.SubmitModelCache
                )
        self.cue_table.setCurrentItem(None)
        # Ensure any edited text in table items is completely synchronized to the segment objects
        for row in range(min(self.cue_table.rowCount(), len(self.segments))):
            item = self.cue_table.item(row, COL_TEXT)
            if item and item.text() != self.segments[row].text:
                self.segments[row].update_text(item.text())
                self.segment_updated.emit(self.segments[row])

    def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
        if self._block_signals:
            return
        row = item.row()
        col = item.column()
        if not (0 <= row < len(self.segments)):
            return
        if col == COL_TEXT:
            seg = self.segments[row]
            seg.update_text(item.text())
            self._invalidate_spell_cache(row)
            self._refresh_duration_cell(row)
            self.cue_table.resizeRowToContents(row)
            self.segment_updated.emit(seg)
        elif col in (COL_START, COL_END):
            self._apply_edited_timecode(row, col, item.text())

    def _apply_edited_timecode(self, row: int, col: int, text: str) -> None:
        seg = self.segments[row]
        parsed = parse_timestamp(text)
        if parsed is None:
            # Unparseable: put the cue's own time back in the cell.
            self._refresh_time_cells(row)
            return
        start_ms = parsed if col == COL_START else seg.start_ms
        end_ms = parsed if col == COL_END else seg.end_ms
        self._retime_segment(row, start_ms, end_ms)

    def _retime_segment(self, row: int, start_ms: int, end_ms: int) -> None:
        seg = self.segments[row]
        start_ms, end_ms = clamped_segment_time(self.segments, row, start_ms, end_ms)
        set_segment_time(seg, start_ms, end_ms)
        self._refresh_time_cells(row)
        self.segment_updated.emit(seg)
        self.segments_updated.emit(self.segments)

    def _refresh_time_cells(self, row: int) -> None:
        seg = self.segments[row]
        was_blocked = self._block_signals
        self._block_signals = True
        for col, ms in ((COL_START, seg.start_ms), (COL_END, seg.end_ms)):
            cell = self.cue_table.item(row, col)
            if cell:
                cell.setText(format_timestamp(ms))
        self._refresh_duration_cell(row)
        self._block_signals = was_blocked

    def _refresh_duration_cell(self, row: int) -> None:
        """Show the cue's length, flagged when the time does not fit its text."""
        seg = self.segments[row]
        cell = self.cue_table.item(row, COL_DURATION)
        if cell is None:
            return
        was_blocked = self._block_signals
        self._block_signals = True
        cell.setText(f"{(seg.end_ms - seg.start_ms) / 1000:.2f} s")
        flag = timing_flag(seg)
        if flag:
            cell.setForeground(QColor(FLAG_COLORS[flag]))
        else:
            cell.setData(Qt.ItemDataRole.ForegroundRole, None)
        cps = chars_per_second(seg)
        if cps is None:
            cell.setToolTip("")
        else:
            note = f"; {TIMING_NOTES[flag]}" if flag else ""
            cell.setToolTip(f"{cps:.1f} characters per second{note}")
        self._block_signals = was_blocked

    def eventFilter(self, obj, event) -> bool:  # type: ignore[override]
        """Alt+arrows retime the selected cue without leaving the table.

        An event filter rather than QShortcut objects: shortcuts registered on
        this table wedged the app's media loading (see test_main_window).
        """
        if obj is self.cue_table and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            mods = event.modifiers()
            if mods & Qt.KeyboardModifier.AltModifier and key in (
                Qt.Key.Key_Left,
                Qt.Key.Key_Right,
            ):
                delta = -NUDGE_MS if key == Qt.Key.Key_Left else NUDGE_MS
                if mods & Qt.KeyboardModifier.ShiftModifier:
                    edge = "end"
                elif mods & Qt.KeyboardModifier.ControlModifier:
                    edge = "both"
                else:
                    edge = "start"
                self.nudge_selected_cue(delta, edge)
                return True
        return super().eventFilter(obj, event)

    def cue_moved_on_timeline(self, seg: CaptionSegment) -> None:
        """The timeline has already retimed `seg`; bring the table and project along."""
        row = self._row_for(seg)
        if row < 0:
            return
        self._refresh_time_cells(row)
        self.segment_updated.emit(seg)
        self.segments_updated.emit(self.segments)

    def active_row(self) -> int:
        """The selected cue, or the one under the playhead when none is selected."""
        row = self.cue_table.currentRow()
        if 0 <= row < len(self.segments):
            return row
        return self._row_for(self.playhead_segment)

    def set_active_start(self, ms: int) -> bool:
        """Put the active cue's start at `ms`. False when no cue is active."""
        row = self.active_row()
        if row < 0:
            return False
        self._retime_segment(row, ms, self.segments[row].end_ms)
        return True

    def set_active_end(self, ms: int) -> bool:
        """Put the active cue's end at `ms`. False when no cue is active."""
        row = self.active_row()
        if row < 0:
            return False
        self._retime_segment(row, self.segments[row].start_ms, ms)
        return True

    def nudge_selected_cue(self, delta_ms: int, edge: str) -> None:
        """Move one edge of the selected cue, or the whole cue when edge='both'."""
        row = self.cue_table.currentRow()
        if not (0 <= row < len(self.segments)):
            return
        seg = self.segments[row]
        if edge == "start":
            self._retime_segment(row, seg.start_ms + delta_ms, seg.end_ms)
        elif edge == "end":
            self._retime_segment(row, seg.start_ms, seg.end_ms + delta_ms)
        else:
            self._retime_segment(row, seg.start_ms + delta_ms, seg.end_ms + delta_ms)

    def _toggle_safe_platform(self, platform_id: str) -> None:
        if platform_id in self.active_safe_platforms:
            self.active_safe_platforms.remove(platform_id)
        else:
            self.active_safe_platforms.add(platform_id)
        self._update_safe_button_styles()
        self.safe_platforms_changed.emit(set(self.active_safe_platforms))

    def _update_safe_button_styles(self) -> None:
        colors = {"tiktok": "#22d3ee", "reels": "#e879f9", "shorts": "#fb923c"}
        buttons = {
            "tiktok": self.btn_safe_tiktok,
            "reels": self.btn_safe_reels,
            "shorts": self.btn_safe_shorts,
        }
        for plat_id, btn in buttons.items():
            is_active = plat_id in self.active_safe_platforms
            btn.setChecked(is_active)
            c = colors[plat_id]
            if is_active:
                btn.setStyleSheet(
                    f"QPushButton {{ font-size: 11px; font-weight: bold; padding: 2px 8px; border-radius: 6px; "
                    f"border: 1px solid {c}; background-color: {c}33; color: {c}; }} "
                    f"QPushButton:hover {{ background-color: {c}55; }}"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton { font-size: 11px; padding: 2px 8px; border-radius: 6px; "
                    "border: 1px solid #3f3f46; background-color: #27272a; color: #a1a1aa; } "
                    "QPushButton:hover { background-color: #3f3f46; color: #ffffff; }"
                )
