from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bible_tui.store import BibleStore
from bible_tui.tui import FOCUS_TEXT, BibleTui, build_fuzzy_matches, match_spans, parse_fuzzy_query
from bible_tui.versions import discover_versions, find_version, inspect_database

from tests.helpers import ASV_PATH, KJV_PATH, FakeScreen, make_bible


class VersionSwitchTest(unittest.TestCase):
    def setUp(self) -> None:
        versions = discover_versions([KJV_PATH.parent]).versions
        self.kjv = find_version(versions, "KJV")
        self.asv = find_version(versions, "ASV")
        self.changes: list[str] = []
        self.app = BibleTui(
            FakeScreen(),
            BibleStore(KJV_PATH),
            self.kjv,
            versions,
            on_version_change=lambda version: self.changes.append(version.abbreviation),
        )

    def tearDown(self) -> None:
        self.app.store.close()

    def go_to(self, book_name: str, chapter: int, verse: int) -> None:
        book = next(book for book in self.app.books if book.name == book_name)
        self.app.jump_to_reference(book, chapter, verse)

    def test_switch_keeps_the_reference(self) -> None:
        self.go_to("John", 3, 16)
        self.app.switch_version(self.asv)
        self.assertEqual(self.app.version, self.asv)
        self.assertEqual(self.app.location_label(), "John 3:16")
        self.assertEqual(self.app.focus, FOCUS_TEXT)
        self.assertTrue(self.app.verses[self.app.verse_cursor].text.startswith("For God so loved the world"))
        self.assertEqual(self.changes, ["ASV"])
        self.assertEqual(self.app.message, "switched to American Standard Version of 1901")

    def test_verse_missing_from_target_lands_on_previous_verse(self) -> None:
        self.go_to("Matthew", 17, 21)
        self.app.switch_version(self.asv)
        self.assertEqual(self.app.location_label(), "Matthew 17:20")

    def test_switch_resets_version_caches(self) -> None:
        self.app.open_fuzzy_finder()
        self.app.close_fuzzy_finder()
        self.assertIsNotNone(self.app.all_verses)
        self.app.switch_version(self.asv)
        self.assertIsNone(self.app.all_verses)
        self.assertEqual(self.app.goto_verse_cache, {})

    def test_alphabetical_order_survives_switch(self) -> None:
        self.app.toggle_book_order()
        self.go_to("Ruth", 2, 3)
        self.app.switch_version(self.asv)
        self.assertTrue(self.app.alphabetical)
        self.assertEqual(self.app.books[0].name, "1 Chronicles")
        self.assertEqual(self.app.location_label(), "Ruth 2:3")

    def test_switch_to_partial_bible_falls_back_to_first_book(self) -> None:
        partial = inspect_database(make_bible(Path(tempfile.mkdtemp()) / "p.sqlite"))
        self.go_to("Ruth", 2, 3)
        self.app.switch_version(partial)
        self.assertEqual(self.app.location_label(), "Genesis 1:1")
        self.go_to("John", 3, 17)
        self.app.switch_version(self.kjv)
        self.assertEqual(self.app.location_label(), "John 3:17")

    def test_version_modal_selects_and_closes(self) -> None:
        self.app.handle_key(ord("t"))
        self.assertTrue(self.app.version_modal_open)
        self.assertEqual(self.app.versions[self.app.version_cursor], self.kjv)
        self.app.handle_key(ord("k"))
        self.app.handle_key(10)
        self.assertFalse(self.app.version_modal_open)
        self.assertEqual(self.app.version, self.asv)


class SearchFunctionsTest(unittest.TestCase):
    def test_match_spans_is_case_insensitive(self) -> None:
        self.assertEqual(match_spans("Love one another; love", "love"), [(0, 4), (18, 22)])

    def test_fuzzy_query_tokens(self) -> None:
        tokens = parse_fuzzy_query("'year' ^blessed wept.$ !fear")
        self.assertEqual([(t.text, t.anchor, t.negate) for t in tokens], [
            ("year", "word", False),
            ("blessed", "prefix", False),
            ("wept.", "suffix", False),
            ("fear", None, True),
        ])

    def test_fuzzy_find_across_bundled_version(self) -> None:
        store = BibleStore(ASV_PATH)
        try:
            matches = build_fuzzy_matches(store.all_verses(), "^jesus wept.$")
        finally:
            store.close()
        self.assertEqual(matches[0].verse.full_reference, "John 11:35")


if __name__ == "__main__":
    unittest.main()
