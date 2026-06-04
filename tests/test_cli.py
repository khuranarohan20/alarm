import pytest
from alarm.cli import parse_days, build_parser
from alarm.models import Recurrence


def test_parse_days_none_returns_once():
    rec, days = parse_days(None)
    assert rec == Recurrence.ONCE
    assert days == []


def test_parse_days_daily():
    rec, days = parse_days("daily")
    assert rec == Recurrence.DAILY
    assert days == []


def test_parse_days_weekdays():
    rec, days = parse_days("weekdays")
    assert rec == Recurrence.WEEKDAYS


def test_parse_days_weekends():
    rec, days = parse_days("weekends")
    assert rec == Recurrence.WEEKENDS


def test_parse_days_custom():
    rec, days = parse_days("mon,wed,fri")
    assert rec == Recurrence.CUSTOM
    assert days == ["mon", "wed", "fri"]


def test_parse_days_invalid_raises():
    with pytest.raises(ValueError, match="Invalid day"):
        parse_days("mon,xyz")


def test_parser_has_add_subcommand():
    parser = build_parser()
    args = parser.parse_args(["add", "Wake up", "07:30"])
    assert args.command == "add"
    assert args.label == "Wake up"
    assert args.time == "07:30"


def test_parser_add_with_days():
    parser = build_parser()
    args = parser.parse_args(["add", "Gym", "06:30", "--days", "mon,wed,fri"])
    assert args.days == "mon,wed,fri"


def test_parser_add_with_snooze():
    parser = build_parser()
    args = parser.parse_args(["add", "Med", "08:00", "--days", "daily", "--snooze", "10"])
    assert args.snooze == 10


def test_parser_snooze_default_minutes():
    parser = build_parser()
    args = parser.parse_args(["snooze", "some-id"])
    assert args.minutes is None


def test_parser_daemon_start():
    parser = build_parser()
    args = parser.parse_args(["daemon", "start"])
    assert args.command == "daemon"
    assert args.action == "start"
