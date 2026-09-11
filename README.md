# PyCapSlap (formerly CapSlap) ⚡

**PyCapSlap** is an AI video caption generator and editor that automatically transcribes audio, generates synchronized subtitles, and burns them into videos. **Works 100% offline** with local Whisper models.

Featuring a snappy native desktop GUI built with **PySide6 (Qt 6)** and a high-performance **Rust** processing core, PyCapSlap replaces the heavy Electron architecture with sub-millisecond video scrubbing and a -74% memory footprint.

---

## 🚀 Quick Start (Native PyCapSlap)

### Prerequisites
* **Rust**: https://rustup.rs/
* **Python 3.12+** & [**uv**](https://github.com/astral-sh/uv)
* **FFmpeg**

### Running PyCapSlap
```bash
# 1. Build the Rust core release binary
cd rust
cargo build --release
cd ..

# 2. Run the native desktop app directly with uv
uv run pycapslap
```

---

## 📦 Legacy Electron Application (Optional)

If you need the legacy Electron + React frontend:

1. **Install dependencies**: `cd electron && bun install`
2. **Run**: `bun run dev`

## Whisper Models (Local Transcription)

All transcription runs **100% locally** using whisper.cpp. Download models directly through the app UI, or manually:

```bash
mkdir -p rust/models

# Tiny model (fastest, 75 MB)
curl -L https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin \
  -o rust/models/ggml-tiny.bin

# Large v3 Turbo ⭐ RECOMMENDED (best speed/accuracy balance, 809 MB)
curl -L https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin \
  -o rust/models/ggml-large-v3-turbo.bin

# Base model (lightweight, 142 MB)
curl -L https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin \
  -o rust/models/ggml-base.bin

# Small model (466 MB)
curl -L https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin \
  -o rust/models/ggml-small.bin
```

**No API key required!** OpenAI API is available as an optional fallback if you prefer cloud transcription.

## Adding More Fonts

Additional fonts can be downloaded using the included script:

```bash
./scripts/download_fonts.sh
```

This downloads fonts from Google Fonts to `rust/src/fonts/`.

## Platform-Specific Notes

### macOS

FFmpeg is automatically downloaded during `bun install` via the postinstall script.
