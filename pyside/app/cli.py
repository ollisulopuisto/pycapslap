"""Command-line interface for headless / agent / LLM driven PyCapSlap workflows."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from app.api.workflow import (
    CapSlapSession,
    edit_captions,
    load_captions,
    save_captions,
)
from app.models.captions import STYLE_PRESETS


def _emit_json(data: Any) -> None:
    print(json.dumps(data, indent=2), flush=True)


def _emit_event(event_type: str, **kwargs: Any) -> None:
    payload = {"event": event_type, **kwargs}
    print(json.dumps(payload), flush=True)


def cmd_info(args: argparse.Namespace) -> int:
    video_path = Path(args.video).expanduser().resolve()
    if not video_path.is_file():
        err = f"Video file not found: {args.video}"
        if args.json:
            _emit_json({"error": err, "ok": False})
        else:
            print(f"Error: {err}", file=sys.stderr)
        return 1

    try:
        with CapSlapSession() as session:
            meta = session.probe(video_path)
            sidecar = Path(f"{video_path}.capslap.json")
            caption_count = 0
            has_captions = False
            style_info = None
            if sidecar.is_file():
                try:
                    caps = load_captions(sidecar)
                    has_captions = True
                    caption_count = len(caps.segments)
                    style_info = caps.style.to_dict()
                except Exception:
                    pass

            result = {
                "ok": True,
                "video": str(video_path),
                "duration": meta.get("duration"),
                "width": meta.get("width"),
                "height": meta.get("height"),
                "fps": meta.get("fps"),
                "audio": meta.get("audio"),
                "hasVideo": meta.get("video"),
                "sidecarExists": sidecar.is_file(),
                "sidecarPath": str(sidecar) if sidecar.is_file() else None,
                "hasFirstFrame": meta.get("hasFirstFrame", False),
                "hasCaptions": has_captions,
                "captionCount": caption_count,
                "style": style_info,
            }
            if args.json:
                _emit_json(result)
            else:
                print(f"Video: {video_path}")
                print(f"Sidecar: {sidecar if sidecar.is_file() else 'None'}")
                print(f"Captions: {caption_count} cues")
                if style_info:
                    print(
                        f"Style: font={style_info.get('fontName')} "
                        f"size={style_info.get('fontSize')} karaoke={style_info.get('karaoke')}"
                    )
            return 0
    except Exception as exc:
        if args.json:
            _emit_json({"error": str(exc), "ok": False})
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1


def cmd_transcribe(args: argparse.Namespace) -> int:
    video_path = Path(args.video).expanduser().resolve()
    if not video_path.is_file():
        err = f"Video file not found: {args.video}"
        if args.json:
            _emit_json({"error": err, "ok": False})
        else:
            print(f"Error: {err}", file=sys.stderr)
        return 1

    def progress_cb(status: str, prog: float) -> None:
        if args.json_events:
            _emit_event("progress", status=status, percent=round(prog * 100, 1))
        elif not args.json:
            print(f"[{round(prog * 100):3d}%] {status}", flush=True)

    try:
        with CapSlapSession() as session:
            if args.json_events:
                _emit_event(
                    "status",
                    status="starting_transcription",
                    backend=args.backend,
                    model=args.model,
                )
            captions = session.transcribe(
                video_path=video_path,
                backend=args.backend,
                model=args.model,
                keep_fillers=args.keep_fillers,
                start_ms=args.start_ms,
                end_ms=args.end_ms,
                language=args.language,
                clean_syllables=not args.no_clean_syllables,
                clean_orphans=not args.no_clean_orphans,
                group_phrases=args.group_phrases,
                progress_callback=progress_cb,
            )

            if args.preset:
                edit_captions(captions, preset=args.preset)

            out_path = (
                Path(args.out).expanduser().resolve()
                if args.out
                else Path(f"{video_path}.capslap.json")
            )
            save_captions(captions, out_path)

            result = {
                "ok": True,
                "video": str(video_path),
                "sidecarPath": str(out_path),
                "cueCount": len(captions.segments),
                "segments": [s.to_dict() for s in captions.segments],
            }

            if args.json_events:
                _emit_event("complete", **result)
            elif args.json:
                _emit_json(result)
            else:
                print(
                    f"Transcription complete: {len(captions.segments)} cues saved to {out_path}"
                )
            return 0
    except Exception as exc:
        if args.json_events:
            _emit_event("error", error=str(exc))
        elif args.json:
            _emit_json({"error": str(exc), "ok": False})
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1


def cmd_edit(args: argparse.Namespace) -> int:
    target_path = Path(args.target).expanduser().resolve()
    sidecar_path = target_path
    if not sidecar_path.name.endswith(".capslap.json"):
        sidecar_path = target_path.with_name(f"{target_path.name}.capslap.json")

    if not sidecar_path.is_file():
        err = f"Captions sidecar not found: {sidecar_path}"
        if args.json:
            _emit_json({"error": err, "ok": False})
        else:
            print(f"Error: {err}", file=sys.stderr)
        return 1

    try:
        captions = load_captions(sidecar_path)

        style_overrides = None
        if args.style_json:
            try:
                style_overrides = json.loads(args.style_json)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid --style-json: {e}")

        text_replacements = None
        if args.replace:
            text_replacements = {}
            for item in args.replace:
                if "=" in item:
                    old, new = item.split("=", 1)
                    text_replacements[old] = new

        segment_patches = None
        if args.patch_json:
            try:
                parsed = json.loads(args.patch_json)
                segment_patches = parsed if isinstance(parsed, list) else [parsed]
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid --patch-json: {e}")

        edited = edit_captions(
            captions,
            preset=args.preset,
            style_overrides=style_overrides,
            position_pct=args.position,
            clean_syllables=args.clean_syllables,
            clean_orphans=args.clean_orphans,
            group_phrases=args.group_phrases,
            trim_start_ms=args.trim_start,
            trim_end_ms=args.trim_end,
            text_replacements=text_replacements,
            segment_patches=segment_patches,
        )

        out_path = Path(args.out).expanduser().resolve() if args.out else sidecar_path
        save_captions(edited, out_path)

        result = {
            "ok": True,
            "sidecarPath": str(out_path),
            "cueCount": len(edited.segments),
            "style": edited.style.to_dict(),
            "segments": [s.to_dict() for s in edited.segments],
        }

        if args.json:
            _emit_json(result)
        else:
            print(
                f"Updated captions saved to: {out_path} ({len(edited.segments)} cues)"
            )
        return 0
    except Exception as exc:
        if args.json:
            _emit_json({"error": str(exc), "ok": False})
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1


def cmd_render(args: argparse.Namespace) -> int:
    video_path = Path(args.video).expanduser().resolve()
    if not video_path.is_file():
        err = f"Video file not found: {args.video}"
        if args.json:
            _emit_json({"error": err, "ok": False})
        else:
            print(f"Error: {err}", file=sys.stderr)
        return 1

    sidecar = (
        Path(args.captions).expanduser().resolve()
        if args.captions
        else video_path.with_name(f"{video_path.name}.capslap.json")
    )
    if not sidecar.is_file():
        err = f"Captions sidecar not found: {sidecar}. Please transcribe or specify --captions."
        if args.json:
            _emit_json({"error": err, "ok": False})
        else:
            print(f"Error: {err}", file=sys.stderr)
        return 1

    try:
        captions = load_captions(sidecar)
        formats = [args.format] if args.format else ["9:16"]

        def progress_cb(status: str, prog: float) -> None:
            if args.json_events:
                _emit_event("progress", status=status, percent=round(prog * 100, 1))
            elif not args.json:
                print(f"[{round(prog * 100):3d}%] {status}", flush=True)

        with CapSlapSession() as session:
            if args.json_events:
                _emit_event(
                    "status",
                    status="starting_render",
                    formats=formats,
                    crop=args.crop,
                )
            rendered = session.render(
                video_path=video_path,
                captions=captions,
                formats=formats,
                crop_strategy=args.crop,
                proof_short_side=args.proof,
                intro_video=args.intro,
                outro_video=args.outro,
                progress_callback=progress_cb,
            )

            result = {
                "ok": True,
                "video": str(video_path),
                "rendered": rendered,
            }

            if args.json_events:
                _emit_event("complete", **result)
            elif args.json:
                _emit_json(result)
            else:
                for item in rendered:
                    print(
                        f"Rendered [{item.get('format')}]: {item.get('captionedVideo')}"
                    )
                    if item.get("proofVideo"):
                        print(f"  Proof copy: {item.get('proofVideo')}")
            return 0
    except Exception as exc:
        if args.json_events:
            _emit_event("error", error=str(exc))
        elif args.json:
            _emit_json({"error": str(exc), "ok": False})
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1


def cmd_render_alpha(args: argparse.Namespace) -> int:
    """Render a captions sidecar alone as an alpha movie/sequence (no video)."""
    sidecar = Path(args.captions).expanduser().resolve()
    if not sidecar.is_file():
        err = f"Captions sidecar not found: {sidecar}"
        if args.json_events:
            _emit_event("error", error=err)
        elif args.json:
            _emit_json({"error": err, "ok": False})
        else:
            print(f"Error: {err}", file=sys.stderr)
        return 1

    try:
        width, height = (int(part) for part in args.size.lower().split("x"))
    except ValueError:
        err = f"Invalid --size {args.size!r}: expected WIDTHxHEIGHT, e.g. 1080x1920"
        if args.json_events:
            _emit_event("error", error=err)
        elif args.json:
            _emit_json({"error": err, "ok": False})
        else:
            print(f"Error: {err}", file=sys.stderr)
        return 1

    try:
        captions = load_captions(sidecar)
        if args.preset:
            edit_captions(captions, preset=args.preset)
        if args.style_json:
            edit_captions(captions, style_overrides=json.loads(args.style_json))
        if args.position is not None:
            edit_captions(captions, position_pct=float(args.position))
        duration_ms = round(args.duration * 1000) if args.duration else None

        def progress_cb(status: str, prog: float) -> None:
            if args.json_events:
                _emit_event("progress", status=status, percent=round(prog * 100, 1))
            elif not args.json:
                print(f"[{round(prog * 100):3d}%] {status}", flush=True)

        with CapSlapSession() as session:
            if args.json_events:
                _emit_event(
                    "status",
                    status="starting_alpha_render",
                    size=f"{width}x{height}",
                    codec=args.codec,
                )
            rendered = session.render_alpha(
                captions=captions,
                width=width,
                height=height,
                fps=args.fps,
                duration_ms=duration_ms,
                output=args.out,
                codec=args.codec,
                progress_callback=progress_cb,
            )
            result = {
                "ok": True,
                "captions": str(sidecar),
                "rendered": rendered,
            }
            if args.json_events:
                _emit_event("complete", **result)
            elif args.json:
                _emit_json(result)
            else:
                print(f"Rendered [{rendered.get('codec')}]: {rendered.get('output')}")
            return 0
    except Exception as exc:
        if args.json_events:
            _emit_event("error", error=str(exc))
        elif args.json:
            _emit_json({"error": str(exc), "ok": False})
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1


def cmd_workflow(args: argparse.Namespace) -> int:
    """Run an end-to-end composite workflow: transcribe -> style/edit -> render."""
    video_path = Path(args.video).expanduser().resolve()
    if not video_path.is_file():
        err = f"Video file not found: {args.video}"
        if args.json:
            _emit_json({"error": err, "ok": False})
        else:
            print(f"Error: {err}", file=sys.stderr)
        return 1

    def progress_cb(status: str, prog: float) -> None:
        if args.json_events:
            _emit_event("progress", status=status, percent=round(prog * 100, 1))
        elif not args.json:
            print(f"[{round(prog * 100):3d}%] {status}", flush=True)

    try:
        with CapSlapSession() as session:
            if args.json_events:
                _emit_event("status", status="transcribing")
            captions = session.transcribe(
                video_path=video_path,
                backend=args.backend,
                model=args.model,
                keep_fillers=args.keep_fillers,
                language=args.language,
                clean_syllables=True,
                clean_orphans=True,
                progress_callback=progress_cb,
            )

            if args.preset:
                edit_captions(captions, preset=args.preset)

            sidecar_path = video_path.with_name(f"{video_path.name}.capslap.json")
            save_captions(captions, sidecar_path)

            if args.json_events:
                _emit_event("status", status="rendering")
            formats = [args.format] if args.format else ["9:16"]
            rendered = session.render(
                video_path=video_path,
                captions=captions,
                formats=formats,
                crop_strategy=args.crop,
                proof_short_side=args.proof,
                progress_callback=progress_cb,
            )

            result = {
                "ok": True,
                "video": str(video_path),
                "sidecarPath": str(sidecar_path),
                "cueCount": len(captions.segments),
                "rendered": rendered,
            }

            if args.json_events:
                _emit_event("complete", **result)
            elif args.json:
                _emit_json(result)
            else:
                print(
                    f"Workflow complete for {video_path}: {len(captions.segments)} captions burned."
                )
                for item in rendered:
                    print(
                        f"Rendered [{item.get('format')}]: {item.get('captionedVideo')}"
                    )
            return 0
    except Exception as exc:
        if args.json_events:
            _emit_event("error", error=str(exc))
        elif args.json:
            _emit_json({"error": str(exc), "ok": False})
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tekstitys",
        description="Tekstitys: Native video captioning, transcription, and render CLI/API.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # info
    p_info = subparsers.add_parser(
        "info", help="Probe video metadata and caption sidecar status"
    )
    p_info.add_argument("video", help="Path to video file")
    p_info.add_argument("--json", action="store_true", help="Emit output as JSON")

    # transcribe
    p_trans = subparsers.add_parser(
        "transcribe", help="Transcribe video audio to captions sidecar"
    )
    p_trans.add_argument("video", help="Path to video file")
    p_trans.add_argument(
        "--backend",
        choices=["whisper", "orukeet"],
        default="whisper",
        help="Transcription backend (default: whisper)",
    )
    p_trans.add_argument(
        "--model", default="tiny", help="Whisper model name (default: tiny)"
    )
    p_trans.add_argument(
        "--keep-fillers",
        action="store_true",
        help="Keep filler words (Orukeet backend)",
    )
    p_trans.add_argument(
        "--start-ms", type=int, help="Transcribe from start timecode (ms)"
    )
    p_trans.add_argument(
        "--end-ms", type=int, help="Transcribe until end timecode (ms)"
    )
    p_trans.add_argument("--language", help="Audio language code (e.g. 'en', 'fi')")
    p_trans.add_argument(
        "--no-clean-syllables",
        action="store_true",
        help="Do not auto-glue broken syllables",
    )
    p_trans.add_argument(
        "--no-clean-orphans",
        action="store_true",
        help="Do not apply orphan line rules",
    )
    p_trans.add_argument(
        "--group-phrases",
        action="store_true",
        help="Group word-level cues into phrases",
    )
    p_trans.add_argument(
        "--preset",
        choices=list(STYLE_PRESETS.keys()),
        help="Initial caption style preset",
    )
    p_trans.add_argument(
        "--out", help="Output path for .capslap.json (default: <video>.capslap.json)"
    )
    p_trans.add_argument("--json", action="store_true", help="Output result as JSON")
    p_trans.add_argument(
        "--json-events",
        action="store_true",
        help="Stream NDJSON progress and status events",
    )

    # edit
    p_edit = subparsers.add_parser(
        "edit", help="Edit and patch caption sidecars non-destructively"
    )
    p_edit.add_argument("target", help="Path to video or .capslap.json sidecar")
    p_edit.add_argument(
        "--preset", choices=list(STYLE_PRESETS.keys()), help="Apply style preset"
    )
    p_edit.add_argument(
        "--style-json", help="JSON dictionary of style overrides to apply"
    )
    p_edit.add_argument(
        "--position",
        type=float,
        help="Vertical anchor position percentage (0-100)",
    )
    p_edit.add_argument(
        "--clean-syllables",
        action="store_true",
        help="Run syllable merge pass",
    )
    p_edit.add_argument(
        "--clean-orphans",
        action="store_true",
        help="Run orphan prevention rules",
    )
    p_edit.add_argument(
        "--group-phrases",
        action="store_true",
        help="Group word-level cues into readable phrases",
    )
    p_edit.add_argument(
        "--replace",
        action="append",
        metavar="OLD=NEW",
        help="Replace text across all captions (e.g. --replace 'capslap=CapSlap')",
    )
    p_edit.add_argument(
        "--patch-json",
        help='JSON list of segment patches [{"index": 0, "text": "...", "startMs": ..., "endMs": ...}]',
    )
    p_edit.add_argument("--trim-start", type=int, help="Set trim start (ms)")
    p_edit.add_argument("--trim-end", type=int, help="Set trim end (ms)")
    p_edit.add_argument("--out", help="Output destination for edited sidecar")
    p_edit.add_argument("--json", action="store_true", help="Output result as JSON")

    # render
    p_render = subparsers.add_parser("render", help="Burn captions into video export")
    p_render.add_argument("video", help="Path to source video")
    p_render.add_argument("--captions", help="Path to .capslap.json sidecar file")
    p_render.add_argument(
        "--format",
        choices=["9:16", "1:1", "4:5", "16:9"],
        default="9:16",
        help="Export aspect ratio (default: 9:16)",
    )
    p_render.add_argument(
        "--crop",
        choices=["fill", "fit", "start", "end"],
        default="fill",
        help="Cropping strategy (default: fill)",
    )
    p_render.add_argument(
        "--proof",
        type=int,
        choices=[720, 540],
        help="Also export proof video with specified short-side resolution (720 or 540)",
    )
    p_render.add_argument("--intro", help="Optional intro bumper video path")
    p_render.add_argument("--outro", help="Optional outro bumper video path")
    p_render.add_argument("--json", action="store_true", help="Output result as JSON")
    p_render.add_argument(
        "--json-events",
        action="store_true",
        help="Stream NDJSON progress and status events",
    )

    # workflow
    p_work = subparsers.add_parser(
        "workflow",
        help="Run end-to-end captioning workflow: transcribe -> style -> render",
    )
    p_work.add_argument("video", help="Path to source video")
    p_work.add_argument("--backend", choices=["whisper", "orukeet"], default="whisper")
    p_work.add_argument("--model", default="tiny")
    p_work.add_argument(
        "--keep-fillers",
        action="store_true",
        help="Keep Orukeet filler words and repetitions",
    )
    p_work.add_argument("--language", help="Audio language code")
    p_work.add_argument(
        "--preset",
        choices=list(STYLE_PRESETS.keys()),
        default="oneliner",
        help="Caption style preset (default: oneliner)",
    )
    p_work.add_argument(
        "--format",
        choices=["9:16", "1:1", "4:5", "16:9"],
        default="9:16",
        help="Export aspect ratio (default: 9:16)",
    )
    p_work.add_argument(
        "--crop",
        choices=["fill", "fit", "start", "end"],
        default="fill",
        help="Cropping strategy (default: fill)",
    )
    p_work.add_argument(
        "--proof",
        type=int,
        choices=[720, 540],
        help="Generate proof video",
    )
    p_work.add_argument("--json", action="store_true", help="Output result as JSON")
    p_work.add_argument(
        "--json-events",
        action="store_true",
        help="Stream NDJSON progress and status events",
    )

    # render-alpha
    p_alpha = subparsers.add_parser(
        "render-alpha",
        help="Render captions alone (no video) as an alpha movie or PNG sequence",
    )
    p_alpha.add_argument(
        "--captions", required=True, help="Path to .capslap.json sidecar"
    )
    p_alpha.add_argument(
        "--size", required=True, help="Canvas as WIDTHxHEIGHT, e.g. 1080x1920"
    )
    p_alpha.add_argument(
        "--fps", type=float, default=25.0, help="Frames per second (default: 25)"
    )
    p_alpha.add_argument(
        "--duration", type=float, help="Length in seconds (default: last cue end)"
    )
    p_alpha.add_argument(
        "--codec",
        choices=["prores", "png"],
        default="prores",
        help="prores = ProRes 4444 .mov, png = RGBA frame sequence (default: prores)",
    )
    p_alpha.add_argument(
        "--out", required=True, help="Output .mov, or directory/%%05d-pattern for png"
    )
    p_alpha.add_argument(
        "--preset",
        choices=list(STYLE_PRESETS.keys()),
        help="Apply a style preset first",
    )
    p_alpha.add_argument("--style-json", help="Style overrides as JSON")
    p_alpha.add_argument("--position", help="Anchor position percent from top of frame")
    p_alpha.add_argument("--json", action="store_true", help="Output result as JSON")
    p_alpha.add_argument(
        "--json-events",
        action="store_true",
        help="Stream NDJSON progress and status events",
    )

    return parser


def run_cli(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "info":
        return cmd_info(args)
    elif args.command == "transcribe":
        return cmd_transcribe(args)
    elif args.command == "edit":
        return cmd_edit(args)
    elif args.command == "render":
        return cmd_render(args)
    elif args.command == "render-alpha":
        return cmd_render_alpha(args)
    elif args.command == "workflow":
        return cmd_workflow(args)
    else:
        parser.print_help()
        return 0
