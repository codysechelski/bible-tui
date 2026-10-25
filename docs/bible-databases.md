# Bible databases

Each version is a single SQLite file. To add a version, copy its database into `~/.config/bible-tui/bibles/` (or
any folder from [configuration.md](configuration.md#where-bible-databases-are-found)) and restart bible-tui. It
appears in the version picker (`t`) and in `bible-tui --list-versions`.

To convert a published Bible (USFM, USX, OSIS, and others) into a database, see
[adding-bibles.md](adding-bibles.md).

Files ending in `.sqlite`, `.sqlite3`, or `.db` are considered. bible-tui opens them read-only and never changes
them.

## Bundled versions

| File | Version | Books, chapters, verses | Source | Licence |
| --- | --- | --- | --- | --- |
| `bible_tui/bibles/bible_kjv.sqlite` | King James Version (1769 standardized text) | 66, 1189, 31102 | [eBible.org](https://ebible.org/find/details.php?id=eng-kjv) | Public domain (outside the United Kingdom, where the Crown's letters patent restrict printing) |
| `bible_tui/bibles/bible_asv.sqlite` | American Standard Version (1901) | 66, 1189, 31086 | [eBible.org](https://ebible.org/find/details.php?id=eng-asv) | Public domain |

The ASV leaves out 16 New Testament verses that later manuscripts add (for example Matthew 17:21 and Acts 8:37).
When you switch to a version that lacks the verse you are on, the cursor moves to the nearest earlier verse.

## Schema

These tables and columns are required. Extra tables, columns, and indexes are allowed.

```sql
CREATE TABLE metadata (          -- optional, but recommended
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE books (
    id INTEGER PRIMARY KEY,
    sort_order INTEGER NOT NULL UNIQUE,   -- canonical position, 1 (Genesis) to 66 (Revelation)
    canonical_name TEXT NOT NULL UNIQUE,
    common_name TEXT NOT NULL,            -- shown in the UI, e.g. "1 Samuel"
    slug TEXT NOT NULL UNIQUE,
    testament TEXT NOT NULL CHECK (testament IN ('old', 'new'))
);

CREATE TABLE chapters (
    id INTEGER PRIMARY KEY,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    chapter_number INTEGER NOT NULL,
    UNIQUE (book_id, chapter_number)
);

CREATE TABLE verses (
    id INTEGER PRIMARY KEY,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    chapter_number INTEGER NOT NULL,
    verse_number INTEGER NOT NULL,
    text TEXT NOT NULL,
    UNIQUE (book_id, chapter_number, verse_number)
);

CREATE INDEX idx_books_testament_order ON books(testament, sort_order);
CREATE INDEX idx_chapters_book_number ON chapters(book_id, chapter_number);
CREATE INDEX idx_verses_book_chapter_verse ON verses(book_id, chapter_number, verse_number);
CREATE INDEX idx_verses_chapter_number ON verses(chapter_id, verse_number);
```

The columns bible-tui reads are `books(id, sort_order, common_name, testament)`,
`chapters(book_id, chapter_number)`, and `verses(book_id, chapter_number, verse_number, text)`. A database
without any verses is skipped.

### Metadata keys

| Key | Used for | Fallback |
| --- | --- | --- |
| `version` | Short abbreviation (`KJV`, `ASV`) used to pick a version on the command line, in `default_version`, and in `state.json`, and to tell versions apart | File name, upper-cased, with a leading `bible_` removed (`bible_web.sqlite` becomes `WEB`) |
| `version_name` | Full name (`King James Version`) shown everywhere in the TUI: title bar, status bar, version picker, and messages | The abbreviation |

Other metadata keys are ignored.

### Conventions

- Keep `sort_order` canonical (1–66) even if a version has only some books. bible-tui uses it to keep your
  place when you switch versions.
- Missing verses should be left out, not stored as empty text.
- Book names come from the database, so a version in another language shows its own book names. The short
  references in the fuzzy finder use English abbreviations when the name matches and the full name otherwise.
