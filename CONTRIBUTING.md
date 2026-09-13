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

Happy to answer questions on any of this in an issue before you start.

## Local development

See the root `README.md` and `pyside/README.md` for running the app,
tests, and linters locally.
