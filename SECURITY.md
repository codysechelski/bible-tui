# Security Policy

## Supported versions

Only the latest release gets security fixes. Please update (`:update` inside the app) before reporting, and check
that the problem still happens.

## Reporting a vulnerability

Please **don't** report security problems in a public issue. Use GitHub's private reporting instead:
[Report a vulnerability](https://github.com/codysechelski/bible-tui/security/advisories/new).

Include what you found, how to reproduce it, and the bible-tui version (`:about` shows it). You should get a
reply within a week. Once the problem is confirmed, a fix will be released as soon as possible, and you'll be
credited in the advisory unless you'd rather not be.

## Scope

bible-tui is a local terminal app, but a few parts are worth a close look:

- **The update check.** Once a day it asks the GitHub API for the latest release. This is the only network
  access, and it can be turned off with `"check_for_updates": false`.
- **`:update`.** It runs `pipx install --force` or `git pull --ff-only` to install a new release, then restarts the app.
- **Bible databases.** Databases from any source can be added to a Bible folder. They are opened read-only,
  and a malformed one should be skipped, never crash the app or cause harm.
- **Settings and data files** in the app home (`config.json`, `state.json`, `marks.json`, `highlights.json`).
- **Clipboard and links.** Copying runs a clipboard tool (`pbcopy`, `wl-copy`, `xclip`, `xsel`, or `clip.exe`),
  and the About modal opens the project link with `open`, `xdg-open`, or `wslview`.
