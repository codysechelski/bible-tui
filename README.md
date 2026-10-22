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

- `j`/`k` or up/down: move within the focused pane
- `h`/`l` or left/right: move between books and chapters
- left/right: move into and out of the text pane
- `h`/`l` in the text pane: move the verse cursor by character
- `enter`: select the focused book or chapter; from chapters this moves focus to text
- `t`: switch version; your book, chapter, and verse are kept
- `v` in the text pane: enter visual mode
- `y` in visual mode: yank selected text to the system clipboard
- `yy` in the text pane: yank the current verse to the system clipboard
- `a`: toggle book ordering between Bible order and alphabetical
- `/`: search books or verses; Enter keeps search visible with match status, then use `n`/`N`, Esc, or `/` to
  edit again
- `ctrl+f`: fuzzy find across all verses with results and preview panes (`ctrl+s` inside shows the query syntax)
- `ctrl+g`: go to a reference like `John 3:16` with autocomplete
- `ctrl+p`: open the commands list
- `page up`/`page down`, `home`, `end`: faster scrolling
- `q`: quit

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
  "book_order": "bible"
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
