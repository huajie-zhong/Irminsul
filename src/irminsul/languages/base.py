"""LanguageProfile dataclass.

Profiles are pure data, and each field says what reads it. New languages are added by
creating a profile and registering it in `irminsul.languages`; nothing in the core checks
needs to change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class LanguageProfile:
    name: str
    """The registry key, and what `[languages] enabled` names."""
    source_root_candidates: tuple[str, ...]
    """Directories the init detector keeps, when they exist, as `paths.source_roots`."""
    schema_leak_patterns: tuple[re.Pattern[str], ...]
    """What `schema-leak` matches line by line in a doc. Each is anchored at the start of a
    line, leading whitespace allowed, so a casual mention does not trigger it: only a line
    that looks like a definition matches."""
    fence_labels: tuple[str, ...] = ()
    """Code-fence labels whose blocks `schema-leak` scans with this profile's patterns."""
    suffixes: tuple[str, ...] = ()
    """File suffixes, with the dot, that mark a file as this language's source.

    The one list of them: every extractor and gate that reads this language's files reads it.
    """
    markers: tuple[str, ...] = ()
    """File names, or globs, at the root of a repository that show it holds this language."""
    confirmed_by: tuple[str, ...] = ()
    """Globs, from the repository root down, of which one must match before a marker names this
    language rather than only code.

    Empty where a marker is the language's alone. `package.json` is every JavaScript project's,
    so TypeScript asks for a `tsconfig.json` or a `.ts` file beside it."""
    test_patterns: tuple[str, ...] = ()
    """Gitignore-style patterns naming this language's test implementation files.

    What makes a file a test is a language convention, not something a document may
    assert. Test ownership is only allowed over files this recognises, so naming an
    ordinary source file as a test cannot become a way around `describes:` ownership.
    Empty where the language has no filename convention — Rust keeps unit tests inside
    the module they cover, and no pattern can see that.
    """
