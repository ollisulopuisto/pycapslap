from PySide6.QtGui import QKeySequence

from app.views.main_window import MainWindow


def _menu_actions(window):
    for menu_action in window.menuBar().actions():
        for action in menu_action.menu().actions():
            if not action.isSeparator():
                yield action


def _find(window, text):
    return next(a for a in _menu_actions(window) if a.text() == text)


def test_standard_mac_shortcuts_are_in_the_menus(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    def native(key):
        return QKeySequence(key).toString(QKeySequence.SequenceFormat.NativeText)

    expected = {
        "Open Video…": QKeySequence.StandardKey.Open,
        "Save Project": QKeySequence.StandardKey.Save,
        "Close Window": QKeySequence.StandardKey.Close,
        "Quit PyCapSlap": QKeySequence.StandardKey.Quit,
        "Zoom In": QKeySequence.StandardKey.ZoomIn,
        "Zoom Out": QKeySequence.StandardKey.ZoomOut,
        "Transcription Settings…": QKeySequence.StandardKey.Preferences,
    }
    for text, key in expected.items():
        assert _find(window, text).shortcut().toString(
            QKeySequence.SequenceFormat.NativeText
        ) == native(key), text


def test_a_menu_item_presses_its_button_only_while_it_is_enabled(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    presses = []
    window.save_btn.clicked.connect(lambda: presses.append("save"))

    window.save_btn.setEnabled(False)
    _find(window, "Save Project").trigger()
    assert presses == []

    window.save_btn.setEnabled(True)
    _find(window, "Save Project").trigger()
    assert presses == ["save"]
