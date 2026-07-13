"""`change impact` (RFC 0033): derived, layered change impact.

A recomputed view over the diff and the DocGraph — never stored on the RFC.
Two evidence levels: *plan* impact (no diff needed; declared scope, direction,
requirements, and graph links) and *observed* impact (adds diff-derived owners,
changed docs, test evidence, and surface routes). Observations are mechanical
facts with source attribution; the review questions they carry are for an
agent or human — the report never claims to know the answers.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from irminsul.change.footprint import Footprint, touched_components
from irminsul.change.report import (
    ChangeBaseline,
    find_rfc_node,
    resolve_change_baseline,
)
from irminsul.config import IrminsulConfig
from irminsul.docgraph import DocGraph, DocNode, build_graph
from irminsul.frontmatter import DirectionEnum

IMPACT_VERSION = 1

LAYERS = (
    "foundation",
    "architecture",
    "components",
    "workflows",
    "decisions",
    "evolution",
    "surfaces",
    "glossary",
)

_LAYER_DIRS = {
    "foundation": "00-foundation",
    "architecture": "10-architecture",
    "workflows": "30-workflows",
    "decisions": "50-decisions",
    "evolution": "80-evolution",
}

_COMPONENTS_DIR = "20-components"


@dataclass(frozen=True)
class Observation:
    observation: str
    source: str
    review: str | None = None


@dataclass(frozen=True)
class ImpactReport:
    version: int
    change: str
    state: str
    level: str  # plan | observed
    baseline: ChangeBaseline
    layers: dict[str, list[Observation]]


def build_impact_report(
    repo_root: Path,
    config: IrminsulConfig,
    change: str,
    *,
    base_ref: str | None = None,
    env: Mapping[str, str] | None = None,
    graph: DocGraph | None = None,
    baseline: ChangeBaseline | None = None,
    footprint: Footprint | None = None,
) -> ImpactReport:
    if graph is None:
        graph = build_graph(repo_root, config)
    node = find_rfc_node(graph, config, change)
    fm = node.frontmatter
    assert fm.rfc_state is not None

    if baseline is None:
        baseline = resolve_change_baseline(repo_root, base_ref, env=env)
    if baseline.changed_paths is None:
        footprint = None
    elif footprint is None:
        footprint = touched_components(graph, config, frozenset(baseline.changed_paths))

    docs_root = (config.paths.docs_root or "docs").replace("\\", "/").strip("/")
    layers: dict[str, list[Observation]] = {layer: [] for layer in LAYERS}

    _plan_impact(graph, node, docs_root, layers)
    if footprint is not None:
        _observed_impact(graph, config, repo_root, node, footprint, docs_root, layers)

    return ImpactReport(
        version=IMPACT_VERSION,
        change=node.id,
        state=fm.rfc_state.value,
        level="observed" if footprint is not None else "plan",
        baseline=baseline,
        layers=layers,
    )


def _outbound_weak(graph: DocGraph, node: DocNode) -> set[str]:
    """Doc ids the RFC's body links to (the inverse view of `inbound_weak`)."""
    return {target for target, sources in graph.inbound_weak.items() if node.id in sources}


def _plan_impact(
    graph: DocGraph,
    node: DocNode,
    docs_root: str,
    layers: dict[str, list[Observation]],
) -> None:
    fm = node.frontmatter
    outbound = _outbound_weak(graph, node)

    if fm.direction == DirectionEnum.revises:
        linked_foundation = sorted(
            target
            for target in outbound
            if (t := graph.nodes.get(target)) is not None
            and t.path.as_posix().startswith(f"{docs_root}/00-foundation/")
        )
        layers["foundation"].append(
            Observation(
                observation=(
                    "direction is `revises`"
                    + (
                        f"; foundation docs linked from the RFC: {', '.join(linked_foundation)}"
                        if linked_foundation
                        else "; the RFC links no foundation doc"
                    )
                ),
                source="rfc:direction",
                review=(
                    "Does the implementation revise a project principle, and if so "
                    "which foundation doc records it?"
                ),
            )
        )

    for component in fm.affects or []:
        owner = graph.nodes.get(component)
        layers["components"].append(
            Observation(
                observation=(
                    f"declared affected component '{component}'"
                    + (f" ({owner.path.as_posix()})" if owner else " (unresolved id)")
                ),
                source="rfc:affects",
            )
        )

    section = graph.requirements.get(node.id)
    if section is not None and section.requirements:
        layers["components"].append(
            Observation(
                observation=(
                    f"{len(section.requirements)} behavioral requirement(s) declared; "
                    "each needs implementation and test evidence"
                ),
                source="rfc:requirements",
            )
        )

    for component in fm.affects or []:
        dependents = graph.inbound_strong.get(component, set()) | graph.inbound_weak.get(
            component, set()
        )
        workflow_docs = sorted(
            dep
            for dep in dependents
            if (d := graph.nodes.get(dep)) is not None
            and d.path.as_posix().startswith(f"{docs_root}/30-workflows/")
        )
        for workflow in workflow_docs:
            layers["workflows"].append(
                Observation(
                    observation=(
                        f"workflow doc '{workflow}' links to or depends on affected "
                        f"component '{component}'"
                    ),
                    source=f"graph:{component}<-{workflow}",
                    review=(
                        "A link is a review route, not proof of behavior change - "
                        "does this workflow's documented behavior still hold?"
                    ),
                )
            )

    if fm.resolved_by:
        layers["decisions"].append(
            Observation(observation=f"resolved by {fm.resolved_by}", source="rfc:resolved_by")
        )
    for entry in fm.required_updates or []:
        exists = graph.by_path.get(Path(entry.path.replace("\\", "/"))) is not None
        layers["decisions"].append(
            Observation(
                observation=(
                    f"required update: {entry.kind.value} {entry.path}"
                    + ("" if exists else " (missing)")
                ),
                source="rfc:required_updates",
                review=None if exists else "Create the doc or correct the path.",
            )
        )

    for superseded in fm.supersedes:
        layers["evolution"].append(
            Observation(
                observation=f"supersedes '{superseded}'",
                source="rfc:supersedes",
                review="Are the superseded doc's live claims retired or replaced?",
            )
        )
    related_rfcs = sorted(
        src
        for src in graph.inbound_weak.get(node.id, set())
        if (s := graph.nodes.get(src)) is not None
        and s.path.as_posix().startswith(f"{docs_root}/80-evolution/")
        and src != node.id
    )
    for related in related_rfcs:
        layers["evolution"].append(
            Observation(
                observation=f"evolution doc '{related}' references this RFC",
                source=f"graph:{related}->{node.id}",
            )
        )


def _observed_impact(
    graph: DocGraph,
    config: IrminsulConfig,
    repo_root: Path,
    node: DocNode,
    footprint: Footprint,
    docs_root: str,
    layers: dict[str, list[Observation]],
) -> None:
    declared = set(node.frontmatter.affects or [])

    for layer, layer_dir in _LAYER_DIRS.items():
        prefix = f"{docs_root}/{layer_dir}/"
        for doc_path in footprint.changed_docs:
            if doc_path.startswith(prefix):
                layers[layer].append(
                    Observation(
                        observation=f"doc changed in the diff: {doc_path}",
                        source=f"diff:{doc_path}",
                    )
                )

    _changed_component_docs(graph, footprint, docs_root, declared, layers)

    for component, files in footprint.touched.items():
        divergence = "" if component in declared else " - absent from `affects`"
        layers["components"].append(
            Observation(
                observation=(
                    f"component '{component}' owns changed source: {', '.join(files)}{divergence}"
                ),
                source=f"diff:{files[0]}",
                review=(
                    None
                    if component in declared
                    else "Intended scope expansion or accidental side effect?"
                ),
            )
        )
    for component in sorted(declared - set(footprint.touched)):
        layers["components"].append(
            Observation(
                observation=(
                    f"declared component '{component}' has no owned source change in this baseline"
                ),
                source="rfc:affects",
                review="Not started, or planned scope that was dropped?",
            )
        )
    for unowned in footprint.unowned_source:
        layers["components"].append(
            Observation(
                observation=f"changed source '{unowned}' has no component claim",
                source=f"diff:{unowned}",
                review="Which component should own this file?",
            )
        )
    for component, tests in footprint.changed_tests.items():
        layers["components"].append(
            Observation(
                observation=f"test evidence for '{component}': {', '.join(tests)}",
                source=f"diff:{tests[0]}",
            )
        )

    changed = set(footprint.changed_paths)
    _surface_impact(repo_root, config, changed, layers)

    glossary_findings = _glossary_findings_for_paths(graph, changed | {node.path.as_posix()})
    for finding_path, message in glossary_findings:
        layers["glossary"].append(
            Observation(
                observation=message,
                source=f"finding:glossary-discipline:{finding_path}",
                review="Is this a domain term the glossary should own?",
            )
        )


def _changed_component_docs(
    graph: DocGraph,
    footprint: Footprint,
    docs_root: str,
    declared: set[str],
    layers: dict[str, list[Observation]],
) -> None:
    """Component docs touched by the diff.

    A doc still in the tree is a components-layer observation attributed to the
    component it defines. A doc that changed but no longer resolves left the
    tree — removed or moved — which is an architecture-layer fact.
    """
    prefix = f"{docs_root}/{_COMPONENTS_DIR}/"
    for doc_path in footprint.changed_docs:
        if not doc_path.startswith(prefix):
            continue
        owner = graph.by_path.get(Path(doc_path))
        if owner is None:
            layers["architecture"].append(
                Observation(
                    observation=f"component doc removed or moved: {doc_path}",
                    source=f"diff:{doc_path}",
                    review=(
                        "Does every inbound link, claim, and `affects` entry that named "
                        "this component still resolve?"
                    ),
                )
            )
            continue
        divergence = "" if owner.id in declared else " - absent from `affects`"
        layers["components"].append(
            Observation(
                observation=(
                    f"component doc changed in the diff: {doc_path} "
                    f"(component '{owner.id}'){divergence}"
                ),
                source=f"diff:{doc_path}",
                review=(
                    None
                    if owner.id in declared
                    else "Intended scope expansion or accidental side effect?"
                ),
            )
        )


def _surface_kinds(config: IrminsulConfig) -> list[str]:
    """Every kind an extractor can serve: the registry plus configured generic rules."""
    from irminsul.inventory import KNOWN_KINDS

    kinds = list(KNOWN_KINDS)
    kinds.extend(
        sorted(
            {
                rule.kind
                for rule in config.checks.inventory_drift.generic
                if rule.kind not in KNOWN_KINDS
            }
        )
    )
    return kinds


def _surface_impact(
    repo_root: Path,
    config: IrminsulConfig,
    changed: set[str],
    layers: dict[str, list[Observation]],
) -> None:
    """Surface identities defined in the changed files, one walk for every kind.

    Feeds the extractors just the changed source files instead of deriving the
    whole repository surface per kind — impact stays cheap on large codebases.
    An extractor that raises costs its kind's identities, so the failure is
    reported rather than swallowed: a kind is never silently empty.
    """
    from irminsul.checks.globs import walk_source_files
    from irminsul.inventory import get_extractor

    files, _missing = walk_source_files(repo_root, config.paths.source_roots)
    changed_files = [(abs_path, display) for abs_path, display in files if display in changed]
    if not changed_files:
        return

    for kind in _surface_kinds(config):
        extractor = get_extractor(kind, config)
        if extractor is None:
            continue
        try:
            items = extractor.extract(changed_files, config)
        except Exception as exc:
            layers["surfaces"].append(
                Observation(
                    observation=(f"{kind} surface extraction failed: {type(exc).__name__}: {exc}"),
                    source=f"surface:{kind}",
                    review=(
                        f"This kind's identities are unknown, not absent - inspect the "
                        f"changed files for {kind} surface changes by hand."
                    ),
                )
            )
            continue
        identities = sorted({item.identity for item in items})
        if not identities:
            continue
        layers["surfaces"].append(
            Observation(
                observation=(
                    f"{kind} surface identities defined in changed files: {', '.join(identities)}"
                ),
                source=f"surface:{kind}",
                review="Does the RFC describe this public behavior and its failure cases?",
            )
        )


def _glossary_findings_for_paths(graph: DocGraph, paths: set[str]) -> list[tuple[str, str]]:
    from irminsul.checks.glossary import GlossaryDisciplineCheck

    out: list[tuple[str, str]] = []
    for finding in GlossaryDisciplineCheck().run(graph):
        finding_path = finding.path.as_posix() if finding.path else None
        if finding_path in paths:
            out.append((finding_path, finding.message))
    return out


def impact_report_to_json(report: ImpactReport, *, all_layers: bool = False) -> str:
    layers_payload = {
        layer: [
            {"observation": o.observation, "source": o.source, "review": o.review}
            for o in observations
        ]
        for layer, observations in report.layers.items()
        if all_layers or observations
    }
    payload: dict[str, object] = {
        "version": report.version,
        "change": report.change,
        "state": report.state,
        "level": report.level,
        "baseline": {
            "source": report.baseline.source,
            "ref": report.baseline.ref,
            "changed_paths": (
                list(report.baseline.changed_paths)
                if report.baseline.changed_paths is not None
                else None
            ),
        },
        "layers": layers_payload,
    }
    return json.dumps(payload, indent=2)


def format_impact_plain(report: ImpactReport, *, all_layers: bool = False) -> str:
    lines = [
        f"{report.change}: impact ({report.level})",
        f"  baseline: {report.baseline.source}"
        + (f" {report.baseline.ref}" if report.baseline.ref else ""),
    ]
    if report.level == "plan":
        lines.append("  note: no diff baseline; observed impact unavailable, not empty")
    for layer in LAYERS:
        observations = report.layers.get(layer, [])
        if not observations and not all_layers:
            continue
        lines.append(f"  {layer}:")
        if not observations:
            lines.append("    (none)")
        for o in observations:
            lines.append(f"    - {o.observation} [{o.source}]")
            if o.review:
                lines.append(f"      review: {o.review}")
    return "\n".join(lines)


def impact_summary(report: ImpactReport) -> dict[str, int]:
    """Terse per-layer observation counts for `change status`."""
    return {layer: len(obs) for layer, obs in report.layers.items() if obs}


__all__ = [
    "IMPACT_VERSION",
    "LAYERS",
    "ImpactReport",
    "Observation",
    "build_impact_report",
    "format_impact_plain",
    "impact_report_to_json",
    "impact_summary",
]
