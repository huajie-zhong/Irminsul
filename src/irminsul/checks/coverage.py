"""CoverageCheck — docs in a layer with `require_tests` declare at least one valid test path."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import ClassVar

from irminsul.checks.base import Finding, FindingClass, Severity
from irminsul.declared_tests import classify_test_reference, test_reference_spec
from irminsul.docgraph import DocGraph, DocNode, layer_rules

CODE_MISSING_TESTS_ENTRY = "coverage/missing-tests-entry"
CODE_TESTS_PATH_MISSING = "coverage/tests-path-missing"


class CoverageCheck:
    name: ClassVar[str] = "coverage"
    default_severity: ClassVar[Severity] = Severity.error
    explanations: ClassVar[dict[str, str]] = {
        CODE_MISSING_TESTS_ENTRY: (
            "A doc with a `describes` claim, in a layer that requires tests, recommends "
            "no tests. Add `recommended_tests: [path/to/test_file.py]` to frontmatter, or "
            "`owns_tests:` for the tests this doc maintains, which the recommendations "
            "default to."
        ),
        CODE_TESTS_PATH_MISSING: (
            "A recommended test entry names a path that matches nothing. Create the test "
            "file, or update or remove the entry. A directory or glob entry satisfies "
            "this when it matches at least one file."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_MISSING_TESTS_ENTRY: FindingClass.certain,
        CODE_TESTS_PATH_MISSING: FindingClass.certain,
    }
    drafts_exempt: ClassVar[frozenset[str]] = frozenset({CODE_MISSING_TESTS_ENTRY})

    def run(self, graph: DocGraph) -> list[Finding]:
        out: list[Finding] = []
        repo_root = graph.repo_root

        for node in graph.nodes.values():
            rules = layer_rules(node, graph.config)
            if rules is None or not rules[1].require_tests:
                continue

            # Placeholder docs with no describes: claim are not yet covering any
            # source, so requiring tests would be noise. Skip them.
            if not node.frontmatter.describes:
                continue

            recommended = node.frontmatter.effective_recommended_tests
            field = _declared_field(node)
            if not recommended:
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_MISSING_TESTS_ENTRY,
                        severity=Severity.error,
                        message=f"{rules[0]} doc recommends no tests in frontmatter",
                        path=node.path,
                        doc_id=node.id,
                        suggestion="Add `recommended_tests: [path/to/test_file.py]` to frontmatter",
                        data={"problem": "missing-tests-entry", "field": field},
                    )
                )
                continue

            if repo_root is None:
                continue

            for test_path in recommended:
                if _resolves(repo_root, test_path):
                    continue
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_TESTS_PATH_MISSING,
                        severity=Severity.error,
                        message=f"{field}: entry '{test_path}' matches no file",
                        path=node.path,
                        doc_id=node.id,
                        suggestion=f"Create '{test_path}' or update the {field}: field",
                        data={
                            "problem": "tests-path-missing",
                            "field": field,
                            "value": test_path,
                        },
                    )
                )

        return out


def _declared_field(node: DocNode) -> str:
    """Which spelling this doc actually used, so the message names the line to edit."""
    if node.frontmatter.recommended_tests:
        return "recommended_tests"
    if node.frontmatter.tests:
        return "tests"
    if node.frontmatter.owns_tests:
        return "owns_tests"
    return "recommended_tests"


def _resolves(repo_root: Path, entry: str) -> bool:
    """Whether a recommendation names anything real.

    An exact path has to exist. A directory or glob is satisfied by matching at least one
    file, because it recommends a group rather than a file — the older reading was a bare
    `Path.exists()`, which passed a directory and failed every wildcard the CLI's own
    `new component --tests` help said was allowed.

    A pattern is matched with `declared_tests`' shared matcher rather than `Path.glob`, for
    two reasons. `Path.glob` disagreed with it — `test_*.py` matched `tests/test_a.py`
    there and not here, so one entry was routed by `footprint` and called dead by this
    check. And `Path.glob` raises on input a person can legitimately type: an absolute
    pattern is `NotImplementedError` and `a**b/*.py` is `ValueError`, neither caught, so a
    single mistyped entry ended the whole run in a traceback instead of a finding.
    """
    reference = classify_test_reference(entry, repo_root)
    if reference.is_exact:
        return (repo_root / reference.raw).exists()
    if reference.kind == "directory":
        directory = repo_root / reference.raw.rstrip("/")
        return _has_a_file(directory)
    spec = test_reference_spec([reference.raw])
    search = repo_root / _literal_prefix(reference.raw)
    try:
        return any(
            spec.match_file(child.relative_to(repo_root).as_posix())
            for child in search.rglob("*")
            if child.is_file()
        )
    except (OSError, ValueError):
        # Outside the repository, or unreadable: nothing here matches it.
        return False


def _has_a_file(directory: Path) -> bool:
    try:
        return directory.is_dir() and any(child.is_file() for child in directory.rglob("*"))
    except OSError:
        return False


def _literal_prefix(pattern: str) -> str:
    """The leading path segments of `pattern` before its first wildcard.

    Bounds the walk to the subtree a pattern could possibly match, so checking one entry
    does not read the whole repository. A leading `/` is dropped: an entry is always
    relative to the repository, and joining an absolute path would escape it.
    """
    segments: list[str] = []
    for segment in PurePosixPath(pattern.lstrip("/")).parts:
        if any(char in segment for char in "*?["):
            break
        segments.append(segment)
    return "/".join(segments)
