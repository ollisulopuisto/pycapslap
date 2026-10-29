# Whisper Backend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let users choose local Whisper as an alternative to Orukeet for transcription.

**Architecture:** Keep Orukeet as the default provider and route the selected backend through the existing Rust transcription RPC. Restore the local whisper.cpp execution path and model management from the pre-Orukeet implementation, adapting its request/result types to the current phrase and filler-aware schema. Put provider selection and Whisper model readiness in the GUI settings.

**Tech Stack:** PySide6, QSettings, Rust/Tokio, whisper.cpp CLI, existing FFmpeg audio extraction.

---

### Task 1: Restore the local Whisper transcription path

**Files:**
- Modify: `rust/src/transcription.rs`
- Create or restore: `rust/src/whisper.rs`
- Modify: `rust/src/lib.rs`
- Modify: `rust/src/types.rs`
- Modify: `rust/src/captions.rs`
- Modify: `rust/src/bin/core.rs`

Route a provider value through the current `transcribe` request. Keep Orukeet as the default for older sidecars/clients. For Whisper, run the bundled `whisper-cli`, use the selected local model, parse its timestamped JSON, and convert segments into the shared caption type. Surface missing binary/model errors directly and keep cancellation behavior.

### Task 2: Make the backend selectable in the GUI

**Files:**
- Modify: `pyside/app/views/caption_panel.py`
- Modify: `pyside/app/views/main_window.py`
- Modify: `pyside/app/views/settings_dialog.py`
- Modify: `pyside/app/core_client.py`

Persist `Orukeet` or `Whisper` in QSettings, default to Orukeet, and pass the selection with each transcription request. Show the current backend and expose model installation/status for Whisper. Leave filler/edited mode visible and enabled only when Orukeet is selected, since it relies on Orukeet's explicit filler-preservation option.

### Task 3: Package and document both backends

**Files:**
- Modify: `pyside/pycapslap.spec`
- Modify: `.github/workflows/release.yml`
- Modify: `README.md`
- Modify: `docs/releasing.md`
- Modify: `CHANGELOG.md`

Ensure the Whisper CLI and its runtime libraries are present in the packaged app, and document model download/storage behavior, provider choice, and the distinction between Orukeet's verbatim/edited mode and Whisper transcription.
