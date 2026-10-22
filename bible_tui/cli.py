"""Command line entry point: resolve paths and settings, pick a version, run the TUI."""

from __future__ import annotations

import argparse
import curses
import locale
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from bible_tui import __version__
from bible_tui.config import ConfigError, Settings, load_settings, load_state, save_state
from bible_tui.paths import (
    BIBLES_DIR_NAME,
    BUNDLED_BIBLES_DIR,
    CONFIG_FILE_NAME,
    STATE_FILE_NAME,
    home_candidates,
    resolve_home,
)
from bible_tui.versions import (
    BibleVersion,
    Discovery,
    VersionError,
    discover_versions,
    find_version,
    inspect_database,
)


class CliError(Exception):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bible-tui",
        description="Browse the Bible in your terminal.",
    )
    parser.add_argument(
        "bible",
        nargs="?",
        metavar="VERSION",
        help="version to open: an abbreviation such as KJV, or a path to a .sqlite file",
    )
    parser.add_argument(
        "-d",
        "--bibles-dir",
        action="append",
        default=[],
        type=Path,
        metavar="DIR",
        help="also load Bible databases from DIR (repeatable; searched before the defaults)",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        metavar="FILE",
        help=f"use FILE instead of {CONFIG_FILE_NAME} in the app home",
    )
    parser.add_argument("-l", "--list-versions", action="store_true", help="list available versions and exit")
    parser.add_argument("--paths", action="store_true", help="show where bible-tui looks for files and exit")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def bibles_search_path(home: Path, settings: Settings, extra_dirs: Sequence[Path]) -> list[Path]:
    """Directories scanned for databases, highest priority first."""
    return [
        *(directory.expanduser() for directory in extra_dirs),
        *settings.bibles_dirs,
        home / BIBLES_DIR_NAME,
        BUNDLED_BIBLES_DIR,
    ]


def choose_version(
    discovery: Discovery,
    requested: str | None,
    settings: Settings,
    state: Mapping[str, object],
) -> tuple[BibleVersion, list[str]]:
    """Pick the version to open: the command line, then ``default_version``, then the
    last version used, then the first available."""
    warnings: list[str] = []
    versions = discovery.versions
    if requested:
        version = find_version(versions, requested)
        if version is None:
            available = ", ".join(v.abbreviation for v in versions) or "none"
            raise CliError(f"unknown version {requested!r} (available: {available})")
        return version, warnings
    if settings.default_version:
        version = find_version(versions, settings.default_version)
        if version is not None:
            return version, warnings
        warnings.append(f"default_version {settings.default_version!r} not found; ignoring it")
    last = state.get("last_version")
    if isinstance(last, str):
        version = find_version(versions, last)
        if version is not None:
            return version, warnings
    if not versions:
        raise CliError("no Bible databases found (run `bible-tui --paths` to see where to put them)")
    return versions[0], warnings


def describe(path: Path) -> str:
    home = str(Path.home())
    text = str(path)
    return "~" + text[len(home) :] if text == home or text.startswith(home + os.sep) else text


def print_paths(home: Path, config_path: Path, search_path: Sequence[Path], env: Mapping[str, str]) -> None:
    def status(path: Path) -> str:
        return "" if path.exists() else "  (missing)"

    print("App home lookup (first existing wins):")
    for candidate in home_candidates(env):
        marker = "*" if candidate == home else " "
        print(f"  {marker} {describe(candidate)}{status(candidate)}")
    print(f"\nConfig: {describe(config_path)}{status(config_path)}")
    state_path = home / STATE_FILE_NAME
    print(f"State:  {describe(state_path)}{status(state_path)}")
    print("\nBible folders (earlier folders win when versions share a name):")
    for index, directory in enumerate(search_path, 1):
        print(f"  {index}. {describe(directory)}{status(directory)}")


def print_versions(discovery: Discovery, current: BibleVersion | None) -> None:
    if not discovery.versions:
        print("No Bible databases found.")
    width = max((len(version.abbreviation) for version in discovery.versions), default=0)
    for version in discovery.versions:
        marker = "*" if version == current else " "
        name = version.name if version.name != version.abbreviation else ""
        print(f"{marker} {version.abbreviation.ljust(width)}  {name}".rstrip())
        print(f"  {' ' * width}  {describe(version.path)}")
    if discovery.skipped:
        print("\nSkipped:")
        for path, reason in discovery.skipped:
            print(f"  {describe(path)}: {reason}")


def run_tui(
    version: BibleVersion,
    versions: Sequence[BibleVersion],
    settings: Settings,
    home: Path,
    state: dict[str, object],
    warnings: Sequence[str] = (),
) -> None:
    from bible_tui.store import BibleStore
    from bible_tui.tui import BibleTui

    def remember(chosen: BibleVersion) -> None:
        state["last_version"] = chosen.abbreviation
        save_state(home, state)

    def run(stdscr: curses.window) -> None:
        app = BibleTui(
            stdscr,
            BibleStore(version.path),
            version,
            versions,
            alphabetical=settings.book_order == "alphabetical",
            on_version_change=remember,
        )
        if warnings:
            app.message = f"warning: {warnings[0]}"
        try:
            app.run()
        finally:
            app.store.close()

    curses.wrapper(run)


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    env = os.environ if env is None else env
    args = build_parser().parse_args(argv)
    try:
        home = resolve_home(env)
        if args.config is not None and not args.config.exists():
            raise CliError(f"config file not found: {args.config}")
        config_path = args.config if args.config is not None else home / CONFIG_FILE_NAME
        settings = load_settings(config_path, env)
        for warning in settings.warnings:
            print(f"bible-tui: warning: {warning}", file=sys.stderr)
        search_path = bibles_search_path(home, settings, args.bibles_dir)

        if args.paths:
            print_paths(home, config_path, search_path, env)
            return 0

        discovery = discover_versions(search_path)
        if args.bible and Path(args.bible).expanduser().is_file():
            try:
                opened = inspect_database(Path(args.bible).expanduser())
            except VersionError as error:
                raise CliError(f"{args.bible}: not a usable Bible database ({error})") from None
            others = tuple(v for v in discovery.versions if v.abbreviation.casefold() != opened.abbreviation.casefold())
            discovery = Discovery((opened, *others), discovery.skipped)
            args.bible = opened.abbreviation

        state = load_state(home)
        if args.list_versions:
            current = None
            try:
                current, _ = choose_version(discovery, args.bible, settings, state)
            except CliError:
                pass
            print_versions(discovery, current)
            return 0

        version, choice_warnings = choose_version(discovery, args.bible, settings, state)
        for warning in choice_warnings:
            print(f"bible-tui: warning: {warning}", file=sys.stderr)
        warnings = [*settings.warnings, *choice_warnings]
    except (CliError, ConfigError) as error:
        print(f"bible-tui: {error}", file=sys.stderr)
        return 1

    locale.setlocale(locale.LC_ALL, "")
    run_tui(version, discovery.versions, settings, home, state, warnings)
    return 0
