"""User settings (``config.json``) and app-managed state (``state.json``).

``config.json`` is written by the user and only ever read by the app. Anything the
app records on its own (the last version used, and later bookmarks, highlights and
notes) lives in separate files beside it, written atomically with ``write_json``.
"""

from __future__ import annotations

import json
import os
import string
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from bible_tui.paths import STATE_FILE_NAME, expand_path


BOOK_ORDERS = ("bible", "alphabetical")

# ``yy`` copies the current verse through this template. Fields, with John 3:16 in the KJV as the example:
YANK_FORMAT_FIELDS = {
    "text": "For God so loved the world...",
    "reference": "John 3:16",
    "book": "John",
    "book_abbr": "John",  # Common abbreviation, e.g. "Gen." for Genesis
    "chapter": 3,
    "verse": 16,
    "version": "KJV",
    "version_name": "King James Version",
}
DEFAULT_YANK_FORMAT = "{text}"


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    default_version: str | None = None
    bibles_dirs: tuple[Path, ...] = ()
    book_order: str = "bible"
    nerd_font: bool = False
    remember_split: bool = False
    yank_format: str = DEFAULT_YANK_FORMAT
    check_for_updates: bool = True
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
    known = {"default_version", "bibles_dirs", "book_order", "nerd_font", "remember_split", "yank_format", "check_for_updates"}
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

    remember_split = data.get("remember_split", False)
    if not isinstance(remember_split, bool):
        raise ConfigError(f"{path}: remember_split must be true or false")

    yank_format = data.get("yank_format", DEFAULT_YANK_FORMAT)
    if not isinstance(yank_format, str):
        raise ConfigError(f"{path}: yank_format must be a string")
    check_yank_format(path, yank_format)

    check_for_updates = data.get("check_for_updates", True)
    if not isinstance(check_for_updates, bool):
        raise ConfigError(f"{path}: check_for_updates must be true or false")

    return Settings(
        default_version=default_version or None,
        bibles_dirs=tuple(bibles_dirs),
        book_order=book_order,
        nerd_font=nerd_font,
        remember_split=remember_split,
        yank_format=yank_format,
        check_for_updates=check_for_updates,
        warnings=tuple(warnings),
    )


def check_yank_format(path: Path, template: str) -> None:
    """Only the plain ``{field}`` names in ``YANK_FORMAT_FIELDS`` are allowed (``{{`` and ``}}`` for braces)."""
    fields = ", ".join(f"{{{name}}}" for name in YANK_FORMAT_FIELDS)
    try:
        parsed = list(string.Formatter().parse(template))
    except ValueError as error:
        raise ConfigError(f"{path}: yank_format is not a valid template ({error}); use {{{{ and }}}} for braces") from None
    for _, name, _, _ in parsed:
        if name is not None and name not in YANK_FORMAT_FIELDS:
            shown = f"{{{name}}}" if name else "{}"
            raise ConfigError(f"{path}: yank_format has unknown field {shown} (available: {fields})")
    try:
        template.format(**YANK_FORMAT_FIELDS)
    except (ValueError, TypeError) as error:
        raise ConfigError(f"{path}: yank_format is not a valid template ({error})") from None


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
