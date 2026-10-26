# bible-tui

<p align="center">
  <a href="https://github.com/codysechelski/bible-tui/releases"><img alt="Release" src="https://img.shields.io/github/v/release/codysechelski/bible-tui?sort=semver"></a>
  <a href="https://github.com/codysechelski/bible-tui/actions/workflows/release.yml"><img alt="CI" src="https://github.com/codysechelski/bible-tui/actions/workflows/release.yml/badge.svg"></a>
  <a href="pyproject.toml"><img alt="Python 3.9+" src="https://img.shields.io/badge/python-3.9%2B-blue"></a>
  <a href="pyproject.toml"><img alt="Dependencies: none" src="https://img.shields.io/badge/dependencies-none-brightgreen"></a>
</p>

A fast, dependency-free terminal Bible reader with Vim-style keys.

![bible-tui showing Genesis 1 with the books and chapters panes](docs/screenshots/images/main.png)

- **[Read and navigate](docs/features/navigation.md)** with arrows or Vim keys,
  [jump to `John 3:16`](docs/features/go-to-reference.md) with autocomplete, and use a Vim-style
  [`:` command line](docs/features/command-line.md).
- **[Search](docs/features/search.md)** within a chapter, or
  [fuzzy-find across the whole Bible](docs/features/fuzzy-find.md) with a live preview.
- **[Compare two versions](docs/features/split-view.md)** side by side, with verses lined up.
- **[Mark](docs/features/marks.md) and [highlight](docs/features/highlights.md)** verses in six colors. They're
  saved and show in every version.
- **[Bring any version](docs/features/versions.md)**, in any language: each one is a SQLite file. The
  public-domain KJV and ASV are included.

| | |
| --- | --- |
| ![Highlight color picker](docs/screenshots/images/multi-color-highlighting.png) | ![List of highlights](docs/screenshots/images/showing-jump-list-of-highlights.png) |
| [Highlight verses](docs/features/highlights.md) in six colors | [Jump back](docs/features/highlights.md) to any highlight or mark |
| ![Version picker](docs/screenshots/images/supports-multiple-versions.png) | ![A Portuguese Bible](docs/screenshots/images/support-for-non-english-bibles.png) |
| [Switch versions](docs/features/versions.md) and keep your place | [Any language](docs/features/versions.md#any-language) works |

<sub>The Portuguese screenshot shows the Bíblia Livre (BLIVRE), copyright © 2018 Diego Santos, Mario Sérgio, and Marco Teles, from
[eBible.org](https://ebible.org/porbr2018/copyright.htm), licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Not bundled with bible-tui.</sub>

**[See all features →](docs/features/index.md)** Each one has a short animation.

## Install

Requires Python 3.9+ on macOS or Linux, and nothing else.

```sh
pipx install git+https://github.com/codysechelski/bible-tui
bible-tui
```

Or run it from a clone with `./bible-tui`.

bible-tui checks for new releases once a day and tells you in the footer. Run `:update` to install the new
version and restart where you were. To turn the check off, set `"check_for_updates": false` (see
[update checks](docs/configuration.md#update-checks)).

## Usage

```sh
bible-tui                         # open the default version
bible-tui asv                     # open a version by abbreviation
bible-tui ~/my.sqlite             # open a database file directly
bible-tui --bibles-dir ~/Bibles   # search an extra folder (repeatable)
bible-tui --list-versions
bible-tui --paths                 # show the config, state, and Bible folders in use
```

| Action | Keys |
| --- | --- |
| Move | arrows, or `h` `j` `k` `l` |
| Next / previous chapter | `]` / `[` |
| Go to a reference | `ctrl+g`, or `:John 3:16` |
| Search the chapter / the whole Bible | `/` / `ctrl+s` |
| Switch version | `t` |
| Split to compare versions | `ctrl+w v` |
| Mark / highlight a verse | `m` / `c` |
| Copy the verse | `yy` |
| All commands and keys | `ctrl+p` or `?` |
| Quit | `q` |

Every action also works without Vim keys. The full list is in [docs/keybindings.md](docs/keybindings.md).

## Adding versions

Each version is one SQLite file. Copy a database into `~/.config/bible-tui/bibles/` and it appears in the
version picker. To make one from a published Bible (USFM, USX, OSIS, and others), use
[bible-tui-bible-converter](https://github.com/codysechelski/bible-tui-bible-converter). See
[docs/adding-bibles.md](docs/adding-bibles.md) for the steps, and
[docs/bible-databases.md](docs/bible-databases.md) for the schema.

## Configuration

`config.json` lives in the app home: `~/.bible-tui` if that folder exists, otherwise `~/.config/bible-tui` (or
`$BIBLE_TUI_HOME`).

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

Every setting is described in [docs/configuration.md](docs/configuration.md).

## Development

```sh
python3 -m unittest discover -s tests -t .
python3 -m py_compile bible_tui/*.py tests/*.py
```

Releases are automatic from [Conventional Commits](https://www.conventionalcommits.org/) on `main`: `fix:`
releases a patch and `feat:` a minor version. See [CONTRIBUTING.md](CONTRIBUTING.md) to get involved, and
[ROADMAP.md](ROADMAP.md) for what's planned.

## Bible texts

The bundled KJV and ASV come from [eBible.org](https://ebible.org) and are in the public domain. Sources and
notes are in [docs/bible-databases.md](docs/bible-databases.md#bundled-versions).

## Licence

bible-tui is released under the [MIT License](LICENSE). The bundled Bible texts are in the public domain.
