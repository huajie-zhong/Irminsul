"""New-dependency review — an import edge this change introduced that no doc declares.

A pass, not a registered graph check: like `co-change` and the diff-integrity pass it
needs the diff range, which `--diff <base>` or `context --after-edit` with a base puts on
the graph.

The question this answers is "did this change add a dependency nobody has said anything
about?", not "is this dependency allowed?". Nothing here declares a forbidden edge. A
prohibition would have to be written before the case that justifies crossing it exists,
and once written it is a contract, so the cheapest way past it stops being revision and
becomes evasion — a deferred import, an indirection module, a callback — each worse than
the honest dependency and none of them visible in review. So the edge itself is the
signal, and the resolution is to declare it: add the `depends_on:` entry and say why.

Deliberately narrow in three ways. It reports only an edge that is **new** in the diff,
so an undeclared edge that already existed stays silent and no tree needs migrating. It
reports only edges between two *owned* modules, because an unowned file has no doc to
declare anything. And it is a hint, so it never fails a run on its own.

It inherits `import-deps`' reach: a module path is resolved under `source_roots`, and a
file of another language, or one that is not UTF-8, backs no edge.
"""

from __future__ import annotations

from collections.abc import Collection
from pathlib import Path
from typing import ClassVar, Final

from irminsul.checks.base import Finding, FindingClass, Severity
from irminsul.checks.change_range import after_text
from irminsul.checks.dependency_check import SourceOwnership, imported_paths, resolve_ownership
from irminsul.docgraph import ChangeRange, DocGraph, DocNode
from irminsul.git.changes import file_at_ref
from irminsul.inventory.base import PythonModule

CHECK_NAME: Final = "new-dependency"
CODE_UNDECLARED_NEW_DEPENDENCY: Final = "new-dependency/undeclared-new-dependency"


class NewDependencyPass:
    """An import edge the diff introduced that the importing doc does not declare."""

    name: ClassVar[str] = CHECK_NAME
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_UNDECLARED_NEW_DEPENDENCY: (
            "This change added an import between two documented components, and the "
            "importing doc's `depends_on` does not carry it. Nothing here says the "
            "dependency is wrong — only that it is new and undeclared. Add the "
            "`depends_on` entry and say in the same change why the component now needs "
            "it, or drop the import."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_UNDECLARED_NEW_DEPENDENCY: FindingClass.hint,
    }

    def run(self, graph: DocGraph, selected: Collection[str]) -> list[Finding]:
        change = graph.change
        if change is None:
            return []
        return run_new_dependency(graph, change)


def _edges_in(
    module: PythonModule | None,
    importer: Path,
    source_roots: list[str],
    repo_root: Path,
    ownership: SourceOwnership,
) -> set[str]:
    """Owning doc ids the imports in `module`, read as the file `importer`, reach; none
    for a module that did not parse.

    `imported_paths` walks the whole AST, so an import inside a function counts — which
    matters, because deferring an import is exactly how a module-level one gets avoided.
    """
    out: set[str] = set()
    if module is None:
        return out
    for candidate in imported_paths(module, importer, source_roots, repo_root):
        dep_id = ownership.owner_of(candidate)
        if dep_id is not None:
            out.add(dep_id)
    return out


def run_new_dependency(graph: DocGraph, change: ChangeRange) -> list[Finding]:
    """Report each doc that gained an undeclared import edge in this diff.

    A changed file's edges as the change leaves it, the working tree or `HEAD` under
    `--committed-only`, are compared with the edges its own content had at the merge base,
    so only what this change added is reported, and what the base branch gained since is
    not part of it; a file the change did not touch is never read at the merge base at all.
    """
    if graph.config is None or graph.repo_root is None:
        return []

    repo_root = graph.repo_root
    source_roots = graph.config.paths.source_roots
    ownership = resolve_ownership(graph)
    changed = change.changed

    gained: dict[str, tuple[DocNode, set[str]]] = {}
    for node in graph.nodes.values():
        declared = set(node.frontmatter.depends_on)
        for abs_path in ownership.doc_py_files.get(node.id, []):
            try:
                display = abs_path.resolve().relative_to(repo_root.resolve()).as_posix()
            except ValueError:
                continue  # a source file outside the docs repo; its history is not ours
            if display not in changed:
                continue
            now_text = after_text(graph.git, repo_root, change.head, display)
            if now_text is None:
                continue
            now = PythonModule.parse(now_text)
            before = PythonModule.parse(
                file_at_ref(graph.git, repo_root, change.merge_base, display) or ""
            )
            new_edges = _edges_in(now, abs_path, source_roots, repo_root, ownership) - _edges_in(
                before, abs_path, source_roots, repo_root, ownership
            )
            new_edges -= {node.id}
            new_edges -= declared
            if new_edges:
                _, collected = gained.setdefault(node.id, (node, set()))
                collected.update(new_edges)

    out: list[Finding] = []
    for doc_id in sorted(gained):
        node, edges = gained[doc_id]
        listed = ", ".join(sorted(edges))
        out.append(
            Finding(
                check=CHECK_NAME,
                code=CODE_UNDECLARED_NEW_DEPENDENCY,
                severity=Severity.warning,
                path=node.path,
                doc_id=node.id,
                message=(
                    f"this change added an import of {listed}, which this doc's "
                    "depends_on does not declare"
                ),
                suggestion=(
                    f"add {listed} to depends_on and say why the component now needs it, "
                    "or drop the import"
                ),
                data={"gained": listed},
            )
        )
    return out


__all__ = [
    "CHECK_NAME",
    "CODE_UNDECLARED_NEW_DEPENDENCY",
    "NewDependencyPass",
    "run_new_dependency",
]
