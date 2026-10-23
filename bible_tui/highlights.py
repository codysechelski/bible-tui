"""Highlighted verses, saved to ``highlights.json`` in the app home.

Like marks, highlights are keyed by ``(book sort_order, chapter, verse)`` so they show in every version.
The file stores color *names*, so the actual terminal colors can change without touching saved data.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from bible_tui.config import ConfigError, read_json, write_json
from bible_tui.marks import VerseKey
from bible_tui.paths import HIGHLIGHTS_FILE_NAME


FORMAT_VERSION = 1

HIGHLIGHT_COLORS: tuple[str, ...] = ("yellow", "green", "blue", "purple", "pink", "orange")


class HighlightError(Exception):
    pass


@dataclass(frozen=True)
class Highlight:
    color: str
    created_at: str


class HighlightStore:
    def __init__(
        self,
        path: Path | None,
        highlights: dict[VerseKey, Highlight] | None = None,
        load_error: str | None = None,
    ) -> None:
        # ``path`` is None for an in-memory store (tests, or no app home).
        self.path = path
        self.highlights: dict[VerseKey, Highlight] = dict(highlights or {})
        self.load_error = load_error

    @classmethod
    def load(cls, home: Path) -> HighlightStore:
        """Load highlights. An unreadable file is kept untouched and the store refuses to save,
        so a damaged file is never overwritten with an empty list."""
        path = home / HIGHLIGHTS_FILE_NAME
        if not path.exists():
            return cls(path)
        try:
            return cls(path, parse_highlights(read_json(path)))
        except (ConfigError, HighlightError) as error:
            return cls(path, load_error=str(error))

    def color(self, key: VerseKey) -> str | None:
        highlight = self.highlights.get(key)
        return highlight.color if highlight else None

    def newest_first(self) -> list[tuple[VerseKey, Highlight]]:
        """Highlights, newest first. Verses highlighted together stay in Bible order."""
        in_bible_order = sorted(self.highlights.items())
        return sorted(in_bible_order, key=lambda item: item[1].created_at, reverse=True)

    def apply(self, keys: Iterable[VerseKey], color: str | None) -> None:
        """Highlight every key in ``color``, or clear them when ``color`` is None. A verse that
        already has that color keeps its original date. Nothing changes if saving fails."""
        before = dict(self.highlights)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for key in keys:
            if color is None:
                self.highlights.pop(key, None)
            elif self.color(key) != color:
                self.highlights[key] = Highlight(color, now)
        if self.highlights == before:
            return
        try:
            self.save()
        except (HighlightError, OSError):
            self.highlights = before
            raise

    def remove(self, key: VerseKey) -> None:
        self.apply([key], None)

    def save(self) -> None:
        if self.path is None:
            return
        if self.load_error is not None:
            raise HighlightError(f"not saving highlights: {self.load_error}")
        write_json(self.path, serialize_highlights(self.highlights))


def parse_highlights(data: object) -> dict[VerseKey, Highlight]:
    if not isinstance(data, dict) or not isinstance(data.get("highlights"), list):
        raise HighlightError("expected an object with a \"highlights\" list")
    highlights: dict[VerseKey, Highlight] = {}
    for entry in data["highlights"]:
        try:
            key = (int(entry["book"]), int(entry["chapter"]), int(entry["verse"]))
            color = entry["color"]
        except (TypeError, KeyError, ValueError):
            raise HighlightError(f"invalid highlight entry: {entry!r}") from None
        if not isinstance(color, str) or not color:
            raise HighlightError(f"invalid highlight entry: {entry!r}")
        # Unknown color names are kept as-is so a newer file isn't damaged by an older app.
        highlights[key] = Highlight(color, str(entry.get("created_at", "")))
    return highlights


def serialize_highlights(highlights: dict[VerseKey, Highlight]) -> dict[str, object]:
    return {
        "version": FORMAT_VERSION,
        "highlights": [
            {
                "book": book,
                "chapter": chapter,
                "verse": verse,
                "color": highlight.color,
                "created_at": highlight.created_at,
            }
            for (book, chapter, verse), highlight in sorted(highlights.items())
        ],
    }
