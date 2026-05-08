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
