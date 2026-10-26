# Contributing to bible-tui

Thanks for your interest in bible-tui! Bug reports, ideas, documentation fixes, and code are all welcome.

Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md). To report a security
problem, please follow the [security policy](SECURITY.md) instead of opening a public issue.

## Reporting bugs and asking for features

Please [open an issue](https://github.com/codysechelski/bible-tui/issues/new/choose) first. The issue forms ask
for what's needed. For a bug, that's:

- what you did, what you expected, and what happened instead
- your operating system, terminal, and Python version (`python3 --version`)
- your bible-tui version (`:about` inside the app shows it)
- any error message, and `./bible-tui --list-versions` output if a Bible didn't load

For a new feature, please describe it in an issue before you start work, so we can agree on the approach. The
[roadmap](ROADMAP.md) lists what's already planned.

## Getting set up

bible-tui uses only the Python standard library, so there's nothing to install. You need Python 3.9 or newer.

```sh
git clone https://github.com/codysechelski/bible-tui.git
cd bible-tui
./bible-tui
```

## Making a change

1. Fork the repository and create a branch from `main`.
2. Make your change, and add or update tests in `tests/`.
3. Run the checks:

   ```sh
   python3 -m py_compile bible_tui/*.py tests/*.py
   python3 -m unittest discover -s tests -t .
   ```

4. For anything you can see in the app, try it in a real terminal with `./bible-tui` as well.
5. Update the docs in `docs/` (and the README if needed) when behaviour or key bindings change.
6. Open a pull request that explains what changed and why.

## Guidelines

- **Standard library only.** No third-party packages, and nothing that shells out to other tools (like `fzf`)
  for core features. Code must keep working on Python 3.9, and every module starts with
  `from __future__ import annotations`.
- **No version is special.** Never hardcode a Bible version's name, abbreviation, or file name. Version names
  come from each database's metadata.
- **Bibles are read-only.** The app never writes to a Bible database. Don't edit the bundled databases in
  `bible_tui/bibles/` by hand; they come from the
  [converter project](docs/adding-bibles.md).
- **Keep user data safe.** If a file like `marks.json` fails to load, refuse to save rather than overwrite it.
- **Every action needs a non-Vim key.** Arrows, Tab, Page Up/Down, Home/End, Enter, and Esc must reach every
  action. Vim-style keys are welcome as extra aliases, never as the only way.
- **Screenshots** may only show the bundled versions or other openly licensed ones.

[AGENTS.md](AGENTS.md) has a fuller map of the code and its conventions.

## Commit messages

Releases are automatic, and the commit messages decide the next version, so please use
[Conventional Commits](https://www.conventionalcommits.org/):

- `fix: ...` for a bug fix (patch release)
- `feat: ...` for a new feature (minor release)
- `docs:`, `test:`, `refactor:`, `ci:`, `chore:` for changes that don't need a release

Pull requests are squash-merged, and the **PR title** becomes the commit message, so the title is what needs
this format (a check on the PR will tell you if it doesn't). Commit messages inside your branch can be anything.

Don't change `__version__`, `CHANGELOG.md`, or release tags yourself; the release workflow handles them.

## Translations

Translating the app's menus and help text is planned (see the [roadmap](ROADMAP.md#translations)). If you'd
like to help with a language, please open a
[translation offer](https://github.com/codysechelski/bible-tui/issues/new?template=translation.yml).

## Licence

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
