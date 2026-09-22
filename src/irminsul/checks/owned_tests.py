"""TestOwnershipCheck — every test implementation file has one maintainer.

A component doc can own its tests; a test needs no document of its own. What it does need
is somebody answerable for it, which is what `owns_tests:` records.

Three rules, and the reasons they are shaped this way:

- **A file must be recognised as a test before it can be owned as one.** Recognition is
  `declared_tests.governed_as_test` — a test-shaped name, or a location inside a declared
  test root that no source root also claims — never the declaration itself. Otherwise
  `owns_tests: [src/important.py]` would be a way to have a source file stop counting as
  undocumented, and the `describes:` invariant would have a back door.
- **Ownership entries are exact paths.** A directory or a glob would claim files nobody
  chose, including ones added later, and "who maintains this" is a decision somebody
  makes rather than a pattern that happens to match.
- **A declared test tree is closed; an undeclared one is adopted progressively.** Under
  `paths.test_roots` every test file needs an owner, because declaring the root is the act
  of agreeing to that. Elsewhere — test-shaped files the ordinary source walk happens to
  reach — an unowned test is reported only beside one already owned, the progressive shape
  `uniqueness/undocumented-file` uses, so switching the check on does not turn an existing
  tree red before anyone has agreed to anything. Migration compatibility and the finished
  invariant are these two halves, and a repository moves from one to the other by naming
  its test root.

Test files inside the configured source walk stay subject to every other check. This
check is the reason they need not be claimed by `describes:`, not a reason to exclude
them from the walk: `source_excludes = ["**/*_test.go"]` would hide them from everything.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from irminsul.checks.base import Finding, FindingClass, Severity
from irminsul.checks.globs import walk_configured_source_files
from irminsul.config import CONFIG_FILENAME, IrminsulConfig
from irminsul.declared_tests import (
    classify_test_reference,
    governed_as_test,
    is_test_path,
    test_root_displays,
)
from irminsul.docgraph import DocGraph, DocNode

CODE_UNOWNED_TEST = "test-ownership/unowned-test"
CODE_DUPLICATE_TEST_OWNER = "test-ownership/duplicate-test-owner"
CODE_NOT_A_TEST = "test-ownership/not-a-test"
CODE_INEXACT_OWNERSHIP = "test-ownership/inexact-ownership"
CODE_OWNED_TEST_MISSING = "test-ownership/owned-test-missing"
CODE_MISSING_TEST_ROOT = "test-ownership/missing-test-root"
CODE_UNGOVERNED_TEST_FILE = "test-ownership/ungoverned-test-file"


class TestOwnershipCheck:
    name: ClassVar[str] = "test-ownership"
    default_severity: ClassVar[Severity] = Severity.error
    explanations: ClassVar[dict[str, str]] = {
        CODE_UNOWNED_TEST: (
            "A test implementation file in a directory whose tests are owned has no "
            "`owns_tests:` entry naming it. Add it to the component doc that maintains "
            "it. A test needs no document of its own, only a maintainer."
        ),
        CODE_DUPLICATE_TEST_OWNER: (
            "Two documents both name this test file in `owns_tests:`. Maintenance "
            "ownership is singular — decide which component maintains it, and let the "
            "other recommend it with `recommended_tests:` instead."
        ),
        CODE_NOT_A_TEST: (
            "`owns_tests:` names a file that is not a test implementation file under the "
            "project's conventions (the enabled languages' patterns, or "
            "`paths.test_patterns`). Ordinary source is owned with `describes:`; a test "
            "declaration does not make a file a test."
        ),
        CODE_INEXACT_OWNERSHIP: (
            "`owns_tests:` names a directory or a glob. Ownership entries are exact "
            "paths, so that it stays a decision about named files rather than a pattern "
            "that silently adopts whatever is added later. Recommendations "
            "(`recommended_tests:`) may be broad; ownership may not."
        ),
        CODE_OWNED_TEST_MISSING: (
            "`owns_tests:` names a file that does not exist. Correct the path, or drop "
            "the entry if the test is gone."
        ),
        CODE_MISSING_TEST_ROOT: (
            "`paths.test_roots` names a directory that is not there. A mistyped root walks "
            "nothing, so the closed invariant quietly becomes the progressive one and no "
            "unowned test is ever reported. Correct the path, or remove the entry."
        ),
        CODE_UNGOVERNED_TEST_FILE: (
            "A file's name exempts it from `describes:` ownership because it looks like a "
            "test, but no test policy governs it: it sits outside every declared "
            "`paths.test_roots`, nothing owns it, and no sibling test is owned either. So "
            "nothing checks who maintains it. Name its tree in `paths.test_roots`, give it "
            "an `owns_tests:` owner, or — if it is not a test — rename it and claim it with "
            "`describes:`."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_UNOWNED_TEST: FindingClass.certain,
        CODE_DUPLICATE_TEST_OWNER: FindingClass.certain,
        CODE_NOT_A_TEST: FindingClass.certain,
        CODE_INEXACT_OWNERSHIP: FindingClass.certain,
        CODE_OWNED_TEST_MISSING: FindingClass.certain,
        CODE_MISSING_TEST_ROOT: FindingClass.certain,
        CODE_UNGOVERNED_TEST_FILE: FindingClass.hint,
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        if graph.config is None or graph.repo_root is None:
            return []

        out: list[Finding] = []
        owners: dict[str, list[DocNode]] = {}
        # A declaration is resolved the way the walk spells things, not by joining it to
        # this repository's root. The siblings layout mandates a code root, so Irminsul
        # knows where `test_a.py` lives — `../code/tests/test_a.py` — and looking for
        # `docs/test_a.py` reported both `owned-test-missing` and `unowned-test`, leaving no
        # declaration that could make the gate green.
        in_test_root = test_root_displays(graph.repo_root, graph.config)
        walked = {display for _, display in graph.source_map.walk}
        for node in graph.nodes.values():
            for entry in node.frontmatter.owns_tests:
                reference = classify_test_reference(entry, graph.repo_root)
                if not reference.is_exact:
                    out.append(self._finding(node, CODE_INEXACT_OWNERSHIP, entry))
                    continue
                if not governed_as_test(
                    reference.raw, graph.config, in_test_root=reference.raw in in_test_root
                ):
                    out.append(self._finding(node, CODE_NOT_A_TEST, entry))
                    continue
                if reference.raw not in walked and not (graph.repo_root / reference.raw).is_file():
                    out.append(self._finding(node, CODE_OWNED_TEST_MISSING, entry))
                    continue
                owners.setdefault(reference.raw, []).append(node)

        for path in sorted(owners):
            claimants = owners[path]
            if len(claimants) > 1:
                named = ", ".join(sorted(node.id for node in claimants))
                out.append(
                    Finding(
                        check=self.name,
                        code=CODE_DUPLICATE_TEST_OWNER,
                        severity=Severity.error,
                        message=f"test file '{path}' is owned by more than one doc: {named}",
                        path=Path(path),
                        suggestion=(
                            "Keep one owner and let the others recommend it with recommended_tests"
                        ),
                        data={"problem": "duplicate-test-owner", "path": path},
                    )
                )

        out.extend(self._missing_roots(graph))
        out.extend(self._unowned(graph, set(owners)))
        return out

    def _missing_roots(self, graph: DocGraph) -> list[Finding]:
        """A declared test root that is not on disk.

        Silence here was the worst kind: the walk returns nothing, `closed` is empty, and
        the closed invariant degrades to the progressive one while the config still reads
        as though it were enforced. `source_roots` gets this from the `globs` check;
        `test_roots` has no other reader.
        """
        assert graph.config is not None and graph.repo_root is not None
        if not graph.config.paths.test_roots:
            return []
        missing = walk_configured_source_files(graph.repo_root, self._scoped(graph.config))
        return [
            Finding(
                check=self.name,
                code=CODE_MISSING_TEST_ROOT,
                severity=Severity.error,
                message=f"paths.test_roots names '{root}', which is not a directory",
                path=Path(CONFIG_FILENAME),
                suggestion="Correct the path, or remove the entry",
                data={"problem": "missing-test-root", "root": root},
            )
            for root in missing.missing_roots
        ]

    @staticmethod
    def _scoped(config: IrminsulConfig) -> IrminsulConfig:
        """The config with the declared test roots standing in for the source roots.

        Reuses the source walk rather than writing a second one, so excludes, includes,
        gitignore and symlink handling stay identical.
        """
        return config.model_copy(
            update={
                "paths": config.paths.model_copy(
                    update={"source_roots": list(config.paths.test_roots)}
                )
            }
        )

    def _test_files(self, graph: DocGraph) -> tuple[list[str], set[str]]:
        """Every test file the policy governs, and the subset enforcement is closed over.

        `paths.test_roots` is the closed part: a declared test tree is one somebody has
        said is a test tree, so every test in it needs an owner and there is nothing to
        adopt progressively. Test files caught by the ordinary source walk stay in the
        progressive half, because an adopter who never declared a test root has not
        agreed to anything yet.
        """
        assert graph.config is not None and graph.repo_root is not None
        config, root = graph.config, graph.repo_root
        walked = {display for _, display in walk_configured_source_files(root, config).files}
        closed = set(test_root_displays(root, config))
        walked |= closed

        def governed(display: str) -> bool:
            return governed_as_test(display, config, in_test_root=display in closed)

        tests = sorted(display for display in walked if governed(display))
        return tests, {display for display in closed if governed(display)}

    def _unowned(self, graph: DocGraph, owned: set[str]) -> list[Finding]:
        assert graph.config is not None and graph.repo_root is not None
        tests, closed = self._test_files(graph)
        # `.` is excluded deliberately: owning one repository-root test would otherwise
        # cover every directory through `parents`, turning a whole tree red at once — the
        # opposite of what progressive adoption promises. `uniqueness` drops it for the
        # same reason.
        covered = {parent for path in owned if (parent := Path(path).parent.as_posix()) != "."}
        # The adoption record answers the same question the progressive rule guesses at,
        # and answers it for tests too: a test the record names was already here, and one
        # it does not name is new wherever it sits. It excepts this finding and no other.
        debt = _recorded_debt(graph)
        out: list[Finding] = []
        for display in tests:
            if display in owned:
                continue
            if debt is not None:
                if display in debt:
                    continue
            elif not self._must_be_owned(display, closed, covered, owned):
                continue
            out.append(
                Finding(
                    check=self.name,
                    code=CODE_UNOWNED_TEST,
                    severity=Severity.error,
                    message=f"test file '{display}' has no doc declaring it in owns_tests",
                    path=Path(display),
                    suggestion=("Add it to owns_tests on the doc for the component it covers"),
                    data={"problem": "unowned-test", "path": display},
                )
            )
        out.extend(self._ungoverned(graph, tests, closed, covered, owned))
        return out

    def _ungoverned(
        self,
        graph: DocGraph,
        tests: list[str],
        closed: set[str],
        covered: set[str],
        owned: set[str],
    ) -> list[Finding]:
        """Files whose name waived `describes:` ownership while no test policy took them.

        The escape this closes is narrow and was silent: a module called `test_refs.py`
        under a source root matched a test convention, so `uniqueness` stopped asking which
        doc describes it, and `test-ownership` never asked who maintains it either. Neither
        check owned the question. Reported as a hint rather than an error because the tree
        may simply not have adopted test ownership yet, and the message says which of the
        three configurations resolves it.
        """
        assert graph.config is not None
        return [
            Finding(
                check=self.name,
                code=CODE_UNGOVERNED_TEST_FILE,
                severity=Severity.warning,
                message=(
                    f"'{display}' is exempt from describes ownership because its name reads "
                    "as a test, and no test policy governs it"
                ),
                path=Path(display),
                suggestion=(
                    "Name its tree in paths.test_roots, give it an owns_tests owner, or "
                    "rename it and claim it with describes"
                ),
                data={"problem": "ungoverned-test-file", "path": display},
            )
            for display in tests
            if display not in owned
            and is_test_path(display, graph.config)
            and not self._must_be_owned(display, closed, covered, owned)
        ]

    @staticmethod
    def _must_be_owned(display: str, closed: set[str], covered: set[str], owned: set[str]) -> bool:
        """Whether this unowned test file is reported.

        Inside a declared test root, always: that is what declaring one means. Outside
        one, only where a sibling test is already owned, so switching the check on does
        not turn a whole existing tree red before anyone has adopted it.
        """
        if display in closed:
            return True
        if not owned:
            return False
        parent = Path(display).parent
        return parent.as_posix() in covered or any(
            directory.as_posix() in covered for directory in parent.parents
        )

    def _finding(self, node: DocNode, code: str, entry: str) -> Finding:
        messages = {
            CODE_NOT_A_TEST: f"owns_tests names '{entry}', which is not a test file",
            CODE_INEXACT_OWNERSHIP: f"owns_tests names '{entry}', which is not an exact path",
            CODE_OWNED_TEST_MISSING: f"owns_tests names '{entry}', which does not exist",
        }
        suggestions = {
            CODE_NOT_A_TEST: "Own ordinary source with describes, or correct the path",
            CODE_INEXACT_OWNERSHIP: "Name each test file, or recommend the group with "
            "recommended_tests",
            CODE_OWNED_TEST_MISSING: "Correct the path, or drop the entry",
        }
        return Finding(
            check=self.name,
            code=code,
            severity=Severity.error,
            message=messages[code],
            path=node.path,
            doc_id=node.id,
            suggestion=suggestions[code],
            data={"problem": code.split("/", 1)[1], "entry": entry},
        )


def _recorded_debt(graph: DocGraph) -> frozenset[str] | None:
    """The adoption record's excepted paths, or `None` when the tree has no record.

    An unreadable record reads as no record here, and `uniqueness` reports it once as
    `adoption-record-unreadable`: two checks saying the same thing about one file is
    noise, and the one that names the record is the one that should say it. The same
    arrangement covers a cross-repo entry no boundary could confirm: `verified_debt`'s
    problems are dropped here and reported there, off the same managed walk, so both
    checks honour one set of exceptions and only one of them explains it.

    That set is the record as written. An entry the boundary contradicts keeps excepting
    its file, because calling it new would assert the opposite of what could not be shown;
    what fails the run is the finding `uniqueness` raises about it.
    """
    from irminsul.adoption import AdoptionError, load_record, record_path, verified_debt

    if graph.repo_root is None or graph.config is None:
        return None
    path = record_path(graph.repo_root, graph.config)
    if not path.is_file():
        return None
    try:
        record = load_record(path)
    except AdoptionError:
        return None
    return verified_debt(graph.repo_root, graph.config, record, graph.source_map)[0]


__all__ = [
    "CODE_DUPLICATE_TEST_OWNER",
    "CODE_INEXACT_OWNERSHIP",
    "CODE_NOT_A_TEST",
    "CODE_OWNED_TEST_MISSING",
    "CODE_UNOWNED_TEST",
    "TestOwnershipCheck",
]
