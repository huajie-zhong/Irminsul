"""Check registry.

Looking-up by name keeps the CLI/config side honest: `irminsul.toml`'s
`checks.hard` field is just a list of strings, and we resolve them here.
"""

from __future__ import annotations

from irminsul.checks.base import Check, Finding, Severity, sort_findings, summarize
from irminsul.checks.frontmatter import FrontmatterCheck
from irminsul.checks.globs import GlobsCheck
from irminsul.checks.links import LinksCheck
from irminsul.checks.schema_leak import SchemaLeakCheck
from irminsul.checks.uniqueness import UniquenessCheck

HARD_REGISTRY: dict[str, type[Check]] = {
    FrontmatterCheck.name: FrontmatterCheck,
    GlobsCheck.name: GlobsCheck,
    UniquenessCheck.name: UniquenessCheck,
    LinksCheck.name: LinksCheck,
    SchemaLeakCheck.name: SchemaLeakCheck,
}

__all__ = [
    "HARD_REGISTRY",
    "Check",
    "Finding",
    "Severity",
    "sort_findings",
    "summarize",
]
