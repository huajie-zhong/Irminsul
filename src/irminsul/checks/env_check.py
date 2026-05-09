"""EnvCheck — verify `requires_env` declarations against source code.

Only activates for docs that have a non-empty `requires_env` list (opt-in).
Scans the source files declared in `describes:` (and transitively through
`depends_on:`) for env var accesses and cross-checks against the declaration.
"""

from __future__ import annotations

import re
from collections import deque
from pathlib import PurePosixPath
from typing import ClassVar

from pathspec import GitIgnoreSpec

from irminsul.checks.base import Finding, Severity
from irminsul.checks.globs import walk_source_files
from irminsul.docgraph import DocGraph, DocNode

_ENV_PATTERN = re.compile(
    r'os\.environ\[["\']([\w]+)["\']\]'
    r'|os\.environ\.get\(["\']([\w]+)["\']'
    r'|os\.getenv\(["\']([\w]+)["\']',
    re.MULTILINE,
)


def _scan_env_vars(source_text: str) -> set[str]:
    return {g for m in _ENV_PATTERN.finditer(source_text) for g in m.groups() if g}


def _collect_transitive_declared(node: DocNode, graph: DocGraph) -> set[str]:
    """BFS over depends_on to collect all transitively declared requires_env."""
    declared: set[str] = set(node.frontmatter.requires_env)
    visited: set[str] = {node.id}
    queue: deque[str] = deque(node.frontmatter.depends_on)
    while queue:
        dep_id = queue.popleft()
        if dep_id in visited:
            continue
        visited.add(dep_id)
        dep = graph.nodes.get(dep_id)
        if dep is None:
            continue
        declared.update(dep.frontmatter.requires_env)
        queue.extend(dep.frontmatter.depends_on)
    return declared


class EnvCheck:
    name: ClassVar[str] = "requires-env"
    default_severity: ClassVar[Severity] = Severity.warning

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None or graph.repo_root is None:
            return []

        source_files, _ = walk_source_files(graph.repo_root, graph.config.paths.source_roots)

        out: list[Finding] = []

        for node in graph.nodes.values():
            if not node.frontmatter.requires_env:
                continue

            declared = _collect_transitive_declared(node, graph)

            found: set[str] = set()
            for pattern in node.frontmatter.describes:
                spec = GitIgnoreSpec.from_lines([pattern])
                for abs_path, display in source_files:
                    if not spec.match_file(display):
                        continue
                    if PurePosixPath(display).suffix != ".py":
                        continue
                    try:
                        text = abs_path.read_text(encoding="utf-8")
                    except OSError:
                        continue
                    found.update(_scan_env_vars(text))

            for key in sorted(found - declared):
                out.append(
                    Finding(
                        check=self.name,
                        severity=Severity.warning,
                        message=f"env var '{key}' used in code but not declared in requires_env",
                        path=node.path,
                        doc_id=node.id,
                    )
                )

            for key in sorted(declared - found):
                out.append(
                    Finding(
                        check=self.name,
                        severity=Severity.warning,
                        message=f"env var '{key}' declared in requires_env but not found in code (stale)",
                        path=node.path,
                        doc_id=node.id,
                    )
                )

        return out
