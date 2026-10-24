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
  for marks, highlights, and future notes files.
- `bible_tui/versions.py` holds `BibleVersion`, `inspect_database` (schema check plus metadata), and
  `discover_versions` (priority-ordered folders; an earlier folder wins when abbreviations collide). It also has
  `connect_read_only`.
- `bible_tui/marks.py` holds `MarkStore`: marked verses keyed by `(sort_order, chapter, verse)` and saved to
  `marks.json` with `config.write_json`. A store whose file failed to load keeps `load_error` and refuses to save.
- `bible_tui/highlights.py` holds `HighlightStore` and `HIGHLIGHT_COLORS`: the same pattern for `highlights.json`,
  storing color names (never curses numbers). `apply` restores the old state if saving fails. Unknown color names
  in the file are kept, and drawn underlined.
- `bible_tui/store.py` holds `BibleStore` (read-only queries for one version), the `Book`/`Verse`/`BibleVerse`
  models, and `BOOK_ABBREVIATIONS`.
- `bible_tui/tui.py` is the curses UI (`BibleTui`) plus the pure search/fuzzy/alignment helpers.
- `bible_tui/bibles/` holds the bundled databases (package data, so installs include them). They are copied
  unchanged from the separate converter project; don't edit them by hand.
- `docs/configuration.md` covers the app home, `config.json`, `state.json`, the search path, and the
  user-data files (`marks.json`, `highlights.json`). `docs/bible-databases.md` covers the database schema, metadata keys, and the bundled
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
  earlier verse. Marks, highlights, and future notes use the same version-independent key.
- Never overwrite user data that failed to load (see `MarkStore.load_error`); losing marks or notes is
  worse than refusing to save.
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
- `ctrl+s` opens the native full-Bible fuzzy finder (`ctrl+s` again inside shows the query syntax). It must stay dependency-free and must not shell out to
  `fzf`. Results use common book abbreviations, an ellipsized snippet column, and a preview pane.
- `ctrl+g` opens a go-to-reference modal for references like `John 3:16`. Autocomplete uses Tab to accept
  suggestions and `ctrl+n` to cycle suggestions.
- Keybinding policy: every action must be reachable without Vim knowledge (arrows, Tab, Page Up/Down,
  Home/End, Enter, Esc). Vim keys are extra aliases, never the only way. Current aliases: `h`/`j`/`k`/`l`,
  `ctrl+u`/`ctrl+d` (half page), `ctrl+b`/`ctrl+f` (page), `gg`/`G`, `0`/`$`, `w`/`b`/`e`, `v`/`V`, `y`/`yy`,
  `:` (go to), `'`/`` ` `` (marks list), `"` (highlights list), `?` (commands), and the `ctrl+w` split commands
  (`v`, `s`, `w`, `h`/`j`/`k`/`l`, `q`/`c`, `o`). Don't add count prefixes, Vim-style lettered marks, jump
  lists, `H`/`L`, or other `ctrl+w` window commands. `M`/`C` are the plain-key marks/highlights lists (`M` is not Vim's middle-of-screen). Two-key sequences (`gg`, `yy`, `ctrl+w x`) use the `pending_g`/`pending_y`/`pending_w` flags. `]`/`[` step chapters
  across books in Bible order even when the list is alphabetical. Moving focus right must not re-select the
  book or chapter already shown (`ensure_cursor_book_selected`), or you lose your place.
- The text pane gutter is a 2-cell sign column followed by the 4-cell verse number (`SIGN_WIDTH`,
  `NUMBER_WIDTH`, `GUTTER_WIDTH`). It's always shown, like Vim's `signcolumn=yes`, so text never shifts. Signs
  are drawn on a verse's first line only. The mark sign is `MARK_SIGN_NERD_FONT` (U+F02E, nf-fa-bookmark,
  present in Nerd Fonts v2 and v3) when the `nerd_font` setting is true, otherwise `MARK_SIGN_PLAIN` (`●`),
  in blue. Nerd Font use is always opt-in; never try to detect the font.
- `m` toggles a mark on the current verse or every verse in the visual selection (`BibleTui.toggle_mark`).
- `c` opens the highlight picker for the same targets (`target_verse_keys`): six colors plus Clear, keys `1`–`6`,
  `0`/`x`/`d` to clear, or arrows and Enter. It preselects the verses' shared color, else the last color used.
  Highlights are drawn as a background on the verse's text characters (`HIGHLIGHT_PALETTE`: soft 256-color tints
  with black text, or ANSI colors on 8-color terminals). Precedence: search match > visual selection > highlight
  > current-verse bar; a highlighted current verse keeps its color and is bold.
- `M` (or `'`/`` ` ``) and `C` (or `"`) open one shared list modal (`list_kind` is `LIST_MARKS` or
  `LIST_HIGHLIGHTS`): newest first by `created_at`, ties in Bible order. Rows show the current version's book
  abbreviation and text (or `(not in <version>)`); highlights add a color swatch. Enter calls `jump_to_key`,
  which uses `restore_position` like a version switch. `d`/Delete removes the row's mark or highlight; a failed
  save leaves it in place.
- `t` opens the version picker (also in `ctrl+p`). `BibleTui.switch_version` swaps the store, clears the
  per-version caches (`all_verses`, `goto_verse_cache`, active search), restores the position, and calls
  `on_version_change`. The CLI uses that callback to record `last_version` in `state.json`.
- Splits: at most two text panes (`split` is `SPLIT_VERTICAL` or `SPLIT_HORIZONTAL`; a third is refused with
  `2 panes max`). The first pane is the app's main state (`store`, `version`, `verses`) and supplies the books
  and chapters lists. The second is a `SplitPane` that follows the same book (by `sort_order`, since book ids
  differ between databases) and chapter. `load_chapter_verses` aligns both with `align_verses`, so both
  `verses` lists have the same rows and `verse_cursor` is shared. A verse one side lacks is a `MissingVerse`
  (empty text) drawn shaded with `MISSING_SHADE`. `text_lines` pads each verse to the taller pane so rows
  line up and `text_scroll` is shared. `active_pane` picks the pane for visual mode, yank, `/` search
  (`search_pane`), and fuzzy find; code that reads verse text uses `active_verses`, not `verses`. Left/Right
  and Tab move between text panes; `h`/`l` stay character motions. Opening a split shows the version picker
  in `PICK_NEW_PANE` mode; `t` while split uses `PICK_PANES` (two columns). Closing the first pane switches the
  main version to the second pane's. A split that no longer fits the terminal draws only the focused pane
  (`text_pane_rects`). `on_split_change` lets the CLI save `split`/`split_version` to `state.json`, only when
  the `remember_split` setting is true; `remembered_split` restores it at launch.
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
