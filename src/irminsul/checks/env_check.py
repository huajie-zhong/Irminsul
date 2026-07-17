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
from irminsul.checks.globs import walk_configured_source_files
from irminsul.docgraph import DocGraph, DocNode

_ENV_PATTERN = re.compile(
    r'os\.environ\s*\[\s*["\'](\w+)["\']\s*\]'
    r'|os\.environ\.get\s*\(\s*["\'](\w+)["\']'
    r'|os\.getenv\s*\(\s*["\'](\w+)["\']',
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


CODE_STALE_DECLARATION = "requires-env/stale-declaration"


class EnvCheck:
    name: ClassVar[str] = "requires-env"
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_STALE_DECLARATION: (
            "A `requires_env` entry is declared but the code it describes no longer "
            "reads that env var. Remove the stale declaration, or check the `describes` "
            "glob if the var is read elsewhere."
        ),
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None or graph.repo_root is None:
            return []

        source_files = walk_configured_source_files(graph.repo_root, graph.config).files

        out: list[Finding] = []

        for node in graph.nodes.values():
            if not node.frontmatter.requires_env:
                continue

            declared = _collect_transitive_declared(node, graph)

            found: set[str] = set()
            spec = GitIgnoreSpec.from_lines(node.frontmatter.describes)
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

            # Intent-only (RFC 0020): we flag a declared env var that the code does
            # not read (a stale declaration), but never the reverse — requiring the
            # doc to mirror every env read would be the materialization pressure the
            # "derive, don't materialize" principle rejects. Use `irminsul surface
            # env-vars` to see the full set of env vars the code reads.
            for key in sorted(declared - found):
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_STALE_DECLARATION,
                        severity=Severity.warning,
                        message=f"env var '{key}' declared in requires_env but not found in code (stale)",
                        path=node.path,
                        doc_id=node.id,
                    )
                )

        return out
