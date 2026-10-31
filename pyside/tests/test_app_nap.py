"""AppNapGuard: refcounted NSProcessInfo assertion, no Mac needed."""

import io

import pytest

from app.services.app_nap import NS_ACTIVITY_BACKGROUND, AppNapGuard

pytest.importorskip("PySide6")


class FakeActivity:
    pass


class FakeProcessInfo:
    def __init__(self, fail=False):
        self.fail = fail
        self.begun = []  # (options, reason)
        self.ended = []

    def beginActivityWithOptions_reason_(self, options, reason):
        if self.fail:
            raise RuntimeError("no assertions for you")
        self.begun.append((options, reason))
        return FakeActivity()

    def endActivity_(self, activity):
        self.ended.append(activity)


def test_background_option_is_nap_only():
    # 1 << 40 is IdleDisplaySleepDisabled; Background must not include it.
    assert NS_ACTIVITY_BACKGROUND & (1 << 40) == 0
    assert NS_ACTIVITY_BACKGROUND == 0xFF


def test_assertion_held_until_last_job_ends():
    pi = FakeProcessInfo()
    guard = AppNapGuard(process_info=pi)
    first = guard.begin("core:transcribe")
    second = guard.begin("core:export")
    assert len(pi.begun) == 1  # overlapping jobs share one assertion
    assert pi.begun[0][0] == NS_ACTIVITY_BACKGROUND
    assert guard.held
    guard.end(first)
    assert guard.held and not pi.ended
    guard.end(second)
    assert not guard.held and len(pi.ended) == 1


def test_begin_failure_still_balances():
    pi = FakeProcessInfo(fail=True)
    guard = AppNapGuard(process_info=pi)
    token = guard.begin("core:transcribe")
    guard.end(token)  # must not raise or leave the counter stuck
    guard.begin("core:export")
    assert pi.begun == []


def test_noop_paths():
    guard = AppNapGuard(process_info=None)  # off-macOS default in tests
    assert not guard.available
    token = guard.begin("core:transcribe")
    guard.end(token)
    guard.end(None)  # None token is a no-op


def test_unmatched_end_is_tolerated():
    pi = FakeProcessInfo()
    guard = AppNapGuard(process_info=pi)
    guard.end(1)  # warns, no crash, counter unchanged
    token = guard.begin("core:transcribe")
    guard.end(token)
    assert len(pi.ended) == 1


class _FakeStdin(io.BytesIO):
    def flush(self):
        pass


class _FakeProc:
    stdin = _FakeStdin()
    stdout = None
    stderr = None

    def poll(self):
        return None

    def terminate(self):
        pass

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass


def test_core_call_holds_assertion_for_call_lifetime(monkeypatch):
    from app.core_client import CoreClient

    monkeypatch.setattr(CoreClient, "_start_process", lambda self: None)
    pi = FakeProcessInfo()
    guard = AppNapGuard(process_info=pi)
    client = CoreClient.__new__(CoreClient)
    # Minimal init without QObject machinery or a real core.
    from PySide6.QtCore import QObject

    QObject.__init__(client)
    client.binary_path = "/nonexistent"
    client._nap_guard = guard
    client.proc = _FakeProc()
    client._pending = {}
    import threading
    from collections import deque

    client._lock = threading.Lock()
    client._write_lock = threading.Lock()
    client._reader_thread = None
    client._stderr_thread = None
    client._stderr_tail = deque(maxlen=20)
    client._running = False

    fut = client.call("transcribe", {}, request_id="t1")
    assert pi.begun and pi.begun[0][1] == "core:transcribe"
    assert not pi.ended
    fut.set_result({"ok": True})
    assert len(pi.ended) == 1

    # A failed send releases immediately.
    client.proc = None
    guard2_pi = FakeProcessInfo()
    client._nap_guard = AppNapGuard(process_info=guard2_pi)
    fut2 = client.call("transcribe", {})
    assert fut2.done() and guard2_pi.begun == []
