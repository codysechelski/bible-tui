from __future__ import annotations

import sqlite3
from pathlib import Path

from bible_tui.paths import BUNDLED_BIBLES_DIR


KJV_PATH = BUNDLED_BIBLES_DIR / "bible_kjv.sqlite"
ASV_PATH = BUNDLED_BIBLES_DIR / "bible_asv.sqlite"

SCHEMA = """
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE books (
    id INTEGER PRIMARY KEY,
    sort_order INTEGER NOT NULL UNIQUE,
    canonical_name TEXT NOT NULL UNIQUE,
    common_name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    testament TEXT NOT NULL
);
CREATE TABLE chapters (id INTEGER PRIMARY KEY, book_id INTEGER NOT NULL, chapter_number INTEGER NOT NULL);
CREATE TABLE verses (
    id INTEGER PRIMARY KEY,
    book_id INTEGER NOT NULL,
    chapter_id INTEGER NOT NULL,
    chapter_number INTEGER NOT NULL,
    verse_number INTEGER NOT NULL,
    text TEXT NOT NULL
);
"""


def make_bible(
    path: Path,
    version: str | None = "TST",
    name: str | None = "Test Version",
    verses: dict[tuple[int, str, int], list[int]] | None = None,
) -> Path:
    """Write a tiny Bible. ``verses`` maps (sort order, book name, chapter) to verse numbers."""
    if verses is None:
        verses = {(1, "Genesis", 1): [1, 2, 3], (43, "John", 3): [15, 16, 17]}
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        if version is not None:
            conn.execute("INSERT INTO metadata VALUES ('version', ?)", (version,))
        if name is not None:
            conn.execute("INSERT INTO metadata VALUES ('version_name', ?)", (name,))
        for (order, book, chapter), numbers in verses.items():
            testament = "old" if order <= 39 else "new"
            conn.execute(
                "INSERT OR IGNORE INTO books VALUES (?, ?, ?, ?, ?, ?)",
                (order, order, book, book, book.lower(), testament),
            )
            chapter_id = conn.execute(
                "INSERT INTO chapters (book_id, chapter_number) VALUES (?, ?)", (order, chapter)
            ).lastrowid
            for number in numbers:
                conn.execute(
                    "INSERT INTO verses (book_id, chapter_id, chapter_number, verse_number, text) VALUES (?, ?, ?, ?, ?)",
                    (order, chapter_id, chapter, number, f"{book} {chapter}:{number} text"),
                )
    conn.close()
    return path


class FakeScreen:
    """Just enough of a curses window for BibleTui's non-drawing logic."""

    def __init__(self, height: int = 30, width: int = 110) -> None:
        self.size = (height, width)

    def getmaxyx(self) -> tuple[int, int]:
        return self.size
