# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Calendar Versioning](https://calver.org/) (`vYY.MM.DD.N`).

## [Unreleased]

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
