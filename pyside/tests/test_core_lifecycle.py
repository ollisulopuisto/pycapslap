import sys
import threading

import pytest

from app.core_client import CoreClient

# A stand-in for the Rust core: says a lot on stderr before every answer, as
# ffmpeg's banner does during transcription, and answers each request with its id.
FAKE_CORE = """\
#!{python}
import json, sys
for line in sys.stdin:
    req = json.loads(line)
    if req["method"] == "hang":
        continue
    sys.stderr.write(("ffmpeg chatter " * 64 + "\\n") * {chatter_lines})
    sys.stderr.flush()
    sys.stdout.write(json.dumps({{"id": req["id"], "result": req["params"]}}) + "\\n")
    sys.stdout.flush()
"""


@pytest.fixture
def fake_core(tmp_path):
    def make(chatter_lines: int = 64) -> CoreClient:
        # Three levels deep: the client looks for rust/bin two levels up.
        path = tmp_path / "rust" / "target" / "release" / "core"
        path.parent.mkdir(parents=True)
        path.write_text(
            FAKE_CORE.format(python=sys.executable, chatter_lines=chatter_lines)
        )
        path.chmod(0o755)
        return CoreClient(binary_path=str(path))

    return make


def test_unread_stderr_does_not_stall_the_core(qapp, fake_core):
    # ~60 KB of stderr per request: without a reader the pipe is full after
    # the first one or two, and the core blocks before it answers.
    client = fake_core(chatter_lines=64)
    try:
        for n in range(10):
            assert client.call("echo", n).result(timeout=5.0) == n
    finally:
        client.close()


def test_close_fails_what_is_still_waiting(qapp, fake_core):
    client = fake_core()
    fut = client.call("hang", None)
    client.close()
    with pytest.raises(RuntimeError):
        fut.result(timeout=2.0)
    assert client.proc.returncode is not None  # reaped, not a zombie
    assert client.proc.stdout.closed and client.proc.stderr.closed
    assert not client._reader_thread.is_alive()
    assert not client._stderr_thread.is_alive()
    client.close()  # twice is fine


def test_a_call_after_close_fails_at_once(qapp, fake_core):
    client = fake_core()
    client.close()
    with pytest.raises((RuntimeError, OSError, ValueError)):
        client.call("echo", 1).result(timeout=1.0)


def test_a_large_reply_arrives_whole(qapp, fake_core):
    # Replies such as a frame are one JSON line of hundreds of kilobytes.
    client = fake_core(chatter_lines=0)
    try:
        blob = "A" * 600_000
        assert client.call("echo", blob).result(timeout=5.0) == blob
    finally:
        client.close()


def test_results_after_close_are_not_delivered_to_the_window(qapp):
    from app.views.main_window import MainWindow

    window = MainWindow()
    ran = threading.Event()
    window.close()
    window._in_gui(ran.set)
    qapp.processEvents()
    assert not ran.is_set()


def test_telemetry_stays_idle_while_its_label_is_hidden(qapp):
    from app.views.main_window import MainWindow

    window = MainWindow()
    try:
        assert not window.perf_lbl.isVisible()
        before = window.perf_lbl.text()
        window._update_telemetry()
        assert window.perf_lbl.text() == before
        assert window._gui_process is None
    finally:
        window.close()
