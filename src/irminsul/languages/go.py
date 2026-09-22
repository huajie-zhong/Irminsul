"""Go LanguageProfile.

Schema-leak patterns target struct/interface declarations and SQL DDL — the
shapes that signal "type definition" and belong in code (derivable via
`irminsul surface`) rather than narrative component docs. All patterns are
anchored at start-of-line so prose
mentions ("the User struct holds…") don't trigger findings.
"""

from __future__ import annotations

import re

from irminsul.languages.base import LanguageProfile

GO_PROFILE = LanguageProfile(
    name="go",
    fence_labels=("go",),
    source_root_candidates=("internal", "pkg", "cmd", "."),
    # Go colocates a test with the package it covers, so this is the only
    # thing that tells `parser_test.go` apart from `parser.go`.
    test_patterns=("*_test.go",),
    schema_leak_patterns=(
        re.compile(r"^\s*type\s+\w+\s+struct\s*\{"),
        re.compile(r"^\s*type\s+\w+\s+interface\s*\{"),
        re.compile(r"^\s*func\s+\([^)]*\)\s+\w+"),
        re.compile(r"^\s*CREATE\s+(TABLE|TYPE|VIEW)\b", re.IGNORECASE),
    ),
)
