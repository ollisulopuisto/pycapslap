"""Run with the signed frozen GUI executable and no GUI event loop."""

from app.services.proofreading import Cue, check_snapshot


def smoke():
    rows = check_snapshot((Cue("Tämä on kaupppa."), Cue("He ei tiedä.")), "errors")
    assert any(
        i.category == "spelling" and "kauppa" in i.replacements for i in rows[0]
    ), rows
    assert any(
        i.category == "grammar" and "eivät" in i.replacements for i in rows[1]
    ), rows
    import punakyna.backend_voikko as backend
    from punakyna.voikko_gc import _resolve_libfile
    import os
    import sys

    if getattr(sys, "frozen", False):
        path = _resolve_libfile(os.environ["PUNAKYNA_LIBVOIKKO_PATH"])
        assert path.startswith(sys._MEIPASS), path
        assert backend.ACTIVE_BACKEND is not None
    print("Bundled Finnish spelling and grammar smoke passed")
