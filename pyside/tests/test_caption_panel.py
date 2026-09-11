from app.models.captions import CaptionSegment
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
