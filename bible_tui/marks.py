"""Marked verses, saved to ``marks.json`` in the app home.

Marks are keyed by ``(book sort_order, chapter, verse)`` rather than database ids, so a
verse marked in one version shows as marked in every version that has it.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from bible_tui.config import ConfigError, read_json, write_json
from bible_tui.paths import MARKS_FILE_NAME


FORMAT_VERSION = 1

VerseKey = tuple[int, int, int]


class MarkError(Exception):
    pass


class MarkStore:
    def __init__(self, path: Path | None, marks: dict[VerseKey, str] | None = None, load_error: str | None = None) -> None:
        # ``path`` is None for an in-memory store (tests, or no app home).
        self.path = path
        self.marks: dict[VerseKey, str] = dict(marks or {})
        self.load_error = load_error

    @classmethod
    def load(cls, home: Path) -> MarkStore:
        """Load marks. An unreadable file is kept untouched and the store refuses to save,
        so a damaged file is never overwritten with an empty list."""
        path = home / MARKS_FILE_NAME
        if not path.exists():
            return cls(path)
        try:
            data = read_json(path)
            return cls(path, parse_marks(data))
        except (ConfigError, MarkError) as error:
            return cls(path, load_error=str(error))

    def is_marked(self, key: VerseKey) -> bool:
        return key in self.marks

    def newest_first(self) -> list[tuple[VerseKey, str]]:
        """Marks with their ``created_at``, newest first. Verses marked together stay in Bible order."""
        in_bible_order = sorted(self.marks.items())
        return sorted(in_bible_order, key=lambda item: item[1], reverse=True)

    def toggle(self, keys: Iterable[VerseKey]) -> bool:
        """Mark every key, or unmark them all if they are all marked already.
        Returns True if the keys are now marked."""
        keys = list(keys)
        if not keys:
            return False
        mark = not all(key in self.marks for key in keys)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for key in keys:
            if mark:
                self.marks.setdefault(key, now)
            else:
                self.marks.pop(key, None)
        self.save()
        return mark

    def remove(self, key: VerseKey) -> None:
        created_at = self.marks.pop(key, None)
        if created_at is None:
            return
        try:
            self.save()
        except (MarkError, OSError):
            self.marks[key] = created_at  # Keep showing what's still on disk.
            raise

    def save(self) -> None:
        if self.path is None:
            return
        if self.load_error is not None:
            raise MarkError(f"not saving marks: {self.load_error}")
        write_json(self.path, serialize_marks(self.marks))


def parse_marks(data: object) -> dict[VerseKey, str]:
    if not isinstance(data, dict) or not isinstance(data.get("marks"), list):
        raise MarkError("expected an object with a \"marks\" list")
    marks: dict[VerseKey, str] = {}
    for entry in data["marks"]:
        try:
            key = (int(entry["book"]), int(entry["chapter"]), int(entry["verse"]))
        except (TypeError, KeyError, ValueError):
            raise MarkError(f"invalid mark entry: {entry!r}") from None
        marks[key] = str(entry.get("created_at", ""))
    return marks


def serialize_marks(marks: dict[VerseKey, str]) -> dict[str, object]:
    return {
        "version": FORMAT_VERSION,
        "marks": [
            {"book": book, "chapter": chapter, "verse": verse, "created_at": created_at}
            for (book, chapter, verse), created_at in sorted(marks.items())
        ],
    }
