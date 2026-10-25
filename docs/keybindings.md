# Key bindings

Every action has a key that works without knowing Vim: arrows, Tab, Page Up/Down, Home/End, Enter, Esc. Vim and
Neovim users get the usual alternatives too. `ctrl+p` (or `?`) lists them all inside the app.

## Navigation

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

## The text pane

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

Copying uses the first of `pbcopy`, `wl-copy`, `xclip`, `xsel`, or `clip.exe` that is installed. Marked verses show `●` in the column left of the verse number, or a
bookmark icon if you set `"nerd_font": true` in `config.json` (which turns on a few other icons too). Marks and
highlights are saved and show in every version.

The footer shows the mode (such as `-- VISUAL --`) on the left. Your place (version, reference, and focused
pane) is on the right, before the `ctrl+p` hint. Messages about what an action did show in yellow just left of
your place (failures in red) and fade after a few seconds.

## The `:` command line

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
| `:update` | Install a newer release and restart at the same verse (see [update checks](configuration.md#update-checks)) |

## Comparing two versions

Split the text pane to read two versions side by side (or one above the other). Choosing a book, chapter,
reference, mark, or highlight moves both panes together. Each verse starts on the same line in both panes, and
a verse that one version leaves out is shaded `░░░`.

| Action | Keys |
| --- | --- |
| Split side by side / top and bottom (then pick the new pane's version) | `ctrl+w v` / `ctrl+w s` |
| Move between the two text panes | ← / →, Tab, or `ctrl+w w` (`ctrl+w h`/`j`/`k`/`l`) |
| Change either pane's version (two columns; ← / → picks the pane) | `t` |
| Close the focused pane / the other pane | `ctrl+w q` / `ctrl+w o` |

Two panes is the most. Visual mode, copying, `/` search, and fuzzy find use the focused pane's version. Set
`"remember_split": true` in `config.json` to reopen the split at launch.
