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
    from app.main import main as app_main

    return app_main()


__all__ = ["main"]
