"""Python LanguageProfile.

Schema-leak patterns target what Part VIII of `Irminsul-reference.md` calls
out: class definitions for Pydantic / SQLAlchemy / Protocol bases, dataclass
decorators, and SQL DDL. All patterns are anchored at start-of-line (with
leading whitespace allowed) so prose mentions don't trigger findings.
"""

from __future__ import annotations

import re

from irminsul.languages.base import LanguageProfile

PYTHON_PROFILE = LanguageProfile(
    name="python",
    source_root_candidates=("src", "app", "lib"),
    schema_leak_patterns=(
        re.compile(r"^\s*class\s+\w+\s*\(\s*BaseModel\s*\)"),
        re.compile(r"^\s*class\s+\w+\s*\([^)]*Base[^)]*\)"),
        re.compile(r"^\s*class\s+\w+\s*\(\s*Protocol\s*\)"),
        re.compile(r"^\s*@dataclass(\(.*\))?\s*$"),
        re.compile(r"^\s*CREATE\s+(TABLE|TYPE|VIEW)\b", re.IGNORECASE),
    ),
)
