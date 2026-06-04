from __future__ import annotations
from datetime import datetime, timedelta
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Input, Label, Select, Static
from textual.widget import Widget
from alarm.models import Alarm, Recurrence
from alarm.scheduler import DaemonManager
from alarm.store import AlarmStore

RECURRENCE_OPTIONS = [
    ("Once",              "once"),
    ("Daily",             "daily"),
    ("Weekdays (Mon–Fri)", "weekdays"),
    ("Weekends (Sat–Sun)", "weekends"),
    ("Custom days",       "custom"),
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _humanize(dt: datetime | None, enabled: bool = True) -> str:
    if not enabled or dt is None:
        return "—"
    delta = dt - datetime.now()
    total = int(delta.total_seconds())
    if total < 0:
        return "overdue"
    if total < 60:
        return f"{total}s"
    if total < 3600:
        return f"{total // 60}m"
    h, m = divmod(total // 60, 60)
    return f"{h}h {m:02d}m" if m else f"{h}h"


def _rec_label(a: Alarm) -> str:
    if a.recurrence == Recurrence.CUSTOM:
        return ",".join(a.days)
    return a.recurrence.value.upper()


# ── Alarm Card ────────────────────────────────────────────────────────────────

class AlarmCard(Widget):
    can_focus = False

    DEFAULT_CSS = """
    AlarmCard {
        height: 3;
        margin: 0 0 1 0;
        padding: 0 2;
        background: #161b22;
        border-left: thick #30363d;
    }
    AlarmCard.active   { border-left: thick #388bfd; }
    AlarmCard.snoozed  { border-left: thick #d29922; }
    AlarmCard.disabled { border-left: thick #30363d; }
    AlarmCard.selected { background: #1c2128; border-left: thick #79c0ff; }
    AlarmCard.selected.snoozed { border-left: thick #e3b341; }
    """

    def __init__(self, alarm: Alarm) -> None:
        super().__init__(id=f"card-{alarm.id}")
        self.alarm = alarm
        self._sync_classes()

    def _sync_classes(self) -> None:
        for cls in ("active", "snoozed", "disabled"):
            self.remove_class(cls)
        if self.alarm.snoozed:
            self.add_class("snoozed")
        elif self.alarm.enabled:
            self.add_class("active")
        else:
            self.add_class("disabled")

    def render(self):
        from rich.text import Text
        from rich.console import Group
        a = self.alarm

        countdown = _humanize(a.next_fire, a.enabled)

        if a.snoozed:
            status_icon, status_style = "💤", "#e3b341"
        elif a.enabled:
            status_icon, status_style = "●", "#3fb950"
        else:
            status_icon, status_style = "○", "#484f58"

        label_style  = "#e6edf3" if a.enabled else "#6e7681"
        time_style   = "#388bfd" if a.enabled else "#484f58"
        rec_style    = "#8b949e" if a.enabled else "#484f58"
        count_style  = "#3fb950" if (a.enabled and not a.snoozed) else ("#e3b341" if a.snoozed else "#484f58")

        # ── row 1: label  time  [REC]  countdown  status ──────────────
        row1 = Text(no_wrap=True, overflow="ellipsis")
        row1.append(f"{a.label:<22}", style=f"bold {label_style}")
        row1.append(f"{a.time}  ", style=f"bold {time_style}")
        row1.append(f"[{_rec_label(a):<10}]  ", style=rec_style)
        row1.append(f"{countdown:>8}  ", style=count_style)
        row1.append(status_icon, style=status_style)

        # ── row 2: meta ────────────────────────────────────────────────
        row2 = Text(no_wrap=True)
        row2.append(f"snooze {a.snooze_minutes}min", style="dim #6e7681")
        if a.sound:
            row2.append("  · 🔊 custom sound", style="dim #6e7681")
        row2.append(f"  ·  {a.id[:8]}", style="dim #30363d")

        return Group(row1, row2)


# ── Sidebar ───────────────────────────────────────────────────────────────────

class Sidebar(Widget):
    DEFAULT_CSS = """
    Sidebar {
        width: 24;
        background: #0d1117;
        border-right: solid #21262d;
        padding: 1 2;
    }
    """

    def __init__(self, store: AlarmStore, daemon: DaemonManager) -> None:
        super().__init__(id="sidebar")
        self._store = store
        self._daemon = daemon

    def compose(self) -> ComposeResult:
        yield Static("", id="sb-title")
        yield Static("", id="sb-divider-1")
        yield Static("", id="sb-next-label")
        yield Static("", id="sb-next-name")
        yield Static("", id="sb-next-time")
        yield Static("", id="sb-divider-2")
        yield Static("", id="sb-stats")
        yield Static("", id="sb-divider-3")
        yield Static("", id="sb-daemon")

    def on_mount(self) -> None:
        self.refresh_content()

    def refresh_content(self) -> None:
        alarms = self._store.load()
        active = [a for a in alarms if a.enabled and not a.snoozed]
        snoozed = [a for a in alarms if a.snoozed]
        off = [a for a in alarms if not a.enabled]

        self.query_one("#sb-title", Static).update(
            "[bold #e6edf3]⏰  alarm[/bold #e6edf3]"
        )
        self.query_one("#sb-divider-1", Static).update(
            "[#21262d]────────────────────[/#21262d]"
        )

        # next alarm
        upcoming = [a for a in alarms if a.enabled and a.next_fire]
        if upcoming:
            nxt = min(upcoming, key=lambda a: a.next_fire or datetime.max)
            self.query_one("#sb-next-label", Static).update("[dim #8b949e]NEXT ALARM[/dim #8b949e]")
            self.query_one("#sb-next-name", Static).update(
                f"[bold #e6edf3]{nxt.label[:18]}[/bold #e6edf3]"
            )
            self.query_one("#sb-next-time", Static).update(
                f"[#388bfd]⏱  {_humanize(nxt.next_fire)}[/#388bfd]"
            )
        else:
            self.query_one("#sb-next-label", Static).update("[dim #8b949e]NEXT ALARM[/dim #8b949e]")
            self.query_one("#sb-next-name", Static).update("[#484f58]none scheduled[/#484f58]")
            self.query_one("#sb-next-time", Static).update("")

        self.query_one("#sb-divider-2", Static).update(
            "[#21262d]────────────────────[/#21262d]"
        )

        # stats
        stats = (
            f"[dim #8b949e]ALARMS[/dim #8b949e]\n"
            f"[bold #e6edf3]{len(alarms):>3}[/bold #e6edf3]  [#8b949e]total[/#8b949e]\n"
            f"[bold #3fb950]{len(active):>3}[/bold #3fb950]  [#8b949e]active[/#8b949e]\n"
            f"[bold #e3b341]{len(snoozed):>3}[/bold #e3b341]  [#8b949e]snoozed[/#8b949e]\n"
            f"[bold #484f58]{len(off):>3}[/bold #484f58]  [#8b949e]off[/#8b949e]"
        )
        self.query_one("#sb-stats", Static).update(stats)

        self.query_one("#sb-divider-3", Static).update(
            "[#21262d]────────────────────[/#21262d]"
        )

        # daemon
        status = self._daemon.status()
        if status == "running":
            daemon_text = "[bold #3fb950]●[/bold #3fb950] [#8b949e]daemon[/#8b949e]\n  [#3fb950]running[/#3fb950]"
        else:
            daemon_text = "[bold #f85149]○[/bold #f85149] [#8b949e]daemon[/#8b949e]\n  [#f85149]stopped[/#f85149]\n\n[dim #6e7681]alarm daemon start[/dim #6e7681]"
        self.query_one("#sb-daemon", Static).update(daemon_text)


# ── Add / Edit Modal ──────────────────────────────────────────────────────────

class AlarmModal(ModalScreen):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    DEFAULT_CSS = """
    AlarmModal { align: center middle; }
    AlarmModal > Vertical {
        padding: 1 2;
        background: #161b22;
        border: solid #388bfd;
        width: 58;
        height: auto;
    }
    AlarmModal #modal-title  { color: #388bfd; text-style: bold; margin-bottom: 1; }
    AlarmModal Label         { color: #8b949e; margin-top: 1; }
    AlarmModal Input         { background: #0d1117; border: solid #30363d; color: #e6edf3; }
    AlarmModal Input:focus   { border: solid #388bfd; }
    AlarmModal Select        { background: #0d1117; border: solid #30363d; }
    AlarmModal #buttons      { margin-top: 1; height: 3; }
    AlarmModal Button        { margin-right: 1; }
    AlarmModal #err          { color: #f85149; height: 1; margin-top: 1; }
    """

    def __init__(self, existing: Alarm | None = None) -> None:
        super().__init__()
        self._existing = existing
        self._error: str = ""

    def compose(self) -> ComposeResult:
        a = self._existing
        rec_val = a.recurrence.value if a else "once"
        days_val = ",".join(a.days) if a and a.days else ""
        with Vertical():
            yield Static("✏  Edit Alarm" if a else "＋  New Alarm", id="modal-title")
            yield Label("Label")
            yield Input(value=a.label if a else "", placeholder="e.g. Wake up", id="label")
            yield Label("Time  [dim](HH:MM, 24h)[/dim]")
            yield Input(value=a.time if a else "", placeholder="07:30", id="time")
            yield Label("Recurrence")
            yield Select(RECURRENCE_OPTIONS, id="recurrence", value=rec_val)
            yield Label("Custom days  [dim](only when Custom selected)[/dim]")
            yield Input(value=days_val, placeholder="mon,wed,fri", id="days")
            yield Label("Snooze  [dim](minutes)[/dim]")
            yield Input(value=str(a.snooze_minutes) if a else "5", placeholder="5", id="snooze")
            yield Static("", id="err")
            with Horizontal(id="buttons"):
                yield Button("Save" if a else "Add", variant="primary", id="submit")
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

    def _show_error(self, msg: str) -> None:
        self.query_one("#err", Static).update(f"[#f85149]⚠  {msg}[/#f85149]")

    def _submit(self) -> None:
        label    = self.query_one("#label", Input).value.strip()
        time_val = self.query_one("#time", Input).value.strip()
        rec_val  = str(self.query_one("#recurrence", Select).value)
        days_val = self.query_one("#days", Input).value.strip()
        snooze_v = self.query_one("#snooze", Input).value.strip()

        if not label:
            self._show_error("Label is required")
            return
        if not time_val:
            self._show_error("Time is required")
            return
        try:
            datetime.strptime(time_val, "%H:%M")
        except ValueError:
            self._show_error("Time must be HH:MM (e.g. 07:30)")
            return

        from alarm.cli import parse_days
        try:
            if rec_val == "custom":
                recurrence, days = parse_days(days_val or "mon")
            else:
                recurrence, days = parse_days(rec_val if rec_val != "once" else None)
        except ValueError as e:
            self._show_error(str(e))
            return

        snooze = int(snooze_v) if snooze_v.isdigit() else 5

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


# ── Main App ──────────────────────────────────────────────────────────────────

class AlarmApp(App):
    TITLE = "alarm"

    CSS = """
    Screen { background: #0d1117; }

    #main-layout {
        height: 1fr;
        layout: horizontal;
    }

    #alarm-list {
        height: 1fr;
        overflow-y: auto;
        padding: 1 2 1 1;
        background: #0d1117;
    }

    #hint-bar {
        height: 1;
        background: #161b22;
        border-top: solid #21262d;
        padding: 0 1;
        color: #6e7681;
    }

    Footer { display: none; }
    """

    BINDINGS = [
        Binding("a",      "add_alarm",    "Add",    show=False),
        Binding("e",      "edit_alarm",   "Edit",   show=False),
        Binding("d",      "delete_alarm", "Delete", show=False),
        Binding("t",      "toggle_alarm", "On/Off", show=False),
        Binding("s",      "snooze_alarm", "Snooze", show=False),
        Binding("q",      "quit",         "Quit",   show=False),
        Binding("down",   "cursor_down",  "",       show=False),
        Binding("up",     "cursor_up",    "",       show=False),
        Binding("j",      "cursor_down",  "",       show=False),
        Binding("k",      "cursor_up",    "",       show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.store = AlarmStore()
        self.daemon = DaemonManager()
        self._cursor: int = 0

    def compose(self) -> ComposeResult:
        with Horizontal(id="main-layout"):
            yield Sidebar(self.store, self.daemon)
            yield ScrollableContainer(id="alarm-list")
        yield Static(
            " [bold #388bfd]↑↓[/bold #388bfd] navigate"
            "  [bold #388bfd]a[/bold #388bfd] add"
            "  [bold #388bfd]e[/bold #388bfd] edit"
            "  [bold #388bfd]t[/bold #388bfd] on/off"
            "  [bold #388bfd]s[/bold #388bfd] snooze"
            "  [bold #388bfd]d[/bold #388bfd] delete"
            "  [bold #388bfd]q[/bold #388bfd] quit",
            id="hint-bar",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._rebuild_cards()
        self.set_interval(1,  self._tick)
        self.set_interval(10, self._refresh_sidebar)

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _rebuild_cards(self) -> None:
        container = self.query_one("#alarm-list", ScrollableContainer)
        container.remove_children()
        self.call_after_refresh(self._mount_cards)

    def _mount_cards(self) -> None:
        alarms = self.store.load()
        container = self.query_one("#alarm-list", ScrollableContainer)
        if not alarms:
            container.mount(Static(
                "\n\n  [#484f58]No alarms yet.[/]\n\n"
                "  Press [bold #388bfd]a[/bold #388bfd] to add your first alarm.",
            ))
            self._cursor = 0
        else:
            self._cursor = min(self._cursor, len(alarms) - 1)
            for i, alarm in enumerate(alarms):
                card = AlarmCard(alarm)
                if i == self._cursor:
                    card.add_class("selected")
                container.mount(card)
        self._refresh_sidebar()

    def _tick(self) -> None:
        for card in self.query(AlarmCard):
            card.refresh()
        self._refresh_sidebar()

    def _refresh_sidebar(self) -> None:
        try:
            self.query_one(Sidebar).refresh_content()
        except Exception:
            pass

    def _cards(self) -> list[AlarmCard]:
        return list(self.query(AlarmCard))

    def _focused_card(self) -> AlarmCard | None:
        cards = self._cards()
        return cards[self._cursor] if cards else None

    def _move_cursor(self, delta: int) -> None:
        cards = self._cards()
        if not cards:
            return
        cards[self._cursor].remove_class("selected")
        self._cursor = (self._cursor + delta) % len(cards)
        cards[self._cursor].add_class("selected")
        cards[self._cursor].scroll_visible()

    # ── Actions ──────────────────────────────────────────────────────────────

    def action_cursor_down(self) -> None:
        self._move_cursor(1)

    def action_cursor_up(self) -> None:
        self._move_cursor(-1)

    def action_add_alarm(self) -> None:
        def on_close(alarm: Alarm | None) -> None:
            if alarm:
                self.store.add(alarm)
                self._rebuild_cards()
                self.notify(f"Added  {alarm.label}  {alarm.time}", severity="information")
        self.push_screen(AlarmModal(), on_close)

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
                self.notify(f"Updated  {updated.label}", severity="information")
        self.push_screen(AlarmModal(existing=alarm), on_close)

    def action_delete_alarm(self) -> None:
        card = self._focused_card()
        if card:
            label = card.alarm.label
            self.store.delete(card.alarm.id)
            self._cursor = max(0, self._cursor - 1)
            self._rebuild_cards()
            self.notify(f"Deleted  {label}", severity="warning")

    def action_toggle_alarm(self) -> None:
        card = self._focused_card()
        if card:
            alarm = self.store.get(card.alarm.id)
            if alarm:
                alarm.enabled = not alarm.enabled
                self.store.update(alarm)
                self._rebuild_cards()
                state = "enabled" if alarm.enabled else "disabled"
                sev = "information" if alarm.enabled else "warning"
                self.notify(f"{alarm.label}  {state}", severity=sev)

    def action_snooze_alarm(self) -> None:
        card = self._focused_card()
        if card:
            alarm = self.store.get(card.alarm.id)
            if alarm:
                alarm.next_fire = (alarm.next_fire or datetime.now()) + timedelta(minutes=alarm.snooze_minutes)
                alarm.snoozed = True
                self.store.update(alarm)
                self._rebuild_cards()
                self.notify(f"Snoozed  {alarm.label}  +{alarm.snooze_minutes}m", severity="information")


def run_tui() -> None:
    AlarmApp().run()
