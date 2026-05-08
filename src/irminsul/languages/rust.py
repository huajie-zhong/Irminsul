"""Rust LanguageProfile.

Schema-leak patterns target struct/enum/trait definitions and impl blocks.
Anchored at start-of-line; the optional `pub` prefix is captured. Patterns
match both struct-with-body (`struct X {`) and tuple structs / generics
(`struct X<T>`).
"""

from __future__ import annotations

import re

from irminsul.languages.base import LanguageProfile

RUST_PROFILE = LanguageProfile(
    name="rust",
    source_root_candidates=("src", "crates"),
    schema_leak_patterns=(
        re.compile(r"^\s*(pub\s+)?struct\s+\w+\s*[<{(]"),
        re.compile(r"^\s*(pub\s+)?enum\s+\w+\s*[<{]"),
        re.compile(r"^\s*(pub\s+)?trait\s+\w+\s*[<{:]"),
        re.compile(r"^\s*impl(\s*<[^>]+>)?\s+(\w+\s+for\s+)?\w+"),
    ),
)
