"""Where bible-tui looks for its config, app data and Bible databases."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path


APP_NAME = "bible-tui"
PACKAGE_DIR = Path(__file__).resolve().parent
BUNDLED_BIBLES_DIR = PACKAGE_DIR / "bibles"

HOME_ENV = "BIBLE_TUI_HOME"
CONFIG_FILE_NAME = "config.json"
STATE_FILE_NAME = "state.json"
MARKS_FILE_NAME = "marks.json"
HIGHLIGHTS_FILE_NAME = "highlights.json"
BIBLES_DIR_NAME = "bibles"


def user_home(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    home = env.get("HOME")
    return Path(home) if home else Path.home()


def expand_path(value: str, env: Mapping[str, str] | None = None) -> Path:
    """Expand a leading ``~`` against ``HOME`` from ``env`` (not the process)."""
    if value == "~" or value.startswith("~/"):
        return user_home(env) / value[2:]
    return Path(value)


def xdg_config_home(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    value = env.get("XDG_CONFIG_HOME", "")
    # The XDG spec says relative paths must be ignored.
    if value and Path(value).is_absolute():
        return Path(value)
    return user_home(env) / ".config"


def home_candidates(env: Mapping[str, str] | None = None) -> list[Path]:
    """App home directories in lookup order."""
    env = os.environ if env is None else env
    candidates: list[Path] = []
    explicit = env.get(HOME_ENV)
    if explicit:
        candidates.append(expand_path(explicit, env))
    candidates.append(user_home(env) / f".{APP_NAME}")
    candidates.append(xdg_config_home(env) / APP_NAME)
    return candidates


def resolve_home(env: Mapping[str, str] | None = None) -> Path:
    """Return the app home: ``$BIBLE_TUI_HOME``, else the first existing candidate,
    else the XDG location (``~/.config/bible-tui``), which is created on first write."""
    env = os.environ if env is None else env
    candidates = home_candidates(env)
    if env.get(HOME_ENV):
        return candidates[0]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[-1]
