"""Check registry.

Looking-up by name keeps the CLI/config side honest: `irminsul.toml`'s
`checks.enabled` is a list of strings, resolved here.
"""

from __future__ import annotations

from irminsul.checks.adr_structure import AdrStructureCheck
from irminsul.checks.agents_manifest import AgentsManifestCheck
from irminsul.checks.base import (
    Check,
    CheckFlag,
    Finding,
    FindingClass,
    FindingSource,
    Fix,
    Severity,
    finding_records,
    fix_commands,
    flags_of,
    sort_findings,
    summarize,
)
from irminsul.checks.boundary import BoundaryCheck
from irminsul.checks.change_binding import ChangeBindingCheck
from irminsul.checks.claim_anchor import ClaimAnchorCheck
from irminsul.checks.claim_provenance import ClaimProvenanceCheck
from irminsul.checks.code_references import CodeReferencesCheck
from irminsul.checks.coverage import CoverageCheck
from irminsul.checks.dependency_check import DependencyCheck
from irminsul.checks.doc_refs import DocRefsCheck
from irminsul.checks.duplicate_block import DuplicateBlockCheck
from irminsul.checks.external_links import ExternalLinksCheck
from irminsul.checks.foundation_readiness import FoundationReadinessCheck
from irminsul.checks.frontmatter import FrontmatterCheck
from irminsul.checks.globs import GlobsCheck
from irminsul.checks.glossary import GlossaryDisciplineCheck
from irminsul.checks.inventory_drift import InventoryDriftCheck
from irminsul.checks.links import LinksCheck
from irminsul.checks.mtime_drift import MtimeDriftCheck
from irminsul.checks.orphans import OrphansCheck
from irminsul.checks.owned_tests import TestOwnershipCheck
from irminsul.checks.parent_child import ParentChildCheck
from irminsul.checks.phantom_layer import PhantomLayerCheck
from irminsul.checks.prose_file_reference import ProseFileReferenceCheck
from irminsul.checks.requirement_grammar import RequirementGrammarCheck
from irminsul.checks.retired_references import RetiredReferencesCheck
from irminsul.checks.rfc_follow_through import RfcFollowThroughCheck
from irminsul.checks.rfc_lifecycle import RfcLifecycleCheck
from irminsul.checks.rfc_structure import RfcStructureCheck
from irminsul.checks.schema_leak import SchemaLeakCheck
from irminsul.checks.stale_reaper import StaleReaperCheck
from irminsul.checks.supersession import SupersessionCheck
from irminsul.checks.uniqueness import UniquenessCheck

REGISTRY: dict[str, type[Check]] = {
    FrontmatterCheck.name: FrontmatterCheck,
    GlobsCheck.name: GlobsCheck,
    UniquenessCheck.name: UniquenessCheck,
    LinksCheck.name: LinksCheck,
    SchemaLeakCheck.name: SchemaLeakCheck,
    CoverageCheck.name: CoverageCheck,
    ProseFileReferenceCheck.name: ProseFileReferenceCheck,
    AgentsManifestCheck.name: AgentsManifestCheck,
    RfcLifecycleCheck.name: RfcLifecycleCheck,
    RetiredReferencesCheck.name: RetiredReferencesCheck,
    AdrStructureCheck.name: AdrStructureCheck,
    RfcStructureCheck.name: RfcStructureCheck,
    MtimeDriftCheck.name: MtimeDriftCheck,
    OrphansCheck.name: OrphansCheck,
    StaleReaperCheck.name: StaleReaperCheck,
    SupersessionCheck.name: SupersessionCheck,
    ParentChildCheck.name: ParentChildCheck,
    RfcFollowThroughCheck.name: RfcFollowThroughCheck,
    GlossaryDisciplineCheck.name: GlossaryDisciplineCheck,
    ExternalLinksCheck.name: ExternalLinksCheck,
    BoundaryCheck.name: BoundaryCheck,
    PhantomLayerCheck.name: PhantomLayerCheck,
    DependencyCheck.name: DependencyCheck,
    ClaimProvenanceCheck.name: ClaimProvenanceCheck,
    FoundationReadinessCheck.name: FoundationReadinessCheck,
    InventoryDriftCheck.name: InventoryDriftCheck,
    ClaimAnchorCheck.name: ClaimAnchorCheck,
    DocRefsCheck.name: DocRefsCheck,
    ChangeBindingCheck.name: ChangeBindingCheck,
    RequirementGrammarCheck.name: RequirementGrammarCheck,
    DuplicateBlockCheck.name: DuplicateBlockCheck,
    CodeReferencesCheck.name: CodeReferencesCheck,
    TestOwnershipCheck.name: TestOwnershipCheck,
}


def flagged(flag: CheckFlag) -> tuple[str, ...]:
    """The registered checks that declare `flag`, in registry order."""
    return tuple(name for name, cls in REGISTRY.items() if flag in flags_of(cls))


DEFAULT_CHECKS = tuple(name for name in REGISTRY if name not in flagged(CheckFlag.opt_in))

__all__ = [
    "DEFAULT_CHECKS",
    "REGISTRY",
    "AdrStructureCheck",
    "AgentsManifestCheck",
    "BoundaryCheck",
    "ChangeBindingCheck",
    "Check",
    "CheckFlag",
    "ClaimAnchorCheck",
    "ClaimProvenanceCheck",
    "CodeReferencesCheck",
    "CoverageCheck",
    "DependencyCheck",
    "DocRefsCheck",
    "DuplicateBlockCheck",
    "Finding",
    "FindingClass",
    "FindingSource",
    "Fix",
    "FoundationReadinessCheck",
    "GlossaryDisciplineCheck",
    "InventoryDriftCheck",
    "PhantomLayerCheck",
    "ProseFileReferenceCheck",
    "RequirementGrammarCheck",
    "RetiredReferencesCheck",
    "RfcFollowThroughCheck",
    "RfcLifecycleCheck",
    "RfcStructureCheck",
    "Severity",
    "TestOwnershipCheck",
    "finding_records",
    "fix_commands",
    "flagged",
    "sort_findings",
    "summarize",
]
