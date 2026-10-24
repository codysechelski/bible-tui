# Configuration and files

bible-tui keeps everything it reads or writes in one folder, the **app home**.

## Where the app home is

The first match wins:

1. `$BIBLE_TUI_HOME`, if set (used even if it does not exist yet).
2. `~/.bible-tui`, if it exists.
3. `$XDG_CONFIG_HOME/bible-tui`, which is `~/.config/bible-tui` by default.

If neither folder exists, bible-tui uses the XDG location and only creates it the first time it needs to save
something. Run `bible-tui --paths` to see which folder is in use and what it contains.

## What lives there

```text
~/.config/bible-tui/
├── config.json      # your settings; bible-tui only ever reads this file
├── state.json       # remembered by the app (the last version you switched to, the split)
├── marks.json       # your marked verses
├── highlights.json  # your highlighted verses and their colors
└── bibles/          # drop extra Bible databases here
```

`config.json` is yours. The app never rewrites it, so your formatting is kept. Anything the app records by
itself goes in its own file next to it. Those files are written atomically, so a crash can't leave one
half-written.

## `config.json`

Every key is optional. A missing file means all defaults.

```json
{
  "default_version": "KJV",
  "bibles_dirs": ["~/Bibles", "/usr/share/bibles"],
  "book_order": "bible",
  "nerd_font": false,
  "remember_split": false
}
```

| Key | Default | Meaning |
| --- | --- | --- |
| `default_version` | none | Version to open at launch. Matches an abbreviation (`KJV`), a full name, or a database file name. |
| `bibles_dirs` | `[]` | Extra folders to search for Bible databases. `~` is expanded; relative paths are taken from the config file's folder. A single string is accepted too. |
| `book_order` | `"bible"` | Starting book order: `"bible"` (canonical, grouped by testament) or `"alphabetical"`. `a` still toggles it in the app. |
| `nerd_font` | `false` | Set to `true` if your terminal uses a [Nerd Font](https://www.nerdfonts.com/) to get icons, such as the bookmark icon for marked verses. Off by default because a terminal program can't detect the font, and a missing glyph shows as an empty box. Without it, plain Unicode symbols (`●`) are used. |
| `remember_split` | `false` | Set to `true` to reopen a split (`ctrl+w v` or `ctrl+w s`) at launch, with the same orientation and second-pane version. The split is saved in `state.json` as `split` and `split_version`. |

Unknown keys are ignored with a warning. Invalid JSON or a value of the wrong type stops the app with a message
naming the file, line, and key. Use `--config FILE` to read a different file.

## Which version opens at launch

1. The version given on the command line (`bible-tui asv` or `bible-tui path/to/file.sqlite`).
2. `default_version` from `config.json`.
3. The last version you switched to in the app (`last_version` in `state.json`).
4. The first available version, alphabetically.

## Where Bible databases are found

Folders are searched in this order:

1. Each `--bibles-dir DIR` on the command line.
2. Each folder in `bibles_dirs`.
3. `<app home>/bibles/`.
4. The versions bundled with bible-tui.

Two databases can have the same abbreviation, for example your own `KJV` and the bundled one. When that
happens, the one from the earlier folder is used and the other is listed under "Skipped" by
`bible-tui --list-versions`. Files that aren't usable Bible databases are skipped the same way and never stop the
app from starting. See [bible-databases.md](bible-databases.md) for the database format.

## User data

Each kind of user data gets its own app-written JSON file in the app home, saved the same atomic way as
`state.json`. Separate files keep each one small, easy to back up or sync on its own, and make a damaged file
affect only one feature. Marks and highlights work this way now; notes and saved searches will follow the same pattern (`notes.json`,
`saved-searches.json`).

Verses are stored by a version-independent reference rather than by database row ids: the book's canonical
`sort_order` (1–66), the chapter, and the verse. A verse marked while reading the KJV shows as marked in the ASV
or any other version that has it.

### `marks.json`

`m` marks or unmarks the current verse, or every verse in a visual selection. A marked verse shows a sign in the
column left of its number. `M` or `'` lists every mark, newest first, Enter jumps to the selected one, and `d` or Delete removes it.
`created_at` (UTC) records when the verse was marked; verses marked together keep Bible order.

```json
{
  "version": 1,
  "marks": [
    { "book": 43, "chapter": 3, "verse": 16, "created_at": "2026-10-22T21:44:36+00:00" }
  ]
}
```

`version` is the file format version. If the file can't be read, bible-tui says so at startup and leaves it
untouched: existing marks are not shown, and new marks aren't saved until the file is fixed or removed, so a
damaged file is never overwritten with an empty list.

### `highlights.json`

`c` opens a color picker for the current verse, or every verse in a visual selection: yellow, green, blue,
purple, pink, orange, or clear. `C` or `"` lists every highlight, newest first; Enter jumps to one and `d` or
Delete removes it.

```json
{
  "version": 1,
  "highlights": [
    { "book": 43, "chapter": 3, "verse": 16, "color": "yellow", "created_at": "2026-10-23T18:24:53+00:00" }
  ]
}
```

Colors are stored by name, so the exact shades can change without touching your data. Changing a verse to a
new color updates its `created_at`. A damaged file is handled the same way as `marks.json`.
