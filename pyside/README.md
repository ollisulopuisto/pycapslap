# PyCapSlap ⚡

**PyCapSlap** is the native, high-performance Python + Qt (PySide6) desktop application for **CapSlap**. It delivers sub-millisecond video scrub latency, interactive on-video caption dragging, visual timeline editing, and local Orukeet or Whisper transcription through the Rust core.

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
* **📋 Caption Inspector & Table:** In-place cue text editing, editable `mm:ss.t` timecodes (clamped to the neighbouring cues, with word timings scaled to match), `Alt`+arrow nudging, deletion of cues emptied by word shifting, quick position presets (`Top 15%`, `Middle 50%`, `Bottom 80%`), and precision slider.
* **🤖 Auto-Dodge Captions:** Calls the Rust core to scan video activity across 10 vertical bands and intelligently dodge faces and platform UI overlays (TikTok, Reels, Shorts).
* **🔒 Local transcription:** Choose Orukeet or whisper.cpp beside Transcribe. Orukeet's verified Q8 model and native runtime stay loaded in a worker; Whisper uses a selectable local model downloaded from Transcription Settings. Both work offline after setup.
* **🧩 Syllable & Orphan Fixups:** One-click "Fix Syllables" rejoins split word fragments, and "Fix Orphans" prevents trailing conjunctions and lone words from being stranded on their own line.
* **🔤 Finnish Spell Check (optional):** with `libvoikko` installed (`brew install libvoikko`), unknown words are underlined in the cue table and right-click offers corrections; deliberately split syllables are not flagged. Without the library nothing is flagged and everything else works unchanged.
* **👁️ Preview = Render:** the canvas draws the layout the Rust core produces for the burn — same cues, line breaks, per-line font sizes, uppercasing, highlighted word and vertical anchor — instead of laying captions out a second time and disagreeing with the export.
* **📐 Justified Two-Line Style:** both lines flush to the same width, each line's font size chosen so it fills the caption box; measured against the actual font file rather than estimated from character counts.
* **📱 Platform Safe Areas:** Toggleable TikTok / Reels / Shorts UI overlays on the canvas, respected by Auto-Dodge placement.
* **🎬 Multi-Format Rendering:** Burn captions into 9:16, 1:1, 4:5, or 16:9 exports with one click via the Rust + FFmpeg VideoToolbox pipeline, with live render progress.
* **💾 Sidecar Persistence:** Automatic loading and saving of `.capslap.json` sidecar files.
* **📊 Live Perf Telemetry:** Status bar shows GUI/Rust core RSS memory and rolling seek latency in real time.

---

## 🧪 Testing & Linting

```bash
# Run unit and Qt widget tests
uv run pytest

# Run linter
uv run ruff check .
```
