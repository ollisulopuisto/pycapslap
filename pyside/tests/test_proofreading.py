from types import SimpleNamespace

import pytest

from app.services import proofreading as p
from app.services.proofreading_worker import Proofreader


def finding(
    start, end, category="grammar", severity="error", replacements=("correct",)
):
    return SimpleNamespace(
        start=start,
        end=end,
        category=category,
        severity=severity,
        replacements=replacements,
        message="Test explanation",
    )


def test_joined_context_preserves_current_offset():
    cues = (p.Cue("Tämä on"), p.Cue("testi"), p.Cue("joka jatkuu."))
    text, a, b = p.context(cues, 1)
    assert text == "Tämä on testi joka jatkuu."
    assert text[a:b] == "testi"


def test_split_word_is_joined_without_whitespace():
    cues = (p.Cue("kaup-"), p.Cue("pa", True), p.Cue("aukeaa."))
    text, a, b = p.context(cues, 1)
    assert text == "kauppa aukeaa."
    assert text[a:b] == "pa"


def test_neighbour_context_and_cross_cue_suppression(monkeypatch):
    seen = []

    def check(text, style):
        seen.append(text)
        return (finding(0, len(text)), finding(6, 8))

    monkeypatch.setattr(p, "_check", check)
    rows = p.check_snapshot((p.Cue("Tämä"), p.Cue("on se")), "errors")
    assert seen == ["Tämä on se", "Tämä on se"]
    assert rows[0] == ()
    assert rows[1][0].start == 1
    assert rows[1][0].end == 3


def test_styles_are_opt_in(monkeypatch):
    monkeypatch.setattr(
        p,
        "_check",
        lambda text, style: (finding(0, 2), finding(3, 5, "grammar", "style")),
    )
    cues = (p.Cue("He ei"),)
    assert len(p.check_snapshot(cues, "errors")[0]) == 1
    assert [i.category for i in p.check_snapshot(cues, "style")[0]] == [
        "grammar",
        "style",
    ]


def test_off_never_loads_native_engine(monkeypatch):
    monkeypatch.setattr(p, "configure_bundle", lambda: pytest.fail("engine loaded"))
    assert p.check_snapshot((p.Cue("x"),), "off") == ((),)


def test_deliberately_split_edge_is_not_flagged(monkeypatch):
    monkeypatch.setattr(p, "_check", lambda *args: (finding(0, 2),))
    assert p.check_snapshot((p.Cue("pa", True),), "errors") == ((),)


def test_missing_frozen_library_is_an_error(monkeypatch, tmp_path):
    monkeypatch.setattr(p.sys, "frozen", True, raising=False)
    monkeypatch.setattr(p.sys, "_MEIPASS", str(tmp_path), raising=False)
    with pytest.raises(RuntimeError, match="missing"):
        p.configure_bundle()


def test_worker_reports_failure_without_text_in_status(qtbot, monkeypatch):
    import app.services.proofreading_worker as w

    monkeypatch.setattr(
        w,
        "check_snapshot",
        lambda *args: (_ for _ in ()).throw(RuntimeError("private text")),
    )
    reader = Proofreader()
    reader.request((p.Cue("private text"),), "errors")
    qtbot.waitUntil(lambda: bool(reader.error))
    assert "private text" not in reader.error


def test_stale_worker_result_is_discarded(qtbot):
    reader = Proofreader()
    reader.generation = 2
    reader.busy = True
    reader._done(1, (("stale",),), "")
    assert reader.rows == ()


def test_worker_starts_only_latest_pending_request(qtbot, monkeypatch):
    import app.services.proofreading_worker as w

    seen = []
    monkeypatch.setattr(
        w, "check_snapshot", lambda cues, mode: seen.append(cues) or ((),)
    )
    reader = Proofreader()
    reader.request((p.Cue("old"),), "errors")
    reader.request((p.Cue("new"),), "off")
    qtbot.waitUntil(lambda: bool(seen))
    assert seen == [(p.Cue("new"),)]


def test_native_engine_when_available():
    try:
        p._check("Tämä on teksti.", False)
    except Exception:
        pytest.skip("Native Voikko not installed")
    from app.services.proofreading_smoke import smoke

    smoke()
