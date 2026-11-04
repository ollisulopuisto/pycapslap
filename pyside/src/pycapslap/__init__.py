import sys
from pathlib import Path

# Ensure pyside root is in sys.path
pyside_root = Path(__file__).resolve().parent.parent.parent
if str(pyside_root) not in sys.path:
    sys.path.insert(0, str(pyside_root))


def main():
    import sys

    if sys.argv[1:2] == ["clips"]:
        from app.clip_workflow import render_clips

        status = render_clips(sys.argv[2:])
        if status:
            raise SystemExit(status)

    cli_subcommands = {"info", "transcribe", "edit", "render", "workflow"}
    if len(sys.argv) > 1 and (
        sys.argv[1] in cli_subcommands or sys.argv[1] in ("-h", "--help")
    ):
        from app.cli import run_cli

        status = run_cli(sys.argv[1:])
        raise SystemExit(status)

    from app.main import main as app_main

    return app_main()


__all__ = ["main"]
