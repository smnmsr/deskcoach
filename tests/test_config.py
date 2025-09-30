from pathlib import Path
from types import SimpleNamespace
import textwrap
import tempfile
import os
import pytest

from deskcoach.config import load_config
import importlib
import deskcoach.config as cfgmod


def write_tmp_config(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def test_load_config_from_custom_path(tmp_path: Path):
    cfg_path = write_tmp_config(
        tmp_path,
        """
        [app]
        base_url = "http://example.com"
        poll_minutes = 2.5
        stand_threshold_mm = 880
        remind_after_minutes = 40
        remind_repeat_minutes = 7
        standing_check_after_minutes = 12
        standing_check_repeat_minutes = 6
        snooze_minutes = 20
        play_sound = false
        use_windows_toast = false
        """,
    )
    ns = load_config(cfg_path).app
    assert ns.base_url == "http://example.com"
    assert ns.poll_minutes == 2.5
    assert ns.stand_threshold_mm == 880
    assert ns.remind_after_minutes == 40
    assert ns.remind_repeat_minutes == 7
    assert ns.snooze_minutes == 20
    assert ns.play_sound is False
    assert ns.use_windows_toast is False
    assert ns.standing_check_after_minutes == 12
    assert ns.standing_check_repeat_minutes == 6


def test_load_config_missing_file_raises(tmp_path: Path):
    missing = tmp_path / "does_not_exist.toml"
    with pytest.raises(FileNotFoundError):
        load_config(missing)


def test_load_config_creates_in_data_dir_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data_dir = tmp_path / "data"

    class DummyPlatformDirs:
        def __init__(self, appname: str, appauthor: str, roaming: bool = False):
            self.user_data_dir = str(data_dir)

    monkeypatch.setattr(cfgmod, "PlatformDirs", DummyPlatformDirs)

    # Ensure clean
    assert not (data_dir / "config.toml").exists()

    ns = load_config().app
    # File now exists
    cfg_file = data_dir / "config.toml"
    assert cfg_file.exists()
    # Defaults applied (from embedded or package)
    assert isinstance(ns.remind_after_minutes, int)
    assert ns.snooze_minutes == 30


def test_load_config_uses_existing_in_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    cfg_text = textwrap.dedent(
        """
        [app]
        base_url = "http://from-data-dir"
        poll_minutes = 3.5
        snooze_minutes = 15
        play_sound = false
        use_windows_toast = false
        """
    )
    (data_dir / "config.toml").write_text(cfg_text, encoding="utf-8")

    class DummyPlatformDirs:
        def __init__(self, appname: str, appauthor: str, roaming: bool = False):
            self.user_data_dir = str(data_dir)

    monkeypatch.setattr(cfgmod, "PlatformDirs", DummyPlatformDirs)

    ns = load_config().app
    assert ns.base_url == "http://from-data-dir"
    assert ns.poll_minutes == 3.5
    assert ns.snooze_minutes == 15
    assert ns.play_sound is False
    assert ns.use_windows_toast is False
