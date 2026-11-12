# Tekstitys CLI & Programmatic API Reference

Tekstitys provides a headless CLI and Python API designed for automation, scripts, and LLM / AI agents to drive video captioning workflows without GUI automation.

## Command-Line Interface (CLI)

The CLI supports inspecting media, transcribing audio, editing caption sidecars, and rendering burned-in captions with structured output (`--json`) and NDJSON streaming progress events (`--json-events`).

In the macOS DMG build, run the bundled CLI directly:

```bash
"/Applications/Tekstitys.app/Contents/MacOS/TekstitysCLI" --help
```

For a source checkout, use `uv run tekstitys` from `pyside/` as shown below.

### 1. Inspect Video & Captions (`tekstitys info`)

Inspect video metadata and verify whether a `.capslap.json` sidecar exists:

```bash
# Human-readable output
uv run tekstitys info video.mp4

# Machine-readable JSON output
uv run tekstitys info video.mp4 --json
```

**JSON Output Format:**
```json
{
  "ok": true,
  "video": "/absolute/path/to/video.mp4",
  "duration": 123.4,
  "width": 1920,
  "height": 1080,
  "fps": 29.97,
  "audio": true,
  "hasVideo": true,
  "sidecarExists": true,
  "sidecarPath": "/absolute/path/to/video.mp4.capslap.json",
  "hasFirstFrame": true,
  "hasCaptions": true,
  "captionCount": 14,
  "style": {
    "templateId": "oneliner",
    "fontName": "Montserrat Black",
    "fontSize": 65,
    "karaoke": false
  }
}
```

---

### 2. Transcribe Audio (`tekstitys transcribe`)

Transcribe a video's audio track locally using Whisper or Orukeet:

```bash
uv run tekstitys transcribe video.mp4 \
  --backend whisper \
  --model tiny \
  --preset justified \
  --json-events
```

**Options:**
- `--backend [whisper|orukeet]`: Transcription backend (default: `whisper`).
- `--model [model_name]`: Whisper model name (`tiny`, `base`, `small`, etc.).
- `--keep-fillers`: Preserve filler words (Orukeet backend).
- `--start-ms <ms>` / `--end-ms <ms>`: Transcribe only a specific timecode range.
- `--language <code>`: Language code (e.g., `en`, `fi`).
- `--preset <preset>`: Apply initial style preset (`oneliner`, `karaoke`, `vibrant`, `storyteller`, `justified`).
- `--no-clean-syllables`: Disable automatic syllable re-gluing.
- `--no-clean-orphans`: Disable orphan line prevention rules.
- `--group-phrases`: Group word-by-word cues into phrase blocks.
- `--out <path>`: Custom output path for the `.capslap.json` sidecar.
- `--json`: Emit completed result as JSON.
- `--json-events`: Stream NDJSON event lines (`progress`, `status`, `complete`, `error`).

---

### 3. Edit & Patch Captions (`tekstitys edit`)

Manipulate caption sidecars non-destructively:

```bash
# Apply a style preset and shift position
uv run tekstitys edit video.mp4 --preset karaoke --position 80 --json

# Replace text terms across all segments
uv run tekstitys edit video.mp4 --replace "oldword=newword" --json

# Patch specific cues by index
uv run tekstitys edit video.mp4 \
  --patch-json '[{"index": 0, "text": "Corrected introductory sentence"}]' \
  --json
```

**Options:**
- `--preset <preset>`: Apply style preset.
- `--style-json <json>`: JSON dictionary of custom style field overrides (`{"fontSize": 70, "textColor": "#00ff00"}`).
- `--position <pct>`: Anchor position percentage from top of frame (0.0 to 100.0).
- `--clean-syllables`: Apply syllable re-gluing pass.
- `--clean-orphans`: Apply orphan prevention pass.
- `--group-phrases`: Group single words into phrases.
- `--replace "OLD=NEW"`: Text replacement across all cues (repeatable).
- `--patch-json <json>`: List of segment patches by index.
- `--trim-start <ms>` / `--trim-end <ms>`: Adjust timeline trim marks.

Trim values are timeline marks from the start of the source video. During render,
Tekstitys converts the saved end mark to the amount trimmed from the source's end.

---

### 4. Burn & Render Export (`tekstitys render`)

Render captioned videos with Apple VideoToolbox / hardware acceleration:

```bash
uv run tekstitys render video.mp4 \
  --format 9:16 \
  --crop fill \
  --proof 720 \
  --json-events
```

**Options:**
- `--captions <path>`: Path to `.capslap.json` sidecar (defaults to `<video>.capslap.json`).
- `--format [9:16|1:1|4:5|16:9]`: Target aspect ratio.
- `--crop [fill|fit|start|end]`: Cropping strategy.
- `--proof [720|540]`: Also encode a proof copy at specified resolution.
- `--intro <path>`: Intro video bumper path.
- `--outro <path>`: Outro video bumper path.
- `--json`: Output final render paths and dimensions as JSON.
- `--json-events`: Stream NDJSON progress events.

---

### 4b. Captions-Only Alpha Export (`tekstitys render-alpha`)

Render captions alone — no input video — as a straight-alpha movie for titles
and credits that get composited downstream (Autoraffkat, Final Cut):

```bash
uv run tekstitys render-alpha \
  --captions titles.capslap.json \
  --size 1080x1920 --fps 25 \
  --out titles.mov \
  --json-events
```

The captions are styled exactly like a burn (same sidecar, same presets) and
drawn by libass twice — on black and on white — with the alpha recovered per
pixel, so the output is a real straight-alpha movie: ProRes 4444
(`yuva444p10le`) or an RGBA PNG sequence.

**Options:**
- `--captions <path>`: `.capslap.json` sidecar (required).
- `--size <WxH>`: canvas in pixels, e.g. `1080x1920` (required — there is no video to inherit it from).
- `--fps <n>`: frames per second (default: 25).
- `--duration <s>`: length in seconds (default: end of the last cue).
- `--codec [prores|png]`: ProRes 4444 .mov, or an RGBA PNG sequence (default: prores).
- `--out <path>`: output .mov; for png, a directory (frames land in `frame_00001.png`…) or an explicit `card_%05d.png` pattern.
- `--preset <preset>`, `--style-json <json>`, `--position <pct>`: optional style edits applied before rendering, like `edit`.
- `--json`: Output final render info as JSON.
- `--json-events`: Stream NDJSON progress events.

Python: `CapSlapSession.render_alpha(captions, width, height, fps=25.0, duration_ms=None, output="alpha.mov", codec="prores")`.

---

### 5. Composite Workflow (`tekstitys workflow`)

Run the full end-to-end captioning workflow (transcribe -> clean/preset -> burn):

```bash
uv run tekstitys workflow video.mp4 \
  --backend whisper \
  --model tiny \
  --preset oneliner \
  --format 9:16 \
  --crop fill \
  --json
```

For Orukeet, pass `--keep-fillers` to retain filler words and repetitions in the
transcript. By default, the composite workflow omits them.

---

## Python Programmatic API

Import and drive headless workflows in Python:

```python
from app.api import CapSlapSession, load_captions, save_captions, edit_captions

with CapSlapSession() as session:
    # 1. Transcribe
    captions = session.transcribe(
        video_path="video.mp4",
        backend="whisper",
        model="tiny",
    )

    # 2. Edit & Style
    edit_captions(
        captions,
        preset="justified",
        position_pct=75.0,
        text_replacements={"capslap": "CapSlap"},
    )
    save_captions(captions, "video.mp4.capslap.json")

    # 3. Render
    rendered = session.render(
        video_path="video.mp4",
        captions=captions,
        formats=["9:16"],
        crop_strategy="fill",
    )
    print("Export created at:", rendered[0]["captionedVideo"])
```
