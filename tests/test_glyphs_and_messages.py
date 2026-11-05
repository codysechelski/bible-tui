from __future__ import annotations

import locale
import unittest
from unittest import mock

from bible_tui.store import BibleStore
from bible_tui.tui import (
    GLYPHS,
    MESSAGE_ERROR,
    MESSAGE_INFO,
    MESSAGE_SECONDS,
    MESSAGE_YANK,
    BibleTui,
    locale_clock_format,
)
from bible_tui.versions import discover_versions, find_version

from tests.helpers import KJV_PATH, FakeScreen


def make_app(nerd_font: bool = False) -> BibleTui:
    versions = discover_versions([KJV_PATH.parent]).versions
    return BibleTui(FakeScreen(), BibleStore(KJV_PATH), find_version(versions, "KJV"), versions, nerd_font=nerd_font)


class GlyphTest(unittest.TestCase):
    def test_plain_glyphs_keep_the_old_text(self) -> None:
        app = make_app()
        self.addCleanup(app.close)
        self.assertEqual(app.glyphs["search"], "SEARCH")
        self.assertEqual(app.fuzzy_prompt(), " FIND > ")
        self.assertEqual(app.glyphs["current"], "*")
        self.assertEqual((app.glyphs["missing"], app.glyphs["yank"], app.glyphs["error"]), ("", "", ""))

    def test_nerd_font_uses_the_icons(self) -> None:
        app = make_app(nerd_font=True)
        self.addCleanup(app.close)
        self.assertEqual(app.glyphs, {name: icon for name, (icon, _) in GLYPHS.items()})
        self.assertEqual(app.fuzzy_prompt(), "  ")
        # Font Awesome 4 range, the same in Nerd Fonts v2 and v3. Font Awesome 4 has no cross, so the title
        # uses Nerd Fonts v3.3's nf-fa-cross.
        icons = [icon for name, (icon, _) in GLYPHS.items() if name != "title"]
        self.assertTrue(all("" <= icon <= "" for icon in icons))
        self.assertEqual(GLYPHS["title"], ("\ueec3", "\u271d"))

    def test_clock_format_drops_seconds(self) -> None:
        def langinfo(item: int) -> str:
            return {locale.D_FMT: "%d.%m.%Y", locale.T_FMT: "%H:%M:%S"}[item]

        with mock.patch("bible_tui.tui.locale.nl_langinfo", side_effect=langinfo):
            self.assertEqual(locale_clock_format(), "%a %d.%m.%Y %H:%M")

    def test_clock_format_expands_twelve_hour_time(self) -> None:
        def langinfo(item: int) -> str:
            return {locale.D_FMT: "%m/%d/%Y", locale.T_FMT: "%r"}[item]

        with mock.patch("bible_tui.tui.locale.nl_langinfo", side_effect=langinfo):
            self.assertEqual(locale_clock_format(), "%a %m/%d/%Y %I:%M %p")


class MessageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = make_app()
        self.addCleanup(self.app.close)

    def test_messages_expire(self) -> None:
        with mock.patch("bible_tui.tui.time.monotonic", return_value=100.0):
            self.app.message = "switched"
            self.assertEqual(self.app.message_kind, MESSAGE_INFO)
            self.assertEqual(self.app.message_timeout_ms(), int(MESSAGE_SECONDS[MESSAGE_INFO] * 1000) + 1)
        with mock.patch("bible_tui.tui.time.monotonic", return_value=100.0 + MESSAGE_SECONDS[MESSAGE_INFO] - 0.1):
            self.app.expire_message()
            self.assertEqual(self.app.message, "switched")
        with mock.patch("bible_tui.tui.time.monotonic", return_value=100.0 + MESSAGE_SECONDS[MESSAGE_INFO]):
            self.app.expire_message()
            self.assertEqual(self.app.message, "")
            self.assertEqual(self.app.message_timeout_ms(), -1)

    def test_errors_stay_longer(self) -> None:
        self.assertGreater(MESSAGE_SECONDS[MESSAGE_ERROR], MESSAGE_SECONDS[MESSAGE_INFO])

    def test_yank_and_clipboard_failure_kinds(self) -> None:
        self.app.focus_pane(0)
        with mock.patch("bible_tui.tui.copy_to_clipboard", return_value=True):
            self.app.handle_key(ord("y"))
            self.app.handle_key(ord("y"))
        self.assertEqual((self.app.message, self.app.message_kind), ("yanked verse", MESSAGE_YANK))
        with mock.patch("bible_tui.tui.copy_to_clipboard", return_value=False):
            self.app.handle_key(ord("y"))
            self.app.handle_key(ord("y"))
        self.assertEqual((self.app.message, self.app.message_kind), ("clipboard unavailable", MESSAGE_ERROR))


if __name__ == "__main__":
    unittest.main()
