# Copying verses

`yy` copies the current verse. To copy part of a verse or several verses, select with `v` (characters) or `V`
(whole verses) and press `y`.

![Copying part of a verse, several verses, a passage with its reference, and a whole verse with and without a copy format, pasted into notes](../../tapes/yanking/gifs/yanking-with-keys_small.gif)

## Copy a passage with its reference

`Y` copies whole verses with one combined reference and the version, ready to paste into notes, a sermon
outline, or Obsidian:

```
16 For God so loved the world, that he gave his only begotten Son, ...
17 For God sent not his Son into the world to condemn the world; ...
18 He that believeth on him is not condemned: ...
— John 3:16–18 · KJV
```

Select with `V` and press `Y`, or press `Y` with nothing selected to copy the current verse the same way. A `v`
selection that starts or ends partway through a verse copies every verse it touches in full, never part of one.
Without Vim keys, open `ctrl+p` and choose "select verses", then "copy passage with reference". In a split, `Y`
uses the version of the pane you're in.

## Choose what gets copied

Set `copy_verse_format` (for `yy`) and `copy_passage_format` (for `Y`) in `config.json`. A template is copied as
written with its fields filled in, so Markdown works just by typing it:

```json
{
  "copy_verse_format": "{text}\n\n  ~ {reference} {version}",
  "copy_passage_format": "> {text}\n>\n> — {reference} ({version})",
  "copy_verse_numbers": true
}
```

With `> ` before `{text}`, every verse line is quoted. Set `copy_verse_numbers` to `false` to leave out the verse
numbers. The fields are `{text}`, `{reference}`, `{book}`, `{book_abbr}`, `{chapter}`, `{version}`, and
`{version_name}`, plus `{verse}` for `yy` and `{start_verse}`/`{end_verse}` for `Y`. See
[copy formats](../configuration.md#copy-formats) for examples. (`copy_verse_format` used to be called
`yank_format`, which still works.)

Copying uses the first of `pbcopy`, `wl-copy`, `xclip`, `xsel`, or `clip.exe` that is installed.
