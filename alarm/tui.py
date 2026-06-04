from __future__ import annotations
from datetime import datetime, timedelta
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Input, Label, ListItem, ListView, Select, Static
from textual.widget import Widget
from alarm.models import Alarm, Recurrence
from alarm.scheduler import DaemonManager
from alarm.store import AlarmStore

RECURRENCE_OPTIONS = [
    ("Once", "once"),
    ("Daily", "daily"),
    ("Weekdays (Mon–Fri)", "weekdays"),
    ("Weekends (Sat–Sun)", "weekends"),
    ("Custom days", "custom"),
]


def _humanize(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    delta = dt - datetime.now()
    total = int(delta.total_seconds())
    if total < 0:
        return "overdue"
    if total < 60:
        return f"in {total}s"
    if total < 3600:
        return f"in {total // 60}m"
    h, m = divmod(total // 60, 60)
    return f"in {h}h {m:02d}m" if m else f"in {h}h"


def _rec_label(a: Alarm) -> str:
    if a.recurrence == Recurrence.CUSTOM:
        return ",".join(a.days)
    return a.recurrence.value.upper()


class AlarmCard(Widget):
    DEFAULT_CSS = """
    AlarmCard {
        height: 4;
        margin: 0 2 1 2;
        padding: 0 2;
        background: #161b22;
        border-left: thick #30363d;
    }
    AlarmCard.active   { border-left: thick #58a6ff; }
    AlarmCard.snoozed  { border-left: thick #d29922; }
    AlarmCard.disabled { border-left: thick #484f58; }
    AlarmCard:focus    { background: #1c2128; border-left: thick #79c0ff; }
    """

    def __init__(self, alarm: Alarm) -> None:
        super().__init__(id=f"card-{alarm.id}")
        self.alarm = alarm
        self._apply_class()

    def _apply_class(self) -> None:
        for cls in ("active", "snoozed", "disabled"):
            self.remove_class(cls)
        if self.alarm.snoozed:
            self.add_class("snoozed")
        elif self.alarm.enabled:
            self.add_class("active")
        else:
            self.add_class("disabled")

    def update_alarm(self, alarm: Alarm) -> None:
        self.alarm = alarm
        self._apply_class()
        self.refresh()

    def render(self):
        from rich.text import Text
        from rich.console import Group
        a = self.alarm

        # ── row 1: label · time · recurrence · countdown ──────────────
        if a.snoozed:
            badge, badge_style = "💤 SNOOZED", "#d29922"
        elif a.enabled:
            badge, badge_style = "● ON ", "#3fb950"
        else:
            badge, badge_style = "○ OFF", "#484f58"

        top = Text(overflow="ellipsis", no_wrap=True)
        top.append(f" {a.label}", style="bold #e6edf3")
        top.append(f"  {a.time}", style="bold #58a6ff")
        top.append(f"  [{_rec_label(a)}]", style="#8b949e")
        countdown = _humanize(a.next_fire) if a.enabled else "—"
        top.append(f"  {countdown}", style="#3fb950" if a.enabled and not a.snoozed else "#484f58")
        top.append(f"   {badge}", style=badge_style)

        # ── row 2: meta ────────────────────────────────────────────────
        bot = Text(overflow="ellipsis", no_wrap=True)
        bot.append(f" snooze {a.snooze_minutes}min", style="dim #8b949e")
        if a.sound:
            bot.append(f"  · 🔊 custom", style="dim #8b949e")
        bot.append(f"  · {a.id[:8]}", style="dim #484f58")

        return Group(top, bot)


class HeaderBar(Static):
    DEFAULT_CSS = """
    HeaderBar {
        height: 3;
        background: #0d1117;
        border-bottom: solid #30363d;
        padding: 0 2;
        layout: horizontal;
        content-align: left middle;
    }
    """


class AddAlarmModal(ModalScreen):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    DEFAULT_CSS = """
    AddAlarmModal { align: center middle; }
    AddAlarmModal > Vertical {
        padding: 1 2;
        background: #161b22;
        border: solid #58a6ff;
        width: 62;
        height: auto;
    }
    AddAlarmModal Label {
        color: #8b949e;
        margin-top: 1;
    }
    AddAlarmModal Input {
        background: #0d1117;
        border: solid #30363d;
        color: #e6edf3;
    }
    AddAlarmModal Input:focus {
        border: solid #58a6ff;
    }
    AddAlarmModal Select {
        background: #0d1117;
        border: solid #30363d;
    }
    AddAlarmModal #buttons { margin-top: 1; height: 3; }
    AddAlarmModal Button { margin-right: 1; }
    """

    def __init__(self, existing: Alarm | None = None) -> None:
        super().__init__()
        self._existing = existing

    def compose(self) -> ComposeResult:
        a = self._existing
        title = "✏  Edit Alarm" if a else "＋  New Alarm"
        rec_val = a.recurrence.value if a else "once"
        days_val = ",".join(a.days) if a and a.days else ""
        with Vertical():
            yield Label(f"[bold #58a6ff]{title}[/bold #58a6ff]")
            yield Label("Label")
            yield Input(value=a.label if a else "", placeholder="Wake up", id="label")
            yield Label("Time  [dim](HH:MM, 24h)[/dim]")
            yield Input(value=a.time if a else "", placeholder="07:30", id="time")
            yield Label("Recurrence")
            yield Select(RECURRENCE_OPTIONS, id="recurrence", value=rec_val)
            yield Label("Custom days  [dim](only for Custom)[/dim]")
            yield Input(value=days_val, placeholder="mon,wed,fri", id="days")
            yield Label("Snooze  [dim](minutes)[/dim]")
            yield Input(value=str(a.snooze_minutes) if a else "5", placeholder="5", id="snooze")
            with Horizontal(id="buttons"):
                yield Button("Save" if a else "Add", variant="primary", id="add")
                yield Button("Cancel", variant="default", id="cancel")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_input_submitted(self, _: Input.Submitted) -> None:
        self._submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
        else:
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
        snooze = int(snooze_val) if snooze_val.isdigit() else 5
        if self._existing:
            self._existing.label = label
            self._existing.time = time_val
            self._existing.recurrence = recurrence
            self._existing.days = days
            self._existing.snooze_minutes = snooze
            self._existing.next_fire = self._existing.compute_next_fire()
            self._existing.snoozed = False
            self.dismiss(self._existing)
        else:
            alarm = Alarm(label=label, time=time_val, recurrence=recurrence,
                          days=days, snooze_minutes=snooze)
            alarm.next_fire = alarm.compute_next_fire()
            self.dismiss(alarm)


class AlarmApp(App):
    TITLE = "alarm"

    CSS = """
    Screen { background: #0d1117; }

    #topbar {
        height: 3;
        background: #0d1117;
        border-bottom: solid #21262d;
        padding: 0 2;
        layout: horizontal;
        content-align: left middle;
    }
    #topbar-title  { width: 1fr; color: #e6edf3; text-style: bold; }
    #topbar-next   { width: 2fr; content-align: center middle; color: #58a6ff; }
    #topbar-daemon { width: 1fr; content-align: right middle; }

    #list-area { height: 1fr; overflow-y: auto; padding: 1 0; }

    #empty-hint {
        content-align: center middle;
        height: 1fr;
        color: #484f58;
    }

    Footer {
        background: #161b22;
        color: #8b949e;
        border-top: solid #21262d;
    }
    Footer > .footer--key { color: #58a6ff; }
    """

    BINDINGS = [
        Binding("a",      "add_alarm",    "Add",          show=True),
        Binding("ctrl+e", "edit_alarm",   "Edit",         show=True),
        Binding("d",      "delete_alarm", "Delete",       show=True),
        Binding("e",      "toggle_alarm", "On/Off",       show=True),
        Binding("s",      "snooze_alarm", "Snooze",       show=True),
        Binding("j",      "cursor_down",  "Down",         show=False),
        Binding("k",      "cursor_up",    "Up",           show=False),
        Binding("q",      "quit",         "Quit",         show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.store = AlarmStore()
        self.daemon = DaemonManager()
        self._cursor: int = 0

    # ── Layout ──────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with Horizontal(id="topbar"):
            yield Static("⏰  alarm", id="topbar-title")
            yield Static("", id="topbar-next")
            yield Static("", id="topbar-daemon")
        with ScrollableContainer(id="list-area"):
            yield Static("No alarms yet — press [bold #58a6ff]a[/bold #58a6ff] to add one",
                         id="empty-hint")
        yield Footer()

    def on_mount(self) -> None:
        self._rebuild_cards()
        self.set_interval(1, self._tick_countdowns)
        self.set_interval(10, self._refresh_daemon_status)

    # ── Rendering ───────────────────────────────────────────────────────────

    def _rebuild_cards(self) -> None:
        alarms = self.store.load()
        container = self.query_one("#list-area", ScrollableContainer)
        container.remove_children()
        if not alarms:
            container.mount(Static(
                "No alarms yet — press [bold #58a6ff]a[/bold #58a6ff] to add one",
                id="empty-hint",
            ))
            self._cursor = 0
        else:
            self._cursor = min(self._cursor, len(alarms) - 1)
            for i, alarm in enumerate(alarms):
                card = AlarmCard(alarm)
                if i == self._cursor:
                    card.add_class("focused")
                container.mount(card)
        self._update_topbar(alarms)
        self._refresh_daemon_status()

    def _tick_countdowns(self) -> None:
        for card in self.query(AlarmCard):
            card.refresh()
        self._update_topbar(self.store.load())

    def _refresh_daemon_status(self) -> None:
        status = self.daemon.status()
        color = "#3fb950" if status == "running" else "#f85149"
        dot = "●" if status == "running" else "○"
        self.query_one("#topbar-daemon", Static).update(
            f"[{color}]{dot} daemon {status}[/{color}]"
        )

    def _update_topbar(self, alarms: list[Alarm]) -> None:
        active = [a for a in alarms if a.enabled and a.next_fire]
        if active:
            nxt = min(active, key=lambda a: a.next_fire)
            self.query_one("#topbar-next", Static).update(
                f"[dim]next:[/dim] [bold #e6edf3]{nxt.label}[/bold #e6edf3] "
                f"[#58a6ff]{_humanize(nxt.next_fire)}[/#58a6ff]"
            )
        else:
            self.query_one("#topbar-next", Static).update("[dim]no active alarms[/dim]")

    def _cards(self) -> list[AlarmCard]:
        return list(self.query(AlarmCard))

    def _focused_card(self) -> AlarmCard | None:
        cards = self._cards()
        return cards[self._cursor] if cards else None

    def _move_cursor(self, delta: int) -> None:
        cards = self._cards()
        if not cards:
            return
        for c in cards:
            c.remove_class("focused")
        self._cursor = (self._cursor + delta) % len(cards)
        cards[self._cursor].add_class("focused")
        cards[self._cursor].scroll_visible()

    # ── Key actions ─────────────────────────────────────────────────────────

    def action_cursor_down(self) -> None:
        self._move_cursor(1)

    def action_cursor_up(self) -> None:
        self._move_cursor(-1)

    def on_key(self, event) -> None:
        if event.key == "down":
            self._move_cursor(1)
        elif event.key == "up":
            self._move_cursor(-1)

    def action_add_alarm(self) -> None:
        def on_close(alarm: Alarm | None) -> None:
            if alarm:
                self.store.add(alarm)
                self._rebuild_cards()
        self.push_screen(AddAlarmModal(), on_close)

    def action_edit_alarm(self) -> None:
        card = self._focused_card()
        if not card:
            return
        alarm = self.store.get(card.alarm.id)
        if not alarm:
            return
        def on_close(updated: Alarm | None) -> None:
            if updated:
                self.store.update(updated)
                self._rebuild_cards()
        self.push_screen(AddAlarmModal(existing=alarm), on_close)

    def action_delete_alarm(self) -> None:
        card = self._focused_card()
        if card:
            self.store.delete(card.alarm.id)
            self._rebuild_cards()

    def action_toggle_alarm(self) -> None:
        card = self._focused_card()
        if card:
            alarm = self.store.get(card.alarm.id)
            if alarm:
                alarm.enabled = not alarm.enabled
                self.store.update(alarm)
                self._rebuild_cards()

    def action_snooze_alarm(self) -> None:
        card = self._focused_card()
        if card:
            alarm = self.store.get(card.alarm.id)
            if alarm:
                alarm.next_fire = (alarm.next_fire or datetime.now()) + timedelta(minutes=alarm.snooze_minutes)
                alarm.snoozed = True
                self.store.update(alarm)
                self._rebuild_cards()


def run_tui() -> None:
    AlarmApp().run()
