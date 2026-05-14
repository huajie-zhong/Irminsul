"""Generate the `docs/AGENTS.md` agent navigation manifest (RFC 0013).

The manifest has three sections: a generated documentation-tree table (the only
part `regen` rewrites and the `agents-manifest` check compares), a curated
Foundations digest, and a curated Protocol pointer. The generated table is
delimited by HTML-comment markers so curated content survives regeneration.
"""

from __future__ import annotations

from pathlib import Path

from irminsul.config import IrminsulConfig
from irminsul.docgraph import DocGraph, DocNode, build_graph

GENERATED_START = "<!-- agents-manifest:generated-start -->"
GENERATED_END = "<!-- agents-manifest:generated-end -->"

MANIFEST_FILENAME = "AGENTS.md"


def manifest_rel_path(config: IrminsulConfig) -> Path:
    return Path(config.paths.docs_root) / MANIFEST_FILENAME


def _docs_root(config: IrminsulConfig) -> str:
    return config.paths.docs_root.strip("/\\")


def _layer_of(node: DocNode, docs_root: str) -> str:
    parts = node.path.as_posix().split("/")
    if len(parts) >= 3 and parts[0] == docs_root:
        return parts[1]
    return "(root)"


def _doc_relpath(node: DocNode, docs_root: str) -> str:
    rel = node.path.as_posix()
    prefix = f"{docs_root}/"
    if rel.startswith(prefix):
        return rel[len(prefix) :]
    return rel


def _cell(text: str) -> str:
    return text.replace("|", r"\|").replace("\n", " ").strip()


def render_generated_section(graph: DocGraph) -> str:
    """Deterministic tree-by-layer table. The `agents-manifest` check compares
    the committed manifest's marked section against this output verbatim."""
    if graph.config is None:
        return ""
    docs_root = _docs_root(graph.config)
    manifest_path = manifest_rel_path(graph.config)

    by_layer: dict[str, list[DocNode]] = {}
    for node in graph.nodes.values():
        if node.path == manifest_path:
            continue
        by_layer.setdefault(_layer_of(node, docs_root), []).append(node)

    lines: list[str] = []
    for layer in sorted(by_layer):
        lines.append(f"### {layer}")
        lines.append("")
        lines.append("| ID | Doc | Audience | Tier | Summary |")
        lines.append("|----|-----|----------|------|---------|")
        for node in sorted(by_layer[layer], key=lambda n: n.id):
            title = _cell(node.frontmatter.title)
            relpath = _doc_relpath(node, docs_root)
            summary = _cell(node.frontmatter.summary or "")
            lines.append(
                f"| `{node.id}` | [{title}]({relpath}) "
                f"| {node.frontmatter.audience.value} | {node.frontmatter.tier} | {summary} |"
            )
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _foundations_section() -> list[str]:
    return [
        "## Foundations",
        "",
        "Read this before editing any doc. Full detail lives in `docs/00-foundation/`",
        "and `docs/10-architecture/`.",
        "",
        "### The Three Laws of Maintenance",
        "",
        "> **Law 1.** Each fact has exactly one home.",
        ">",
        "> **Law 2.** Each document has exactly one purpose and one audience moment.",
        ">",
        "> **Law 3.** Every cross-reference is bidirectional and machine-verifiable.",
        "",
        "### The Layered Structure",
        "",
        "Numeric prefixes give stable sort order and namespace doc IDs as bare slugs.",
        "",
        "- `00-foundation` — principles, constraints, stakeholders; rarely changes.",
        "- `10-architecture` — system context, containers, boundaries, deployment.",
        '- `20-components` — the per-component "what".',
        '- `30-workflows` — cross-component "how".',
        "- `40-reference` — generated; never hand-edited.",
        '- `50-decisions` — ADRs; the "why", append-only.',
        "- `60-operations` — runbooks, playbooks, SLOs.",
        "- `70-knowledge` — tutorials, how-tos, explanations.",
        "- `80-evolution` — roadmap, RFCs, risks, debt.",
        "- `90-meta` — docs about the doc system.",
        "",
        "### The Tier System",
        "",
        "Each doc's tier dictates its enforcement policy.",
        "",
        "| Tier | Name | Edited by | Examples |",
        "|------|------|-----------|----------|",
        "| T1 | Generated | CI only | API reference, type schemas, config reference |",
        "| T2 | Stable | Humans, rarely | Principles, architecture overview, ADRs |",
        "| T3 | Living | Humans, often | Component docs, workflows, runbooks |",
        "| T4 | Ephemeral | Anyone | Sprint plans, RFCs in flight |",
    ]


def _protocol_section() -> list[str]:
    return [
        "## Protocol",
        "",
        "Before editing docs, follow the agent lifecycle protocol: read this",
        "manifest, run `irminsul context` to locate ownership, tests, dependencies,",
        "and findings, create or update RFCs and ADRs for direction or behavior",
        "changes, keep component docs and generated references current, and run",
        "`irminsul check --profile hard` before returning work.",
        "",
        "The full lifecycle work order is defined in",
        "[`0016-agent-lifecycle-protocol`]"
        "(80-evolution/rfcs/0016-agent-lifecycle-protocol.md). Its canonical",
        "protocol document under `docs/90-meta/` lands with RFC 0016; until then",
        "the RFC is authoritative.",
    ]


def render_default_manifest(graph: DocGraph) -> str:
    # AGENTS.md is an exempt top-level doc (like README.md): it carries no
    # frontmatter and is validated by the `agents-manifest` check, not the graph.
    body = [
        "# Agent Navigation Manifest",
        "",
        "This manifest is the curated entry point into `docs/` for agents. The",
        "documentation-tree table below is generated; the Foundations and Protocol",
        "sections are curated. Run `irminsul regen agents-md` after adding or",
        "moving docs.",
        "",
        "## Documentation Tree",
        "",
        GENERATED_START,
        "",
        render_generated_section(graph).strip(),
        "",
        GENERATED_END,
        "",
        *_foundations_section(),
        "",
        *_protocol_section(),
        "",
    ]
    return "\n".join(body)


def _replace_generated_section(text: str, section: str) -> str | None:
    """Replace the marked generated block in an existing manifest. Returns None
    if the markers are missing or unmatched."""
    start = text.find(GENERATED_START)
    end = text.find(GENERATED_END)
    if start == -1 or end == -1 or end < start:
        return None
    head = text[: start + len(GENERATED_START)]
    tail = text[end:]
    return f"{head}\n\n{section.strip()}\n\n{tail}"


def regen_agents_md(repo_root: Path, config: IrminsulConfig) -> list[Path]:
    """Write or refresh `docs/AGENTS.md`.

    Missing file: scaffold the full manifest. Existing file: rewrite only the
    generated section, preserving frontmatter and the curated sections. A file
    with broken markers is rebuilt from the default template.
    """
    graph = build_graph(repo_root, config)
    rel_path = manifest_rel_path(config)
    dest = repo_root / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        current = dest.read_text(encoding="utf-8").replace("\r\n", "\n")
        updated = _replace_generated_section(current, render_generated_section(graph))
        content = updated if updated is not None else render_default_manifest(graph)
    else:
        content = render_default_manifest(graph)

    dest.write_text(content, encoding="utf-8")
    return [dest]
