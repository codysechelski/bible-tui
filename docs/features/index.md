# Features

bible-tui is a terminal Bible reader that stays out of your way. Everything works with the arrow keys, Enter,
and Esc, and Vim users get the keys they already know. Each page below has a short animation of the feature.

## Reading

- **[Reading and navigation](navigation.md)**: books, chapters, and text in three panes. Arrows or Vim
  motions, and `]` / `[` to read straight through chapter by chapter.
- **[Go to a reference](go-to-reference.md)**: type `John 3:16` with autocomplete, in a box (`ctrl+g`) or on
  the command line (`:John 3:16`).
- **[Commands and the command line](command-line.md)**: every action listed under `ctrl+p`, and a Vim-style `:`
  command line.

## Finding

- **[Search books and chapters](search.md)**: `/` finds a book or a word in the chapter, with `n` / `N` to step
  through matches.
- **[Fuzzy-find the whole Bible](fuzzy-find.md)**: `ctrl+s` searches every verse as you type, with a preview
  and a query syntax for exact words, prefixes, and exclusions.

## Versions

- **[Versions](versions.md)**: switch translations with `t` without losing your place. Any version, in any
  language, is one SQLite file. KJV and ASV are included.
- **[Compare versions side by side](split-view.md)**: split the screen with `ctrl+w v` and read two versions
  with their verses lined up.

## Studying

- **[Marks](marks.md)**: bookmark verses with `m` and jump back to them from a list.
- **[Highlights](highlights.md)**: highlight verses in six colors with `c`, with a list of every highlight.
- **[Copying verses](copying.md)**: copy a verse with `yy` or a selection with `y`, with an optional format that
  adds the reference.

## Your data

- **[Plain files you own](your-files.md)**: settings, marks, and highlights are readable JSON files in one
  folder, easy to back up or keep in your dotfiles.
