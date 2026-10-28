import os

from app.models.captions import CaptionSegment, ProjectState
from app.models.history import History


def test_uncapped_branches_and_snapshot_isolation():
    history = History({"text": "root", "style": {"size": 20}})
    for i in range(1100):
        history.record({"text": str(i), "style": {"size": 20}})
    tip_a = history.current
    history.undo()
    history.record({"text": "branch B", "style": {"size": 40}})
    tip_b = history.current
    assert history.tips() == [tip_a, tip_b]
    assert history.select(tip_a)["text"] == "1099"
    history.undo()
    assert history.redo()["text"] == "1099"
    value = history.select(tip_b)
    value["style"]["size"] = 999
    assert history.select(tip_b)["style"]["size"] == 40
    for _ in range(1100):
        history.undo()
    assert history.current == 0


def test_atomic_save_failure_preserves_original(tmp_path, monkeypatch):
    target = tmp_path / "video.capslap.json"
    target.write_text("last good save")
    project = ProjectState(segments=[CaptionSegment(0, 1000, "new")], is_dirty=True)

    def fail(*_):
        raise OSError("disk error")

    monkeypatch.setattr(os, "replace", fail)
    assert project.save_sidecar(target) is False
    assert project.is_dirty
    assert target.read_text() == "last good save"
    assert list(tmp_path.iterdir()) == [target]


def test_atomic_save_success(tmp_path):
    target = tmp_path / "video.capslap.json"
    project = ProjectState(segments=[CaptionSegment(0, 1000, "new")], is_dirty=True)
    assert project.save_sidecar(target)
    assert not project.is_dirty
    restored = ProjectState()
    assert restored.load_sidecar(target)
    assert restored.segments[0].text == "new"


def _window(qtbot):
    from concurrent.futures import Future
    from PySide6.QtCore import QObject, Signal
    from app.views.main_window import MainWindow

    class Core(QObject):
        progress = Signal(str, str, float)
        proc = None

        def call(self, *_args):
            result = Future()
            result.set_result({})
            return result

        def close(self):
            pass

    window = MainWindow(core_client=Core())
    qtbot.addWidget(window)
    return window


def test_window_cancel_discard_and_failed_save(qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    window = _window(qtbot)
    window.project.is_dirty = True
    monkeypatch.setattr(
        QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Cancel
    )
    assert not window._confirm_unsaved()
    monkeypatch.setattr(
        QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Save
    )
    assert not window._confirm_unsaved()  # no destination, must not close
    monkeypatch.setattr(
        QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Discard
    )
    assert window._confirm_unsaved()
    window.project.is_dirty = False
    window.close()


def test_window_project_edit_undo_redo(qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(
        QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Discard
    )
    window = _window(qtbot)
    window.set_caption_segments([CaptionSegment(0, 1000, "A")])
    from app.views.caption_panel import COL_TEXT

    window.caption_panel.cue_table.item(0, COL_TEXT).setText("B")
    window._undo_project()
    assert window.project.segments[0].text == "A"
    window._redo_project()
    assert window.project.segments[0].text == "B"
    monkeypatch.setattr(
        QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Discard
    )
    window.close()


def test_qt_window_branches_style_trim_and_close_cancel(qtbot, monkeypatch):
    from dataclasses import replace
    from PySide6.QtGui import QCloseEvent
    from PySide6.QtWidgets import QMessageBox
    from app.views.caption_panel import COL_TEXT

    monkeypatch.setattr(
        QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Discard
    )
    window = _window(qtbot)
    window.set_caption_segments([CaptionSegment(0, 1000, "root")])
    window.caption_panel.cue_table.item(0, COL_TEXT).setText("A")
    history = window._histories[""]
    tip_a = history.current
    window._undo_project()
    window.caption_panel.cue_table.item(0, COL_TEXT).setText("B")
    tip_b = history.current
    assert tip_a in history.tips() and tip_b in history.tips()
    window._restore_history(history.select(tip_a))
    assert window.project.segments[0].text == "A"
    original = window.project.style.font_size
    window._on_style_changed(replace(window.project.style, font_size=original + 10))
    window._undo_project()
    assert window.project.style.font_size == original
    window.timeline.set_duration(10000)
    window.timeline.set_trim_range(1000, 7000)
    window._on_trim_changed()
    assert window.project.trim_start_ms == 1000
    window._undo_project()
    assert window.project.trim_start_ms != 1000
    monkeypatch.setattr(
        QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Cancel
    )
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted() and not window._closed
    monkeypatch.setattr(
        QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Discard
    )
    window.close()


def test_source_switch_cancel_leaves_project_untouched(qtbot, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QMessageBox

    window = _window(qtbot)
    window.project.is_dirty = True
    monkeypatch.setattr(
        QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Cancel
    )
    window.load_video(str(tmp_path / "another.mp4"))
    assert window.project.video is None and not window._history_loading
    monkeypatch.setattr(
        QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Discard
    )
    window.close()


def test_source_load_resets_metadata_but_keeps_separate_session_trees(
    qtbot, monkeypatch, tmp_path
):
    from PySide6.QtWidgets import QMessageBox
    from app.models.captions import PositionOverride
    from app.models.project import VideoMetadata
    from app.views import main_window
    from app.views.caption_panel import COL_TEXT

    monkeypatch.setattr(
        QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Discard
    )
    window = _window(qtbot)
    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    a.write_bytes(b"a")
    b.write_bytes(b"b")
    window.project.video = VideoMetadata(str(a))
    window.project.position_overrides = [PositionOverride(0, 1000, 20)]
    window.project.thumbnail = {"headline": "old"}
    window.set_caption_segments([CaptionSegment(0, 1000, "A")])
    window.caption_panel.cue_table.item(0, COL_TEXT).setText("A edited")
    a_history = window._histories[str(a)]
    monkeypatch.setattr(window.player, "load_video", lambda *_: None)
    monkeypatch.setattr(window, "trigger_extract_thumbnail", lambda *_: None)
    monkeypatch.setattr(main_window.shutil, "which", lambda *_: None)
    window.load_video(str(b))
    assert window.project.video_path == str(b)
    assert window.project.thumbnail == {}
    assert not window.project.is_dirty
    assert str(b) in window._histories and window._histories[str(a)] is a_history
    assert a_history.nodes[a_history.current].value["segments"][0]["text"] == "A edited"
    assert not window._history_loading
    window.close()


def test_failed_save_has_visible_feedback_and_does_not_close(
    qtbot, monkeypatch, tmp_path, no_modal_message_boxes
):
    from PySide6.QtWidgets import QMessageBox
    from app.models.project import VideoMetadata

    window = _window(qtbot)
    window.project.video = VideoMetadata(str(tmp_path / "a.mp4"))
    window.project.sidecar_path = str(tmp_path / "a.mp4.capslap.json")
    window.project.is_dirty = True
    monkeypatch.setattr(window.project, "save_sidecar", lambda *_: False)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Save
    )
    assert not window._confirm_unsaved()
    assert window.project.is_dirty and not window._closed
    assert (
        "warning",
        "The project was not saved. Your edits are still open.",
    ) in no_modal_message_boxes
    monkeypatch.setattr(
        QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Discard
    )
    window.close()
