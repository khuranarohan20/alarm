from datetime import datetime
import pytest
from alarm.models import Alarm, Recurrence, alarm_to_dict, dict_to_alarm


# ── Recurrence parsing ──────────────────────────────────────────────────────

def test_recurrence_values():
    assert Recurrence("once") == Recurrence.ONCE
    assert Recurrence("daily") == Recurrence.DAILY
    assert Recurrence("weekdays") == Recurrence.WEEKDAYS
    assert Recurrence("weekends") == Recurrence.WEEKENDS
    assert Recurrence("custom") == Recurrence.CUSTOM


# ── compute_next_fire ───────────────────────────────────────────────────────

BASE = datetime(2026, 6, 3, 6, 0)  # Wednesday 06:00 (2026-06-03 is a Wednesday)


def make(recurrence: Recurrence, days: list[str] | None = None) -> Alarm:
    return Alarm(label="x", time="07:30", recurrence=recurrence, days=days or [])


def test_once_fires_today_when_time_is_future():
    alarm = make(Recurrence.ONCE)
    nf = alarm.compute_next_fire(BASE)
    assert nf == datetime(2026, 6, 3, 7, 30)


def test_once_fires_tomorrow_when_time_has_passed():
    alarm = make(Recurrence.ONCE)
    after = datetime(2026, 6, 3, 8, 0)  # 08:00 on Wed, past 07:30
    nf = alarm.compute_next_fire(after)
    assert nf == datetime(2026, 6, 4, 7, 30)


def test_daily_same_as_once_when_future():
    alarm = make(Recurrence.DAILY)
    nf = alarm.compute_next_fire(BASE)
    assert nf == datetime(2026, 6, 3, 7, 30)


def test_weekdays_skips_weekend():
    # BASE is Wed; 07:30 not yet passed → today
    alarm = make(Recurrence.WEEKDAYS)
    nf = alarm.compute_next_fire(BASE)
    assert nf == datetime(2026, 6, 3, 7, 30)


def test_weekdays_from_friday_afternoon_skips_to_monday():
    alarm = make(Recurrence.WEEKDAYS)
    fri_afternoon = datetime(2026, 6, 5, 8, 0)  # Friday after 07:30 (Jun 3 Wed + 2 = Jun 5 Fri)
    nf = alarm.compute_next_fire(fri_afternoon)
    assert nf == datetime(2026, 6, 8, 7, 30)  # Monday


def test_weekends_from_wednesday_skips_to_saturday():
    alarm = make(Recurrence.WEEKENDS)
    nf = alarm.compute_next_fire(BASE)
    assert nf == datetime(2026, 6, 6, 7, 30)  # Saturday (Jun 3 Wed + 3 = Jun 6 Sat)


def test_custom_days_mon_wed_fri():
    alarm = make(Recurrence.CUSTOM, days=["mon", "wed", "fri"])
    nf = alarm.compute_next_fire(BASE)  # Wed 06:00, time 07:30 not yet passed
    assert nf == datetime(2026, 6, 3, 7, 30)  # today (Wednesday)


def test_custom_days_skips_to_next_match():
    alarm = make(Recurrence.CUSTOM, days=["mon", "fri"])
    nf = alarm.compute_next_fire(BASE)  # Wed → skip to Fri (Jun 5)
    assert nf == datetime(2026, 6, 5, 7, 30)  # Friday 2026-06-05


# ── Serialization ───────────────────────────────────────────────────────────

def test_round_trip_serialization(sample_alarm):
    d = alarm_to_dict(sample_alarm)
    restored = dict_to_alarm(d)
    assert restored.id == sample_alarm.id
    assert restored.label == sample_alarm.label
    assert restored.time == sample_alarm.time
    assert restored.recurrence == sample_alarm.recurrence
    assert restored.next_fire == sample_alarm.next_fire
    assert restored.snooze_minutes == sample_alarm.snooze_minutes
