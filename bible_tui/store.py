"""Read access to one Bible version's SQLite database."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from bible_tui.versions import connect_read_only


BOOK_ABBREVIATIONS = {
    "Genesis": "Gen.",
    "Exodus": "Ex.",
    "Leviticus": "Lev.",
    "Numbers": "Num.",
    "Deuteronomy": "Deut.",
    "Joshua": "Josh.",
    "Judges": "Judg.",
    "Ruth": "Ruth",
    "1 Samuel": "1 Sam.",
    "2 Samuel": "2 Sam.",
    "1 Kings": "1 Kings",
    "2 Kings": "2 Kings",
    "1 Chronicles": "1 Chron.",
    "2 Chronicles": "2 Chron.",
    "Ezra": "Ezra",
    "Nehemiah": "Neh.",
    "Esther": "Est.",
    "Job": "Job",
    "Psalms": "Ps.",
    "Proverbs": "Prov",
    "Ecclesiastes": "Eccles.",
    "Song of Solomon": "Song",
    "Isaiah": "Isa.",
    "Jeremiah": "Jer.",
    "Lamentations": "Lam.",
    "Ezekiel": "Ezek.",
    "Daniel": "Dan.",
    "Hosea": "Hos.",
    "Joel": "Joel",
    "Amos": "Amos",
    "Obadiah": "Obad.",
    "Jonah": "Jonah",
    "Micah": "Mic.",
    "Nahum": "Nah.",
    "Habakkuk": "Hab.",
    "Zephaniah": "Zeph.",
    "Haggai": "Hag.",
    "Zechariah": "Zech.",
    "Malachi": "Mal.",
    "Matthew": "Matt.",
    "Mark": "Mark",
    "Luke": "Luke",
    "John": "John",
    "Acts": "Acts",
    "Romans": "Rom.",
    "1 Corinthians": "1 Cor.",
    "2 Corinthians": "2 Cor.",
    "Galatians": "Gal.",
    "Ephesians": "Eph.",
    "Philippians": "Phil.",
    "Colossians": "Col.",
    "1 Thessalonians": "1 Thess.",
    "2 Thessalonians": "2 Thess.",
    "1 Timothy": "1 Tim.",
    "2 Timothy": "2 Tim.",
    "Titus": "Titus",
    "Philemon": "Philem.",
    "Hebrews": "Heb.",
    "James": "James",
    "1 Peter": "1 Pet.",
    "2 Peter": "2 Pet.",
    "1 John": "1 John",
    "2 John": "2 John",
    "3 John": "3 John",
    "Jude": "Jude",
    "Revelation": "Rev",
}


@dataclass(frozen=True)
class Book:
    id: int
    sort_order: int
    name: str
    testament: str


@dataclass(frozen=True)
class Verse:
    number: int
    text: str



@dataclass(frozen=True)
class BibleVerse:
    book_id: int
    book_order: int
    book_name: str
    chapter_number: int
    verse_number: int
    text: str

    @property
    def full_reference(self) -> str:
        return f"{self.book_name} {self.chapter_number}:{self.verse_number}"

    @property
    def short_reference(self) -> str:
        abbr = BOOK_ABBREVIATIONS.get(self.book_name, self.book_name)
        return f"{abbr} {self.chapter_number}:{self.verse_number}"


class BibleStore:
    def __init__(self, db_path: Path) -> None:
        self.conn = connect_read_only(db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    def books(self, alphabetical: bool) -> list[Book]:
        order = "common_name COLLATE NOCASE" if alphabetical else "sort_order"
        rows = self.conn.execute(
            f"""
            SELECT id, sort_order, common_name, testament
            FROM books
            ORDER BY {order}
            """
        ).fetchall()
        return [
            Book(row["id"], row["sort_order"], row["common_name"], row["testament"])
            for row in rows
        ]

    def chapters(self, book_id: int) -> list[int]:
        rows = self.conn.execute(
            """
            SELECT chapter_number
            FROM chapters
            WHERE book_id = ?
            ORDER BY chapter_number
            """,
            (book_id,),
        ).fetchall()
        return [row["chapter_number"] for row in rows]

    def verses(self, book_id: int, chapter: int) -> list[Verse]:
        rows = self.conn.execute(
            """
            SELECT verse_number, text
            FROM verses
            WHERE book_id = ? AND chapter_number = ?
            ORDER BY verse_number
            """,
            (book_id, chapter),
        ).fetchall()
        return [Verse(row["verse_number"], row["text"]) for row in rows]

    def all_verses(self) -> list[BibleVerse]:
        rows = self.conn.execute(
            """
            SELECT books.id AS book_id,
                   books.sort_order,
                   books.common_name,
                   verses.chapter_number,
                   verses.verse_number,
                   verses.text
            FROM verses
            JOIN books ON books.id = verses.book_id
            ORDER BY books.sort_order, verses.chapter_number, verses.verse_number
            """
        ).fetchall()
        return [
            BibleVerse(
                row["book_id"],
                row["sort_order"],
                row["common_name"],
                row["chapter_number"],
                row["verse_number"],
                row["text"],
            )
            for row in rows
        ]
