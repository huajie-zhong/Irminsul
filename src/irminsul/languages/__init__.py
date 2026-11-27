"""Language-profile registry, and the readers profiles name.

Looking up by name keeps the toml side honest: `[languages] enabled = ["python",
"typescript"]` resolves through here, and config validation rejects a name not in the
registry.
"""

from __future__ import annotations

from pathlib import PurePath, PurePosixPath

from irminsul.languages.base import LanguageProfile
from irminsul.languages.go import GO_PROFILE
from irminsul.languages.python import PYTHON_PROFILE
from irminsul.languages.python_reader import PYTHON_READER
from irminsul.languages.reader import CodeReader
from irminsul.languages.rust import RUST_PROFILE
from irminsul.languages.typescript import TYPESCRIPT_PROFILE

LANGUAGE_REGISTRY: dict[str, LanguageProfile] = {
    PYTHON_PROFILE.name: PYTHON_PROFILE,
    TYPESCRIPT_PROFILE.name: TYPESCRIPT_PROFILE,
    GO_PROFILE.name: GO_PROFILE,
    RUST_PROFILE.name: RUST_PROFILE,
}

READERS: dict[str, CodeReader] = {"python": PYTHON_READER}
"""Each reader by the name a profile's `reader` gives it."""


def reader_for(path: str | PurePath) -> CodeReader | None:
    """The reader of the language whose profile lists the suffix of `path`, a display path or
    a filesystem one, or None when no profile with a reader lists it.

    Every profile is asked, whether or not `languages.enabled` names its language: a file's
    suffix says what it holds, and the features that read code read Python in every project."""
    suffix = path.suffix if isinstance(path, PurePath) else PurePosixPath(path).suffix
    for profile in LANGUAGE_REGISTRY.values():
        if profile.reader is not None and suffix in profile.suffixes:
            return READERS[profile.reader]
    return None


def languages_read() -> list[str]:
    """The names of the languages whose profile names a reader, in registry order."""
    return [name for name, profile in LANGUAGE_REGISTRY.items() if profile.reader is not None]


__all__ = [
    "GO_PROFILE",
    "LANGUAGE_REGISTRY",
    "PYTHON_PROFILE",
    "READERS",
    "RUST_PROFILE",
    "TYPESCRIPT_PROFILE",
    "LanguageProfile",
    "languages_read",
    "reader_for",
]
