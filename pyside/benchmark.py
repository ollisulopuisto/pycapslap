import os
import sys
import time
from pathlib import Path

import psutil
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from app.views.main_window import MainWindow


def measure_pyside(video_path: str):
    print("=" * 60)
    print("RUNNING PYSIDE6 / QT 6 FEASIBILITY BENCHMARK")
    print("=" * 60)

    # 1. Measure Startup Time
    t_start = time.perf_counter()
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    # Process initial events to ensure window is painted on screen
    app.processEvents()
    startup_sec = time.perf_counter() - t_start

    # 2. Measure Idle RSS
    time.sleep(0.5)
    app.processEvents()
    proc = psutil.Process(os.getpid())
    idle_rss_mb = proc.memory_info().rss / (1024 * 1024)

    core_rss_mb = 0.0
    if window.core.proc:
        try:
            core_proc = psutil.Process(window.core.proc.pid)
            core_rss_mb = core_proc.memory_info().rss / (1024 * 1024)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    print(
        f"[PySide6] Cold Startup Time       : {startup_sec * 1000:.1f} ms ({startup_sec:.3f} s)"
    )
    print(f"[PySide6] GUI Process Idle RSS    : {idle_rss_mb:.2f} MB")
    print(f"[PySide6] Rust Core Subprocess RSS: {core_rss_mb:.2f} MB")
    print(f"[PySide6] Total Idle Footprint    : {idle_rss_mb + core_rss_mb:.2f} MB")

    # 3. Load 1080p Video
    print(f"\nLoading 1080p Video: {video_path}")
    t_load = time.perf_counter()
    window.load_video(video_path)

    # Wait for media player to load metadata
    loop = QEventLoop()
    window.player.media_player.durationChanged.connect(lambda _: loop.quit())
    QTimer.singleShot(2000, loop.quit)  # Timeout fallback
    loop.exec()
    load_latency_ms = (time.perf_counter() - t_load) * 1000

    time.sleep(0.5)
    app.processEvents()
    video_loaded_rss = proc.memory_info().rss / (1024 * 1024)
    if window.core.proc:
        try:
            core_proc = psutil.Process(window.core.proc.pid)
            core_rss_mb = core_proc.memory_info().rss / (1024 * 1024)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    print(f"[PySide6] Video Load Time         : {load_latency_ms:.1f} ms")
    print(f"[PySide6] GUI RSS (Video Loaded)  : {video_loaded_rss:.2f} MB")
    print(
        f"[PySide6] Total RSS (Video Loaded): {video_loaded_rss + core_rss_mb:.2f} MB"
    )

    # 4. Measure Seek Latencies across 10 points
    duration_ms = window.player.media_player.duration() or 10000
    seek_points = [
        int(duration_ms * pct)
        for pct in [0.1, 0.5, 0.25, 0.8, 0.3, 0.9, 0.15, 0.65, 0.4, 0.05]
    ]

    seek_latencies = []
    print(f"\nPerforming 10 random seeks across {duration_ms / 1000:.1f}s video...")

    for _i, target_ms in enumerate(seek_points):
        seek_loop = QEventLoop()
        t0 = time.perf_counter()
        measured_lat = None

        def on_pos_changed(pos, target=target_ms, t_start=t0, loop_ref=seek_loop):
            nonlocal measured_lat
            if abs(pos - target) < 250:
                measured_lat = (time.perf_counter() - t_start) * 1000
                loop_ref.quit()

        window.player.media_player.positionChanged.connect(on_pos_changed)
        window.player.seek_to_ms(target_ms)
        QTimer.singleShot(500, seek_loop.quit)
        seek_loop.exec()

        lat = (
            measured_lat
            if measured_lat is not None
            else (time.perf_counter() - t0) * 1000
        )
        seek_latencies.append(lat)
        window.player.media_player.positionChanged.disconnect(on_pos_changed)

    avg_seek = sum(seek_latencies) / len(seek_latencies)
    min_seek = min(seek_latencies)
    max_seek = max(seek_latencies)
    print(
        f"[PySide6] Seek Latencies (10 runs) : min={min_seek:.1f}ms, avg={avg_seek:.1f}ms, max={max_seek:.1f}ms"
    )

    # 5. Measure Playback CPU & Memory
    window.player.media_player.play()
    time.sleep(1.0)
    app.processEvents()
    cpu_percent = proc.cpu_percent(interval=0.5)
    playback_rss = proc.memory_info().rss / (1024 * 1024)
    window.player.media_player.pause()

    print(f"[PySide6] Active Playback RSS     : {playback_rss:.2f} MB")
    print(f"[PySide6] Active Playback CPU     : {cpu_percent:.1f}%")

    window.close()
    app.processEvents()

    return {
        "startup_sec": startup_sec,
        "idle_gui_rss": idle_rss_mb,
        "idle_total_rss": idle_rss_mb + core_rss_mb,
        "video_loaded_rss": video_loaded_rss + core_rss_mb,
        "avg_seek_ms": avg_seek,
        "min_seek_ms": min_seek,
        "max_seek_ms": max_seek,
        "playback_rss": playback_rss,
        "playback_cpu": cpu_percent,
    }


def main():
    video_path = str(Path("../rust/bin/test_input.mp4").resolve())
    if not os.path.exists(video_path):
        print(f"Error: test video not found at {video_path}")
        return

    metrics = measure_pyside(video_path)
    print("\nPyCapSlap benchmark results")
    print(f"GUI startup: {metrics['startup_sec']:.3f} s")
    print(f"Idle GUI memory: {metrics['idle_gui_rss']:.1f} MB")
    print(f"Idle total memory (including Rust): {metrics['idle_total_rss']:.1f} MB")
    print(f"Video loaded memory (including Rust): {metrics['video_loaded_rss']:.1f} MB")
    print(f"Average seek latency: {metrics['avg_seek_ms']:.1f} ms")
    print(f"Playback CPU: {metrics['playback_cpu']:.1f}%")


if __name__ == "__main__":
    main()
