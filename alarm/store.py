from __future__ import annotations
import json
import logging
from pathlib import Path
from alarm.models import Alarm, alarm_to_dict, dict_to_alarm

logger = logging.getLogger(__name__)

DEFAULT_PATH = Path.home() / ".alarm" / "alarms.json"


class AlarmStore:
    def __init__(self, path: Path = DEFAULT_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> list[Alarm]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text())
            return [dict_to_alarm(d) for d in data]
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Corrupt alarm store, resetting: {e}")
            backup = self.path.with_suffix(".json.bak")
            self.path.rename(backup)
            return []

    def save(self, alarms: list[Alarm]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps([alarm_to_dict(a) for a in alarms], indent=2))
        tmp.rename(self.path)

    def add(self, alarm: Alarm) -> None:
        alarms = self.load()
        alarms.append(alarm)
        self.save(alarms)

    def delete(self, alarm_id: str) -> bool:
        alarms = self.load()
        new = [a for a in alarms if a.id != alarm_id]
        if len(new) == len(alarms):
            return False
        self.save(new)
        return True

    def get(self, alarm_id: str) -> Alarm | None:
        return next((a for a in self.load() if a.id == alarm_id), None)

    def update(self, alarm: Alarm) -> bool:
        alarms = self.load()
        for i, a in enumerate(alarms):
            if a.id == alarm.id:
                alarms[i] = alarm
                self.save(alarms)
                return True
        return False

    def export(self, path: Path) -> None:
        path.write_text(json.dumps([alarm_to_dict(a) for a in self.load()], indent=2))

    def import_from(self, path: Path) -> int:
        incoming = json.loads(path.read_text())
        existing_ids = {a.id for a in self.load()}
        new_alarms = [dict_to_alarm(d) for d in incoming if d["id"] not in existing_ids]
        for alarm in new_alarms:
            self.add(alarm)
        return len(new_alarms)
