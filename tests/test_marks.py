from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bible_tui.config import ConfigError, load_settings
from bible_tui.marks import MarkError, MarkStore
from bible_tui.store import BibleStore
from bible_tui.tui import MARK_SIGN_NERD_FONT, MARK_SIGN_PLAIN, BibleTui
from bible_tui.versions import discover_versions, find_version

from tests.helpers import KJV_PATH, FakeScreen


class MarkStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp()) / "home"

    def test_toggle_persists_and_reloads(self) -> None:
        store = MarkStore.load(self.home)
        self.assertTrue(store.toggle([(43, 3, 16)]))
        reloaded = MarkStore.load(self.home)
        self.assertTrue(reloaded.is_marked((43, 3, 16)))
        data = json.loads((self.home / "marks.json").read_text(encoding="utf-8"))
        self.assertEqual(data["version"], 1)
        self.assertEqual(
            {key: data["marks"][0][key] for key in ("book", "chapter", "verse")},
            {"book": 43, "chapter": 3, "verse": 16},
        )
        self.assertFalse(reloaded.toggle([(43, 3, 16)]))
        self.assertFalse(MarkStore.load(self.home).is_marked((43, 3, 16)))

    def test_toggle_many_marks_all_unless_all_marked(self) -> None:
        store = MarkStore.load(self.home)
        store.toggle([(1, 1, 1)])
        self.assertTrue(store.toggle([(1, 1, 1), (1, 1, 2)]))
        self.assertTrue(store.is_marked((1, 1, 2)))
        self.assertFalse(store.toggle([(1, 1, 1), (1, 1, 2)]))
        self.assertEqual(store.marks, {})

    def test_damaged_file_is_never_overwritten(self) -> None:
        self.home.mkdir(parents=True)
        path = self.home / "marks.json"
        for content in ("{broken", '{"marks": [{"book": "x"}]}', "[]"):
            with self.subTest(content=content):
                path.write_text(content, encoding="utf-8")
                store = MarkStore.load(self.home)
                self.assertIsNotNone(store.load_error)
                with self.assertRaises(MarkError):
                    store.toggle([(1, 1, 1)])
                self.assertEqual(path.read_text(encoding="utf-8"), content)

    def test_nerd_font_setting(self) -> None:
        config = Path(tempfile.mkdtemp()) / "config.json"
        config.write_text('{"nerd_font": true}', encoding="utf-8")
        self.assertTrue(load_settings(config).nerd_font)
        config.write_text('{"nerd_font": "yes"}', encoding="utf-8")
        with self.assertRaises(ConfigError):
            load_settings(config)


class TuiMarkTest(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp())
        versions = discover_versions([KJV_PATH.parent]).versions
        self.versions = versions
        self.app = BibleTui(
            FakeScreen(),
            BibleStore(KJV_PATH),
            find_version(versions, "KJV"),
            versions,
            marks=MarkStore.load(self.home),
        )

    def tearDown(self) -> None:
        self.app.store.close()

    def go_to(self, book_name: str, chapter: int, verse: int) -> None:
        book = next(book for book in self.app.books if book.name == book_name)
        self.app.jump_to_reference(book, chapter, verse)

    def test_m_toggles_the_current_verse(self) -> None:
        self.go_to("John", 3, 16)
        self.app.handle_key(ord("m"))
        self.assertEqual(self.app.message, "marked John 3:16")
        self.assertTrue(MarkStore.load(self.home).is_marked((43, 3, 16)))
        self.app.handle_key(ord("m"))
        self.assertEqual(self.app.message, "unmarked John 3:16")

    def test_m_in_visual_mode_marks_each_selected_verse(self) -> None:
        self.go_to("Psalms", 23, 1)
        for key in "Vjjm":
            self.app.handle_key(ord(key))
        self.assertEqual(self.app.message, "marked 3 verses")
        self.assertFalse(self.app.visual_mode)
        self.assertEqual(sorted(self.app.marks.marks), [(19, 23, 1), (19, 23, 2), (19, 23, 3)])

    def test_marks_follow_the_verse_across_versions(self) -> None:
        self.go_to("John", 3, 16)
        self.app.handle_key(ord("m"))
        self.app.switch_version(find_version(self.versions, "ASV"))
        self.assertTrue(self.app.marks.is_marked(self.app.verse_key(self.app.verse_cursor)))

    def test_m_outside_the_text_pane_explains(self) -> None:
        self.app.handle_key(ord("m"))
        self.assertEqual(self.app.message, "select a verse to mark")
        self.assertEqual(self.app.marks.marks, {})

    def test_sign_depends_on_nerd_font_setting(self) -> None:
        self.assertEqual(self.app.mark_sign, MARK_SIGN_PLAIN)
        app = BibleTui(FakeScreen(), self.app.store, self.app.version, nerd_font=True)
        self.assertEqual(app.mark_sign, MARK_SIGN_NERD_FONT)


if __name__ == "__main__":
    unittest.main()
