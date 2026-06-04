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

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Add Alarm")
            yield Label("Label:")
            yield Input(placeholder="e.g. Morning standup", id="label")
            yield Label("Time (HH:MM 24h):")
            yield Input(placeholder="07:30", id="time")
            yield Label("Recurrence:")
            yield Select(RECURRENCE_OPTIONS, id="recurrence", value="once")
            yield Label("Custom days (mon,wed,fri) — only if Custom selected:")
            yield Input(placeholder="mon,wed,fri", id="days")
            yield Label("Snooze minutes:")
            yield Input(placeholder="5", id="snooze", value="5")
            with Horizontal(id="buttons"):
                yield Button("Add", variant="primary", id="add")
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
