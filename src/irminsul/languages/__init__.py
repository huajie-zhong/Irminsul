"""Language-profile registry, and the readers profiles name.

Looking up by name keeps the toml side honest: `[languages] enabled = ["python",
"typescript"]` resolves through here, and config validation rejects a name not in the
registry.
"""

from __future__ import annotations

from pathlib import PurePath, PurePosixPath

from irminsul.languages.base import LanguageProfile
from irminsul.languages.go import GO_PROFILE
from irminsul.languages.go_reader import GO_READER
from irminsul.languages.python import PYTHON_PROFILE
from irminsul.languages.python_reader import PYTHON_READER
from irminsul.languages.reader import CodeReader
from irminsul.languages.rust import RUST_PROFILE
from irminsul.languages.rust_reader import RUST_READER
from irminsul.languages.typescript import TYPESCRIPT_PROFILE
from irminsul.languages.typescript_reader import TSX_READER, TYPESCRIPT_READER

LANGUAGE_REGISTRY: dict[str, LanguageProfile] = {
    PYTHON_PROFILE.name: PYTHON_PROFILE,
    TYPESCRIPT_PROFILE.name: TYPESCRIPT_PROFILE,
    GO_PROFILE.name: GO_PROFILE,
    RUST_PROFILE.name: RUST_PROFILE,
}

READERS: dict[str, CodeReader] = {
    "python": PYTHON_READER,
    "typescript": TYPESCRIPT_READER,
    "tsx": TSX_READER,
    "go": GO_READER,
    "rust": RUST_READER,
}
"""Each reader by the name a profile's `reader` or `suffix_readers` gives it."""


def _read(path: str | PurePath) -> tuple[LanguageProfile, CodeReader] | None:
    suffix = path.suffix if isinstance(path, PurePath) else PurePosixPath(path).suffix
    for profile in LANGUAGE_REGISTRY.values():
        if profile.reader is not None and suffix in profile.suffixes:
            return profile, READERS[dict(profile.suffix_readers).get(suffix, profile.reader)]
    return None


def reader_for(path: str | PurePath) -> CodeReader | None:
    """The reader of the language whose profile lists the suffix of `path`, a display path or
    a filesystem one, or None when no profile with a reader lists it.

    Every profile is asked, whether or not `languages.enabled` names its language: a file's
    suffix says what it holds, and the features that read code read it in every project."""
    found = _read(path)
    return None if found is None else found[1]


def language_read(path: str | PurePath) -> str | None:
    """The name of the language a reader reads the file `path` as, or None when no profile
    with a reader lists its suffix. Two files of one language can import each other,
    whichever dialect's reader reads each."""
    found = _read(path)
    return None if found is None else found[0].name


def places_every_import(language: str) -> bool:
    """Whether the reader of `language` places every import of it."""
    reader = LANGUAGE_REGISTRY[language].reader
    return reader is not None and READERS[reader].places_every_import


def languages_placing_every_import() -> list[str]:
    """The names of the languages whose reader places every import, in registry order."""
    return [name for name in LANGUAGE_REGISTRY if places_every_import(name)]


__all__ = [
    "GO_PROFILE",
    "LANGUAGE_REGISTRY",
    "PYTHON_PROFILE",
    "READERS",
    "RUST_PROFILE",
    "TYPESCRIPT_PROFILE",
    "LanguageProfile",
    "language_read",
    "languages_placing_every_import",
    "places_every_import",
    "reader_for",
]
