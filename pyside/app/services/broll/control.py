"""Cooperative cancellation and bounded external-process diagnostics."""

import subprocess
import threading
from collections import deque
from pathlib import Path


class Cancelled(ValueError):
    pass


def check(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise Cancelled("B-roll cancelled. Existing finished files were kept.")


def run(command: list[str], *, cwd: Path | None = None, cancel=None):
    check(cancel)
    tail = deque(maxlen=32)
    with subprocess.Popen(
        command, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    ) as process:

        def drain():
            while block := process.stderr.read(4096):
                tail.append(block)

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        try:
            while process.poll() is None:
                if cancel is not None and cancel.wait(0.1):
                    check(cancel)
                elif cancel is None:
                    threading.Event().wait(0.1)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            reader.join()
        return subprocess.CompletedProcess(
            command,
            process.returncode,
            stderr=b"".join(tail).decode("utf-8", "replace"),
        )
