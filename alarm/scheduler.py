from __future__ import annotations
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from alarm.models import Recurrence
from alarm.notifier import notify
from alarm.store import AlarmStore

logger = logging.getLogger(__name__)

DEFAULT_DIR = Path.home() / ".alarm"


class DaemonManager:
    def __init__(
        self,
        pid_path: Path = DEFAULT_DIR / "daemon.pid",
        log_path: Path = DEFAULT_DIR / "daemon.log",
        store_path: Path = DEFAULT_DIR / "alarms.json",
    ) -> None:
        self.pid_path = pid_path
        self.log_path = log_path
        self.store_path = store_path
        for p in (pid_path.parent, log_path.parent):
            p.mkdir(parents=True, exist_ok=True)

    def status(self) -> str:
        if not self.pid_path.exists():
            return "stopped"
        try:
            pid = int(self.pid_path.read_text().strip())
        except ValueError:
            return "dead"
        return "running" if _process_alive(pid) else "dead"

    def start(self) -> None:
        if self.status() == "running":
            print("Daemon already running.")
            return
        log_file = open(self.log_path, "a")
        proc = subprocess.Popen(
            [sys.executable, "-m", "alarm.daemon_runner",
             str(self.store_path), str(self.pid_path)],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self.pid_path.write_text(str(proc.pid))
        print(f"Daemon started (PID {proc.pid}).")

    def stop(self) -> None:
        if self.status() != "running":
            print("Daemon is not running.")
            return
        pid = int(self.pid_path.read_text().strip())
        try:
            os.kill(pid, 15)  # SIGTERM
        except ProcessLookupError:
            pass
        self.pid_path.unlink(missing_ok=True)
        print("Daemon stopped.")


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _tick(store: AlarmStore) -> None:
    now = datetime.now()
    for alarm in store.load():
        if not alarm.enabled or alarm.next_fire is None:
            continue
        if alarm.next_fire <= now:
            try:
                notify(alarm)
            except Exception as e:
                logger.error(f"Failed to notify alarm {alarm.id}: {e}")
            if alarm.recurrence == Recurrence.ONCE:
                alarm.enabled = False
            else:
                alarm.next_fire = alarm.compute_next_fire(now)
            alarm.snoozed = False
            store.update(alarm)
