from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bible_tui.config import ConfigError, Settings, load_settings, load_state, save_state
from bible_tui.paths import home_candidates, resolve_home


class HomeResolutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.env = {"HOME": str(self.tmp)}

    def test_defaults_to_xdg_location_when_nothing_exists(self) -> None:
        self.assertEqual(resolve_home(self.env), self.tmp / ".config" / "bible-tui")

    def test_dot_directory_wins_when_it_exists(self) -> None:
        (self.tmp / ".bible-tui").mkdir()
        (self.tmp / ".config" / "bible-tui").mkdir(parents=True)
        self.assertEqual(resolve_home(self.env), self.tmp / ".bible-tui")

    def test_existing_xdg_directory_is_used(self) -> None:
        (self.tmp / ".config" / "bible-tui").mkdir(parents=True)
        self.assertEqual(resolve_home(self.env), self.tmp / ".config" / "bible-tui")

    def test_xdg_config_home_is_respected(self) -> None:
        env = {**self.env, "XDG_CONFIG_HOME": str(self.tmp / "cfg")}
        self.assertEqual(resolve_home(env), self.tmp / "cfg" / "bible-tui")

    def test_relative_xdg_config_home_is_ignored(self) -> None:
        env = {**self.env, "XDG_CONFIG_HOME": "relative/cfg"}
        self.assertEqual(resolve_home(env), self.tmp / ".config" / "bible-tui")

    def test_explicit_home_wins_even_if_missing(self) -> None:
        (self.tmp / ".bible-tui").mkdir()
        env = {**self.env, "BIBLE_TUI_HOME": "~/custom"}
        self.assertEqual(resolve_home(env), self.tmp / "custom")
        self.assertEqual(home_candidates(env)[0], self.tmp / "custom")


class SettingsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.path = self.tmp / "config.json"
        self.env = {"HOME": str(self.tmp)}

    def write(self, data: object) -> None:
        self.path.write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")

    def test_missing_file_gives_defaults(self) -> None:
        self.assertEqual(load_settings(self.path, self.env), Settings())

    def test_reads_settings_and_resolves_directories(self) -> None:
        self.write({"default_version": "KJV", "bibles_dirs": ["~/Bibles", "local", "/abs"], "book_order": "alphabetical"})
        settings = load_settings(self.path, self.env)
        self.assertEqual(settings.default_version, "KJV")
        self.assertEqual(settings.bibles_dirs, (self.tmp / "Bibles", self.tmp / "local", Path("/abs")))
        self.assertEqual(settings.book_order, "alphabetical")

    def test_single_directory_string_is_accepted(self) -> None:
        self.write({"bibles_dirs": "/abs"})
        self.assertEqual(load_settings(self.path, self.env).bibles_dirs, (Path("/abs"),))

    def test_unknown_keys_warn(self) -> None:
        self.write({"colour": "blue"})
        self.assertEqual(len(load_settings(self.path, self.env).warnings), 1)

    def test_invalid_values_raise(self) -> None:
        for data in ("{nope", [], {"book_order": "random"}, {"bibles_dirs": [1]}, {"default_version": 3}):
            with self.subTest(data=data):
                self.write(data)
                with self.assertRaises(ConfigError):
                    load_settings(self.path, self.env)


class StateTest(unittest.TestCase):
    def test_round_trip_and_creates_home(self) -> None:
        home = Path(tempfile.mkdtemp()) / "new" / "home"
        save_state(home, {"last_version": "ASV"})
        self.assertEqual(load_state(home), {"last_version": "ASV"})
        self.assertEqual([path.name for path in home.iterdir()], ["state.json"])

    def test_corrupt_state_is_ignored(self) -> None:
        home = Path(tempfile.mkdtemp())
        (home / "state.json").write_text("{broken", encoding="utf-8")
        self.assertEqual(load_state(home), {})


if __name__ == "__main__":
    unittest.main()
