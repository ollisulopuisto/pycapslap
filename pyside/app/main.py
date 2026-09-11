import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.views.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("CapSlap")
    app.setOrganizationName("CapSlap")

    window = MainWindow()
    window.show()

    # If a video was passed as CLI argument, load it immediately
    if len(sys.argv) > 1 and Path(sys.argv[1]).exists():
        window.load_video(str(Path(sys.argv[1]).resolve()))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
