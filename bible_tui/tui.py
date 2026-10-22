"""Curses TUI for browsing a Bible version's SQLite database."""

from __future__ import annotations

import curses
import re
import shutil
import sqlite3
import subprocess
import sys
import termios
import textwrap
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from bible_tui.store import BOOK_ABBREVIATIONS, BibleStore, BibleVerse, Book, Verse
from bible_tui.versions import BibleVersion

FOCUS_BOOKS = 0
FOCUS_CHAPTERS = 1
FOCUS_TEXT = 2
KEY_CTRL_P = 16
KEY_CTRL_F = 6
KEY_CTRL_G = 7
KEY_CTRL_N = 14
KEY_CTRL_S = 19
PAIR_SEARCH = 8
PAIR_ERROR = 9
PAIR_HEADING = 10


@dataclass(frozen=True)
class RenderLine:
    verse_index: int
    verse_number: str
    text: str
    start_col: int


@dataclass(frozen=True)
class Command:
    name: str
    keybind: str
    action: str


@dataclass(frozen=True)
class SearchResult:
    item_index: int
    start_col: int = 0
    end_col: int = 0


@dataclass(frozen=True)
class FuzzyMatch:
    verse: BibleVerse
    score: int
    positions: tuple[int, ...]


COMMAND_GROUPS: tuple[tuple[str, tuple[Command, ...]], ...] = (
    (
        "Navigation",
        (
            Command("move up", "k / up", "move_up"),
            Command("move down", "j / down", "move_down"),
            Command("move left", "h / left", "move_left"),
            Command("move right", "l / right", "move_right"),
            Command("page up", "page up", "page_up"),
            Command("page down", "page down", "page_down"),
            Command("first item", "home", "home"),
            Command("last item", "end", "end"),
        ),
    ),
    (
        "Search",
        (
            Command("search", "/", "search"),
            Command("fuzzy find", "ctrl+f", "fuzzy_find"),
            Command("go to reference", "ctrl+g", "go_to_reference"),
            Command("next match", "n", "next_match"),
            Command("previous match", "N", "previous_match"),
        ),
    ),
    (
        "Selection",
        (
            Command("select", "enter", "select"),
            Command("visual mode", "v", "visual_mode"),
            Command("yank selection", "y", "yank_selection"),
            Command("yank verse", "yy", "yank_verse"),
        ),
    ),
    (
        "View",
        (
            Command("switch version", "t", "switch_version"),
            Command("toggle sort", "a", "toggle_sort"),
        ),
    ),
    (
        "General",
        (Command("quit", "q", "quit"),),
    ),
)

COMMANDS: tuple[Command, ...] = tuple(
    command for _, commands in COMMAND_GROUPS for command in commands
)


def _build_command_rows() -> tuple[tuple[str, object], ...]:
    rows: list[tuple[str, object]] = []
    index = 0
    for heading, commands in COMMAND_GROUPS:
        rows.append(("heading", heading))
        for _ in commands:
            rows.append(("command", index))
            index += 1
    return tuple(rows)


COMMAND_ROWS: tuple[tuple[str, object], ...] = _build_command_rows()
COMMAND_ROW_INDEX: dict[int, int] = {
    payload: row for row, (kind, payload) in enumerate(COMMAND_ROWS) if kind == "command"
}

SEARCH_HINTS: tuple[tuple[str, str], ...] = (
    ("Next", "n"),
    ("Previous", "N"),
    ("Quit Search", "esc"),
    ("Search Again", "/"),
)

FUZZY_HELP_ROWS: tuple[tuple[str, str, str], ...] = (
    ("fuzzy", "lite", 'loose, typo-tolerant match — still finds "light"'),
    ("exact", "'faith", 'exact substring — also matches "faithful", "faithfulness"'),
    ("word", "'year'", 'exact whole word — matches "year" but not "years"'),
    ("prefix", "^blessed", 'verses that begin with "blessed"'),
    ("suffix", "wept.$", 'verses that end with "wept."'),
    ("exclude", "comfort !fear", 'verses about "comfort" that do NOT mention "fear"'),
    ("combine", "love neighbor", 'verses containing both "love" and "neighbor"'),
)


class BibleTui:
    def __init__(
        self,
        stdscr: curses.window,
        store: BibleStore,
        version: BibleVersion,
        versions: Sequence[BibleVersion] = (),
        *,
        alphabetical: bool = False,
        on_version_change: Callable[[BibleVersion], None] | None = None,
    ) -> None:
        self.stdscr = stdscr
        self.store = store
        self.version = version
        self.versions: tuple[BibleVersion, ...] = tuple(versions) or (version,)
        self.on_version_change = on_version_change
        self.version_modal_open = False
        self.version_cursor = 0
        self.version_scroll = 0
        self.alphabetical = alphabetical
        self.books = store.books(self.alphabetical)
        self.book_rows: tuple[tuple[str, object], ...] = ()
        self.book_row_index: dict[int, int] = {}
        self.rebuild_book_rows()
        self.chapters: list[int] = []
        self.verses: list[Verse] = []

        self.focus = FOCUS_BOOKS
        self.book_cursor = 0
        self.chapter_cursor = 0
        self.text_scroll = 0
        self.selected_book: Book | None = None
        self.selected_chapter: int | None = None
        self.book_scroll = 0
        self.chapter_scroll = 0
        self.verse_cursor = 0
        self.text_cursor_col = 0
        self.visual_mode = False
        self.visual_anchor: tuple[int, int] | None = None
        self.pending_y = False
        self.message = ""
        self.command_modal_open = False
        self.command_cursor = 0
        self.command_scroll = 0
        self.search_scope: int | None = None
        self.search_query = ""
        self.search_input_active = False
        self.search_result_cursor = 0
        self.all_verses: list[BibleVerse] | None = None
        self.fuzzy_open = False
        self.fuzzy_help_open = False
        self.fuzzy_query = ""
        self.fuzzy_cursor = 0
        self.fuzzy_scroll = 0
        self.fuzzy_matches: list[FuzzyMatch] = []
        self.goto_open = False
        self.goto_query = ""
        self.goto_error = False
        self.goto_suggestion_cursor = 0
        self.goto_scroll = 0
        self.goto_verse_cache: dict[tuple[int, int], list[Verse]] = {}
        if self.books:
            self.select_book(self.book_cursor)

    def run(self) -> None:
        self.set_cursor_visibility(False)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(2, curses.COLOR_WHITE, -1)
        curses.init_pair(3, curses.COLOR_YELLOW, -1)
        curses.init_pair(4, curses.COLOR_WHITE, -1)
        curses.init_pair(5, curses.COLOR_GREEN, -1)
        curses.init_pair(6, curses.COLOR_BLACK, curses.COLOR_WHITE)
        curses.init_pair(7, curses.COLOR_RED, -1)
        orange = 208 if getattr(curses, "COLORS", 0) > 208 else curses.COLOR_YELLOW
        try:
            curses.init_pair(PAIR_SEARCH, orange, -1)
        except curses.error:
            curses.init_pair(PAIR_SEARCH, curses.COLOR_YELLOW, -1)
        curses.init_pair(PAIR_ERROR, curses.COLOR_RED, -1)
        curses.init_pair(PAIR_HEADING, curses.COLOR_BLUE, -1)
        try:
            curses.set_escdelay(25)
        except AttributeError:
            pass
        try:
            fd = sys.stdin.fileno()
            attrs = termios.tcgetattr(fd)
            attrs[0] &= ~termios.IXON
            termios.tcsetattr(fd, termios.TCSANOW, attrs)
        except termios.error:
            pass
        self.stdscr.keypad(True)
        self.stdscr.timeout(-1)

        while True:
            self.draw()
            key = self.stdscr.getch()
            if not self.handle_key(key):
                return

    def handle_key(self, key: int) -> bool:
        if self.version_modal_open:
            return self.handle_version_modal_key(key)
        if self.goto_open:
            return self.handle_goto_key(key)
        if self.fuzzy_open:
            return self.handle_fuzzy_key(key)
        if self.command_modal_open:
            return self.handle_command_modal_key(key)
        if self.search_input_active:
            self.handle_search_input_key(key)
            return True
        if key == KEY_CTRL_P:
            self.open_command_modal()
            return True
        if key == KEY_CTRL_F:
            self.open_fuzzy_finder()
            return True
        if key == KEY_CTRL_G:
            self.open_goto_modal()
            return True
        if key == 27:
            if self.search_scope is not None:
                self.clear_search()
            elif self.visual_mode:
                self.exit_visual_mode()
            return True
        if key == ord("q"):
            return False
        if key == ord("/") and self.search_scope is not None:
            self.edit_search()
            return True
        if key == ord("/") and self.focus in (FOCUS_BOOKS, FOCUS_CHAPTERS, FOCUS_TEXT):
            self.open_search()
            return True
        if key in (ord("n"), ord("N")) and self.search_scope is not None:
            self.pending_y = False
            self.jump_search_match(1 if key == ord("n") else -1)
            return True
        if key == ord("a"):
            self.pending_y = False
            self.toggle_book_order()
            return True
        if key == ord("t"):
            self.open_version_modal()
            return True
        if key == ord("v") and self.focus == FOCUS_TEXT and self.verses:
            self.pending_y = False
            self.enter_visual_mode()
            return True
        if key == ord("y") and self.focus == FOCUS_TEXT and self.verses:
            self.handle_yank_key()
            return True
        if key in (ord("h"), ord("l")) and self.focus == FOCUS_TEXT and self.verses:
            self.pending_y = False
            self.move_text_cursor(-1 if key == ord("h") else 1)
            return True
        if key == curses.KEY_LEFT:
            self.pending_y = False
            self.move_focus_left()
            return True
        if key == curses.KEY_RIGHT:
            self.pending_y = False
            self.move_focus_right()
            return True
        if key in (ord("h"), ord("l")):
            self.pending_y = False
            if key == ord("h"):
                self.move_focus_left()
            else:
                self.move_focus_right()
            return True
        if key in (ord("\n"), curses.KEY_ENTER, 10, 13):
            self.pending_y = False
            self.activate_selection()
            return True
        if key in (curses.KEY_UP, ord("k")):
            self.pending_y = False
            self.move_vertical(-1)
            return True
        if key in (curses.KEY_DOWN, ord("j")):
            self.pending_y = False
            self.move_vertical(1)
            return True
        if key == curses.KEY_PPAGE:
            self.pending_y = False
            self.page(-1)
            return True
        if key == curses.KEY_NPAGE:
            self.pending_y = False
            self.page(1)
            return True
        if key == curses.KEY_HOME:
            self.pending_y = False
            self.home()
            return True
        if key == curses.KEY_END:
            self.pending_y = False
            self.end()
            return True
        self.pending_y = False
        return True

    def handle_command_modal_key(self, key: int) -> bool:
        if key == 27:
            self.close_command_modal()
            return True
        if key in (curses.KEY_UP, ord("k")):
            self.command_cursor = clamp(self.command_cursor - 1, 0, len(COMMANDS) - 1)
            self.ensure_command_visible()
            return True
        if key in (curses.KEY_DOWN, ord("j")):
            self.command_cursor = clamp(self.command_cursor + 1, 0, len(COMMANDS) - 1)
            self.ensure_command_visible()
            return True
        if key in (ord("\n"), curses.KEY_ENTER, 10, 13):
            action = COMMANDS[self.command_cursor].action
            self.close_command_modal()
            return self.run_command(action)
        return True

    def run_command(self, action: str) -> bool:
        self.pending_y = False
        if action == "quit":
            return False
        if action == "select":
            self.activate_selection()
        elif action == "search":
            if self.search_scope is not None:
                self.edit_search()
            else:
                self.open_search()
        elif action == "fuzzy_find":
            self.open_fuzzy_finder()
        elif action == "go_to_reference":
            self.open_goto_modal()
        elif action == "next_match":
            self.jump_search_match(1)
        elif action == "previous_match":
            self.jump_search_match(-1)
        elif action == "move_up":
            self.move_vertical(-1)
        elif action == "move_down":
            self.move_vertical(1)
        elif action == "move_left":
            self.move_focus_left()
        elif action == "move_right":
            self.move_focus_right()
        elif action == "page_up":
            self.page(-1)
        elif action == "page_down":
            self.page(1)
        elif action == "home":
            self.home()
        elif action == "end":
            self.end()
        elif action == "toggle_sort":
            self.toggle_book_order()
        elif action == "switch_version":
            self.open_version_modal()
        elif action == "visual_mode":
            if self.focus == FOCUS_TEXT and self.verses:
                self.enter_visual_mode()
            else:
                self.message = "select text to use visual mode"
        elif action == "yank_selection":
            if self.visual_mode:
                text = self.selected_text()
                if text:
                    self.yank_to_clipboard(text, "selection")
                self.exit_visual_mode()
            else:
                self.message = "no visual selection"
        elif action == "yank_verse":
            if self.focus == FOCUS_TEXT and self.verses:
                self.yank_to_clipboard(self.verses[self.verse_cursor].text, "verse")
            else:
                self.message = "no verse selected"
        return True

    def open_command_modal(self) -> None:
        self.pending_y = False
        self.command_modal_open = True
        self.ensure_command_visible()

    def close_command_modal(self) -> None:
        self.command_modal_open = False

    def open_version_modal(self) -> None:
        self.pending_y = False
        self.exit_visual_mode()
        self.command_modal_open = False
        self.search_input_active = False
        self.version_modal_open = True
        self.version_cursor = next(
            (index for index, version in enumerate(self.versions) if version == self.version),
            0,
        )
        self.version_scroll = 0
        self.ensure_version_visible()
        self.message = ""

    def close_version_modal(self) -> None:
        self.version_modal_open = False

    def handle_version_modal_key(self, key: int) -> bool:
        if key in (27, ord("t")):
            self.close_version_modal()
            return True
        if key in (curses.KEY_UP, ord("k")):
            self.version_cursor = clamp(self.version_cursor - 1, 0, len(self.versions) - 1)
            self.ensure_version_visible()
            return True
        if key in (curses.KEY_DOWN, ord("j")):
            self.version_cursor = clamp(self.version_cursor + 1, 0, len(self.versions) - 1)
            self.ensure_version_visible()
            return True
        if key in (ord("\n"), curses.KEY_ENTER, 10, 13):
            self.close_version_modal()
            self.switch_version(self.versions[self.version_cursor])
            return True
        return True

    def ensure_version_visible(self) -> None:
        self.version_scroll = scroll_to_cursor(
            self.version_cursor,
            self.version_scroll,
            self.version_visible_rows(),
        )

    def version_visible_rows(self) -> int:
        height, _ = self.stdscr.getmaxyx()
        return min(len(self.versions), max(1, height - 6))

    def switch_version(self, version: BibleVersion) -> None:
        if version == self.version:
            return
        try:
            store = BibleStore(version.path)
            books = store.books(self.alphabetical)
        except sqlite3.Error as error:
            self.message = f"could not open {version.name}: {error}"
            return

        position = self.current_position()
        focus = self.focus
        self.store.close()
        self.store = store
        self.version = version
        self.books = books
        self.rebuild_book_rows()
        self.all_verses = None
        self.goto_verse_cache = {}
        self.clear_search()
        self.restore_position(position)
        self.focus = focus if self.verses or focus != FOCUS_TEXT else FOCUS_BOOKS
        self.ensure_visible()
        self.message = f"switched to {version.name}"
        if self.on_version_change is not None:
            try:
                self.on_version_change(version)
            except OSError:
                self.message = f"switched to {version.name} (could not save state)"

    def current_position(self) -> tuple[int | None, int | None, int | None]:
        """The current place as (book sort order, chapter, verse), which carries across versions."""
        book_order = self.selected_book.sort_order if self.selected_book else None
        verse = self.verses[self.verse_cursor].number if self.verses else None
        return book_order, self.selected_chapter, verse

    def restore_position(self, position: tuple[int | None, int | None, int | None]) -> None:
        book_order, chapter, verse = position
        self.book_cursor = 0
        self.book_scroll = 0
        self.selected_book = None
        self.chapters = []
        self.verses = []
        self.selected_chapter = None
        if not self.books:
            return
        book_index = next(
            (index for index, book in enumerate(self.books) if book.sort_order == book_order),
            None,
        )
        self.book_cursor = book_index or 0
        self.select_book(self.book_cursor)
        if book_index is None or chapter not in self.chapters:
            return
        self.chapter_cursor = self.chapters.index(chapter)
        self.select_chapter(self.chapter_cursor)
        if verse is not None and self.verses:
            # A verse this version leaves out lands on the nearest earlier verse.
            self.verse_cursor = max(
                (index for index, item in enumerate(self.verses) if item.number <= verse),
                default=0,
            )

    def open_fuzzy_finder(self) -> None:
        self.pending_y = False
        self.exit_visual_mode()
        self.command_modal_open = False
        self.search_input_active = False
        if self.all_verses is None:
            self.all_verses = self.store.all_verses()
        self.fuzzy_open = True
        self.fuzzy_help_open = False
        self.fuzzy_query = ""
        self.fuzzy_cursor = 0
        self.fuzzy_scroll = 0
        self.fuzzy_matches = []
        self.message = ""

    def close_fuzzy_finder(self) -> None:
        self.fuzzy_open = False
        self.fuzzy_help_open = False
        self.fuzzy_query = ""
        self.fuzzy_cursor = 0
        self.fuzzy_scroll = 0

    def open_goto_modal(self) -> None:
        self.pending_y = False
        self.exit_visual_mode()
        self.command_modal_open = False
        self.search_input_active = False
        self.fuzzy_open = False
        self.goto_open = True
        self.goto_query = ""
        self.goto_error = False
        self.goto_suggestion_cursor = 0
        self.goto_scroll = 0
        self.message = ""

    def close_goto_modal(self) -> None:
        self.goto_open = False
        self.goto_query = ""
        self.goto_error = False
        self.goto_suggestion_cursor = 0
        self.goto_scroll = 0

    def handle_goto_key(self, key: int) -> bool:
        if key == 27:
            self.close_goto_modal()
            return True
        if key in (ord("\n"), curses.KEY_ENTER, 10, 13):
            book, chapter, verse = self.parse_goto_reference(self.goto_query)
            if book and chapter and verse:
                self.jump_to_reference(book, chapter, verse)
                self.close_goto_modal()
                return True
            suggestions = self.goto_suggestions()
            if suggestions:
                self.goto_query = suggestions[self.goto_suggestion_cursor]
                self.goto_error = False
                self.goto_suggestion_cursor = 0
                self.goto_scroll = 0
            else:
                self.goto_error = True
            return True
        if key == curses.KEY_UP:
            suggestions = self.goto_suggestions()
            if suggestions:
                self.goto_suggestion_cursor = (self.goto_suggestion_cursor - 1) % len(suggestions)
                self.ensure_goto_suggestion_visible()
            return True
        if key == curses.KEY_DOWN:
            suggestions = self.goto_suggestions()
            if suggestions:
                self.goto_suggestion_cursor = (self.goto_suggestion_cursor + 1) % len(suggestions)
                self.ensure_goto_suggestion_visible()
            return True
        if key == KEY_CTRL_N:
            suggestions = self.goto_suggestions()
            if suggestions:
                self.goto_suggestion_cursor = (self.goto_suggestion_cursor + 1) % len(suggestions)
                self.ensure_goto_suggestion_visible()
            return True
        if key == 9:
            suggestions = self.goto_suggestions()
            if suggestions:
                self.goto_query = suggestions[self.goto_suggestion_cursor]
                self.goto_error = False
                self.goto_suggestion_cursor = 0
                self.goto_scroll = 0
            return True
        if key in (curses.KEY_BACKSPACE, 127, 8):
            self.goto_query = self.goto_query[:-1]
            self.goto_error = False
            self.goto_suggestion_cursor = 0
            self.goto_scroll = 0
            return True
        if 32 <= key <= 126:
            self.goto_query += chr(key)
            self.goto_error = False
            self.goto_suggestion_cursor = 0
            self.goto_scroll = 0
            return True
        return True

    def ensure_goto_suggestion_visible(self) -> None:
        self.goto_scroll = scroll_to_cursor(
            self.goto_suggestion_cursor,
            self.goto_scroll,
            self.goto_suggestion_visible_rows(),
        )

    def parse_goto_reference(self, query: str) -> tuple[Book | None, int | None, int | None]:
        book, rest = self.goto_book_and_rest(query.strip())
        if book is None or not rest or ":" not in rest:
            return None, None, None
        chapter_text, verse_text = rest.split(":", 1)
        if not chapter_text.isdigit() or not verse_text.isdigit():
            return None, None, None
        chapter = int(chapter_text)
        verse = int(verse_text)
        if chapter not in self.store.chapters(book.id):
            return None, None, None
        valid_verses = self.verses_for_reference(book.id, chapter)
        if verse not in [item.number for item in valid_verses]:
            return None, None, None
        return book, chapter, verse

    def goto_book_and_rest(self, query: str) -> tuple[Book | None, str]:
        folded = query.casefold()
        matches = sorted(self.store.books(False), key=lambda book: len(book.name), reverse=True)
        for book in matches:
            name = book.name.casefold()
            if folded == name:
                return book, ""
            if folded.startswith(f"{name} "):
                return book, query[len(book.name) + 1 :].strip()
        return None, query

    def goto_suggestions(self) -> list[str]:
        query = self.goto_query
        book, rest = self.goto_book_and_rest(query.strip())
        if book is None:
            folded = query.strip().casefold()
            return [
                f"{candidate.name} "
                for candidate in self.store.books(False)
                if not folded or candidate.name.casefold().startswith(folded)
                if f"{candidate.name} " != query
            ]
        if not query.endswith(" ") and not rest:
            suggestion = f"{book.name} "
            return [] if suggestion == query else [suggestion]

        base = f"{book.name} "
        if ":" in rest:
            chapter_text, verse_prefix = rest.split(":", 1)
            if not chapter_text.isdigit():
                return []
            chapter = int(chapter_text)
            if chapter not in self.store.chapters(book.id):
                return []
            return [
                f"{base}{chapter}:{verse.number}"
                for verse in self.verses_for_reference(book.id, chapter)
                if str(verse.number).startswith(verse_prefix)
                if f"{base}{chapter}:{verse.number}" != query
            ]

        chapter_prefix = rest
        return [
            f"{base}{chapter}:"
            for chapter in self.store.chapters(book.id)
            if str(chapter).startswith(chapter_prefix)
            if f"{base}{chapter}:" != query
        ]

    def verses_for_reference(self, book_id: int, chapter: int) -> list[Verse]:
        key = (book_id, chapter)
        if key not in self.goto_verse_cache:
            self.goto_verse_cache[key] = self.store.verses(book_id, chapter)
        return self.goto_verse_cache[key]

    def jump_to_reference(self, book: Book, chapter: int, verse: int) -> None:
        book_index = next(
            (index for index, candidate in enumerate(self.books) if candidate.id == book.id),
            0,
        )
        self.select_book(book_index)
        chapter_index = next(
            (index for index, candidate in enumerate(self.chapters) if candidate == chapter),
            0,
        )
        self.select_chapter(chapter_index)
        self.verse_cursor = next(
            (index for index, candidate in enumerate(self.verses) if candidate.number == verse),
            0,
        )
        self.text_cursor_col = 0
        self.focus = FOCUS_TEXT
        self.clear_search()
        self.message = f"selected {book.name} {chapter}:{verse}"
        self.ensure_visible()

    def handle_fuzzy_key(self, key: int) -> bool:
        if self.fuzzy_help_open:
            if key == 27:
                self.fuzzy_help_open = False
            return True
        if key == KEY_CTRL_S:
            self.fuzzy_help_open = True
            return True
        if key == 27:
            self.close_fuzzy_finder()
            return True
        if key in (ord("\n"), curses.KEY_ENTER, 10, 13):
            if self.fuzzy_matches:
                self.jump_to_bible_verse(self.fuzzy_matches[self.fuzzy_cursor].verse)
            self.close_fuzzy_finder()
            return True
        if key == curses.KEY_UP:
            self.move_fuzzy_cursor(-1)
            return True
        if key == curses.KEY_DOWN:
            self.move_fuzzy_cursor(1)
            return True
        if key == curses.KEY_PPAGE:
            self.move_fuzzy_cursor(-self.fuzzy_page_size())
            return True
        if key == curses.KEY_NPAGE:
            self.move_fuzzy_cursor(self.fuzzy_page_size())
            return True
        if key == curses.KEY_HOME:
            self.fuzzy_cursor = 0
            self.ensure_fuzzy_visible()
            return True
        if key == curses.KEY_END:
            self.fuzzy_cursor = max(0, len(self.fuzzy_matches) - 1)
            self.ensure_fuzzy_visible()
            return True
        if key in (curses.KEY_BACKSPACE, 127, 8):
            self.fuzzy_query = self.fuzzy_query[:-1]
            self.refresh_fuzzy_matches()
            return True
        if 32 <= key <= 126:
            self.fuzzy_query += chr(key)
            self.refresh_fuzzy_matches()
            return True
        return True

    def refresh_fuzzy_matches(self) -> None:
        if self.all_verses is None:
            self.all_verses = self.store.all_verses()
        self.fuzzy_matches = (
            build_fuzzy_matches(self.all_verses, self.fuzzy_query)
            if self.fuzzy_query
            else []
        )
        self.fuzzy_cursor = clamp(self.fuzzy_cursor, 0, max(0, len(self.fuzzy_matches) - 1))
        self.fuzzy_scroll = 0
        self.ensure_fuzzy_visible()

    def move_fuzzy_cursor(self, delta: int) -> None:
        if not self.fuzzy_matches:
            return
        self.fuzzy_cursor = clamp(self.fuzzy_cursor + delta, 0, len(self.fuzzy_matches) - 1)
        self.ensure_fuzzy_visible()

    def ensure_fuzzy_visible(self) -> None:
        self.fuzzy_scroll = scroll_to_cursor(
            self.fuzzy_cursor,
            self.fuzzy_scroll,
            self.fuzzy_page_size(),
        )

    def fuzzy_page_size(self) -> int:
        height, _ = self.stdscr.getmaxyx()
        return max(1, self.fuzzy_modal_geometry(height, self.stdscr.getmaxyx()[1])[2] - 3)

    def jump_to_bible_verse(self, selected: BibleVerse) -> None:
        book_index = next(
            (index for index, book in enumerate(self.books) if book.id == selected.book_id),
            0,
        )
        self.select_book(book_index)
        chapter_index = next(
            (
                index
                for index, chapter in enumerate(self.chapters)
                if chapter == selected.chapter_number
            ),
            0,
        )
        self.select_chapter(chapter_index)
        self.verse_cursor = next(
            (
                index
                for index, verse in enumerate(self.verses)
                if verse.number == selected.verse_number
            ),
            0,
        )
        self.text_cursor_col = 0
        self.focus = FOCUS_TEXT
        self.clear_search()
        self.message = f"selected {selected.full_reference}"
        self.ensure_visible()

    def activate_selection(self) -> None:
        if (
            self.search_scope == FOCUS_BOOKS
            and self.focus == FOCUS_BOOKS
            and self.search_query
            and self.book_is_search_match(self.book_cursor)
        ):
            self.clear_search()
        if self.focus == FOCUS_BOOKS and self.books:
            self.select_book(self.book_cursor)
            self.focus = FOCUS_CHAPTERS
        elif self.focus == FOCUS_CHAPTERS and self.chapters:
            self.select_chapter(self.chapter_cursor)
            self.focus = FOCUS_TEXT
        self.ensure_visible()

    def move_focus_left(self) -> None:
        self.focus = max(FOCUS_BOOKS, self.focus - 1)
        self.ensure_visible()

    def move_focus_right(self) -> None:
        if self.focus == FOCUS_BOOKS:
            if self.books:
                self.select_book(self.book_cursor)
            self.focus = FOCUS_CHAPTERS
        elif self.focus == FOCUS_CHAPTERS:
            if self.chapters:
                self.select_chapter(self.chapter_cursor)
            self.focus = FOCUS_TEXT
        self.ensure_visible()

    def handle_search_input_key(self, key: int) -> None:
        if key == 27:
            self.clear_search()
            return
        if key in (ord("\n"), curses.KEY_ENTER, 10, 13):
            self.accept_search_input()
            return
        if key in (curses.KEY_BACKSPACE, 127, 8):
            self.search_query = self.search_query[:-1]
            self.refresh_search_cursor()
            return
        if 32 <= key <= 126:
            self.search_query += chr(key)
            self.refresh_search_cursor()

    def open_search(self) -> None:
        if self.focus == FOCUS_CHAPTERS:
            if self.chapters:
                self.select_chapter(self.chapter_cursor)
            self.focus = FOCUS_TEXT
        if self.focus not in (FOCUS_BOOKS, FOCUS_TEXT):
            self.message = "search books or text"
            return
        if self.focus == FOCUS_TEXT and not self.verses:
            self.message = "select a chapter to search text"
            return
        self.pending_y = False
        self.search_scope = self.focus
        self.search_query = ""
        self.search_input_active = True
        self.message = ""

    def edit_search(self) -> None:
        self.pending_y = False
        self.search_input_active = True
        self.message = ""
        self.refresh_search_cursor()

    def accept_search_input(self) -> None:
        if not self.search_query:
            self.clear_search()
            return
        self.search_input_active = False
        if not self.current_search_matches():
            self.message = "no search matches"

    def clear_search(self) -> None:
        self.search_scope = None
        self.search_query = ""
        self.search_input_active = False
        self.search_result_cursor = 0
        self.message = ""

    def refresh_search_cursor(self) -> None:
        results = self.current_search_results()
        if not self.search_query or not results:
            self.search_result_cursor = 0
            return
        self.search_result_cursor = self.current_search_result_index(results)
        self.move_to_search_result(results[self.search_result_cursor])
        self.ensure_visible()

    def move_to_search_result(self, result: SearchResult) -> None:
        if self.search_scope == FOCUS_BOOKS:
            self.book_cursor = result.item_index
            self.select_book(self.book_cursor)
        elif self.search_scope == FOCUS_TEXT:
            self.verse_cursor = result.item_index
            self.text_cursor_col = result.start_col

    def jump_search_match(self, direction: int) -> None:
        results = self.current_search_results()
        if not self.search_query or not results:
            self.message = "no search matches"
            return
        current_index = self.current_search_result_index(results)
        self.search_result_cursor = (current_index + direction) % len(results)
        if self.search_scope == FOCUS_BOOKS:
            self.focus = FOCUS_BOOKS
        elif self.search_scope == FOCUS_TEXT:
            self.focus = FOCUS_TEXT
        self.move_to_search_result(results[self.search_result_cursor])
        self.message = ""
        self.ensure_visible()

    def current_search_result_index(self, results: list[SearchResult]) -> int:
        if not results:
            return 0
        if self.search_scope == FOCUS_BOOKS:
            for index, result in enumerate(results):
                if result.item_index == self.book_cursor:
                    return index
            return next(
                (index for index, result in enumerate(results) if result.item_index > self.book_cursor),
                0,
            )
        if self.search_scope == FOCUS_TEXT:
            for index, result in enumerate(results):
                if (
                    result.item_index == self.verse_cursor
                    and result.start_col <= self.text_cursor_col < result.end_col
                ):
                    return index
            return next(
                (
                    index
                    for index, result in enumerate(results)
                    if result.item_index > self.verse_cursor
                    or (
                        result.item_index == self.verse_cursor
                        and result.start_col >= self.text_cursor_col
                    )
                ),
                0,
            )
        return 0

    def current_search_results(self) -> list[SearchResult]:
        if not self.search_query:
            return []
        if self.search_scope == FOCUS_BOOKS:
            return [
                SearchResult(index)
                for index, book in enumerate(self.books)
                if match_spans(book.name, self.search_query)
            ]
        if self.search_scope == FOCUS_TEXT:
            results: list[SearchResult] = []
            for verse_index, verse in enumerate(self.verses):
                results.extend(
                    SearchResult(verse_index, start_col, end_col)
                    for start_col, end_col in match_spans(verse.text, self.search_query)
                )
            return results
        return []

    def current_search_matches(self) -> list[int]:
        return sorted({result.item_index for result in self.current_search_results()})

    def book_is_search_match(self, index: int) -> bool:
        return self.search_scope == FOCUS_BOOKS and index in self.current_search_matches()

    def first_verse_match_col(self, verse_index: int) -> int:
        if not self.search_query or not (0 <= verse_index < len(self.verses)):
            return 0
        spans = match_spans(self.verses[verse_index].text, self.search_query)
        return spans[0][0] if spans else 0

    def search_match_spans(self, verse_index: int) -> list[tuple[int, int]]:
        if (
            self.search_scope != FOCUS_TEXT
            or not self.search_query
            or not (0 <= verse_index < len(self.verses))
        ):
            return []
        return match_spans(self.verses[verse_index].text, self.search_query)

    def col_is_in_spans(self, col: int, spans: list[tuple[int, int]]) -> bool:
        return any(start <= col < end for start, end in spans)

    def handle_yank_key(self) -> None:
        if self.visual_mode:
            text = self.selected_text()
            if text:
                self.yank_to_clipboard(text, "selection")
            self.exit_visual_mode()
            return
        if self.pending_y:
            self.yank_to_clipboard(self.verses[self.verse_cursor].text, "verse")
            self.pending_y = False
            return
        self.pending_y = True
        self.message = "y: press y again to yank verse"

    def enter_visual_mode(self) -> None:
        self.visual_mode = True
        self.visual_anchor = (self.verse_cursor, self.text_cursor_col)
        self.message = ""

    def exit_visual_mode(self) -> None:
        self.visual_mode = False
        self.visual_anchor = None

    def yank_to_clipboard(self, text: str, label: str) -> None:
        if not copy_to_clipboard(text):
            self.message = "clipboard unavailable"
            return
        self.message = f"yanked {label}"

    def move_text_cursor(self, delta: int) -> None:
        if not self.verses:
            return
        max_col = max(0, len(self.verses[self.verse_cursor].text) - 1)
        self.text_cursor_col = clamp(self.text_cursor_col + delta, 0, max_col)
        self.ensure_visible()

    def move_verse_cursor(self, delta: int) -> None:
        if not self.verses:
            return
        self.verse_cursor = clamp(self.verse_cursor + delta, 0, len(self.verses) - 1)
        max_col = max(0, len(self.verses[self.verse_cursor].text) - 1)
        self.text_cursor_col = clamp(self.text_cursor_col, 0, max_col)
        self.ensure_visible()

    def toggle_book_order(self) -> None:
        selected_id = self.selected_book.id if self.selected_book else None
        cursor_id = self.books[self.book_cursor].id if self.books else None
        self.alphabetical = not self.alphabetical
        self.books = self.store.books(self.alphabetical)
        self.rebuild_book_rows()
        target_id = selected_id or cursor_id
        self.book_cursor = next(
            (i for i, book in enumerate(self.books) if book.id == target_id), 0
        )
        if selected_id is not None:
            self.selected_book = self.books[self.book_cursor]
        self.book_scroll = 0
        self.ensure_visible()

    def rebuild_book_rows(self) -> None:
        if self.alphabetical or not self.books:
            self.book_rows = tuple(("book", index) for index in range(len(self.books)))
        else:
            rows: list[tuple[str, object]] = []
            current_testament: str | None = None
            for index, book in enumerate(self.books):
                if book.testament != current_testament:
                    current_testament = book.testament
                    heading = "Old Testament" if book.testament == "old" else "New Testament"
                    rows.append(("heading", heading))
                rows.append(("book", index))
            self.book_rows = tuple(rows)
        self.book_row_index = {
            payload: row for row, (kind, payload) in enumerate(self.book_rows) if kind == "book"
        }

    def move_vertical(self, delta: int) -> None:
        if self.focus == FOCUS_BOOKS and self.books:
            self.book_cursor = clamp(self.book_cursor + delta, 0, len(self.books) - 1)
            self.select_book(self.book_cursor)
        elif self.focus == FOCUS_CHAPTERS and self.chapters:
            self.chapter_cursor = clamp(
                self.chapter_cursor + delta, 0, len(self.chapters) - 1
            )
            self.select_chapter(self.chapter_cursor)
        elif self.focus == FOCUS_TEXT:
            self.move_verse_cursor(delta)
        self.ensure_visible()

    def page(self, direction: int) -> None:
        _, _, content_h, _, _, _ = self.layout()
        page_size = max(1, content_h - 4)
        if self.focus == FOCUS_BOOKS and self.books:
            self.book_cursor = clamp(
                self.book_cursor + direction * page_size, 0, len(self.books) - 1
            )
            self.select_book(self.book_cursor)
        elif self.focus == FOCUS_CHAPTERS and self.chapters:
            self.chapter_cursor = clamp(
                self.chapter_cursor + direction * page_size, 0, len(self.chapters) - 1
            )
            self.select_chapter(self.chapter_cursor)
        elif self.focus == FOCUS_TEXT:
            self.move_verse_cursor(direction * page_size)
        self.ensure_visible()

    def home(self) -> None:
        if self.focus == FOCUS_BOOKS:
            self.book_cursor = 0
            if self.books:
                self.select_book(self.book_cursor)
        elif self.focus == FOCUS_CHAPTERS:
            self.chapter_cursor = 0
            if self.chapters:
                self.select_chapter(self.chapter_cursor)
        else:
            self.verse_cursor = 0
            self.text_cursor_col = 0
        self.ensure_visible()

    def end(self) -> None:
        if self.focus == FOCUS_BOOKS and self.books:
            self.book_cursor = len(self.books) - 1
            self.select_book(self.book_cursor)
        elif self.focus == FOCUS_CHAPTERS and self.chapters:
            self.chapter_cursor = len(self.chapters) - 1
            self.select_chapter(self.chapter_cursor)
        else:
            if self.verses:
                self.verse_cursor = len(self.verses) - 1
                self.text_cursor_col = 0
        self.ensure_visible()

    def select_book(self, index: int) -> None:
        self.selected_book = self.books[index]
        self.chapters = self.store.chapters(self.selected_book.id)
        self.chapter_cursor = 0
        self.chapter_scroll = 0
        self.text_scroll = 0
        self.verse_cursor = 0
        self.text_cursor_col = 0
        if self.chapters:
            self.select_chapter(0)
        else:
            self.verses = []
            self.selected_chapter = None
            self.exit_visual_mode()

    def select_chapter(self, index: int) -> None:
        if self.selected_book is None or not self.chapters:
            return
        self.selected_chapter = self.chapters[index]
        self.verses = self.store.verses(self.selected_book.id, self.selected_chapter)
        self.text_scroll = 0
        self.verse_cursor = 0
        self.text_cursor_col = 0
        self.exit_visual_mode()

    def ensure_visible(self) -> None:
        _, _, content_h, _, _, _ = self.layout()
        inner_h = max(1, content_h - 2)
        book_row = self.book_row_index.get(self.book_cursor, self.book_cursor)
        self.book_scroll = scroll_to_cursor(book_row, self.book_scroll, inner_h)
        self.chapter_scroll = scroll_to_cursor(
            self.chapter_cursor, self.chapter_scroll, inner_h
        )
        wrapped = self.wrapped_verses(max(1, self.layout()[5] - 2))
        if self.verses and wrapped:
            verse_rows = [
                i for i, line in enumerate(wrapped) if line.verse_index == self.verse_cursor
            ]
            if verse_rows:
                first_row = verse_rows[0]
                last_row = verse_rows[-1]
                if first_row < self.text_scroll:
                    self.text_scroll = first_row
                elif last_row >= self.text_scroll + inner_h:
                    self.text_scroll = last_row - inner_h + 1
        max_scroll = max(0, len(wrapped) - inner_h)
        self.text_scroll = clamp(self.text_scroll, 0, max_scroll)

    def draw(self) -> None:
        self.stdscr.erase()
        height, width = self.stdscr.getmaxyx()
        if height < 10 or width < 50:
            self.stdscr.addnstr(0, 0, "Terminal too small: need at least 50x10", width - 1)
            self.stdscr.refresh()
            return

        top_y, content_y, content_h, book_w, chapter_w, text_w = self.layout()
        self.draw_top_bar(top_y, width)
        self.draw_books(content_y, 0, content_h, book_w)
        self.draw_chapters(content_y, book_w, content_h, chapter_w)
        self.draw_text(content_y, book_w + chapter_w, content_h, text_w)
        self.draw_status(height - 1, width)
        if self.command_modal_open:
            self.draw_command_modal(height, width)
        if self.fuzzy_open:
            self.draw_fuzzy_finder(height, width)
            if self.fuzzy_help_open:
                self.draw_fuzzy_help_modal(height, width)
        if self.goto_open:
            self.draw_goto_modal(height, width)
        if self.version_modal_open:
            self.draw_version_modal(height, width)
        if self.search_input_active:
            self.position_search_cursor(height - 1, width)
        elif self.goto_open:
            self.position_goto_cursor(height, width)
        elif self.fuzzy_open:
            if self.fuzzy_help_open:
                self.set_cursor_visibility(False)
            else:
                self.position_fuzzy_cursor(height, width)
        else:
            self.position_terminal_cursor(content_y, book_w + chapter_w, content_h, text_w)
        self.stdscr.refresh()

    def layout(self) -> tuple[int, int, int, int, int, int]:
        height, width = self.stdscr.getmaxyx()
        top_y = 0
        content_y = 1
        content_h = max(1, height - 2)
        chapter_w = 7  # 5 content chars plus borders.
        book_w = clamp(max(len(book.name) for book in self.books) + 4, 15, 25)
        text_w = max(10, width - book_w - chapter_w)
        return top_y, content_y, content_h, book_w, chapter_w, text_w

    def draw_top_bar(self, y: int, width: int) -> None:
        order = "A-Z" if self.alphabetical else "Bible order"
        title = f" Bible TUI | {self.version.name} | {order} "
        self.add_screen_line(y, title, width)

    def draw_books(self, y: int, x: int, h: int, w: int) -> None:
        win = self.stdscr.derwin(h, w, y, x)
        self.draw_box(win, "Books", self.focus == FOCUS_BOOKS)
        inner_h = max(0, h - 2)
        inner_w = max(0, w - 2)
        for row, (kind, payload) in enumerate(
            self.book_rows[self.book_scroll : self.book_scroll + inner_h]
        ):
            if kind == "heading":
                win.addnstr(
                    row + 1,
                    1,
                    str(payload).ljust(inner_w),
                    inner_w,
                    curses.color_pair(PAIR_HEADING) | curses.A_BOLD,
                )
                continue
            index = payload
            book = self.books[index]
            search_match = self.book_is_search_match(index)
            if index == self.book_cursor and self.focus == FOCUS_BOOKS:
                attr = curses.color_pair(1)
            elif self.selected_book and book.id == self.selected_book.id:
                attr = curses.color_pair(PAIR_SEARCH) | curses.A_REVERSE if search_match else curses.A_REVERSE
            elif search_match:
                attr = curses.color_pair(PAIR_SEARCH) | curses.A_BOLD
            else:
                attr = 0
            win.addnstr(row + 1, 1, f" {book.name} ".ljust(inner_w), inner_w, attr)
        self.draw_scrollbar(win, len(self.book_rows), self.book_scroll, inner_h)

    def draw_chapters(self, y: int, x: int, h: int, w: int) -> None:
        win = self.stdscr.derwin(h, w, y, x)
        self.draw_box(win, "Ch", self.focus == FOCUS_CHAPTERS)
        inner_h = max(0, h - 2)
        for row, chapter in enumerate(
            self.chapters[self.chapter_scroll : self.chapter_scroll + inner_h]
        ):
            index = self.chapter_scroll + row
            attr = curses.color_pair(1) if index == self.chapter_cursor and self.focus == FOCUS_CHAPTERS else 0
            if self.selected_chapter == chapter:
                attr |= curses.A_REVERSE if self.focus != FOCUS_CHAPTERS else curses.A_BOLD
            win.addnstr(row + 1, 1, f"{chapter:^5}", 5, attr)
        self.draw_scrollbar(win, len(self.chapters), self.chapter_scroll, inner_h)

    def draw_text(self, y: int, x: int, h: int, w: int) -> None:
        win = self.stdscr.derwin(h, w, y, x)
        title = "Text"
        if self.selected_book and self.selected_chapter:
            title = f"{self.selected_book.name} {self.selected_chapter}"
        self.draw_box(win, title, self.focus == FOCUS_TEXT)
        inner_h = max(0, h - 2)
        inner_w = max(0, w - 2)
        lines = self.wrapped_verses(inner_w)
        for row, line in enumerate(lines[self.text_scroll : self.text_scroll + inner_h]):
            selected = self.verses and line.verse_index == self.verse_cursor
            if selected:
                base_attr = curses.color_pair(6)
            else:
                base_attr = 0
            win.addnstr(row + 1, 1, " " * inner_w, inner_w, base_attr)
            if line.verse_number:
                number_attr = base_attr | curses.A_BOLD if selected else curses.color_pair(3) | curses.A_BOLD
                win.addnstr(row + 1, 1, line.verse_number, 4, number_attr)
            self.draw_text_segment(win, row + 1, 5, line, max(0, inner_w - 4), base_attr)
        self.draw_scrollbar(win, len(lines), self.text_scroll, inner_h)

    def draw_status(self, y: int, width: int) -> None:
        if self.search_scope is not None:
            self.draw_search_line(y, width)
            return
        version = self.version.name
        location = self.location_label()
        focus = ("books", "chapters", "text")[self.focus]
        status = f" {version} | {location} | focus: {focus} "
        if self.message:
            status = f"{status}| {self.message} "
        visual = "-- VISUAL --"
        hint_width = len("ctrl+p commands")
        # Keep the status text clear of the right-aligned visual marker and command hint.
        reserved = hint_width + 2 + (len(visual) + 1 if self.visual_mode else 0)
        available = max(0, width - 1 - reserved)
        if len(status) > available:
            status = status[: max(0, available - 4)] + "... "
        self.add_screen_line(y, status, width, curses.color_pair(4) | curses.A_DIM)
        if self.visual_mode and width > 14:
            visual_x = max(0, width - hint_width - len(visual) - 3)
            self.stdscr.addnstr(y, visual_x, visual, len(visual), curses.color_pair(7) | curses.A_BOLD)
        self.draw_command_hint(y, width)

    def draw_command_hint(self, y: int, width: int) -> None:
        parts = (("ctrl+p", "commands"),)
        hint = "  ".join(f"{key} {label}" for key, label in parts)
        usable_width = max(0, width - 1)
        start_x = usable_width - len(hint)
        if start_x <= 0:
            return
        x = start_x
        for index, (key, label) in enumerate(parts):
            if index:
                x += 2
            self.stdscr.addnstr(y, x, key, len(key), curses.color_pair(2))
            x += len(key) + 1
            self.stdscr.addnstr(y, x, label, len(label), curses.color_pair(4) | curses.A_DIM)
            x += len(label)

    def draw_search_line(self, y: int, width: int) -> None:
        usable_width = max(0, width - 1)
        if usable_width <= 0:
            return

        self.add_screen_line(y, "", width, curses.color_pair(4) | curses.A_DIM)
        prefix = "SEARCH"
        prompt = f" /{self.search_query}"
        hint_start = usable_width
        if not self.search_input_active:
            hint_start = self.search_hints_start(width)
        self.stdscr.addnstr(y, 0, prefix, usable_width, curses.color_pair(PAIR_SEARCH) | curses.A_BOLD)
        prompt_width = max(0, hint_start - len(prefix))
        status = self.search_status_label()
        if prompt_width:
            if status and prompt_width > len(status):
                text_width = prompt_width - len(status)
                self.stdscr.addnstr(y, len(prefix), prompt, text_width, curses.color_pair(2))
                self.stdscr.addnstr(
                    y,
                    len(prefix) + min(len(prompt), text_width),
                    status,
                    len(status),
                    curses.color_pair(4) | curses.A_DIM,
                )
            else:
                self.stdscr.addnstr(y, len(prefix), prompt, prompt_width, curses.color_pair(2))
        if not self.search_input_active:
            self.draw_search_hints(y, width)

    def search_status_label(self) -> str:
        if not self.search_query:
            return ""
        results = self.current_search_results()
        count = len(results)
        plural = "" if count == 1 else "es"
        if self.search_input_active:
            return f" {count:,} match{plural}"
        if not count:
            return " 0 of 0"
        current = self.current_search_result_index(results) + 1
        return f" {current:,} of {count:,}"

    def search_hints_start(self, width: int) -> int:
        usable_width = max(0, width - 1)
        hint_width = sum(len(label) + 1 + len(key) for label, key in SEARCH_HINTS)
        hint_width += 2 * (len(SEARCH_HINTS) - 1)
        return max(len("SEARCH /") + 1, usable_width - hint_width)

    def draw_search_hints(self, y: int, width: int) -> None:
        usable_width = max(0, width - 1)
        x = self.search_hints_start(width)
        if x >= usable_width:
            return
        for index, (label, key) in enumerate(SEARCH_HINTS):
            if index:
                if x + 2 >= usable_width:
                    return
                self.stdscr.addnstr(y, x, ", ", 2, curses.color_pair(4) | curses.A_DIM)
                x += 2
            if x + len(label) + 1 + len(key) > usable_width:
                return
            self.stdscr.addnstr(
                y,
                x,
                label,
                len(label),
                curses.color_pair(4) | curses.A_DIM,
            )
            x += len(label) + 1
            self.stdscr.addnstr(
                y,
                x,
                key,
                len(key),
                curses.color_pair(2),
            )
            x += len(key)

    def draw_command_modal(self, height: int, width: int) -> None:
        visible_rows = self.command_visible_rows()
        modal_w = self.command_modal_width(width)
        modal_h = visible_rows + 2
        y = max(1, (height - modal_h) // 2)
        x = max(0, (width - modal_w) // 2)
        win = self.stdscr.derwin(modal_h, modal_w, y, x)
        border_attr = curses.color_pair(5) | curses.A_BOLD
        win.attron(border_attr)
        win.box()
        win.attroff(border_attr)

        title = " Commands "
        win.addnstr(0, 2, title, max(0, modal_w - 4), curses.color_pair(2) | curses.A_BOLD)
        esc = " esc "
        if modal_w > len(esc) + 4:
            win.addnstr(0, modal_w - len(esc) - 2, esc, len(esc), curses.color_pair(4))

        for row, (kind, payload) in enumerate(
            COMMAND_ROWS[self.command_scroll : self.command_scroll + visible_rows]
        ):
            row_y = row + 1
            if kind == "heading":
                win.addnstr(row_y, 1, " " * max(0, modal_w - 2), max(0, modal_w - 2), 0)
                win.addnstr(
                    row_y,
                    2,
                    str(payload),
                    max(0, modal_w - 4),
                    curses.color_pair(PAIR_HEADING) | curses.A_BOLD,
                )
                continue
            index = payload
            command = COMMANDS[index]
            selected = index == self.command_cursor
            row_attr = curses.color_pair(1) if selected else 0
            name_attr = row_attr if selected else curses.color_pair(2)
            key_attr = row_attr if selected else curses.color_pair(4) | curses.A_DIM
            win.addnstr(row_y, 1, " " * max(0, modal_w - 2), max(0, modal_w - 2), row_attr)
            key_x = max(4, modal_w - len(command.keybind) - 2)
            name_width = max(0, key_x - 5)
            win.addnstr(row_y, 4, command.name, name_width, name_attr)
            win.addnstr(row_y, key_x, command.keybind, max(0, modal_w - key_x - 2), key_attr)

    def draw_version_modal(self, height: int, width: int) -> None:
        visible_rows = self.version_visible_rows()
        content_w = max(len(version.name) for version in self.versions)
        modal_w = min(max(40, content_w + 10), max(20, width - 4))
        modal_h = visible_rows + 2
        y = max(1, (height - modal_h) // 2)
        x = max(0, (width - modal_w) // 2)
        win = self.stdscr.derwin(modal_h, modal_w, y, x)
        win.erase()
        border_attr = curses.color_pair(5) | curses.A_BOLD
        win.attron(border_attr)
        win.box()
        win.attroff(border_attr)

        win.addnstr(0, 2, " Versions ", max(0, modal_w - 4), curses.color_pair(2) | curses.A_BOLD)
        esc = " esc "
        if modal_w > len(esc) + 14:
            win.addnstr(0, modal_w - len(esc) - 2, esc, len(esc), curses.color_pair(4))

        inner_w = max(0, modal_w - 2)
        for row, version in enumerate(
            self.versions[self.version_scroll : self.version_scroll + visible_rows]
        ):
            index = self.version_scroll + row
            selected = index == self.version_cursor
            row_attr = curses.color_pair(1) if selected else 0
            marker_attr = row_attr if selected else curses.color_pair(3) | curses.A_BOLD
            name_attr = row_attr if selected else curses.color_pair(2)
            marker = "*" if version == self.version else " "
            win.addnstr(row + 1, 1, " " * inner_w, inner_w, row_attr)
            win.addnstr(row + 1, 2, marker, 1, marker_attr)
            win.addnstr(row + 1, 4, version.name, max(0, modal_w - 6), name_attr)
        self.draw_scrollbar(win, len(self.versions), self.version_scroll, visible_rows)

    def draw_fuzzy_finder(self, height: int, width: int) -> None:
        modal_y, modal_x, modal_h, modal_w = self.fuzzy_modal_geometry(height, width)
        result_w = max(20, int((modal_w - 1) * 0.75))
        preview_w = modal_w - result_w - 1
        if preview_w < 20:
            result_w = max(20, modal_w - 21)
            preview_w = modal_w - result_w - 1
        pane_h = max(1, modal_h - 1)
        modal_attr = curses.color_pair(4)
        self.fill_rect(modal_y, modal_x, modal_h, modal_w, modal_attr)
        result_win = self.stdscr.derwin(pane_h, result_w, modal_y, modal_x)
        preview_win = self.stdscr.derwin(pane_h, preview_w, modal_y, modal_x + result_w + 1)
        result_win.bkgd(" ", modal_attr)
        preview_win.bkgd(" ", modal_attr)
        result_win.erase()
        preview_win.erase()

        self.draw_box(result_win, "", True)
        self.draw_fuzzy_header(result_win)

        selected_match = self.fuzzy_matches[self.fuzzy_cursor] if self.fuzzy_matches else None
        preview_title = selected_match.verse.full_reference if selected_match else "Preview"
        self.draw_box(preview_win, preview_title, False)

        self.draw_fuzzy_results(result_win)
        self.draw_fuzzy_preview(preview_win, selected_match)
        self.draw_fuzzy_footer(modal_y + pane_h, modal_x, modal_w)

    def draw_fuzzy_header(self, win: curses.window) -> None:
        _, max_x = win.getmaxyx()
        if max_x <= 4:
            return

        prompt = " FIND > "
        prompt_x = 2
        query_x = prompt_x + len(prompt)
        count_label = ""
        if self.fuzzy_query:
            count = len(self.fuzzy_matches)
            count_label = f" {count:,} match{'es' if count != 1 else ''} "

        prompt_attr = curses.color_pair(5) | curses.A_BOLD
        query_attr = curses.color_pair(2)
        win.addnstr(0, prompt_x, prompt, max(0, max_x - prompt_x - 2), prompt_attr)
        count_start = max_x - len(count_label) - 2 if count_label else max_x - 2
        query_width = max(0, count_start - query_x)
        if query_width:
            win.addnstr(0, query_x, f"{self.fuzzy_query} ", query_width, query_attr)
        if count_label and count_start > query_x:
            win.addnstr(0, count_start, count_label, max(0, max_x - count_start - 1), prompt_attr)

    def draw_fuzzy_results(self, win: curses.window) -> None:
        max_y, max_x = win.getmaxyx()
        inner_h = max(0, max_y - 2)
        inner_w = max(0, max_x - 2)
        if inner_h <= 0 or inner_w <= 0:
            return
        if not self.fuzzy_matches:
            if self.fuzzy_query:
                win.addnstr(1, 1, " No matches".ljust(inner_w), inner_w, curses.color_pair(4) | curses.A_DIM)
            return

        ref_w = min(reference_width(self.all_verses or []) + 1, max(8, inner_w // 2))
        snippet_w = max(0, inner_w - ref_w)
        for row, match in enumerate(
            self.fuzzy_matches[self.fuzzy_scroll : self.fuzzy_scroll + inner_h]
        ):
            index = self.fuzzy_scroll + row
            selected = index == self.fuzzy_cursor
            row_attr = curses.color_pair(1) if selected else 0
            ref_attr = row_attr if selected else curses.color_pair(3) | curses.A_BOLD
            win.addnstr(row + 1, 1, " " * inner_w, inner_w, row_attr)
            win.addnstr(
                row + 1,
                1,
                match.verse.short_reference.ljust(ref_w),
                ref_w,
                ref_attr,
            )
            self.draw_fuzzy_snippet(
                win,
                row + 1,
                1 + ref_w,
                match.verse.text,
                match.positions,
                snippet_w,
                row_attr,
            )
        self.draw_scrollbar(win, len(self.fuzzy_matches), self.fuzzy_scroll, inner_h)

    def draw_fuzzy_footer(self, y: int, x: int, width: int) -> None:
        if width < 12:
            return
        hints = (("ctrl+s", "syntax"), ("esc", "close"))
        hint = "  ".join(f"{key} {label}" for key, label in hints)
        if width <= len(hint) + 2:
            hints = (("esc", "close"),)
            hint = "  ".join(f"{key} {label}" for key, label in hints)
        start_x = x + max(1, width - len(hint) - 1)
        current_x = start_x
        for index, (key, label) in enumerate(hints):
            if index:
                current_x += 2
            self.stdscr.addnstr(y, current_x, key, len(key), curses.color_pair(2))
            current_x += len(key) + 1
            self.stdscr.addnstr(y, current_x, label, len(label), curses.color_pair(4) | curses.A_DIM)
            current_x += len(label)

    def draw_fuzzy_help_footer(self, y: int, x: int, width: int) -> None:
        if width < 12:
            return
        key = "esc"
        label = "close"
        start_x = x + width - len(key) - len(label) - 2
        self.stdscr.addnstr(y, start_x, key, len(key), curses.color_pair(2))
        self.stdscr.addnstr(y, start_x + len(key) + 1, label, len(label), curses.color_pair(4) | curses.A_DIM)

    def fuzzy_help_modal_geometry(self, height: int, width: int) -> tuple[int, int, int, int]:
        type_w = max(len(kind) for kind, _, _ in FUZZY_HELP_ROWS) + 1
        example_w = max(len(example) for _, example, _ in FUZZY_HELP_ROWS) + 2
        finds_w = max(len(finds) for _, _, finds in FUZZY_HELP_ROWS)
        content_w = 2 + type_w + 1 + example_w + 1 + finds_w + 2
        modal_w = min(max(40, content_w), max(30, width - 8))
        modal_h = min(13, max(11, height - 4))
        y = max(0, (height - modal_h) // 2)
        x = max(0, (width - modal_w) // 2)
        return y, x, modal_h, modal_w

    def draw_fuzzy_help_modal(self, height: int, width: int) -> None:
        modal_y, modal_x, modal_h, modal_w = self.fuzzy_help_modal_geometry(height, width)
        pane_h = max(1, modal_h - 1)
        modal_attr = curses.color_pair(4)
        self.fill_rect(modal_y, modal_x, modal_h, modal_w, modal_attr)
        win = self.stdscr.derwin(pane_h, modal_w, modal_y, modal_x)
        win.bkgd(" ", modal_attr)
        win.erase()
        self.draw_box(win, " Search Syntax ", True)

        type_w = max(len(kind) for kind, _, _ in FUZZY_HELP_ROWS) + 1
        example_w = max(len(example) for _, example, _ in FUZZY_HELP_ROWS) + 2
        type_x = 2
        example_x = type_x + type_w + 1
        finds_x = example_x + example_w + 1
        finds_w = max(0, modal_w - finds_x - 2)

        heading_attr = curses.color_pair(PAIR_HEADING) | curses.A_BOLD
        header_y = 1
        win.addnstr(header_y, type_x, "Type", type_w, heading_attr)
        win.addnstr(header_y, example_x, "Example", example_w, heading_attr)
        win.addnstr(header_y, finds_x, "Finds", finds_w, heading_attr)

        for row, (kind, example, finds) in enumerate(FUZZY_HELP_ROWS):
            row_y = header_y + 2 + row
            if row_y >= pane_h - 1:
                break
            win.addnstr(row_y, type_x, kind, type_w, curses.color_pair(2))
            win.addnstr(row_y, example_x, example, example_w, curses.color_pair(3) | curses.A_BOLD)
            win.addnstr(row_y, finds_x, finds, finds_w, curses.color_pair(4) | curses.A_DIM)

        self.draw_fuzzy_help_footer(modal_y + pane_h, modal_x, modal_w)

    def draw_goto_modal(self, height: int, width: int) -> None:
        modal_y, modal_x, modal_h, modal_w = self.goto_modal_geometry(height, width)
        pane_h = max(1, modal_h - 1)
        modal_attr = curses.color_pair(4)
        self.fill_rect(modal_y, modal_x, modal_h, modal_w, modal_attr)
        win = self.stdscr.derwin(pane_h, modal_w, modal_y, modal_x)
        win.bkgd(" ", modal_attr)
        win.erase()
        self.draw_box(win, " Go To Reference ", True)

        input_y = 2
        input_x = 3
        input_w = max(1, modal_w - 6)
        input_attr = curses.color_pair(PAIR_ERROR) if self.goto_error else curses.color_pair(2)
        win.addnstr(input_y, input_x - 1, "[", 1, curses.color_pair(5) | curses.A_BOLD)
        win.addnstr(input_y, input_x, self.goto_query.ljust(input_w), input_w, input_attr)
        win.addnstr(input_y, input_x + input_w, "]", 1, curses.color_pair(5) | curses.A_BOLD)

        if self.goto_error:
            win.addnstr(3, input_x, "Invalid Reference", input_w, curses.color_pair(PAIR_ERROR) | curses.A_BOLD)

        suggestions = self.goto_suggestions()
        suggestions_y = 4 if self.goto_error else 3
        available_rows = self.goto_suggestion_visible_rows()
        suggestion_w = max(1, modal_w - 1 - input_x)
        visible_suggestions = suggestions[self.goto_scroll : self.goto_scroll + available_rows]
        for row, suggestion in enumerate(visible_suggestions):
            index = self.goto_scroll + row
            selected = index == self.goto_suggestion_cursor
            attr = curses.color_pair(1) if selected else curses.color_pair(4)
            win.addnstr(suggestions_y + row, input_x, suggestion.ljust(suggestion_w), suggestion_w, attr)
        self.draw_scrollbar(
            win,
            len(suggestions),
            self.goto_scroll,
            available_rows,
            row_start=suggestions_y,
            track_h=available_rows,
        )

        self.draw_goto_footer(modal_y + pane_h, modal_x, modal_w)

    def goto_suggestion_visible_rows(self) -> int:
        height, width = self.stdscr.getmaxyx()
        _, _, modal_h, _ = self.goto_modal_geometry(height, width)
        pane_h = max(1, modal_h - 1)
        suggestions_y = 4 if self.goto_error else 3
        return max(0, pane_h - suggestions_y - 1)

    def draw_goto_footer(self, y: int, x: int, width: int) -> None:
        hints = (("tab", "accept"), ("ctrl+n", "next"), ("enter", "go"), ("esc", "close"))
        hint = "  ".join(f"{key} {label}" for key, label in hints)
        if width <= len(hint) + 2:
            hints = (("enter", "go"), ("esc", "close"))
            hint = "  ".join(f"{key} {label}" for key, label in hints)
        start_x = x + max(1, width - len(hint) - 1)
        current_x = start_x
        for index, (key, label) in enumerate(hints):
            if index:
                current_x += 2
            self.stdscr.addnstr(y, current_x, key, len(key), curses.color_pair(2))
            current_x += len(key) + 1
            self.stdscr.addnstr(y, current_x, label, len(label), curses.color_pair(4) | curses.A_DIM)
            current_x += len(label)

    def goto_modal_geometry(self, height: int, width: int) -> tuple[int, int, int, int]:
        modal_w = min(max(44, int(width * 0.42)), max(20, width - 8))
        modal_h = min(13, max(7, height - 4))
        y = max(0, (height - modal_h) // 2)
        x = max(0, (width - modal_w) // 2)
        return y, x, modal_h, modal_w

    def draw_fuzzy_snippet(
        self,
        win: curses.window,
        y: int,
        x: int,
        text: str,
        positions: tuple[int, ...],
        width: int,
        base_attr: int,
    ) -> None:
        if width <= 0:
            return
        prefix, offset, snippet, suffix = snippet_parts(text, positions, width)
        position_set = set(positions)
        current_x = x
        remaining = width
        for chunk in (prefix,):
            if chunk and remaining > 0:
                win.addnstr(y, current_x, chunk, remaining, base_attr)
                current_x += min(len(chunk), remaining)
                remaining -= min(len(chunk), remaining)
        for char_index, char in enumerate(snippet):
            if remaining <= 0:
                return
            absolute = offset + char_index
            attr = base_attr
            if absolute in position_set and not base_attr:
                attr = curses.color_pair(PAIR_SEARCH) | curses.A_BOLD
            elif absolute in position_set:
                attr = base_attr | curses.A_BOLD
            win.addnstr(y, current_x, char, 1, attr)
            current_x += 1
            remaining -= 1
        if suffix and remaining > 0:
            win.addnstr(y, current_x, suffix, remaining, base_attr)

    def draw_fuzzy_preview(self, win: curses.window, match: FuzzyMatch | None) -> None:
        max_y, max_x = win.getmaxyx()
        inner_h = max(0, max_y - 2)
        inner_w = max(0, max_x - 2)
        if inner_h <= 0 or inner_w <= 0:
            return
        if match is None:
            win.addnstr(1, 1, " Type to search all verses".ljust(inner_w), inner_w, curses.color_pair(4) | curses.A_DIM)
            return
        lines = textwrap.wrap(
            match.verse.text,
            width=max(1, inner_w - 2),
            replace_whitespace=True,
            drop_whitespace=True,
        ) or [""]
        for row, line in enumerate(lines[:inner_h]):
            prefix = "  " if row == 0 else ""
            win.addnstr(row + 1, 1, f"{prefix}{line}".ljust(inner_w), inner_w, curses.color_pair(2))

    def fuzzy_modal_geometry(self, height: int, width: int) -> tuple[int, int, int, int]:
        modal_h = min(max(10, int(height * 0.72)), max(1, height - 4))
        modal_w = min(max(60, int(width * 0.82)), max(20, width - 8))
        y = max(0, (height - modal_h) // 2)
        x = max(0, (width - modal_w) // 2)
        return y, x, modal_h, modal_w

    def fill_rect(self, y: int, x: int, h: int, w: int, attr: int = 0) -> None:
        height, width = self.stdscr.getmaxyx()
        usable_w = max(0, min(w, width - x - 1))
        if usable_w <= 0:
            return
        for row in range(max(0, y), min(height, y + h)):
            self.stdscr.addnstr(row, x, " " * usable_w, usable_w, attr)

    def position_fuzzy_cursor(self, height: int, width: int) -> None:
        modal_y, modal_x, _, modal_w = self.fuzzy_modal_geometry(height, width)
        result_w = max(20, int((modal_w - 1) * 0.75))
        preview_w = modal_w - result_w - 1
        if preview_w < 20:
            result_w = max(20, modal_w - 21)
        cursor_x = modal_x + 2 + min(
            max(0, result_w - 4),
            len(" FIND > ") + len(self.fuzzy_query),
        )
        self.set_cursor_visibility(True)
        try:
            self.stdscr.move(modal_y, cursor_x)
        except curses.error:
            self.set_cursor_visibility(False)

    def add_screen_line(self, y: int, text: str, width: int, attr: int = 0) -> None:
        # Avoid the bottom-right terminal cell; many curses backends treat it as ERR.
        usable_width = max(0, width - 1)
        if usable_width:
            self.stdscr.addnstr(y, 0, text.ljust(usable_width), usable_width, attr)

    def draw_box(self, win: curses.window, title: str, focused: bool) -> None:
        attr = curses.color_pair(5) | curses.A_BOLD if focused else curses.color_pair(4) | curses.A_DIM
        win.attron(attr)
        win.box()
        win.attroff(attr)
        max_y, max_x = win.getmaxyx()
        label = f" {title} "[: max(0, max_x - 2)]
        if max_x > 4:
            heading_attr = curses.color_pair(5) | curses.A_BOLD if focused else 0
            win.addnstr(0, 2, label, max_x - 4, heading_attr)

    def command_visible_rows(self) -> int:
        height, _ = self.stdscr.getmaxyx()
        return min(len(COMMAND_ROWS), max(1, height - 6))

    def command_modal_width(self, width: int) -> int:
        content_width = max(len(command.name) + len(command.keybind) for command in COMMANDS)
        return min(max(68, (content_width + 8) * 2), max(20, width - 4))

    def ensure_command_visible(self) -> None:
        visible_rows = self.command_visible_rows()
        row = COMMAND_ROW_INDEX[self.command_cursor]
        self.command_scroll = scroll_to_cursor(row, self.command_scroll, visible_rows)

    def draw_scrollbar(
        self,
        win: curses.window,
        total: int,
        scroll: int,
        visible: int,
        *,
        col: int | None = None,
        row_start: int = 1,
        track_h: int | None = None,
    ) -> None:
        if total <= visible or visible <= 0:
            return
        max_y, max_x = win.getmaxyx()
        if col is None:
            col = max_x - 1
        if track_h is None:
            track_h = max_y - 2
        if track_h <= 0:
            return
        thumb_h = max(1, round(track_h * visible / total))
        max_scroll = max(1, total - visible)
        thumb_top = row_start + round((track_h - thumb_h) * scroll / max_scroll)
        for y in range(row_start, row_start + track_h):
            ch = "┃" if thumb_top <= y < thumb_top + thumb_h else curses.ACS_VLINE
            try:
                win.addch(y, col, ch, curses.color_pair(2))
            except (curses.error, UnicodeEncodeError):
                if thumb_top <= y < thumb_top + thumb_h:
                    win.addch(y, col, curses.ACS_CKBOARD, curses.color_pair(2))

    def wrapped_verses(self, width: int) -> list[RenderLine]:
        if not self.verses:
            return []
        text_width = max(8, width - 4)
        lines: list[RenderLine] = []
        for verse_index, verse in enumerate(self.verses):
            wrapped = textwrap.wrap(
                verse.text,
                width=text_width,
                replace_whitespace=True,
                drop_whitespace=True,
            ) or [""]
            start_col = 0
            lines.append(RenderLine(verse_index, f"{verse.number:>3} ", wrapped[0], start_col))
            start_col += len(wrapped[0])
            for continuation in wrapped[1:]:
                if start_col < len(verse.text) and verse.text[start_col : start_col + 1] == " ":
                    start_col += 1
                lines.append(RenderLine(verse_index, "", continuation, start_col))
                start_col += len(continuation)
        return lines

    def draw_text_segment(
        self,
        win: curses.window,
        y: int,
        x: int,
        line: RenderLine,
        width: int,
        base_attr: int,
    ) -> None:
        if not line.text or width <= 0:
            return
        selection = self.visual_selection_bounds()
        search_spans = self.search_match_spans(line.verse_index)
        for offset, char in enumerate(line.text[:width]):
            absolute_col = line.start_col + offset
            attr = base_attr
            if selection and self.char_is_selected(line.verse_index, absolute_col, selection):
                attr = curses.A_REVERSE if not base_attr else base_attr | curses.A_REVERSE
            if self.col_is_in_spans(absolute_col, search_spans):
                attr = curses.color_pair(PAIR_SEARCH) | curses.A_BOLD
            win.addnstr(y, x + offset, char, 1, attr)

    def position_terminal_cursor(self, content_y: int, text_x: int, content_h: int, text_w: int) -> None:
        if (
            self.command_modal_open
            or self.version_modal_open
            or self.search_input_active
            or self.focus != FOCUS_TEXT
            or not self.verses
        ):
            self.set_cursor_visibility(False)
            return
        lines = self.wrapped_verses(max(1, text_w - 2))
        inner_h = max(0, content_h - 2)
        for row, line in enumerate(lines[self.text_scroll : self.text_scroll + inner_h]):
            line_end = line.start_col + len(line.text)
            if line.verse_index == self.verse_cursor and line.start_col <= self.text_cursor_col <= max(line.start_col, line_end):
                self.set_cursor_visibility(True)
                col = min(max(0, self.text_cursor_col - line.start_col), max(0, len(line.text) - 1))
                self.stdscr.move(content_y + row + 1, text_x + 5 + col)
                return
        self.set_cursor_visibility(False)

    def position_search_cursor(self, y: int, width: int) -> None:
        usable_width = max(0, width - 1)
        if usable_width <= 0:
            self.set_cursor_visibility(False)
            return
        self.set_cursor_visibility(True)
        self.stdscr.move(y, min(len("SEARCH /") + len(self.search_query), usable_width - 1))

    def position_goto_cursor(self, height: int, width: int) -> None:
        modal_y, modal_x, _, modal_w = self.goto_modal_geometry(height, width)
        input_w = max(1, modal_w - 6)
        cursor_x = modal_x + 3 + min(len(self.goto_query), input_w - 1)
        self.set_cursor_visibility(True)
        try:
            self.stdscr.move(modal_y + 2, cursor_x)
        except curses.error:
            self.set_cursor_visibility(False)

    def set_cursor_visibility(self, visible: bool) -> None:
        try:
            curses.curs_set(1 if visible else 0)
        except curses.error:
            pass

    def visual_selection_bounds(self) -> tuple[tuple[int, int], tuple[int, int]] | None:
        if not self.visual_mode or self.visual_anchor is None:
            return None
        current = (self.verse_cursor, self.text_cursor_col)
        start, end = sorted((self.visual_anchor, current))
        return start, end

    def char_is_selected(
        self,
        verse_index: int,
        col: int,
        selection: tuple[tuple[int, int], tuple[int, int]],
    ) -> bool:
        start, end = selection
        if verse_index < start[0] or verse_index > end[0]:
            return False
        if start[0] == end[0]:
            return start[1] <= col <= end[1]
        if verse_index == start[0]:
            return col >= start[1]
        if verse_index == end[0]:
            return col <= end[1]
        return True

    def selected_text(self) -> str:
        selection = self.visual_selection_bounds()
        if not selection:
            return ""
        start, end = selection
        chunks: list[str] = []
        for verse_index in range(start[0], end[0] + 1):
            text = self.verses[verse_index].text
            start_col = start[1] if verse_index == start[0] else 0
            end_col = end[1] if verse_index == end[0] else len(text) - 1
            chunks.append(text[start_col : end_col + 1])
        return "\n".join(chunks)

    def location_label(self) -> str:
        if not self.selected_book:
            return "no book"
        if not self.selected_chapter:
            return f"{self.selected_book.name} | no chapter"
        if self.verses:
            return f"{self.selected_book.name} {self.selected_chapter}:{self.verses[self.verse_cursor].number}"
        return f"{self.selected_book.name} {self.selected_chapter}"


CLIPBOARD_COMMANDS: tuple[tuple[str, ...], ...] = (
    ("pbcopy",),
    ("wl-copy",),
    ("xclip", "-selection", "clipboard"),
    ("xsel", "--clipboard", "--input"),
    ("clip.exe",),
)


def copy_to_clipboard(text: str) -> bool:
    for command in CLIPBOARD_COMMANDS:
        if shutil.which(command[0]) is None:
            continue
        try:
            subprocess.run(
                command,
                input=text,
                text=True,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        return True
    return False


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def scroll_to_cursor(cursor: int, scroll: int, visible: int) -> int:
    if cursor < scroll:
        return cursor
    if cursor >= scroll + visible:
        return cursor - visible + 1
    return scroll


def match_spans(text: str, query: str) -> list[tuple[int, int]]:
    if not query:
        return []
    spans: list[tuple[int, int]] = []
    folded_query = query.casefold()
    query_len = len(query)
    index = 0
    while index <= len(text) - query_len:
        if text[index : index + query_len].casefold() == folded_query:
            spans.append((index, index + query_len))
            index += query_len
        else:
            index += 1
    return spans


def fuzzy_score(text: str, query: str) -> tuple[int, tuple[int, ...]] | None:
    if not query:
        return 0, ()

    folded_text = text.casefold()
    folded_query = query.casefold()
    exact_start = folded_text.find(folded_query)
    if exact_start >= 0:
        positions = tuple(range(exact_start, exact_start + len(query)))
        return 100_000 - exact_start, positions

    positions: list[int] = []
    search_from = 0
    for char in folded_query:
        index = folded_text.find(char, search_from)
        if index < 0:
            return None
        positions.append(index)
        search_from = index + 1

    span = positions[-1] - positions[0] + 1
    gaps = span - len(positions)
    score = 50_000 - span * 10 - gaps * 3 - positions[0]
    for position in positions:
        previous = text[position - 1 : position] if position else " "
        if previous.isspace() or previous in "-:;,.()[]{}\"'":
            score += 15
    return score, tuple(positions)


@dataclass(frozen=True)
class QueryToken:
    text: str
    exact: bool
    anchor: str | None
    negate: bool


def parse_fuzzy_query(query: str) -> list[QueryToken]:
    tokens: list[QueryToken] = []
    for raw in query.split():
        term = raw
        negate = term.startswith("!")
        if negate:
            term = term[1:]
        if not term:
            continue
        exact = negate
        anchor: str | None = None
        if term.startswith("'"):
            exact = True
            term = term[1:]
            if len(term) > 1 and term.endswith("'"):
                anchor = "word"
                term = term[:-1]
        elif term.startswith("^"):
            exact = True
            anchor = "prefix"
            term = term[1:]
        elif term.endswith("$"):
            exact = True
            anchor = "suffix"
            term = term[:-1]
        tokens.append(QueryToken(term, exact, anchor, negate))
    return tokens


def match_token(text: str, token: QueryToken) -> tuple[tuple[int, ...], int] | None:
    term = token.text
    if not term:
        return (), 0

    if not token.exact:
        result = fuzzy_score(text, term)
        if result is None:
            return None
        score, positions = result
        return positions, score

    folded_text = text.casefold()
    folded_term = term.casefold()
    if token.anchor == "prefix":
        matched = folded_text.startswith(folded_term)
        start = 0
    elif token.anchor == "suffix":
        matched = folded_text.endswith(folded_term)
        start = len(text) - len(term)
    elif token.anchor == "word":
        found = re.search(r"\b" + re.escape(term) + r"\b", text, re.IGNORECASE)
        matched = found is not None
        start = found.start() if found else -1
    else:
        start = folded_text.find(folded_term)
        matched = start >= 0

    if token.negate:
        return ((), 0) if not matched else None
    if not matched:
        return None

    positions = tuple(range(start, start + len(term)))
    return positions, 30_000 - max(start, 0)


def score_verse(text: str, tokens: list[QueryToken]) -> tuple[int, tuple[int, ...]] | None:
    total_score = 0
    positions: list[int] = []
    for token in tokens:
        result = match_token(text, token)
        if result is None:
            return None
        token_positions, token_score = result
        total_score += token_score
        positions.extend(token_positions)
    return total_score, tuple(sorted(set(positions)))


def build_fuzzy_matches(verses: list[BibleVerse], query: str) -> list[FuzzyMatch]:
    tokens = parse_fuzzy_query(query)
    if not tokens:
        return [FuzzyMatch(verse, 0, ()) for verse in verses]

    matches: list[FuzzyMatch] = []
    for verse in verses:
        result = score_verse(verse.text, tokens)
        if result is None:
            continue
        score, positions = result
        matches.append(FuzzyMatch(verse, score, positions))

    return sorted(
        matches,
        key=lambda match: (
            -match.score,
            match.verse.book_order,
            match.verse.chapter_number,
            match.verse.verse_number,
        ),
    )


def snippet_parts(text: str, positions: tuple[int, ...], width: int) -> tuple[str, int, str, str]:
    if width <= 0:
        return "", 0, "", ""
    if len(text) <= width:
        return "", 0, text, ""

    marker = "..."
    prefix = marker
    suffix = marker
    target = positions[0] if positions else 0
    content_width = max(1, width - len(prefix) - len(suffix))
    start = max(0, target - content_width // 3)
    end = start + content_width
    if end > len(text):
        end = len(text)
        start = max(0, end - content_width)

    if start == 0:
        prefix = ""
        end = min(len(text), width - len(suffix))
    if end == len(text):
        suffix = ""
        start = max(0, len(text) - (width - len(prefix)))

    return prefix, start, text[start:end], suffix


def reference_width(verses: list[BibleVerse]) -> int:
    if not verses:
        return 8
    max_book = max(len(BOOK_ABBREVIATIONS.get(verse.book_name, verse.book_name)) for verse in verses)
    max_chapter = max(len(str(verse.chapter_number)) for verse in verses)
    max_verse = max(len(str(verse.verse_number)) for verse in verses)
    return max_book + 1 + max_chapter + 1 + max_verse
