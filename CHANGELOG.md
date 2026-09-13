# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Calendar Versioning](https://calver.org/) (`vYY.MM.DD.N`).

## [Unreleased]

### Added
- Transcription settings dialog (⚙, next to Transcribe): choose local whisper.cpp vs. the OpenAI API, pick a local model size, and check/download it, all from the GUI. Local is preferred by default; OpenAI only used when explicitly selected with a key.
- "Apply to All" position button: sets one vertical position for every caption at once, replacing all per-caption overrides — also sidesteps a bug where re-chunked segments (e.g. after re-transcribing) could keep a stale position.
- Optional "BG Box" style toggle: a semi-transparent box behind caption text in the actual render (previously only ever shown in the editor preview, never burned in). Off by default; ASS can only draw square corners, not the preview's rounded pill.
- "2-Line" karaoke toggle (on by default): wraps karaoke captions onto two lines instead of forcing one, since single-line karaoke at a large font on portrait video could shrink to ~2 words per on-screen block.
- Safe zones (TikTok/Reels/Shorts) and Karaoke are now on by default for new projects.
- Render export filenames no longer collide: re-rendering the same video/format produces `name (2).mp4`, `name (3).mp4`, etc. instead of silently overwriting the previous export.
- Font picker menu now actually previews each entry in its own typeface instead of plain text that looked nothing like what got applied.

### Fixed
- Local whisper.cpp transcription was completely broken: the bundled `whisper-cli` binary and its dylibs had absolute rpaths baked in from the machine they were built on, and separately were compiled to require CoreML encoder files that were never generated (and had no non-CoreML fallback) — both silently fell through to the OpenAI API, surfacing only as "OpenAI API key not provided" with no other clue. Rebuilt without CoreML, rpaths fixed to be relocatable, and the previously-`.gitignore`d runtime dylibs are now committed so a fresh clone works too.
- Transcription progress bar never moved during local whisper.cpp transcription: the Rust core parsed whisper.cpp's stderr for "progress = N%" lines that are only printed when `--print-progress` is passed, which it never was.
- Transcription always split into one caption per word regardless of the karaoke setting, because `splitByWords` was hardcoded `true`; now tied to the karaoke toggle, giving whisper's natural phrase/sentence segments the rest of the time.
- Auto Dodge could place captions in the top half of the frame — often directly over a face — because its scoring only weighed "how calm do the pixels look," with no floor. Placement is now floored at the vertical midline by default.
- Render/Transcribe/Auto Dodge's portrait-vs-landscape default guess was silently always wrong (always landscape): the video's real width/height were never actually read into the project state (an empty probe dict was always passed to `load_video`). Now reads the real decoded frame or extracted thumbnail instead.
- The on-video caption preview used a font-name lookup that kept only the first word (e.g. "Montserrat Black" → "Montserrat", "THE BOLD FONT" → "THE"), so nearly every multi-word bundled font previewed as something else entirely — while the actual burned render always used the full, correct name.
- The style panel's outline-width setting was saved and displayed but never actually sent to the renderer, which always used a hardcoded 4px stroke regardless.
- Removed the blocking "Export Complete" dialog after rendering — it required a click to dismiss on every single export, which is pure friction when rendering several clips in a row; the status bar's completion message (with the output path) is enough.

### Added
- Automatic caption placement: one pass over the video scores every row for edge energy, texture and brightness, and each caption is assigned a height by a Viterbi pass that charges a penalty for moving relative to the previous caption — so captions avoid faces and burned-in text without jittering. Results land in the same manual overrides, so any of them can still be dragged.
- The caption position settings now dodge the selected platforms' interface. Whichever overlays are switched on, every position — bottom, bottom quarter, centre, top — is nudged vertically until the text clears them, taking the height of the block into account so a four-line storyteller caption is judged differently from a one-liner. A caption placed by hand is left exactly where it was put.
- Platform interface overlays in the position editor: toggle TikTok, Instagram Reels and YouTube Shorts to see, in their own colour, which parts of the frame each app covers with its own buttons and captions. Approximate by nature, and labelled as such. Whichever overlays are switched on are also treated as off limits by automatic placement, so it stops choosing a spot that looks best on the frame but that the app covers up.
- Recent videos on the start screen, with thumbnails, so a video being iterated on is one click away. Entries whose file has moved are dropped automatically.
- Caption text can now be edited from the position view: clicking a filmstrip frame reveals the matching segment, double-clicking opens it for editing.
- Caption position editor: a "Position" mode in the caption editor where captions can be dragged to a different height over a still of the video, with a filmstrip of every caption for jumping between them. Placements are optional, stored per time range, saved with the captions, and applied when burning. Timings are untouched.
- `generatePreviewFrame` gained `renderMode` (`video` / `clean` / `captions`) and `thumbnailHeight`, so the editor can composite a caption layer over a caption-free frame instead of re-rendering while dragging.

### Changed
- The caption filmstrip shows one frame per segment rather than one per on-screen block. Rendering splits a sentence into as many blocks as it takes to fit the frame — in karaoke that is a word or two each, which turned a minute of video into 28 near-identical thumbnails. Dragging one now moves the whole sentence, which is what was wanted from it anyway, and the strip lines up with the text list beside it.
- The terminal is quiet by default. Every RPC call, progress tick and rendered preview frame used to be printed — and a preview frame is hundreds of kilobytes of base64, printed three times over, which buried anything worth reading. Startup and failures are still shown; the rest, including FFmpeg's own output and the Rust core's tracing, now needs `CAPSLAP_DEBUG=1`, or `bun run dev:debug`.

### Fixed
- Exporting at "Original (Source)" could crawl to the point of looking frozen. A source whose shape is far from the target — a 4032x3024 phone video into 9:16 — needs a 4032x7168 canvas to avoid downscaling, most of it black bars and fourteen times the pixels of 1080p. VideoToolbox refuses a canvas that large, so the export silently fell back to software encoding. Canvases are now capped at the 4096-pixel edge H.264 encoders accept, keeping their shape, which puts hardware encoding back in play.
- A word that Whisper split across a segment boundary was drawn with a space in the middle of it — "KORKE ALLA" instead of "KORKEALLA". Whisper marks a new word with a leading space on the piece, but the merge that uses that signal runs per segment, so the halves arrived as separate words. The signal is now carried on each word and the halves are rejoined before layout, which also gives karaoke the whole word to highlight. Hits Finnish hard, where words are long and get split often.
- Words on a segment boundary were assigned to two segments at once: the ±100ms tolerance scanned ahead with a separate cursor and never consumed what it took, so the next segment collected the same words again. They showed up duplicated in the editor and rendered as two caption blocks on top of each other.
- Editing a caption's words left the position editor showing the render made before the edit. Its image cache was keyed on timing and style, and editing text changes neither.
- The caption editor could be pushed off screen: a flex child in the main layout had no `min-w-0`, so the filmstrip's intrinsic width — which grows with the length of the video — widened the whole row and pushed the text panel out of the window.
- `scripts/download-ffmpeg.sh` fetched an x86_64 FFmpeg on Apple Silicon (both architecture branches used the same Intel-only source), so the app skipped the bundled binary and fell back to whatever was on `PATH` — which since Homebrew split its formula is a slim build with no libass, and could not burn captions at all. It now downloads a static per-architecture build with libass, and verifies architecture and libass support before accepting a binary, existing ones included.
- Preview stills now show the caption that is actually on screen at the requested moment. Input seeking rebases timestamps to zero, so libass was looking for a cue at t=0 and usually drew nothing.
- "Top" and "Top quarter" caption positions rendered near the bottom of the frame: the top alignment measured its margin from the wrong edge.

## [v26.08.12.52] - 2026-08-12

### Fixed
- Fixed memory leaks and OOM connection drops in remote Whisper uploads by streaming audio files directly from disk instead of loading full file byte buffers into RAM.
- Improved error handling and surfacing for remote Whisper server connection drops and non-JSON error responses.

### Added
- Added `tokio-util` dependency with stream features for efficient async I/O streaming.
