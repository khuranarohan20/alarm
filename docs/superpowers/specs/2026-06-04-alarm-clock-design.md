# Alarm Clock CLI — Design Spec

**Date:** 2026-06-04  
**Status:** Approved

---

## Context

Build a Python CLI alarm clock application as a 30-minute Senior Software Engineer build exercise. No web UI, no database. The goal is to demonstrate real engineering instincts: modular design, persistence, background scheduling, clean CLI/TUI split, and production-quality error handling.

---

## Approach

Modular `alarm/` package with a background APScheduler daemon. State persists to `~/.alarm/alarms.json`. A subcommand CLI handles scripting; a Textual TUI is the default interactive experience.

---

## Package Structure

```
alarm/
├── __main__.py          # Entry point: routes to CLI or TUI
├── models.py            # Alarm dataclass + recurrence enums
├── store.py             # JSON persistence (~/.alarm/alarms.json) + import/export
├── scheduler.py         # APScheduler wrapper; daemon start/stop/status
├── notifier.py          # Terminal bell, system notification, audio — best-effort
├── cli.py               # argparse subcommands
└── tui.py               # Textual TUI (default when run with no args)

~/.alarm/
├── alarms.json          # Persisted alarm state
├── daemon.pid           # Daemon PID file
└── daemon.log           # Daemon stdout/stderr
```

---

## Data Model

```python
@dataclass
class Alarm:
    id: str                    # UUID4
    label: str                 # Human-readable name
    time: str                  # "HH:MM" (24h)
    recurrence: Recurrence     # ONCE | DAILY | WEEKDAYS | WEEKENDS | CUSTOM
    days: list[str]            # ["mon","wed","fri"] — used when recurrence=CUSTOM
    enabled: bool              # Toggleable without deleting
    snooze_minutes: int        # Default 5, configurable per alarm
    next_fire: datetime        # Computed; updated after each fire
    created_at: datetime
```

### Recurrence Logic

| Value | Behaviour |
|-------|-----------|
| `ONCE` | Fires once, then `enabled → False` |
| `DAILY` | Every day at `time` |
| `WEEKDAYS` | Mon–Fri |
| `WEEKENDS` | Sat–Sun |
| `CUSTOM` | Days listed in `days` field |

### Snooze

Adds `snooze_minutes` to `next_fire` and re-arms without altering the base schedule. Snoozed alarms show a `💤` indicator in the list. Per-alarm default is 5 minutes unless overridden with `--snooze N` at add time.

### Persistence

Full alarm list serializes to `~/.alarm/alarms.json` as a JSON array. Import merges by ID (no duplicates). Export writes to a user-specified path.

---

## CLI Interface

```bash
# Alarm management
alarm add "Wake up" 07:30                          # no --days flag → ONCE
alarm add "Standup" 09:00 --days weekdays
alarm add "Gym" 06:30 --days mon,wed,fri
alarm add "Meds" 08:00 --days daily --snooze 10
# --days accepts: daily | weekdays | weekends | mon,tue,wed,... (default: once)

alarm list
alarm delete <id>
alarm enable <id>
alarm disable <id>
alarm snooze <id>
alarm snooze <id> --minutes 15

# Persistence
alarm export ~/backups/alarms.json
alarm import ~/backups/alarms.json

# Daemon
alarm daemon start
alarm daemon stop
alarm daemon status

# Default (no args) → TUI
alarm
```

---

## TUI (Textual)

- Table view of all alarms with live `next fire` countdown
- Keybindings: `a` add, `d` delete, `e` enable/disable, `s` snooze, `q` quit
- Modal form for adding/editing alarms
- Status bar showing daemon health

---

## Daemon & Scheduling

- `alarm daemon start` forks a background APScheduler process
- Polls every 30 seconds; fires notifications when alarms are due
- Re-reads `alarms.json` each cycle — CLI changes take effect immediately
- PID written to `~/.alarm/daemon.pid`; stdout/stderr to `~/.alarm/daemon.log`
- Double-start prevented by PID file check

---

## Notifier

Three layers, each attempted independently (failures logged, not raised):

1. **Terminal bell** — `print("\a")` + rich ASCII banner with label/time
2. **System notification** — macOS: `osascript`; Linux: `notify-send`
3. **Audio** — `playsound` for .mp3/.wav; fallback to `afplay` (macOS) / `aplay` (Linux)

A bundled `alarm.wav` ships with the package. Custom sound settable per alarm via `--sound /path/to/file`.

---

## Error Handling

| Layer | Behaviour |
|-------|-----------|
| Notifier | Best-effort: audio failure doesn't suppress bell/banner |
| Store | Atomic writes (tmp → rename); malformed JSON → backup + fresh start + warning |
| Daemon | PID prevents double-start; per-alarm scheduler exceptions caught + logged, daemon continues |
| CLI | User-friendly messages for bad time formats, unknown IDs, invalid day names — no raw stack traces |

---

## Testing

| Layer | Approach |
|-------|----------|
| `models.py` | Unit tests: recurrence logic, next-fire calculation |
| `store.py` | Unit tests: serialize/deserialize, import/export merge |
| `scheduler.py` | Integration test with mocked clock |
| `notifier.py` | Unit tests with mocks (no real audio/popups in CI) |
| `cli.py` | Subprocess-level tests for key subcommands |

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `apscheduler` | Background scheduling |
| `textual` | TUI framework |
| `rich` | Terminal banner formatting |
| `playsound` | Cross-platform audio |

All installable via `pip install -e .` with a `pyproject.toml`.

---

## Out of Scope

- Web UI / REST API
- Database (SQLite or otherwise)
- Windows audio support beyond best-effort
- Alarm labels with emoji (display may vary by terminal)
