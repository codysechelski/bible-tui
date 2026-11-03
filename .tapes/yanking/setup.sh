#!/usr/bin/env bash
# Builds a throwaway HOME for the yanking recording, then attaches to its tmux session.
#
# nvim needs its own config for the notes pane, and with XDG_CONFIG_HOME pointed at the sandbox bible-tui
# reads its app home from there too: a copy of the clean one setup.tape made, plus a plain zsh prompt.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
sandbox="$(mktemp -d -t bible-tui-yanking)"
mkdir -p "$sandbox/.config/bible-tui" "$sandbox/.config/nvim"

# The app home, found the way bible-tui finds it. setup.tape has already reset it to the clean defaults
# (no yank_format, ASV open, no update check), so the sandbox starts from a copy of it.
if [[ -n "${BIBLE_TUI_HOME:-}" ]]; then
  app="$BIBLE_TUI_HOME"
elif [[ -d "$HOME/.bible-tui" ]]; then
  app="$HOME/.bible-tui"
else
  app="${XDG_CONFIG_HOME:-$HOME/.config}/bible-tui"
fi
cp "$app/config.json" "$app/state.json" "$sandbox/.config/bible-tui/"

# A private clipboard: bible-tui copies with pbcopy and nvim pastes with pbpaste, so these stand-ins
# (first on PATH) keep the demo's copies in a file. Otherwise anything copied on the Mac while the tape
# records lands in the paste, and the recording overwrites the real clipboard.
mkdir -p "$sandbox/bin"
cat > "$sandbox/bin/pbcopy" <<EOF
#!/bin/sh
cat > "$sandbox/.clipboard"
EOF
cat > "$sandbox/bin/pbpaste" <<EOF
#!/bin/sh
cat "$sandbox/.clipboard" 2>/dev/null
EOF
chmod +x "$sandbox/bin/pbcopy" "$sandbox/bin/pbpaste"

# Login shells run macOS's path_helper, which moves the system folders back in front, so put bin/ first
# again here.
cat > "$sandbox/.zshrc" <<'EOF'
PROMPT='%F{magenta}❯%f '
path=("$HOME/bin" $path)
EOF

cat > "$sandbox/.config/nvim/init.lua" <<'EOF'
vim.opt.clipboard = "unnamedplus" -- p pastes what bible-tui copied
vim.opt.wrap = true
vim.opt.linebreak = true          -- wrap between words
EOF

tmux -L vhs-yank kill-server 2>/dev/null || true
cd "$sandbox"
# Point every config/data location at the sandbox too: with XDG_CONFIG_HOME set, nvim and bible-tui
# would otherwise read (and nvim's plugin manager write) the real ones.
unset BIBLE_TUI_HOME ZDOTDIR XDG_DATA_DIRS XDG_CONFIG_DIRS
exec env HOME="$sandbox" PATH="$sandbox/bin:$PATH" \
  XDG_CONFIG_HOME="$sandbox/.config" XDG_DATA_HOME="$sandbox/.local/share" \
  XDG_STATE_HOME="$sandbox/.local/state" XDG_CACHE_HOME="$sandbox/.cache" \
  tmux -L vhs-yank -f "$here/tmux.conf" attach
