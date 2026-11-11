# Tekstitys

Tekstitys is a desktop caption editor for video. Transcribe audio on your own
computer, correct words and timing, style captions over a video preview, and
export a video with the captions burned in. Projects use a `.capslap.json`
sidecar beside the source video, so editing captions does not overwrite the
original footage.

The desktop app uses Python/PySide6 for the editor and a Rust core for media and
caption processing. The repository also contains a browser caption-review page
and an optional self-hosted review portal.

## Install on a Mac

Packaged releases target **Apple Silicon and macOS 15 or later**. Windows and Linux
packaged apps are not currently provided; the export encoder uses Apple's
VideoToolbox. See [CONTRIBUTING.md](CONTRIBUTING.md) for portability work.

1. Open this repository's [Releases](../../releases) and download `Tekstitys.dmg`
   from the release you want.
2. Open it and copy Tekstitys to Applications.
3. Open a video. Use **Transcription Settings** to install/verify the selected
   local model and runtime before the first transcription.
4. Transcribe, check the cue text and timing, choose a style, then render.

Orukeet and whisper.cpp run locally after their downloads are installed. Setup
needs a network connection and enough disk space for the chosen model. Review
transcriptions before export, especially names, numbers and punctuation.

## Editing and export

- **Two transcription backends:** Orukeet with its verified Q8 model/runtime,
  including verbatim or edited output, and whisper.cpp with selectable models.
- **Cue editing:** text and timecode editing, keyboard timing nudges, shifting
  words between neighbouring cues, syllable repair and orphan-line cleanup.
  Local Punakynä/Voikko proofreading adds Finnish spelling and grammar suggestions; style advice is opt-in.
- **Preview and placement:** drag captions on the video, adjust their vertical
  anchor, view platform safe areas and use activity-based Auto Dodge placement.
  The preview uses the core's caption layout instead of separate line breaking.
- **Styles:** bundled fonts, saved show presets, uppercase/karaoke styling and
  a justified two-line layout that sizes each line to the caption box.
- **Trim and render:** timeline handles or I/O marks set the cut. Render 9:16,
  1:1, 4:5 or 16:9, with fit/crop choices and an optional smaller proof copy.
  Logo overlays and intro/outro clips are supported.
- **Audio episodes:** the B-roll Reel dialog can search public media sources,
  let you accept or reject assets and render a vertical reel with credits.
  Check each source's licence and attribution before publishing.
- **Automation:** `info`, `transcribe`, `edit`, `render` and `workflow` commands
  expose JSON results and NDJSON progress. See the [CLI/API reference](docs/api.md).

## Client review

There are two review routes; neither is required for local editing.

**File-based review:** use **Client Review → Export for Review…** to save a
password-locked caption file. Send the video and caption file to the reviewer,
with the password through a separate channel. They open both in the
[browser review page](review/README.md), edit text/timing, leave comments and
return the reviewed file. Import it with **Import Reviewed Captions…**.

The standalone page processes selected local files in the browser. Its draft and
returned caption file are password-locked, but **the video is not encrypted by
that lock**. Protect video sharing separately. URL-based media can require
network access. See [review/README.md](review/README.md) for hosting and formats.

**Review portal:** an optional server stores series, episodes, proof videos,
caption versions, feedback and social post texts. The app can publish a render
and import reviewed captions from it. A series link grants access to that series;
anyone holding the link can use it. Use HTTPS, protect the admin token and manage
who receives links. This route uploads content to your configured server.
Setup and deployment are in [portal/README.md](portal/README.md).

## Build from source

The supported development path is a Mac. You need Xcode command-line tools,
Python **3.13+**, [uv](https://docs.astral.sh/uv/), Rust/Cargo and FFmpeg with libass
for subtitle burning. The macOS helper uses Homebrew's `ffmpeg-full`, not the
plain FFmpeg package that may lack the needed subtitle filter.

```sh
git clone https://github.com/ollisulopuisto/tekstitys.git
cd tekstitys
TARGET_OS=macOS bash scripts/download-binaries.sh
cargo build --release --manifest-path rust/Cargo.toml
cd pyside
uv sync
uv run tekstitys
```

The helper installs/copies FFmpeg and ffprobe into `rust/bin/`. The application
finds the Rust core at `rust/target/release/core`. Model
installation is still a separate step in Transcription Settings.

For Finnish proofreading when running from source:

```sh
brew install libvoikko
```

Open a file directly or inspect it without opening the GUI:

```sh
# From pyside/
uv run tekstitys /path/to/video.mp4
uv run tekstitys info /path/to/video.mp4 --json
```

The packaged Mac app also includes a CLI:

```sh
"/Applications/Tekstitys.app/Contents/MacOS/TekstitysCLI" --help
```

For timecoded vertical clips, install `autoraffkat` separately and run
`uv run tekstitys clips interview.mp4 --cuts moments.csv`. It creates clips for
captioning in the editor. The [clip workflow guide](pyside/README.md#timecoded-vertical-clips)
has the CSV format and options; some older component names there still say
PyCapSlap.

## Privacy and security

Transcription does not require a cloud transcription service. Models and native
runtimes are downloaded first; subsequent model inference runs locally.

Other features do use the network: model/runtime downloads, optional B-roll
search/downloads and publishing to the review portal. Keep private footage out
of public asset searches and check what you upload. The sidecar contains
transcript text and project details; treat it as private along with the video.
A password-locked review export is not the same as encrypting the source project
or its media.

Do not commit API credentials, portal tokens, client footage or caption exports.
When filing a bug, use a small synthetic clip and remove private paths and text
from logs.

## Test and contribute

From the repository root:

```sh
uv run --project pyside python -m pytest pyside/tests
cargo test --manifest-path rust/Cargo.toml
uv run --project pyside ruff check .
uv run --project pyside ruff format --check .
node --test review/*.test.js
```

Qt tests need the appropriate graphical environment; macOS CI also tests native
framework paths. A successful source test is not proof that a packaged binary
starts or renders correctly. Smoke-test the bundled core and media tools too.

- [Contributing and packaging limits](CONTRIBUTING.md)
- [CLI/API reference](docs/api.md)
- [Review page](review/README.md)
- [Review portal](portal/README.md)
- [Changelog](CHANGELOG.md)
