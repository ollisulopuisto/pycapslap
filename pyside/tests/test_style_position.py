from dataclasses import replace

from PySide6.QtGui import QColor, QImage

from app.models.captions import CaptionSegment, CaptionStyle, ProjectState
from app.views.caption_panel import CaptionPanelWidget
from app.views.thumbnail_panel import compose


def test_style_carries_its_position_and_defaults_to_75():
    assert CaptionStyle().anchor_pct == 75.0
    style = CaptionStyle(anchor_pct=60.0)
    assert CaptionStyle.from_dict(style.to_dict()).anchor_pct == 60.0
    assert CaptionStyle.from_dict({}).anchor_pct == 75.0


def test_moving_the_position_without_a_caption_changes_the_style(qtbot):
    panel = CaptionPanelWidget()
    qtbot.addWidget(panel)
    changed = []
    panel.style_changed.connect(changed.append)

    panel.set_anchor_pct(40.0, user_action=True)

    assert changed and changed[-1].anchor_pct == 40.0
    assert panel.get_current_style().anchor_pct == 40.0


def test_a_style_sets_the_panel_position(qtbot):
    panel = CaptionPanelWidget()
    qtbot.addWidget(panel)

    panel.set_style(replace(panel.get_current_style(), anchor_pct=60.0))

    assert panel.active_anchor_pct == 60.0
    assert panel.lbl_anchor_value.text() == "60.0%"


def test_captions_without_their_own_position_sit_at_the_style_position():
    project = ProjectState()
    project.style = CaptionStyle(anchor_pct=60.0)
    seg = CaptionSegment(start_ms=0, end_ms=1000, text="a")

    project.ensure_position()

    assert len(project.position_overrides) == 1
    assert project.position_overrides[0].y_pct == 60.0
    assert project.get_anchor_y_for_segment(seg) == 60.0
    assert project.is_dirty is False


def test_thumbnail_title_follows_the_caption_style(qtbot):
    frame = QImage(540, 960, QImage.Format.Format_ARGB32)
    frame.fill(QColor("#336699"))
    base = CaptionStyle()

    small = compose(frame, "Otsikko", replace(base, font_size=30))
    large = compose(frame, "Otsikko", replace(base, font_size=120))
    high = compose(frame, "Otsikko", replace(base, anchor_pct=20.0))
    low = compose(frame, "Otsikko", replace(base, anchor_pct=80.0))

    assert small != large
    assert high != low


def test_glow_checkbox_sets_the_style(qtbot):
    panel = CaptionPanelWidget()
    qtbot.addWidget(panel)
    changed = []
    panel.style_changed.connect(changed.append)

    panel.chk_glow.setChecked(False)
    assert changed and changed[-1].glow_effect is False

    panel.set_style(CaptionStyle(glow_effect=True))
    assert panel.chk_glow.isChecked()
