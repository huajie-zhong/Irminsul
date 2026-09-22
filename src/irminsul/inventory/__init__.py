"""Surface-extractor registry.

Kinds come from the always-on core extractors, the enabled framework packs, and the
generic rules in `irminsul.toml`; see `irminsul.inventory.packs`.
"""

from __future__ import annotations

from irminsul.inventory.base import Extractor, SurfaceItem
from irminsul.inventory.packs import (
    BUILTIN_CAPABILITIES,
    CORE_EXTRACTORS,
    PACKS,
    KindCapabilities,
    available_kinds,
    get_extractor,
    kind_capabilities,
)

KNOWN_KINDS = tuple(
    sorted(
        {extractor.kind for extractor in CORE_EXTRACTORS}
        | {extractor.kind for pack in PACKS.values() for extractor in pack.extractors}
        | {rule.kind for pack in PACKS.values() for rule in pack.rules}
    )
)
KNOWN_KINDS_TEXT = ", ".join(KNOWN_KINDS)

__all__ = [
    "BUILTIN_CAPABILITIES",
    "KNOWN_KINDS",
    "KNOWN_KINDS_TEXT",
    "PACKS",
    "Extractor",
    "KindCapabilities",
    "SurfaceItem",
    "available_kinds",
    "get_extractor",
    "kind_capabilities",
]
