"""Generate the `docs/AGENTS.md` agent navigation manifest.

The manifest has three sections: a generated documentation-tree table (the only
part `regen` rewrites and the `agents-manifest` check compares), a curated
Foundations digest, and a curated Protocol pointer. The generated table is
delimited by HTML-comment markers so curated content survives regeneration.
"""

from __future__ import annotations

from pathlib import Path

from irminsul.config import IrminsulConfig, LayerName, doc_folder, normalize_layer_path
from irminsul.docgraph import DocGraph, DocNode, build_graph

GENERATED_START = "<!-- agents-manifest:generated-start -->"
GENERATED_END = "<!-- agents-manifest:generated-end -->"

MANIFEST_FILENAME = "AGENTS.md"


def manifest_rel_path(config: IrminsulConfig) -> Path:
    return Path(config.paths.docs_root) / MANIFEST_FILENAME


def _docs_root(config: IrminsulConfig) -> str:
    return config.paths.docs_root.strip("/\\")


def _doc_relpath(node: DocNode, docs_root: str) -> str:
    """The doc path relative to `docs_root` — i.e. relative to the manifest,
    which lives at `<docs_root>/AGENTS.md`."""
    try:
        return node.path.relative_to(docs_root).as_posix()
    except ValueError:
        return node.path.as_posix()


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
        by_layer.setdefault(doc_folder(graph.config, node.path) or "(root)", []).append(node)

    lines: list[str] = []
    for layer in sorted(by_layer):
        lines.append(f"### {layer}")
        lines.append("")
        lines.append("| ID | Doc | Summary |")
        lines.append("|----|-----|---------|")
        for node in sorted(by_layer[layer], key=lambda n: n.id):
            title = _cell(node.frontmatter.title)
            relpath = _doc_relpath(node, docs_root)
            summary = _cell(node.frontmatter.summary or "")
            lines.append(f"| `{node.id}` | [{title}]({relpath}) | {summary} |")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _foundations_section(config: IrminsulConfig) -> list[str]:
    def folder(name: LayerName) -> str:
        return normalize_layer_path(getattr(config.layers, name).path)

    return [
        "## Foundations",
        "",
        f"Read this before editing any doc. Full detail lives in `{folder('foundation')}/`",
        f"and `{folder('architecture')}/`.",
        "",
        "### The Three Laws of Maintenance",
        "",
        "> **Law 1.** Each fact has exactly one home.",
        ">",
        "> **Law 2.** Each document has exactly one purpose and one audience moment.",
        ">",
        "> **Law 3.** Every cross-reference is bidirectional and machine-verifiable.",
        "",
        "### The Layers",
        "",
        f"- `{folder('foundation')}` — principles and non-goals; rarely changes.",
        f"- `{folder('architecture')}` — how the parts fit and how data flows between them.",
        f'- `{folder("components")}` — one doc per component: the "what".',
        f'- `{folder("decisions")}` — ADRs: the "why".',
        f"- `{folder('rfcs')}` — proposals moving through the change lifecycle.",
        f"- `{folder('guides')}` — how-tos, operations, and the docs about this doc system.",
    ]


def _protocol_section(config: IrminsulConfig) -> list[str]:
    guides = normalize_layer_path(config.layers.guides.path)
    return [
        "## Protocol",
        "",
        "Before editing docs, follow the agent lifecycle protocol: read this",
        "manifest, run `irminsul context <path>` to locate ownership, tests, dependencies,",
        "and findings, create or update RFCs and ADRs for direction or behavior",
        "changes, keep the affected docs current, and run",
        "`irminsul check` before returning work.",
        "",
        "The full lifecycle work order lives at",
        f"[`{guides}/agent-protocol`]({guides}/agent-protocol.md).",
    ]


def render_default_manifest(graph: DocGraph) -> str:
    # AGENTS.md is an exempt top-level doc (like README.md): it carries no
    # frontmatter and is validated by the `agents-manifest` check, not the graph.
    config = graph.config or IrminsulConfig()
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
        *_foundations_section(config),
        "",
        *_protocol_section(config),
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


class RegenError(Exception):
    """A manifest that cannot be refreshed without destroying authored content."""


def regen_agents_md(repo_root: Path, config: IrminsulConfig) -> list[Path]:
    """Write or refresh `docs/AGENTS.md`.

    Missing file: scaffold the full manifest. Existing file: rewrite only the
    generated section, preserving frontmatter and the curated sections.

    An existing file that cannot be read back raises `RegenError` rather than being
    rebuilt from the default template — whether its markers do not parse, or the bytes do
    not decode, or the file will not open. Rebuilding deleted every curated section — the
    manifest's own intro, its protocol, and the paragraph promising those survive a
    regen — and the finding for each of those states suggests running this command, so the
    tool talked the reader into destroying their own file. Refusing is recoverable; a
    wholesale rewrite is not.

    The decode case is why this is a `RegenError` and not a traceback. `check` reports a
    manifest saved as UTF-16 as `agents-manifest/manifest-unreadable`, whose suggestion is
    to run this command; arriving here and getting a `UnicodeDecodeError` is the tool
    handing the reader a stack trace for following its own advice.
    """
    graph = build_graph(repo_root, config)
    rel_path = manifest_rel_path(config)
    dest = repo_root / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        try:
            current = dest.read_text(encoding="utf-8").replace("\r\n", "\n")
        except UnicodeDecodeError as exc:
            raise RegenError(
                f"{rel_path.as_posix()} exists but is not valid UTF-8 ({exc.reason} at byte "
                f"{exc.start}), so its curated sections cannot be read back. An editor that "
                "saved it as UTF-16 is the usual cause: save it as UTF-8 and run this "
                "command again, or delete it to scaffold a fresh manifest, which loses "
                "whatever was curated in it."
            ) from exc
        except OSError as exc:
            raise RegenError(
                f"{rel_path.as_posix()} exists but could not be opened "
                f"({type(exc).__name__}: {exc}), so there is nothing to rewrite."
            ) from exc
        updated = _replace_generated_section(current, render_generated_section(graph))
        if updated is None:
            raise RegenError(
                f"{rel_path.as_posix()} exists but its generated-section markers do not "
                f"parse, so there is nowhere to write. Restore a matching "
                f"`{GENERATED_START}` / `{GENERATED_END}` pair around the generated "
                f"block, or delete the file to scaffold a fresh manifest."
            )
        content = updated
    else:
        content = render_default_manifest(graph)

    dest.write_text(content, encoding="utf-8", newline="\n")
    return [dest]
