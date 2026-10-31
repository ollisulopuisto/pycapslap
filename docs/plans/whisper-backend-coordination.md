# Whisper Backend Coordination

**Goal:** Finish the selectable local Whisper backend and deliver a verified macOS DMG by 08:00 Helsinki time on 2026-10-30. The local artifact was completed and verified ahead of that deadline; hosted release follow-through is being finalized.

**Working tree:** Shared checkout at `/Users/dst/Documents/koodi/pycapslap`, branch `main`. Reviews were read-only; integrator changes below include their verified findings and fixes.

## Rust and runtime review

- Owner: Sol review agent
- Scope: `rust/src/whisper.rs`, `rust/src/captions.rs`, `rust/src/bin/core.rs`, restored whisper.cpp executable and dylibs.
- Check model download and output parsing behavior, cancellation, language defaults, dylib resolution in the `.app` layout, and any runtime blocker.
- Result: static review complete; no tests run. The integrator applied the release-relevant fixes.
  - **Minimum macOS mismatch:** `otool -l` reports `minos 15.0` for the CLI and versioned Whisper/Metal libraries. App metadata, README, and release documentation now consistently require macOS 15. CI uses a macOS 15 Apple Silicon runner.
  - **Download race/cancellation:** downloads use a unique partial file per invocation and an RAII drop guard, so cancellation removes only that request's temporary file. Model readiness checks file type and a 1 MB minimum; full cryptographic integrity verification remains future work.
  - **Temporary directory lifecycle:** one-shot generation now keeps extraction artifacts until rendering finishes; direct transcription retains its prior cleanup behavior.
  - **Diagnostics:** transcription errors include a bounded tail of Whisper stderr.
  - **Invocation/parsing:** extracted audio is 16 kHz mono PCM; absent/empty language becomes `auto`; requested flags exist in the restored CLI. The parser expects `transcription[].text` and unsigned millisecond `offsets.from/to`, skips malformed rows, and errors on an empty result. Full-JSON token timing is currently discarded (`words: Vec::new()`), so existing rendering falls back to evenly spaced words. A real transcription fixture was not exercised in this review.
  - **Bundle lookup:** current core location resolves to `Contents/Frameworks/rust/bin/whisper-cli-macos-arm64`; the explicitly injected `DYLD_LIBRARY_PATH` points at its existing `lib/libinternal`, containing every versioned dylib in the CLI's dependency list. Static lookup is consistent. Unversioned/old dylibs are also mixed in this directory; `libwhisper.dylib` references absent `libwhisper.coreml.dylib`, although the CLI uses the complete `libwhisper.1.dylib` instead.
  - **Diagnostics:** Whisper stderr is consumed only for progress and discarded; a model-load, Metal, language, or dyld failure is reduced to an exit status. Retain a bounded stderr tail in returned errors so release failures can be diagnosed.

## Packaging and DMG review

- Owner: second review agent
- Scope: `pyside/pycapslap.spec`, `docs/releasing.md`, `.github/workflows/release.yml`, `pyside/dist/PyCapSlap.app`.
- Check that a clean CI build includes the Whisper CLI and runtime libraries, that the Rust binary can locate them in the app bundle, and that the DMG can be staged with an `/Applications` alias.
- Result: initial review found **Release blocker:** `git ls-files rust/bin` was empty; a clean checkout had no Whisper runtime. The release change includes the 843,968-byte CLI and all 13 required dylibs (about 6.3 MB total), makes the spec fail on missing runtime files, and adds a bundled CLI `--help` smoke check to CI.
- The current local app contains `Contents/Frameworks/rust/bin/whisper-cli-macos-arm64` and `lib/libinternal` dylibs. The core's executable-relative lookup reaches this CLI, and it sets `DYLD_LIBRARY_PATH` to the adjacent `lib/libinternal`; the packaged CLI's `@rpath` also points to `Contents/Frameworks`, where PyInstaller collected its direct dylibs. This is a layout inspection, not an independent transcription test.
- The CI and local recipes stage the app beside an `/Applications` symlink. The new local DMG was mounted read-only and its contents verified.

## Integrator status

- Rust release build and `cargo check --release`: passed after final code changes.
- Python syntax compilation and `git diff --check`: passed.
- Bundled core `ping`: passed.
- Bundled Whisper CLI `--help` with packaged dylib path: passed.
- App metadata and Whisper CLI deployment target both report macOS 15.0.
- PyInstaller arm64 app bundle: built successfully; includes CLI, all 13 dylibs, and the Whisper MIT license.
- Final DMG created at `pyside/dist/PyCapSlap-macos-arm64.dmg` for tag `v26.10.30.2`; app metadata inside the mounted image reports version `26.10.30.2` and minimum macOS `15.0`.
- `hdiutil verify` checksum valid; mounted contents include `PyCapSlap.app` and `Applications -> /Applications`; cleanly detached.
- SHA-256: `e7e3a913d5072f12634b4ea73bf6df71558caeeff8a24430a7b0882a978de207`.
- Tag `v26.10.30.1` was a pre-rebase attempt, its queued workflow was cancelled, and the stale tag was removed. `v26.10.30.2` includes the newer remote bundle-version fix.
- Integrated `main` and tag `v26.10.30.2` are pushed. The hosted tagged workflow stayed queued, so it was cancelled and the locally built, verified DMG was published directly to the GitHub release.
- Release: <https://github.com/ollisulopuisto/pycapslap/releases/tag/v26.10.30.2>. Uploaded asset `PyCapSlap-macos-arm64.dmg` is 136,914,002 bytes; GitHub's SHA-256 `e7e3a913d5072f12634b4ea73bf6df71558caeeff8a24430a7b0882a978de207` matches the local file.
- No end-to-end audio transcription was run because no Whisper model was installed; CI currently smoke-checks the bundled CLI, not model inference.

## CI lint follow-up

- GitHub CI on 2026-10-30 found Ruff formatting drift in `settings_dialog.py` and Clippy `too_many_arguments` warnings on the new range-transcription functions.
- Reproduced both failures locally. Fixed Python formatting and grouped transcription inputs in `ExtractAndTranscribeParams`.
- Local `ruff check .`, `ruff format --check .`, and `cargo clippy --all-targets -- -D warnings` all pass after the fixes.
- Commit and remote CI rerun are pending.
