"""PhantomLayerCheck — directories that have only INDEX.md and no content docs.

A hollow directory is navigation rot: an INDEX that promises a section but
points at nothing. A content doc anywhere beneath the directory, in a subfolder at any
depth, is content. The class follows the INDEX's own status. A `status: draft`
INDEX marks a layer deliberately under construction, the state every freshly
scaffolded layer starts in, so the finding is an info hint: visible, but not
gating. A hollow layer whose INDEX claims `stable` is certain: it asserts a
finished section that has no content.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from irminsul.checks.base import Finding, FindingClass, Severity
from irminsul.config import docs_root_prefix
from irminsul.docgraph import DocGraph
from irminsul.frontmatter import StatusEnum

CODE_LAYER_UNDER_CONSTRUCTION = "phantom-layer/layer-under-construction"
CODE_HOLLOW_LAYER = "phantom-layer/hollow-layer"


class PhantomLayerCheck:
    name: ClassVar[str] = "phantom-layer"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_LAYER_UNDER_CONSTRUCTION: (
            "A directory has only a draft INDEX.md and no content docs, beside it or in any "
            "folder beneath it. Non-gating while the layer is deliberately still under "
            "construction."
        ),
        CODE_HOLLOW_LAYER: (
            "A directory has only INDEX.md and no content docs, beside it or in any folder "
            "beneath it, and the INDEX claims 'stable'. Add content docs or remove the "
            "directory from the nav."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_LAYER_UNDER_CONSTRUCTION: FindingClass.hint,
        CODE_HOLLOW_LAYER: FindingClass.certain,
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None:
            return []

        # The graph's own view of the docs, so a `docs_root` spelled "/docs" or "docs/" names
        # the same folder here as it did when the graph was walked. A doc that failed to parse
        # still counts as content: `frontmatter` reports it, and its folder is not hollow.
        doc_paths = [
            *graph.by_path,
            *graph.missing_frontmatter,
            *(failure.path for failure in graph.parse_failures),
        ]
        docs_root = Path(docs_root_prefix(graph.config))
        indexed: set[Path] = set()
        content_dirs: set[Path] = set()
        for path in doc_paths:
            if path.parent == docs_root:
                continue
            (indexed if path.name == "INDEX.md" else content_dirs).add(path.parent)

        out: list[Finding] = []
        for directory in sorted(indexed):
            if any(directory == folder or directory in folder.parents for folder in content_dirs):
                continue
            rel = directory.as_posix()
            index_node = graph.by_path.get(directory / "INDEX.md")
            is_draft = index_node is not None and index_node.frontmatter.status == StatusEnum.draft
            if is_draft:
                code = CODE_LAYER_UNDER_CONSTRUCTION
                severity = Severity.info
                message = f"layer under construction: '{rel}' has only a draft INDEX.md"
                suggestion = "add content docs, or this stays as a non-gating note while draft"
            else:
                code = CODE_HOLLOW_LAYER
                severity = Severity.error
                message = f"phantom layer: '{rel}' has only INDEX.md and no content docs"
                suggestion = "add content docs or remove the directory from the nav"
            out.append(
                Finding(
                    check=self.name,
                    code=code,
                    severity=severity,
                    message=message,
                    path=Path(rel + "/INDEX.md"),
                    suggestion=suggestion,
                )
            )

        return out
