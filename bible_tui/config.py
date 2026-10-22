"""User settings (``config.json``) and app-managed state (``state.json``).

``config.json`` is written by the user and only ever read by the app. Anything the
app records on its own (the last version used, and later bookmarks, highlights and
notes) lives in separate files beside it, written atomically with ``write_json``.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from bible_tui.paths import STATE_FILE_NAME, expand_path


BOOK_ORDERS = ("bible", "alphabetical")


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    default_version: str | None = None
    bibles_dirs: tuple[Path, ...] = ()
    book_order: str = "bible"
    nerd_font: bool = False
    warnings: tuple[str, ...] = field(default=(), compare=False)


def read_json(path: Path) -> object:
    try:
        with path.open(encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError as error:
        raise ConfigError(f"{path}: invalid JSON at line {error.lineno}, column {error.colno}: {error.msg}") from None
    except OSError as error:
        raise ConfigError(f"{path}: {error.strerror}") from None


def write_json(path: Path, data: object) -> None:
    """Write JSON through a temporary file so a crash never leaves a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
            file.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def load_settings(path: Path, env: Mapping[str, str] | None = None) -> Settings:
    """Load ``config.json``; a missing file means defaults."""
    if not path.exists():
        return Settings()
    data = read_json(path)
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: expected a JSON object at the top level")

    warnings: list[str] = []
    known = {"default_version", "bibles_dirs", "book_order", "nerd_font"}
    for key in sorted(set(data) - known):
        warnings.append(f"{path}: ignoring unknown setting {key!r}")

    default_version = data.get("default_version")
    if default_version is not None and not isinstance(default_version, str):
        raise ConfigError(f"{path}: default_version must be a string")

    raw_dirs = data.get("bibles_dirs", [])
    if isinstance(raw_dirs, str):
        raw_dirs = [raw_dirs]
    if not isinstance(raw_dirs, list) or not all(isinstance(item, str) for item in raw_dirs):
        raise ConfigError(f"{path}: bibles_dirs must be a list of directory paths")
    # Relative entries are taken from the config file's directory.
    bibles_dirs = []
    for item in raw_dirs:
        directory = expand_path(item, env)
        bibles_dirs.append(directory if directory.is_absolute() else path.parent / directory)

    book_order = data.get("book_order", "bible")
    if book_order not in BOOK_ORDERS:
        raise ConfigError(f"{path}: book_order must be one of {', '.join(BOOK_ORDERS)}")

    nerd_font = data.get("nerd_font", False)
    if not isinstance(nerd_font, bool):
        raise ConfigError(f"{path}: nerd_font must be true or false")

    return Settings(
        default_version=default_version or None,
        bibles_dirs=tuple(bibles_dirs),
        book_order=book_order,
        nerd_font=nerd_font,
        warnings=tuple(warnings),
    )


def load_state(home: Path) -> dict[str, object]:
    """Load ``state.json``. State is disposable, so an unreadable file is ignored."""
    path = home / STATE_FILE_NAME
    if not path.exists():
        return {}
    try:
        data = read_json(path)
    except ConfigError:
        return {}
    return data if isinstance(data, dict) else {}


def save_state(home: Path, state: Mapping[str, object]) -> None:
    write_json(home / STATE_FILE_NAME, dict(state))
