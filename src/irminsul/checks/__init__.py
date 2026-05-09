"""Check registry.

Looking-up by name keeps the CLI/config side honest: `irminsul.toml`'s
`checks.hard` (and `soft_deterministic`, `soft_llm`) are just lists of strings,
and we resolve them here.
"""

from __future__ import annotations

from irminsul.checks.base import Check, Finding, Fix, Severity, sort_findings, summarize
from irminsul.checks.boundary import BoundaryCheck
from irminsul.checks.coverage import CoverageCheck
from irminsul.checks.dependency_check import DependencyCheck
from irminsul.checks.env_check import EnvCheck
from irminsul.checks.external_links import ExternalLinksCheck
from irminsul.checks.frontmatter import FrontmatterCheck
from irminsul.checks.globs import GlobsCheck
from irminsul.checks.glossary import GlossaryCheck
from irminsul.checks.liar import LiarCheck
from irminsul.checks.links import LinksCheck
from irminsul.checks.mtime_drift import MtimeDriftCheck
from irminsul.checks.orphans import OrphansCheck
from irminsul.checks.overlap import OverlapCheck
from irminsul.checks.parent_child import ParentChildCheck
from irminsul.checks.phantom_layer import PhantomLayerCheck
from irminsul.checks.reality import RealityCheck
from irminsul.checks.schema_leak import SchemaLeakCheck
from irminsul.checks.scope_appropriateness import ScopeAppropriatenessCheck
from irminsul.checks.semantic_drift import SemanticDriftCheck
from irminsul.checks.stale_reaper import StaleReaperCheck
from irminsul.checks.supersession import SupersessionCheck
from irminsul.checks.uniqueness import UniquenessCheck

HARD_REGISTRY: dict[str, type[Check]] = {
    FrontmatterCheck.name: FrontmatterCheck,
    GlobsCheck.name: GlobsCheck,
    UniquenessCheck.name: UniquenessCheck,
    LinksCheck.name: LinksCheck,
    SchemaLeakCheck.name: SchemaLeakCheck,
    CoverageCheck.name: CoverageCheck,
    LiarCheck.name: LiarCheck,
}

SOFT_REGISTRY: dict[str, type[Check]] = {
    MtimeDriftCheck.name: MtimeDriftCheck,
    OrphansCheck.name: OrphansCheck,
    StaleReaperCheck.name: StaleReaperCheck,
    SupersessionCheck.name: SupersessionCheck,
    ParentChildCheck.name: ParentChildCheck,
    GlossaryCheck.name: GlossaryCheck,
    ExternalLinksCheck.name: ExternalLinksCheck,
    RealityCheck.name: RealityCheck,
    BoundaryCheck.name: BoundaryCheck,
    PhantomLayerCheck.name: PhantomLayerCheck,
    EnvCheck.name: EnvCheck,
    DependencyCheck.name: DependencyCheck,
}

LLM_REGISTRY: dict[str, type] = {
    OverlapCheck.name: OverlapCheck,
    SemanticDriftCheck.name: SemanticDriftCheck,
    ScopeAppropriatenessCheck.name: ScopeAppropriatenessCheck,
}

__all__ = [
    "HARD_REGISTRY",
    "LLM_REGISTRY",
    "SOFT_REGISTRY",
    "BoundaryCheck",
    "Check",
    "CoverageCheck",
    "DependencyCheck",
    "EnvCheck",
    "Finding",
    "Fix",
    "LiarCheck",
    "OverlapCheck",
    "PhantomLayerCheck",
    "RealityCheck",
    "ScopeAppropriatenessCheck",
    "SemanticDriftCheck",
    "Severity",
    "sort_findings",
    "summarize",
]
