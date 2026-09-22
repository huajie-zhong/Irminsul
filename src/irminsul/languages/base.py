"""LanguageProfile dataclass.

Profiles are pure data — a name, a tuple of source-root directory candidates
(used by `irminsul init`'s detector in Week 4), and a tuple of compiled
schema-leak patterns. New languages are added by creating a profile and
registering it in `irminsul.languages.__init__`; nothing in the core checks
needs to change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class LanguageProfile:
    name: str
    source_root_candidates: tuple[str, ...]
    schema_leak_patterns: tuple[re.Pattern[str], ...]
    fence_labels: tuple[str, ...] = ()
    """Code-fence labels whose blocks `schema-leak` scans with this profile's patterns."""
    test_patterns: tuple[str, ...] = ()
    """Gitignore-style patterns naming this language's test implementation files.

    What makes a file a test is a language convention, not something a document may
    assert. Test ownership is only allowed over files this recognises, so naming an
    ordinary source file as a test cannot become a way around `describes:` ownership.
    Empty where the language has no filename convention — Rust keeps unit tests inside
    the module they cover, and no pattern can see that.
    """
