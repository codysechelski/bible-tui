from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from bible_tui.store import BibleStore
from bible_tui.tui import (
    COMMANDS,
    FOCUS_TEXT,
    KEY_TAB,
    LIST_MARKS,
    MESSAGE_ERROR,
    PICK_NEW_PANE,
    PICK_VERSION,
    BibleTui,
    proverb_of_the_day,
)
from bible_tui.versions import discover_versions, find_version

from tests.helpers import KJV_PATH, FakeScreen, make_bible


class CommandLineTest(unittest.TestCase):
    def setUp(self) -> None:
        versions = discover_versions([KJV_PATH.parent]).versions
        self.kjv = find_version(versions, "KJV")
        self.asv = find_version(versions, "ASV")
        self.app = BibleTui(FakeScreen(), BibleStore(KJV_PATH), self.kjv, versions)
        self.addCleanup(self.app.close)

    def type(self, text: str, *keys: int) -> bool:
        """Open the command line, type ``text``, then press ``keys``; returns the last handle_key result."""
        result = self.app.handle_key(ord(":"))
        for char in text:
            result = self.app.handle_key(ord(char))
        for key in keys:
            result = self.app.handle_key(key)
        return result

    def labels(self) -> list[str]:
        return [item.label for item in self.app.cmdline_completions()]

    def test_quit_and_its_abbreviations(self) -> None:
        for text in ("q", "quit", "qu", "q!", "wq", "x"):
            with self.subTest(text=text):
                self.assertFalse(self.type(text, 10))
        self.assertTrue(self.type("Job", 10))  # A book, not a command

    def test_reference_with_or_without_verse(self) -> None:
        self.type("John 3:16", 10)
        self.assertEqual((self.app.location_label(), self.app.focus), ("John 3:16", FOCUS_TEXT))
        self.type("Romans 8", 10)
        self.assertEqual(self.app.location_label(), "Romans 8:1")
        self.type("Ruth", 10)
        self.assertEqual(self.app.location_label(), "Ruth 1:1")
        self.assertFalse(self.app.cmdline_active)

    def test_empty_line_lists_commands(self) -> None:
        self.app.open_cmdline()
        self.assertEqual(self.labels()[:3], ["quit", "find [words]", "set version=<name>"])

    def test_completions_mix_commands_and_books(self) -> None:
        self.app.open_cmdline()
        self.app.cmdline_text = "m"
        self.assertEqual(self.labels(), ["marks", "Micah", "Malachi", "Matthew", "Mark"])  # Books in Bible order
        self.app.cmdline_text = "John 3:1"
        self.assertIn("John 3:16", self.labels())

    def test_tab_accepts_and_enter_takes_the_highlight_when_incomplete(self) -> None:
        self.type("Jo", KEY_TAB)
        self.assertEqual(self.app.cmdline_text, "Joshua ")  # Bible order
        self.app.handle_key(27)
        self.type("Job", KEY_TAB)
        self.assertEqual(self.app.cmdline_text, "Job ")
        self.app.handle_key(14)  # ctrl+n: "Job " alone would run, but a chosen completion wins
        self.app.handle_key(10)
        self.assertTrue(self.app.cmdline_active)
        self.assertEqual(self.app.cmdline_text, "Job 2:")
        self.app.handle_key(10)  # Not a reference yet: takes the first completion, Job 2:1
        self.app.handle_key(10)
        self.assertEqual((self.app.cmdline_active, self.app.location_label()), (False, "Job 2:1"))

    def test_find_opens_fuzzy_finder_with_words(self) -> None:
        self.type("find jesus wept", 10)
        self.assertTrue(self.app.fuzzy_open)
        self.assertEqual(self.app.fuzzy_query, "jesus wept")
        self.assertTrue(self.app.fuzzy_matches)

    def test_set_version(self) -> None:
        self.app.open_cmdline()
        self.app.cmdline_text = "set version="
        self.assertEqual(self.labels(), ["ASV", "KJV"])
        self.app.cmdline_text = "set version=a"
        self.assertEqual(self.labels(), ["ASV"])
        self.app.cmdline_text = "set ver"
        self.assertEqual(self.labels(), ["set version="])
        self.app.close_cmdline()
        self.type("set version=asv", 10)
        self.assertEqual(self.app.version, self.asv)
        self.type("se version KJV", 10)
        self.assertEqual(self.app.version, self.kjv)
        self.type("set version", 10)
        self.assertEqual((self.app.version_modal_open, self.app.version_mode), (True, PICK_VERSION))

    def test_set_version_changes_the_focused_split_pane(self) -> None:
        self.app.open_split("vertical", self.kjv)
        self.app.focus_pane(1)
        self.type("set version=ASV", 10)
        self.assertEqual((self.app.version, self.app.split_pane.version), (self.kjv, self.asv))

    def test_window_and_list_commands(self) -> None:
        self.type("vs", 10)
        self.assertEqual(self.app.version_mode, PICK_NEW_PANE)
        self.app.handle_key(27)
        self.type("marks", 10)
        self.assertEqual(self.app.list_kind, LIST_MARKS)

    def on_day(self, day: int) -> None:
        fake = mock.patch("bible_tui.tui.date")
        fake.start().today.return_value = date(2026, 10, day)
        self.addCleanup(fake.stop)

    def test_potd_goes_to_the_chapter_for_today(self) -> None:
        self.on_day(28)
        self.type("POTD", 10)
        self.assertEqual((self.app.location_label(), self.app.focus), ("Proverbs 28:1", FOCUS_TEXT))
        self.assertEqual(self.app.message, "proverb of the day: Proverbs 28:1")

    def test_potd_from_the_commands_list(self) -> None:
        self.on_day(31)
        self.assertIn("proverb_of_the_day", [item.action for item in COMMANDS])
        self.app.run_command("proverb_of_the_day")
        self.assertEqual(self.app.location_label(), "Proverbs 31:1")

    def test_every_day_of_the_month_has_a_chapter(self) -> None:
        book = self.app.key_book(proverb_of_the_day(date(2026, 1, 1)))
        chapters = self.app.store.chapters(book.id)
        for day in range(1, 32):
            self.assertIn(proverb_of_the_day(date(2026, 1, day))[1], chapters)

    def test_potd_in_a_version_without_proverbs(self) -> None:
        path = make_bible(Path(tempfile.mkdtemp()) / "bible_tst.sqlite")
        versions = discover_versions([path.parent]).versions
        app = BibleTui(FakeScreen(), BibleStore(path), find_version(versions, "TST"), versions)
        self.addCleanup(app.close)
        self.on_day(28)
        app.go_to_proverb_of_the_day()
        self.assertEqual((app.message, app.message_kind), ("Test Version doesn't include Proverbs", MESSAGE_ERROR))

    def test_unknown_input_is_an_error(self) -> None:
        self.type("zzz", 10)
        self.assertEqual(self.app.message, "not a command or reference: zzz")
        self.assertEqual(self.app.message_kind, MESSAGE_ERROR)
        self.type("set colour=red", 10)
        self.assertEqual(self.app.message, "unknown option: colour")

    def test_escape_and_backspace_leave(self) -> None:
        self.type("qu", 27)
        self.assertFalse(self.app.cmdline_active)
        self.type("", 127)
        self.assertFalse(self.app.cmdline_active)


if __name__ == "__main__":
    unittest.main()
