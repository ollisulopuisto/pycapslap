# Timecoded Vertical Clips Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let a user pass one long video and timecoded ranges on the command line, render each range as a vertical clip with autoraffkat, then open the clips in PyCapSlap for caption editing and final export.

**Architecture:** PyCapSlap provides the orchestration command and writes a temporary synthetic FCPXML project containing the source video and requested ranges. Autoraffkat adds a headless render entry point that reuses its existing FCPXML reader, vertical framing, and MP4 renderer to produce one output per range. PyCapSlap accepts the rendered clip list and opens a review queue so each clip can be captioned in turn.

**Tech Stack:** Python 3.12, PySide6, existing `fcpxml` and autoraffkat render/reframe code, FFmpeg/AVFoundation.

---

### Task 1: Define and parse a timecode manifest

**Files:**
- Create: `pyside/app/services/clip_manifest.py`
- Test: `pyside/tests/test_clip_manifest.py`

Parse CSV rows with `name,start,end`; accept `HH:MM:SS.mmm`, `MM:SS.mmm`, or numeric seconds; reject invalid, negative, zero-length, overlapping/duplicate-name ranges with clear row errors; optionally validate against source duration.

### Task 2: Generate a temporary one-source FCPXML project

**Files:**
- Create: `pyside/app/services/autoraffkat_job.py`
- Test: `pyside/tests/test_autoraffkat_job.py`

Write one valid synthetic FCPXML per requested range (or an equivalent project encoding), referencing the original media and preserving source in/out precisely. Use a temporary workspace; never modify the source or persist intermediates in its folder.

### Task 3: Add autoraffkat headless vertical render support

**Files:**
- Modify: `../podcast/apps/autoraffkat/src/autoraffkat/__main__.py`
- Create: `../podcast/apps/autoraffkat/src/autoraffkat/cli_render.py`
- Tests: `../podcast/apps/autoraffkat/tests/`

Add an explicit headless render subcommand for a synthetic one-video project. Reuse the existing timeline reader, `Shot` generation, vertical reframe measurements when available, and `render_program`; emit deterministic output paths and line-oriented progress, and fail with nonzero status on an invalid project or render error.

### Task 4: Orchestrate rendering and launch PyCapSlap

**Files:**
- Modify: `pyside/pycapslap.py`
- Modify: `pyside/pyproject.toml`
- Modify: `pyside/app/main.py`
- Modify: `pyside/app/views/main_window.py`

Add `pycapslap clips <video> --cuts <manifest> --output-dir <dir>`. Run the autoraffkat headless renderer, show progress/errors in the terminal, then launch PyCapSlap with the completed clip list. Add a lightweight next/previous clip queue so the user can caption and review every generated clip from one app session.

### Task 5: Document the end-to-end workflow

**Files:**
- Modify: `README.md`
- Modify: `pyside/README.md`
- Modify: autoraffkat CLI documentation

Document manifest syntax, a complete command example, local video path support, output naming, framing behavior, prerequisites, and how the review queue advances between clips.

### Task 6: Validate both project members

Run focused manifest/FCPXML/render/queue checks, then the autoraffkat and PyCapSlap member suites and Ruff. Keep the synthetic render small and deterministic; do not run a real episode as a test.
