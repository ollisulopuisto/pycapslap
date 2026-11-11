import logging
import os
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Ensure pyside root is in sys.path when executed directly as `python app/main.py`
pyside_dir = Path(__file__).resolve().parent.parent
if str(pyside_dir) not in sys.path:
    sys.path.insert(0, str(pyside_dir))

from PySide6.QtGui import QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication

from app.views.main_window import MainWindow


def ensure_macos_app_name() -> bool:
    """Ensure the process name shown in macOS Dock, Menu Bar, and Cmd+Tab is Tekstitys.

    On macOS, unbundled processes display the executable binary basename in the
    Task Switcher (Cmd+Tab) and Dock. By ensuring a Mach-O executable named 'Tekstitys'
    exists and executing it, macOS registers the process under the name 'Tekstitys'.
    """
    if sys.platform != "darwin":
        return False

    if "PYTEST_CURRENT_TEST" in os.environ:
        return False

    if (
        os.environ.get("TEKSTITYS_REEXECED") == "1"
        or os.environ.get("TEKSTITYS_NO_REEXEC") == "1"
        or os.environ.get("PYCAPSLAP_REEXECED") == "1"
        or os.environ.get("PYCAPSLAP_NO_REEXEC") == "1"
    ):
        return False

    if os.path.basename(sys.executable) == "Tekstitys":
        return False

    try:
        real_py = os.path.realpath(sys.executable)
        real_bin_dir = os.path.dirname(real_py)
        toolchain_bin = os.path.join(real_bin_dir, "Tekstitys")

        if not os.path.exists(toolchain_bin):
            try:
                os.link(real_py, toolchain_bin)
            except OSError:
                shutil.copy2(real_py, toolchain_bin)
                os.chmod(toolchain_bin, 0o755)

        # On macOS (APFS/HFS+), filesystems are usually case-insensitive.
        # Placing 'Tekstitys' in .venv/bin would collide with the 'tekstitys' script.
        # Instead, we place the symlink in .venv/MacOS/Tekstitys, where Python
        # discovers .venv/pyvenv.cfg automatically (via grandparent directory).
        venv_root = Path(sys.prefix)
        venv_macos = venv_root / "MacOS"
        venv_macos.mkdir(parents=True, exist_ok=True)
        venv_tekstitys = venv_macos / "Tekstitys"
        try:
            # A stale link (e.g. left by a test's temp dir) must be replaced, or
            # the re-exec falls back to a Python outside the venv.
            if (
                venv_tekstitys.is_symlink()
                and os.readlink(venv_tekstitys) != toolchain_bin
            ):
                venv_tekstitys.unlink()
            if not venv_tekstitys.exists():
                os.symlink(toolchain_bin, str(venv_tekstitys))
        except OSError:
            pass

        target_bin = str(venv_tekstitys) if venv_tekstitys.exists() else toolchain_bin
        main_script = str(Path(__file__).resolve())
        args = [target_bin, main_script] + sys.argv[1:]
        env = os.environ.copy()
        env["TEKSTITYS_REEXECED"] = "1"
        if str(pyside_dir) not in env.get("PYTHONPATH", ""):
            existing_pythonpath = env.get("PYTHONPATH")
            env["PYTHONPATH"] = (
                f"{pyside_dir}:{existing_pythonpath}"
                if existing_pythonpath
                else str(pyside_dir)
            )
        if sys.prefix != sys.base_prefix:
            env["VIRTUAL_ENV"] = sys.prefix
        os.execve(target_bin, args, env)
        return True
    except Exception as e:
        logger.warning("Could not set macOS process name to Tekstitys: %s", e)
        return False


def _use_installed_default_font(app: QApplication) -> None:
    families = set(QFontDatabase.families())
    default = app.font()
    if default.family() in families:
        return
    for family in ("Helvetica Neue", "Segoe UI", "Noto Sans", "DejaVu Sans", "Arial"):
        if family in families:
            default.setFamily(family)
            app.setFont(default)
            return


def main():
    if sys.argv[1:] == ["--proofreading-smoke"]:
        from app.services.proofreading_smoke import smoke

        smoke()
        return
    ensure_macos_app_name()

    app = QApplication(sys.argv)
    app.setApplicationName("Tekstitys")
    app.setApplicationDisplayName("Tekstitys")
    app.setOrganizationName("Tekstitys")
    # Stylesheets resolve the default font's family; when it is the missing
    # "Sans Serif" alias Qt spends ~300 ms building its alias table on the
    # first styled widget. A family that exists skips that.
    _use_installed_default_font(app)

    icon_path = Path(__file__).resolve().parent / "resources" / "icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    videos = [Path(arg).resolve() for arg in sys.argv[1:] if Path(arg).is_file()]
    windows = []
    for video in videos or [None]:
        window = MainWindow()
        windows.append(window)  # Keep every queued document window alive.
        window.show()
        if video is not None:
            window.load_video(str(video))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
