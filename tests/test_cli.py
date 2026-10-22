from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from bible_tui.cli import CliError, choose_version, main
from bible_tui.config import Settings
from bible_tui.paths import BUNDLED_BIBLES_DIR
from bible_tui.versions import discover_versions

from tests.helpers import make_bible


def run_cli(argv: list[str], env: dict[str, str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv, env)
    return code, out.getvalue(), err.getvalue()


class ChooseVersionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.discovery = discover_versions([BUNDLED_BIBLES_DIR])

    def choose(self, requested: str | None = None, default: str | None = None, last: str | None = None) -> str:
        state = {"last_version": last} if last else {}
        version, _ = choose_version(self.discovery, requested, Settings(default_version=default), state)
        return version.abbreviation

    def test_precedence(self) -> None:
        self.assertEqual(self.choose(), "ASV")
        self.assertEqual(self.choose(last="KJV"), "KJV")
        self.assertEqual(self.choose(default="KJV", last="ASV"), "KJV")
        self.assertEqual(self.choose(requested="asv", default="KJV", last="KJV"), "ASV")

    def test_unknown_default_falls_back_with_warning(self) -> None:
        version, warnings = choose_version(self.discovery, None, Settings(default_version="XYZ"), {"last_version": "KJV"})
        self.assertEqual(version.abbreviation, "KJV")
        self.assertEqual(len(warnings), 1)

    def test_unknown_requested_version_is_an_error(self) -> None:
        with self.assertRaisesRegex(CliError, "available: ASV, KJV"):
            self.choose(requested="XYZ")


class MainTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / "home"
        self.env = {"HOME": str(self.tmp), "BIBLE_TUI_HOME": str(self.home)}

    def test_list_versions_includes_drop_in_folder(self) -> None:
        make_bible(self.home / "bibles" / "web.sqlite", "WEB", "World English Bible")
        code, out, _ = run_cli(["--list-versions"], self.env)
        self.assertEqual(code, 0)
        self.assertIn("WEB  World English Bible", out)
        self.assertIn("KJV", out)

    def test_config_bibles_dirs_and_cli_dirs(self) -> None:
        make_bible(self.tmp / "from-config" / "a.sqlite", "AAA", "From Config")
        make_bible(self.tmp / "from-cli" / "b.sqlite", "BBB", "From CLI")
        self.home.mkdir()
        (self.home / "config.json").write_text(json.dumps({"bibles_dirs": [str(self.tmp / "from-config")]}))
        code, out, _ = run_cli(["-l", "-d", str(self.tmp / "from-cli")], self.env)
        self.assertEqual(code, 0)
        self.assertIn("AAA", out)
        self.assertIn("BBB", out)

    def test_database_path_as_version(self) -> None:
        path = make_bible(self.tmp / "loose.sqlite", "LSE", "Loose File")
        code, out, _ = run_cli(["-l", str(path)], self.env)
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("* LSE"))

    def test_errors_exit_1(self) -> None:
        self.assertEqual(run_cli(["XYZ"], self.env)[0], 1)
        self.assertEqual(run_cli(["-c", str(self.tmp / "missing.json")], self.env)[0], 1)
        self.home.mkdir()
        (self.home / "config.json").write_text("{bad")
        code, _, err = run_cli(["-l"], self.env)
        self.assertEqual(code, 1)
        self.assertIn("invalid JSON", err)

    def test_paths_does_not_create_anything(self) -> None:
        code, out, _ = run_cli(["--paths"], self.env)
        self.assertEqual(code, 0)
        self.assertIn("config.json", out)
        self.assertFalse(self.home.exists())


if __name__ == "__main__":
    unittest.main()
