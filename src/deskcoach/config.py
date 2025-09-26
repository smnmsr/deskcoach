from __future__ import annotations

import logging
import os
from types import SimpleNamespace
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import tomllib  # Python 3.11+
except Exception:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

try:  # Pythonic resource access for packaged data
    import importlib.resources as resources
except Exception:  # pragma: no cover
    resources = None  # type: ignore

log = logging.getLogger(__name__)

# Embedded default config as a safe fallback when running from a single-file bundle
_DEFAULT_CONFIG_TOML = b"""
[app]
base_url = "http://moss_table_watcher.zhaw.ch"
poll_minutes = 1.0
stand_threshold_mm = 850
remind_after_minutes = 45
remind_repeat_minutes = 5
standing_check_after_minutes = 5
standing_check_repeat_minutes = 2
snooze_minutes = 30
play_sound = true
use_windows_toast = true
log_level = "WARNING"
"""


def _read_toml_bytes(data_bytes: bytes) -> Dict[str, Any]:
    return tomllib.loads(data_bytes.decode("utf-8"))


def _load_from_path(p: Path) -> Dict[str, Any]:
    with p.open("rb") as f:
        return tomllib.load(f)


def _candidate_config_paths() -> list[Path]:
    """Return likely config paths in decreasing priority for default lookup."""
    candidates: list[Path] = []
    # 1) Project root (development runs)
    try:
        dev_root = Path(__file__).resolve().parents[2]
        candidates.append(dev_root / "config.toml")
    except Exception:
        pass
    # 2) PyInstaller one-file extracted dir (_MEIPASS)
    try:
        meipass = Path(getattr(sys, "_MEIPASS", ""))  # type: ignore[name-defined]
        if meipass:
            candidates.append(meipass / "config.toml")
    except Exception:
        pass
    # 3) Beside the executable (one-folder build)
    try:
        exe_dir = Path(getattr(sys, "executable", ""))  # type: ignore[name-defined]
        if exe_dir:
            candidates.append(Path(exe_dir).resolve().parent / "config.toml")
    except Exception:
        pass
    # 4) Package resources (src/deskcoach/resources)
    try:
        pkg_res_dir = Path(__file__).resolve().parents[1] / "resources"
        candidates.append(pkg_res_dir / "config.toml")
    except Exception:
        pass
    return candidates


def load_config(path: Optional[Path | str] = None) -> SimpleNamespace:
    """Load configuration into a SimpleNamespace.

    Behavior:
    - If an explicit `path` is provided and the file doesn't exist, raise FileNotFoundError (preserves tests).
    - If `path` is None, try multiple default locations suitable for dev, PyInstaller, and packaged runs.
      If none exist, fall back to an embedded default config.
    """
    data: Dict[str, Any]

    if path is not None:
        cfg_path = Path(path)
        if not cfg_path.exists():
            raise FileNotFoundError(f"Config file not found at {cfg_path}")
        data = _load_from_path(cfg_path)
    else:
        # Try candidate locations
        for cand in _candidate_config_paths():
            try:
                if cand.exists():
                    data = _load_from_path(cand)
                    break
            except Exception:
                continue
        else:
            # Try importlib.resources: deskcoach/resources/config.toml (optional)
            loaded = False
            try:
                if resources is not None and resources.files:  # type: ignore[attr-defined]
                    from importlib.resources import files
                    res_pkg = files("deskcoach.resources") / "config.toml"
                    if res_pkg.is_file():
                        data = tomllib.loads(res_pkg.read_text("utf-8"))
                        loaded = True
            except Exception:
                loaded = False
            if not loaded:
                # Fall back to embedded defaults
                data = _read_toml_bytes(_DEFAULT_CONFIG_TOML)
                log.warning("Using embedded default config; external config.toml not found.")

    # Minimal validation and defaults
    app = data.get("app", {})
    base_url = str(app.get("base_url", "http://localhost"))
    poll_minutes = float(app.get("poll_minutes", 5))
    stand_threshold_mm = int(app.get("stand_threshold_mm", 900))
    remind_after_minutes = int(app.get("remind_after_minutes", 45))
    remind_repeat_minutes = int(app.get("remind_repeat_minutes", 5))
    snooze_minutes = int(app.get("snooze_minutes", 30))
    play_sound = bool(app.get("play_sound", True))
    use_windows_toast = bool(app.get("use_windows_toast", True))
    standing_check_after_minutes = int(app.get("standing_check_after_minutes", 30))
    standing_check_repeat_minutes = int(app.get("standing_check_repeat_minutes", 30))
    log_level = str(app.get("log_level", "INFO")).upper()

    ns = SimpleNamespace(
        app=SimpleNamespace(
            base_url=base_url,
            poll_minutes=poll_minutes,
            stand_threshold_mm=stand_threshold_mm,
            remind_after_minutes=remind_after_minutes,
            remind_repeat_minutes=remind_repeat_minutes,
            snooze_minutes=snooze_minutes,
            play_sound=play_sound,
            use_windows_toast=use_windows_toast,
            standing_check_after_minutes=standing_check_after_minutes,
            standing_check_repeat_minutes=standing_check_repeat_minutes,
            log_level=log_level,
        )
    )
    log.debug(
        "Loaded config: base_url=%s, poll_minutes=%s, stand_threshold_mm=%s, remind_after=%s, repeat=%s, snooze=%s, play_sound=%s, toast=%s, stand_after=%s, stand_repeat=%s, log_level=%s",
        base_url, poll_minutes, stand_threshold_mm, remind_after_minutes, remind_repeat_minutes, snooze_minutes, play_sound, use_windows_toast, standing_check_after_minutes, standing_check_repeat_minutes, log_level,
    )
    return ns
