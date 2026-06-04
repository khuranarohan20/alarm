from __future__ import annotations
import array
import logging
import math
import platform
import subprocess
import wave
from pathlib import Path
from alarm.models import Alarm

logger = logging.getLogger(__name__)

SOUNDS_DIR = Path(__file__).parent / "sounds"
DEFAULT_SOUND = SOUNDS_DIR / "default.wav"


def generate_default_sound(path: Path, frequency: int = 880, duration: float = 1.0) -> None:
    sample_rate = 44100
    n = int(sample_rate * duration)
    samples = array.array("h", [
        int(32767 * math.sin(2 * math.pi * frequency * i / sample_rate))
        for i in range(n)
    ])
    with wave.open(str(path), "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes(samples.tobytes())


def notify(alarm: Alarm) -> None:
    _bell(alarm)
    try:
        _system_notify(alarm)
    except Exception as e:
        logger.warning(f"System notify failed: {e}")
    try:
        _play_audio(alarm)
    except Exception as e:
        logger.warning(f"Audio failed: {e}")


def _bell(alarm: Alarm) -> None:
    from rich.console import Console
    from rich.panel import Panel
    console = Console()
    print("\a", end="", flush=True)
    console.print(Panel(
        f"[bold yellow]{alarm.label}[/bold yellow]\n[dim]{alarm.time}[/dim]",
        title="[red]⏰ ALARM[/red]",
        border_style="red",
    ))


def _system_notify(alarm: Alarm) -> None:
    system = platform.system()
    if system == "Darwin":
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{alarm.label}" with title "⏰ Alarm" sound name "Glass"'],
            check=True, capture_output=True,
        )
    elif system == "Linux":
        subprocess.run(["notify-send", "⏰ Alarm", alarm.label], check=True, capture_output=True)


def _play_audio(alarm: Alarm) -> None:
    sound_path = Path(alarm.sound) if alarm.sound else DEFAULT_SOUND
    if not sound_path.exists() and sound_path == DEFAULT_SOUND:
        SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
        generate_default_sound(DEFAULT_SOUND)
    if not sound_path.exists():
        return
    system = platform.system()
    if system == "Darwin":
        subprocess.Popen(
            ["afplay", str(sound_path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    elif system == "Linux":
        for player in ("aplay", "paplay", "mpg123"):
            if subprocess.run(["which", player], capture_output=True).returncode == 0:
                subprocess.Popen(
                    [player, str(sound_path)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                break
    elif system == "Windows":
        import winsound
        winsound.PlaySound(str(sound_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
