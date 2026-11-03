# Reading and navigation

The screen has three panes: books, chapters, and the text. Move through them with the arrow keys, Tab, Page
Up/Down, and Home/End, or use Vim keys if you know them. Highlighting a book shows its first chapter right away,
so you can browse without pressing Enter.

![Moving through books, chapters, and verses with arrows or Vim motions, then stepping through chapters with ] and [](../../.tapes/navigation/gifs/navigation-with-keys.gif)

| Action | Keys | Vim-style |
| --- | --- | --- |
| Move up / down | ↑ / ↓ | `k` / `j` |
| Move between books, chapters, and text | ← / →, Tab / Shift+Tab | `h` / `l` |
| Half page up / down | | `ctrl+u` / `ctrl+d` |
| Page up / down | Page Up / Page Down | `ctrl+b` / `ctrl+f` |
| First / last item | Home / End | `gg` / `G` |
| Start / end of the verse | | `0` / `$` |
| Next word / previous word / end of word | | `w` / `b` / `e` |
| Bible order / alphabetical book list | `a` | |

## Chapter by chapter

`]` and `[` step to the next or previous chapter from anywhere. At the end of a book they continue into the
next one, in Bible order, even when the book list is sorted alphabetically.

![The books pane in alphabetical order](../../.tapes/navigation/screenshots/showing-books-in-alphabetical-order.png)

Every key is listed in [keybindings.md](../keybindings.md), and in the app under `ctrl+p` or `?`.
