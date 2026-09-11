# PyCapSlap ⚡

**PyCapSlap** is the native, high-performance Python + Qt (PySide6) desktop application for **CapSlap**. It delivers sub-millisecond video scrub latency, a -74% RAM reduction compared to Electron, interactive on-video caption dragging, visual timeline editing, and 100% offline Whisper transcription powered by the Rust core processing engine.

---

## 🚀 Quick Start

### Prerequisites
* **Python 3.12+**
* [**uv**](https://github.com/astral-sh/uv) (recommended Python package manager)
* Rust release binary built in `../rust` (`cargo build --release`)

### Installation & Launch

```bash
# Enter the pyside directory
cd pyside

# Run directly with uv
uv run pycapslap

# Or pass a video file directly
uv run pycapslap ../rust/bin/test_input.mp4
```

---

## ✨ Features

* **⚡ Sub-Millisecond Frame Scrubbing:** Direct hardware-accelerated playback with Qt 6 Multimedia + FFmpeg backend (0.1–0.5 ms average seek latency).
* **🖱️ Direct On-Video Dragging:** Click and drag caption cues directly on top of the video canvas to adjust vertical placement (`anchor_y`) with a live guideline and percentage badge.
* **🎞️ Interactive Visual Timeline:** Proportional cue blocks, scrubber needle, and instant timeline scrubbing.
* **📋 Caption Inspector & Table:** In-place cue text editing, quick position presets (`Top 15%`, `Middle 50%`, `Bottom 80%`), and precision slider.
* **🤖 Auto-Dodge Captions:** Calls the Rust core to scan video activity across 10 vertical bands and intelligently dodge faces and platform UI overlays (TikTok, Reels, Shorts).
* **🔒 100% Offline AI Transcription:** Local whisper.cpp transcription via asynchronous Rust IPC with live progress reporting.
* **💾 Sidecar Persistence:** Automatic loading and saving of `.capslap.json` sidecar files.

---

## 📊 Measured Benchmark: PyCapSlap vs. Electron

Tested on macOS Apple Silicon (Darwin arm64) using a 1080p sample video:

| Metric | Electron (Legacy) | PyCapSlap | Delta |
| :--- | :--- | :--- | :--- |
| **Processes Spawned** | 7 processes | **1 process** | **-85% process overhead** |
| **Startup Time** | 3.01 s | **1.38 s** | **2.18× faster** |
| **Idle Memory (GUI)** | 597.5 MB | **154.8 MB** | **-74.1% memory** |
| **Total Memory (inc. Rust)** | 602.2 MB | **158.8 MB** | **-73.6% memory** |
| **Playback CPU Load** | 15% – 35% | **4.7%** | **~3× to 7× lower CPU** |
| **Seek Latency** | ~120 – 250 ms | **0.3 ms** | **Near-instantaneous** |

---

## 🧪 Testing & Linting

```bash
# Run unit and Qt widget tests
uv run pytest

# Run linter
uv run ruff check .
```
