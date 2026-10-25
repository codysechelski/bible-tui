from __future__ import annotations

import unittest
from unittest import mock

from bible_tui import __version__
from bible_tui.store import BibleStore
from bible_tui.tui import COMMANDS, MESSAGE_ERROR, MESSAGE_YANK, BibleTui
from bible_tui.update import REPOSITORY_URL, UpdateCheck
from bible_tui.versions import discover_versions, find_version

from tests.helpers import KJV_PATH, FakeScreen


def make_app(latest: str | None = None, checking: bool = False, checks: bool = True) -> BibleTui:
    check = None
    if checks:
        check = UpdateCheck(__version__, {}, fetch=lambda current: None)
        check.latest = latest
        if checking:
            check.thread = mock.Mock()
    versions = discover_versions([KJV_PATH.parent]).versions
    app = BibleTui(FakeScreen(), BibleStore(KJV_PATH), find_version(versions, "KJV"), versions, update_check=check)
    return app


class AboutTest(unittest.TestCase):
    def app(self, **kwargs: object) -> BibleTui:
        app = make_app(**kwargs)
        self.addCleanup(app.close)
        return app

    def test_opens_from_the_command_line_and_the_commands_list(self) -> None:
        app = self.app()
        command, _ = app.parse_ex_command("ab")
        app.run_ex_command(command, "")
        self.assertTrue(app.about_open)
        self.assertIn("about", [item.action for item in COMMANDS])

    def test_rows_show_the_version_and_link(self) -> None:
        rows = dict(self.app().about_rows())
        self.assertEqual(rows["Version"], __version__)
        self.assertEqual(rows["Project"], REPOSITORY_URL)
        self.assertEqual(rows["Reading"], "King James Version")

    def test_latest_row_follows_the_update_check(self) -> None:
        cases = {
            "update checks are off": {"checks": False},
            "checking...": {"checking": True},
            "couldn't check (offline?)": {},
            "up to date": {"latest": __version__},
            "99.0.0 is out (u to update)": {"latest": "99.0.0"},
        }
        for expected, kwargs in cases.items():
            self.assertEqual(dict(self.app(**kwargs).about_rows())["Latest"], expected, kwargs)

    def test_update_hint_only_when_there_is_one(self) -> None:
        self.assertNotIn("u", dict(self.app(latest=__version__).about_hints()))
        self.assertIn("u", dict(self.app(latest="99.0.0").about_hints()))

    def test_keys(self) -> None:
        app = self.app()
        app.open_about_modal()
        with mock.patch("bible_tui.tui.copy_to_clipboard", return_value=True) as copy:
            app.handle_key(ord("y"))
        copy.assert_called_once_with(REPOSITORY_URL)
        self.assertEqual(app.message_kind, MESSAGE_YANK)
        with mock.patch("bible_tui.tui.open_url", return_value=False):
            app.handle_key(ord("o"))
        self.assertEqual(app.message_kind, MESSAGE_ERROR)
        self.assertTrue(app.about_open)
        app.handle_key(27)
        self.assertFalse(app.about_open)

    def test_u_runs_the_update(self) -> None:
        app = self.app(latest="99.0.0")
        app.open_about_modal()
        with mock.patch.object(app, "run_update", return_value=False) as run_update:
            self.assertFalse(app.handle_key(ord("u")))
        run_update.assert_called_once()
        self.assertFalse(app.about_open)

    def test_u_does_nothing_without_an_update(self) -> None:
        app = self.app(latest=__version__)
        app.open_about_modal()
        with mock.patch.object(app, "run_update") as run_update:
            self.assertTrue(app.handle_key(ord("u")))
        run_update.assert_not_called()
        self.assertTrue(app.about_open)


if __name__ == "__main__":
    unittest.main()
