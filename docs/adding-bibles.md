# Adding Bibles

bible-tui reads each version from one SQLite database. To add a version, put its database in a Bible folder
and restart bible-tui. The KJV and ASV are already included.

Bible texts are usually published as USFM, USX, OSIS, or a similar format, not as SQLite. The companion
[bible-tui-bible-converter](https://github.com/codysechelski/bible-tui-bible-converter) turns them into
databases with the schema bible-tui expects. Like bible-tui, it needs only Python 3.9+.

## 1. Find a source

Pick a translation whose licence lets you use it, and download it in a text format. Good places to look:

- [eBible.org](https://ebible.org/download.php) has hundreds of translations, many public domain or openly
  licensed. Download the **USFM** zip (for example `eng-web_usfm.zip` for the World English Bible).
- The [Digital Bible Library's open-access entries](https://app.thedigitalbiblelibrary.org/entries/open_access_entries)
  (USX bundles, with a `metadata.xml` that names the version).
- [CrossWire](https://crosswire.org/sword/modules/) OSIS files.

The converter reads USFM, USX, OSIS, VPL, USJ, and RTF. It accepts a single file, a folder of book files, or
the zip as downloaded. You don't need to unzip it.

## 2. Convert it

```sh
git clone https://github.com/codysechelski/bible-tui-bible-converter
cd bible-tui-bible-converter

cp ~/Downloads/eng-web_usfm.zip WEB.zip   # the file name becomes the abbreviation (see below)
tool/bin/bibles WEB.zip -o ~/.config/bible-tui/bibles/bible_web.sqlite
```

`-o` writes the database straight into bible-tui's Bible folder. Without it, the database goes into the
converter's own `bibles/` folder, and you can copy it over afterwards.

Every conversion validates the database before writing it. Read the warnings it prints: skipped books should
be only non-canonical ones (Apocrypha, front matter), and missing verses should be ones the translation
really leaves out. If a check fails, nothing is written. To convert only part of a Bible, such as a New
Testament, add `--allow-partial`.

The converter's [README](https://github.com/codysechelski/bible-tui-bible-converter#readme) and
[Quickstart](https://github.com/codysechelski/bible-tui-bible-converter/blob/main/Quickstart.md) cover every
format and option.

### How the version is named

bible-tui shows each version by the `version` (abbreviation) and `version_name` (full name) stored in the
database:

- A Digital Bible Library `metadata.xml` or an OSIS header supplies both.
- Otherwise the abbreviation is the source's file name without its extension, which is why the example copies
  the zip to `WEB.zip` first. The full name is then the same as the abbreviation.

The abbreviation is what you type to open a version (`bible-tui web`) and to set `default_version` in
`config.json`. Matching ignores case. Two versions with the same abbreviation can't both be used. The one in
the earlier folder wins, and `--list-versions` lists the other under "Skipped".

## 3. Check it in bible-tui

```sh
bible-tui --list-versions   # the new version should be listed
bible-tui web               # open it
```

If it isn't listed:

- Run `bible-tui --paths` to see which folders are searched. The app home is `~/.bible-tui` if that folder
  exists, otherwise `~/.config/bible-tui` (or `$BIBLE_TUI_HOME`). Databases go in its `bibles/` folder.
- The file must end in `.sqlite`, `.sqlite3`, or `.db`.
- A database that can't be read or doesn't match the schema is listed under "Skipped", with the reason.

## Keeping Bibles somewhere else

You don't have to use the app home. List other folders in `config.json`, or pass `--bibles-dir` (repeatable):

```json
{
  "bibles_dirs": ["~/Bibles"]
}
```

```sh
bible-tui --bibles-dir ~/Bibles
```

Folders given with `--bibles-dir` are searched first, then `bibles_dirs`, then `<app home>/bibles/`, then the
bundled versions. See [configuration.md](configuration.md#where-bible-databases-are-found).

## Making a database another way

Any tool can produce a database, as long as it matches the schema in
[bible-databases.md](bible-databases.md#schema). In particular, use the canonical book `sort_order` (1 to 66)
and leave out missing verses rather than storing empty text. The converter already follows these rules.
