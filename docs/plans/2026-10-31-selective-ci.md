# Selective CI Implementation Plan

**Goal:** Run only the CI jobs affected by a change while keeping cross-component checks for shared dependencies.

**Architecture:** Add one lightweight path-detection job to the existing CI workflow and use its outputs to gate the Rust, PySide, review, and portal test jobs. Move Ruff into a separate Ubuntu job so Python linting does not require a macOS runner. Keep the release and Pages workflows unchanged. Component paths include their manifests, shared workflow/scripts, and fixtures used across components.

**Tech Stack:** GitHub Actions, `dorny/paths-filter`, Rust, Ruff/pytest, Node, Docker.

---

### Task 1: Record the change-to-check mapping

**Files:**
- Create: `.github/workflows/ci.yml` path filters
- Document: `docs/plans/2026-10-31-selective-ci.md`

**Done.** Mapped Rust changes to Rust checks; Rust, PySide, and review fixture changes to PySide checks; review JavaScript changes to review checks; portal plus bundled review-page changes to portal checks. Python source/configuration changes run Ruff. Workflow changes run every CI job.

### Task 2: Gate independent CI jobs

**Done.** Added a detection job with `dorny/paths-filter@v3`; gated the component jobs on its outputs. Included `pull-requests: read` for pull request diff detection and full checkout history for push comparisons.

### Task 3: Validate and document

Validate workflow structure locally, document the path mapping in `CONTRIBUTING.md`, and use the first GitHub Actions run to confirm docs-only changes skip component jobs while representative Rust, PySide, review, and portal changes select the expected suites.
