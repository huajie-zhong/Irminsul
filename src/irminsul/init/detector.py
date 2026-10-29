"""Auto-detect languages and source roots for `irminsul init`.

Cheap heuristics: presence of the marker files each language profile lists. We
deliberately don't parse anything; existence checks are fast and resilient to weird
repo shapes.
"""

from __future__ import annotations

from pathlib import Path

from irminsul.languages import LANGUAGE_REGISTRY, LanguageProfile


def detect_languages(repo_root: Path) -> list[str]:
    """Return language names that appear active in this repo.

    A language is active when one of its profile's `markers` sits at the root and, where the
    profile asks for it, so does something that `confirmed_by` names. Names align with
    `irminsul.languages.LANGUAGE_REGISTRY` keys, in registry order.
    """
    return [
        name
        for name, profile in LANGUAGE_REGISTRY.items()
        if has_marker(repo_root, profile) and _confirmed(repo_root, profile)
    ]


def has_marker(repo_root: Path, profile: LanguageProfile) -> bool:
    return any(path.is_file() for pattern in profile.markers for path in repo_root.glob(pattern))


def _confirmed(repo_root: Path, profile: LanguageProfile) -> bool:
    return not profile.confirmed_by or any(
        any(repo_root.glob(pattern)) for pattern in profile.confirmed_by
    )


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
