from __future__ import annotations

import curses
import json
import tempfile
import unittest
from pathlib import Path

from bible_tui.cli import remembered_split
from bible_tui.config import ConfigError, Settings, load_settings
from bible_tui.store import BibleStore, Verse
from bible_tui.tui import (
    FOCUS_BOOKS,
    FOCUS_TEXT,
    KEY_CTRL_W,
    KEY_TAB,
    PICK_NEW_PANE,
    PICK_PANES,
    SPLIT_HORIZONTAL,
    SPLIT_VERTICAL,
    BibleTui,
    MissingVerse,
    align_verses,
)
from bible_tui.versions import discover_versions, find_version, inspect_database

from tests.helpers import KJV_PATH, FakeScreen, make_bible


class AlignVersesTest(unittest.TestCase):
    def test_every_number_gets_a_row_in_both(self) -> None:
        left, right = align_verses(
            [Verse(1, "a"), Verse(2, "b"), Verse(4, "d")],
            [Verse(1, "A"), Verse(3, "C"), Verse(4, "D")],
        )
        self.assertEqual([verse.number for verse in left], [1, 2, 3, 4])
        self.assertEqual([verse.number for verse in right], [1, 2, 3, 4])
        self.assertIsInstance(left[2], MissingVerse)
        self.assertIsInstance(right[1], MissingVerse)
        self.assertEqual((left[3].text, right[3].text), ("d", "D"))


class SplitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.versions = discover_versions([KJV_PATH.parent]).versions
        self.kjv = find_version(self.versions, "KJV")
        self.asv = find_version(self.versions, "ASV")
        self.version_changes: list[str] = []
        self.split_changes: list[tuple[str | None, str | None]] = []
        self.app = BibleTui(
            FakeScreen(),
            BibleStore(KJV_PATH),
            self.kjv,
            self.versions,
            on_version_change=lambda version: self.version_changes.append(version.abbreviation),
            on_split_change=lambda split, version: self.split_changes.append(
                (split, version.abbreviation if version else None)
            ),
        )

    def tearDown(self) -> None:
        self.app.close()

    def press(self, *keys: object) -> None:
        for key in keys:
            self.app.handle_key(ord(key) if isinstance(key, str) else key)

    def go_to(self, book_name: str, chapter: int, verse: int) -> None:
        book = next(book for book in self.app.books if book.name == book_name)
        self.app.jump_to_reference(book, chapter, verse)

    def split_with_asv(self, key: str = "v") -> None:
        self.press(KEY_CTRL_W, key)
        self.assertTrue(self.app.version_modal_open)
        self.assertEqual(self.app.version_mode, PICK_NEW_PANE)
        self.assertEqual(self.app.versions[self.app.version_cursor], self.asv)  # Starts on another version.
        self.press(10)

    def test_ctrl_w_v_opens_a_pane_with_the_chosen_version(self) -> None:
        self.go_to("John", 3, 16)
        self.split_with_asv()
        self.assertEqual(self.app.split, SPLIT_VERTICAL)
        self.assertEqual(self.app.split_pane.version, self.asv)
        self.assertEqual((self.app.focus, self.app.active_pane), (FOCUS_TEXT, 1))
        self.assertEqual(self.app.location_label(), "John 3:16")
        self.assertTrue(self.app.active_verses[self.app.verse_cursor].text.startswith("For God so loved"))
        self.assertEqual(self.split_changes, [(SPLIT_VERTICAL, "ASV")])

    def test_esc_cancels_the_new_pane(self) -> None:
        self.press(KEY_CTRL_W, "s", 27)
        self.assertIsNone(self.app.split_pane)

    def test_third_pane_is_refused(self) -> None:
        self.split_with_asv()
        self.press(KEY_CTRL_W, "s")
        self.assertFalse(self.app.version_modal_open)
        self.assertEqual(self.app.message, "2 panes max")

    def test_missing_verse_is_a_placeholder_in_that_pane_only(self) -> None:
        self.go_to("Matthew", 17, 21)
        self.split_with_asv()
        self.assertEqual(self.app.location_label(), "Matthew 17:21")
        self.assertEqual(len(self.app.verses), len(self.app.split_pane.verses))
        self.assertIsInstance(self.app.split_pane.verses[self.app.verse_cursor], MissingVerse)
        self.assertNotIsInstance(self.app.verses[self.app.verse_cursor], MissingVerse)
        self.press("y", "y")
        self.assertEqual(self.app.message, "Matthew 17:21 is not in American Standard Version of 1901")

    def test_navigation_moves_both_panes(self) -> None:
        self.split_with_asv()
        self.press("]")
        self.assertEqual(self.app.location_label(), "Genesis 2:1")
        self.assertTrue(self.app.split_pane.verses[0].text.startswith("And the heavens"))
        self.go_to("Psalms", 23, 1)
        self.assertTrue(self.app.verses[0].text.startswith("The LORD is my shepherd"))
        self.assertTrue(self.app.split_pane.verses[0].text.startswith("Jehovah is my shepherd"))

    def test_arrows_and_tab_move_between_text_panes(self) -> None:
        self.split_with_asv()
        self.press(curses.KEY_LEFT)
        self.assertEqual((self.app.focus, self.app.active_pane), (FOCUS_TEXT, 0))
        self.press(curses.KEY_RIGHT)
        self.assertEqual(self.app.active_pane, 1)
        self.press(KEY_TAB)
        self.assertEqual(self.app.focus, FOCUS_BOOKS)
        self.press(curses.KEY_BTAB)
        self.assertEqual((self.app.focus, self.app.active_pane), (FOCUS_TEXT, 1))
        self.press(KEY_CTRL_W, "h")
        self.assertEqual(self.app.active_pane, 0)
        self.press(KEY_CTRL_W, "w")
        self.assertEqual(self.app.active_pane, 1)

    def test_h_and_l_still_move_the_text_cursor(self) -> None:
        self.split_with_asv()
        self.press("l", "l")
        self.assertEqual((self.app.active_pane, self.app.text_cursor_col), (1, 2))

    def test_visual_selection_yanks_the_focused_version(self) -> None:
        self.go_to("John", 3, 16)
        self.split_with_asv()
        self.press("V")
        self.assertTrue(self.app.selected_text().startswith("For God so loved the world, that he gave his only begotten Son"))
        self.assertIn("whosoever believeth on him", self.app.selected_text())  # ASV wording
        self.press(curses.KEY_LEFT)
        self.assertFalse(self.app.visual_mode)  # A selection belongs to one pane.
        self.press("V")
        self.assertIn("whosoever believeth in him", self.app.selected_text())  # KJV wording

    def test_search_looks_in_the_focused_pane(self) -> None:
        self.go_to("John", 3, 16)
        self.split_with_asv()
        self.press("/", *"believeth on", 10)
        self.assertEqual(self.app.search_pane, 1)
        self.assertTrue(self.app.current_search_results())
        self.assertEqual(self.app.search_match_spans(self.app.verse_cursor, 0), [])

    def test_two_column_picker_changes_each_pane(self) -> None:
        self.split_with_asv()
        self.press("t")
        self.assertEqual(self.app.version_mode, PICK_PANES)
        self.assertEqual(self.app.version_column, 1)
        self.assertEqual([self.app.versions[c] for c in self.app.version_cursors], [self.kjv, self.asv])
        self.press(curses.KEY_DOWN)  # Right column: ASV -> KJV
        self.press(curses.KEY_LEFT, curses.KEY_UP)  # Left column: KJV -> ASV
        self.press(10)
        self.assertEqual((self.app.version, self.app.split_pane.version), (self.asv, self.kjv))
        self.assertEqual(self.version_changes, ["ASV"])
        self.assertEqual(self.split_changes[-1], (SPLIT_VERTICAL, "KJV"))

    def test_closing_the_first_pane_keeps_the_second_version(self) -> None:
        self.go_to("Matthew", 17, 21)
        self.split_with_asv()
        self.press(curses.KEY_LEFT, KEY_CTRL_W, "q")
        self.assertIsNone(self.app.split_pane)
        self.assertEqual(self.app.version, self.asv)
        self.assertEqual(self.app.location_label(), "Matthew 17:20")
        self.assertFalse(any(isinstance(verse, MissingVerse) for verse in self.app.verses))
        self.assertEqual(self.version_changes, ["ASV"])
        self.assertEqual(self.split_changes[-1], (None, None))

    def test_ctrl_w_o_closes_the_other_pane(self) -> None:
        self.go_to("Matthew", 17, 21)
        self.split_with_asv()
        self.press(curses.KEY_LEFT, KEY_CTRL_W, "o")  # Keep the focused (KJV) pane.
        self.assertIsNone(self.app.split_pane)
        self.assertEqual((self.app.version, self.app.location_label()), (self.kjv, "Matthew 17:21"))
        self.press(KEY_CTRL_W, "q")
        self.assertEqual(self.app.message, "only one pane: q quits")

    def test_split_refused_when_terminal_is_too_narrow(self) -> None:
        self.app.stdscr.size = (30, 70)
        self.press(KEY_CTRL_W, "v")
        self.assertFalse(self.app.version_modal_open)
        self.assertEqual(self.app.message, "terminal too narrow to split side by side")

    def test_pane_rows_line_up(self) -> None:
        self.go_to("Psalms", 119, 1)
        self.split_with_asv()
        rects = self.app.text_pane_rects()
        self.assertEqual([rect[0] for rect in rects], [0, 1])
        lines = self.app.text_lines(rects)
        self.assertEqual(len(lines[0]), len(lines[1]))
        self.assertEqual(
            [line.verse_index for line in lines[0]], [line.verse_index for line in lines[1]]
        )
        self.app.stdscr.size = (30, 70)  # Shrunk after splitting: only the focused pane shows.
        self.assertEqual([rect[0] for rect in self.app.text_pane_rects()], [1])

    def test_horizontal_split_stacks_panes(self) -> None:
        self.split_with_asv("s")
        (_, top_y, top_x, top_h, _), (_, bottom_y, bottom_x, _, _) = self.app.text_pane_rects()
        self.assertEqual((top_x, bottom_y), (bottom_x, top_y + top_h))
        self.press(KEY_CTRL_W, "k")
        self.assertEqual(self.app.active_pane, 0)

    def test_chapter_missing_from_second_version(self) -> None:
        partial = inspect_database(make_bible(Path(tempfile.mkdtemp()) / "p.sqlite"))
        self.assertTrue(self.app.open_split(SPLIT_VERTICAL, partial))
        self.go_to("Exodus", 1, 1)
        self.assertTrue(all(isinstance(verse, MissingVerse) for verse in self.app.split_pane.verses))
        self.go_to("John", 3, 16)
        self.assertEqual(self.app.split_pane.verses[self.app.verse_cursor].text, "John 3:16 text")

    def test_restoring_keeps_focus_and_does_not_save(self) -> None:
        self.assertTrue(self.app.open_split(SPLIT_HORIZONTAL, self.asv, restoring=True))
        self.assertEqual((self.app.focus, self.app.active_pane), (FOCUS_BOOKS, 0))
        self.assertEqual(self.split_changes, [])


class RememberSplitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.versions = discover_versions([KJV_PATH.parent]).versions

    def test_setting(self) -> None:
        config = Path(tempfile.mkdtemp()) / "config.json"
        self.assertFalse(load_settings(config).remember_split)
        config.write_text(json.dumps({"remember_split": True}), encoding="utf-8")
        settings = load_settings(config)
        self.assertTrue(settings.remember_split)
        self.assertEqual(settings.warnings, ())
        config.write_text(json.dumps({"remember_split": "yes"}), encoding="utf-8")
        with self.assertRaises(ConfigError):
            load_settings(config)

    def test_restores_only_when_enabled(self) -> None:
        state = {"split": "vertical", "split_version": "ASV"}
        self.assertIsNone(remembered_split(Settings(), state, self.versions))
        split, version = remembered_split(Settings(remember_split=True), state, self.versions)
        self.assertEqual((split, version.abbreviation), ("vertical", "ASV"))

    def test_ignores_bad_state(self) -> None:
        settings = Settings(remember_split=True)
        for state in ({}, {"split": "diagonal", "split_version": "ASV"}, {"split": "vertical", "split_version": "NOPE"}):
            with self.subTest(state=state):
                self.assertIsNone(remembered_split(settings, state, self.versions))


if __name__ == "__main__":
    unittest.main()
