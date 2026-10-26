# Roadmap

Features planned for bible-tui. They aren't in any order, and nothing here has a date yet.

## Custom themes

Right now bible-tui uses your terminal's colors. The interface uses the basic ANSI colors on your terminal's own
background, so it looks different in every terminal theme. Only the highlight tints are fixed 256-color shades.
Themes would let you set the colors yourself, so the app looks the same everywhere. You could set the pane
borders, the selection and current-verse bars, search matches, the footer, and the six highlight colors.

Themes would be set in `config.json` like the other settings, probably with a few built-in themes to start from.
The current terminal-based colors would stay the default. Themes need to work on 8-color, 256-color, and
true-color terminals, so each color will need a fallback for terminals that can't show it.

## Custom key bindings

You'll be able to change any key binding and add new ones from `config.json`. You could map an action to a key
that's easier to reach, avoid a clash with your terminal or tmux, or bind an action that has no key yet. The
defaults stay the same. Your bindings only change the keys you set.

Every action in the `ctrl+p` commands list will have a name you can bind to. The commands list and the
key-binding docs will show your own keys, not the defaults. Bindings with problems (a key used twice, an
unknown action, a key the terminal can't send) will show a warning at startup, the same way other config
problems do. The app will still start. One rule from the keybinding policy stays: every action must still be
reachable with arrows, Tab, Enter, and Esc, so a custom binding can add a key but can't leave an action with
no key.

## Translations

The menus, the commands list, help text, prompts, and footer messages will be translatable, so people can use
bible-tui in their own language. This covers the app's own text only. The Bible text comes from whichever
version you load, and you can already add Bibles in any language (see
[Adding Bibles](docs/adding-bibles.md)).

The plan is to move every user-facing string into a separate file for each language. Python's built-in
`gettext` should handle this without adding any dependencies. A `language` setting will choose the language,
and English will be used for anything not yet translated. Book names already come from each Bible database. The
short book abbreviations (`Gen.`, `Ex.`) are still a fixed English list, and will need to be translated too.

**Help wanted:** I'm hoping the community will help with this one. Once the strings are ready to translate,
I'll write a short guide on adding a language. If you'd like to translate bible-tui into your language, or
check someone else's translation, please open an issue to say so. That will help decide which languages come
first.
