# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Calendar Versioning](https://calver.org/) (`vYY.MM.DD.N`).

## [Unreleased]

### Fixed
- The editor previewed the source frame while the render burned captions onto an export canvas chosen afterwards, in a dialog. For a 16:9 clip exported 9:16 that put the captions somewhere the preview never showed them — down in the padding. The export format is now a dropdown in the toolbar, it drives the layout, the rendered layer and the burn alike, and the editor draws the canvas that format produces: the video fitted inside it, the padding around it, the safe zones and the caption block measured against the whole frame. "Source" keeps the video's own frame and is the default. `previewLayout` takes the format and answers with the canvas it used, so the geometry is worked out in one place instead of being re-derived on the Python side.
- Until a frame had been decoded, the frame size was a guess and so was every layout computed from it, with nothing to correct it later. The canvas now says when the video's real size arrives and the layout is redone.

### Added
- Karaoke blocks are prefetched: when one window of a block comes up, the renderer is asked for every other window in it, at most three renders in flight. Playback and scrubbing within a block then show the burned pixels instead of falling back to the painted approximation.
- The preview is now libass's own output instead of a lookalike. Whenever the editor stands still — paused, scrubbed, restyled — it asks the renderer for the current cue as pixels, drawn from the same ASS document the burn writes, on a transparent canvas the size of the video frame, and composites that over the video. Playback and dragging keep the painted approximation, which costs nothing per frame. Two whole classes of divergence go away with it: the editor's font (Qt has no family called "Montserrat Black", so the preview had been drawing **Helvetica** and measuring line widths against it), and its second wrapping pass over lines the renderer had already broken and marked `\q2` — which could show a two-line justified cue as three.
- Justified lines were sized against the wrong typeface for seven of the fonts the picker offers. `find_font_file` matched a font file by its family and full name only, and fell back to *whatever file the directory listed first* when neither matched — so "Montserrat", "Roboto", "Poppins", "THE BOLD FONT", "Fredoka Light", "Raleway Thin" and "Merriweather Light 18pt" silently measured against another font, in the burned video as well as the preview, and flush lines came out not flush. Font files are now matched on the typographic family and PostScript name too (closest name first), because the style presets carry full names while the font menu shows the family Qt reports. Nothing matches, nothing is measured: an unknown font falls back to one plain line at the style's own size rather than to another font's glyph widths.
- The preview never showed the styled layout: two flush lines, the karaoke highlight, the per-line font size — all of it stayed invisible no matter what the style panel or preset said, and the canvas kept drawing its stand-in (one uppercased stream, wrapped, all white). The renderer answered correctly every time; the answer just never arrived. It lands on the core client's reader thread, and the hop back to the GUI thread used `QTimer.singleShot(0, callable)` — a timer created in a plain Python thread with no event loop, which never fires. Every other core callback in the window already used the three-argument form that queues onto a context object's thread; this one now does too.
- The editor preview and the burned-in render were two separate layout engines that agreed on almost nothing. The render used a font 1.78× larger (it scaled against a different reference frame), uppercased every caption where the preview did not, anchored the text block by its bottom edge where the preview centred it on the same line, and — worst — threw away the cues as authored: every word in the project was rejoined into one stream and re-cut on punctuation and pauses, so "Fix Syllables", the word shifts and every hand-made split never reached the video at all. The burn now uses one cue per authored segment (a syllable glued across a cue boundary still joins its word — half a word on screen is nobody's intent), and the preview no longer lays anything out: it asks the renderer for the layout and draws what it gets back, so the uppercasing, line breaks, per-line font size, highlighted word and vertical anchor all come from the code that writes the subtitle file.
- Captions could overflow the frame. Line breaking was a character-count estimate — `font_px * 0.5` in one place, `0.7` in another, `0.85` in a third — and automatic wrapping was switched off, so when the estimate ran under, the line simply ran off the edge. Text is now measured against the actual font file and wrapped on real metrics against one margin defined in one place.
- Shifting a word between cues with `◀ Shift Start` / `Shift End ▶` put a space in the middle of a word when what moved was a syllable: the cue text was rebuilt with a plain space join, ignoring the very "glue to previous" mark that "Fix Syllables" exists to act on.

### Added
- Justified caption style: two lines flush to the same width, each line's font size chosen so it fills the caption box — a short line renders large, a long one small, and the block reads as one solid rectangle. Available as the "Justified (Two Flush Lines)" preset or the "Justify" toggle in the style panel.
- Finnish spell check in the caption table (libvoikko): unknown words get a red squiggle, right-click offers corrections. Syllables split on purpose — a piece glued to the previous cue, a fragment ending in a hyphen — are not flagged, or a syllable-split transcript would be red end to end. Entirely optional: without `brew install libvoikko` nothing is flagged and the panel behaves exactly as before.
- Editable timecodes: the Start and End columns take `mm:ss.t`, `h:mm:ss.t` or a bare seconds count, clamped so a cue cannot cross its neighbours or collapse to nothing, with each cue's word timings scaled to match. `Alt`+`←`/`→` nudges the start by 100 ms, `Alt`+`Shift`+`←`/`→` the end, `Alt`+`Ctrl`+`←`/`→` the whole cue.
- Empty caption slots can be deleted. Shifting every word out of a cue used to leave a slot with no way to remove it; the time it occupied now goes to the cue before it — the one that just took its words — instead of becoming a silent gap.
- The transcription language can be chosen in the settings dialog (⚙) instead of always auto-detecting, which guesses wrong often enough on short clips.

## [v26.09.13.2] - 2026-09-13

### Fixed
- The v26.09.13.1 release build's bundled ffmpeg/ffprobe were x86_64-only (from evermeet.cx), silently non-functional on an Apple Silicon Mac without Rosetta 2 installed — PyInstaller copies files without executing them, so packaging "succeeded" while shipping a broken binary. Switched to Homebrew's arch-native `ffmpeg-full`.

## [v26.09.13.1] - 2026-09-13

### Changed
- Native rewrite: PyCapSlap is now a PySide6 (Qt) desktop app backed by the same Rust processing core, replacing the Electron/React frontend — see README for the performance comparison (memory, startup, scrub latency).

### Added
- Transcription settings dialog (⚙, next to Transcribe): choose local whisper.cpp vs. the OpenAI API, pick a local model size, and check/download it, all from the GUI. Local is preferred by default; OpenAI only used when explicitly selected with a key.
- "Apply to All" position button: sets one vertical position for every caption at once, replacing all per-caption overrides — also sidesteps a bug where re-chunked segments (e.g. after re-transcribing) could keep a stale position.
- Optional "BG Box" style toggle: a semi-transparent box behind caption text in the actual render (previously only ever shown in the editor preview, never burned in). Off by default; ASS can only draw square corners, not the preview's rounded pill.
- "2-Line" karaoke toggle (on by default): wraps karaoke captions onto two lines instead of forcing one, since single-line karaoke at a large font on portrait video could shrink to ~2 words per on-screen block.
- Safe zones (TikTok/Reels/Shorts) and Karaoke are now on by default for new projects.
- Render export filenames no longer collide: re-rendering the same video/format produces `name (2).mp4`, `name (3).mp4`, etc. instead of silently overwriting the previous export.
- Font picker menu now actually previews each entry in its own typeface instead of plain text that looked nothing like what got applied.
- A real downloadable build: `PyCapSlap.app` (macOS Apple Silicon) is now produced and attached to GitHub Releases, bundling the Rust core, ffmpeg/ffprobe, whisper.cpp and fonts into a standalone app — no repo checkout, `uv`, or Rust toolchain required to run it.

### Fixed
- Local whisper.cpp transcription was completely broken: the bundled `whisper-cli` binary and its dylibs had absolute rpaths baked in from the machine they were built on, and separately were compiled to require CoreML encoder files that were never generated (and had no non-CoreML fallback) — both silently fell through to the OpenAI API, surfacing only as "OpenAI API key not provided" with no other clue. Rebuilt without CoreML, rpaths fixed to be relocatable, and the previously-`.gitignore`d runtime dylibs are now committed so a fresh clone works too.
- Transcription progress bar never moved during local whisper.cpp transcription: the Rust core parsed whisper.cpp's stderr for "progress = N%" lines that are only printed when `--print-progress` is passed, which it never was.
- Transcription always split into one caption per word regardless of the karaoke setting, because `splitByWords` was hardcoded `true`; now tied to the karaoke toggle, giving whisper's natural phrase/sentence segments the rest of the time.
- Auto Dodge could place captions in the top half of the frame — often directly over a face — because its scoring only weighed "how calm do the pixels look," with no floor. Placement is now floored at the vertical midline by default.
- Render/Transcribe/Auto Dodge's portrait-vs-landscape default guess was silently always wrong (always landscape): the video's real width/height were never actually read into the project state (an empty probe dict was always passed to `load_video`). Now reads the real decoded frame or extracted thumbnail instead.
- The on-video caption preview used a font-name lookup that kept only the first word (e.g. "Montserrat Black" → "Montserrat", "THE BOLD FONT" → "THE"), so nearly every multi-word bundled font previewed as something else entirely — while the actual burned render always used the full, correct name.
- The style panel's outline-width setting was saved and displayed but never actually sent to the renderer, which always used a hardcoded 4px stroke regardless.
- Removed the blocking "Export Complete" dialog after rendering — it required a click to dismiss on every single export, which is pure friction when rendering several clips in a row; the status bar's completion message (with the output path) is enough.
- The CI/CD pipeline (`ci.yml`, `release.yml`) only ever built and released the old Electron app, never updated after the rewrite to this native PySide6 + Rust app — a tagged release would have shipped the wrong thing entirely. Rewritten to lint/test the actual current code and package a real standalone macOS build.

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
