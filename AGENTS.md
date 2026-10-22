# AGENTS.md

## Repo Purpose

`bible-tui` is a dependency-free Python curses Bible reader. It doesn't depend on any one version: each version is
one SQLite database, discovered from a list of folders. The KJV and ASV are bundled.

## Repository Map

- `bible-tui` is a bash wrapper that runs `python3 -m bible_tui` with the repo on `PYTHONPATH`.
  `pyproject.toml` also installs a `bible-tui` console script (`bible_tui.cli:main`) for `pipx install .`.
- `bible_tui/cli.py` handles argument parsing, path/settings resolution, `--paths`, and `--list-versions`.
  `choose_version` picks the launch version, and `run_tui` starts curses. `main(argv, env)` returns an exit code
  so tests can call it directly. User-facing failures raise `CliError` or `ConfigError` and exit 1.
- `bible_tui/paths.py` resolves the app home (`$BIBLE_TUI_HOME`, else `~/.bible-tui` if it exists, else
  `$XDG_CONFIG_HOME/bible-tui`). Functions take an `env` mapping so tests never touch the real home.
- `bible_tui/config.py` holds `Settings`/`load_settings` for the user-written `config.json` and
  `load_state`/`save_state` for the app-written `state.json`. It also has `write_json`, an atomic writer meant
  for future bookmarks/highlights/notes files.
- `bible_tui/versions.py` holds `BibleVersion`, `inspect_database` (schema check plus metadata), and
  `discover_versions` (priority-ordered folders; an earlier folder wins when abbreviations collide). It also has
  `connect_read_only`.
- `bible_tui/store.py` holds `BibleStore` (read-only queries for one version), the `Book`/`Verse`/`BibleVerse`
  models, and `BOOK_ABBREVIATIONS`.
- `bible_tui/tui.py` is the curses UI (`BibleTui`) plus the pure search/fuzzy helpers.
- `bible_tui/bibles/` holds the bundled databases (package data, so installs include them). They are copied
  unchanged from the separate converter project; don't edit them by hand.
- `docs/configuration.md` covers the app home, `config.json`, `state.json`, the search path, and the planned
  user-data layout. `docs/bible-databases.md` covers the database schema, metadata keys, and the bundled
  versions.
- `tests/` holds `unittest` tests. `tests/helpers.py` has `make_bible` (writes a tiny database) and
  `FakeScreen` (lets `BibleTui` logic run without a terminal).
- `.backlog/` holds Backlog.md tasks.

## Commands

- Run: `./bible-tui [VERSION] [-d DIR] [-c CONFIG]`; `./bible-tui --paths`; `./bible-tui --list-versions`
- Tests: `python3 -m unittest discover -s tests -t .`
- Syntax check: `python3 -m py_compile bible_tui/*.py tests/*.py`

No linter or formatter is installed. Automated verification (`.agent/verification.json`) is intentionally
disabled.

## Design Rules

- Python standard library only; keep Python 3.9 compatibility (`from __future__ import annotations` in every
  module).
- Nothing may assume a particular version. Version names come from database metadata (`version`,
  `version_name`) with a filename fallback. The TUI always shows the full `version_name`. The `version`
  abbreviation is for identifying versions (CLI argument, `default_version`, `state.json`, shadowing) and for
  `--list-versions`. Never hardcode a version abbreviation or file name outside tests and
  the docs for the bundled versions.
- Databases are always opened read-only (`connect_read_only`). Never write to a Bible database.
- Versions can differ in verse coverage (the ASV omits 16 verses) and may be partial. Cross-version positions
  use `(book sort_order, chapter, verse)`, not row ids; restoring a missing verse falls back to the nearest
  earlier verse. Future bookmarks, highlights, and notes must use the same version-independent key.
- The user writes `config.json` and the app never rewrites it. App-written data goes in separate files in the
  app home, saved with `config.write_json`.
- Commands that only report (`--paths`, `--list-versions`) must not create the app home.
- A broken or unrecognised database in a Bible folder is reported under "Skipped" and never stops startup.

## TUI Notes

- The curses UI has three focus panes: books, chapters, and text. Navigation supports Vim-style keys and arrows.
- Highlighting a book previews that book immediately: the chapters pane loads, chapter 1 is selected, and the
  text pane shows chapter 1 without moving focus away from books. Focus only moves from books on Enter, right
  arrow, or `l`.
- Keybinding help lives in the `ctrl+p` commands modal, not in the top header. The footer prompt keeps
  `ctrl+p` white and `commands` in the dim footer gray.
- Search is Vim-style in the books and text panes. `/` opens a footer command line and live search shows a
  match count. Enter accepts the query and leaves the search bar visible read-only with current/total match
  status. `/` edits the active search again, `n`/`N` jump through matches, and Esc clears highlighting. From the
  chapters pane, `/` first selects the highlighted chapter and moves focus to text search. Only `q` exits the
  TUI; Esc is for clearing/dismissing UI modes.
- `ctrl+f` opens the native full-Bible fuzzy finder. It must stay dependency-free and must not shell out to
  `fzf`. Results use common book abbreviations, an ellipsized snippet column, and a preview pane.
- `ctrl+g` opens a go-to-reference modal for references like `John 3:16`. Autocomplete uses Tab to accept
  suggestions and `ctrl+n` to cycle suggestions.
- `t` opens the version picker (also in `ctrl+p`). `BibleTui.switch_version` swaps the store, clears the
  per-version caches (`all_verses`, `goto_verse_cache`, active search), restores the position, and calls
  `on_version_change`. The CLI uses that callback to record `last_version` in `state.json`.
- Clipboard support tries `pbcopy`, `wl-copy`, `xclip`, `xsel`, then `clip.exe` (`copy_to_clipboard`). If none
  works, the status bar says `clipboard unavailable`.
- Be careful with terminal sizing logic and bottom-right curses writes; `add_screen_line` intentionally avoids
  the bottom-right cell.

## Working Practices

- After changing Python code, run the syntax check and the test suite.
- Manual TUI behaviour still needs a real terminal check with `./bible-tui`. A tmux session
  (`tmux new-session -d -x 110 -y 30 './bible-tui'`, then `send-keys` / `capture-pane -p`) works for scripted
  checks.
- When adding a bundled version, add it under `bible_tui/bibles/` and to the table in
  `docs/bible-databases.md`. If it's public domain, mention it in the README.
- Keep this file updated as new conventions, commands, risks, or decisions come up.
