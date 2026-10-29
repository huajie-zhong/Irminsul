"""Tests for DependencyCheck (import-deps)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from irminsul.checks.dependency_check import DependencyCheck, SourceOwnership, resolve_ownership
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph

from .conftest import run_check, write_config


def _findings(repo: Path) -> list:
    return run_check(DependencyCheck, repo)


def test_hallucinated_dep_flagged(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("bad-dependency")
    findings = _findings(repo)
    hallucinated = [f for f in findings if "declared but no import" in f.message]
    assert any("renderer" in f.message for f in hallucinated)


def test_good_fixture_no_findings(fixture_repo: Callable[[str], Path]) -> None:
    repo = fixture_repo("good")
    assert _findings(repo) == []


def _two_docs(tmp_path: Path, files: dict[str, str], a_describes: str, b_describes: str) -> Path:
    """Doc `a` declares `depends_on: [b]`; each owns the files its glob names."""
    write_config(tmp_path, project_name="p", source_roots=["src"])
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    docs = tmp_path / "docs" / "components"
    docs.mkdir(parents=True)
    for doc_id, describes, extra in [
        ("a", a_describes, "depends_on:\n  - b\n"),
        ("b", b_describes, ""),
    ]:
        (docs / f"{doc_id}.md").write_text(
            f"---\nid: {doc_id}\ntitle: {doc_id}\nstatus: stable\ndescribes:\n"
            f"  - {describes}\n{extra}---\n\n# {doc_id}\n",
            encoding="utf-8",
        )
    return tmp_path


@pytest.mark.parametrize(
    "importing",
    [
        "import pkg.b",
        "from pkg.b import x",
        "from pkg import b",
        "from . import b",
        "from .b import x",
    ],
)
def test_every_python_import_form_backs_a_dependency(tmp_path: Path, importing: str) -> None:
    files = {
        "src/pkg/__init__.py": "",
        "src/pkg/a.py": f"{importing}\n",
        "src/pkg/b.py": "x = 1\n",
    }
    repo = _two_docs(tmp_path, files, "src/pkg/a.py", "src/pkg/b.py")
    assert _findings(repo) == []


def test_a_dependency_no_import_backs_is_still_reported(tmp_path: Path) -> None:
    files = {"src/pkg/__init__.py": "", "src/pkg/a.py": "import json\n", "src/pkg/b.py": "x = 1\n"}
    repo = _two_docs(tmp_path, files, "src/pkg/a.py", "src/pkg/b.py")
    assert [f.message for f in _findings(repo)] == [
        "depends_on 'b' declared but no import relationship found"
    ]


@pytest.mark.parametrize(
    ("files", "a_describes", "b_describes"),
    [
        (
            {"src/a.ts": "import { b } from './b';\n", "src/b.ts": "export const b = 1;\n"},
            "src/a.ts",
            "src/b.ts",
        ),
        ({"src/a.py": "import json\n", "src/b.yml": "key: value\n"}, "src/a.py", "src/b.yml"),
    ],
    ids=["typescript-importer", "dependency-owns-no-python"],
)
def test_a_relationship_python_imports_cannot_show_is_not_judged(
    tmp_path: Path, files: dict[str, str], a_describes: str, b_describes: str
) -> None:
    assert _findings(_two_docs(tmp_path, files, a_describes, b_describes)) == []


def test_a_python_file_that_is_not_utf8_is_not_read(tmp_path: Path) -> None:
    files = {"src/pkg/__init__.py": "", "src/pkg/a.py": "import json\n", "src/pkg/b.py": "x = 1\n"}
    repo = _two_docs(tmp_path, files, "src/pkg/a.py", "src/pkg/b.py")
    (repo / "src" / "pkg" / "a.py").write_bytes(b"x = '\xff\xfe'\n")
    assert [f.message for f in _findings(repo)] == [
        "depends_on 'b' declared but no import relationship found"
    ]


def _ownership(repo: Path) -> SourceOwnership:
    return resolve_ownership(build_graph(repo, load(find_config(repo))))


def test_owner_of_answers_for_every_spelling_of_an_owned_file(tmp_path: Path) -> None:
    files = {"src/pkg/__init__.py": "", "src/pkg/a.py": "x = 1\n", "src/pkg/b.py": "x = 1\n"}
    repo = _two_docs(tmp_path, files, "src/pkg/a.py", "src/pkg/b.py")
    ownership = _ownership(repo)
    assert ownership.owner_of(repo / "src" / "pkg" / "b.py") == "b"
    assert ownership.owner_of(repo / "src" / "pkg" / ".." / "pkg" / "b.py") == "b"
    assert ownership.owner_of(repo / "src" / "pkg" / "a.py") == "a"


def test_owner_of_is_none_for_a_file_that_is_not_there_or_not_owned(tmp_path: Path) -> None:
    files = {"src/pkg/__init__.py": "", "src/pkg/a.py": "x = 1\n", "src/pkg/b.py": "x = 1\n"}
    repo = _two_docs(tmp_path, files, "src/pkg/a.py", "src/pkg/b.py")
    ownership = _ownership(repo)
    assert ownership.owner_of(repo / "src" / "pkg" / "missing.py") is None
    assert ownership.owner_of(repo / "src" / "pkg" / "__init__.py") is None
    assert ownership.owner_of(repo / "src" / "nothing" / "__init__.py") is None
    assert ownership.owner_of(repo / "src" / "pkg" / "missing.py") is None


def test_a_file_symlink_backs_the_dependency_on_what_it_points_at(tmp_path: Path) -> None:
    files = {
        "src/pkg/__init__.py": "",
        "src/pkg/a.py": "import alias\n",
        "src/pkg/b.py": "x = 1\n",
    }
    repo = _two_docs(tmp_path, files, "src/pkg/a.py", "src/pkg/b.py")
    try:
        (repo / "src" / "alias.py").symlink_to(Path("pkg") / "b.py")
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    assert _findings(repo) == []


def _docs_repo_beside_code(tmp_path: Path, a_source: str) -> Path:
    docs_repo = tmp_path / "docs-repo"
    code = tmp_path / "code" / "src" / "pkg"
    code.mkdir(parents=True)
    (code / "__init__.py").write_text("", encoding="utf-8")
    (code / "a.py").write_text(a_source, encoding="utf-8")
    (code / "b.py").write_text("x = 1\n", encoding="utf-8")
    docs_repo.mkdir()
    (docs_repo / "irminsul.toml").write_text(
        'project_name = "p"\n[paths]\ndocs_root = "docs"\nsource_roots = ["../code/src"]\n',
        encoding="utf-8",
    )
    components = docs_repo / "docs" / "components"
    components.mkdir(parents=True)
    for doc_id, describes, extra in [
        ("a", "pkg/a.py", "depends_on:\n  - b\n"),
        ("b", "pkg/b.py", ""),
    ]:
        (components / f"{doc_id}.md").write_text(
            f"---\nid: {doc_id}\ntitle: {doc_id}\nstatus: stable\ndescribes:\n"
            f"  - {describes}\n{extra}---\n\n# {doc_id}\n",
            encoding="utf-8",
        )
    return docs_repo


def test_a_source_root_beside_the_docs_repo_backs_the_dependency(tmp_path: Path) -> None:
    assert _findings(_docs_repo_beside_code(tmp_path, "from pkg import b\n")) == []


def test_a_source_root_beside_the_docs_repo_still_reports_a_missing_import(
    tmp_path: Path,
) -> None:
    repo = _docs_repo_beside_code(tmp_path, "import json\n")
    assert [f.message for f in _findings(repo)] == [
        "depends_on 'b' declared but no import relationship found"
    ]


def test_owner_of_names_a_file_in_a_source_root_beside_the_docs_repo(tmp_path: Path) -> None:
    repo = _docs_repo_beside_code(tmp_path, "import json\n")
    assert _ownership(repo).owner_of(tmp_path / "code" / "src" / "pkg" / "b.py") == "b"
