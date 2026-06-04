from __future__ import annotations
from datetime import datetime, timedelta
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Select, Static
from alarm.models import Alarm, Recurrence
from alarm.scheduler import DaemonManager
from alarm.store import AlarmStore

RECURRENCE_OPTIONS = [
    ("Once", "once"),
    ("Daily", "daily"),
    ("Weekdays (Mon-Fri)", "weekdays"),
    ("Weekends (Sat-Sun)", "weekends"),
    ("Custom days", "custom"),
]


class AddAlarmModal(ModalScreen):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    CSS = """
    AddAlarmModal { align: center middle; }
    #dialog {
        padding: 1 2;
        background: $surface;
        border: thick $primary;
        width: 60;
    }
    Label { margin-bottom: 1; }
    Input { margin-bottom: 1; }
    #buttons { margin-top: 1; }
    """

    def __init__(self, existing: Alarm | None = None) -> None:
        super().__init__()
        self._existing = existing

    def compose(self) -> ComposeResult:
        a = self._existing
        title = "Edit Alarm" if a else "Add Alarm"
        rec_val = a.recurrence.value if a else "once"
        days_val = ",".join(a.days) if a and a.days else ""
        with Vertical(id="dialog"):
            yield Label(title)
            yield Label("Label:")
            yield Input(value=a.label if a else "", placeholder="e.g. Morning standup", id="label")
            yield Label("Time (HH:MM 24h):")
            yield Input(value=a.time if a else "", placeholder="07:30", id="time")
            yield Label("Recurrence:")
            yield Select(RECURRENCE_OPTIONS, id="recurrence", value=rec_val)
            yield Label("Custom days (mon,wed,fri) — only if Custom selected:")
            yield Input(value=days_val, placeholder="mon,wed,fri", id="days")
            yield Label("Snooze minutes:")
            yield Input(value=str(a.snooze_minutes) if a else "5", placeholder="5", id="snooze")
            with Horizontal(id="buttons"):
                yield Button("Save" if a else "Add", variant="primary", id="add")
                yield Button("Cancel", id="cancel")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        self._submit()

    def _submit(self) -> None:
        label = self.query_one("#label", Input).value.strip()
        time_val = self.query_one("#time", Input).value.strip()
        recurrence_val = str(self.query_one("#recurrence", Select).value)
        days_val = self.query_one("#days", Input).value.strip()
        snooze_val = self.query_one("#snooze", Input).value.strip()
        if not label or not time_val:
            return
        try:
            datetime.strptime(time_val, "%H:%M")
        except ValueError:
            return
        from alarm.cli import parse_days
        try:
            if recurrence_val == "custom":
                recurrence, days = parse_days(days_val or "mon")
            else:
                recurrence, days = parse_days(recurrence_val if recurrence_val != "once" else None)
        except ValueError:
            return
        if self._existing:
            self._existing.label = label
            self._existing.time = time_val
            self._existing.recurrence = recurrence
            self._existing.days = days
            self._existing.snooze_minutes = int(snooze_val) if snooze_val.isdigit() else 5
            self._existing.next_fire = self._existing.compute_next_fire()
            self._existing.snoozed = False
            self.dismiss(self._existing)
        else:
            alarm = Alarm(
                label=label,
                time=time_val,
                recurrence=recurrence,
                days=days,
                snooze_minutes=int(snooze_val) if snooze_val.isdigit() else 5,
            )
            alarm.next_fire = alarm.compute_next_fire()
            self.dismiss(alarm)


class AlarmApp(App):
    CSS = """
    DataTable { height: 1fr; }
    #status-bar { height: 1; background: $primary-darken-2; padding: 0 1; }
    """
    BINDINGS = [
        Binding("a", "add_alarm", "Add"),
        Binding("ctrl+e", "edit_alarm", "Edit"),
        Binding("d", "delete_alarm", "Delete"),
        Binding("e", "toggle_alarm", "Enable/Disable"),
        Binding("s", "snooze_alarm", "Snooze"),
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.store = AlarmStore()
        self.daemon = DaemonManager()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield DataTable(id="alarm-table")
        yield Static(id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#alarm-table", DataTable)
        table.add_columns("ID", "Label", "Time", "Recurrence", "Next Fire", "Status")
        self.refresh_table()
        self.set_interval(30, self.refresh_table)

    def refresh_table(self) -> None:
        table = self.query_one("#alarm-table", DataTable)
        table.clear()
        alarms = self.store.load()
        for a in alarms:
            status = "✓" if a.enabled else "✗"
            if a.snoozed:
                status = "💤"
            nf = a.next_fire.strftime("%Y-%m-%d %H:%M") if a.next_fire else "—"
            rec = a.recurrence.value
            if a.recurrence == Recurrence.CUSTOM:
                rec = ",".join(a.days)
            table.add_row(a.id[:8], a.label, a.time, rec, nf, status, key=a.id)
        daemon_status = self.daemon.status()
        color = "green" if daemon_status == "running" else "red"
        self.query_one("#status-bar", Static).update(
            f"[{color}]Daemon: {daemon_status}[/{color}]  [dim]{len(alarms)} alarm(s)[/dim]"
        )

    def _selected_alarm_id(self) -> str | None:
        table = self.query_one("#alarm-table", DataTable)
        if not table.row_count:
            return None
        row_key = table.get_row_at(table.cursor_row)[0]
        alarms = self.store.load()
        for a in alarms:
            if a.id.startswith(str(row_key)):
                return a.id
        return None

    def action_add_alarm(self) -> None:
        def on_close(alarm: Alarm | None) -> None:
            if alarm:
                self.store.add(alarm)
                self.refresh_table()
        self.push_screen(AddAlarmModal(), on_close)

    def action_edit_alarm(self) -> None:
        alarm_id = self._selected_alarm_id()
        if not alarm_id:
            return
        alarm = self.store.get(alarm_id)
        if not alarm:
            return
        def on_close(updated: Alarm | None) -> None:
            if updated:
                self.store.update(updated)
                self.refresh_table()
        self.push_screen(AddAlarmModal(existing=alarm), on_close)

    def action_delete_alarm(self) -> None:
        alarm_id = self._selected_alarm_id()
        if alarm_id:
            self.store.delete(alarm_id)
            self.refresh_table()

    def action_toggle_alarm(self) -> None:
        alarm_id = self._selected_alarm_id()
        if alarm_id:
            alarm = self.store.get(alarm_id)
            if alarm:
                alarm.enabled = not alarm.enabled
                self.store.update(alarm)
                self.refresh_table()

    def action_snooze_alarm(self) -> None:
        alarm_id = self._selected_alarm_id()
        if alarm_id:
            alarm = self.store.get(alarm_id)
            if alarm:
                alarm.next_fire = (alarm.next_fire or datetime.now()) + timedelta(minutes=alarm.snooze_minutes)
                alarm.snoozed = True
                self.store.update(alarm)
                self.refresh_table()

    def action_refresh(self) -> None:
        self.refresh_table()


def run_tui() -> None:
    AlarmApp().run()
