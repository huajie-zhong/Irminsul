"""Which tests `irminsul context` names for a path, in what order, and why.

The owner's declared tests are the starting set. Every test in the declared test roots that
imports the file joins them, whichever doc owns it, and they are ordered by evidence: the
importers first, then the commits that changed test and file together, then the rest.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from irminsul.config import find_config, load
from irminsul.context import build_context_report
from irminsul.git.reader import GitReader

from .conftest import commit_all, git_init, invoke, write, write_config

_CORE = "src/pkg/core.py"
_CORE_DOC = "docs/components/core.md"


def _component(doc_id: str, describes: str, owns: list[str]) -> str:
    lines = [
        "---",
        f"id: {doc_id}",
        f"title: {doc_id.title()}",
        "status: stable",
        f"summary: The {doc_id} component.",
        "describes:",
        f"  - {describes}",
        "owns_tests:",
        *(f"  - {test}" for test in owns),
    ]
    return "\n".join([*lines, "---", "", f"# {doc_id.title()}", "", "Text.", ""])


def _ranking_repo(tmp_path: Path) -> Path:
    """`core` owns four tests, `other` owns a fifth that also imports core's file.

    History, so that the counts are known: `test_alpha.py` changed with `core.py` in two
    commits and `test_beta.py` in one; `test_zeta.py` never did, and only mentions "core"
    in a comment. `test_core.py` and `test_other.py` import it and never changed with it.
    """
    repo = tmp_path / "rank"
    write_config(repo, source_roots=["src"], extra='test_roots = ["tests"]\n')
    git_init(repo)
    write(repo, _CORE, "def run():\n    return 1\n")
    write(repo, "src/pkg/other.py", "def go():\n    return 2\n")
    write(
        repo,
        _CORE_DOC,
        _component(
            "core",
            _CORE,
            [
                "tests/test_alpha.py",
                "tests/test_beta.py",
                "tests/test_core.py",
                "tests/test_zeta.py",
            ],
        ),
    )
    write(
        repo,
        "docs/components/other.md",
        _component("other", "src/pkg/other.py", ["tests/test_other.py"]),
    )
    commit_all(repo, "docs and source")
    write(repo, "tests/test_zeta.py", "# nothing to do with core\n\n\ndef test_zeta():\n    pass\n")
    commit_all(repo, "zeta")
    write(repo, "tests/test_alpha.py", "def test_alpha():\n    pass\n")
    write(repo, _CORE, "def run():\n    return 11\n")
    commit_all(repo, "alpha with core")
    write(repo, "tests/test_alpha.py", "def test_alpha():\n    assert True\n")
    write(repo, "tests/test_beta.py", "def test_beta():\n    pass\n")
    write(repo, _CORE, "def run():\n    return 12\n")
    commit_all(repo, "alpha and beta with core")
    write(repo, "tests/test_core.py", "from pkg.core import run\n\n\ndef test_core():\n    run()\n")
    write(repo, "tests/test_other.py", "import pkg.core as c\n\n\ndef test_other():\n    c.run()\n")
    commit_all(repo, "importers")
    return repo


def _context(repo: Path, *paths: str) -> dict[str, Any]:
    code, output = invoke(repo, "context", *paths, "--format", "json")
    assert code in (0, 1), output
    data: dict[str, Any] = json.loads(output)
    return data


def test_tests_importing_the_file_come_first_whichever_doc_owns_them(tmp_path: Path) -> None:
    repo = _ranking_repo(tmp_path)

    [result] = _context(repo, _CORE)["results"]

    assert result["tests"][:2] == ["tests/test_core.py", "tests/test_other.py"]
    assert set(result["test_reasons"]) >= {"tests/test_core.py", "tests/test_other.py"}
    assert result["test_reasons"]["tests/test_core.py"] == [f"imports {_CORE}"]


def test_tests_that_changed_with_the_file_follow_by_commit_count(tmp_path: Path) -> None:
    repo = _ranking_repo(tmp_path)

    [result] = _context(repo, _CORE)["results"]

    assert result["tests"] == [
        "tests/test_core.py",
        "tests/test_other.py",
        "tests/test_alpha.py",
        "tests/test_beta.py",
        "tests/test_zeta.py",
    ]
    assert result["test_reasons"]["tests/test_alpha.py"] == ["changed with it in 2 commits"]
    assert result["test_reasons"]["tests/test_beta.py"] == ["changed with it in 1 commit"]


def test_a_test_owned_by_another_doc_says_who_owns_it(tmp_path: Path) -> None:
    repo = _ranking_repo(tmp_path)

    [result] = _context(repo, _CORE)["results"]

    assert result["test_reasons"]["tests/test_other.py"] == [
        f"imports {_CORE}",
        "owned by docs/components/other.md",
    ]
    assert "owned by" not in " ".join(result["test_reasons"]["tests/test_core.py"])


def test_a_comment_naming_the_module_is_not_an_import(tmp_path: Path) -> None:
    repo = _ranking_repo(tmp_path)

    [result] = _context(repo, _CORE)["results"]

    assert "tests/test_zeta.py" not in result["test_reasons"]
    assert result["tests"][-1] == "tests/test_zeta.py"


def test_a_commit_over_thirty_files_does_not_count_as_changing_together(tmp_path: Path) -> None:
    repo = _ranking_repo(tmp_path)
    for index in range(31):
        write(repo, f"data/sample_{index}.txt", f"{index}\n")
    write(repo, "tests/test_zeta.py", "def test_zeta():\n    pass\n")
    write(repo, _CORE, "def run():\n    return 13\n")
    commit_all(repo, "sweep")

    [result] = _context(repo, _CORE)["results"]

    assert "tests/test_zeta.py" not in result["test_reasons"]


def test_ranking_starts_exactly_one_git_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _ranking_repo(tmp_path)
    started: list[tuple[str, ...]] = []
    original_run = GitReader.run_live

    def recording_run(self: GitReader, repo_root: Path, *args: str) -> Any:
        started.append(args)
        return original_run(self, repo_root, *args)

    monkeypatch.setattr(GitReader, "run_live", recording_run)

    report = build_context_report(repo, load(find_config(repo)), target_paths=[repo / _CORE])

    assert len(started) == 1
    assert "log" in started[0] and "--full-diff" in started[0]
    assert report.results[0].test_reasons["tests/test_alpha.py"] == ["changed with it in 2 commits"]


def test_plain_output_lists_each_reasoned_test_then_counts_the_rest(tmp_path: Path) -> None:
    repo = _ranking_repo(tmp_path)

    code, output = invoke(repo, "context", _CORE)

    assert code == 0, output
    assert (
        "  tests:\n"
        f"    tests/test_core.py: imports {_CORE}\n"
        f"    tests/test_other.py: imports {_CORE}; owned by docs/components/other.md\n"
        "    tests/test_alpha.py: changed with it in 2 commits\n"
        "    tests/test_beta.py: changed with it in 1 commit\n"
        f"    … 1 more owned by {_CORE_DOC} (--format json lists every test)\n"
    ) in output.replace("\r\n", "\n")


def test_plain_output_shows_ten_tests_and_counts_the_rest_when_none_has_a_reason(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "many"
    write_config(repo, source_roots=["src"], extra='test_roots = ["tests"]\n')
    tests = [f"tests/test_{letter}.py" for letter in "abcdefghijkl"]
    write(repo, "src/pkg/lonely.py", "X = 1\n")
    write(repo, _CORE_DOC, _component("core", "src/pkg/lonely.py", tests))
    git_init(repo)
    commit_all(repo, "source and doc")
    for test in tests:
        write(repo, test, "def test_it():\n    pass\n")
    commit_all(repo, "tests")

    code, output = invoke(repo, "context", "src/pkg/lonely.py")
    data = _context(repo, "src/pkg/lonely.py")

    assert code == 0, output
    plain = output.replace("\r\n", "\n")
    shown = "".join(f"    {test}\n" for test in tests[:10])
    assert (
        f"  tests:\n{shown}    … 2 more owned by {_CORE_DOC} (--format json lists every test)\n"
        in plain
    )
    assert tests[10] not in plain
    assert data["results"][0]["tests"] == tests
    assert data["results"][0]["test_reasons"] == {}


def test_few_tests_with_no_reason_stay_on_one_line(tmp_path: Path) -> None:
    repo = tmp_path / "few"
    write_config(repo, source_roots=["src"], extra='test_roots = ["tests"]\n')
    write(repo, "src/pkg/lonely.py", "X = 1\n")
    write(
        repo,
        _CORE_DOC,
        _component("core", "src/pkg/lonely.py", ["tests/test_a.py", "tests/test_b.py"]),
    )
    git_init(repo)
    commit_all(repo, "source and doc")
    write(repo, "tests/test_a.py", "def test_a():\n    pass\n")
    write(repo, "tests/test_b.py", "def test_b():\n    pass\n")
    commit_all(repo, "tests")

    _, output = invoke(repo, "context", "src/pkg/lonely.py")

    assert "  tests: tests/test_a.py, tests/test_b.py" in output


def test_a_doc_path_keeps_its_declared_order_and_has_no_reasons(tmp_path: Path) -> None:
    repo = _ranking_repo(tmp_path)

    [result] = _context(repo, _CORE_DOC)["results"]

    assert result["tests"] == [
        "tests/test_alpha.py",
        "tests/test_beta.py",
        "tests/test_core.py",
        "tests/test_zeta.py",
    ]
    assert result["test_reasons"] == {}


def test_a_sibling_code_repo_ranks_by_its_imports_and_its_own_history(tmp_path: Path) -> None:
    code = tmp_path / "ws" / "code"
    docs = tmp_path / "ws" / "docs"
    write(code, "src/app/core.py", "def start():\n    return 1\n")
    git_init(code)
    commit_all(code, "core")
    write(code, "tests/test_a.py", "def test_a():\n    pass\n")
    write(code, "tests/test_b.py", "def test_b():\n    pass\n")
    write(
        code,
        "tests/test_core.py",
        "from app.core import start\n\n\ndef test_core():\n    start()\n",
    )
    commit_all(code, "tests")
    write(code, "src/app/core.py", "def start():\n    return 2\n")
    write(code, "tests/test_b.py", "def test_b():\n    assert True\n")
    commit_all(code, "core with b")
    write_config(
        docs,
        source_roots=["../code/src"],
        extra='test_roots = ["../code/tests"]\n',
    )
    write(
        docs,
        "docs/components/core.md",
        _component("core", "app/core.py", ["test_a.py", "test_b.py", "test_core.py"]),
    )

    [result] = _context(docs, "app/core.py")["results"]

    assert result["tests"] == ["test_core.py", "test_b.py", "test_a.py"]
    assert result["test_reasons"] == {
        "test_core.py": ["imports app/core.py"],
        "test_b.py": ["changed with it in 1 commit"],
    }
