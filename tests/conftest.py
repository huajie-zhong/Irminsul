"""Shared pytest fixtures."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

FIXTURE_REPOS_DIR = Path(__file__).parent / "fixtures" / "repos"


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
