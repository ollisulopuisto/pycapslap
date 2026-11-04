"""Console entry point for the PyCapSlap agent CLI bundle."""

import sys

from app.cli import run_cli


if __name__ == "__main__":
    raise SystemExit(run_cli(sys.argv[1:]))
