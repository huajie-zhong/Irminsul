"""Auto-detect languages and source roots for `irminsul init`.

Cheap heuristics: presence of well-known marker files. We deliberately don't
parse anything; existence checks are fast and resilient to weird repo shapes.
"""

from __future__ import annotations

from pathlib import Path

from irminsul.languages import LANGUAGE_REGISTRY


def detect_languages(repo_root: Path) -> list[str]:
    """Return language names that appear active in this repo.

    Order: python first, typescript second. Names align with
    `irminsul.languages.LANGUAGE_REGISTRY` keys.
    """
    detected: list[str] = []

    if _has_python_signals(repo_root):
        detected.append("python")
    if _has_typescript_signals(repo_root):
        detected.append("typescript")

    return detected


def detect_source_roots(repo_root: Path, languages: list[str]) -> list[str]:
    """Pick source-root directories that exist on disk for the given languages.

    Falls back to `["src"]` if nothing matches — avoids producing an empty list
    that would silently disable the globs/uniqueness checks.
    """
    candidates: list[str] = []
    for lang in languages:
        profile = LANGUAGE_REGISTRY.get(lang)
        if profile is None:
            continue
        for root in profile.source_root_candidates:
            if root in candidates:
                continue
            if (repo_root / root).is_dir():
                candidates.append(root)

    return candidates or ["src"]


def _has_python_signals(repo_root: Path) -> bool:
    if (repo_root / "pyproject.toml").is_file():
        return True
    if (repo_root / "setup.py").is_file():
        return True
    if (repo_root / "setup.cfg").is_file():
        return True
    return any(repo_root.glob("requirements*.txt"))


def _has_typescript_signals(repo_root: Path) -> bool:
    if not (repo_root / "package.json").is_file():
        return False
    if (repo_root / "tsconfig.json").is_file():
        return True
    return any(repo_root.rglob("*.ts"))
