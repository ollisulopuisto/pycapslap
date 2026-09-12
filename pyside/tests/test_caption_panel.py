from app.models.captions import CaptionSegment, WordSpan
from app.views.caption_panel import CaptionPanelWidget


def test_caption_panel_initial_state(qtbot):
    panel = CaptionPanelWidget()
    qtbot.addWidget(panel)

    assert panel.segments == []
    assert panel.selected_segment is None
    assert panel.active_anchor_pct == 80.0


def test_caption_panel_load_segments(qtbot):
    panel = CaptionPanelWidget()
    qtbot.addWidget(panel)

    seg1 = CaptionSegment(start_ms=1000, end_ms=2000, text="First cue")
    seg2 = CaptionSegment(start_ms=2500, end_ms=4000, text="Second cue")
    panel.set_segments([seg1, seg2])

    assert len(panel.segments) == 2
    assert panel.cue_table.rowCount() == 2
    assert panel.cue_table.item(0, 2).text() == "First cue"
    assert panel.cue_table.item(1, 2).text() == "Second cue"


def test_caption_panel_preset_position_buttons(qtbot):
    panel = CaptionPanelWidget()
    qtbot.addWidget(panel)

    seg = CaptionSegment(start_ms=1000, end_ms=2000, text="Position test")
    panel.set_segments([seg])
    panel.select_segment(seg, anchor_y_pct=80.0)

    emitted_overrides = []
    panel.position_override_changed.connect(
        lambda s, y: emitted_overrides.append((s, y))
    )

    # Click 'Top' button (15%)
    panel.btn_top.click()
    assert len(emitted_overrides) == 1
    assert emitted_overrides[-1] == (seg, 15.0)
    assert panel.slider_anchor.value() == 15

    # Click 'Middle' button (50%)
    panel.btn_middle.click()
    assert len(emitted_overrides) == 2
    assert emitted_overrides[-1] == (seg, 50.0)
    assert panel.slider_anchor.value() == 50

    # Click 'Bottom' button (80%)
    panel.btn_bottom.click()
    assert len(emitted_overrides) == 3
    assert emitted_overrides[-1] == (seg, 80.0)
    assert panel.slider_anchor.value() == 80


def test_caption_panel_style_selection(qtbot):
    panel = CaptionPanelWidget()
    qtbot.addWidget(panel)

    emitted_styles = []
    panel.style_changed.connect(emitted_styles.append)

    # Change template preset to Karaoke
    idx = panel.combo_template.findData("karaoke")
    assert idx >= 0
    panel.combo_template.setCurrentIndex(idx)

    assert len(emitted_styles) > 0
    current_style = panel.get_current_style()
    assert current_style.karaoke is True
    assert current_style.template_id == "karaoke"


def test_caption_panel_style_collapsible(qtbot):
    panel = CaptionPanelWidget()
    qtbot.addWidget(panel)
    panel.show()

    # Style content should be collapsed by default
    assert hasattr(panel, "btn_toggle_style")
    assert hasattr(panel, "style_content")
    assert not panel.style_content.isVisible()
    assert "▶" in panel.btn_toggle_style.text()

    # Click toggle to expand
    panel.btn_toggle_style.click()
    assert panel.style_content.isVisible()
    assert "▼" in panel.btn_toggle_style.text()

    # Click toggle to collapse again
    panel.btn_toggle_style.click()
    assert not panel.style_content.isVisible()
    assert "▶" in panel.btn_toggle_style.text()


def test_caption_panel_edit_cell_syncs_segment(qtbot):
    panel = CaptionPanelWidget()
    qtbot.addWidget(panel)

    seg = CaptionSegment(
        start_ms=0,
        end_ms=2000,
        text="Initial text",
        words=[
            WordSpan(start_ms=0, end_ms=1000, text="Initial"),
            WordSpan(start_ms=1000, end_ms=2000, text=" text"),
        ],
    )
    panel.set_segments([seg])

    emitted_updates = []
    panel.segment_updated.connect(emitted_updates.append)

    # Edit text in table item
    item = panel.cue_table.item(0, 2)
    item.setText("Replaced caption here")

    assert len(emitted_updates) == 1
    assert seg.text == "Replaced caption here"
    assert len(seg.words) == 3
    assert seg.words[0].text == "Replaced"
    assert seg.words[-1].text == " here"

    # Verify commit_active_editor clears selection / finishes editing
    panel.commit_active_editor()
    assert panel.cue_table.currentItem() is None


def test_caption_panel_hierarchical_font_menu(qtbot):
    panel = CaptionPanelWidget()
    qtbot.addWidget(panel)

    assert hasattr(panel, "btn_font")
    assert hasattr(panel, "font_menu")
    actions = panel.font_menu.actions()
    assert len(actions) > 0

    emitted = []
    panel.style_changed.connect(emitted.append)
    panel.set_font_name("Komika Axis")
    assert panel.current_style.font_name == "Komika Axis"
    assert "Komika Axis" in panel.btn_font.text()
    assert len(emitted) > 0


def test_caption_panel_custom_preset_saving(qtbot, tmp_path, monkeypatch):
    preset_file = tmp_path / "panel_presets.json"
    from PySide6.QtWidgets import QInputDialog
    from app.services.preset_manager import PresetManager

    manager = PresetManager(storage_path=preset_file)

    panel = CaptionPanelWidget(preset_manager=manager)
    qtbot.addWidget(panel)

    panel.set_font_name("Komika Axis")
    panel.slider_font_size.setValue(77)

    monkeypatch.setattr(
        QInputDialog, "getText", lambda *args, **kwargs: ("Podcast Show", True)
    )

    panel.btn_save_preset.click()

    assert "Podcast Show" in manager.list_presets()
    idx = panel.combo_template.findData("Podcast Show")
    assert idx >= 0


def test_caption_panel_combine_syllables_button(qtbot):
    panel = CaptionPanelWidget()
    qtbot.addWidget(panel)

    seg1 = CaptionSegment(
        start_ms=0,
        end_ms=1000,
        text="kaup",
        words=[WordSpan(0, 1000, "kaup")],
    )
    seg2 = CaptionSegment(
        start_ms=1000,
        end_ms=2000,
        text="pa kes kus",
        words=[
            WordSpan(1000, 1500, "pa", glue_to_previous=True),
            WordSpan(1500, 2000, "kes kus"),
        ],
    )
    panel.set_segments([seg1, seg2])

    emitted = []
    panel.segments_updated.connect(emitted.append)

    panel.btn_combine_syllables.click()
    assert len(emitted) == 1
    assert len(panel.segments) == 2
    assert panel.segments[0].text == "kauppa"
    assert panel.segments[1].text == "kes kus"


def test_caption_panel_shift_start_and_end(qtbot):
    panel = CaptionPanelWidget()
    qtbot.addWidget(panel)

    seg1 = CaptionSegment(
        start_ms=0,
        end_ms=1000,
        text="First",
        words=[WordSpan(0, 1000, "First")],
    )
    seg2 = CaptionSegment(
        start_ms=1000,
        end_ms=2500,
        text="Second Third",
        words=[WordSpan(1000, 1800, "Second"), WordSpan(1800, 2500, "Third")],
    )
    panel.set_segments([seg1, seg2])

    # Select second segment
    panel.cue_table.selectRow(1)

    # Shift first word ("Second") to previous segment
    panel.btn_shift_prev.click()
    assert panel.segments[0].text == "First Second"
    assert panel.segments[1].text == "Third"

    # Shift it back
    panel.cue_table.selectRow(0)
    panel.btn_shift_next.click()
    assert panel.segments[0].text == "First"
    assert panel.segments[1].text == "Second Third"
