"""Shared pytest fixtures."""

from __future__ import annotations

import shutil
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from git import Repo

FIXTURE_REPOS_DIR = Path(__file__).parent / "fixtures" / "repos"


@contextmanager
def open_repo(root: Path) -> Iterator[Repo]:
    """A `git.Repo` handle that is always released.

    A handle a test forgets keeps a git process and its pipes alive until the garbage
    collector reaches it, and the collection that reaches it is usually the `gc.collect()`
    inside some *later* `Repo.close()`. The ResourceWarning then surfaces during an
    unrelated test, which `filterwarnings = ["error"]` fails. Coverage shifts collection
    timing, which is why the symptom only appeared under `--cov`.
    """
    repo = Repo(root)
    try:
        yield repo
    finally:
        repo.close()


def seed_repo(root: Path, message: str = "seed") -> str:
    """Init a git repo at `root`, commit everything already in it, and return the sha.

    Returns the sha rather than the handle, so there is nothing for a caller to leak.
    Reach for `open_repo` when a test needs the repo afterwards.
    """
    repo = Repo.init(root)
    try:
        with repo.config_writer() as cw:
            cw.set_value("user", "name", "Test")
            cw.set_value("user", "email", "test@example.com")
        repo.git.add("-A")
        return repo.index.commit(message).hexsha
    finally:
        repo.close()


@pytest.fixture(autouse=True)
def _isolate_change_baseline_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """CI exports GITHUB_BASE_REF for PR builds; the change-baseline resolver
    would try that ref inside fixture repos (where it never resolves) instead
    of falling back to the local working tree. Tests always run env-clean."""
    monkeypatch.delenv("IRMINSUL_BASE_REF", raising=False)
    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)


@pytest.fixture
def fixture_repo(tmp_path: Path) -> Callable[[str], Path]:
    """Copy a fixture repo into `tmp_path` and return the destination root.

    Tests can mutate the copy freely without polluting the source tree.
    """

    def _copy(name: str) -> Path:
        src = FIXTURE_REPOS_DIR / name
        if not src.exists():
            raise FileNotFoundError(f"unknown fixture repo: {name} (looked in {src})")
        dst = tmp_path / name
        shutil.copytree(src, dst)
        return dst

    return _copy


@pytest.fixture
def aged_deprecated_repo(tmp_path: Path) -> Path:
    """A git repo whose one deprecated doc was committed in 2020, so it is past the
    stale-reaper threshold: a time finding on any day the tests run."""
    import os
    import subprocess

    root = tmp_path / "aged"
    (root / "docs" / "components").mkdir(parents=True)
    (root / "docs" / "components" / "widget.md").write_text(
        "---\nid: widget\ntitle: Widget\nstatus: deprecated\n---\n\n# Widget\n",
        encoding="utf-8",
    )
    (root / "irminsul.toml").write_text(
        'project_name = "aged"\n[paths]\ndocs_root = "docs"\nsource_roots = []\n'
        '[checks]\nenabled = ["frontmatter", "stale-reaper"]\n',
        encoding="utf-8",
    )
    date = "2020-01-01T12:00:00"
    env = {**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    for args in (
        ["init", "-q"],
        ["add", "-A"],
        ["-c", "user.name=T", "-c", "user.email=t@e.com", "commit", "-qm", "init"],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, env=env)
    return root


def cli_output(result: object) -> str:
    """Everything a CLI invocation printed, on either stream.

    Click 8.1 merged stderr into `stdout` for the test runner and 8.2 separated them, so
    a test that asserts on an error message has to read both or it passes on one Click
    and fails on the next.
    """
    out = getattr(result, "output", "") or ""
    try:
        err = result.stderr or ""  # type: ignore[attr-defined]
    except ValueError:
        err = ""  # Click 8.1 with mix_stderr=True: already part of `output`.
    return out if err in out else out + err
