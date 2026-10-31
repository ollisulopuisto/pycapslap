# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Calendar Versioning](https://calver.org/) (`vYY.MM.DD.N`).

## [Unreleased]

### Added
- **App Nap awareness on macOS.** The editor holds a background-power assertion while a core call (transcription, render, export) is in flight, so hiding the window no longer lets App Nap throttle the editor's progress handling or starve the Rust core's pipe readers. Idle and paused states stay nappable; display and system sleep are unaffected.

## [v26.10.31.1] - 2026-10-31

### Fixed
- **CI lint checks pass for the Whisper transcription route.** Group transcription options into a request struct and format the Whisper settings list according to Ruff.

## [v26.10.30.2] - 2026-10-30

### Fixed
- macOS app bundle version fields now follow the release tag instead of the PyInstaller default `0.0.0`. Local builds use the latest version in this changelog.

### Packaging
- Fresh Apple Silicon release build includes the selectable local Whisper backend and corrected bundle version metadata.

## [v26.10.30.1] - 2026-10-30

### Added
- **Local Whisper as an alternative transcription backend.** Choose Orukeet or whisper.cpp in the caption panel; Orukeet remains the default. Whisper models can be downloaded from Transcription Settings.
- **Verbatim and edited caption styles.** Both styles remain available when Orukeet is selected; Whisper uses its native transcript output.

### Fixed
- **One-shot caption generation keeps its temporary files through rendering.** The extracted audio and timed transcript are now retained until caption render files have been written.
- **Whisper downloads and release packaging are more reliable.** Concurrent downloads use separate partial files, cancelled downloads clean up automatically, and CI refuses an incomplete Whisper runtime.

### Changed
- **Minimum macOS version is 15.0.** This matches the deployment target of the bundled whisper.cpp runtime.

## [v26.10.29.1] - 2026-10-29

### Fixed
- **Exports without a known duration show activity instead of 0%.** FFmpeg progress remains indeterminate until a percentage can be calculated.

### Changed
- **The macOS installer DMG includes an Applications shortcut** beside PyCapSlap.app for drag-and-drop installation.

## [v26.10.28.1] - 2026-10-28

### Changed
- **Rebuilt the macOS DMG from the latest released source.** This reissue contains the review-page URL validation shipped in v26.10.27.1.

## [v26.10.27.1] - 2026-10-27

### Fixed
- **Client-side XSS in the review page.** Assign the parsed, http(s)-validated URL to the `?back=` link's `href` instead of the raw query string, so untrusted input can no longer reach the link sink.

## [v26.10.26.4] - 2026-10-26

### Fixed
- **Orukeet model verification works in the packaged worker.** The worker now reads the artifact manifest from the installed Orukeet package.

## [v26.10.26.3] - 2026-10-26

### Fixed
- **Orukeet installation status follows its cache location.** The settings dialog now finds the installation receipt where the worker stores it on each platform.

### Added
- **Verbatim or edited transcription.** Choose whether Orukeet keeps filler words and repetitions or produces a cleaner transcript. Verbatim is selected by default.
- **Crop position.** When exporting to a shape the source does not share, crop can now be centred ("fill"), from the start (top/left, "start") or from the end (bottom/right, "end"). The editor offers all three in the crop combo, and the choice reaches the render and the caption placement.

## [v26.10.26.1] - 2026-10-26

### Changed
- **Local transcription now uses Orukeet.** The Whisper/OpenAI providers, model picker, inference code, build downloads, and bundled Whisper binaries are removed. Install Orukeet's verified Q8 model and native runtime from the settings dialog; one worker keeps the model loaded and processes transcripts locally. Captions keep Orukeet's phrase-level timestamps.

## [v26.10.22.2] - 2026-10-22

### Added
- **Crop or letterbox when the export has another shape.** Exporting a 9:16 video as 4:5 (or any shape the source does not have) now offers a choice: **Fit** keeps the whole frame with black bars, as before, and **Crop** fills the new shape and cuts the edges off, centred. The editor shows the crop, and the caption placement samples the same frame. The choice is kept between sessions, and it only appears when the shape changes.

## [v26.10.22.1] - 2026-10-22

### Fixed
- **The spell-check underline no longer crashes the caption table.** Misspelled words are underlined again, and a saved style keeps its own caption position rather than the template's.
- **The core no longer stalls after about twenty transcriptions.** Its error output is read, so it cannot fill the pipe and hang; the core starts faster, and closing it cleans up its processes.
- **Telemetry labels are kept alive,** so they are not destroyed while in use.
- **The development re-launch stays in the virtual environment,** even when a stale link is left in `.venv`.

## [v26.10.21.2] - 2026-10-21

### Changed
- **Long transcripts stay quick.** Editing a cue no longer re-measures every row of the caption table (2000 cues: seconds down to about 15 ms), the playhead finds its cue without scanning the list, spell-check results are cached per text, and the thumbnail preview scales the frame in two steps. The squiggle under a misspelled word is drawn again.
- **Frame scoring comes from the shared `framescore` package**, also used by YouThumber. The scoring rules and ranking weights are no longer copied in two places. Python 3.13 is now the minimum, because the package requires it.

### Added
- **A wider window, with the sidebar taking three parts to the preview column's two.** The window opens at 1060 px, so the caption list and its controls have room beside the 9:16 preview.
- **Suggested thumbnail frames, from Apple Vision (macOS).** Suggest frames samples the video every few seconds and scores the faces in each frame: Apple's own capture quality, sharpness, the expression (smile, open mouth, raised eyebrows) and the gesture (a raised hand, most of all a pointing one). The best frames appear as pictures under the thumbnail; picking one takes that frame and the time is saved in the sidecar. The scoring is the same as YouThumber's.
- **The sidecar keeps the thumbnail.** The `.capslap.json` file records which frame is the thumbnail (its time) and the headline. Opening the video takes that frame again and shows the headline.
- **Caption position is part of the style, and defaults to 75%.** A preset saves where the captions sit. Moving the position with no caption picked moves every caption, and loading a style moves them to its position. The thumbnail title is set in the caption style's font, colours, outline, glow and background box, at the same position.
- **The scrubber lines up with the timeline.** It spans the width of the timeline below, so both playheads sit in the same place. Play and Stop have icons, and the times show milliseconds, `mm:ss.mmm`, as the caption table does.
- **Thumbnails from the playhead.** Extract Thumbnail takes the frame under the playhead at full size. The thumbnail panel under the captions shows it with a title field of its own; the preview draws the title as it will be saved, and Save thumbnail… writes a PNG next to the video.
- **One button style across the window.** Buttons, chips and the format and proof menus share one height and one set of state colours, the menu arrows sit in their own slot, and the caption sidebar's controls are tighter, so the caption table is taller.
- **The top bar is shorter and Render has a share icon.** The export buttons are shorter tiles, the format and proof menus match their height, and menu arrows sit inside their tiles so they do not push the rows out of line.
- **The caption buttons are compact.** Add, Transcribe, Save, Auto Dodge and the others in the caption header are short buttons with a small icon beside the label, so the caption table gets the height.
- **The window opens tall, for vertical video.** Most footage is 9:16, so the window now opens 760 px wide and up to 900 px high, with the preview taking the height and the caption sidebar beside it. The top bar and the buttons are square tiles with icons, in three columns, and their colours show the state: lit when a mode is on, solid for Render, faded when an action is unavailable.
- **Long captions wrap in the sidebar.** A caption's text now wraps across lines in the table instead of running off the column, so the whole text is visible, and a word on a later line can be split off like any other.
- **Menus and standard shortcuts.** File, Edit, Video, View and Captions menus, with the usual Mac keys: Cmd+O opens a video, Cmd+S saves, Cmd+W closes, Cmd+Q quits, Cmd+, opens the transcription settings, Cmd+= / Cmd+- zoom the timeline and Cmd+0 fits it. Cmd+R renders, Cmd+T transcribes. Each item presses its button, so it does nothing while that button is disabled.
- **The buttons line up.** The top bar and the caption header are grids now, so each button sits in the same column as the one above it instead of wrapping where the window happens to end. The export and proof menus are dark like the buttons.
- **The timeline zooms, and has two edit tools.** Ctrl + scroll, or the + / − buttons, zoom in on the timeline, so a splice between two captions can be placed to the frame; Fit shows the whole video again. **Regular edit** (the default) moves only the caption whose edge is dragged. **Rolling edit** moves the splice between two touching captions: one grows as the other shrinks, and both stay in place otherwise.
- **A comma that ends a caption line is not shown.** Whisper's commas stay in the captions, so a later transcript merge brings them back, but the video shows a line without the comma when it ends the line or the caption. Periods are shown as before.
- **Caption length in the table, and captions whose time does not fit their text.** A Duration column shows each caption's length in seconds. Its reading speed is the characters it holds per second: above 20 a caption is flagged red (too fast for its text, shorten it or give it more time), below 4 amber (it lingers on the screen). The flag and the characters per second are in the cell's tooltip, and the cell follows the text and the timing as they change.

## [v26.10.20.1] - 2026-10-20

### Added
- **Split a caption where the speaker changes.** Whisper can put two speakers into one cue. Right-click a word in the caption table and choose **Split caption before “…”**: the cue is cut there, each half keeps its own word timings, and the cut is kept as a forced break. **Fix Orphans**, **Fix Syllables** and **Group Words** do not move words across a forced break, so a "ja" that ends one speaker's sentence stays with it. The break is saved in the sidecar as `breakAfter`; the renderer and the review portal ignore it.
- **In and Out set a caption's start and end from the playhead.** Two buttons beside Adjust words: **In** sets the active caption's start, **Out** its end, to the exact millisecond the playback is at. The active caption is the selected row, or the one under the playhead when none is selected. The time cells show milliseconds (`00:01.234`) so the value can be checked.
- **Captions can be dragged on the timeline.** Drag a caption's left or right edge to retime it, or its body to move it with its length kept. A caption stops at its neighbours, and its words are scaled with it. A click still selects and seeks as before; the drag starts only after a few pixels of movement.
- **Footage from NASA and the Internet Archive is laid out by its real shape.** Neither says how big a file is until it is downloaded, so the reel did not know whether to fill the frame or fit the picture, and an old 4:3 film was cropped from the middle. The size is now read from the downloaded file: a wide or square clip is fitted over a blurred copy of itself, a tall one fills the frame, and on a Mac the GPU can scale it. A file whose size cannot be read is fitted rather than cropped, since a fit loses nothing. The downloaded files are also kept apart by address rather than title, so two pictures with the same title from different sources no longer get each other's file.
- **The reel renders about twice as fast.** A still was fed in as a loop, so its file was decoded, scaled and (for a blurred fit) blurred again for every frame: a 12-megapixel photo cost 12 megapixels thirty times a second. It is now decoded and scaled once and the zoom makes all the frames out of that one picture, and a still is first shrunk to the size its place in the frame can use (a picture already small enough is left alone). A crossfade carries an alpha channel only while it fades, not for the whole shot, and the flattening of transparent pictures runs only for pictures whose pixel format can carry transparency (it had taken about 40 % of a render on photos that have none). Measured on three 4000×3000 photos at 1080×1920 in software, medians of three runs: cuts 22.8 → 9.3 s, crossfades 28.8 → 10.7 s, whip pans 25.3 → 9.7 s.
- **The reel moves.** Stills no longer all zoom in the same way: six Ken Burns moves (zoom in, zoom out, pan left, right, up, down) that cycle from shot to shot and always end exactly when the shot does. The shots arrive by a crossfade, a slide, or a whip pan (the old shot is pushed out to the left as the new one comes in from the right, with a sideways blur), mixed or one style for the whole reel, or by cuts; the choice is in the picker. A wide or square picture is fitted over a blurred, dimmed copy of itself instead of being cropped to 9:16; a tall one still fills the frame; **Layout** in the picker overrides it. Ctrl-click a second picture in the picker to stack two in one window, one over the other, each moving the opposite way. Transparent PNGs go dark where they are transparent rather than showing the waveform through. The credit of each picture in a stack shows together.
- **More sources for the B-roll picker.** Besides Wikimedia Commons, the picker now searches Openverse (Flickr and others; asked only for licences that allow commercial use and changes), the Internet Archive (video that is public domain, CC0, CC BY or CC BY-SA; asked for in the search itself, since the most downloaded films are often NC or ND) and NASA's image and video library (public domain). Results from the sources are interleaved, a source that is down costs nothing, and the same file from two is listed once. The Archive and NASA only name the file when asked, so it is looked up when the reel is built. The licence of Openverse and Archive items is what the uploader declared, so check a picture you are unsure of at its page link.
- **The review portal runs under Podman.** `portal/podman/` holds systemd user units (Quadlet) for the portal and Caddy, a Caddyfile and an example settings file, so the portal starts at boot without a Docker daemon and without root; the README has the four steps and the two one-time system settings rootless Podman needs to listen on 80 and 443. A test keeps the container name, port, network, volumes and settings file the units and the Caddyfile share in agreement.
- **Long episodes are transcribed a part at a time.** Transcribe on a recording over ten minutes no longer starts on the whole file, which kept every core busy for as long as the episode. It asks for a range first: play to where the part starts and press I, to where it ends and press O, and Transcribe covers just that part (the audio is cut out of the file before whisper sees it, so the rest costs nothing). The cues are placed at the right time among the ones already there, replacing only those inside the range, so an episode can be done in pieces over a day. A short recording, or one with marks, behaves as before. Loading a file never transcribed anything; this changes what the button does on a long one.
- **More of the macOS render runs on the GPU.** Encoding was already VideoToolbox; decoding and scaling now are too. The render decodes into VideoToolbox frames, scales them with `scale_vt` (fill or fit, to an exact even size computed from the source), and only then brings the picture to the CPU, because `ass` (the captions), `crop`, `pad` and `overlay` exist only for system memory. The proof copy is scaled on the GPU as well, and the intro and outro, the placement scan and the B-roll reel's clips decode on it. Attempts go from the whole pipeline to GPU decode only, to the hardware encoder alone, to software, each one handing over if it fails at start-up (a build without `scale_vt`, 10-bit or odd sources). HDR keeps its CPU tone-mapping. Look for `Starting encoder: VideoToolbox, GPU use: Pipeline` in the log. Not tested on a Mac yet.
- **B-roll reel from an audio episode.** **B-roll Reel…** searches Wikimedia Commons for pictures and footage that fit what is being said, window by window, and shows the candidates with thumbnails. Accept one per window or reject the window; nothing is chosen for you. Only CC0, public domain, CC BY and CC BY-SA are offered (NC is out because a podcast may earn money, ND because cropping to 9:16 and zooming modify the work). The reel is the episode audio as a waveform with the accepted footage over it, stills with a slow zoom, a credit line (title, author, licence, source) while each piece is on screen and every credit again on a closing card. Beside the reel go the captions (`.reel.mp4.capslap.json`, so the app can burn them as for any video) and `.reel.credits.txt` with links, for the episode description. Audio files (`m4a`, `mp3`, `wav`, `aac`, `flac`, `ogg`) now show in the open dialog. Search terms are plain frequent words, so Finnish inflected forms find little.
- **Post texts in the review portal.** Every video gets the title and text it is posted with on each service it goes to (YouTube, TikTok, Instagram, Facebook, LinkedIn, X; chosen per video on the admin page). Editor and client write and edit them beside the video; the client approves each one, and any change clears the approval. Every text is checked live against its service: length (X's own weighted count, links as 23), YouTube's title length, 15-hashtag cap and forbidden `<` `>`, Instagram's five hashtags, TikTok's 2200 for scheduling tools, and what shows before "more" on Instagram, Facebook and LinkedIn. Tabs show each service's state (empty, draft, approved, over a limit); a copy button per field for posting, and a new service's text can start from one already written.

### Fixed
- **Opening an audio file no longer ends in an error dialog.** The editor takes a first frame of every file it loads, and ffmpeg's "Output file does not contain any stream" came back as a dialog on every WAV or MP3. An audio file now gets a plain dark frame to draw captions on. **Render Video** on an audio file says there is no picture to put captions on and points to **B-roll Reel…**, instead of failing inside ffmpeg.
- **Toolbar buttons no longer lose their text.** The action bar above the video and the caption header were single rows that squeezed every button below its label width when the pane was narrow, cutting "Open Video" to "en Vide" and the like. Both are now rows that wrap onto another line when the buttons do not fit, each button keeping its natural size.
- The macOS test run could still segfault in `QTimerInfoList::activateTimers`, right after the test that loads a real video and closes the window. The window now releases its media player (stop, detach the video sink, clear the source) and stops its own timers when it closes, so the macOS backend has nothing left to fire into.
- **Caption lines no longer jump from word to word.** A karaoke caption is one cue per word, and libass wrapped each on its own; the highlighted word is set bigger and every window opens slightly stretched, so the same block broke into different lines from one word to the next. The line breaks are now decided once per caption block, with room for the biggest word highlighted and the stretch, balanced like libass's own wrap, and written into every window as forced breaks (`\N`, `\q2`). Plain captions get the same treatment against their bounce-in.
- Text is now measured the way libass sizes fonts: an ASS font size is the height of the font's Windows ascent + descent, not its em. Fonts with tall ascenders, such as Anton, set far narrower than the old em-based measure said, so their lines broke too early and justified lines came out narrow.
- The preview showed each caption twice: first the editor's own approximation in Qt fonts, a moment later libass's real rendering in a slightly different size and wrap. Now it shows only libass's rendering, and nothing while that is on its way. A dragged caption moves as its rendered image until the new position is rendered.
- Core replies now reach the window through a queued signal instead of `QTimer.singleShot` called from the core client's reader thread, which makes a timer object on that thread and hands it to the GUI's timer list; the macOS test run crashed inside that list (`QTimerInfoList::activateTimers`) with such timers pending.

### Added
- **Logo (bug).** A toolbar menu picks a logo image, its corner, size (8, 12 or 16 % of the frame's short side) and opacity, kept between sessions. *Put it on this video* is on by default and remembered per video, for sources that already carry a logo. The core lays it over the captioned video in the same ffmpeg graph (`burn` takes `watermark: { path, corner, sizePct, marginPct, opacity }`), under neither the intro nor the outro, so the proof copy has it too. The preview draws it at the render's position and size.
- **Review portal** (`portal/`): a FastAPI + SQLite server, run on your own machine or in Docker behind Caddy, for clients to review renders by series and episode. Each series has one secret link (a new one retires the old); an episode shows its videos with a player and a download button, opens the caption review page on each (whose new *Send to the editor* posts the fixes back as a new captions version), and collects free-form feedback, optionally at a moment in a video. The admin page lists series, links, episodes, every captions version and all feedback. In the app, **Client Review → Publish to Portal…** uploads a render and its captions into a series and episode, and **Import from Portal** applies the newest captions for the video, so corrections come in without files changing hands.
- **Intro and outro clips.** A toolbar menu next to the proof copy picks a ready-made clip to play before the captioned video, one to play after it, or both; the choice is kept between sessions. The clips are scaled and padded to the output frame at the video's frame rate, keep their own audio or get silence, and are concatenated in the same ffmpeg graph as the caption burn, so the proof copy has them too. Captions stay on the video itself. `burn` takes `introVideo` and `outroVideo`. The trim's `-t` is now an input option, so it limits the source only.
- **Password-locked review files.** The review page is public, so **Export for Review…** now locks the captions file with a password (AES-256-GCM, key from PBKDF2-SHA256 at 600 000 rounds), offering a generated one like `k7mq-x2fp-9tza-hw4c` to send the client separately; clearing it exports an unlocked file as before. The page asks for the password, keeps the unfinished review in the browser locked with it, and locks the reviewed file it downloads with it too. Importing tries the export's password first and asks only when that fails. The video is not locked: share it through a link that needs a login or a password. Adds the `cryptography` dependency.
- **Proof copy.** Rendering can write a smaller copy (720p or 540p on the short side; 720p by default, off in the new toolbar dropdown) next to the full-size video, for clients to proof while the full-size one is for publishing. It comes from the same ffmpeg pass: the burned frame is split and the copy scaled down and encoded alongside, so captions are drawn and the source decoded once. No copy is made when the video is no bigger than the proof. `burn` takes `proofShortSide` and answers with `proofVideo`.
- **Client review.** A static review page (`review/`, published to GitHub Pages) where a client opens the video and a captions file, watches with the captions drawn on the video, fixes wording and timing, comments on a caption, and downloads the reviewed file; nothing leaves their computer, and an unfinished review survives a closed tab. Finnish or English by the browser's language. Ctrl/⌘+Z undoes any edit on the page — text, times, comments, reverts — with typing in one box as one step, and Shift+Ctrl/⌘+Z or Ctrl+Y redoes. In the app, **Client Review → Export for Review…** writes the file to send, and **Import Reviewed Captions…** applies what comes back cue by cue — text through the same re-timing as editing in the table, times through the same clamped move, style and positions untouched — then lists the reviewer's comments next to their captions. A reviewed file is still a valid sidecar.

### Fixed
- The pyside tests no longer hang. The window opens a modal message box when the core reports an error, and in a test run nobody clicks it; which test froze depended on when the error arrived, so the hang looked random and two tests had been skipped for it. Message boxes are now recorded instead of shown in tests, and the two tests run again. The sample video the core and window tests need (git-ignored, so missing in CI) is generated with ffmpeg when absent. CI was also red on three clippy lints in `captions.rs` and four unformatted Python files.

### Added
- **I** and **O** set the trim's start and end at the playhead, as in video editors: stop playback on the right frame and mark it, no handle dragging. Marking a start past the current end (or an end before the start) lets the other side go back to the video's own end (start). Text fields keep their letters. The same two marks are buttons next to Stop.
- A **Stop** button next to Play: it pauses and goes back to the start of the trim, so checking where the cut begins is one click. Playback stops by itself at the trim's end and shows its last frame; Play from there starts the trim over. Before, the player knew nothing of the trim and played the whole video.

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
- Native rewrite: PyCapSlap is now a PySide6 (Qt) desktop app backed by the Rust processing core.

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
- The CI/CD pipeline (`ci.yml`, `release.yml`) had not been updated after the rewrite to the native PySide6 + Rust app. Rewritten to lint/test the current code and package a standalone macOS build.

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
