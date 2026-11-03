# Vim-inspired navigation philosophy

> **Vim is an inspiration, not a specification.**

bible-tui borrows familiar Vim navigation conventions because they make a keyboard-driven Bible reader comfortable and efficient. But bible-tui is **a Bible reader, not a text editor or a Vim replacement**. We prioritize reading and navigating Scripture over matching Vim's behavior for its own sake.

Our guiding principle is **familiarity without complexity**: use Vim-inspired interactions where they make reading easier, without importing the entire Vim interaction model.

## What fits

- Simple, recognizable navigation keys such as `h`, `j`, `k`, and `l`.
- Keyboard shortcuts that make it faster to move between books, chapters, verses, and reading tools.
- Discoverable commands that solve real reader needs, whether or not Vim has an equivalent.
- **Non-Vim alternatives for every action.** Vim familiarity must never be required to use bible-tui.

## What we're not pursuing

These are intentional boundaries for the project's current direction, not missing features waiting to be implemented.

- **Leader-key mappings.** A configurable leader key and the surrounding mapping conventions would add a layer of editor-like complexity that doesn't serve the core reading experience.
- **Count-prefixed motions**, such as `5j` to move five positions. For now, we don't plan to add Vim's numeric motion prefixes. Their value is less compelling here without relative line numbers, and we prefer simpler, reading-oriented navigation.
- **Relative line numbers.** We don't plan to introduce them. The book selector has no line numbers, and chapters and verses have meaningful, canonical numbers that should not be confused with editor-style line numbering.
- **Vim compatibility as a goal.** We are not aiming for complete Vim motions, modes, remapping, or an editor-compatible command language simply for parity.

These examples are not a blanket rejection of better navigation. They explain why a feature that makes sense in an editor may not make sense in a Bible reader.

## Proposing a navigation improvement

Issues and contributions are welcome. Before suggesting a Vim feature, consider:

1. What reading or navigation problem does it solve?
2. Would it still make sense to someone who has never used Vim?
3. Is there a simpler, more discoverable solution?
4. Can the action remain accessible without Vim-style keys?
5. Does it respect the structure of Scripture, especially book names and canonical chapter and verse numbers?

Please describe the **user problem first**, rather than assuming Vim's solution is the right one. We can revisit individual choices if a compelling reader-focused use case emerges, but these boundaries represent the current design direction—not an invitation to reproduce Vim feature by feature.

**The goal is an excellent terminal Bible reader that feels familiar to Vim users, not Vim with a Bible inside it.**
