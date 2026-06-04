import os
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timedelta
import pytest
from alarm.models import Alarm, Recurrence
from alarm.store import AlarmStore
from alarm.scheduler import DaemonManager, _tick


@pytest.fixture
def daemon_mgr(tmp_path):
    return DaemonManager(
        pid_path=tmp_path / "daemon.pid",
        log_path=tmp_path / "daemon.log",
        store_path=tmp_path / "alarms.json",
    )


def test_status_stopped_when_no_pid_file(daemon_mgr):
    assert daemon_mgr.status() == "stopped"


def test_status_dead_when_pid_file_has_invalid_pid(daemon_mgr):
    daemon_mgr.pid_path.write_text("999999999")
    assert daemon_mgr.status() == "dead"


def test_double_start_is_noop(daemon_mgr):
    daemon_mgr.pid_path.write_text(str(os.getpid()))  # our own PID — alive
    with patch("alarm.scheduler.subprocess.Popen") as mock_popen:
        daemon_mgr.start()
        mock_popen.assert_not_called()


def test_stop_removes_pid_file(daemon_mgr):
    daemon_mgr.pid_path.write_text(str(os.getpid()))
    with patch("alarm.scheduler.os.kill"):
        daemon_mgr.stop()
    assert not daemon_mgr.pid_path.exists()


def test_tick_fires_due_alarm(tmp_path):
    store = AlarmStore(tmp_path / "alarms.json")
    alarm = Alarm(
        label="Due",
        time="07:00",
        recurrence=Recurrence.ONCE,
        next_fire=datetime.now() - timedelta(seconds=1),
        enabled=True,
    )
    store.add(alarm)
    with patch("alarm.scheduler.notify") as mock_notify:
        _tick(store)
        mock_notify.assert_called_once()
    updated = store.get(alarm.id)
    assert updated.enabled is False  # ONCE alarm disabled after firing


def test_tick_does_not_fire_disabled_alarm(tmp_path):
    store = AlarmStore(tmp_path / "alarms.json")
    alarm = Alarm(
        label="Off",
        time="07:00",
        recurrence=Recurrence.ONCE,
        next_fire=datetime.now() - timedelta(seconds=1),
        enabled=False,
    )
    store.add(alarm)
    with patch("alarm.scheduler.notify") as mock_notify:
        _tick(store)
        mock_notify.assert_not_called()


def test_tick_reschedules_daily_alarm(tmp_path):
    store = AlarmStore(tmp_path / "alarms.json")
    alarm = Alarm(
        label="Daily",
        time="07:00",
        recurrence=Recurrence.DAILY,
        next_fire=datetime.now() - timedelta(seconds=1),
        enabled=True,
    )
    store.add(alarm)
    with patch("alarm.scheduler.notify"):
        _tick(store)
    updated = store.get(alarm.id)
    assert updated.enabled is True
    assert updated.next_fire > datetime.now()
