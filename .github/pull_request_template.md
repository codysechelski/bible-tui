## What changed and why

<!-- Link the issue this fixes, if there is one: "Fixes #123". -->

## Checklist

- [ ] The PR title follows [Conventional Commits](https://www.conventionalcommits.org/) (`fix:`, `feat:`, `docs:`, ...)
- [ ] `python3 -m py_compile bible_tui/*.py tests/*.py` and `python3 -m unittest discover -s tests -t .` pass
- [ ] Tests added or updated for the change
- [ ] Tried in a real terminal with `./bible-tui` (for anything you can see in the app)
- [ ] Docs updated (`docs/`, README) if behaviour or key bindings changed
- [ ] New actions have a non-Vim key (arrows, Tab, Enter, Esc, ...)
- [ ] Standard library only, and still works on Python 3.9
