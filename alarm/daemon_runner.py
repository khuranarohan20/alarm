"""Entry point for the background daemon process."""
import logging
import sys
import time
from pathlib import Path
from alarm.scheduler import _tick
from alarm.store import AlarmStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

POLL_INTERVAL = 30  # seconds


def main() -> None:
    store_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / ".alarm" / "alarms.json"
    store = AlarmStore(store_path)
    while True:
        try:
            _tick(store)
        except Exception as e:
            logging.error(f"Tick error: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
