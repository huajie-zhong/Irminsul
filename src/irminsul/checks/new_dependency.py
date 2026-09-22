"""New-dependency review — an import edge this change introduced that no doc declares.

Not a registered graph check: like `co-change` and the diff-integrity pass it needs the
diff range, which only the CLI's `--diff <base>` flag supplies, so the CLI calls
`run_new_dependency` directly.

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

It inherits `import-deps`' reach, and its blind spot with it: a dotted module path is
resolved under `source_roots`, so `from package import module` records the package rather
than the module and an edge spelled that way is seen by neither pass.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, Final

from irminsul.checks.base import Finding, FindingClass, Severity
from irminsul.checks.dependency_check import (
    dotted_to_paths,
    extract_imports,
    resolve_ownership,
)
from irminsul.docgraph import DocGraph, DocNode
from irminsul.git.changes import file_at_ref

CHECK_NAME: Final = "new-dependency"
CODE_UNDECLARED_NEW_DEPENDENCY: Final = "new-dependency/undeclared-new-dependency"


class NewDependencyCheck:
    """An import edge the diff introduced that the importing doc does not declare.

    Absent from both registries for the same reason `co-change` is: it cannot run from a
    `DocGraph` alone. The class exists so `irminsul explain` resolves the code.
    """

    name: ClassVar[str] = CHECK_NAME
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_UNDECLARED_NEW_DEPENDENCY: (
            "This change added an import between two documented components, and the "
            "importing doc's `depends_on` does not carry it. Nothing here says the "
            "dependency is wrong — only that it is new and undeclared. Add the "
            "`depends_on` entry and say in the same change why the component now needs "
            "it, or drop the import. If it is genuinely one-off, an "
            "`irminsul:ignore` comment with a reason records that decision too."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_UNDECLARED_NEW_DEPENDENCY: FindingClass.hint,
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        raise NotImplementedError(
            "new-dependency needs the diff range; call run_new_dependency(graph, base_ref)"
        )


def _edges_in(
    text: str, source_roots: list[str], repo_root: Path, file_to_doc: dict[Path, str]
) -> set[str]:
    """Owning doc ids the imports in `text` reach.

    `extract_imports` walks the whole AST, so an import inside a function counts — which
    matters, because deferring an import is exactly how a module-level one gets avoided.
    """
    out: set[str] = set()
    for module in extract_imports(text):
        for candidate in dotted_to_paths(module, source_roots, repo_root):
            dep_id = file_to_doc.get(candidate.resolve())
            if dep_id is not None:
                out.add(dep_id)
    return out


def run_new_dependency(graph: DocGraph, base_ref: str, changed: frozenset[str]) -> list[Finding]:
    """Report each doc that gained an undeclared import edge in this diff.

    `changed` is the repo-relative POSIX path set from `git diff --name-only`, and
    `base_ref` the revision it was taken against. A file's edges are compared with the
    edges its own content had at that revision, so only what this change added is
    reported; a file the change did not touch is never read at the base at all.
    """
    if graph.config is None or graph.repo_root is None:
        return []

    repo_root = graph.repo_root
    source_roots = graph.config.paths.source_roots
    ownership = resolve_ownership(graph)
    file_to_doc = ownership.file_to_doc

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
            try:
                now = abs_path.read_text(encoding="utf-8")
            except OSError:
                continue
            before = file_at_ref(repo_root, base_ref, display) or ""
            new_edges = _edges_in(now, source_roots, repo_root, file_to_doc) - _edges_in(
                before, source_roots, repo_root, file_to_doc
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
                data={"problem": "undeclared-new-dependency", "gained": listed},
            )
        )
    return out


__all__ = [
    "CHECK_NAME",
    "CODE_UNDECLARED_NEW_DEPENDENCY",
    "NewDependencyCheck",
    "run_new_dependency",
]
