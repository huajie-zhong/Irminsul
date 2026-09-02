"""PhantomLayerCheck — directories that have only INDEX.md and no content docs.

A hollow directory is navigation rot: an INDEX that promises a section but
points at nothing. Severity depends on the INDEX's own status. A `status:
draft` INDEX marks a layer deliberately under construction (every freshly
scaffolded layer starts this way), so the finding is downgraded to `info` —
visible, but not a gating warning. A hollow layer whose INDEX claims `stable`
is a real warning: it asserts a finished section that has no content.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph
from irminsul.frontmatter import StatusEnum

CODE_LAYER_UNDER_CONSTRUCTION = "phantom-layer/layer-under-construction"
CODE_HOLLOW_LAYER = "phantom-layer/hollow-layer"


class PhantomLayerCheck:
    name: ClassVar[str] = "phantom-layer"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_LAYER_UNDER_CONSTRUCTION: (
            "A directory has only a draft INDEX.md and no content docs. Non-gating while "
            "the layer is deliberately still under construction."
        ),
        CODE_HOLLOW_LAYER: (
            "A directory has only INDEX.md and no content docs, and the INDEX claims "
            "'stable'. Add content docs or remove the directory from the nav."
        ),
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None or graph.repo_root is None:
            return []

        docs_root = graph.repo_root / graph.config.paths.docs_root
        out: list[Finding] = []

        for d in sorted(docs_root.rglob("*")):
            if not d.is_dir():
                continue
            md_files = [f for f in d.iterdir() if f.suffix == ".md"]
            non_index = [f for f in md_files if f.name != "INDEX.md"]
            if md_files and not non_index:
                rel = d.relative_to(graph.repo_root).as_posix()
                index_node = graph.by_path.get(Path(rel) / "INDEX.md")
                is_draft = (
                    index_node is not None and index_node.frontmatter.status == StatusEnum.draft
                )
                if is_draft:
                    code = CODE_LAYER_UNDER_CONSTRUCTION
                    severity = Severity.info
                    message = f"layer under construction: '{rel}' has only a draft INDEX.md"
                    suggestion = "add content docs, or this stays as a non-gating note while draft"
                else:
                    code = CODE_HOLLOW_LAYER
                    severity = Severity.warning
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
