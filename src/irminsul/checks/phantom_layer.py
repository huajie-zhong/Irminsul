"""PhantomLayerCheck — directories that have only INDEX.md and no content docs."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from irminsul.checks.base import Finding, Severity
from irminsul.docgraph import DocGraph


class PhantomLayerCheck:
    name: ClassVar[str] = "phantom-layer"
    default_severity: ClassVar[Severity] = Severity.warning

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
                out.append(
                    Finding(
                        check=self.name,
                        severity=Severity.warning,
                        message=f"phantom layer: '{rel}' has only INDEX.md and no content docs",
                        path=Path(rel + "/INDEX.md"),
                        suggestion="add content docs or remove the directory from the nav",
                    )
                )

        return out
