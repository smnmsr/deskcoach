import sys
import builtins

import deskcoach.services.notifier as notifier


def test_notifier_falls_back_to_stderr(monkeypatch, capsys):
    monkeypatch.setenv("PYTHONIOENCODING", "utf-8")

    # Ensure no tray is present in the notifier module
    if "tray" in notifier.__dict__:
        del notifier.__dict__["tray"]

    notifier.notify("Title", "Message")
    out = capsys.readouterr()
    assert "[Notification] Title: Message" in out.err
