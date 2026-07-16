"""Content seals for implemented RFC records."""

from __future__ import annotations

import hashlib
import re

from ruamel.yaml.scalarstring import DoubleQuotedScalarString

from irminsul.frontmatter_edit import set_value

_PLACEHOLDER = f"sha256:{'0' * 64}"
_FROZEN_HASH_LINE = re.compile(r"^frozen_hash:[^\n]*(?:\n|$)", re.MULTILINE)


def compute_frozen_hash(text: str) -> str:
    """Hash the complete normalized RFC, excluding the self-referential seal line."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    canonical = _FROZEN_HASH_LINE.sub("", normalized, count=1)
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def seal_text(text: str) -> str:
    """Canonicalize frontmatter and write the seal calculated over the resulting file."""
    prepared = set_value(text, "frozen_hash", DoubleQuotedScalarString(_PLACEHOLDER))
    digest = DoubleQuotedScalarString(compute_frozen_hash(prepared))
    return set_value(prepared, "frozen_hash", digest)
