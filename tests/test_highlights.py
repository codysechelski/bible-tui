from __future__ import annotations

import curses
import json
import tempfile
import unittest
from pathlib import Path

from bible_tui.highlights import HIGHLIGHT_COLORS, Highlight, HighlightError, HighlightStore
from bible_tui.store import BibleStore
from bible_tui.tui import HIGHLIGHT_PALETTE, PICKER_CLEAR, BibleTui
from bible_tui.versions import discover_versions, find_version

from tests.helpers import KJV_PATH, FakeScreen


class HighlightStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp()) / "home"

    def test_apply_persists_color_and_date(self) -> None:
        store = HighlightStore.load(self.home)
        store.apply([(43, 3, 16)], "yellow")
        data = json.loads((self.home / "highlights.json").read_text(encoding="utf-8"))
        self.assertEqual(data["version"], 1)
        entry = data["highlights"][0]
        self.assertEqual(
            {key: entry[key] for key in ("book", "chapter", "verse", "color")},
            {"book": 43, "chapter": 3, "verse": 16, "color": "yellow"},
        )
        self.assertTrue(entry["created_at"].endswith("+00:00"))
        self.assertEqual(HighlightStore.load(self.home).color((43, 3, 16)), "yellow")

    def test_recoloring_updates_the_date_but_the_same_color_does_not(self) -> None:
        store = HighlightStore(None, {(1, 1, 1): Highlight("yellow", "2026-01-01T00:00:00+00:00")})
        store.apply([(1, 1, 1)], "yellow")
        self.assertEqual(store.highlights[(1, 1, 1)].created_at, "2026-01-01T00:00:00+00:00")
        store.apply([(1, 1, 1)], "green")
        self.assertEqual(store.color((1, 1, 1)), "green")
        self.assertNotEqual(store.highlights[(1, 1, 1)].created_at, "2026-01-01T00:00:00+00:00")

    def test_clear_and_remove(self) -> None:
        store = HighlightStore.load(self.home)
        store.apply([(1, 1, 1), (1, 1, 2)], "blue")
        store.apply([(1, 1, 1)], None)
        store.remove((1, 1, 2))
        self.assertEqual(HighlightStore.load(self.home).highlights, {})

    def test_newest_first_keeps_verses_highlighted_together_in_bible_order(self) -> None:
        store = HighlightStore(
            None,
            {
                (1, 1, 1): Highlight("yellow", "2026-01-01T00:00:00+00:00"),
                (19, 23, 2): Highlight("green", "2026-03-01T00:00:00+00:00"),
                (19, 23, 1): Highlight("green", "2026-03-01T00:00:00+00:00"),
            },
        )
        self.assertEqual([key for key, _ in store.newest_first()], [(19, 23, 1), (19, 23, 2), (1, 1, 1)])

    def test_damaged_file_is_never_overwritten(self) -> None:
        self.home.mkdir(parents=True)
        path = self.home / "highlights.json"
        for content in ("{broken", '{"highlights": [{"book": 1, "chapter": 1, "verse": 1}]}', "[]"):
            with self.subTest(content=content):
                path.write_text(content, encoding="utf-8")
                store = HighlightStore.load(self.home)
                self.assertIsNotNone(store.load_error)
                with self.assertRaises(HighlightError):
                    store.apply([(1, 1, 1)], "yellow")
                self.assertEqual(store.highlights, {})
                self.assertEqual(path.read_text(encoding="utf-8"), content)

    def test_unknown_color_names_are_kept(self) -> None:
        self.home.mkdir(parents=True)
        (self.home / "highlights.json").write_text(
            '{"version": 1, "highlights": [{"book": 1, "chapter": 1, "verse": 1, "color": "teal"}]}',
            encoding="utf-8",
        )
        store = HighlightStore.load(self.home)
        store.apply([(1, 1, 2)], "yellow")
        self.assertEqual(HighlightStore.load(self.home).color((1, 1, 1)), "teal")

    def test_every_color_has_a_palette_entry(self) -> None:
        self.assertEqual(set(HIGHLIGHT_COLORS), set(HIGHLIGHT_PALETTE))


class TuiHighlightTest(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp())
        versions = discover_versions([KJV_PATH.parent]).versions
        self.app = BibleTui(
            FakeScreen(),
            BibleStore(KJV_PATH),
            find_version(versions, "KJV"),
            versions,
            highlights=HighlightStore.load(self.home),
        )

    def tearDown(self) -> None:
        self.app.store.close()

    def go_to(self, book_name: str, chapter: int, verse: int) -> None:
        book = next(book for book in self.app.books if book.name == book_name)
        self.app.jump_to_reference(book, chapter, verse)

    def press(self, keys: str) -> None:
        for key in keys:
            self.app.handle_key(ord(key))

    def saved_color(self, key: tuple[int, int, int]) -> str | None:
        return HighlightStore.load(self.home).color(key)

    def test_number_key_picks_a_color(self) -> None:
        self.go_to("John", 3, 16)
        self.press("c")
        self.assertTrue(self.app.picker_open)
        self.press("2")
        self.assertFalse(self.app.picker_open)
        self.assertEqual(self.app.message, "highlighted John 3:16 green")
        self.assertEqual(self.saved_color((43, 3, 16)), "green")

    def test_arrows_and_enter_pick_a_color_and_it_is_remembered(self) -> None:
        self.go_to("John", 3, 16)
        self.press("c")
        self.assertEqual(self.app.picker_cursor, 0)
        self.app.handle_key(curses.KEY_DOWN)
        self.press("jk")
        self.app.handle_key(10)
        self.assertEqual(self.saved_color((43, 3, 16)), HIGHLIGHT_COLORS[1])
        self.go_to("John", 3, 17)
        self.press("c")  # The last color used is preselected for a new verse.
        self.assertEqual(self.app.picker_cursor, 1)

    def test_picker_starts_on_the_verse_color_and_can_clear_it(self) -> None:
        self.go_to("John", 3, 16)
        self.press("c4")
        self.go_to("John", 3, 1)
        self.press("c1")
        self.go_to("John", 3, 16)
        self.press("c")
        self.assertEqual(self.app.picker_cursor, 3)
        self.app.handle_key(curses.KEY_END)
        self.assertEqual(self.app.picker_cursor, PICKER_CLEAR)
        self.app.handle_key(10)
        self.assertEqual(self.app.message, "cleared highlight from John 3:16")
        self.assertIsNone(self.saved_color((43, 3, 16)))

    def test_esc_cancels(self) -> None:
        self.go_to("John", 3, 16)
        self.press("c")
        self.app.handle_key(27)
        self.assertFalse(self.app.picker_open)
        self.assertEqual(self.app.highlights.highlights, {})

    def test_visual_selection_highlights_each_verse(self) -> None:
        self.go_to("Psalms", 23, 1)
        self.press("Vjjc")
        self.assertFalse(self.app.visual_mode)
        self.press("6")
        self.assertEqual(self.app.message, "highlighted 3 verses orange")
        self.assertEqual(sorted(self.app.highlights.highlights), [(19, 23, 1), (19, 23, 2), (19, 23, 3)])

    def test_c_outside_the_text_pane_explains(self) -> None:
        self.press("c")
        self.assertFalse(self.app.picker_open)
        self.assertEqual(self.app.message, "select a verse to highlight")

    def test_highlights_list_shows_newest_first_jumps_and_deletes(self) -> None:
        self.go_to("Genesis", 1, 1)
        self.press("c1")
        self.go_to("John", 3, 16)
        self.press("c3")
        self.app.highlights.highlights[(43, 3, 16)] = Highlight("blue", "2099-01-01T00:00:00+00:00")
        for open_key in ("C", '"'):
            with self.subTest(open_key=open_key):
                self.press(open_key)
                self.assertEqual(self.app.list_kind, "highlights")
                self.assertEqual([row.color for row in self.app.list_rows], ["blue", "yellow"])
                self.press(open_key)
                self.assertIsNone(self.app.list_kind)
        self.press('"j')
        self.app.handle_key(10)
        self.assertEqual(self.app.location_label(), "Genesis 1:1")
        self.press('"d')
        self.assertEqual(self.app.message, "removed highlight from John 3:16")
        self.assertEqual(self.app.list_kind, "highlights")
        self.assertIsNone(self.saved_color((43, 3, 16)))

    def test_commands_modal_entries(self) -> None:
        self.go_to("John", 3, 16)
        self.app.run_command("highlight")
        self.assertTrue(self.app.picker_open)
        self.app.handle_key(27)
        self.app.run_command("list_highlights")
        self.assertEqual(self.app.list_kind, "highlights")

    def test_failed_save_keeps_things_as_they_were(self) -> None:
        self.app.highlights = HighlightStore(self.home / "highlights.json", load_error="damaged")
        self.go_to("John", 3, 16)
        self.press("c1")
        self.assertEqual(self.app.message, "highlights not saved: not saving highlights: damaged")
        self.assertEqual(self.app.highlights.highlights, {})


if __name__ == "__main__":
    unittest.main()
