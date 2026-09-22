"""TypeScript LanguageProfile.

Same anchoring discipline as the Python profile: patterns must look like
definitions, not casual prose mentions.
"""

from __future__ import annotations

import re

from irminsul.languages.base import LanguageProfile

TYPESCRIPT_PROFILE = LanguageProfile(
    name="typescript",
    fence_labels=("typescript", "ts", "tsx", "javascript", "js"),
    source_root_candidates=("src", "lib"),
    test_patterns=("*.test.ts", "*.spec.ts", "*.test.tsx", "*.spec.tsx", "*.test.js", "*.spec.js"),
    schema_leak_patterns=(
        re.compile(r"^\s*(export\s+)?interface\s+\w+\s*(extends\s+[\w,\s]+)?\s*\{"),
        re.compile(r"^\s*(export\s+)?type\s+\w+\s*="),
        re.compile(r"^\s*(export\s+)?enum\s+\w+\s*\{"),
    ),
)
