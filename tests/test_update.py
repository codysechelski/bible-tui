from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from bible_tui import __version__
from bible_tui.cli import update_notice
from bible_tui.config import ConfigError, load_settings
from bible_tui.store import BibleStore
from bible_tui.tui import MESSAGE_ERROR, MESSAGE_UPDATE, UPDATE_POLL_MS, BibleTui
from bible_tui.update import (
    CHECK_INTERVAL_SECONDS,
    STATE_LAST_CHECK,
    STATE_LATEST,
    UPDATED_FROM_ENV,
    Install,
    UpdateCheck,
    detect_install,
    format_position,
    is_newer,
    parse_position,
    parse_version,
)
from bible_tui.versions import discover_versions, find_version

from tests.helpers import KJV_PATH, FakeScreen


NOW = 1_800_000_000.0


def make_check(state: dict[str, object], latest: str | None = "9.0.0", **kwargs: object) -> UpdateCheck:
    return UpdateCheck("0.2.0", state, fetch=lambda current: latest, now=lambda: NOW, **kwargs)


def finish(check: UpdateCheck) -> None:
    if check.thread is not None:
        check.thread.join(5)


class VersionTest(unittest.TestCase):
    def test_parse_version(self) -> None:
        self.assertEqual(parse_version("v0.3.0"), (0, 3, 0))
        self.assertEqual(parse_version("1.10"), (1, 10))
        for text in ("v1.0.0-rc.1", "latest", "", None, 3):
            self.assertIsNone(parse_version(text))

    def test_is_newer_compares_numerically(self) -> None:
        self.assertTrue(is_newer("0.10.0", "0.9.0"))
        self.assertFalse(is_newer("0.2.0", "0.2.0"))
        self.assertFalse(is_newer("0.1.9", "0.2.0"))
        self.assertFalse(is_newer(None, "0.2.0"))


class UpdateCheckTest(unittest.TestCase):
    def test_fresh_check_records_the_result_and_reports_once(self) -> None:
        state: dict[str, object] = {}
        saves: list[dict[str, object]] = []
        check = make_check(state, save=lambda: saves.append(dict(state)))
        check.start()
        self.assertTrue(check.pending)
        finish(check)
        self.assertEqual(check.poll(), "9.0.0")
        self.assertFalse(check.pending)
        self.assertEqual(state, {STATE_LAST_CHECK: int(NOW), STATE_LATEST: "9.0.0"})
        self.assertEqual(len(saves), 1)
        self.assertIsNone(check.poll())

    def test_poll_waits_for_the_thread(self) -> None:
        release = threading.Event()

        def slow_fetch(current: str) -> str:
            release.wait(5)
            return "9.0.0"

        check = UpdateCheck("0.2.0", {}, fetch=slow_fetch, now=lambda: NOW)
        check.start()
        self.assertIsNone(check.poll())
        self.assertTrue(check.pending)
        release.set()
        finish(check)
        self.assertEqual(check.poll(), "9.0.0")

    def test_failed_check_leaves_state_alone(self) -> None:
        state: dict[str, object] = {"last_version": "KJV"}
        check = make_check(state, latest=None)
        check.start()
        finish(check)
        self.assertIsNone(check.poll())
        self.assertEqual(state, {"last_version": "KJV"})
        self.assertIsNone(check.latest)

    def test_same_version_is_not_reported(self) -> None:
        check = make_check({}, latest="0.2.0")
        check.start()
        finish(check)
        self.assertIsNone(check.poll())
        self.assertFalse(check.update_available)
        self.assertEqual(check.latest, "0.2.0")

    def test_recent_check_uses_the_cache_without_fetching(self) -> None:
        state: dict[str, object] = {STATE_LAST_CHECK: NOW - 60, STATE_LATEST: "0.5.0"}
        check = UpdateCheck("0.2.0", state, fetch=mock.Mock(side_effect=AssertionError), now=lambda: NOW)
        check.start()
        self.assertFalse(check.pending)
        self.assertEqual(check.poll(), "0.5.0")

    def test_stale_or_odd_timestamps_check_again(self) -> None:
        for last in (NOW - CHECK_INTERVAL_SECONDS, NOW + 3600, "yesterday", True):
            self.assertTrue(make_check({STATE_LAST_CHECK: last}).due(), last)

    def test_save_failure_is_ignored(self) -> None:
        check = make_check({}, save=mock.Mock(side_effect=OSError("read-only")))
        check.start()
        finish(check)
        self.assertEqual(check.poll(), "9.0.0")


class DetectInstallTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.package = self.tmp / "repo" / "bible_tui"
        self.package.mkdir(parents=True)
        self.venv = self.tmp / "venv"
        self.venv.mkdir()
        which = mock.patch("bible_tui.update.shutil.which", side_effect=lambda name: f"/bin/{name}")
        which.start()
        self.addCleanup(which.stop)

    def write_pipx_metadata(self, spec: str) -> None:
        data = {"main_package": {"package_or_url": spec}}
        (self.venv / "pipx_metadata.json").write_text(json.dumps(data), encoding="utf-8")

    def test_pipx_upgrades(self) -> None:
        self.write_pipx_metadata("git+https://github.com/codysechelski/bible-tui")
        install = detect_install(self.package, str(self.venv))
        self.assertEqual(install, Install("pipx", ("/bin/pipx", "upgrade", "bible-tui")))

    def test_pipx_pinned_to_a_tag_reinstalls_from_the_repo(self) -> None:
        self.write_pipx_metadata("git+https://github.com/codysechelski/bible-tui@v0.1.0")
        install = detect_install(self.package, str(self.venv))
        self.assertEqual(
            install.command,
            ("/bin/pipx", "install", "--force", "git+https://github.com/codysechelski/bible-tui"),
        )

    def test_git_clone_pulls(self) -> None:
        repo = self.package.parent
        (repo / ".git").mkdir()
        (repo / "pyproject.toml").write_text("", encoding="utf-8")
        install = detect_install(self.package, str(self.venv))
        self.assertEqual(install, Install("git", ("/bin/git", "-C", str(repo), "pull", "--ff-only")))

    def test_anything_else_is_manual(self) -> None:
        self.assertIsNone(detect_install(self.package, str(self.venv)))

    def test_missing_tool_is_manual(self) -> None:
        self.write_pipx_metadata("bible-tui")
        with mock.patch("bible_tui.update.shutil.which", return_value=None):
            self.assertIsNone(detect_install(self.package, str(self.venv)))


def make_app(check: UpdateCheck | None = None, install: Install | None = None) -> BibleTui:
    versions = discover_versions([KJV_PATH.parent]).versions
    return BibleTui(
        FakeScreen(),
        BibleStore(KJV_PATH),
        find_version(versions, "KJV"),
        versions,
        update_check=check,
        install=install,
    )


class TuiUpdateTest(unittest.TestCase):
    def test_new_release_is_announced(self) -> None:
        check = make_check({})
        check.start()
        finish(check)
        app = make_app(check)
        self.addCleanup(app.close)
        app.poll_update_check()
        self.assertEqual(app.message_kind, MESSAGE_UPDATE)
        self.assertIn("9.0.0 is out", app.message)

    def test_notice_waits_for_the_current_message(self) -> None:
        check = make_check({})
        check.start()
        finish(check)
        app = make_app(check)
        self.addCleanup(app.close)
        app.show_error("save failed")
        app.poll_update_check()
        self.assertEqual(app.message, "save failed")
        app.message = ""
        app.poll_update_check()
        self.assertIn("9.0.0", app.message)

    def test_input_timeout_polls_while_checking(self) -> None:
        check = make_check({})
        app = make_app(check)
        self.addCleanup(app.close)
        self.assertEqual(app.input_timeout_ms(), -1)
        check.thread = mock.Mock()  # Pretend the check is still out.
        self.assertEqual(app.input_timeout_ms(), UPDATE_POLL_MS)

    def test_update_when_already_latest_does_nothing(self) -> None:
        check = make_check({}, latest="0.2.0")
        check.start()
        finish(check)
        check.poll()
        app = make_app(check, Install("git", ("git", "pull")))
        self.addCleanup(app.close)
        with mock.patch("bible_tui.tui.subprocess.run") as run:
            self.assertTrue(app.run_update())
        run.assert_not_called()
        self.assertIn("up to date", app.message)

    def test_update_without_a_known_install_explains(self) -> None:
        app = make_app()
        self.addCleanup(app.close)
        self.assertTrue(app.run_update())
        self.assertEqual(app.message_kind, MESSAGE_ERROR)
        self.assertIn("pipx upgrade bible-tui", app.message)

    def test_successful_update_requests_a_restart(self) -> None:
        app = make_app(install=Install("git", ("git", "pull")))
        self.addCleanup(app.close)
        app.stdscr = mock.Mock()
        with mock.patch("bible_tui.tui.curses") as curses, mock.patch("bible_tui.tui.subprocess.run") as run, \
                mock.patch("builtins.print"):
            run.return_value.returncode = 0
            self.assertFalse(app.run_update())
        curses.endwin.assert_called_once()
        # Back in curses mode so curses.wrapper can end it cleanly.
        curses.reset_prog_mode.assert_called_once()
        self.assertTrue(app.restart_requested)

    def test_failed_update_returns_to_the_app(self) -> None:
        app = make_app(install=Install("git", ("git", "pull")))
        self.addCleanup(app.close)
        app.stdscr = mock.Mock()
        with mock.patch("bible_tui.tui.curses") as curses, mock.patch("bible_tui.tui.subprocess.run") as run, \
                mock.patch("builtins.print"), mock.patch("builtins.input", return_value=""):
            run.return_value.returncode = 1
            self.assertTrue(app.run_update())
        curses.reset_prog_mode.assert_called_once()
        self.assertFalse(app.restart_requested)
        self.assertIn("update failed", app.message)

    def test_update_is_an_ex_command(self) -> None:
        app = make_app()
        self.addCleanup(app.close)
        command, _ = app.parse_ex_command("up")
        self.assertEqual(command.name, "update")


class RestartPositionTest(unittest.TestCase):
    def test_position_round_trip(self) -> None:
        self.assertEqual(parse_position(format_position((43, 3, 16))), (43, 3, 16))
        self.assertEqual(format_position((None, None, None)), "")
        for text in (None, "", "-", "43:3", "a:b:c", "43:3:16:1"):
            self.assertIsNone(parse_position(text))

    def test_successful_update_remembers_the_place(self) -> None:
        app = make_app(install=Install("git", ("git", "pull")))
        self.addCleanup(app.close)
        self.assertTrue(app.jump_to_key((43, 3, 16)))
        app.stdscr = mock.Mock()
        with mock.patch("bible_tui.tui.curses"), mock.patch("bible_tui.tui.subprocess.run") as run, \
                mock.patch("builtins.print"):
            run.return_value.returncode = 0
            app.run_update()
        self.assertEqual(app.restart_position, (43, 3, 16))


class NoticeAndSettingTest(unittest.TestCase):
    def test_update_notice_after_restart(self) -> None:
        self.assertEqual(update_notice({}), "")
        self.assertIn("up to date", update_notice({UPDATED_FROM_ENV: __version__}))
        self.assertEqual(update_notice({UPDATED_FROM_ENV: "0.0.1"}), f"updated bible-tui 0.0.1 to {__version__}")

    def test_check_for_updates_setting(self) -> None:
        path = Path(tempfile.mkdtemp()) / "config.json"
        self.assertTrue(load_settings(path).check_for_updates)
        path.write_text('{"check_for_updates": false}', encoding="utf-8")
        self.assertFalse(load_settings(path).check_for_updates)
        path.write_text('{"check_for_updates": "no"}', encoding="utf-8")
        with self.assertRaisesRegex(ConfigError, "check_for_updates must be true or false"):
            load_settings(path)


if __name__ == "__main__":
    unittest.main()
