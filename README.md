# PyCapSlap ⚡

**PyCapSlap** is a high-performance native desktop video caption generator and subtitle editor. It transcribes audio locally with Orukeet, creates timed caption segments, lets you edit placement and styling, and burns captions into exports across social aspect ratios.

**Local by default.** Orukeet's Q8 model and native runtime are downloaded and verified once. Audio is processed on your computer; transcription works offline after setup.

---

## 🛠️ Architecture

PyCapSlap is a native PySide6 (Qt 6) desktop application powered by a Rust core engine.

* **Unified Hardware Canvas**: Native `QVideoSink` surface renders video frames and active caption overlays in a single hardware-accelerated pass.
* **Non-blocking IPC**: Bi-directional asynchronous JSON-RPC streaming between Python and the Rust binary prevents UI stuttering under heavy transcription or encoding workloads.
* **Direct Project Root Execution**: Managed seamlessly with [`uv`](https://github.com/astral-sh/uv) workspace orchestration.

---

## ✨ Key Features

* 🎙️ **Local Orukeet Transcription**: Multilingual offline recognition using Orukeet's verified Q8 model and native runtime, with Metal acceleration on supported Apple Silicon systems. Choose **Verbatim** to keep filler words and repetitions, or **Edited** for a cleaner transcript. Download Orukeet from **Orukeet Settings** beside Transcribe. Orukeet supplies phrase-level timings; caption word timings are not fabricated.
* 🧩 **Smart Syllable Logic & Word Preservation**:
  * **Automatic Syllable Re-gluing**: Detects and merges broken syllables (`sep-` + `a-` + `rat-` + `ed` → `separated`) both within cues and across segment boundaries.
  * **Atomic Word Protection**: Guarantees that compound words or hyphenated phrases never get cut in half across line breaks or subtitle screens.
  * **Manual Word Shifting**: Instant `◀ Shift Start` and `Shift End ▶` buttons to shift words between adjacent cues without typing — a shifted syllable joins the word it belongs to instead of landing next to it.
  * **Finnish Spell Check** (optional): with [libvoikko](https://voikko.puimula.org/) installed, unknown words are underlined in the cue table and right-click offers corrections. Syllables split on purpose are left alone.
* ⏱️ **Cue Timing You Can Edit**:
  * Type timecodes straight into the Start/End columns (`mm:ss.t`), clamped to the neighbouring cues, with word timings scaled to match.
  * `Alt`+`←`/`→` nudges the start, `Alt`+`Shift`+`←`/`→` the end, `Alt`+`Ctrl`+`←`/`→` the whole cue.
* ✂️ **Trimming**: drag the blue handles on the timeline, or stop playback on the frame you want and press `I` (start) or `O` (end), or click the I and O buttons next to Stop. **Stop** returns to the trim's start and playback stops at its end, so checking the cut is one click.
  * Delete a cue emptied by shifting its words away; its time goes to the cue that took them.
* 🔤 **Hierarchical Typography System**:
  * Organized font menus categorized into **Modern / Sans**, **Display / Impact**, **Fun / Comic**, **Serif / Elegant**, and **Handwritten / Script**.
  * Bundled with creator-favorite fonts: Montserrat, Komika Axis, THE BOLD FONT, Roboto, Bebas Neue, Bangers, and more.
* 🎨 **Custom Show Style Presets**:
  * Save custom typography, font sizes, colors, and karaoke highlight styling permanently per show or podcast.
  * Fast dropdown switcher to recall styles for different projects instantly.
  * **Justified two-line style**: both lines flush to the same width, each sized to fill it, so a short line renders large and a long one small — measured against the real font, not guessed.
* 👁️ **What You See Is What Gets Burned**: the on-video preview draws the layout the renderer produces — the same line breaks, font sizes, uppercasing and placement that end up in the export, rather than a second guess at them.
* 🎯 **Interactive Timeline & Auto-Dodge**:
  * Real-time drag-and-drop vertical subtitle positioning on video canvas.
  * Automated computer-vision activity detection ("Auto Dodge") to avoid obscuring faces or high-motion areas.
* ✅ **Client Review**: send the captions to a client, who checks and corrects them in their browser on the [review page](https://ollisulopuisto.github.io/pycapslap/) and sends the file back.
  * **Client Review → Export for Review…** saves a `.review.capslap.json`, locked with a password it offers to generate. Send the file with the video (a smaller preview is fine), and the password another way, such as a text message. The page is public, but a locked file is useless without the password; share the video through a link that needs a login or a password.
  * The client opens both on the page, watches the video with the captions on it, fixes wording or timing, leaves comments, and downloads the reviewed file, locked with the same password. Nothing is uploaded; a half-done review survives a closed tab, locked too.
  * **Client Review → Import Reviewed Captions…** applies their fixes cue by cue (word timings are rebuilt from yours, style and positions stay) and lists their comments. Save, render.
* 🗂️ **Review portal** ([`portal/`](portal/README.md)): a small server of your own where clients see their series and episodes through one secret link per series, play and download the proof renders, check the captions on the review page and send the fixes straight back, and leave free-form feedback, optionally pinned to a moment in a video.
  * **Client Review → Publish to Portal…** uploads the latest render (its proof copy, by default) and the captions into a series and episode, made when new, and copies the episode's link.
  * **Client Review → Import from Portal** fetches the newest captions for this video, with the client's corrections, and applies them like an imported review. The admin page (`/admin`) lists every captions version and all feedback.
* 💾 **Non-destructive Sidecar Storage**:
  * Projects are automatically saved as lightweight `.capslap.json` sidecar files next to your source video.
* 🖼️ **B-roll reel for audio episodes**: **B-roll Reel…** finds Creative Commons pictures and footage on Wikimedia Commons, Openverse, the Internet Archive and NASA for each stretch of the transcript, you accept or reject each, and it builds a 9:16 reel with credits on screen, a credits card at the end and a credits text for the episode description. Only CC0, public domain, CC BY and CC BY-SA are used.
* 🎬 **Multi-Format Video Rendering**:
  * Burn captions with one click into **9:16 (TikTok / Reels / Shorts)**, **1:1 (Square)**, **4:5 (Instagram)**, or **16:9 (YouTube)** with Apple VideoToolbox hardware encoding.
  * A smaller **proof copy** (720p or 540p) is encoded in the same pass as the full-size video: send the small one to be checked, publish the big one.
  * **Logo (bug)**: a logo in a corner of the render, for videos that don't carry one. Pick the image (a PNG with transparency is best), the corner, size and opacity once; turn it off for a video that has its own, and that video remembers it. It sits over the captions, stays off the intro and outro, and the preview shows it where the render puts it.
  * **Intro and outro clips**: pick a ready-made clip to play before the video, after it, or both (a channel ident, a "listen to the new episode" end card). They are scaled and padded to the output frame, keep their own sound (or get silence), and are joined in the same encode, proof copy included. The choice is remembered for later renders.

---

## 🚀 Quick Start

### Prerequisites
* **Python 3.12+** and [**uv**](https://github.com/astral-sh/uv)
* **Rust**: [rustup.rs](https://rustup.rs/)
* **FFmpeg** installed on your system (`brew install ffmpeg` on macOS)
* *Optional* — **libvoikko** for Finnish spell check in the caption table
  (`brew install libvoikko`). Without it the app runs exactly as before,
  just without the squiggles.

### Running PyCapSlap
```bash
# 1. Build the Rust core binary
cd rust
cargo build --release
cd ..

# 2. Launch the desktop application
uv run pycapslap
```

---

## 🧠 Local Orukeet Model

Open **Orukeet Settings** beside Transcribe and choose **Download / Repair Orukeet**. The app fetches the Q8 model and platform runtime, verifies their hashes, and saves them in the user's cache. The download requires an internet connection once; subsequent transcription runs locally without network access.

Orukeet's model and runtime installation details are documented in the [Orukeet repository](https://github.com/Oruk-AI/orukeet).

---

## 🧪 Development & Quality Assurance

PyCapSlap strictly follows a **Red-Green Test-Driven Development (TDD)** workflow.

```bash
# Run all Python Qt and model tests
uv run python -m pytest

# Run Rust core tests
cargo test --manifest-path rust/Cargo.toml

# Check linter and formatting
uv run ruff check .
uv run ruff format --check .
```

---

## 🤝 Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) — in particular, Windows/Linux
packaged builds are a wanted contribution (currently only macOS Apple
Silicon is built/released).

---

## 📜 License

MIT License. Built for creators and podcast producers.
