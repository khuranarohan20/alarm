# alarm

A Python CLI alarm clock with a Textual TUI, persistent schedules, and a background daemon.

## Installation

```bash
pip install -e .
```

## Quick Start

```bash
# Launch interactive TUI (default when run with no args)
alarm

# Add a one-time alarm
alarm add "Wake up" 07:30

# Add a weekday alarm with 10-minute snooze
alarm add "Standup" 09:00 --days weekdays --snooze 10

# Add a custom-day alarm
alarm add "Gym" 06:30 --days mon,wed,fri

# List all alarms
alarm list

# Start background daemon (fires notifications even after terminal closes)
alarm daemon start
alarm daemon status
alarm daemon stop

# Snooze an alarm (use ID from `alarm list`)
alarm snooze <id>
alarm snooze <id> --minutes 15

# Enable / disable
alarm enable <id>
alarm disable <id>

# Import / export
alarm export ~/backup.json
alarm import ~/backup.json
```

## `--days` values

| Value | Schedule |
|-------|----------|
| *(omitted)* | Fire once |
| `daily` | Every day |
| `weekdays` | Mon–Fri |
| `weekends` | Sat–Sun |
| `mon,wed,fri` | Custom day combination |

## TUI Keybindings

| Key | Action |
|-----|--------|
| `a` | Add alarm |
| `d` | Delete selected |
| `e` | Enable/disable selected |
| `s` | Snooze selected (uses per-alarm snooze duration) |
| `r` | Refresh table |
| `q` | Quit |

## Architecture

```
alarm/
├── models.py        — Alarm dataclass, Recurrence enum, next_fire logic
├── store.py         — JSON persistence (~/.alarm/alarms.json), atomic writes
├── scheduler.py     — DaemonManager: start/stop/status via PID file
├── daemon_runner.py — Background poll loop (every 30s)
├── notifier.py      — Terminal bell + system notify + audio (best-effort)
├── cli.py           — argparse subcommands
├── tui.py           — Textual interactive UI
└── __main__.py      — Entry point: CLI if args given, TUI otherwise
```

State is persisted to `~/.alarm/alarms.json`. The daemon re-reads this file on every poll cycle, so CLI changes take effect immediately without restarting the daemon.

## Notifications

When an alarm fires, three layers are attempted independently — a failure in one doesn't suppress the others:

1. **Terminal bell** — `\a` + Rich panel banner
2. **System notification** — `osascript` (macOS) or `notify-send` (Linux)
3. **Audio** — `afplay` (macOS) or `aplay`/`paplay` (Linux); generates a default 880Hz beep on first use

Custom sound per alarm: `alarm add "Gym" 06:30 --sound ~/sounds/beep.wav`

## Requirements

- Python 3.11+
- macOS or Linux (Windows best-effort for audio)
- Dependencies: `apscheduler`, `textual`, `rich` (installed via `pip install -e .`)
