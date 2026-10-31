"""Keep the editor out of App Nap while core jobs are in flight (macOS).

Transcription, rendering and exports run in the Rust core subprocess, but
the editor process is what keeps that work alive: its reader threads drain
the core's stdout/stderr (the core blocks on a full pipe, which has hung
transcription before), it dispatches every job, and it reports progress.
When every PyCapSlap window is hidden, App Nap may throttle the process —
timers coalesce and scheduling priority drops — and a worker spawned while
its parent is napped can inherit the lowered priority. App Nap's candidacy
rules are app-centric (foreground, visible windows, audible), so the core
binary is not itself a candidate; the editor is the process to protect.

``AppNapGuard`` brackets in-flight core calls with an ``NSProcessInfo``
activity, reference-counted so overlapping jobs share one assertion. The
option is ``NSActivityBackground`` on purpose: it only makes the app
ineligible for App Nap. The user-initiated option would also keep the
*display* awake for the whole export, which is the opposite of saving
power; the machine must still sleep on its normal schedule.

Off macOS, without PyObjC, or if the assertion itself fails, the guard is
a no-op: the job still runs, the OS simply keeps its default heuristics.
The Cocoa object is injectable so tests need no Mac.
"""

from __future__ import annotations

import logging
import sys
import threading
from typing import Any

logger = logging.getLogger("capslap.app_nap")

# NSActivityBackground from NSProcessInfo.h: makes the app ineligible for
# App Nap only — no display-sleep or system-sleep effect. (The
# UserInitiated options include IdleDisplaySleepDisabled = 1 << 40.)
NS_ACTIVITY_BACKGROUND = 0x00000000000000FF


class AppNapGuard:
    """Reference-counted NSProcessInfo assertion against App Nap.

    Thread-safe: ``begin`` is called on the main thread (``CoreClient.call``)
    and ``end`` from the reader thread that completes the call's Future.
    """

    def __init__(self, process_info: Any = None):
        self._lock = threading.Lock()
        self._active = 0
        self._activity: Any = None
        self._process_info = process_info
        if self._process_info is None and sys.platform == "darwin":
            try:
                from Foundation import NSProcessInfo

                self._process_info = NSProcessInfo.processInfo()
            except Exception as exc:  # no PyObjC, or not a Cocoa process
                logger.debug("NSProcessInfo unavailable, App Nap guard off: %s", exc)

    @property
    def available(self) -> bool:
        return self._process_info is not None

    @property
    def held(self) -> bool:
        with self._lock:
            return self._activity is not None

    def begin(self, reason: str) -> int:
        """Hold the app out of App Nap until the returned token is ended."""
        with self._lock:
            self._active += 1
            if self._activity is None and self._process_info is not None:
                try:
                    self._activity = self._process_info.beginActivityWithOptions_reason_(
                        NS_ACTIVITY_BACKGROUND, reason
                    )
                except Exception as exc:
                    logger.warning("could not begin App Nap assertion: %s", exc)
            return self._active

    def end(self, token: int | None) -> None:
        """Release one ``begin``; the assertion drops when the last job ends."""
        if token is None:
            return
        with self._lock:
            if self._active <= 0:
                logger.warning("AppNapGuard.end without a matching begin")
                return
            self._active -= 1
            if self._active == 0 and self._activity is not None:
                activity, self._activity = self._activity, None
                try:
                    self._process_info.endActivity_(activity)
                except Exception as exc:
                    logger.warning("could not end App Nap assertion: %s", exc)
