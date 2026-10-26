#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$ROOT_DIR/electron/resources/worker"
mkdir -p "$DIST_DIR"

uv run --project "$ROOT_DIR/pyside" --with pyinstaller pyinstaller \
  --noconfirm --clean --onefile --console --collect-all orukeet \
  --name orukeet-worker --distpath "$DIST_DIR" \
  --workpath "${TMPDIR:-/tmp}/capslap-orukeet-pyinstaller" \
  --specpath "${TMPDIR:-/tmp}/capslap-orukeet-spec" \
  "$ROOT_DIR/pyside/app/services/orukeet_worker.py"
