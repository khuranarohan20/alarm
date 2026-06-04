import sys
from alarm.cli import run_cli
from alarm.tui import run_tui


def main() -> None:
    if len(sys.argv) > 1:
        run_cli()
    else:
        run_tui()


if __name__ == "__main__":
    main()
