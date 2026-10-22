from app.models.captions import CaptionSegment, CaptionsFile, ProjectState, WordSpan
from app.views.thumbnail_panel import ThumbnailPanel


def test_the_sidecar_keeps_the_thumbnail_frame_and_headline(tmp_path):
    project = ProjectState()
    project.segments = [CaptionSegment(0, 1000, "a", words=[WordSpan(0, 1000, "a")])]
    project.thumbnail = {"timeMs": 17897, "title": "Miksi Eurooppa ajautuu sotaan?"}
    path = tmp_path / "episode.capslap.json"
    assert project.save_sidecar(path)

    loaded = ProjectState()
    assert loaded.load_sidecar(path)
    assert loaded.thumbnail == {
        "timeMs": 17897,
        "title": "Miksi Eurooppa ajautuu sotaan?",
    }


def test_no_thumbnail_leaves_the_file_as_before():
    assert "thumbnail" not in CaptionsFile().to_dict()


def test_the_panel_restores_its_state_without_marking_a_change(qtbot):
    panel = ThumbnailPanel()
    qtbot.addWidget(panel)
    changed = []
    panel.changed.connect(lambda: changed.append(True))

    panel.load_state({"timeMs": 5000, "title": "Otsikko"})

    assert panel.title_edit.text() == "Otsikko"
    assert panel.state() == {"timeMs": 5000, "title": "Otsikko"}
    assert changed == []
