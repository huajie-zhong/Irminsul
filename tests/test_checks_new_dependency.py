"""Tests for the new-dependency diff pass.

Built on a real git repository rather than a fixture tree: the pass compares a file with
its own content at a base ref, so there is nothing to test without history.
"""

from __future__ import annotations

from pathlib import Path

from git import Repo

from irminsul.checks.new_dependency import CODE_UNDECLARED_NEW_DEPENDENCY, run_new_dependency
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph
from irminsul.git.changes import working_tree_changed_paths

ALPHA = "from mylib.shared import helper\n\n\ndef run() -> None:\n    helper()\n"
BETA = "def helper() -> None:\n    pass\n"


def _doc(doc_id: str, describes: str, *, depends_on: list[str] | None = None) -> str:
    declared = "".join(f"  - {dep}\n" for dep in depends_on or [])
    block = f"depends_on:\n{declared}" if declared else ""
    return (
        f"---\nid: {doc_id}\ntitle: {doc_id}\nstatus: stable\n{block}"
        f"describes:\n  - {describes}\n---\n\n# {doc_id}\n\nOwns it.\n"
    )


def _repo(tmp_path: Path, *, alpha_depends: list[str] | None = None) -> Path:
    root = tmp_path / "r"
    (root / "src" / "mylib").mkdir(parents=True)
    (root / "src" / "mylib" / "alpha.py").write_text(
        "def run() -> None:\n    pass\n", encoding="utf-8"
    )
    (root / "src" / "mylib" / "shared.py").write_text(BETA, encoding="utf-8")
    docs = root / "docs" / "components"
    docs.mkdir(parents=True)
    (docs / "alpha.md").write_text(
        _doc("alpha", "src/mylib/alpha.py", depends_on=alpha_depends), encoding="utf-8"
    )
    (docs / "shared.md").write_text(_doc("shared", "src/mylib/shared.py"), encoding="utf-8")
    (root / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
        encoding="utf-8",
    )
    repo = Repo.init(root)
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "Test")
        cw.set_value("user", "email", "test@example.com")
    repo.git.add("-A")
    repo.index.commit("base")
    repo.close()
    return root


def _run(root: Path) -> list:
    config = load(find_config(root))
    changed = frozenset(working_tree_changed_paths(root))
    graph = build_graph(root, config)
    return run_new_dependency(graph, "HEAD", changed)


def test_an_import_the_change_added_is_reported(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "src" / "mylib" / "alpha.py").write_text(ALPHA, encoding="utf-8")

    [finding] = _run(root)

    assert finding.code == CODE_UNDECLARED_NEW_DEPENDENCY
    assert finding.doc_id == "alpha"
    assert "added an import of shared" in finding.message
    assert "add shared to depends_on" in (finding.suggestion or "")


def test_a_deferred_import_is_reported_too(tmp_path: Path) -> None:
    """Moving the import inside a function is how a module-level one gets avoided, so
    the pass reads the whole AST rather than the file's top."""
    root = _repo(tmp_path)
    (root / "src" / "mylib" / "alpha.py").write_text(
        "def run() -> None:\n    from mylib.shared import helper\n\n    helper()\n",
        encoding="utf-8",
    )

    [finding] = _run(root)

    assert "added an import of shared" in finding.message


def test_a_declared_dependency_is_silent(tmp_path: Path) -> None:
    root = _repo(tmp_path, alpha_depends=["shared"])
    (root / "src" / "mylib" / "alpha.py").write_text(ALPHA, encoding="utf-8")

    assert _run(root) == []


def test_an_edge_that_already_existed_is_silent(tmp_path: Path) -> None:
    """Undeclared edges already in the tree stay quiet: the pass reports what this change
    added, so adopting it needs no migration."""
    root = _repo(tmp_path)
    alpha = root / "src" / "mylib" / "alpha.py"
    alpha.write_text(ALPHA, encoding="utf-8")
    repo = Repo(root)
    repo.git.add("-A")
    repo.index.commit("undeclared edge lands")
    repo.close()

    # The edge is still undeclared, and editing the file again says nothing about it.
    alpha.write_text(ALPHA + "\n\ndef more() -> None:\n    pass\n", encoding="utf-8")

    assert _run(root) == []


def test_a_change_that_adds_no_edge_is_silent(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "src" / "mylib" / "alpha.py").write_text(
        "def run() -> None:\n    return None\n", encoding="utf-8"
    )

    assert _run(root) == []
