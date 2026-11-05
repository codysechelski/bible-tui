#!/usr/bin/env bash
# Runs inside the sandbox (../sandbox your-files ./setup.sh): keeps config.json in a dotfiles repo, linked
# into the app home the way GNU Stow would, and starts the app home without marks or highlights.
set -euo pipefail

stowed="$HOME/dotfiles/bible-tui/.config/bible-tui"
mkdir -p "$stowed"
# A config someone might keep: the clean app home's settings, minus the recording machine's Bible folder.
cat > "$stowed/config.json" <<'JSON'
{
  "book_order": "bible",
  "nerd_font": true,
  "show_clock": false,
  "yank_format": "{text}\n\n  ~ {reference} {version}"
}
JSON
rm -f "$HOME/.config/bible-tui/config.json"
ln -s ../../dotfiles/bible-tui/.config/bible-tui/config.json "$HOME/.config/bible-tui/config.json"

git -C "$HOME/dotfiles" init -q
git -C "$HOME/dotfiles" add .
git -C "$HOME/dotfiles" -c user.name=demo -c user.email=demo@example.com commit -qm "Add bible-tui config"
