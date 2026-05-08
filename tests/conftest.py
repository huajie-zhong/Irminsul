"""Shared pytest fixtures."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

FIXTURE_REPOS_DIR = Path(__file__).parent / "fixtures" / "repos"


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
