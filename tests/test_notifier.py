import sys
from types import SimpleNamespace
import builtins

import deskcoach.services.notifier as notifier


class DummyCfg:
    def __init__(self, use_windows_toast=True, play_sound=True):
        self.use_windows_toast = use_windows_toast
        self.play_sound = play_sound


def test_notifier_falls_back_to_stderr(monkeypatch, capsys):
    # Force config
    dummy_ns = SimpleNamespace(app=DummyCfg(use_windows_toast=True, play_sound=True))
    monkeypatch.setenv("PYTHONIOENCODING", "utf-8")
    monkeypatch.setattr(notifier, "ToastNotificationManager", None)
    monkeypatch.setattr(notifier, "XmlDocument", None)
    # Ensure no tray
    if "tray" in notifier.__dict__:
        del notifier.__dict__["tray"]

    # Stub load_config to avoid reading filesystem
    def fake_load_config():
        return dummy_ns

    # Monkeypatch import at runtime inside notify
    monkeypatch.setitem(sys.modules, "deskcoach.config", SimpleNamespace(load_config=fake_load_config))

    notifier.notify("Title", "Message")
    out = capsys.readouterr()
    assert "[Notification] Title: Message" in out.err
