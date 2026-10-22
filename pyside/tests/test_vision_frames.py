from PySide6.QtGui import QColor, QImage

from app.services.vision_frames import SuggestedFrame, _jpeg, _sharpness
from app.views.thumbnail_panel import ThumbnailPanel


def _checkerboard(size: int = 96) -> QImage:
    image = QImage(size, size, QImage.Format.Format_RGB32)
    for y in range(size):
        for x in range(size):
            image.setPixelColor(
                x, y, QColor("#ffffff" if (x // 4 + y // 4) % 2 else "#000000")
            )
    return image


def _flat(size: int = 96) -> QImage:
    image = QImage(size, size, QImage.Format.Format_RGB32)
    image.fill(QColor("#808080"))
    return image


def test_a_detailed_frame_is_sharper_than_a_flat_one(qtbot):
    assert _sharpness(_checkerboard()) > _sharpness(_flat()) + 1000


def test_a_suggestion_is_a_small_jpeg(qtbot):
    data = _jpeg(_checkerboard(640), 320)
    picture = QImage.fromData(data)
    assert data[:2] == b"\xff\xd8"
    assert picture.width() == 320


def test_the_panel_lists_suggested_frames_and_reports_the_pick(qtbot):
    panel = ThumbnailPanel()
    qtbot.addWidget(panel)
    panel.show()
    picked = []
    panel.suggestion_chosen.connect(picked.append)

    frames = [
        SuggestedFrame(
            time_seconds=12.5, scores={"quality": 0.9}, jpeg=_jpeg(_checkerboard(), 96)
        ),
        SuggestedFrame(
            time_seconds=40.0, scores={"quality": 0.7}, jpeg=_jpeg(_flat(), 96)
        ),
    ]
    panel.show_suggestions(frames)

    assert panel.suggestions.count() == 2
    assert panel.suggestions.isVisible()
    panel.suggestions.itemClicked.emit(panel.suggestions.item(1))
    assert picked == [40.0]
