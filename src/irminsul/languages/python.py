"""Python LanguageProfile.

Schema-leak patterns target class definitions for Pydantic / SQLAlchemy / Protocol
bases, dataclass decorators, and SQL DDL. All patterns are anchored at start-of-line (with
leading whitespace allowed) so prose mentions don't trigger findings.
"""

from __future__ import annotations

import re

from irminsul.languages.base import LanguageProfile

PYTHON_PROFILE = LanguageProfile(
    name="python",
    fence_labels=("python", "py"),
    suffixes=(".py",),
    markers=("pyproject.toml", "setup.py", "setup.cfg", "requirements*.txt"),
    source_root_candidates=("src", "app", "lib"),
    test_patterns=("test_*.py", "*_test.py", "conftest.py"),
    schema_leak_patterns=(
        re.compile(r"^\s*class\s+\w+\s*\(\s*BaseModel\s*\)"),
        re.compile(r"^\s*class\s+\w+\s*\([^)]*Base[^)]*\)"),
        re.compile(r"^\s*class\s+\w+\s*\(\s*Protocol\s*\)"),
        re.compile(r"^\s*@dataclass(\(.*\))?\s*$"),
        re.compile(r"^\s*CREATE\s+(TABLE|TYPE|VIEW)\b", re.IGNORECASE),
    ),
)
