import json
import pytest
from pathlib import Path
from alarm.models import Alarm, Recurrence
from alarm.store import AlarmStore


def test_load_returns_empty_list_when_file_missing(tmp_store):
    assert tmp_store.load() == []


def test_add_and_load(tmp_store, sample_alarm):
    tmp_store.add(sample_alarm)
    alarms = tmp_store.load()
    assert len(alarms) == 1
    assert alarms[0].id == sample_alarm.id
    assert alarms[0].label == "Test"


def test_delete_existing(tmp_store, sample_alarm):
    tmp_store.add(sample_alarm)
    removed = tmp_store.delete(sample_alarm.id)
    assert removed is True
    assert tmp_store.load() == []


def test_delete_missing_returns_false(tmp_store):
    assert tmp_store.delete("nonexistent-id") is False


def test_get_by_id(tmp_store, sample_alarm):
    tmp_store.add(sample_alarm)
    found = tmp_store.get(sample_alarm.id)
    assert found is not None
    assert found.id == sample_alarm.id


def test_get_missing_returns_none(tmp_store):
    assert tmp_store.get("no-such-id") is None


def test_update(tmp_store, sample_alarm):
    tmp_store.add(sample_alarm)
    sample_alarm.enabled = False
    result = tmp_store.update(sample_alarm)
    assert result is True
    assert tmp_store.get(sample_alarm.id).enabled is False


def test_update_missing_returns_false(tmp_store, sample_alarm):
    assert tmp_store.update(sample_alarm) is False


def test_atomic_write_does_not_leave_tmp_file(tmp_store, sample_alarm):
    tmp_store.add(sample_alarm)
    tmp_file = tmp_store.path.with_suffix(".tmp")
    assert not tmp_file.exists()


def test_malformed_json_starts_fresh(tmp_path):
    path = tmp_path / "alarms.json"
    path.write_text("not valid json")
    store = AlarmStore(path)
    alarms = store.load()
    assert alarms == []
    backup = tmp_path / "alarms.json.bak"
    assert backup.exists()


def test_export_and_import(tmp_store, sample_alarm, tmp_path):
    tmp_store.add(sample_alarm)
    export_path = tmp_path / "export.json"
    tmp_store.export(export_path)
    assert export_path.exists()

    other_store = AlarmStore(tmp_path / "other.json")
    count = other_store.import_from(export_path)
    assert count == 1
    assert other_store.get(sample_alarm.id).label == "Test"


def test_import_skips_duplicates(tmp_store, sample_alarm, tmp_path):
    tmp_store.add(sample_alarm)
    export_path = tmp_path / "export.json"
    tmp_store.export(export_path)
    count = tmp_store.import_from(export_path)
    assert count == 0  # already exists
    assert len(tmp_store.load()) == 1
