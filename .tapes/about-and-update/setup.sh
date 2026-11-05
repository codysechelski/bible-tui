#!/usr/bin/env bash
# Runs inside the sandbox (../sandbox about-and-update ./setup.sh): fakes a newer release, so :update has
# something real to do without the network or this repo.
#
# ~/release is a git repo with two commits of this working copy: an "older" one and the current one.
# ~/bible-tui is a clone of it, one commit behind, and `bible-tui` runs that clone. state.json says the
# newer version came out at the last update check (just now, so no check runs), so the app announces it,
# and :update's `git pull --ff-only` really fast-forwards the clone, then restarts at the same verse.
set -euo pipefail

repo="$(cd "$(dirname "$0")/../.." && pwd)"
current="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$repo/bible_tui/__init__.py")"
# One release back: the patch number down one, or the minor number when the patch is 0.
IFS=. read -r major minor patch <<<"$current"
if (( patch > 0 )); then older="$major.$minor.$((patch - 1))"; else older="$major.$((minor > 0 ? minor - 1 : 0)).0"; fi

git_demo() { git -c user.name=demo -c user.email=demo@example.com -c init.defaultBranch=main "$@"; }
release="$HOME/release"
mkdir -p "$release"
cp -R "$repo/bible_tui" "$repo/bible-tui" "$repo/pyproject.toml" "$release/"
find "$release" -name __pycache__ -prune -exec rm -rf {} +
sed -i '' "s/^__version__ = .*/__version__ = \"$older\"/" "$release/bible_tui/__init__.py"
git_demo -C "$release" init -q
git_demo -C "$release" add .
git_demo -C "$release" commit -qm "chore(release): $older"
sed -i '' "s/^__version__ = .*/__version__ = \"$current\"/" "$release/bible_tui/__init__.py"
git_demo -C "$release" commit -qam "chore(release): $current"

git_demo clone -q "$release" "$HOME/bible-tui"
git -C "$HOME/bible-tui" reset -q --hard HEAD~1
# A script, not a link: the launcher finds the package from its own path.
rm -f "$HOME/bin/bible-tui"
printf '#!/bin/sh\nexec "%s" "$@"\n' "$HOME/bible-tui/bible-tui" > "$HOME/bin/bible-tui"
chmod +x "$HOME/bin/bible-tui"

printf '{\n  "last_version": "ASV",\n  "last_update_check": %s,\n  "latest_version": "%s"\n}\n' \
  "$(date +%s)" "$current" > "$HOME/.config/bible-tui/state.json"
