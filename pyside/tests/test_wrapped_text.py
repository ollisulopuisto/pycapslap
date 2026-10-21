from PySide6.QtGui import QFont

from app.models.captions import CaptionSegment, WordSpan
from app.views.caption_panel import CaptionPanelWidget
from app.views.wrapped_text import WrappedText


def test_words_on_the_last_line_are_found(qtbot):
    text = "aaaa bbbb cccc dddd eeee ffff"
    wrapped = WrappedText(text, QFont(), 60)

    assert len(wrapped.lines) > 1
    last = wrapped.lines[-1]
    char = wrapped.char_at(2, last.y() + 1)
    assert char >= last.textStart()
    assert wrapped.token_index(text.index("ffff") + 2) == 5


def test_past_the_last_word_there_is_no_word(qtbot):
    wrapped = WrappedText("one two", QFont(), 400)
    assert wrapped.token_index(len("one two") + 1) is None


def test_long_caption_gets_a_taller_row(qtbot):
    panel = CaptionPanelWidget()
    qtbot.addWidget(panel)
    panel.resize(300, 600)
    panel.show()
    short = CaptionSegment(
        start_ms=0, end_ms=1000, text="Joo", words=[WordSpan(0, 1000, "Joo")]
    )
    long_text = " ".join(["sanoja"] * 30)
    long = CaptionSegment(
        start_ms=1000,
        end_ms=9000,
        text=long_text,
        words=[WordSpan(1000, 9000, long_text)],
    )
    panel.set_segments([short, long])
    qtbot.wait(20)

    assert panel.cue_table.rowHeight(1) > panel.cue_table.rowHeight(0)


def test_a_word_on_a_wrapped_line_can_be_split_from_the_table(qtbot):
    from PySide6.QtCore import QPoint

    panel = CaptionPanelWidget()
    qtbot.addWidget(panel)
    panel.resize(300, 600)
    panel.show()
    text = " ".join(f"sana{i}" for i in range(20))
    seg = CaptionSegment(
        start_ms=0, end_ms=5000, text=text, words=[WordSpan(0, 5000, text)]
    )
    panel.set_segments([seg])
    qtbot.wait(20)

    item = panel.cue_table.item(0, 3)
    rect = panel.cue_table.visualItemRect(item).adjusted(4, 0, -4, 0)
    wrapped = WrappedText(text, panel.cue_table.font(), rect.width())
    last = wrapped.lines[-1]
    top = rect.top() + (rect.height() - wrapped.height) / 2
    pos = QPoint(rect.left() + 3, int(top + last.y() + 2))

    expected = wrapped.token_index(last.textStart() + 1)
    assert expected is not None and expected > 0
    assert panel._token_under(0, pos) == expected
