import pytest
from pathlib import Path
from alarm.models import Alarm, Recurrence
from alarm.store import AlarmStore


@pytest.fixture
def tmp_store(tmp_path: Path) -> AlarmStore:
    return AlarmStore(tmp_path / "alarms.json")


@pytest.fixture
def sample_alarm() -> Alarm:
    from datetime import datetime
    a = Alarm(label="Test", time="07:30", recurrence=Recurrence.ONCE)
    a.next_fire = a.compute_next_fire(datetime(2026, 6, 4, 6, 0))
    return a
