"""Curses TUI for browsing a Bible version's SQLite database."""

from __future__ import annotations

import curses
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import termios
import textwrap
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from bible_tui import __version__
from bible_tui.config import DEFAULT_YANK_FORMAT
from bible_tui.highlights import HIGHLIGHT_COLORS, HighlightError, HighlightStore
from bible_tui.marks import MarkError, MarkStore, VerseKey
from bible_tui.store import BOOK_ABBREVIATIONS, BibleStore, BibleVerse, Book, Verse
from bible_tui.update import MANUAL_UPDATE, REPOSITORY_URL, Install, UpdateCheck
from bible_tui.versions import BibleVersion, find_version

FOCUS_BOOKS = 0
FOCUS_CHAPTERS = 1
FOCUS_TEXT = 2
KEY_CTRL_B = 2
KEY_CTRL_D = 4
KEY_CTRL_F = 6
KEY_CTRL_G = 7
KEY_CTRL_N = 14
KEY_CTRL_P = 16
KEY_CTRL_S = 19
KEY_CTRL_U = 21
KEY_CTRL_W = 23
KEY_CTRL_O = 15
KEY_CTRL_Q = 17
KEY_CTRL_V = 22
KEY_TAB = 9
PAIR_SEARCH = 8
PAIR_ERROR = 9
PAIR_HEADING = 10
PAIR_SIGN = 11
PAIR_SIGN_SELECTED = 12
PAIR_HIGHLIGHT_BASE = 13  # One pair per HIGHLIGHT_COLORS entry, in order.

# Highlight backgrounds: (256-color background, 8-color background, 8-color foreground).
# 256-color terminals get soft tints with black text, like a paper highlighter.
HIGHLIGHT_PALETTE: dict[str, tuple[int, int, int]] = {
    "yellow": (222, curses.COLOR_YELLOW, curses.COLOR_BLACK),
    "green": (114, curses.COLOR_GREEN, curses.COLOR_BLACK),
    "blue": (111, curses.COLOR_CYAN, curses.COLOR_BLACK),
    "purple": (183, curses.COLOR_BLUE, curses.COLOR_WHITE),
    "pink": (218, curses.COLOR_MAGENTA, curses.COLOR_WHITE),
    "orange": (215, curses.COLOR_RED, curses.COLOR_WHITE),
}
PICKER_CLEAR = len(HIGHLIGHT_COLORS)  # The picker row after the colors.

LIST_MARKS = "marks"
LIST_HIGHLIGHTS = "highlights"
LIST_OPEN_KEYS: dict[str, tuple[int, ...]] = {
    LIST_MARKS: (ord("M"), ord("'"), ord("`")),
    LIST_HIGHLIGHTS: (ord("C"), ord('"')),
}

# The text pane gutter: a sign column (like Vim's signcolumn=yes), then the verse number.
SIGN_WIDTH = 2
NUMBER_WIDTH = 4
GUTTER_WIDTH = SIGN_WIDTH + NUMBER_WIDTH
MARK_SIGN_NERD_FONT = "\uf02e"  # nf-fa-bookmark, present in Nerd Fonts v2 and v3
MARK_SIGN_PLAIN = "\u25cf"  # ● renders in practically every font

# Each glyph as (Nerd Font icon, plain fallback). Nerd Fonts are opt-in (the nerd_font setting) and never
# detected. The icons are all Font Awesome 4 (nf-fa-*), whose code points are the same in Nerd Fonts v2 and
# v3. Put a space after an icon: non-Mono Nerd Fonts draw it wider than the one cell curses counts.
GLYPHS: dict[str, tuple[str, str]] = {
    "mark": (MARK_SIGN_NERD_FONT, MARK_SIGN_PLAIN),
    "missing": ("\uf070", ""),  # nf-fa-eye_slash: a verse one split pane's version leaves out
    "search": ("\uf002", "SEARCH"),  # nf-fa-search: the search footer prefix
    "find": ("\uf002", "FIND >"),  # nf-fa-search: the fuzzy finder prompt
    "goto": ("\uf05b", ""),  # nf-fa-crosshairs: the go-to modal title
    "yank": ("\uf0ea", ""),  # nf-fa-clipboard: copied-to-clipboard messages
    "error": ("\uf071", ""),  # nf-fa-warning: failure messages
    "current": ("\uf00c", "*"),  # nf-fa-check: the version a pane shows now, in the version picker
    "update": ("\uf0aa", ""),  # nf-fa-arrow_circle_up: the new-release message
}

# Footer messages: what an action did. They fade after a few seconds; failures stay longer.
MESSAGE_INFO = "info"
MESSAGE_YANK = "yank"
MESSAGE_ERROR = "error"
MESSAGE_UPDATE = "update"
MESSAGE_SECONDS = {MESSAGE_INFO: 3.0, MESSAGE_YANK: 3.0, MESSAGE_ERROR: 6.0, MESSAGE_UPDATE: 10.0}
UPDATE_POLL_MS = 250  # How often the run loop looks for the background update check's answer.
MISSING_SHADE = "\u2591"  # ░ fills a verse that one split pane's version leaves out

# A split shows a second text pane beside (vertical) or below (horizontal) the first.
SPLIT_VERTICAL = "vertical"
SPLIT_HORIZONTAL = "horizontal"
SPLITS = (SPLIT_VERTICAL, SPLIT_HORIZONTAL)
MIN_PANE_WIDTH = GUTTER_WIDTH + 2 + 16  # Borders plus a readable line of text.
MIN_PANE_HEIGHT = 5  # Borders plus three lines.

# Version picker modes.
PICK_VERSION = "version"  # Switch the only pane's version.
PICK_NEW_PANE = "new_pane"  # Choose the version for a new split pane.
PICK_PANES = "panes"  # Two columns, one per split pane.


@dataclass(frozen=True)
class RenderLine:
    verse_index: int
    verse_number: str
    text: str
    start_col: int
    missing: bool = False


@dataclass(frozen=True)
class MissingVerse(Verse):
    """Stands in for a verse one split pane's version leaves out, so both panes keep the same rows."""

    text: str = ""


@dataclass
class SplitPane:
    """The second text pane. It shows the same chapter as the first in its own version."""

    version: BibleVersion
    store: BibleStore
    books: dict[int, Book]  # By sort order, since book ids differ between databases.
    verses: list[Verse] = field(default_factory=list)
    all_verses: list[BibleVerse] | None = None


@dataclass(frozen=True)
class Command:
    name: str
    keybind: str
    action: str


@dataclass(frozen=True)
class ListRow:
    """A row in the marks or highlights list. ``color`` is None for marks."""

    key: VerseKey
    created_at: str
    color: str | None = None


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


@dataclass(frozen=True)
class ExCommand:
    """A ``:`` command. Like Vim, it runs from any prefix at least as long as ``short`` (``:q``)."""

    name: str
    short: str
    args: str
    description: str
    aliases: tuple[str, ...] = ()


EX_COMMANDS: tuple[ExCommand, ...] = (
    ExCommand("quit", "q", "", "quit bible-tui", ("q!", "qa", "qa!", "qall", "wq", "wq!", "x")),
    ExCommand("find", "fin", "[words]", "fuzzy find across the Bible"),
    ExCommand("set", "se", "version=<name>", "change the focused pane's version"),
    ExCommand("vsplit", "vs", "", "split side by side"),
    ExCommand("split", "sp", "", "split top and bottom"),
    ExCommand("close", "clo", "", "close the focused pane"),
    ExCommand("only", "on", "", "close the other pane"),
    ExCommand("marks", "marks", "", "list marks"),
    ExCommand("highlights", "hi", "", "list highlights"),
    ExCommand("update", "up", "", "update bible-tui and restart"),
    ExCommand("about", "ab", "", "version and project link"),
)


@dataclass(frozen=True)
class Completion:
    """A ``:`` command-line suggestion: Tab replaces the line with ``text``."""

    text: str
    label: str
    description: str = ""


COMMAND_GROUPS: tuple[tuple[str, tuple[Command, ...]], ...] = (
    (
        "Navigation",
        (
            Command("move up", "k / up", "move_up"),
            Command("move down", "j / down", "move_down"),
            Command("move left", "h / left", "move_left"),
            Command("move right", "l / right", "move_right"),
            Command("open book or chapter", "enter", "select"),
            Command("next pane", "tab", "next_pane"),
            Command("previous pane", "shift+tab", "previous_pane"),
            Command("page up", "page up / ctrl+b", "page_up"),
            Command("page down", "page down / ctrl+f", "page_down"),
            Command("half page up", "ctrl+u", "half_page_up"),
            Command("half page down", "ctrl+d", "half_page_down"),
            Command("first item", "home / gg", "home"),
            Command("last item", "end / G", "end"),
            Command("next chapter", "]", "next_chapter"),
            Command("previous chapter", "[", "previous_chapter"),
        ),
    ),
    (
        "Find",
        (
            Command("go to reference", "ctrl+g / :John 3:16", "go_to_reference"),
            Command("fuzzy find", "ctrl+s", "fuzzy_find"),
            Command("search", "/", "search"),
            Command("next match", "n", "next_match"),
            Command("previous match", "N", "previous_match"),
        ),
    ),
    (
        "Move in text",
        (
            Command("next word", "w", "next_word"),
            Command("previous word", "b", "previous_word"),
            Command("end of word", "e", "end_of_word"),
            Command("start of verse", "0", "start_of_verse"),
            Command("end of verse", "$", "end_of_verse"),
        ),
    ),
    (
        "Select and copy",
        (
            Command("select text", "v", "visual_mode"),
            Command("select verses", "V", "visual_line_mode"),
            Command("copy selection", "y", "yank_selection"),
            Command("copy verse", "yy", "yank_verse"),
        ),
    ),
    (
        "Marks and highlights",
        (
            Command("toggle mark", "m", "toggle_mark"),
            Command("highlight", "c", "highlight"),
            Command("list marks", "M / '", "list_marks"),
            Command("list highlights", 'C / "', "list_highlights"),
        ),
    ),
    (
        "Versions and splits",
        (
            Command("switch version", "t", "switch_version"),
            Command("split side by side", "ctrl+w v", "split_vertical"),
            Command("split top and bottom", "ctrl+w s", "split_horizontal"),
            Command("switch pane", "ctrl+w w / left / right", "switch_pane"),
            Command("close pane", "ctrl+w q", "close_pane"),
            Command("close other pane", "ctrl+w o", "close_other_pane"),
            Command("toggle book order", "a", "toggle_sort"),
        ),
    ),
    (
        "App",
        (
            Command("command line", ":", "command_line"),
            Command("commands", "ctrl+p / ?", "commands"),
            Command("about bible-tui", ":about", "about"),
            Command("update bible-tui", ":update", "update"),
            Command("quit", "q", "quit"),
        ),
    ),
)

TEXT_MOTIONS: dict[str, str] = {
    "start_of_verse": "0",
    "end_of_verse": "$",
    "next_word": "w",
    "previous_word": "b",
    "end_of_word": "e",
}

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
        on_split_change: Callable[[str | None, BibleVersion | None], None] | None = None,
        marks: MarkStore | None = None,
        highlights: HighlightStore | None = None,
        nerd_font: bool = False,
        yank_format: str = DEFAULT_YANK_FORMAT,
        update_check: UpdateCheck | None = None,
        install: Install | None = None,
    ) -> None:
        self.stdscr = stdscr
        self._message = ""
        self.message_kind = MESSAGE_INFO
        self.message_until = 0.0  # time.monotonic() when the footer message goes away
        self.yank_format = yank_format
        self.store = store
        self.version = version
        self.versions: tuple[BibleVersion, ...] = tuple(versions) or (version,)
        self.on_version_change = on_version_change
        self.on_split_change = on_split_change
        self.update_check = update_check
        self.install = install
        self.restart_requested = False  # Set by a successful :update; the CLI restarts the app.
        self.restart_position: tuple[int | None, int | None, int | None] = (None, None, None)
        self.marks = marks if marks is not None else MarkStore(None)
        self.highlights = highlights if highlights is not None else HighlightStore(None)
        self.glyphs = {name: icon if nerd_font else plain for name, (icon, plain) in GLYPHS.items()}
        self.mark_sign = self.glyphs["mark"]
        self.version_modal_open = False
        self.version_mode = PICK_VERSION
        self.version_column = 0  # The picker column (split pane) the cursor is in.
        self.version_cursors = [0, 0]
        self.version_scrolls = [0, 0]
        self.new_pane_split = SPLIT_VERTICAL  # Orientation waiting on the PICK_NEW_PANE choice.
        self.split: str | None = None  # SPLIT_VERTICAL or SPLIT_HORIZONTAL while split.
        self.split_pane: SplitPane | None = None
        self.active_pane = 0  # The text pane that gets visual mode, yank, and search.
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
        self.visual_line = False
        self.visual_anchor: tuple[int, int] | None = None
        self.pending_y = False
        self.pending_g = False
        self.pending_w = False
        self.message = ""
        self.command_modal_open = False
        self.command_cursor = 0
        self.command_scroll = 0
        self.cmdline_active = False  # The ":" command line in the footer.
        self.cmdline_text = ""
        self.cmdline_cursor = 0  # The highlighted completion.
        self.cmdline_chosen = False  # True once arrows or ctrl+n/ctrl+p move through completions.
        self.cmdline_scroll = 0
        self.search_scope: int | None = None
        self.search_pane = 0  # The text pane a text search looks in.
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
        self.list_kind: str | None = None  # LIST_MARKS or LIST_HIGHLIGHTS while the list modal is open.
        self.list_rows: list[ListRow] = []
        self.list_cursor = 0
        self.list_scroll = 0
        self.picker_open = False
        self.picker_cursor = 0
        self.about_open = False
        self.picker_keys: list[VerseKey] = []
        self.last_highlight_color = HIGHLIGHT_COLORS[0]
        if self.books:
            self.select_book(self.book_cursor)

    @property
    def message(self) -> str:
        return self._message

    @message.setter
    def message(self, text: str) -> None:
        self.set_message(text)

    def set_message(self, text: str, kind: str = MESSAGE_INFO) -> None:
        """Show ``text`` in the footer for a few seconds. ``kind`` picks the color, icon, and time."""
        self._message = text
        self.message_kind = kind
        self.message_until = time.monotonic() + MESSAGE_SECONDS[kind] if text else 0.0

    def show_error(self, text: str) -> None:
        self.set_message(text, MESSAGE_ERROR)

    def expire_message(self) -> None:
        if self._message and time.monotonic() >= self.message_until:
            self._message = ""

    def message_timeout_ms(self) -> int:
        """How long ``getch`` may wait before the footer message needs clearing (-1: no limit)."""
        if not self._message:
            return -1
        return max(1, int((self.message_until - time.monotonic()) * 1000) + 1)

    def input_timeout_ms(self) -> int:
        """The ``getch`` timeout: until the message fades, or sooner while an update check is out."""
        timeout = self.message_timeout_ms()
        if self.update_check is not None and self.update_check.pending:
            timeout = UPDATE_POLL_MS if timeout < 0 else min(timeout, UPDATE_POLL_MS)
        return timeout

    def poll_update_check(self) -> None:
        """Announce a newer release once, without covering a message that's showing."""
        if self.update_check is None or self._message:
            return
        latest = self.update_check.poll()
        if latest is not None:
            self.set_message(f"bible-tui {latest} is out: :update", MESSAGE_UPDATE)

    def run_update(self) -> bool:
        """``:update``: run the install's update command outside curses. False means restart now."""
        check = self.update_check
        if check is not None and check.latest is not None and not check.update_available:
            self.message = f"bible-tui {check.current} is up to date"
            return True
        if self.install is None:
            self.show_error(f"can't update this install automatically; use {MANUAL_UPDATE}")
            return True
        curses.def_prog_mode()
        curses.endwin()
        print(f"Updating bible-tui: {self.install.command_text}\n", flush=True)
        try:
            code = subprocess.run(self.install.command).returncode
        except OSError as error:
            print(error)
            code = -1
        if code == 0:
            # Back into curses mode, so curses.wrapper's own endwin() on the way out succeeds.
            curses.reset_prog_mode()
            self.stdscr.refresh()
            self.restart_requested = True
            self.restart_position = self.current_position()
            return False
        try:
            input("\nThe update failed. Press Enter to go back to bible-tui.")
        except EOFError:
            pass
        curses.reset_prog_mode()
        self.stdscr.clear()
        self.show_error(f"update failed ({self.install.command_text} exited with {code})")
        return True

    def close(self) -> None:
        self.store.close()
        if self.split_pane is not None:
            self.split_pane.store.close()

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
        curses.init_pair(PAIR_SIGN, curses.COLOR_BLUE, -1)
        curses.init_pair(PAIR_SIGN_SELECTED, curses.COLOR_BLUE, curses.COLOR_WHITE)
        rich = getattr(curses, "COLORS", 0) >= 256
        for index, name in enumerate(HIGHLIGHT_COLORS):
            tint, background, foreground = HIGHLIGHT_PALETTE[name]
            try:
                if rich:
                    curses.init_pair(PAIR_HIGHLIGHT_BASE + index, curses.COLOR_BLACK, tint)
                else:
                    curses.init_pair(PAIR_HIGHLIGHT_BASE + index, foreground, background)
            except curses.error:
                curses.init_pair(PAIR_HIGHLIGHT_BASE + index, foreground, background)
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
            self.expire_message()
            self.poll_update_check()
            self.draw()
            self.stdscr.timeout(self.input_timeout_ms())
            key = self.stdscr.getch()
            if key == -1:
                continue  # Timed out to clear a message or collect the update check.
            if not self.handle_key(key):
                return

    def handle_key(self, key: int) -> bool:
        if self.version_modal_open:
            return self.handle_version_modal_key(key)
        if self.picker_open:
            return self.handle_picker_key(key)
        if self.about_open:
            return self.handle_about_key(key)
        if self.list_kind is not None:
            return self.handle_list_modal_key(key)
        if self.goto_open:
            return self.handle_goto_key(key)
        if self.fuzzy_open:
            return self.handle_fuzzy_key(key)
        if self.command_modal_open:
            return self.handle_command_modal_key(key)
        if self.search_input_active:
            self.handle_search_input_key(key)
            return True
        if self.cmdline_active:
            return self.handle_cmdline_key(key)
        pending_g = self.pending_g
        self.pending_g = False
        if self.pending_w:
            self.pending_w = False
            self.handle_window_key(key)
            return True
        if key == KEY_CTRL_W:
            self.pending_y = False
            self.pending_w = True
            self.message = "ctrl+w: v side by side, s top and bottom, w switch, q close, o close other"
            return True
        if key in (KEY_CTRL_P, ord("?")):
            self.open_command_modal()
            return True
        if key == KEY_CTRL_S:
            self.open_fuzzy_finder()
            return True
        if key == KEY_CTRL_G:
            self.open_goto_modal()
            return True
        if key == ord(":"):
            self.open_cmdline()
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
        if key in (ord("v"), ord("V")) and self.focus == FOCUS_TEXT and self.verses:
            self.pending_y = False
            self.toggle_visual_mode(line=key == ord("V"))
            return True
        if key == ord("y") and self.focus == FOCUS_TEXT and self.verses:
            self.handle_yank_key()
            return True
        if key == ord("m"):
            self.pending_y = False
            self.toggle_mark()
            return True
        if key == ord("c"):
            self.pending_y = False
            self.open_highlight_picker()
            return True
        for kind, open_keys in LIST_OPEN_KEYS.items():
            if key in open_keys:
                self.open_list_modal(kind)
                return True
        if key in (ord("h"), ord("l")) and self.focus == FOCUS_TEXT and self.verses:
            self.pending_y = False
            if key == ord("h") and self.text_cursor_col == 0 and not self.visual_mode:
                self.move_focus_left()  # Already at the start of the verse: go back a pane.
            else:
                self.move_text_cursor(-1 if key == ord("h") else 1)
            return True
        if key in (ord("0"), ord("$")) and self.focus == FOCUS_TEXT and self.verses:
            self.pending_y = False
            self.move_to_verse_edge(key == ord("$"))
            return True
        if key in (ord("w"), ord("b"), ord("e")) and self.focus == FOCUS_TEXT and self.verses:
            self.pending_y = False
            self.move_word(chr(key))
            return True
        if key in (ord("]"), ord("[")):
            self.pending_y = False
            self.step_chapter(1 if key == ord("]") else -1)
            return True
        if key in (KEY_TAB, curses.KEY_BTAB):
            self.pending_y = False
            self.cycle_focus(1 if key == KEY_TAB else -1)
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
        if key in (curses.KEY_PPAGE, KEY_CTRL_B):
            self.pending_y = False
            self.page(-1)
            return True
        if key in (curses.KEY_NPAGE, KEY_CTRL_F):
            self.pending_y = False
            self.page(1)
            return True
        if key in (KEY_CTRL_U, KEY_CTRL_D):
            self.pending_y = False
            self.page(-1 if key == KEY_CTRL_U else 1, half=True)
            return True
        if key == curses.KEY_HOME or (key == ord("g") and pending_g):
            self.pending_y = False
            self.home()
            return True
        if key == ord("g"):
            self.pending_y = False
            self.pending_g = True
            return True
        if key in (curses.KEY_END, ord("G")):
            self.pending_y = False
            self.end()
            return True
        self.pending_y = False
        return True

    def handle_window_key(self, key: int) -> None:
        """The key after ``ctrl+w``, as in Vim's window commands."""
        self.message = ""
        if key in (ord("v"), KEY_CTRL_V):
            self.open_split_picker(SPLIT_VERTICAL)
        elif key in (ord("s"), ord("S"), KEY_CTRL_S):
            self.open_split_picker(SPLIT_HORIZONTAL)
        elif key in (ord("q"), ord("c"), KEY_CTRL_Q):
            self.close_pane(self.active_pane)
        elif key in (ord("o"), KEY_CTRL_O):
            if self.split_pane is None:
                self.message = "already only one pane"
            else:
                self.close_pane(1 - self.active_pane)
        elif key in (ord("w"), KEY_CTRL_W, ord("p")):
            self.focus_pane(1 - self.active_pane if self.focus == FOCUS_TEXT else self.active_pane)
        elif key in (ord("h"), ord("k"), curses.KEY_LEFT, curses.KEY_UP):
            self.focus_pane(0)
        elif key in (ord("l"), ord("j"), curses.KEY_RIGHT, curses.KEY_DOWN):
            self.focus_pane(1 if self.split_pane is not None else 0)

    def handle_command_modal_key(self, key: int) -> bool:
        if key in (27, ord("?")):
            self.close_command_modal()
            return True
        if key in (curses.KEY_UP, ord("k"), curses.KEY_DOWN, ord("j")):
            step = -1 if key in (curses.KEY_UP, ord("k")) else 1
            self.command_cursor = (self.command_cursor + step) % len(COMMANDS)  # Wraps around at either end.
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
        if action == "update":
            return self.run_update()
        if action == "about":
            self.open_about_modal()
            return True
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
        elif action == "half_page_up":
            self.page(-1, half=True)
        elif action == "half_page_down":
            self.page(1, half=True)
        elif action == "next_pane":
            self.cycle_focus(1)
        elif action == "previous_pane":
            self.cycle_focus(-1)
        elif action == "next_chapter":
            self.step_chapter(1)
        elif action == "previous_chapter":
            self.step_chapter(-1)
        elif action in TEXT_MOTIONS:
            if self.focus == FOCUS_TEXT and self.verses:
                if action in ("start_of_verse", "end_of_verse"):
                    self.move_to_verse_edge(action == "end_of_verse")
                else:
                    self.move_word(TEXT_MOTIONS[action])
            else:
                self.message = "select text to move the cursor"
        elif action == "commands":
            self.open_command_modal()
        elif action == "command_line":
            self.open_cmdline()
        elif action == "toggle_mark":
            self.toggle_mark()
        elif action == "list_marks":
            self.open_list_modal(LIST_MARKS)
        elif action == "highlight":
            self.open_highlight_picker()
        elif action == "list_highlights":
            self.open_list_modal(LIST_HIGHLIGHTS)
        elif action == "home":
            self.home()
        elif action == "end":
            self.end()
        elif action == "toggle_sort":
            self.toggle_book_order()
        elif action == "switch_version":
            self.open_version_modal()
        elif action == "split_vertical":
            self.open_split_picker(SPLIT_VERTICAL)
        elif action == "split_horizontal":
            self.open_split_picker(SPLIT_HORIZONTAL)
        elif action == "switch_pane":
            self.handle_window_key(ord("w"))
        elif action == "close_pane":
            self.close_pane(self.active_pane)
        elif action == "close_other_pane":
            self.handle_window_key(ord("o"))
        elif action in ("visual_mode", "visual_line_mode"):
            if self.focus == FOCUS_TEXT and self.verses:
                self.toggle_visual_mode(line=action == "visual_line_mode")
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
                self.yank_current_verse()
            else:
                self.message = "no verse selected"
        return True

    def open_command_modal(self) -> None:
        self.pending_y = False
        self.command_modal_open = True
        self.ensure_command_visible()

    def close_command_modal(self) -> None:
        self.command_modal_open = False

    @property
    def version_cursor(self) -> int:
        return self.version_cursors[self.version_column]

    @version_cursor.setter
    def version_cursor(self, value: int) -> None:
        self.version_cursors[self.version_column] = value

    def version_index(self, version: BibleVersion) -> int:
        return next((index for index, item in enumerate(self.versions) if item == version), 0)

    def prepare_version_modal(self) -> None:
        self.pending_y = False
        self.exit_visual_mode()
        self.command_modal_open = False
        self.search_input_active = False
        self.version_modal_open = True
        self.version_scrolls = [0, 0]
        self.message = ""

    def open_version_modal(self) -> None:
        self.prepare_version_modal()
        if self.split_pane is not None:
            self.version_mode = PICK_PANES
            self.version_cursors = [self.version_index(self.version), self.version_index(self.split_pane.version)]
            self.version_column = self.active_pane
        else:
            self.version_mode = PICK_VERSION
            self.version_cursors = [self.version_index(self.version), 0]
            self.version_column = 0
        for column in (0, 1):
            self.ensure_version_visible(column)

    def open_split_picker(self, split: str) -> None:
        """Start a split: the version picker chooses the new pane's version."""
        if self.split_pane is not None:
            self.message = "2 panes max"
            return
        _, _, content_h, _, _, text_w = self.layout()
        if split == SPLIT_VERTICAL and text_w < 2 * MIN_PANE_WIDTH:
            self.message = "terminal too narrow to split side by side"
            return
        if split == SPLIT_HORIZONTAL and content_h < 2 * MIN_PANE_HEIGHT:
            self.message = "terminal too short to split top and bottom"
            return
        self.prepare_version_modal()
        self.version_mode = PICK_NEW_PANE
        self.new_pane_split = split
        self.version_column = 0
        # Usually you split to compare, so start on a different version.
        other = next((index for index, item in enumerate(self.versions) if item != self.version), None)
        self.version_cursors = [self.version_index(self.version) if other is None else other, 0]
        self.ensure_version_visible(0)

    def close_version_modal(self) -> None:
        self.version_modal_open = False
        self.version_mode = PICK_VERSION
        self.version_column = 0

    def handle_version_modal_key(self, key: int) -> bool:
        if key in (27, ord("t")):
            self.close_version_modal()
            return True
        if self.version_mode == PICK_PANES and key in (
            curses.KEY_LEFT, curses.KEY_RIGHT, ord("h"), ord("l"), KEY_TAB, curses.KEY_BTAB
        ):
            if key in (curses.KEY_LEFT, ord("h")):
                self.version_column = 0
            elif key in (curses.KEY_RIGHT, ord("l")):
                self.version_column = 1
            else:
                self.version_column = 1 - self.version_column
            return True
        if key in (curses.KEY_UP, ord("k")):
            self.version_cursor = clamp(self.version_cursor - 1, 0, len(self.versions) - 1)
            self.ensure_version_visible(self.version_column)
            return True
        if key in (curses.KEY_DOWN, ord("j")):
            self.version_cursor = clamp(self.version_cursor + 1, 0, len(self.versions) - 1)
            self.ensure_version_visible(self.version_column)
            return True
        if key in (ord("\n"), curses.KEY_ENTER, 10, 13):
            mode = self.version_mode
            first, second = (self.versions[cursor] for cursor in self.version_cursors)
            self.close_version_modal()
            if mode == PICK_NEW_PANE:
                self.open_split(self.new_pane_split, first)
            elif mode == PICK_PANES:
                messages = []
                # The second pane first: switching the first restores the place against it.
                if self.split_pane is not None and second != self.split_pane.version:
                    self.switch_split_version(second)
                    messages.append(self.message)
                if first != self.version:
                    self.switch_version(first)
                    messages.append(self.message)
                self.message = "; ".join(messages)
            else:
                self.switch_version(first)
            return True
        return True

    def ensure_version_visible(self, column: int) -> None:
        self.version_scrolls[column] = scroll_to_cursor(
            self.version_cursors[column],
            self.version_scrolls[column],
            self.version_visible_rows(),
        )

    def version_visible_rows(self) -> int:
        height, _ = self.stdscr.getmaxyx()
        extra = 2 if self.version_mode == PICK_PANES else 0  # Column headings and hints.
        return min(len(self.versions), max(1, height - 6 - extra))

    def switch_version(
        self,
        version: BibleVersion,
        position: tuple[int | None, int | None, int | None] | None = None,
    ) -> None:
        """Change the first (or only) pane's version. It also supplies the book and chapter lists."""
        if version == self.version:
            return
        try:
            store = BibleStore(version.path)
            books = store.books(self.alphabetical)
        except sqlite3.Error as error:
            self.show_error(f"could not open {version.name}: {error}")
            return

        if position is None:
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
                self.show_error(f"switched to {version.name} (could not save state)")

    def open_split_pane(self, version: BibleVersion) -> SplitPane | None:
        try:
            store = BibleStore(version.path)
            books = {book.sort_order: book for book in store.books(False)}
        except sqlite3.Error as error:
            self.show_error(f"could not open {version.name}: {error}")
            return None
        return SplitPane(version, store, books)

    def open_split(self, split: str, version: BibleVersion, *, restoring: bool = False) -> bool:
        """Add the second text pane. ``restoring`` reopens a remembered split at launch: focus stays put
        and nothing is saved."""
        if self.split_pane is not None:
            self.message = "2 panes max"
            return False
        pane = self.open_split_pane(version)
        if pane is None:
            return False
        number = self.current_position()[2]
        self.split = split
        self.split_pane = pane
        self.load_chapter_verses()
        self.cursor_to_verse(number)
        if not restoring:
            self.focus_pane(1)
            self.message = f"opened {version.name}"
            self.notify_split_change()
        self.ensure_visible()
        return True

    def switch_split_version(self, version: BibleVersion) -> None:
        if self.split_pane is None or version == self.split_pane.version:
            return
        pane = self.open_split_pane(version)
        if pane is None:
            return
        number = self.current_position()[2]
        if self.search_scope == FOCUS_TEXT and self.search_pane == 1:
            self.clear_search()
        self.split_pane.store.close()
        self.split_pane = pane
        self.load_chapter_verses()
        self.cursor_to_verse(number)
        self.clamp_text_cursor()
        self.ensure_visible()
        self.message = f"switched to {version.name}"
        self.notify_split_change()

    def close_pane(self, index: int) -> None:
        """Close a split pane. Closing the first pane hands its place to the second pane's version."""
        if self.split_pane is None:
            self.message = "only one pane: q quits"
            return
        position = self.current_position()
        kept = self.split_pane.version
        self.exit_visual_mode()
        if self.search_scope == FOCUS_TEXT:
            self.clear_search()
        self.split_pane.store.close()
        self.split_pane = None
        self.split = None
        self.active_pane = 0
        self.load_chapter_verses()
        self.cursor_to_verse(position[2])
        self.clamp_text_cursor()
        if index == 0 and kept != self.version:
            self.switch_version(kept, position)
        self.ensure_visible()
        self.notify_split_change()
        if index == 0:
            self.message = f"closed pane; showing {self.version.name}"
        else:
            self.message = "closed pane"

    def notify_split_change(self) -> None:
        if self.on_split_change is None:
            return
        try:
            self.on_split_change(self.split, self.split_pane.version if self.split_pane else None)
        except OSError:
            self.show_error(f"{self.message} (could not save state)")

    def focus_pane(self, index: int) -> None:
        """Move focus to a text pane (0 is the left or top pane)."""
        if not self.verses:
            self.message = "select a chapter first"
            return
        index = index if self.split_pane is not None else 0
        if index != self.active_pane:
            self.exit_visual_mode()
            self.active_pane = index
        self.pending_y = False
        self.focus = FOCUS_TEXT
        self.clamp_text_cursor()
        self.ensure_visible()

    def pane_verses(self, index: int) -> list[Verse]:
        if index == 1 and self.split_pane is not None:
            return self.split_pane.verses
        return self.verses

    @property
    def active_verses(self) -> list[Verse]:
        """The focused text pane's verses. Both panes have the same rows, so only the text differs."""
        return self.pane_verses(self.active_pane)

    def pane_version(self, index: int) -> BibleVersion:
        if index == 1 and self.split_pane is not None:
            return self.split_pane.version
        return self.version

    def load_chapter_verses(self) -> None:
        """Load the selected chapter into each pane, lined up by verse number when split."""
        if self.selected_book is None or self.selected_chapter is None:
            self.verses = []
            if self.split_pane is not None:
                self.split_pane.verses = []
            return
        primary = self.store.verses(self.selected_book.id, self.selected_chapter)
        if self.split_pane is None:
            self.verses = primary
            return
        book = self.split_pane.books.get(self.selected_book.sort_order)
        secondary = self.split_pane.store.verses(book.id, self.selected_chapter) if book else []
        self.verses, self.split_pane.verses = align_verses(primary, secondary)

    def cursor_to_verse(self, number: int | None) -> None:
        """Put the verse cursor on a verse number, or the nearest earlier verse."""
        if number is None or not self.verses:
            self.verse_cursor = 0
            return
        self.verse_cursor = max(
            (index for index, item in enumerate(self.verses) if item.number <= number),
            default=0,
        )

    def clamp_text_cursor(self) -> None:
        verses = self.active_verses
        if not verses:
            self.text_cursor_col = 0
            return
        self.verse_cursor = clamp(self.verse_cursor, 0, len(verses) - 1)
        max_col = max(0, len(verses[self.verse_cursor].text) - 1)
        self.text_cursor_col = clamp(self.text_cursor_col, 0, max_col)

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
        self.selected_chapter = None
        self.load_chapter_verses()
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
            self.cursor_to_verse(verse)

    def open_list_modal(self, kind: str) -> None:
        self.pending_y = False
        self.exit_visual_mode()
        self.command_modal_open = False
        self.search_input_active = False
        self.list_kind = kind
        if kind == LIST_MARKS:
            self.list_rows = [ListRow(key, created_at) for key, created_at in self.marks.newest_first()]
        else:
            self.list_rows = [
                ListRow(key, highlight.created_at, highlight.color)
                for key, highlight in self.highlights.newest_first()
            ]
        self.list_cursor = 0
        self.list_scroll = 0
        self.message = ""

    def close_list_modal(self) -> None:
        self.list_kind = None

    def handle_list_modal_key(self, key: int) -> bool:
        if key == 27 or key in LIST_OPEN_KEYS[self.list_kind]:
            self.close_list_modal()
            return True
        last = max(0, len(self.list_rows) - 1)
        page = self.list_visible_rows()
        moves = {
            curses.KEY_UP: self.list_cursor - 1,
            ord("k"): self.list_cursor - 1,
            curses.KEY_DOWN: self.list_cursor + 1,
            ord("j"): self.list_cursor + 1,
            curses.KEY_PPAGE: self.list_cursor - page,
            KEY_CTRL_B: self.list_cursor - page,
            curses.KEY_NPAGE: self.list_cursor + page,
            KEY_CTRL_F: self.list_cursor + page,
            curses.KEY_HOME: 0,
            ord("g"): 0,
            curses.KEY_END: last,
            ord("G"): last,
        }
        if key in moves:
            self.list_cursor = clamp(moves[key], 0, last)
            self.list_scroll = scroll_to_cursor(self.list_cursor, self.list_scroll, page)
            return True
        if key in (ord("\n"), curses.KEY_ENTER, 10, 13):
            self.close_list_modal()
            if self.list_rows:
                self.jump_to_key(self.list_rows[self.list_cursor].key)
            return True
        if key in (ord("d"), curses.KEY_DC) and self.list_rows:
            self.delete_selected_list_row()
            return True
        return True

    def delete_selected_list_row(self) -> None:
        key = self.list_rows[self.list_cursor].key
        try:
            if self.list_kind == LIST_MARKS:
                self.marks.remove(key)
            else:
                self.highlights.remove(key)
        except (MarkError, HighlightError, OSError) as error:
            self.show_error(f"{self.list_kind} not saved: {error}")
            return
        del self.list_rows[self.list_cursor]
        self.list_cursor = clamp(self.list_cursor, 0, max(0, len(self.list_rows) - 1))
        self.list_scroll = scroll_to_cursor(self.list_cursor, self.list_scroll, self.list_visible_rows())
        if self.list_kind == LIST_MARKS:
            self.message = f"unmarked {self.verse_reference(key)}"
        else:
            self.message = f"removed highlight from {self.verse_reference(key)}"

    def list_visible_rows(self) -> int:
        height, _ = self.stdscr.getmaxyx()
        return max(1, min(len(self.list_rows), height - 6))

    def key_book(self, key: VerseKey) -> Book | None:
        return next((book for book in self.books if book.sort_order == key[0]), None)

    def verse_reference(self, key: VerseKey) -> str:
        book = self.key_book(key)
        name = BOOK_ABBREVIATIONS.get(book.name, book.name) if book else f"Book {key[0]}"
        return f"{name} {key[1]}:{key[2]}"

    def text_for_key(self, key: VerseKey) -> str | None:
        """The verse's text in this version, or None if the version leaves it out."""
        book = self.key_book(key)
        if book is None:
            return None
        verse = next(
            (verse for verse in self.verses_for_reference(book.id, key[1]) if verse.number == key[2]),
            None,
        )
        return verse.text if verse else None

    def jump_to_key(self, key: VerseKey) -> bool:
        book = self.key_book(key)
        if book is None or key[1] not in self.store.chapters(book.id):
            self.message = f"{self.verse_reference(key)} is not in {self.version.name}"
            return False
        self.restore_position(key)
        self.text_cursor_col = 0
        self.focus = FOCUS_TEXT
        self.clamp_text_cursor()
        self.clear_search()
        self.message = f"selected {self.location_label()}"
        self.ensure_visible()
        return True

    def open_highlight_picker(self) -> None:
        if self.focus != FOCUS_TEXT or not self.verses:
            self.message = "select a verse to highlight"
            return
        self.picker_keys = self.target_verse_keys()
        self.exit_visual_mode()
        self.command_modal_open = False
        colors = {self.highlights.color(key) for key in self.picker_keys}
        current = colors.pop() if len(colors) == 1 else None
        color = current if current in HIGHLIGHT_COLORS else self.last_highlight_color
        self.picker_cursor = HIGHLIGHT_COLORS.index(color)
        self.picker_open = True
        self.message = ""

    def close_highlight_picker(self) -> None:
        self.picker_open = False
        self.picker_keys = []

    def handle_picker_key(self, key: int) -> bool:
        if key in (27, ord("c")):
            self.close_highlight_picker()
            return True
        moves = {
            curses.KEY_UP: self.picker_cursor - 1,
            ord("k"): self.picker_cursor - 1,
            curses.KEY_DOWN: self.picker_cursor + 1,
            ord("j"): self.picker_cursor + 1,
            curses.KEY_HOME: 0,
            ord("g"): 0,
            curses.KEY_END: PICKER_CLEAR,
            ord("G"): PICKER_CLEAR,
        }
        if key in moves:
            self.picker_cursor = clamp(moves[key], 0, PICKER_CLEAR)
            return True
        if ord("1") <= key < ord("1") + len(HIGHLIGHT_COLORS):
            self.apply_highlight(HIGHLIGHT_COLORS[key - ord("1")])
            return True
        if key in (ord("0"), ord("x"), ord("d"), curses.KEY_DC):
            self.apply_highlight(None)
            return True
        if key in (ord("\n"), curses.KEY_ENTER, 10, 13):
            row = self.picker_cursor
            self.apply_highlight(None if row == PICKER_CLEAR else HIGHLIGHT_COLORS[row])
            return True
        return True

    def apply_highlight(self, color: str | None) -> None:
        keys = self.picker_keys
        self.close_highlight_picker()
        try:
            self.highlights.apply(keys, color)
        except (HighlightError, OSError) as error:
            self.show_error(f"highlights not saved: {error}")
            return
        target = self.verse_reference(keys[0]) if len(keys) == 1 else f"{len(keys)} verses"
        if color is None:
            self.message = f"cleared highlight from {target}"
        else:
            self.last_highlight_color = color
            self.message = f"highlighted {target} {color}"

    def open_fuzzy_finder(self) -> None:
        self.pending_y = False
        self.exit_visual_mode()
        self.command_modal_open = False
        self.search_input_active = False
        self.fuzzy_verses()
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
        return self.reference_suggestions(self.goto_query)

    def reference_suggestions(self, query: str) -> list[str]:
        """Completions for a reference being typed: book names, then ``Book 3:``, then ``Book 3:16``."""
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
        self.clamp_text_cursor()
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

    def fuzzy_verses(self) -> list[BibleVerse]:
        """Every verse of the focused pane's version, loaded once per version."""
        if self.active_pane == 1 and self.split_pane is not None:
            if self.split_pane.all_verses is None:
                self.split_pane.all_verses = self.split_pane.store.all_verses()
            return self.split_pane.all_verses
        if self.all_verses is None:
            self.all_verses = self.store.all_verses()
        return self.all_verses

    def refresh_fuzzy_matches(self) -> None:
        self.fuzzy_matches = (
            build_fuzzy_matches(self.fuzzy_verses(), self.fuzzy_query)
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
        # By sort order: the verse may come from the second pane's database, whose book ids differ.
        if self.jump_to_key((selected.book_order, selected.chapter_number, selected.verse_number)):
            self.message = f"selected {selected.full_reference}"

    def activate_selection(self) -> None:
        if (
            self.search_scope == FOCUS_BOOKS
            and self.focus == FOCUS_BOOKS
            and self.search_query
            and self.book_is_search_match(self.book_cursor)
        ):
            self.clear_search()
        if self.focus == FOCUS_BOOKS and self.books:
            self.ensure_cursor_book_selected()
            self.focus = FOCUS_CHAPTERS
        elif self.focus == FOCUS_CHAPTERS and self.chapters:
            self.ensure_cursor_chapter_selected()
            self.focus = FOCUS_TEXT
        self.ensure_visible()

    def ensure_cursor_book_selected(self) -> None:
        # Re-selecting the book already shown would reset the chapter and verse.
        if self.selected_book is None or self.selected_book.id != self.books[self.book_cursor].id:
            self.select_book(self.book_cursor)

    def ensure_cursor_chapter_selected(self) -> None:
        if self.selected_chapter != self.chapters[self.chapter_cursor]:
            self.select_chapter(self.chapter_cursor)

    def move_focus_left(self) -> None:
        if self.focus == FOCUS_TEXT and self.active_pane == 1:
            self.focus_pane(0)
            return
        self.focus = max(FOCUS_BOOKS, self.focus - 1)
        self.ensure_visible()

    def move_focus_right(self) -> None:
        if self.focus == FOCUS_TEXT and self.split_pane is not None and self.active_pane == 0:
            self.focus_pane(1)
            return
        if self.focus == FOCUS_CHAPTERS and self.active_pane != 0:
            self.exit_visual_mode()
            self.active_pane = 0  # Coming in from the left lands in the left (or top) pane.
        if self.focus == FOCUS_BOOKS:
            if self.books:
                self.ensure_cursor_book_selected()
            self.focus = FOCUS_CHAPTERS
        elif self.focus == FOCUS_CHAPTERS:
            if self.chapters:
                self.ensure_cursor_chapter_selected()
            self.focus = FOCUS_TEXT
        self.ensure_visible()

    def open_cmdline(self) -> None:
        self.pending_y = False
        self.exit_visual_mode()
        self.cmdline_active = True
        self.cmdline_text = ""
        self.cmdline_cursor = 0
        self.cmdline_chosen = False
        self.cmdline_scroll = 0
        self.message = ""

    def close_cmdline(self) -> None:
        self.cmdline_active = False
        self.cmdline_text = ""
        self.cmdline_cursor = 0
        self.cmdline_scroll = 0

    def handle_cmdline_key(self, key: int) -> bool:
        if key == 27:
            self.close_cmdline()
            return True
        if key in (ord("\n"), curses.KEY_ENTER, 10, 13):
            return self.submit_cmdline()
        completions = self.cmdline_completions()
        if key in (KEY_TAB, curses.KEY_DOWN, KEY_CTRL_N, curses.KEY_UP, KEY_CTRL_P, curses.KEY_BTAB):
            if not completions:
                return True
            if key == KEY_TAB:
                self.accept_completion(completions)
            else:
                step = -1 if key in (curses.KEY_UP, KEY_CTRL_P, curses.KEY_BTAB) else 1
                self.cmdline_cursor = (self.cmdline_cursor + step) % len(completions)
                self.cmdline_chosen = True
                self.cmdline_scroll = scroll_to_cursor(
                    self.cmdline_cursor, self.cmdline_scroll, self.cmdline_visible_rows(len(completions))
                )
            return True
        if key in (curses.KEY_BACKSPACE, 127, 8):
            if not self.cmdline_text:
                self.close_cmdline()  # Vim: backspace on an empty command line leaves it.
                return True
            self.cmdline_text = self.cmdline_text[:-1]
        elif 32 <= key <= 126:
            self.cmdline_text += chr(key)
        else:
            return True
        self.cmdline_cursor = 0
        self.cmdline_chosen = False
        self.cmdline_scroll = 0
        return True

    def accept_completion(self, completions: list[Completion]) -> None:
        self.cmdline_text = completions[clamp(self.cmdline_cursor, 0, len(completions) - 1)].text
        self.cmdline_cursor = 0
        self.cmdline_chosen = False
        self.cmdline_scroll = 0

    def cmdline_visible_rows(self, count: int) -> int:
        height, _ = self.stdscr.getmaxyx()
        return max(1, min(count, 8, height - 6))

    def submit_cmdline(self) -> bool:
        """Run the command line. A completion chosen with the arrows (or ctrl+n/ctrl+p) is taken first.
        Something that isn't a command or reference yet takes the highlighted completion instead, like
        the go-to modal."""
        chosen = self.cmdline_chosen
        if chosen:
            completions = self.cmdline_completions()
            if completions:
                self.accept_completion(completions)
        text = self.cmdline_text.strip()
        if not text:
            self.close_cmdline()
            return True
        command, args = self.parse_ex_command(text)
        if command is not None:
            self.close_cmdline()
            return self.run_ex_command(command, args)
        target = self.parse_cmdline_reference(text)
        if target is not None:
            self.close_cmdline()
            self.jump_to_reference(*target)
            return True
        completions = self.cmdline_completions()
        if chosen or completions:
            if not chosen:
                self.accept_completion(completions)
            return True  # Keep editing: one Enter takes one completion.
        self.close_cmdline()
        self.show_error(f"not a command or reference: {text}")
        return True

    def parse_ex_command(self, text: str) -> tuple[ExCommand | None, str]:
        word, _, args = text.partition(" ")
        folded = word.casefold()
        for command in EX_COMMANDS:
            if folded in command.aliases or (
                len(folded) >= len(command.short) and command.name.startswith(folded)
            ):
                return command, args.strip()
        return None, ""

    def parse_cmdline_reference(self, text: str) -> tuple[Book, int, int] | None:
        """``John 3:16``, or ``John 3`` and ``John`` for the start of a chapter or book."""
        book, chapter, verse = self.parse_goto_reference(text)
        if book is not None:
            return book, chapter, verse
        book, rest = self.goto_book_and_rest(text)
        if book is None:
            return None
        chapters = self.store.chapters(book.id)
        if not rest and chapters:
            chapter = chapters[0]
        elif rest.isdigit() and int(rest) in chapters:
            chapter = int(rest)
        else:
            return None
        verses = self.verses_for_reference(book.id, chapter)
        return (book, chapter, verses[0].number) if verses else None

    def run_ex_command(self, command: ExCommand, args: str) -> bool:
        if command.name == "quit":
            return False
        if command.name == "find":
            self.open_fuzzy_finder()
            if args:
                self.fuzzy_query = args
                self.refresh_fuzzy_matches()
        elif command.name == "set":
            self.run_set(args)
        elif command.name == "vsplit":
            self.open_split_picker(SPLIT_VERTICAL)
        elif command.name == "split":
            self.open_split_picker(SPLIT_HORIZONTAL)
        elif command.name == "close":
            self.close_pane(self.active_pane)
        elif command.name == "only":
            self.handle_window_key(ord("o"))
        elif command.name == "marks":
            self.open_list_modal(LIST_MARKS)
        elif command.name == "highlights":
            self.open_list_modal(LIST_HIGHLIGHTS)
        elif command.name == "update":
            return self.run_update()
        elif command.name == "about":
            self.open_about_modal()
        return True

    def run_set(self, args: str) -> None:
        """``:set version`` opens the picker; ``:set version=ASV`` (or ``version ASV``) switches."""
        option, _, value = args.replace("=", " ", 1).partition(" ")
        if option.casefold() != "version":
            self.show_error(f"unknown option: {option}" if option else "usage: :set version=<name>")
            return
        value = value.strip()
        if not value:
            self.open_version_modal()
            return
        version = find_version(self.versions, value)
        if version is None:
            available = ", ".join(item.abbreviation for item in self.versions)
            self.show_error(f"unknown version {value!r} (available: {available})")
        elif self.active_pane == 1 and self.split_pane is not None:
            self.switch_split_version(version)
        else:
            self.switch_version(version)

    def cmdline_completions(self) -> list[Completion]:
        """Typeahead for the command line: commands, ``:set version=`` values, then references."""
        text = self.cmdline_text
        word, space, rest = text.lstrip().partition(" ")
        folded = word.casefold()
        if space and len(folded) >= 2 and "set".startswith(folded):
            option, equals, prefix = rest.lstrip().replace(" ", "=", 1).partition("=")
            if not equals:
                return [Completion("set version=", "set version=", "change the focused pane's version")] if (
                    "version".startswith(option.casefold())
                ) else []
            if option.casefold() != "version":
                return []
            prefix = prefix.casefold()
            return [
                Completion(f"set version={version.abbreviation}", version.abbreviation, version.name)
                for version in self.versions
                if version.abbreviation.casefold().startswith(prefix) or version.name.casefold().startswith(prefix)
            ]
        completions: list[Completion] = []
        if not space:
            for command in EX_COMMANDS:
                if command.name.startswith(folded):
                    if command.name == "set":
                        insert = "set version="
                    else:
                        insert = command.name + (" " if command.args else "")
                    label = f"{command.name} {command.args}".rstrip()
                    completions.append(Completion(insert, label, command.description))
        elif self.parse_ex_command(text.strip())[0] is not None:
            return []  # Free-form arguments, such as :find's words.
        if text.strip():
            completions.extend(Completion(item, item.strip()) for item in self.reference_suggestions(text))
        return [item for item in completions if item.text != text]

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
        self.search_pane = self.active_pane
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
            self.focus_pane(self.search_pane)
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
            for verse_index, verse in enumerate(self.pane_verses(self.search_pane)):
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

    def search_match_spans(self, verse_index: int, pane: int = 0) -> list[tuple[int, int]]:
        verses = self.pane_verses(pane)
        if (
            self.search_scope != FOCUS_TEXT
            or pane != self.search_pane
            or not self.search_query
            or not (0 <= verse_index < len(verses))
        ):
            return []
        return match_spans(verses[verse_index].text, self.search_query)

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
            self.yank_current_verse()
            self.pending_y = False
            return
        self.pending_y = True
        self.message = "y: press y again to yank verse"

    def verse_key(self, verse_index: int) -> VerseKey | None:
        if self.selected_book is None or self.selected_chapter is None:
            return None
        return (self.selected_book.sort_order, self.selected_chapter, self.verses[verse_index].number)

    def target_verse_keys(self) -> list[VerseKey]:
        """Keys for every verse in the visual selection, or just the current verse."""
        selection = self.visual_selection_bounds()
        indexes = range(selection[0][0], selection[1][0] + 1) if selection else [self.verse_cursor]
        return [key for key in (self.verse_key(index) for index in indexes) if key is not None]

    def highlight_attr(self, color: str | None) -> int:
        if color is None:
            return 0
        if color not in HIGHLIGHT_COLORS:
            return curses.A_UNDERLINE  # A color name from a newer app: show something, keep the data.
        return curses.color_pair(PAIR_HIGHLIGHT_BASE + HIGHLIGHT_COLORS.index(color))

    def toggle_mark(self) -> None:
        """Mark or unmark the current verse, or every verse in the visual selection."""
        if self.focus != FOCUS_TEXT or not self.verses:
            self.message = "select a verse to mark"
            return
        keys = self.target_verse_keys()
        try:
            marked = self.marks.toggle(keys)
        except (MarkError, OSError) as error:
            self.show_error(f"marks not saved: {error}")
            return
        finally:
            self.exit_visual_mode()
        action = "marked" if marked else "unmarked"
        if len(keys) == 1:
            self.message = f"{action} {self.selected_book.name} {self.selected_chapter}:{keys[0][2]}"
        else:
            self.message = f"{action} {len(keys)} verses"

    def enter_visual_mode(self, line: bool = False) -> None:
        self.visual_mode = True
        self.visual_line = line
        self.visual_anchor = (self.verse_cursor, self.text_cursor_col)
        self.message = ""

    def toggle_visual_mode(self, line: bool) -> None:
        """Vim behaviour: the same key leaves visual mode, the other key switches kind."""
        if not self.visual_mode:
            self.enter_visual_mode(line)
        elif self.visual_line == line:
            self.exit_visual_mode()
        else:
            self.visual_line = line

    def exit_visual_mode(self) -> None:
        self.visual_mode = False
        self.visual_line = False
        self.visual_anchor = None

    def yank_current_verse(self) -> None:
        """``yy``: the verse through the ``yank_format`` template (just the text by default)."""
        verse = self.active_verses[self.verse_cursor]
        if isinstance(verse, MissingVerse):
            self.message = f"{self.location_label()} is not in {self.pane_version(self.active_pane).name}"
            return
        self.yank_to_clipboard(self.format_yank(verse), "verse")

    def format_yank(self, verse: Verse) -> str:
        """Fill ``yank_format`` from the focused pane, so its version and book name are used."""
        version = self.pane_version(self.active_pane)
        book = self.selected_book
        if self.active_pane == 1 and self.split_pane is not None:
            book = self.split_pane.books.get(book.sort_order, book)
        reference = f"{book.name} {self.selected_chapter}:{verse.number}"
        return self.yank_format.format(
            text=verse.text,
            reference=reference,
            book=book.name,
            book_abbr=BOOK_ABBREVIATIONS.get(book.name, book.name),
            chapter=self.selected_chapter,
            verse=verse.number,
            version=version.abbreviation,
            version_name=version.name,
        )

    def yank_to_clipboard(self, text: str, label: str) -> None:
        if not copy_to_clipboard(text):
            self.show_error("clipboard unavailable")
            return
        self.set_message(f"yanked {label}", MESSAGE_YANK)

    def move_text_cursor(self, delta: int) -> None:
        if not self.verses:
            return
        max_col = max(0, len(self.active_verses[self.verse_cursor].text) - 1)
        self.text_cursor_col = clamp(self.text_cursor_col + delta, 0, max_col)
        self.ensure_visible()

    def move_to_verse_edge(self, end: bool) -> None:
        if not self.verses:
            return
        self.text_cursor_col = max(0, len(self.active_verses[self.verse_cursor].text) - 1) if end else 0
        self.ensure_visible()

    def move_word(self, motion: str) -> None:
        """Vim ``w``/``b``/``e``: move by word, continuing into the next or previous verse."""
        verses = self.active_verses
        if not verses:
            return
        col = self.text_cursor_col
        spans = word_spans(verses[self.verse_cursor].text)
        target: tuple[int, int] | None = None
        if motion == "w":
            target = next(((self.verse_cursor, start) for start, _ in spans if start > col), None)
            if target is None and self.verse_cursor + 1 < len(verses):
                next_spans = word_spans(verses[self.verse_cursor + 1].text)
                target = (self.verse_cursor + 1, next_spans[0][0] if next_spans else 0)
        elif motion == "b":
            target = next(((self.verse_cursor, start) for start, _ in reversed(spans) if start < col), None)
            if target is None and self.verse_cursor > 0:
                previous_spans = word_spans(verses[self.verse_cursor - 1].text)
                target = (self.verse_cursor - 1, previous_spans[-1][0] if previous_spans else 0)
        elif motion == "e":
            target = next(((self.verse_cursor, end - 1) for _, end in spans if end - 1 > col), None)
            if target is None and self.verse_cursor + 1 < len(verses):
                next_spans = word_spans(verses[self.verse_cursor + 1].text)
                target = (self.verse_cursor + 1, next_spans[0][1] - 1 if next_spans else 0)
        if target is None:
            return
        self.verse_cursor, self.text_cursor_col = target
        self.ensure_visible()

    def step_chapter(self, delta: int) -> None:
        """Turn the page: the next or previous chapter, crossing into the adjacent book in Bible order."""
        if self.selected_book is None or self.selected_chapter is None:
            return
        index = self.chapters.index(self.selected_chapter) + delta
        if 0 <= index < len(self.chapters):
            self.chapter_cursor = index
            self.select_chapter(index)
        else:
            canonical = self.store.books(False)
            position = next(i for i, book in enumerate(canonical) if book.id == self.selected_book.id)
            target = position + (1 if delta > 0 else -1)
            if not 0 <= target < len(canonical):
                self.message = "last chapter" if delta > 0 else "first chapter"
                return
            self.book_cursor = next(i for i, book in enumerate(self.books) if book.id == canonical[target].id)
            self.select_book(self.book_cursor)
            if delta < 0 and self.chapters:
                self.chapter_cursor = len(self.chapters) - 1
                self.select_chapter(self.chapter_cursor)
        self.message = f"{self.selected_book.name} {self.selected_chapter}"
        self.ensure_visible()

    def cycle_focus(self, delta: int) -> None:
        if delta > 0 and self.focus == FOCUS_TEXT:
            if self.split_pane is not None and self.active_pane == 0:
                self.focus_pane(1)
            else:
                self.focus = FOCUS_BOOKS
        elif delta < 0 and self.focus == FOCUS_BOOKS:
            if self.verses:
                self.focus_pane(1)
        elif delta > 0:
            self.move_focus_right()
        else:
            self.move_focus_left()
        self.ensure_visible()

    def move_verse_cursor(self, delta: int) -> None:
        if not self.verses:
            return
        self.verse_cursor = clamp(self.verse_cursor + delta, 0, len(self.verses) - 1)
        max_col = max(0, len(self.active_verses[self.verse_cursor].text) - 1)
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

    def page(self, direction: int, half: bool = False) -> None:
        _, _, content_h, _, _, _ = self.layout()
        if self.focus == FOCUS_TEXT:
            content_h = min(h for _, _, _, h, _ in self.text_pane_rects())
        page_size = max(1, (content_h - 2) // 2) if half else max(1, content_h - 4)
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
            self.selected_chapter = None
            self.load_chapter_verses()
            self.exit_visual_mode()

    def select_chapter(self, index: int) -> None:
        if self.selected_book is None or not self.chapters:
            return
        self.selected_chapter = self.chapters[index]
        self.load_chapter_verses()
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
        rects = self.text_pane_rects()
        inner_h = max(1, min(h for _, _, _, h, _ in rects) - 2)
        wrapped = next(iter(self.text_lines(rects).values()))  # Split panes share rows.
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

        top_y, content_y, content_h, book_w, chapter_w, _ = self.layout()
        self.draw_top_bar(top_y, width)
        self.draw_books(content_y, 0, content_h, book_w)
        self.draw_chapters(content_y, book_w, content_h, chapter_w)
        rects = self.text_pane_rects()
        lines = self.text_lines(rects)
        for pane, pane_y, pane_x, pane_h, pane_w in rects:
            self.draw_text(pane, pane_y, pane_x, pane_h, pane_w, lines[pane], hidden_pane=len(rects) < self.pane_count)
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
        if self.list_kind is not None:
            self.draw_list_modal(height, width)
        if self.picker_open:
            self.draw_highlight_picker(height, width)
        if self.about_open:
            self.draw_about_modal(height, width)
        if self.cmdline_active:
            self.draw_cmdline(height, width)
        if self.cmdline_active:
            self.set_cursor_visibility(True)
            self.stdscr.move(height - 1, min(1 + len(self.cmdline_text), max(0, width - 2)))
        elif self.search_input_active:
            self.position_search_cursor(height - 1, width)
        elif self.goto_open:
            self.position_goto_cursor(height, width)
        elif self.fuzzy_open:
            if self.fuzzy_help_open:
                self.set_cursor_visibility(False)
            else:
                self.position_fuzzy_cursor(height, width)
        else:
            self.position_terminal_cursor(rects, lines)
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

    @property
    def pane_count(self) -> int:
        return 1 if self.split_pane is None else 2

    def text_pane_rects(self) -> list[tuple[int, int, int, int, int]]:
        """(pane, y, x, height, width) for each text pane drawn. A split that no longer fits the
        terminal shows only the focused pane until there is room again."""
        _, content_y, content_h, book_w, chapter_w, text_w = self.layout()
        x = book_w + chapter_w
        if self.split_pane is None:
            return [(0, content_y, x, content_h, text_w)]
        if self.split == SPLIT_VERTICAL and text_w >= 2 * MIN_PANE_WIDTH:
            left_w = text_w // 2
            return [(0, content_y, x, content_h, left_w), (1, content_y, x + left_w, content_h, text_w - left_w)]
        if self.split == SPLIT_HORIZONTAL and content_h >= 2 * MIN_PANE_HEIGHT:
            top_h = content_h // 2
            return [(0, content_y, x, top_h, text_w), (1, content_y + top_h, x, content_h - top_h, text_w)]
        return [(self.active_pane, content_y, x, content_h, text_w)]

    def draw_top_bar(self, y: int, width: int) -> None:
        order = "A-Z" if self.alphabetical else "Bible order"
        # Split panes name their versions in their own titles.
        version = "" if self.split_pane is not None else f"{self.version.name} | "
        title = f" Bible TUI | {version}{order} "
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
        self.draw_scrollbar(win, len(self.book_rows), self.book_scroll, inner_h, focused=self.focus == FOCUS_BOOKS)

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
        self.draw_scrollbar(win, len(self.chapters), self.chapter_scroll, inner_h, focused=self.focus == FOCUS_CHAPTERS)

    def draw_text(
        self,
        pane: int,
        y: int,
        x: int,
        h: int,
        w: int,
        lines: list[RenderLine],
        *,
        hidden_pane: bool = False,
    ) -> None:
        win = self.stdscr.derwin(h, w, y, x)
        chapter = "Text"
        if self.selected_book and self.selected_chapter:
            chapter = f"{self.selected_book.name} {self.selected_chapter}"
        title = chapter
        if self.split_pane is not None:
            title = f"{self.pane_version(pane).name} | {chapter}"
            if hidden_pane:
                title = f"{title} | other pane hidden: terminal too small"
        focused = self.focus == FOCUS_TEXT and pane == self.active_pane
        self.draw_box(win, title, focused)
        inner_h = max(0, h - 2)
        inner_w = max(0, w - 2)
        verses = self.pane_verses(pane)
        if verses and all(isinstance(verse, MissingVerse) for verse in verses):
            note = f"{chapter} is not in {self.pane_version(pane).name}"
            win.addnstr(1, 2, note, max(0, inner_w - 2), curses.color_pair(4) | curses.A_DIM)
            return
        for row, line in enumerate(lines[self.text_scroll : self.text_scroll + inner_h]):
            selected = self.verses and line.verse_index == self.verse_cursor
            if selected:
                base_attr = curses.color_pair(6)
            else:
                base_attr = 0
            win.addnstr(row + 1, 1, " " * inner_w, inner_w, base_attr)
            if line.missing:
                shade_attr = base_attr | curses.A_DIM if selected else curses.color_pair(4) | curses.A_DIM
                if line.verse_number:
                    win.addnstr(row + 1, 1 + SIGN_WIDTH, line.verse_number, NUMBER_WIDTH, shade_attr)
                shade_w = max(0, inner_w - GUTTER_WIDTH - 1)
                shade = MISSING_SHADE * shade_w
                icon = self.glyphs["missing"]
                if icon and line.verse_number:
                    note = f"{icon} not in {self.pane_version(pane).name} "
                    shade = (note + shade[len(note) :])[:shade_w]
                win.addnstr(row + 1, 1 + GUTTER_WIDTH, shade, shade_w, shade_attr)
                continue
            if line.verse_number:
                key = self.verse_key(line.verse_index)
                if key is not None and self.marks.is_marked(key):
                    sign_attr = curses.color_pair(PAIR_SIGN_SELECTED if selected else PAIR_SIGN) | curses.A_BOLD
                    win.addnstr(row + 1, 1, self.mark_sign, 1, sign_attr)
                number_attr = base_attr | curses.A_BOLD if selected else curses.color_pair(3) | curses.A_BOLD
                win.addnstr(row + 1, 1 + SIGN_WIDTH, line.verse_number, NUMBER_WIDTH, number_attr)
            self.draw_text_segment(
                win, row + 1, 1 + GUTTER_WIDTH, line, max(0, inner_w - GUTTER_WIDTH), base_attr, pane
            )
        self.draw_scrollbar(win, len(lines), self.text_scroll, inner_h, focused=focused)

    def draw_status(self, y: int, width: int) -> None:
        if self.search_scope is not None:
            self.draw_search_line(y, width)
            return
        version = self.pane_version(self.active_pane).name
        location = self.location_label()
        focus = ("books", "chapters", "text")[self.focus]
        if self.focus == FOCUS_TEXT and self.split_pane is not None:
            sides = ("left", "right") if self.split == SPLIT_VERTICAL else ("top", "bottom")
            focus = f"text ({sides[self.active_pane]})"
        # Vim-style: the mode on the left, the place on the right before the ctrl+p hint, and
        # messages just left of the place, so the left side stays free for the mode.
        self.add_screen_line(y, "", width, curses.color_pair(4) | curses.A_DIM)
        usable = max(0, width - 1)
        hint_x = usable - len("ctrl+p commands")
        mode = ""
        if self.visual_mode:
            mode = " -- VISUAL LINE --" if self.visual_line else " -- VISUAL --"
            self.stdscr.addnstr(y, 0, mode, max(0, hint_x - 1), curses.color_pair(7) | curses.A_BOLD)
        left = len(mode) + 1
        info = f"{version} | {location} | {focus}"
        room = hint_x - 2 - left
        if len(info) > room:
            info = "..." + info[-(room - 3) :] if room > 3 else ""
        info_x = hint_x - 2 - len(info)
        if info:
            self.stdscr.addnstr(y, info_x, info, len(info), curses.color_pair(4) | curses.A_DIM)
        if self.message:
            icon = self.glyphs.get(self.message_kind, "")
            message = f"{icon} {self.message}" if icon else self.message
            room = info_x - 3 - left
            if len(message) > room:
                message = message[: room - 3] + "..." if room > 3 else ""
            if message:
                # Yellow, or red for a failure, so it stands out from the gray status.
                if self.message_kind == MESSAGE_ERROR:
                    attr = curses.color_pair(PAIR_ERROR) | curses.A_BOLD
                else:
                    attr = curses.color_pair(3)
                self.stdscr.addnstr(y, info_x - 3 - len(message), message, len(message), attr)
        if hint_x > 0:
            self.draw_command_hint(y, width)

    def draw_cmdline(self, height: int, width: int) -> None:
        """The ``:`` line in the footer, with completions in a menu above it."""
        y = height - 1
        usable = max(0, width - 1)
        self.add_screen_line(y, "", width, 0)
        self.stdscr.addnstr(y, 0, f":{self.cmdline_text}", usable, curses.color_pair(2))
        hints = "tab complete  enter run  esc cancel"
        if usable - len(hints) > len(self.cmdline_text) + 4:
            self.stdscr.addnstr(y, usable - len(hints), hints, len(hints), curses.color_pair(4) | curses.A_DIM)
        completions = self.cmdline_completions()
        if not completions:
            return
        rows = self.cmdline_visible_rows(len(completions))
        label_w = max(len(item.label) for item in completions)
        desc_w = max(len(item.description) for item in completions)
        menu_w = min(max(20, label_w + desc_w + (6 if desc_w else 4)), max(20, width - 2))
        menu_h = rows + 2
        menu_y = max(1, y - menu_h)
        win = self.stdscr.derwin(menu_h, menu_w, menu_y, 0)
        win.erase()
        border_attr = curses.color_pair(5) | curses.A_BOLD
        win.attron(border_attr)
        win.box()
        win.attroff(border_attr)
        inner_w = menu_w - 2
        cursor = clamp(self.cmdline_cursor, 0, len(completions) - 1)
        for row, item in enumerate(completions[self.cmdline_scroll : self.cmdline_scroll + rows]):
            selected = self.cmdline_scroll + row == cursor
            row_attr = curses.color_pair(1) if selected else 0
            win.addnstr(row + 1, 1, " " * inner_w, inner_w, row_attr)
            win.addnstr(row + 1, 2, item.label, max(0, inner_w - 2), row_attr if selected else curses.color_pair(2))
            desc_x = 2 + label_w + 2
            if item.description and desc_x < inner_w:
                desc_attr = row_attr if selected else curses.color_pair(4) | curses.A_DIM
                win.addnstr(row + 1, desc_x, item.description, inner_w - desc_x, desc_attr)
        self.draw_scrollbar(win, len(completions), self.cmdline_scroll, rows, focused=True)

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
        prefix = self.glyphs["search"]
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
        return max(len(self.glyphs["search"]) + 3, usable_width - hint_width)

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
        columns = 2 if self.version_mode == PICK_PANES else 1
        visible_rows = self.version_visible_rows()
        content_w = max(len(version.name) for version in self.versions)
        column_w = content_w + 6
        modal_w = min(max(40, column_w * columns + columns + 1), max(20, width - 4))
        modal_h = visible_rows + 2 + (2 if columns == 2 else 0)
        y = max(1, (height - modal_h) // 2)
        x = max(0, (width - modal_w) // 2)
        win = self.stdscr.derwin(modal_h, modal_w, y, x)
        win.erase()
        border_attr = curses.color_pair(5) | curses.A_BOLD
        win.attron(border_attr)
        win.box()
        win.attroff(border_attr)

        title = " Version for new pane " if self.version_mode == PICK_NEW_PANE else " Versions "
        win.addnstr(0, 2, title, max(0, modal_w - 4), curses.color_pair(2) | curses.A_BOLD)
        esc = " esc "
        if modal_w > len(title) + len(esc) + 6:
            win.addnstr(0, modal_w - len(esc) - 2, esc, len(esc), curses.color_pair(4))

        if columns == 1:
            current = self.version if self.version_mode == PICK_VERSION else None
            self.draw_version_column(win, 0, 1, 1, modal_w - 2, visible_rows, current, active=True)
            self.draw_scrollbar(win, len(self.versions), self.version_scrolls[0], visible_rows, focused=True)
            return

        inner_w = modal_w - 2
        left_w = (inner_w - 1) // 2
        divider_x = 1 + left_w
        sides = ("Left", "Right") if self.split == SPLIT_VERTICAL else ("Top", "Bottom")
        current_versions = (self.version, self.pane_version(1))
        for column, (col_x, col_w) in enumerate(((1, left_w), (divider_x + 1, inner_w - left_w - 1))):
            active = column == self.version_column
            heading_attr = curses.color_pair(5) | curses.A_BOLD if active else curses.color_pair(4) | curses.A_DIM
            win.addnstr(1, col_x + 1, f"{sides[column]} pane", max(0, col_w - 2), heading_attr)
            self.draw_version_column(
                win, column, 2, col_x, col_w, visible_rows, current_versions[column], active=active
            )
        for row in range(1, modal_h - 2):
            win.addch(row, divider_x, curses.ACS_VLINE, curses.color_pair(4) | curses.A_DIM)
        self.draw_modal_hints(
            win, modal_h - 2, modal_w, (("left/right", "pane"), ("enter", "apply"), ("esc", "cancel"))
        )

    def draw_version_column(
        self,
        win: curses.window,
        column: int,
        top: int,
        x: int,
        w: int,
        visible_rows: int,
        current: BibleVersion | None,
        *,
        active: bool,
    ) -> None:
        """One list of versions. ``*`` marks the version the pane shows now. The other column's
        choice stays visible, without the cursor color."""
        scroll = self.version_scrolls[column]
        for row, version in enumerate(self.versions[scroll : scroll + visible_rows]):
            selected = scroll + row == self.version_cursors[column]
            if selected:
                row_attr = curses.color_pair(1) if active else curses.A_REVERSE
            else:
                row_attr = 0
            marker_attr = row_attr if selected else curses.color_pair(3) | curses.A_BOLD
            name_attr = row_attr if selected else curses.color_pair(2)
            marker = self.glyphs["current"] if version == current else " "
            win.addnstr(top + row, x, " " * w, w, row_attr)
            win.addnstr(top + row, x + 1, marker, 1, marker_attr)
            win.addnstr(top + row, x + 3, version.name, max(0, w - 4), name_attr)

    def draw_list_modal(self, height: int, width: int) -> None:
        marks = self.list_kind == LIST_MARKS
        visible_rows = self.list_visible_rows()
        modal_w = min(max(60, int(width * 0.7)), max(20, width - 4))
        modal_h = visible_rows + 3
        y = max(1, (height - modal_h) // 2)
        x = max(0, (width - modal_w) // 2)
        win = self.stdscr.derwin(modal_h, modal_w, y, x)
        win.erase()
        border_attr = curses.color_pair(5) | curses.A_BOLD
        win.attron(border_attr)
        win.box()
        win.attroff(border_attr)

        count = len(self.list_rows)
        label = "Marks" if marks else "Highlights"
        title = f" {label} ({count}) " if count else f" {label} "
        win.addnstr(0, 2, title, max(0, modal_w - 4), curses.color_pair(2) | curses.A_BOLD)
        esc = " esc "
        if modal_w > len(title) + len(esc) + 6:
            win.addnstr(0, modal_w - len(esc) - 2, esc, len(esc), curses.color_pair(4))

        inner_w = max(0, modal_w - 2)
        if not self.list_rows:
            store = self.marks if marks else self.highlights
            if store.load_error:
                empty = f"{self.list_kind}.json could not be read: {store.load_error}"
            elif marks:
                empty = "No marks yet. Press m on a verse to mark it."
            else:
                empty = "No highlights yet. Press c on a verse to highlight it."
            win.addnstr(1, 2, empty, max(0, modal_w - 4), curses.color_pair(4) | curses.A_DIM)
        else:
            swatch_w = 0 if marks else 3  # Two colored cells and a space.
            date_w = len("2026-01-01 00:00")
            visible = self.list_rows[self.list_scroll : self.list_scroll + visible_rows]
            references = [self.verse_reference(item.key) for item in visible]
            ref_w = max(len(reference) for reference in references)
            date_x = 2 + swatch_w
            ref_x = date_x + date_w + 2
            text_x = ref_x + ref_w + 2
            text_w = max(0, modal_w - text_x - 2)
            for row, (item, reference) in enumerate(zip(visible, references)):
                selected = self.list_scroll + row == self.list_cursor
                row_attr = curses.color_pair(1) if selected else 0
                date_attr = row_attr if selected else curses.color_pair(4) | curses.A_DIM
                ref_attr = row_attr if selected else curses.color_pair(3) | curses.A_BOLD
                text = self.text_for_key(item.key)
                text_attr = row_attr if selected else curses.color_pair(2)
                if text is None:
                    text = f"(not in {self.version.name})"
                    text_attr = row_attr if selected else curses.color_pair(4) | curses.A_DIM
                if len(text) > text_w:
                    text = text[: max(0, text_w - 3)].rstrip() + "..."
                win.addnstr(row + 1, 1, " " * inner_w, inner_w, row_attr)
                if swatch_w:
                    win.addnstr(row + 1, 2, "  ", 2, self.highlight_attr(item.color))
                win.addnstr(row + 1, date_x, format_mark_time(item.created_at), date_w, date_attr)
                win.addnstr(row + 1, ref_x, reference, ref_w, ref_attr)
                if text_w > 0:
                    win.addnstr(row + 1, text_x, text, text_w, text_attr)
            self.draw_scrollbar(win, count, self.list_scroll, visible_rows, track_h=visible_rows, focused=True)

        hints = (("d", "delete"), ("enter", "go"), ("esc", "close")) if self.list_rows else (("esc", "close"),)
        hint = "  ".join(f"{key} {label}" for key, label in hints)
        if self.list_rows and self.message:
            # Status from the last action in the modal (a delete), on the left of the hints.
            note_w = max(0, modal_w - len(hint) - 7)
            win.addnstr(modal_h - 2, 2, self.message, note_w, curses.color_pair(4) | curses.A_DIM)
        self.draw_modal_hints(win, modal_h - 2, modal_w, hints)

    def draw_highlight_picker(self, height: int, width: int) -> None:
        rows = len(HIGHLIGHT_COLORS) + 1
        modal_w = min(36, max(20, width - 4))
        modal_h = rows + 3
        y = max(1, (height - modal_h) // 2)
        x = max(0, (width - modal_w) // 2)
        win = self.stdscr.derwin(modal_h, modal_w, y, x)
        win.erase()
        border_attr = curses.color_pair(5) | curses.A_BOLD
        win.attron(border_attr)
        win.box()
        win.attroff(border_attr)

        count = len(self.picker_keys)
        title = " Highlight " if count == 1 else f" Highlight {count} verses "
        win.addnstr(0, 2, title, max(0, modal_w - 4), curses.color_pair(2) | curses.A_BOLD)
        inner_w = max(0, modal_w - 2)
        current = {self.highlights.color(key) for key in self.picker_keys}
        for row in range(rows):
            selected = row == self.picker_cursor
            row_attr = curses.color_pair(1) if selected else 0
            name_attr = row_attr if selected else curses.color_pair(2)
            key_attr = row_attr if selected else curses.color_pair(4) | curses.A_DIM
            win.addnstr(row + 1, 1, " " * inner_w, inner_w, row_attr)
            if row == PICKER_CLEAR:
                win.addnstr(row + 1, 3, " x ", 3, row_attr if selected else curses.color_pair(4) | curses.A_DIM)
                name, number = "Clear", "0"
            else:
                color = HIGHLIGHT_COLORS[row]
                win.addnstr(row + 1, 3, "   ", 3, self.highlight_attr(color))
                name = color.capitalize() + ("  (current)" if current == {color} else "")
                number = str(row + 1)
            win.addnstr(row + 1, 8, name, max(0, modal_w - 13), name_attr)
            win.addnstr(row + 1, modal_w - 4, number, 1, key_attr)
        self.draw_modal_hints(win, modal_h - 2, modal_w, (("enter", "apply"), ("esc", "cancel")))

    def about_rows(self) -> list[tuple[str, str]]:
        """The About modal's ``(label, value)`` rows."""
        check = self.update_check
        if check is None:
            latest = "update checks are off"
        elif check.pending:
            latest = "checking..."
        elif check.update_available:
            latest = f"{check.latest} is out (u to update)"
        elif check.latest is not None:
            latest = "up to date"
        else:
            latest = "couldn't check (offline?)"
        return [
            ("Version", __version__),
            ("Latest", latest),
            ("Reading", self.version.name),
            ("Python", platform.python_version()),
            ("Project", REPOSITORY_URL),
        ]

    def about_hints(self) -> tuple[tuple[str, str], ...]:
        hints = (("o", "open link"), ("y", "copy link"), ("esc", "close"))
        if self.update_check is not None and self.update_check.update_available:
            hints = (("u", "update"), *hints)
        return hints

    def draw_about_modal(self, height: int, width: int) -> None:
        rows = self.about_rows()
        label_w = max(len(label) for label, _ in rows)
        tagline = "A dependency-free terminal Bible reader"
        hints = self.about_hints()
        hint_w = sum(len(key) + len(label) + 3 for key, label in hints)
        content_w = max(len(tagline), label_w + 2 + max(len(value) for _, value in rows), hint_w)
        modal_w = min(content_w + 6, max(20, width - 4))
        modal_h = len(rows) + 6
        y = max(1, (height - modal_h) // 2)
        x = max(0, (width - modal_w) // 2)
        win = self.stdscr.derwin(modal_h, modal_w, y, x)
        win.erase()
        border_attr = curses.color_pair(5) | curses.A_BOLD
        win.attron(border_attr)
        win.box()
        win.attroff(border_attr)
        win.addnstr(0, 2, " About ", max(0, modal_w - 4), curses.color_pair(2) | curses.A_BOLD)
        inner = max(0, modal_w - 6)
        win.addnstr(1, 3, "bible-tui", inner, curses.color_pair(PAIR_HEADING) | curses.A_BOLD)
        win.addnstr(2, 3, tagline, inner, curses.color_pair(4) | curses.A_DIM)
        value_x = 3 + label_w + 2
        for row, (label, value) in enumerate(rows):
            win.addnstr(row + 4, 3, label, inner, curses.color_pair(4) | curses.A_DIM)
            attr = curses.color_pair(3) if label == "Latest" and "u to update" in value else curses.color_pair(2)
            win.addnstr(row + 4, value_x, value, max(0, modal_w - value_x - 2), attr)
        self.draw_modal_hints(win, modal_h - 2, modal_w, hints)

    def open_about_modal(self) -> None:
        self.pending_y = False
        self.command_modal_open = False
        self.about_open = True

    def handle_about_key(self, key: int) -> bool:
        if key in (27, ord("q"), ord("\n"), curses.KEY_ENTER, 10, 13):
            self.about_open = False
        elif key == ord("o"):
            if not open_url(REPOSITORY_URL):
                self.show_error("couldn't open a browser; the link is in the About box")
        elif key == ord("y"):
            self.yank_to_clipboard(REPOSITORY_URL, "project link")
        elif key == ord("u") and self.update_check is not None and self.update_check.update_available:
            self.about_open = False
            return self.run_update()
        return True

    def draw_modal_hints(self, win: curses.window, y: int, modal_w: int, hints: tuple[tuple[str, str], ...]) -> None:
        hint = "  ".join(f"{key} {label}" for key, label in hints)
        hint_x = max(1, modal_w - len(hint) - 2)
        for key, label in hints:
            win.addnstr(y, hint_x, key, len(key), curses.color_pair(2))
            hint_x += len(key) + 1
            win.addnstr(y, hint_x, label, len(label), curses.color_pair(4) | curses.A_DIM)
            hint_x += len(label) + 2

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

    def fuzzy_prompt(self) -> str:
        return f" {self.glyphs['find']} "

    def draw_fuzzy_header(self, win: curses.window) -> None:
        _, max_x = win.getmaxyx()
        if max_x <= 4:
            return

        prompt = self.fuzzy_prompt()
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
        icon = self.glyphs["goto"]
        self.draw_box(win, f" {icon} Go To Reference " if icon else " Go To Reference ", True)

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
            len(self.fuzzy_prompt()) + len(self.fuzzy_query),
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
        if COMMAND_ROWS[row - 1][0] == "heading":
            # Show the group's heading with its first command.
            self.command_scroll = scroll_to_cursor(row - 1, self.command_scroll, visible_rows)
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
        focused: bool = False,
    ) -> None:
        """Draw over the window's right border. ``focused`` matches a focused (green) border."""
        if total <= visible or visible <= 0:
            return
        attr = curses.color_pair(5) | curses.A_BOLD if focused else curses.color_pair(2)
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
                win.addch(y, col, ch, attr)
            except (curses.error, UnicodeEncodeError):
                if thumb_top <= y < thumb_top + thumb_h:
                    win.addch(y, col, curses.ACS_CKBOARD, attr)

    def text_lines(self, rects: list[tuple[int, int, int, int, int]]) -> dict[int, list[RenderLine]]:
        """Wrapped lines for each drawn pane. Split panes pad each verse to the taller side, so a verse
        starts on the same row in both and they scroll together."""
        widths = {pane: max(1, w - 2) for pane, _, _, _, w in rects}
        result: dict[int, list[RenderLine]] = {pane: [] for pane in widths}
        for verse_index in range(len(self.verses)):
            blocks = {
                pane: wrap_verse(verse_index, self.pane_verses(pane)[verse_index], max(8, width - GUTTER_WIDTH))
                for pane, width in widths.items()
            }
            rows = max(len(block) for block in blocks.values())
            for pane, block in blocks.items():
                verse = self.pane_verses(pane)[verse_index]
                filler = RenderLine(verse_index, "", "", len(verse.text), missing=block[0].missing)
                result[pane].extend(block + [filler] * (rows - len(block)))
        return result

    def draw_text_segment(
        self,
        win: curses.window,
        y: int,
        x: int,
        line: RenderLine,
        width: int,
        base_attr: int,
        pane: int = 0,
    ) -> None:
        if not line.text or width <= 0:
            return
        selection = self.visual_selection_bounds() if pane == self.active_pane else None
        search_spans = self.search_match_spans(line.verse_index, pane)
        key = self.verse_key(line.verse_index)
        highlight = self.highlight_attr(self.highlights.color(key) if key is not None else None)
        if highlight and base_attr:
            highlight |= curses.A_BOLD  # The current verse: keep its color, bold to stand out.
        for offset, char in enumerate(line.text[:width]):
            absolute_col = line.start_col + offset
            attr = highlight or base_attr
            if selection and self.char_is_selected(line.verse_index, absolute_col, selection):
                attr = attr | curses.A_REVERSE
            if self.col_is_in_spans(absolute_col, search_spans):
                attr = curses.color_pair(PAIR_SEARCH) | curses.A_BOLD
            win.addnstr(y, x + offset, char, 1, attr)

    def position_terminal_cursor(
        self,
        rects: list[tuple[int, int, int, int, int]],
        lines: dict[int, list[RenderLine]],
    ) -> None:
        rect = next((rect for rect in rects if rect[0] == self.active_pane), None)
        if (
            self.command_modal_open
            or self.version_modal_open
            or self.list_kind is not None
            or self.picker_open
            or self.search_input_active
            or self.focus != FOCUS_TEXT
            or not self.verses
            or rect is None
        ):
            self.set_cursor_visibility(False)
            return
        _, pane_y, pane_x, pane_h, _ = rect
        inner_h = max(0, pane_h - 2)
        for row, line in enumerate(lines[self.active_pane][self.text_scroll : self.text_scroll + inner_h]):
            if line.missing or (not line.text and not line.verse_number and line.start_col > 0):
                continue  # Shading and padding rows hold no text.
            line_end = line.start_col + len(line.text)
            if line.verse_index == self.verse_cursor and line.start_col <= self.text_cursor_col <= max(line.start_col, line_end):
                self.set_cursor_visibility(True)
                col = min(max(0, self.text_cursor_col - line.start_col), max(0, len(line.text) - 1))
                self.stdscr.move(pane_y + row + 1, pane_x + 1 + GUTTER_WIDTH + col)
                return
        self.set_cursor_visibility(False)

    def position_search_cursor(self, y: int, width: int) -> None:
        usable_width = max(0, width - 1)
        if usable_width <= 0:
            self.set_cursor_visibility(False)
            return
        self.set_cursor_visibility(True)
        self.stdscr.move(y, min(len(self.glyphs["search"]) + 2 + len(self.search_query), usable_width - 1))

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
        if self.visual_line:
            last_col = max(0, len(self.active_verses[end[0]].text) - 1)
            return (start[0], 0), (end[0], last_col)
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
        verses = self.active_verses
        for verse_index in range(start[0], end[0] + 1):
            if isinstance(verses[verse_index], MissingVerse):
                continue
            text = verses[verse_index].text
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


URL_OPENERS: tuple[str, ...] = ("open", "xdg-open", "wslview")  # macOS, Linux, WSL


def open_url(url: str) -> bool:
    """Open ``url`` in the default browser without waiting for it."""
    for opener in URL_OPENERS:
        path = shutil.which(opener)
        if path is None:
            continue
        try:
            subprocess.Popen(
                [path, url],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            continue
        return True
    return False


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


def format_mark_time(created_at: str) -> str:
    """A mark's UTC ``created_at`` as local ``YYYY-MM-DD HH:MM``; blank if missing or unreadable."""
    try:
        return datetime.fromisoformat(created_at).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return ""


def wrap_verse(verse_index: int, verse: Verse, text_width: int) -> list[RenderLine]:
    """A verse's wrapped lines; ``start_col`` maps each line back into the verse text."""
    number = f"{verse.number:>3} "
    if isinstance(verse, MissingVerse):
        return [RenderLine(verse_index, number, "", 0, missing=True)]
    wrapped = textwrap.wrap(
        verse.text,
        width=text_width,
        replace_whitespace=True,
        drop_whitespace=True,
    ) or [""]
    start_col = 0
    lines = [RenderLine(verse_index, number, wrapped[0], start_col)]
    start_col += len(wrapped[0])
    for continuation in wrapped[1:]:
        if start_col < len(verse.text) and verse.text[start_col : start_col + 1] == " ":
            start_col += 1
        lines.append(RenderLine(verse_index, "", continuation, start_col))
        start_col += len(continuation)
    return lines


def align_verses(primary: list[Verse], secondary: list[Verse]) -> tuple[list[Verse], list[Verse]]:
    """Give two versions of a chapter the same rows: every verse number either has, with a
    ``MissingVerse`` where one leaves it out."""
    first = {verse.number: verse for verse in primary}
    second = {verse.number: verse for verse in secondary}
    numbers = sorted(first.keys() | second.keys())
    return (
        [first.get(number) or MissingVerse(number) for number in numbers],
        [second.get(number) or MissingVerse(number) for number in numbers],
    )


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def scroll_to_cursor(cursor: int, scroll: int, visible: int) -> int:
    if cursor < scroll:
        return cursor
    if cursor >= scroll + visible:
        return cursor - visible + 1
    return scroll


def word_spans(text: str) -> list[tuple[int, int]]:
    """Vim-style words: runs of letters/digits, or runs of other non-space characters."""
    return [match.span() for match in re.finditer(r"\w+|[^\w\s]+", text)]


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
