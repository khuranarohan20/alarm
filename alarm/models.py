from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import uuid

DAY_MAP = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


class Recurrence(str, Enum):
    ONCE = "once"
    DAILY = "daily"
    WEEKDAYS = "weekdays"
    WEEKENDS = "weekends"
    CUSTOM = "custom"


@dataclass
class Alarm:
    label: str
    time: str  # "HH:MM" 24h
    recurrence: Recurrence = Recurrence.ONCE
    days: list[str] = field(default_factory=list)
    enabled: bool = True
    snooze_minutes: int = 5
    snoozed: bool = False
    sound: str | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    next_fire: datetime | None = None
    created_at: datetime = field(default_factory=datetime.now)

    def compute_next_fire(self, from_dt: datetime | None = None) -> datetime:
        from_dt = from_dt or datetime.now()
        h, m = map(int, self.time.split(":"))
        candidate = from_dt.replace(hour=h, minute=m, second=0, microsecond=0)
        if candidate <= from_dt:
            candidate += timedelta(days=1)
        if self.recurrence in (Recurrence.ONCE, Recurrence.DAILY):
            return candidate
        if self.recurrence == Recurrence.WEEKDAYS:
            while candidate.weekday() >= 5:
                candidate += timedelta(days=1)
            return candidate
        if self.recurrence == Recurrence.WEEKENDS:
            while candidate.weekday() < 5:
                candidate += timedelta(days=1)
            return candidate
        # CUSTOM
        target = {DAY_MAP[d] for d in self.days}
        while candidate.weekday() not in target:
            candidate += timedelta(days=1)
        return candidate


def alarm_to_dict(alarm: Alarm) -> dict:
    return {
        "id": alarm.id,
        "label": alarm.label,
        "time": alarm.time,
        "recurrence": alarm.recurrence.value,
        "days": alarm.days,
        "enabled": alarm.enabled,
        "snooze_minutes": alarm.snooze_minutes,
        "snoozed": alarm.snoozed,
        "sound": alarm.sound,
        "next_fire": alarm.next_fire.isoformat() if alarm.next_fire else None,
        "created_at": alarm.created_at.isoformat(),
    }


def dict_to_alarm(d: dict) -> Alarm:
    return Alarm(
        id=d["id"],
        label=d["label"],
        time=d["time"],
        recurrence=Recurrence(d["recurrence"]),
        days=d.get("days", []),
        enabled=d.get("enabled", True),
        snooze_minutes=d.get("snooze_minutes", 5),
        snoozed=d.get("snoozed", False),
        sound=d.get("sound"),
        next_fire=datetime.fromisoformat(d["next_fire"]) if d.get("next_fire") else None,
        created_at=datetime.fromisoformat(d["created_at"]),
    )
