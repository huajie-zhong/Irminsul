"""Check registry.

Looking-up by name keeps the CLI/config side honest: `irminsul.toml`'s
`checks.enabled` is a list of strings, resolved here.
"""

from __future__ import annotations

from irminsul.checks.adr_structure import AdrStructureCheck
from irminsul.checks.base import (
    Check,
    Finding,
    FindingClass,
    Fix,
    Severity,
    finding_records,
    fix_commands,
    sort_findings,
    summarize,
)
from irminsul.checks.boundary import BoundaryCheck
from irminsul.checks.change_binding import ChangeBindingCheck
from irminsul.checks.claim_anchor import ClaimAnchorCheck
from irminsul.checks.code_references import CodeReferencesCheck
from irminsul.checks.coverage import CoverageCheck
from irminsul.checks.dependency_check import DependencyCheck
from irminsul.checks.doc_reality import (
    AgentsManifestCheck,
    ClaimProvenanceCheck,
    ProseFileReferenceCheck,
    TerminologyOverloadCheck,
)
from irminsul.checks.doc_refs import DocRefsCheck
from irminsul.checks.duplicate_block import DuplicateBlockCheck
from irminsul.checks.env_check import EnvCheck
from irminsul.checks.external_links import ExternalLinksCheck
from irminsul.checks.foundation_readiness import FoundationReadinessCheck
from irminsul.checks.frontmatter import FrontmatterCheck
from irminsul.checks.globs import GlobsCheck
from irminsul.checks.glossary import GlossaryDisciplineCheck
from irminsul.checks.inventory_drift import InventoryDriftCheck
from irminsul.checks.liar import LiarCheck
from irminsul.checks.links import LinksCheck
from irminsul.checks.mtime_drift import MtimeDriftCheck
from irminsul.checks.orphans import OrphansCheck
from irminsul.checks.owned_tests import TestOwnershipCheck
from irminsul.checks.parent_child import ParentChildCheck
from irminsul.checks.phantom_layer import PhantomLayerCheck
from irminsul.checks.reality import RealityCheck
from irminsul.checks.requirement_grammar import RequirementGrammarCheck
from irminsul.checks.retired_references import RetiredReferencesCheck
from irminsul.checks.rfc_follow_through import RfcFollowThroughCheck
from irminsul.checks.rfc_lifecycle import RfcLifecycleCheck
from irminsul.checks.schema_leak import SchemaLeakCheck
from irminsul.checks.section_reference import SectionReferenceCheck
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
    LiarCheck.name: LiarCheck,
    ProseFileReferenceCheck.name: ProseFileReferenceCheck,
    AgentsManifestCheck.name: AgentsManifestCheck,
    RfcLifecycleCheck.name: RfcLifecycleCheck,
    RetiredReferencesCheck.name: RetiredReferencesCheck,
    AdrStructureCheck.name: AdrStructureCheck,
    MtimeDriftCheck.name: MtimeDriftCheck,
    OrphansCheck.name: OrphansCheck,
    StaleReaperCheck.name: StaleReaperCheck,
    SupersessionCheck.name: SupersessionCheck,
    ParentChildCheck.name: ParentChildCheck,
    RfcFollowThroughCheck.name: RfcFollowThroughCheck,
    GlossaryDisciplineCheck.name: GlossaryDisciplineCheck,
    ExternalLinksCheck.name: ExternalLinksCheck,
    RealityCheck.name: RealityCheck,
    BoundaryCheck.name: BoundaryCheck,
    PhantomLayerCheck.name: PhantomLayerCheck,
    EnvCheck.name: EnvCheck,
    DependencyCheck.name: DependencyCheck,
    TerminologyOverloadCheck.name: TerminologyOverloadCheck,
    ClaimProvenanceCheck.name: ClaimProvenanceCheck,
    FoundationReadinessCheck.name: FoundationReadinessCheck,
    InventoryDriftCheck.name: InventoryDriftCheck,
    ClaimAnchorCheck.name: ClaimAnchorCheck,
    DocRefsCheck.name: DocRefsCheck,
    ChangeBindingCheck.name: ChangeBindingCheck,
    RequirementGrammarCheck.name: RequirementGrammarCheck,
    DuplicateBlockCheck.name: DuplicateBlockCheck,
    SectionReferenceCheck.name: SectionReferenceCheck,
    CodeReferencesCheck.name: CodeReferencesCheck,
    TestOwnershipCheck.name: TestOwnershipCheck,
}

__all__ = [
    "REGISTRY",
    "AdrStructureCheck",
    "AgentsManifestCheck",
    "BoundaryCheck",
    "ChangeBindingCheck",
    "Check",
    "ClaimAnchorCheck",
    "ClaimProvenanceCheck",
    "CodeReferencesCheck",
    "CoverageCheck",
    "DependencyCheck",
    "DocRefsCheck",
    "DuplicateBlockCheck",
    "EnvCheck",
    "Finding",
    "FindingClass",
    "Fix",
    "FoundationReadinessCheck",
    "GlossaryDisciplineCheck",
    "InventoryDriftCheck",
    "LiarCheck",
    "PhantomLayerCheck",
    "ProseFileReferenceCheck",
    "RealityCheck",
    "RequirementGrammarCheck",
    "RetiredReferencesCheck",
    "RfcFollowThroughCheck",
    "RfcLifecycleCheck",
    "SectionReferenceCheck",
    "Severity",
    "TerminologyOverloadCheck",
    "TestOwnershipCheck",
    "finding_records",
    "fix_commands",
    "sort_findings",
    "summarize",
]
