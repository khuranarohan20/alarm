from __future__ import annotations
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from alarm.models import Alarm, Recurrence
from alarm.store import AlarmStore
from alarm.scheduler import DaemonManager


def parse_days(days_str: str | None) -> tuple[Recurrence, list[str]]:
    if days_str is None:
        return Recurrence.ONCE, []
    if days_str == "daily":
        return Recurrence.DAILY, []
    if days_str == "weekdays":
        return Recurrence.WEEKDAYS, []
    if days_str == "weekends":
        return Recurrence.WEEKENDS, []
    valid = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
    parts = [d.strip() for d in days_str.split(",")]
    invalid = [d for d in parts if d not in valid]
    if invalid:
        raise ValueError(f"Invalid day(s): {', '.join(invalid)}. Use: mon,tue,wed,thu,fri,sat,sun")
    return Recurrence.CUSTOM, parts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="alarm", description="CLI alarm clock")
    sub = parser.add_subparsers(dest="command")

    p_add = sub.add_parser("add", help="Add a new alarm")
    p_add.add_argument("label", help="Alarm label")
    p_add.add_argument("time", help="Alarm time HH:MM (24h)")
    p_add.add_argument("--days", default=None,
                       help="Recurrence: daily|weekdays|weekends|mon,wed,fri (default: once)")
    p_add.add_argument("--snooze", type=int, default=5, metavar="N", help="Snooze minutes (default 5)")
    p_add.add_argument("--sound", default=None, metavar="PATH", help="Custom sound file")

    sub.add_parser("list", help="List all alarms")

    p_del = sub.add_parser("delete", help="Delete an alarm")
    p_del.add_argument("id", help="Alarm ID")

    for cmd in ("enable", "disable"):
        p = sub.add_parser(cmd, help=f"{cmd.capitalize()} an alarm")
        p.add_argument("id", help="Alarm ID")

    p_snooze = sub.add_parser("snooze", help="Snooze a firing alarm")
    p_snooze.add_argument("id", help="Alarm ID")
    p_snooze.add_argument("--minutes", type=int, default=None, help="Override snooze duration")

    p_exp = sub.add_parser("export", help="Export alarms to JSON")
    p_exp.add_argument("path", help="Output file path")

    p_imp = sub.add_parser("import", help="Import alarms from JSON")
    p_imp.add_argument("path", help="Input file path")

    p_daemon = sub.add_parser("daemon", help="Manage background daemon")
    p_daemon.add_argument("action", choices=["start", "stop", "status"])

    return parser


def run_cli(args: list[str] | None = None) -> None:
    parser = build_parser()
    ns = parser.parse_args(args)

    if ns.command is None:
        parser.print_help()
        return

    store = AlarmStore()
    daemon = DaemonManager()

    if ns.command == "add":
        try:
            recurrence, days = parse_days(ns.days)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        try:
            datetime.strptime(ns.time, "%H:%M")
        except ValueError:
            print("Error: time must be HH:MM (e.g. 07:30)", file=sys.stderr)
            sys.exit(1)
        alarm = Alarm(
            label=ns.label,
            time=ns.time,
            recurrence=recurrence,
            days=days,
            snooze_minutes=ns.snooze,
            sound=ns.sound,
        )
        alarm.next_fire = alarm.compute_next_fire()
        store.add(alarm)
        print(f"Added alarm '{alarm.label}' [{alarm.id[:8]}] — next fire: {alarm.next_fire:%Y-%m-%d %H:%M}")

    elif ns.command == "list":
        _print_list(store)

    elif ns.command == "delete":
        if store.delete(ns.id):
            print(f"Deleted alarm {ns.id}.")
        else:
            print(f"No alarm with id {ns.id}.", file=sys.stderr)
            sys.exit(1)

    elif ns.command in ("enable", "disable"):
        alarm = store.get(ns.id)
        if alarm is None:
            print(f"No alarm with id {ns.id}.", file=sys.stderr)
            sys.exit(1)
        alarm.enabled = (ns.command == "enable")
        store.update(alarm)
        print(f"Alarm {ns.id[:8]} {'enabled' if alarm.enabled else 'disabled'}.")

    elif ns.command == "snooze":
        alarm = store.get(ns.id)
        if alarm is None:
            print(f"No alarm with id {ns.id}.", file=sys.stderr)
            sys.exit(1)
        minutes = ns.minutes if ns.minutes is not None else alarm.snooze_minutes
        alarm.next_fire = (alarm.next_fire or datetime.now()) + timedelta(minutes=minutes)
        alarm.snoozed = True
        store.update(alarm)
        print(f"Snoozed for {minutes} min — next fire: {alarm.next_fire:%H:%M}")

    elif ns.command == "export":
        store.export(Path(ns.path))
        print(f"Exported to {ns.path}.")

    elif ns.command == "import":
        count = store.import_from(Path(ns.path))
        print(f"Imported {count} new alarm(s).")

    elif ns.command == "daemon":
        if ns.action == "start":
            daemon.start()
        elif ns.action == "stop":
            daemon.stop()
        elif ns.action == "status":
            print(f"Daemon: {daemon.status()}")


def _print_list(store: AlarmStore) -> None:
    from rich.console import Console
    from rich.table import Table
    alarms = store.load()
    console = Console()
    if not alarms:
        console.print("[dim]No alarms configured.[/dim]")
        return
    table = Table(title="Alarms", show_header=True)
    table.add_column("ID", style="dim", width=8)
    table.add_column("Label")
    table.add_column("Time")
    table.add_column("Recurrence")
    table.add_column("Next Fire")
    table.add_column("Status")
    for a in alarms:
        status = "✓" if a.enabled else "✗"
        if a.snoozed:
            status = "💤"
        nf = a.next_fire.strftime("%Y-%m-%d %H:%M") if a.next_fire else "—"
        rec = a.recurrence.value
        if a.recurrence == Recurrence.CUSTOM:
            rec = ",".join(a.days)
        table.add_row(a.id[:8], a.label, a.time, rec, nf, status)
    console.print(table)
