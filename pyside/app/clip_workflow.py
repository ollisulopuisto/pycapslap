"""Run autoraffkat's timecoded vertical renderer before opening PyCapSlap."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse


def render_clips(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="pycapslap clips",
        description="Render timecoded vertical clips, then open them in PyCapSlap.",
    )
    parser.add_argument("video", help="local video path or file:// URL")
    parser.add_argument("--cuts", required=True, help="CSV with name,start,end columns")
    parser.add_argument("--output-dir")
    parser.add_argument("--autoraffkat", help="autoraffkat executable; defaults to PATH")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--center-crop", action="store_true",
                        help="skip face measurement and center-crop each clip")
    args = parser.parse_args(argv)

    parsed_source = urlparse(args.video)
    if parsed_source.scheme == "file" and parsed_source.netloc not in ("", "localhost"):
        parser.error("file URLs must refer to this Mac; remote file hosts are unsupported")
    if parsed_source.scheme not in ("", "file"):
        parser.error("video must be a local path or file:// URL")
    source_value = unquote(parsed_source.path) if parsed_source.scheme == "file" else args.video
    source = Path(source_value).expanduser()
    if not source.is_file():
        parser.error(f"video file not found: {args.video}")
    cuts = Path(args.cuts).expanduser()
    if not cuts.is_file():
        parser.error(f"cuts CSV not found: {cuts}")
    output = Path(args.output_dir).expanduser() if args.output_dir else (
        source.parent / f"{source.stem}-vertical-clips"
    )
    executable = args.autoraffkat or os.environ.get("AUTORAFFKAT") or shutil.which(
        "autoraffkat"
    )
    if not executable:
        print(
            "PyCapSlap clips needs autoraffkat on PATH. Install autoraffkat or pass "
            "--autoraffkat /path/to/autoraffkat.",
            file=sys.stderr,
        )
        return 2

    command = [
        executable, "render-clips", str(source.resolve()), "--cuts", str(cuts.resolve()),
        "--output-dir", str(output.resolve()),
    ]
    if args.overwrite:
        command.append("--overwrite")
    if args.center_crop:
        command.append("--center-crop")
    print("Running autoraffkat vertical renders…", flush=True)
    try:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
        )
    except OSError as exc:
        print(f"Could not start autoraffkat: {exc}", file=sys.stderr)
        return 2
    outputs: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="", flush=True)
        if line.startswith("OUTPUT\t"):
            outputs.append(line.rstrip("\r\n").split("\t", 1)[1])
    result = process.wait()
    if result:
        return result
    if not outputs:
        print("autoraffkat finished without reporting output clips.", file=sys.stderr)
        return 1

    # app.main() opens one document window per video argument.
    sys.argv[:] = [sys.argv[0], *outputs]
    return 0
