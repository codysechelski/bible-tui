# Contributing to bible-tui

Thanks for your interest in bible-tui! Bug reports, ideas, documentation fixes, and code are all welcome.

Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md). To report a security
problem, please follow the [security policy](SECURITY.md) instead of opening a public issue.

## Christian identity and project scope

I created bible-tui as a Christian Bible-reading application, and I intend to maintain that identity as the project grows.

**Everyone is welcome to contribute.** You do not need to be Christian, share my beliefs, or profess any faith to report bugs, suggest improvements, or submit pull requests. I will evaluate contributions based on their content, quality, and fit with the project—not the contributor's religion, beliefs, or identity.

**Being welcome to contribute is not a promise that every change will be merged.** As the maintainer of this repository, I retain final discretion over what belongs in it. I will not approve features or content that undermine its purpose as a Christian Bible application or that I believe conflict with my Christian faith. For example, I will not merge functionality intended to add non-biblical religious or spiritual texts to the app's reading library. This is a boundary on the scope of this repository, not a judgment about the people proposing those changes.

Questions, respectful disagreement, and constructive discussion are welcome. I will aim to explain scope-based decisions clearly and respectfully, and I ask contributors to extend the same courtesy to others.

The [MIT License](LICENSE) still governs what others may do with their own copies or forks of the code. Contributors are free to exercise those rights; this policy only describes what I am willing to accept into **this repository**.

If you're unsure whether an idea fits, please [open a feature request](https://github.com/codysechelski/bible-tui/issues/new/choose) before investing time in implementation.

## Reporting bugs and asking for features

Please [open an issue](https://github.com/codysechelski/bible-tui/issues/new/choose) first. The issue forms ask
for what's needed. For a bug, that's:

- what you did, what you expected, and what happened instead
- your operating system, terminal, and Python version (`python3 --version`)
- your bible-tui version (`:about` inside the app shows it)
- any error message, and `./bible-tui --list-versions` output if a Bible didn't load

For a new feature, please describe it in an issue before you start work, so we can agree on the approach. The
[roadmap](ROADMAP.md) lists what's already planned.

For Vim-style navigation proposals, please read the [Vim-inspired navigation philosophy](docs/vim-inspired-navigation.md)\nbefore opening an issue or starting a pull request.\n\n## Getting set up

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
- **Only public-domain or openly licensed Bibles are bundled.** Pull requests that add a copyrighted
  translation can't be accepted. To read one you have the rights to, add it as your own database
  ([adding-bibles.md](docs/adding-bibles.md)).
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
