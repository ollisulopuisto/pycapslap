# Contributing

## Good first contribution: Windows / Linux packaged builds

`.github/workflows/release.yml` currently only builds and releases a macOS
(Apple Silicon) `PyCapSlap.app`. Windows and Linux aren't built at all. If
you want to take this on:

**What exists already:**
- `rust/bin-win/whisper-cli.exe` is committed — Windows has a head start on
  the whisper.cpp binary. Linux has nothing bundled yet.
- `scripts/download-binaries.sh` has `download_windows()`/`download_linux()`
  functions already stubbed in, but unused and untested — the macOS path
  (`download_macos()`) is the one that's actually been exercised.
- `pyside/pycapslap.spec` (PyInstaller) bundles `rust/target/release/core`,
  `rust/bin/` (ffmpeg/ffprobe/whisper-cli + their runtime libs) and
  `rust/src/fonts/` — the same shape should carry over per platform, but the
  macOS-specific bits (`.icns` icon, `BUNDLE(...)` producing a `.app`) need
  a Windows (`.ico`, plain onedir/onefile `.exe`) and Linux (AppImage or
  plain dir, no bundle icon convention) equivalent.
- `core_client.py`/`fonts.py` already check `sys.frozen`/`sys._MEIPASS` for
  a packaged build, and the launcher sets `WHISPER_CLI_PATH`/`FFPROBE_PATH`/
  `CAPSLAP_FONTS_DIR`/`FFMPEG_PATH` explicitly rather than relying on the
  Rust core's own path-guessing — that part should already work cross-platform
  as long as the packaging script points those env vars at the right bundled
  files.

**What's missing, per platform:**
- **A real hardware video encoder path.** The Rust side currently assumes
  Apple VideoToolbox (see `rust/src/video.rs`, `HardwareEncoder`) — Windows
  needs an NVENC/QSV/AMF path, Linux needs VAAPI (or fall back to software
  x264, which works everywhere but is much slower).
- **A genuinely architecture-native ffmpeg + ffprobe** for that OS,
  statically built or with all its shared-library dependencies resolvable
  (this exact issue broke the very first macOS release, so verify by
  *running* the downloaded/bundled binary, not just checking its file type).
- A `download_windows()`/`download_linux()` rewrite mirroring whatever fix
  `download_macos()` ended up needing (see CHANGELOG v26.09.13.1 →
  v26.09.13.2: the first macOS release attempt bundled an x86_64-only
  ffmpeg build that silently doesn't run on Apple Silicon without Rosetta —
  the *build* succeeded because PyInstaller just copies files without
  executing them, so this class of bug won't show up until someone
  actually launches the packaged app. **Always smoke-test the packaged
  binaries themselves** — running them, not just checking their file type
  — before calling a release build done. See the `release.yml` build job's
  own "Smoke-test the bundled core binary" step for the pattern).
- CI: extend the `release.yml` build matrix, and ideally `ci.yml` too if
  there's a Windows/Linux-only code path worth testing.

## Good first contribution: pytest-qt tests in `test_main_window.py` hang

**This one isn't fully solved — read this before assuming a clean local
`uv run python -m pytest` run.** Two tests are already skipped
(`test_main_window_save_action`, `test_main_window_style_selection_and_sidecar`
— marked `@_skip_hangs`, an unconditional `pytest.mark.skip`, because they
reproducibly hang even run completely alone). But running the *rest* of
`test_main_window.py` together can still hang on a **different** test a
few tests later (observed hanging on `test_main_window_clean_sidebar_layout`,
which doesn't even touch `QMediaPlayer`) — so this isn't fully contained to
those two, and if a full `pytest` run of this file hangs for you, that's
this same issue, not a new one. CI is protected by `ci.yml`'s job-level
`timeout-minutes: 15` (the one mechanism that reliably cuts it off — see
below), but a local run has no such backstop; if it hangs, Ctrl+C and run
narrower (a single test or file at a time) instead of the whole suite.

What's been ruled out while chasing this:

- **Not the file content.** Tried both a handful of garbage bytes named
  `.mp4` (the original) and a real, valid decodable video — both hang the
  same way.
- **Not (only) cross-test state.** `test_main_window_save_action` hangs the
  same running completely alone as it does as part of the full suite — so
  whatever it's hitting isn't solely about state left over from earlier
  tests. That said, something sequence/accumulation-dependent is *also*
  going on, and it's **non-deterministic**: running the rest of the file
  after skipping the two known offenders can still hang, but not
  reliably on the same test — one run hung on
  `test_main_window_clean_sidebar_layout` (doesn't touch `QMediaPlayer` at
  all), a later run instead got past that one fine and hung on
  `test_main_window_progress_bar_and_empty_segments_on_load` instead. That
  smells like resource exhaustion (thread/handle/media-session count) from
  creating a real `MainWindow`+`QMediaPlayer` repeatedly in one process,
  which eventually — unpredictably — wedges *something*, rather than one
  specific test having a bug. Skipping individual tests can't fully fix a
  problem shaped like that; a session-scoped/reused `MainWindow` fixture
  (or mocking `QMediaPlayer` for tests that don't need a real one) probably
  would.
- **Not `QT_QPA_PLATFORM=offscreen` specifically** — it was tried as a fix,
  reproduced the same hang instead of avoiding it, so it's ruled out as
  the *cause* too (though it may still be a contributing factor alongside
  the real one).
- **The exact same sequence — create `MainWindow`, `load_video()` a bogus
  file, `set_caption_segments()`, `save_btn.click()`** — completes in well
  under a second in a bare Python script with no pytest and no `qtbot`
  involved at all. So it's specific to running under pytest (pytest-qt's
  fixture machinery, event-loop interaction, or something else pytest
  brings along), not to the app code itself.
- `pytest-timeout`'s per-test signal-based timeout (`pyproject.toml`,
  `timeout = 120`) does not reliably interrupt whatever it's actually
  blocked on — hence `ci.yml`'s job-level `timeout-minutes: 15` as the real
  backstop.

Properly isolating this (bisect what pytest-qt's `qtbot` fixture actually
does differently around widget teardown / event processing versus a plain
script, or mock `QMediaPlayer` for tests where a real one isn't the point)
would let these two run again instead of being skipped.

Happy to answer questions on any of this in an issue before you start.

## Local development

See the root `README.md` and `pyside/README.md` for running the app,
tests, and linters locally.
