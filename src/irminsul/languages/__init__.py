"""Language-profile registry.

Looking up by name keeps the toml side honest: `[languages] enabled = ["python",
"typescript"]` resolves through here, and unknown names are skipped.
"""

from __future__ import annotations

from irminsul.languages.base import LanguageProfile
from irminsul.languages.python import PYTHON_PROFILE
from irminsul.languages.typescript import TYPESCRIPT_PROFILE

LANGUAGE_REGISTRY: dict[str, LanguageProfile] = {
    PYTHON_PROFILE.name: PYTHON_PROFILE,
    TYPESCRIPT_PROFILE.name: TYPESCRIPT_PROFILE,
}

__all__ = [
    "LANGUAGE_REGISTRY",
    "PYTHON_PROFILE",
    "TYPESCRIPT_PROFILE",
    "LanguageProfile",
]
