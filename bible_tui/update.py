"""Checking GitHub for a newer release, and updating the install in place.

The check runs in a background thread at most once a day (``CHECK_INTERVAL_SECONDS``) and never delays
startup; any failure (offline, rate limited, a bad response) just means no notice. The thread only fetches.
The result is applied to ``state.json`` from the main thread when the TUI calls ``UpdateCheck.poll``.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import threading
import time
import urllib.request
from collections.abc import Callable, MutableMapping, Sequence
from dataclasses import dataclass
from pathlib import Path


REPOSITORY = "codysechelski/bible-tui"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
REPOSITORY_URL = f"https://github.com/{REPOSITORY}"
RELEASES_PAGE = f"{REPOSITORY_URL}/releases"
CHECK_INTERVAL_SECONDS = 24 * 60 * 60
FETCH_TIMEOUT_SECONDS = 5.0
PACKAGE_DIR = Path(__file__).resolve().parent

# state.json keys.
STATE_LAST_CHECK = "last_update_check"  # Unix time of the last successful check.
STATE_LATEST = "latest_version"  # The newest release seen then, without the leading "v".

# Set in the environment of the restarted process so it can say what changed and reopen where you were.
UPDATED_FROM_ENV = "BIBLE_TUI_UPDATED_FROM"
RESTORE_POSITION_ENV = "BIBLE_TUI_RESTORE_POSITION"  # "book sort order:chapter:verse"

_VERSION_RE = re.compile(r"v?(\d+(?:\.\d+)*)")


def parse_version(text: object) -> tuple[int, ...] | None:
    """``"v0.3.0"`` → ``(0, 3, 0)``. Anything else (pre-releases included) is ``None``."""
    if not isinstance(text, str):
        return None
    match = _VERSION_RE.fullmatch(text.strip())
    return tuple(int(part) for part in match.group(1).split(".")) if match else None


def is_newer(candidate: object, current: str) -> bool:
    new, old = parse_version(candidate), parse_version(current)
    return new is not None and old is not None and new > old


def fetch_latest_version(current: str, timeout: float = FETCH_TIMEOUT_SECONDS) -> str | None:
    """The latest published release's version, or ``None`` if it can't be found out."""
    request = urllib.request.Request(
        LATEST_RELEASE_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": f"bible-tui/{current}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.load(response)
    except Exception:  # Offline, DNS, TLS, HTTP errors, bad JSON: no notice.
        return None
    tag = data.get("tag_name") if isinstance(data, dict) else None
    return tag.strip().lstrip("v") if parse_version(tag) is not None else None


class UpdateCheck:
    """Finds out whether a newer release exists, using the answer cached in ``state`` for a day."""

    def __init__(
        self,
        current: str,
        state: MutableMapping[str, object],
        *,
        save: Callable[[], None] = lambda: None,
        fetch: Callable[[str], str | None] = fetch_latest_version,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.current = current
        self.state = state
        self.save = save
        self.fetch = fetch
        self.now = now
        self.latest: str | None = None  # Newest release known, once checked.
        self.thread: threading.Thread | None = None
        self.result: str | None = None
        self.reported = False

    def due(self) -> bool:
        last = self.state.get(STATE_LAST_CHECK)
        if not isinstance(last, (int, float)) or isinstance(last, bool):
            return True
        return not 0 <= self.now() - last < CHECK_INTERVAL_SECONDS

    def start(self) -> None:
        """Start a background check if the cached one is stale; otherwise use the cache."""
        if not self.due():
            cached = self.state.get(STATE_LATEST)
            self.latest = cached if parse_version(cached) is not None else None
            return
        self.thread = threading.Thread(target=self._run, name="bible-tui update check", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        self.result = self.fetch(self.current)

    @property
    def pending(self) -> bool:
        """True while a background check hasn't been collected by ``poll`` yet."""
        return self.thread is not None

    def poll(self) -> str | None:
        """Call from the main thread. Returns a newer version once, the first time it's known."""
        if self.thread is not None:
            if self.thread.is_alive():
                return None
            self.thread = None
            if self.result is not None:
                self.latest = self.result
                self.state[STATE_LAST_CHECK] = int(self.now())
                self.state[STATE_LATEST] = self.result
                try:
                    self.save()
                except OSError:
                    pass  # State is disposable; the check just runs again next launch.
        if self.reported or not self.update_available:
            return None
        self.reported = True
        return self.latest

    @property
    def update_available(self) -> bool:
        return is_newer(self.latest, self.current)


@dataclass(frozen=True)
class Install:
    """How this copy of bible-tui was installed, and the command that updates it."""

    kind: str  # "pipx" or "git"
    command: tuple[str, ...]

    @property
    def command_text(self) -> str:
        return " ".join(self.command)


MANUAL_UPDATE = f"pipx upgrade bible-tui, or git pull in your clone (releases: {RELEASES_PAGE})"


def detect_install(package_dir: Path = PACKAGE_DIR, prefix: str = sys.prefix) -> Install | None:
    """A pipx venv or a git clone can be updated in place; anything else gets ``None``."""
    venv = Path(prefix)
    pipx = shutil.which("pipx")
    metadata = venv / "pipx_metadata.json"
    if metadata.is_file() and pipx:
        if pinned_to_github_ref(metadata):
            # `pipx upgrade` would reinstall the same tag, so move it to the latest release.
            return Install("pipx", (pipx, "install", "--force", f"git+https://github.com/{REPOSITORY}"))
        return Install("pipx", (pipx, "upgrade", "bible-tui"))
    repo = package_dir.parent
    git = shutil.which("git")
    if (repo / ".git").exists() and (repo / "pyproject.toml").is_file() and git:
        return Install("git", (git, "-C", str(repo), "pull", "--ff-only"))
    return None


def pinned_to_github_ref(metadata: Path) -> bool:
    """Whether pipx installed from this repo at a fixed ref (``git+https://github.com/...@v0.1.0``)."""
    try:
        data = json.loads(metadata.read_text(encoding="utf-8"))
        spec = data["main_package"]["package_or_url"]
    except (OSError, ValueError, KeyError, TypeError):
        return False
    if not isinstance(spec, str) or f"github.com/{REPOSITORY}" not in spec:
        return False
    return "@" in spec.split(f"github.com/{REPOSITORY}", 1)[1]


def format_position(position: Sequence[int | None]) -> str:
    return ":".join(str(part) for part in position) if all(isinstance(part, int) for part in position) else ""


def parse_position(text: str | None) -> tuple[int, int, int] | None:
    parts = (text or "").split(":")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    book, chapter, verse = (int(part) for part in parts)
    return book, chapter, verse


def restart_command(args: Sequence[str]) -> list[str]:
    """Run the (now updated) package again with the same arguments."""
    return [sys.executable, "-m", "bible_tui", *args]
