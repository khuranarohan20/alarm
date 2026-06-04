from unittest.mock import patch
from pathlib import Path
from alarm.models import Alarm, Recurrence
from alarm.notifier import notify, generate_default_sound


def make_alarm() -> Alarm:
    return Alarm(label="Morning", time="07:30", recurrence=Recurrence.ONCE)


def test_notify_calls_bell(capsys):
    with patch("alarm.notifier._system_notify"), patch("alarm.notifier._play_audio"):
        notify(make_alarm())
    out = capsys.readouterr().out
    assert "\a" in out or "Morning" in out


def test_notify_continues_if_system_notify_fails():
    with patch("alarm.notifier._system_notify", side_effect=Exception("oops")), \
         patch("alarm.notifier._play_audio"):
        notify(make_alarm())  # must not raise


def test_notify_continues_if_audio_fails():
    with patch("alarm.notifier._system_notify"), \
         patch("alarm.notifier._play_audio", side_effect=Exception("no audio")):
        notify(make_alarm())  # must not raise


def test_generate_default_sound_creates_wav(tmp_path):
    out = tmp_path / "beep.wav"
    generate_default_sound(out)
    assert out.exists()
    assert out.stat().st_size > 0
