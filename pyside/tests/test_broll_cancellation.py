import sys
import threading
import time

import pytest

from app.services.broll import control, net


def test_stream_reads_only_bounded_chunks_and_cancel_cleans_caller(
    tmp_path, monkeypatch
):
    cancel = threading.Event()
    sizes = []

    class Response:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def read(self, size):
            sizes.append(size)
            assert 0 < size <= 256 * 1024
            return b"x" * size

    monkeypatch.setattr(net.urllib.request, "urlopen", lambda *_a, **_k: Response())
    with pytest.raises(control.Cancelled):
        net.download(
            "https://example.invalid/video",
            tmp_path / "part",
            cancel=cancel,
            progress=lambda *_: cancel.set(),
        )
    assert sizes == [256 * 1024]


def test_process_cancellation_terminates_child_and_bounds_diagnostics():
    cancel = threading.Event()
    timer = threading.Timer(0.2, cancel.set)
    timer.start()
    start = time.monotonic()
    try:
        with pytest.raises(control.Cancelled):
            control.run(
                [sys.executable, "-c", "import time; time.sleep(20)"], cancel=cancel
            )
    finally:
        timer.join()
    assert time.monotonic() - start < 5
    result = control.run(
        [sys.executable, "-c", 'import sys; sys.stderr.write("x"*1000000)']
    )
    assert result.returncode == 0
    assert len(result.stderr) <= 32 * 4096


def test_download_cancel_removes_partial_not_completed_asset(tmp_path, monkeypatch):
    from app.services.broll import download
    from app.services.broll.assets import Asset

    asset = Asset("clip", "video", "https://example.invalid/clip.mp4", "page")
    monkeypatch.setattr(download.sources, "resolve", lambda a: a)

    def interrupted(_url, path, **_kwargs):
        path.write_bytes(b"partial")
        raise control.Cancelled("cancelled")

    monkeypatch.setattr(net, "download", interrupted)
    with pytest.raises(control.Cancelled):
        download.fetch(asset, tmp_path, cancel=threading.Event())
    assert list(tmp_path.iterdir()) == []


def test_cancelled_render_keeps_existing_output(tmp_path, monkeypatch):
    from app.services.broll import reel

    out = tmp_path / "reel.mp4"
    out.write_bytes(b"existing finished movie")
    monkeypatch.setattr(reel, "prepare_stills", lambda shots, *_: shots)
    monkeypatch.setattr(reel, "command", lambda *_a, **_k: ["fake-ffmpeg"])

    def cancelled(*_a, **_k):
        (tmp_path / ".reel.part.mp4").write_bytes(b"partial")
        raise control.Cancelled("cancelled")

    monkeypatch.setattr(control, "run", cancelled)
    with pytest.raises(control.Cancelled):
        reel.render(
            tmp_path / "audio.wav",
            [],
            out,
            tmp_path / "work",
            duration_s=2,
            hw=False,
            cancel=threading.Event(),
        )
    assert out.read_bytes() == b"existing finished movie"
    assert not (tmp_path / ".reel.part.mp4").exists()


def test_short_download_is_not_treated_as_complete(tmp_path, monkeypatch):
    class Response:
        headers = {"Content-Length": "1000"}
        chunks = iter([b"short", b""])

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def read(self, _size):
            return next(self.chunks)

    monkeypatch.setattr(net.urllib.request, "urlopen", lambda *_a, **_k: Response())
    with pytest.raises(OSError, match="Incomplete"):
        net.download("https://example.invalid/clip", tmp_path / "part")
