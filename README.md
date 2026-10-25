# bible-tui

A fast, dependency-free terminal Bible reader with Vim-style navigation, live search, a full-Bible fuzzy finder,
and go-to-reference with autocomplete.

It ships with the **King James Version** and the **American Standard Version** (both public domain). To add
another version, drop its SQLite database into a folder.

## Requirements

- Python 3.9 or newer (standard library only)
- A terminal at least 50×10
- macOS or Linux. Copying to the clipboard uses the first of `pbcopy`, `wl-copy`, `xclip`, `xsel`, or `clip.exe`
  that is installed.

## Install

Run it straight from a clone:

```sh
git clone <this repo> bible-tui
cd bible-tui
./bible-tui
```

Or install the `bible-tui` command with [pipx](https://pipx.pypa.io/):

```sh
pipx install .
bible-tui
```

## Usage

```sh
bible-tui              # open the default version
bible-tui asv          # open a specific version by abbreviation
bible-tui ~/my.sqlite  # open a database file directly
bible-tui --list-versions
bible-tui --paths      # show the config, state, and Bible folders in use
bible-tui --bibles-dir ~/Bibles   # search an extra folder (repeatable)
```

### Key bindings

Every action has a key that works without knowing Vim: arrows, Tab, Page Up/Down, Home/End, Enter, Esc. Vim and
Neovim users get the usual alternatives too. `ctrl+p` (or `?`) lists them all inside the app.

| Action | Keys | Vim-style |
| --- | --- | --- |
| Move up / down | ↑ / ↓ | `k` / `j` |
| Move between books and chapters | ← / → | `h` / `l` |
| Next / previous pane | Tab / Shift+Tab | |
| Next / previous chapter (continues into the next/previous book) | `]` / `[` | |
| Half page up / down | | `ctrl+u` / `ctrl+d` |
| Page up / down | Page Up / Page Down | `ctrl+b` / `ctrl+f` |
| First / last item | Home / End | `gg` / `G` |
| Select the book or chapter | Enter | |
| Switch version (keeps your place) | `t` | |
| Toggle Bible order / alphabetical | `a` | |
| Search books or the chapter | `/`, then `n` / `N` for matches, Esc to clear | |
| Fuzzy find across the whole Bible | `ctrl+s` (press again inside for the query syntax) | |
| Go to a reference like `John 3:16` | `ctrl+g` | `:John 3:16` |
| Commands and key list | `ctrl+p` | `?` |
| Quit | `q` | `:q` |

### The `:` command line

`:` opens a Vim-style command line in the footer. A menu above it suggests commands, book names, chapters,
and verses as you type: Tab accepts the highlighted one, ↑ / ↓ or `ctrl+n` / `ctrl+p` move through them,
Enter runs the line, and Esc cancels. Commands can be shortened like in Vim (`:q`, `:vs`).

| Command | Does |
| --- | --- |
| `:John 3:16`, `:John 3`, `:John` | Go to a verse, or the start of a chapter or book |
| `:q` / `:quit` | Quit (`:wq`, `:x`, and `:q!` work too) |
| `:find [words]` | Open the fuzzy finder, searching for the words if given |
| `:set version=ASV` | Switch the focused pane's version; `:set version` alone opens the picker |
| `:vsplit` / `:split` | Split side by side / top and bottom |
| `:close` / `:only` | Close the focused pane / the other pane |
| `:marks` / `:highlights` | List marks / highlights |

The footer shows the mode (such as `-- VISUAL --`) on the left. Your place (version, reference, and focused
pane) is on the right, before the `ctrl+p` hint.

In the text pane:

| Action | Keys |
| --- | --- |
| Move the cursor by character | `h` / `l` |
| Start / end of the verse | `0` / `$` |
| Next word / previous word / end of word | `w` / `b` / `e` |
| Select text / select whole verses | `v` / `V` (press again or Esc to cancel) |
| Copy the selection | `y` |
| Copy the current verse (add its reference with the `yank_format` setting) | `yy` |
| Mark / unmark the verse (or every verse in a selection) | `m` |
| List all marks, newest first (Enter jumps to one, `d` or Delete removes it) | `M` or `'` |
| Highlight the verse (or every verse in a selection) in a color | `c` |
| List all highlights, newest first (Enter jumps, `d` or Delete removes) | `C` or `"` |

Copying uses the system clipboard. Marked verses show `●` in the column left of the verse number, or a
bookmark icon if you set `"nerd_font": true` in `config.json` (which turns on a few other icons too).
Messages about what an action did show in yellow in the footer, just left of your place (failures in red),
and fade after a few seconds. Marks are saved and show in every version.

### Comparing two versions

Split the text pane to read two versions side by side (or one above the other). Choosing a book, chapter,
reference, mark, or highlight moves both panes together. Each verse starts on the same line in both panes, and
a verse that one version leaves out is shaded `░░░`.

| Action | Keys |
| --- | --- |
| Split side by side / top and bottom (then pick the new pane's version) | `ctrl+w v` / `ctrl+w s` |
| Move between the two text panes | ← / →, Tab, or `ctrl+w w` (`ctrl+w h`/`j`/`k`/`l`) |
| Change either pane's version (two columns; ← / → picks the pane) | `t` |
| Close the focused pane / the other pane | `ctrl+w q` / `ctrl+w o` |

Two panes is the most. Visual mode, copying, `/` search, and fuzzy find use the focused pane's version. These
are in the `ctrl+p` list too. Set `"remember_split": true` in `config.json` to reopen the split at launch.

## Adding versions

Copy a Bible database into `~/.config/bible-tui/bibles/` and it shows up in the version picker. You can also
list other folders in `config.json` or pass `--bibles-dir`. The database format is described in
[docs/bible-databases.md](docs/bible-databases.md).

## Configuration

Settings live in `config.json` in the app home: `~/.bible-tui` if that folder exists, otherwise
`~/.config/bible-tui` (or wherever `$BIBLE_TUI_HOME` points).

```json
{
  "default_version": "KJV",
  "bibles_dirs": ["~/Bibles"],
  "book_order": "bible",
  "nerd_font": false,
  "remember_split": false,
  "yank_format": "{text}"
}
```

See [docs/configuration.md](docs/configuration.md) for every setting, the lookup order, and the files the app
writes.

## Development

```sh
python3 -m unittest discover -s tests -t .
python3 -m py_compile bible_tui/*.py tests/*.py
```

## Bible texts

The bundled KJV and ASV come from [eBible.org](https://ebible.org) and are in the public domain. Sources and notes
on each text are in [docs/bible-databases.md](docs/bible-databases.md#bundled-versions).
