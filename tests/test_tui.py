from __future__ import annotations

import tempfile
import unittest
from unittest import mock
from pathlib import Path

from bible_tui.store import BibleStore
import curses

from bible_tui.tui import (
    COMMANDS,
    FOCUS_BOOKS,
    FOCUS_CHAPTERS,
    FOCUS_TEXT,
    KEY_CTRL_D,
    KEY_CTRL_F,
    KEY_CTRL_G,
    KEY_CTRL_P,
    KEY_CTRL_S,
    KEY_CTRL_U,
    KEY_TAB,
    BibleTui,
    build_fuzzy_matches,
    fill_copy_template,
    match_spans,
    passage_reference,
    parse_fuzzy_query,
    word_spans,
)
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


class KeybindingTest(unittest.TestCase):
    def setUp(self) -> None:
        versions = discover_versions([KJV_PATH.parent]).versions
        self.app = BibleTui(FakeScreen(), BibleStore(KJV_PATH), find_version(versions, "KJV"), versions)

    def tearDown(self) -> None:
        self.app.store.close()

    def press(self, *keys: object) -> None:
        for key in keys:
            self.app.handle_key(ord(key) if isinstance(key, str) else key)

    def go_to(self, book_name: str, chapter: int, verse: int) -> None:
        book = next(book for book in self.app.books if book.name == book_name)
        self.app.jump_to_reference(book, chapter, verse)

    def cursor_word(self) -> str:
        text = self.app.verses[self.app.verse_cursor].text
        col = self.app.text_cursor_col
        return next(text[start:end] for start, end in word_spans(text) if start <= col < end)

    def test_gg_and_G(self) -> None:
        self.go_to("Genesis", 1, 10)
        self.press("G")
        self.assertEqual(self.app.location_label(), "Genesis 1:31")
        self.press("g")
        self.assertEqual(self.app.location_label(), "Genesis 1:31")
        self.press("g")
        self.assertEqual(self.app.location_label(), "Genesis 1:1")

    def test_gg_in_books_keeps_testament_heading_visible(self) -> None:
        self.app.focus = FOCUS_BOOKS
        self.press("G")
        self.assertGreater(self.app.book_scroll, 1)
        self.press("g", "g")
        self.assertEqual(self.app.selected_book.name, "Genesis")
        self.assertEqual(self.app.book_scroll, 0)
        self.assertEqual(self.app.book_rows[0], ("heading", "Old Testament"))

    def test_g_then_other_key_does_not_jump(self) -> None:
        self.go_to("Genesis", 1, 10)
        self.press("g", "j", "g")
        self.assertEqual(self.app.location_label(), "Genesis 1:11")

    def test_half_and_full_page(self) -> None:
        self.go_to("Genesis", 1, 1)
        self.press(KEY_CTRL_D)
        half = self.app.verse_cursor
        self.press(KEY_CTRL_U)
        self.assertEqual(self.app.verse_cursor, 0)
        self.press(KEY_CTRL_F)
        self.assertGreater(self.app.verse_cursor, half)
        self.assertGreater(half, 0)

    def test_word_motions_cross_verses(self) -> None:
        self.go_to("Genesis", 1, 1)
        self.press("w", "w")
        self.assertEqual(self.cursor_word(), "beginning")
        self.press("e")
        self.assertEqual(self.app.text_cursor_col, len("In the beginning") - 1)
        self.press("$")
        self.assertEqual(self.cursor_word(), ".")
        self.press("w")
        self.assertEqual((self.app.location_label(), self.app.text_cursor_col), ("Genesis 1:2", 0))
        self.press("b")
        self.assertEqual((self.app.location_label(), self.cursor_word()), ("Genesis 1:1", "."))
        self.press("0")
        self.assertEqual(self.app.text_cursor_col, 0)

    def test_commands_list_wraps_around(self) -> None:
        self.press(KEY_CTRL_P, curses.KEY_UP)
        self.assertEqual(self.app.command_cursor, len(COMMANDS) - 1)
        self.press(curses.KEY_DOWN)
        self.assertEqual((self.app.command_cursor, self.app.command_scroll), (0, 0))  # Heading shows too.
        self.press("k", "j", "j")
        self.assertEqual(self.app.command_cursor, 1)

    def test_h_at_start_of_verse_moves_focus_left(self) -> None:
        self.go_to("Genesis", 1, 1)
        self.press("l", "h")
        self.assertEqual((self.app.focus, self.app.text_cursor_col), (FOCUS_TEXT, 0))
        self.press("v", "h")
        self.assertEqual(self.app.focus, FOCUS_TEXT)  # Not while selecting.
        self.press(27, "h")
        self.assertEqual(self.app.focus, FOCUS_CHAPTERS)
        self.press("h")
        self.assertEqual(self.app.focus, FOCUS_BOOKS)

    def test_visual_verse_mode_selects_whole_verses(self) -> None:
        self.go_to("John", 11, 35)
        self.press("w", "V", "j")
        self.assertEqual(self.app.selected_text().splitlines()[0], "Jesus wept.")
        self.assertEqual(len(self.app.selected_text().splitlines()), 2)
        self.press("v")
        self.assertTrue(self.app.visual_mode)
        self.assertFalse(self.app.visual_line)
        self.press("v")
        self.assertFalse(self.app.visual_mode)

    def test_yy_yanks_just_the_verse_text_by_default(self) -> None:
        self.go_to("John", 11, 35)
        copied: list[str] = []
        with mock.patch("bible_tui.tui.copy_to_clipboard", side_effect=lambda text: copied.append(text) or True):
            self.press("y", "y")
        self.assertEqual(copied, ["Jesus wept."])
        self.assertEqual(self.app.message, "yanked verse")

    def test_yy_uses_the_copy_verse_format(self) -> None:
        self.go_to("Genesis", 1, 1)
        self.app.copy_verse_format = '"{text}" ({book_abbr} {chapter}:{verse} {version}) {{{version_name}}}'
        copied: list[str] = []
        with mock.patch("bible_tui.tui.copy_to_clipboard", side_effect=lambda text: copied.append(text) or True):
            self.press("y", "y")
        self.assertEqual(
            copied,
            ['"In the beginning God created the heaven and the earth." (Gen. 1:1 KJV) {King James Version}'],
        )

    def copied_by(self, *keys: object) -> list[str]:
        copied: list[str] = []
        with mock.patch("bible_tui.tui.copy_to_clipboard", side_effect=lambda text: copied.append(text) or True):
            self.press(*keys)
        return copied

    def test_Y_copies_selected_verses_as_a_passage(self) -> None:
        self.go_to("John", 3, 16)
        copied = self.copied_by("V", "j", "j", "Y")
        self.assertEqual(len(copied), 1)
        lines = copied[0].split("\n")
        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[0].startswith("16 For God so loved the world"))
        self.assertTrue(lines[2].startswith("18 He that believeth on him"))
        self.assertEqual(lines[3], "\u2014 John 3:16\u201318 \u00b7 KJV")
        self.assertEqual(self.app.message, "yanked John 3:16\u201318")
        self.assertFalse(self.app.visual_mode)

    def test_Y_without_a_selection_copies_the_verse_without_a_number(self) -> None:
        self.go_to("John", 11, 35)
        self.assertEqual(self.copied_by("Y"), ["Jesus wept.\n\u2014 John 11:35 \u00b7 KJV"])

    def test_Y_copies_whole_verses_from_a_character_selection(self) -> None:
        self.go_to("John", 11, 35)
        self.app.copy_verse_numbers = False
        self.app.copy_passage_format = "> {text}\n>\n> {book_abbr} {chapter}:{start_verse}-{end_verse} ({version_name})"
        copied = self.copied_by("w", "v", "j", "Y")
        self.assertEqual(len(copied), 1)
        lines = copied[0].split("\n")
        self.assertEqual(lines[0], "> Jesus wept.")
        self.assertTrue(lines[1].startswith("> Then said the Jews"))
        self.assertEqual(lines[2:], [">", "> John 11:35-36 (King James Version)"])
        self.assertEqual(self.app.message, "yanked John 11:35\u201336 (whole verses)")

    def test_copy_passage_command(self) -> None:
        self.go_to("John", 11, 35)
        with mock.patch("bible_tui.tui.copy_to_clipboard", return_value=True) as copy:
            self.app.run_command("yank_passage")
        copy.assert_called_once_with("Jesus wept.\n\u2014 John 11:35 \u00b7 KJV")

    def test_chapter_stepping_crosses_books(self) -> None:
        self.go_to("Genesis", 50, 3)
        self.press("]")
        self.assertEqual(self.app.location_label(), "Exodus 1:1")
        self.press("[")
        self.assertEqual(self.app.location_label(), "Genesis 50:1")
        self.press("[")
        self.assertEqual(self.app.location_label(), "Genesis 49:1")
        self.go_to("Revelation", 22, 1)
        self.press("]")
        self.assertEqual((self.app.location_label(), self.app.message), ("Revelation 22:1", "last chapter"))

    def test_chapter_stepping_uses_bible_order_when_alphabetical(self) -> None:
        self.app.toggle_book_order()
        self.go_to("Genesis", 50, 1)
        self.press("]")
        self.assertEqual(self.app.location_label(), "Exodus 1:1")
        self.assertEqual(self.app.books[self.app.book_cursor].name, "Exodus")

    def test_tab_cycles_panes(self) -> None:
        self.assertEqual(self.app.focus, FOCUS_BOOKS)
        self.press(KEY_TAB)
        self.assertEqual(self.app.focus, FOCUS_CHAPTERS)
        self.press(KEY_TAB)
        self.assertEqual(self.app.focus, FOCUS_TEXT)
        self.press(KEY_TAB)
        self.assertEqual(self.app.focus, FOCUS_BOOKS)
        self.press(curses.KEY_BTAB)
        self.assertEqual(self.app.focus, FOCUS_TEXT)

    def test_moving_right_keeps_the_current_place(self) -> None:
        self.press("]", "]")
        self.assertEqual(self.app.focus, FOCUS_BOOKS)
        self.press(KEY_TAB, KEY_TAB)
        self.assertEqual((self.app.focus, self.app.location_label()), (FOCUS_TEXT, "Genesis 3:1"))
        self.press("j", "j", curses.KEY_BTAB, "l")
        self.assertEqual(self.app.location_label(), "Genesis 3:3")

    def test_modal_keys(self) -> None:
        self.press("?")
        self.assertTrue(self.app.command_modal_open)
        self.press("?")
        self.assertFalse(self.app.command_modal_open)
        self.press(":")
        self.assertTrue(self.app.cmdline_active)
        self.press(27, KEY_CTRL_G)
        self.assertTrue(self.app.goto_open)
        self.press(27, KEY_CTRL_S)
        self.assertTrue(self.app.fuzzy_open)
        self.press(KEY_CTRL_S)
        self.assertTrue(self.app.fuzzy_help_open)


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


class CopyTemplateTest(unittest.TestCase):
    def test_passage_reference(self) -> None:
        self.assertEqual(passage_reference("John", 3, 16), "John 3:16")
        self.assertEqual(passage_reference("John", 3, 16, 18), "John 3:16\u201318")
        self.assertEqual(passage_reference("John", 3, 36, 2, end_chapter=4), "John 3:36\u20134:2")

    def test_text_lines_repeat_a_symbol_prefix(self) -> None:
        lines = ["16 a", "17 b"]
        self.assertEqual(fill_copy_template("{text}", lines), "16 a\n17 b")
        self.assertEqual(fill_copy_template("> {text}\n> {ref}", lines, ref="J"), "> 16 a\n> 17 b\n> J")
        self.assertEqual(fill_copy_template("    {text}", lines), "    16 a\n    17 b")
        self.assertEqual(fill_copy_template("{ref}: {text}", lines, ref="J"), "J: 16 a\n17 b")  # Words aren't repeated.
        self.assertEqual(fill_copy_template("{text!r}", lines), "'16 a\\n17 b'")


if __name__ == "__main__":
    unittest.main()
