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
VERSE_FORMAT_FIELDS = {
    "text": "For God so loved the world...",
    "reference": "John 3:16",
    "book": "John",
    "book_abbr": "John",  # Common abbreviation, e.g. "Gen." for Genesis
    "chapter": 3,
    "verse": 16,
    "version": "KJV",
    "version_name": "King James Version",
}
DEFAULT_VERSE_FORMAT = "{text}"

# ``Y`` copies whole verses through this template. Fields, with John 3:16-18 in the KJV as the example:
PASSAGE_FORMAT_FIELDS = {
    "text": "16 For God so loved the world...\n17 For God sent not his Son...",
    "reference": "John 3:16\u201318",
    "book": "John",
    "book_abbr": "John",
    "chapter": 3,
    "start_verse": 16,
    "end_verse": 18,
    "version": "KJV",
    "version_name": "King James Version",
}
DEFAULT_PASSAGE_FORMAT = "{text}\n\u2014 {reference} \u00b7 {version}"


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    default_version: str | None = None
    bibles_dirs: tuple[Path, ...] = ()
    book_order: str = "bible"
    nerd_font: bool = False
    show_clock: bool = True
    remember_split: bool = False
    remember_position: bool = False
    copy_verse_format: str = DEFAULT_VERSE_FORMAT
    copy_passage_format: str = DEFAULT_PASSAGE_FORMAT
    copy_verse_numbers: bool = True
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
    known = {"default_version", "bibles_dirs", "book_order", "nerd_font", "show_clock", "remember_split", "remember_position", "copy_verse_format", "copy_passage_format", "copy_verse_numbers", "yank_format", "check_for_updates"}
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

    show_clock = data.get("show_clock", True)
    if not isinstance(show_clock, bool):
        raise ConfigError(f"{path}: show_clock must be true or false")

    remember_split = data.get("remember_split", False)
    if not isinstance(remember_split, bool):
        raise ConfigError(f"{path}: remember_split must be true or false")

    remember_position = data.get("remember_position", False)
    if not isinstance(remember_position, bool):
        raise ConfigError(f"{path}: remember_position must be true or false")

    # ``yank_format`` was the first name of ``copy_verse_format``; it still works.
    verse_key = "copy_verse_format"
    if "yank_format" in data:
        if verse_key in data:
            warnings.append(f"{path}: ignoring yank_format, because copy_verse_format is set")
        else:
            verse_key = "yank_format"
            warnings.append(f"{path}: yank_format is now called copy_verse_format; please rename it")
    copy_verse_format = data.get(verse_key, DEFAULT_VERSE_FORMAT)
    check_template(path, verse_key, copy_verse_format, VERSE_FORMAT_FIELDS)

    copy_passage_format = data.get("copy_passage_format", DEFAULT_PASSAGE_FORMAT)
    check_template(path, "copy_passage_format", copy_passage_format, PASSAGE_FORMAT_FIELDS)

    copy_verse_numbers = data.get("copy_verse_numbers", True)
    if not isinstance(copy_verse_numbers, bool):
        raise ConfigError(f"{path}: copy_verse_numbers must be true or false")

    check_for_updates = data.get("check_for_updates", True)
    if not isinstance(check_for_updates, bool):
        raise ConfigError(f"{path}: check_for_updates must be true or false")

    return Settings(
        default_version=default_version or None,
        bibles_dirs=tuple(bibles_dirs),
        book_order=book_order,
        nerd_font=nerd_font,
        show_clock=show_clock,
        remember_split=remember_split,
        remember_position=remember_position,
        copy_verse_format=copy_verse_format,
        copy_passage_format=copy_passage_format,
        copy_verse_numbers=copy_verse_numbers,
        check_for_updates=check_for_updates,
        warnings=tuple(warnings),
    )


def check_template(path: Path, setting: str, template: object, fields: Mapping[str, object]) -> None:
    """Only the plain ``{field}`` names in ``fields`` are allowed (``{{`` and ``}}`` for braces)."""
    if not isinstance(template, str):
        raise ConfigError(f"{path}: {setting} must be a string")
    available = ", ".join(f"{{{name}}}" for name in fields)
    try:
        parsed = list(string.Formatter().parse(template))
    except ValueError as error:
        raise ConfigError(f"{path}: {setting} is not a valid template ({error}); use {{{{ and }}}} for braces") from None
    for _, name, _, _ in parsed:
        if name is not None and name not in fields:
            shown = f"{{{name}}}" if name else "{}"
            raise ConfigError(f"{path}: {setting} has unknown field {shown} (available: {available})")
    try:
        template.format(**fields)
    except (ValueError, TypeError) as error:
        raise ConfigError(f"{path}: {setting} is not a valid template ({error})") from None


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
