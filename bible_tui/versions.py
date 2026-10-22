"""Discover Bible versions: one SQLite database per version, found in a list of folders."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path


DATABASE_SUFFIXES = (".sqlite", ".sqlite3", ".db")

REQUIRED_COLUMNS = {
    "books": {"id", "sort_order", "common_name", "testament"},
    "chapters": {"book_id", "chapter_number"},
    "verses": {"book_id", "chapter_number", "verse_number", "text"},
}


class VersionError(Exception):
    pass


@dataclass(frozen=True)
class BibleVersion:
    abbreviation: str
    name: str
    path: Path
    metadata: dict[str, str] = field(default_factory=dict, compare=False, hash=False)

    def matches(self, query: str) -> bool:
        folded = query.casefold()
        return folded in (
            self.abbreviation.casefold(),
            self.name.casefold(),
            self.path.stem.casefold(),
            self.path.name.casefold(),
        )


@dataclass(frozen=True)
class Discovery:
    versions: tuple[BibleVersion, ...]
    # (path, reason) for files that were skipped: unreadable, wrong schema, or shadowed.
    skipped: tuple[tuple[Path, str], ...] = ()


def connect_read_only(path: Path) -> sqlite3.Connection:
    """Open a database without ever creating or modifying it."""
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def abbreviation_from_filename(path: Path) -> str:
    stem = path.stem
    if stem.lower().startswith("bible_"):
        stem = stem[len("bible_") :]
    return stem.upper()


def inspect_database(path: Path) -> BibleVersion:
    """Read a database's version details, raising ``VersionError`` if it is unusable."""
    try:
        conn = connect_read_only(path)
    except sqlite3.Error as error:
        raise VersionError(str(error)) from None
    try:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        for table, columns in REQUIRED_COLUMNS.items():
            if table not in tables:
                raise VersionError(f"missing table {table!r}")
            present = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            missing = columns - present
            if missing:
                raise VersionError(f"table {table!r} is missing {', '.join(sorted(missing))}")
        metadata: dict[str, str] = {}
        if "metadata" in tables:
            metadata = {
                str(key): str(value) for key, value in conn.execute("SELECT key, value FROM metadata")
            }
        if conn.execute("SELECT 1 FROM verses LIMIT 1").fetchone() is None:
            raise VersionError("no verses")
    except sqlite3.Error as error:
        raise VersionError(str(error)) from None
    finally:
        conn.close()

    abbreviation = metadata.get("version", "").strip() or abbreviation_from_filename(path)
    name = metadata.get("version_name", "").strip() or abbreviation
    return BibleVersion(abbreviation, name, path, metadata)


def database_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        (
            path
            for path in directory.iterdir()
            if path.suffix.lower() in DATABASE_SUFFIXES and path.is_file() and not path.name.startswith(".")
        ),
        key=lambda path: path.name.casefold(),
    )


def discover_versions(directories: Iterable[Path]) -> Discovery:
    """Scan ``directories`` in priority order. When two databases share an
    abbreviation, the one in the earlier directory wins and the other is skipped."""
    found: dict[str, BibleVersion] = {}
    skipped: list[tuple[Path, str]] = []
    seen_dirs: set[Path] = set()
    for directory in directories:
        directory = directory.expanduser()
        resolved = directory.resolve()
        if resolved in seen_dirs:
            continue
        seen_dirs.add(resolved)
        for path in database_files(directory):
            try:
                version = inspect_database(path)
            except VersionError as error:
                skipped.append((path, str(error)))
                continue
            key = version.abbreviation.casefold()
            if key in found:
                skipped.append((path, f"{version.abbreviation} already loaded from {found[key].path}"))
                continue
            found[key] = version
    versions = sorted(found.values(), key=lambda version: version.abbreviation.casefold())
    return Discovery(tuple(versions), tuple(skipped))


def find_version(versions: Iterable[BibleVersion], query: str) -> BibleVersion | None:
    return next((version for version in versions if version.matches(query)), None)
