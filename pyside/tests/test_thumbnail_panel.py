from PySide6.QtGui import QColor, QImage

from app.views.thumbnail_panel import ThumbnailPanel, compose


def _frame(width=540, height=960):
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor("#336699"))
    return image


def test_title_is_drawn_over_the_frame(qtbot):
    frame = _frame()
    plain = compose(frame, "")
    titled = compose(frame, "Kuinka huolissanne")

    assert plain == frame.convertToFormat(QImage.Format.Format_ARGB32)
    assert titled != plain
    assert titled.size() == frame.size()


def test_blank_title_leaves_the_frame_alone(qtbot):
    frame = _frame()
    assert compose(frame, "   ") == frame.convertToFormat(QImage.Format.Format_ARGB32)


def test_preview_follows_the_title_field(qtbot):
    panel = ThumbnailPanel()
    qtbot.addWidget(panel)
    panel.show()
    assert not panel.save_btn.isEnabled()

    panel.set_frame(_frame())
    assert panel.save_btn.isEnabled()
    first = panel.preview.pixmap().toImage()

    panel.title_edit.setText("Otsikko")
    assert panel.preview.pixmap().toImage() != first
    assert panel.rendered().size() == _frame().size()
