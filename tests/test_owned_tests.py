"""Who maintains a test, and what declaring one does *not* buy you.

The invariant: every test implementation file inside the configured source walk has one
maintenance owner. The trap it must not open: a test declaration is not a way for an
ordinary source file to stop needing `describes:` ownership.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.checks.base import Severity
from irminsul.checks.owned_tests import TestOwnershipCheck
from irminsul.checks.uniqueness import UniquenessCheck
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph
from irminsul.frontmatter import DocFrontmatter

_GO_CONFIG = (
    'project_name = "t"\n[paths]\ndocs_root = "docs"\nsource_roots = ["parser"]\n'
    '[languages]\nenabled = ["go"]\n'
    '[checks]\nenabled = ["frontmatter", "uniqueness", "test-ownership"]\n'
)


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _doc(doc_id: str, body: str = "A component.", **fields: list[str]) -> str:
    lines: list[str] = []
    for key, values in fields.items():
        if not values:
            lines.append(f"{key}: []")
            continue
        lines.append(f"{key}:")
        lines.extend(f"  - {value}" for value in values)
    block = "\n".join(lines)
    return (
        f"---\nid: {doc_id}\ntitle: {doc_id}\nstatus: stable\n"
        f"{block}\n---\n\n# {doc_id}\n\n{body}\n"
    )


def _go_repo(root: Path) -> Path:
    _write(root, "irminsul.toml", _GO_CONFIG)
    _write(root, "parser/parser.go", "package parser\n\nfunc Parse() {}\n")
    _write(root, "parser/parser_test.go", "package parser\n\nfunc TestParse() {}\n")
    return root


def _codes(root: Path) -> list[str]:
    graph = build_graph(root, load(find_config(root)))
    return sorted(f.code for f in TestOwnershipCheck().run(graph))


def _blocking(root: Path) -> list[str]:
    """Only the codes that fail a run. `ungoverned-test-file` is a hint by design."""
    graph = build_graph(root, load(find_config(root)))
    return sorted(f.code for f in TestOwnershipCheck().run(graph) if f.severity is Severity.error)


def _uniqueness_codes(root: Path) -> list[str]:
    graph = build_graph(root, load(find_config(root)))
    return sorted(f.code for f in UniquenessCheck().run(graph))


# --- the invariant --------------------------------------------------------------


def test_a_colocated_go_test_can_be_owned(tmp_path: Path) -> None:
    """Go puts `parser_test.go` beside `parser.go`, so the owner is the component doc
    itself and no separate test document exists to hold the declaration."""
    root = _go_repo(tmp_path)
    _write(
        root,
        "docs/components/parser.md",
        _doc("parser", describes=["parser/parser.go"], owns_tests=["parser/parser_test.go"]),
    )

    assert _codes(root) == []


def test_an_unowned_test_beside_an_owned_one_is_reported(tmp_path: Path) -> None:
    root = _go_repo(tmp_path)
    _write(root, "parser/scanner_test.go", "package parser\n\nfunc TestScan() {}\n")
    _write(
        root,
        "docs/components/parser.md",
        _doc("parser", describes=["parser/parser.go"], owns_tests=["parser/parser_test.go"]),
    )

    assert _codes(root) == ["test-ownership/unowned-test"]


def test_a_tree_nobody_has_adopted_stays_quiet(tmp_path: Path) -> None:
    """The rule spreads from where it started, so turning the check on does not make
    every existing test file an error at once."""
    root = _go_repo(tmp_path)
    _write(root, "docs/components/parser.md", _doc("parser", describes=["parser/parser.go"]))

    assert _blocking(root) == []
    # Quiet of errors, not silent: the file waived describes ownership by its name, and
    # the hint says nothing is checking who maintains it.
    assert _codes(root) == ["test-ownership/ungoverned-test-file"]


def test_two_owners_are_reported(tmp_path: Path) -> None:
    root = _go_repo(tmp_path)
    _write(
        root,
        "docs/components/parser.md",
        _doc("parser", describes=["parser/parser.go"], owns_tests=["parser/parser_test.go"]),
    )
    _write(
        root,
        "docs/components/other.md",
        _doc("other", describes=[], owns_tests=["parser/parser_test.go"]),
    )

    assert _codes(root) == ["test-ownership/duplicate-test-owner"]


def test_a_shared_test_has_one_owner_and_many_recommenders(tmp_path: Path) -> None:
    """Recommending never claims. An integration test one doc maintains can be the test
    three components tell you to run."""
    root = _go_repo(tmp_path)
    _write(root, "parser/integration_test.go", "package parser\n\nfunc TestAll() {}\n")
    _write(
        root,
        "docs/components/parser.md",
        _doc(
            "parser",
            describes=["parser/parser.go"],
            owns_tests=["parser/parser_test.go", "parser/integration_test.go"],
        ),
    )
    _write(
        root,
        "docs/components/other.md",
        _doc("other", describes=[], recommended_tests=["parser/integration_test.go"]),
    )

    assert _codes(root) == []


# --- the bypasses it must not open ----------------------------------------------


def test_owning_a_source_file_as_a_test_is_refused(tmp_path: Path) -> None:
    root = _go_repo(tmp_path)
    _write(root, "parser/helper.go", "package parser\n\nfunc Helper() {}\n")
    _write(
        root,
        "docs/components/parser.md",
        _doc("parser", describes=["parser/parser.go"], owns_tests=["parser/helper.go"]),
    )

    assert "test-ownership/not-a-test" in _codes(root)


def test_a_test_declaration_does_not_document_a_source_file(tmp_path: Path) -> None:
    """The bypass this whole design exists to refuse: if naming a file under a test field
    counted as owning it, `owns_tests: [src/important.py]` would clear the undocumented
    finding that says nothing describes it."""
    root = tmp_path
    _write(
        root,
        "irminsul.toml",
        'project_name = "t"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n'
        '[languages]\nenabled = ["python"]\n'
        '[checks]\nenabled = ["frontmatter", "uniqueness", "test-ownership"]\n',
    )
    _write(root, "src/important.py", "X = 1\n")
    _write(root, "src/known.py", "Y = 1\n")
    _write(
        root,
        "docs/components/known.md",
        _doc(
            "known",
            describes=["src/known.py"],
            owns_tests=["src/important.py"],
            recommended_tests=["src/important.py"],
        ),
    )

    assert "uniqueness/undocumented-file" in _uniqueness_codes(root)
    assert "test-ownership/not-a-test" in _codes(root)


def test_a_broad_directory_cannot_claim_ownership(tmp_path: Path) -> None:
    root = _go_repo(tmp_path)
    _write(root, "parser/scanner_test.go", "package parser\n\nfunc TestScan() {}\n")
    _write(
        root,
        "docs/components/parser.md",
        _doc("parser", describes=["parser/parser.go"], owns_tests=["parser/"]),
    )

    codes = _codes(root)
    assert "test-ownership/inexact-ownership" in codes
    # And nothing became owned by it, so the adoption gate never opened.
    assert "test-ownership/unowned-test" not in codes


def test_a_glob_cannot_claim_ownership(tmp_path: Path) -> None:
    root = _go_repo(tmp_path)
    _write(
        root,
        "docs/components/parser.md",
        _doc("parser", describes=["parser/parser.go"], owns_tests=["parser/*_test.go"]),
    )

    assert _blocking(root) == ["test-ownership/inexact-ownership"]


def test_owning_a_test_that_is_gone_is_reported(tmp_path: Path) -> None:
    root = _go_repo(tmp_path)
    _write(
        root,
        "docs/components/parser.md",
        _doc(
            "parser",
            describes=["parser/parser.go"],
            owns_tests=["parser/parser_test.go", "parser/removed_test.go"],
        ),
    )

    assert _codes(root) == ["test-ownership/owned-test-missing"]


# --- the two fields, and the one they replace -----------------------------------


def test_recommendations_default_to_the_tests_a_doc_owns(tmp_path: Path) -> None:
    """So an ordinary component writes one list rather than two identical ones."""
    frontmatter = DocFrontmatter(
        id="a", title="A", status="stable", owns_tests=["parser/parser_test.go"]
    )

    assert frontmatter.effective_recommended_tests == ["parser/parser_test.go"]


def test_an_explicit_recommendation_replaces_the_default(tmp_path: Path) -> None:
    frontmatter = DocFrontmatter(
        id="a",
        title="A",
        status="stable",
        owns_tests=["parser/parser_test.go"],
        recommended_tests=["parser/integration_test.go"],
    )

    assert frontmatter.effective_recommended_tests == ["parser/integration_test.go"]


def test_the_legacy_spelling_is_still_read(tmp_path: Path) -> None:
    frontmatter = DocFrontmatter(id="a", title="A", status="stable", tests=["tests/test_a.py"])

    assert frontmatter.effective_recommended_tests == ["tests/test_a.py"]


def test_both_spellings_at_once_is_refused(tmp_path: Path) -> None:
    """Two sources of truth for one answer. Combining them would hide the disagreement,
    so the doc is rejected and somebody picks."""
    with pytest.raises(ValueError, match="same field under two names"):
        DocFrontmatter(
            id="a",
            title="A",
            status="stable",
            tests=["tests/test_a.py"],
            recommended_tests=["tests/test_b.py"],
        )


def test_a_file_cannot_be_owned_as_source_and_as_a_test(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="owned as source or as a test"):
        DocFrontmatter(
            id="a",
            title="A",
            status="stable",
            describes=["src/a.py"],
            owns_tests=["src/a.py"],
        )


def test_the_fixture_repo_reports_every_code(fixture_repo: Callable[[str], Path]) -> None:
    root = fixture_repo("bad-test-ownership")

    assert set(_codes(root)) == {
        "test-ownership/duplicate-test-owner",
        "test-ownership/inexact-ownership",
        "test-ownership/not-a-test",
        "test-ownership/owned-test-missing",
        "test-ownership/ungoverned-test-file",
        "test-ownership/unowned-test",
    }


# --- a declared test root closes the invariant -----------------------------------

_CLOSED_CONFIG = (
    'project_name = "t"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n'
    'test_roots = ["tests"]\n'
    '[languages]\nenabled = ["python"]\n'
    '[checks]\nenabled = ["frontmatter", "uniqueness", "test-ownership"]\n'
)


def _closed_repo(root: Path) -> Path:
    _write(root, "irminsul.toml", _CLOSED_CONFIG)
    _write(root, "src/core.py", "X = 1\n")
    _write(root, "tests/test_core.py", "def test_core(): pass\n")
    _write(root, "tests/deep/test_more.py", "def test_more(): pass\n")
    _write(root, "docs/components/core.md", _doc("core", describes=["src/core.py"]))
    return root


def test_a_declared_test_root_reports_every_unowned_test(tmp_path: Path) -> None:
    """Nothing is owned anywhere, and the progressive rule would therefore stay silent.
    Declaring the root is the agreement that makes silence wrong."""
    root = _closed_repo(tmp_path)

    findings = TestOwnershipCheck().run(build_graph(root, load(find_config(root))))

    assert sorted(f.data["path"] for f in findings) == [
        "tests/deep/test_more.py",
        "tests/test_core.py",
    ]
    assert {f.code for f in findings} == {"test-ownership/unowned-test"}


def test_a_new_test_in_an_untouched_directory_is_caught(tmp_path: Path) -> None:
    """The question the progressive rule answered wrongly: a directory with no owned
    file at all never became covered, so anything added there stayed invisible."""
    root = _closed_repo(tmp_path)
    _write(
        root,
        "docs/components/core.md",
        _doc(
            "core",
            describes=["src/core.py"],
            owns_tests=["tests/test_core.py", "tests/deep/test_more.py"],
        ),
    )
    assert _codes(root) == []

    _write(root, "tests/untouched/test_fresh.py", "def test_fresh(): pass\n")

    findings = TestOwnershipCheck().run(build_graph(root, load(find_config(root))))
    assert [f.data["path"] for f in findings] == ["tests/untouched/test_fresh.py"]


def test_an_undeclared_tree_stays_progressive(tmp_path: Path) -> None:
    """Migration compatibility is the other half: without a declared root, a repository
    that has agreed to nothing is not turned red by enabling the check."""
    root = tmp_path
    _write(root, "irminsul.toml", _CLOSED_CONFIG.replace('test_roots = ["tests"]\n', ""))
    _write(root, "src/core.py", "X = 1\n")
    _write(root, "src/pkg/thing_test.py", "def test_thing(): pass\n")
    _write(root, "docs/components/core.md", _doc("core", describes=["src/core.py"]))

    assert _blocking(root) == []


def test_python_and_go_layouts_are_both_covered(tmp_path: Path) -> None:
    """A top-level tests/ tree and a colocated Go test reach the same invariant by
    different routes — a declared root, and the ordinary source walk."""
    root = tmp_path
    _write(
        root,
        "irminsul.toml",
        'project_name = "t"\n[paths]\ndocs_root = "docs"\nsource_roots = ["parser"]\n'
        'test_roots = ["tests"]\n'
        '[languages]\nenabled = ["python", "go"]\n'
        '[checks]\nenabled = ["frontmatter", "uniqueness", "test-ownership"]\n',
    )
    _write(root, "parser/parser.go", "package parser\n\nfunc Parse() {}\n")
    _write(root, "parser/parser_test.go", "package parser\n\nfunc TestParse() {}\n")
    _write(root, "tests/test_end_to_end.py", "def test_e2e(): pass\n")
    _write(root, "docs/components/parser.md", _doc("parser", describes=["parser/parser.go"]))

    findings = TestOwnershipCheck().run(build_graph(root, load(find_config(root))))
    reported = sorted(f.data["path"] for f in findings)

    # The Go test is not in the declared root, so it waits for a sibling to be owned —
    # and is named by the hint meanwhile rather than vanishing.
    assert reported == ["parser/parser_test.go", "tests/test_end_to_end.py"]
    assert sorted({f.code for f in findings}) == [
        "test-ownership/ungoverned-test-file",
        "test-ownership/unowned-test",
    ]

    _write(
        root,
        "docs/components/parser.md",
        _doc(
            "parser",
            describes=["parser/parser.go"],
            owns_tests=["tests/test_end_to_end.py", "parser/parser_test.go"],
        ),
    )
    assert _codes(root) == []


def test_this_repository_owns_every_test_it_governs() -> None:
    """The invariant, dogfooded. If this fails, a test file was added without an owner."""
    root = Path(__file__).resolve().parents[1]
    graph = build_graph(root, load(find_config(root)))
    check = TestOwnershipCheck()
    governed, closed = check._test_files(graph)

    assert len(governed) > 100, "the declared test root is not being walked"
    assert governed == sorted(closed), "every governed test should sit in the closed scope"
    assert check.run(graph) == []


def test_an_unowned_directory_inside_a_declared_test_root_is_reported(
    fixture_repo: Callable[[str], Path],
) -> None:
    """The case the progressive rule structurally cannot reach: a directory where nothing
    is owned never became covered, so every test added there stayed invisible. Declaring
    the root is what closes it."""
    root = fixture_repo("bad-test-roots")
    graph = build_graph(root, load(find_config(root)))

    findings = TestOwnershipCheck().run(graph)

    assert sorted(f.data["path"] for f in findings) == [
        "tests/fresh/test_fresh.py",
        "tests/nested/deeper/test_deep.py",
    ]
    assert {f.code for f in findings} == {"test-ownership/unowned-test"}
    # The one test that does have an owner is not reported, so the rule is about
    # ownership rather than about the directory being unfamiliar.
    assert "tests/test_core.py" not in {f.data["path"] for f in findings}


def test_the_same_fixture_goes_quiet_once_every_test_is_owned(
    fixture_repo: Callable[[str], Path],
) -> None:
    root = fixture_repo("bad-test-roots")
    doc = root / "docs" / "components" / "core.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(
            "owns_tests:\n  - tests/test_core.py\n",
            "owns_tests:\n  - tests/test_core.py\n"
            "  - tests/fresh/test_fresh.py\n"
            "  - tests/nested/deeper/test_deep.py\n",
        ),
        encoding="utf-8",
    )

    assert _codes(root) == []


# --- the classification contract: every managed file answers to one policy ---------

_MIXED = (
    'project_name = "t"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n'
    'test_roots = ["tests"]\n'
    '[languages]\nenabled = ["python"]\n'
    '[checks]\nenabled = ["frontmatter", "uniqueness", "test-ownership"]\n'
)


def _mixed_repo(root: Path, config: str = _MIXED) -> Path:
    _write(root, "irminsul.toml", config)
    _write(root, "src/core.py", "X = 1\n")
    _write(root, "docs/components/core.md", _doc("core", describes=["src/core.py"]))
    # The declared test root has to exist, or `missing-test-root` becomes the finding
    # under test rather than the one each case is about.
    _write(root, "tests/test_smoke.py", "def test_smoke(): pass\n")
    _write(
        root,
        "docs/components/smoke.md",
        _doc("smoke", describes=[], owns_tests=["tests/test_smoke.py"]),
    )
    return root


def test_a_source_module_named_like_a_test_does_not_vanish(tmp_path: Path) -> None:
    """Scenario 1. `src/irminsul/test_refs.py` was an ordinary module whose name matched a
    test convention: `uniqueness` stopped asking which doc describes it and nothing asked
    who maintains it. The name still waives `describes:`, but no longer in silence."""
    root = _mixed_repo(tmp_path)
    _write(root, "src/test_refs.py", "def resolve(): ...\n")

    codes = _codes(root)
    assert "test-ownership/ungoverned-test-file" in codes
    assert [f.data["path"] for f in _findings(root) if f.code.endswith("ungoverned-test-file")] == [
        "src/test_refs.py"
    ]


def test_naming_it_in_owns_tests_is_the_configuration_path(tmp_path: Path) -> None:
    """...and the diagnostic goes away by answering it, not by renaming around it."""
    root = _mixed_repo(tmp_path)
    _write(root, "src/test_refs.py", "def resolve(): ...\n")
    _write(
        root,
        "docs/components/core.md",
        _doc("core", describes=["src/core.py"], owns_tests=["src/test_refs.py"]),
    )

    assert _codes(root) == []


def test_a_helper_in_a_test_root_is_governed_by_location(tmp_path: Path) -> None:
    """Scenario 7. `tests/helpers.py` matches no test filename convention. Inside a
    declared test root it is still managed, so it cannot disappear between the policies."""
    root = _mixed_repo(tmp_path)
    _write(root, "tests/helpers.py", "def helper(): ...\n")

    assert _codes(root) == ["test-ownership/unowned-test"]


def test_a_project_configured_pattern_recognises_its_own_layout(tmp_path: Path) -> None:
    """Scenario 6. A suite that does not use `test_*.py` says so once in config."""
    root = _mixed_repo(
        tmp_path,
        _MIXED.replace('test_roots = ["tests"]\n', 'test_patterns = ["src/**/check_*.py"]\n'),
    )
    _write(root, "src/check_core.py", "def check(): ...\n")

    codes = _codes(root)
    assert "test-ownership/ungoverned-test-file" in codes
    assert "uniqueness/undocumented-file" not in _uniqueness_codes(root)


def test_overlapping_roots_leave_ordinary_source_under_describes(tmp_path: Path) -> None:
    """Scenario 5. A Go repository may set both roots to the same directory. Location must
    not then capture ordinary source into the test policy."""
    root = tmp_path
    _write(
        root,
        "irminsul.toml",
        'project_name = "t"\n[paths]\ndocs_root = "docs"\nsource_roots = ["."]\n'
        'test_roots = ["."]\nsource_excludes = ["docs/**"]\n'
        '[languages]\nenabled = ["go"]\n'
        '[checks]\nenabled = ["frontmatter", "uniqueness", "test-ownership"]\n',
    )
    _write(root, "main.go", "package main\n")
    _write(root, "main_test.go", "package main\n\nfunc TestMain() {}\n")
    _write(root, "docs/components/main.md", _doc("main", describes=["main.go"]))

    findings = TestOwnershipCheck().run(build_graph(root, load(find_config(root))))
    reported = sorted(f.data["path"] for f in findings)

    # The colocated test is governed; `main.go` is not dragged in with it.
    assert reported == ["main_test.go"]


def test_owning_one_root_level_test_does_not_indict_the_whole_tree(tmp_path: Path) -> None:
    """`parent.parents` reaches `.`, so a repository-root owned test used to cover every
    directory at once — the opposite of progressive adoption."""
    root = tmp_path
    _write(
        root,
        "irminsul.toml",
        'project_name = "t"\n[paths]\ndocs_root = "docs"\nsource_roots = ["."]\n'
        'source_excludes = ["docs/**"]\n'
        '[languages]\nenabled = ["go"]\n'
        '[checks]\nenabled = ["frontmatter", "test-ownership"]\n',
    )
    _write(root, "main.go", "package main\n")
    _write(root, "main_test.go", "package main\n")
    _write(root, "pkg/a/a_test.go", "package a\n")
    _write(root, "pkg/b/b_test.go", "package b\n")
    _write(root, "docs/components/main.md", _doc("main", describes=[], owns_tests=["main_test.go"]))

    findings = TestOwnershipCheck().run(build_graph(root, load(find_config(root))))

    assert [f.code for f in findings if f.code.endswith("unowned-test")] == []


def test_a_mistyped_test_root_is_reported(tmp_path: Path) -> None:
    """Silence here degraded the closed invariant to the progressive one while the config
    still read as though it were enforced."""
    root = _mixed_repo(tmp_path, _MIXED.replace('test_roots = ["tests"]', 'test_roots = ["test"]'))

    assert "test-ownership/missing-test-root" in _codes(root)


def _findings(root: Path) -> list:
    return TestOwnershipCheck().run(build_graph(root, load(find_config(root))))
