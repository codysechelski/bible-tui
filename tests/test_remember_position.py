from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bible_tui.cli import remembered_position
from bible_tui.config import ConfigError, Settings, load_settings


class RememberPositionTest(unittest.TestCase):
    def test_setting(self) -> None:
        config = Path(tempfile.mkdtemp()) / "config.json"
        self.assertFalse(load_settings(config).remember_position)
        config.write_text(json.dumps({"remember_position": True}), encoding="utf-8")
        settings = load_settings(config)
        self.assertTrue(settings.remember_position)
        self.assertEqual(settings.warnings, ())
        config.write_text(json.dumps({"remember_position": "yes"}), encoding="utf-8")
        with self.assertRaises(ConfigError):
            load_settings(config)

    def test_restores_only_when_enabled(self) -> None:
        state = {"position": "43:3:16"}
        self.assertIsNone(remembered_position(Settings(), state))
        self.assertEqual(remembered_position(Settings(remember_position=True), state), (43, 3, 16))

    def test_ignores_bad_state(self) -> None:
        settings = Settings(remember_position=True)
        for state in ({}, {"position": "43:3"}, {"position": [43, 3, 16]}, {"position": "a:b:c"}):
            with self.subTest(state=state):
                self.assertIsNone(remembered_position(settings, state))


if __name__ == "__main__":
    unittest.main()
