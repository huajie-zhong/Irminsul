"""End-to-end tests for the private-docs topologies.

The supported story: an open-source code repository whose Irminsul docs tree
stays private. Two layouts make that work, and these tests are the contract
that both keep working:

- **Topology A** — the private docs repo is primary; the public code repo is
  cloned inside it as a gitignored subfolder and `paths.source_roots` points
  into it.
- **Topology B** — the public code repo is primary; `docs/` is itself a
  separate (private) git repository, gitignored by the outer repo.

Both need real git history, so each test bootstraps repos in `tmp_path`.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from git import Repo
from typer.testing import CliRunner

from irminsul.cli import app
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph
from irminsul.git.mtime import last_commit_time_any_repo

runner = CliRunner()

_DOC = """---
id: core
title: Core
audience: explanation
tier: 3
status: stable
describes:
  - {claim}
tests:
  - tests/
---

# Core

The core module.

## Scope & Limitations
None.
"""

_INDEX = """---
id: 20-components
title: Components
audience: reference
tier: 3
status: stable
describes: []
tests:
  - tests/
---

# Components

- [`core`](core.md)

## Scope & Limitations
Index.
"""


def _init_repo(root: Path) -> Repo:
    root.mkdir(parents=True, exist_ok=True)
    repo = Repo.init(root)
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "Test")
        cw.set_value("user", "email", "test@example.com")
        cw.set_value("commit", "gpgsign", "false")
    return repo


def _commit_all(repo: Repo, message: str, *, when: _dt.datetime | None = None) -> None:
    repo.git.add(A=True)
    if when is None:
        repo.index.commit(message)
    else:
        repo.index.commit(message, author_date=when, commit_date=when)


def _config_toml(source_root: str) -> str:
    return (
        'project_name = "private-docs"\n'
        '[paths]\ndocs_root = "docs"\n'
        f'source_roots = ["{source_root}"]\n'
    )


def _build_topology_a(tmp_path: Path) -> Path:
    """Private docs repo with the public code repo as a gitignored subfolder."""
    docs_repo_root = tmp_path / "docs-repo"

    code_repo = _init_repo(docs_repo_root / "code")
    src = docs_repo_root / "code" / "src"
    src.mkdir(parents=True)
    (src / "core.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    _commit_all(code_repo, "public code")
    code_repo.close()

    docs_repo = _init_repo(docs_repo_root)
    (docs_repo_root / ".gitignore").write_text("/code/\n", encoding="utf-8")
    (docs_repo_root / "irminsul.toml").write_text(_config_toml("code/src"), encoding="utf-8")
    (docs_repo_root / "tests").mkdir()
    (docs_repo_root / "tests" / ".keep").write_text("", encoding="utf-8")
    components = docs_repo_root / "docs" / "20-components"
    components.mkdir(parents=True)
    (components / "INDEX.md").write_text(_INDEX, encoding="utf-8")
    (components / "core.md").write_text(_DOC.format(claim="code/src/core.py"), encoding="utf-8")
    _commit_all(docs_repo, "private docs repo")
    docs_repo.close()
    return docs_repo_root


def _build_topology_b(tmp_path: Path, *, doc_when: _dt.datetime | None = None) -> Path:
    """Public code repo whose docs/ is a nested, gitignored private repo."""
    code_repo_root = tmp_path / "public-repo"

    code_repo = _init_repo(code_repo_root)
    src = code_repo_root / "src"
    src.mkdir(parents=True)
    (src / "core.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (code_repo_root / ".gitignore").write_text("/docs/\n", encoding="utf-8")
    (code_repo_root / "irminsul.toml").write_text(_config_toml("src"), encoding="utf-8")
    (code_repo_root / "tests").mkdir()
    (code_repo_root / "tests" / ".keep").write_text("", encoding="utf-8")
    _commit_all(code_repo, "public code")
    code_repo.close()

    docs_repo = _init_repo(code_repo_root / "docs")
    components = code_repo_root / "docs" / "20-components"
    components.mkdir(parents=True)
    (components / "INDEX.md").write_text(_INDEX, encoding="utf-8")
    (components / "core.md").write_text(_DOC.format(claim="src/core.py"), encoding="utf-8")
    _commit_all(docs_repo, "private docs", when=doc_when)
    docs_repo.close()
    return code_repo_root


def test_topology_a_checks_pass_across_the_repo_boundary(tmp_path: Path) -> None:
    repo_root = _build_topology_a(tmp_path)
    result = runner.invoke(app, ["check", "--profile", "configured", "--path", str(repo_root)])
    assert result.exit_code == 0, result.output
    assert "0 errors, 0 warnings" in result.output


def test_topology_a_claims_resolve_into_the_gitignored_code_repo(tmp_path: Path) -> None:
    repo_root = _build_topology_a(tmp_path)
    result = runner.invoke(app, ["context", "code/src/core.py", "--path", str(repo_root)])
    assert result.exit_code == 0, result.output
    assert "owner: core" in result.output


def test_topology_a_mtime_uses_nested_code_history(tmp_path: Path) -> None:
    repo_root = _build_topology_a(tmp_path)
    code_repo = Repo(repo_root / "code")
    expected_sha = code_repo.head.commit.hexsha
    code_repo.close()

    git_time = last_commit_time_any_repo(repo_root / "code" / "src" / "core.py", repo_root)
    assert git_time is not None
    assert git_time.sha == expected_sha


def test_topology_b_checks_pass_with_nested_private_docs_repo(tmp_path: Path) -> None:
    repo_root = _build_topology_b(tmp_path)
    result = runner.invoke(app, ["check", "--profile", "configured", "--path", str(repo_root)])
    assert result.exit_code == 0, result.output
    assert "0 errors, 0 warnings" in result.output


def test_topology_b_claims_and_context_resolve(tmp_path: Path) -> None:
    repo_root = _build_topology_b(tmp_path)
    result = runner.invoke(app, ["context", "src/core.py", "--path", str(repo_root)])
    assert result.exit_code == 0, result.output
    assert "owner: core" in result.output


def test_topology_b_mtime_drift_crosses_the_nested_repo_boundary(tmp_path: Path) -> None:
    """The doc's commit time comes from the nested docs repo, the source's from
    the outer repo — drift between them must still be measurable."""
    old = _dt.datetime(2024, 1, 1, tzinfo=_dt.UTC)
    repo_root = _build_topology_b(tmp_path, doc_when=old)

    config = load(find_config(repo_root))
    graph = build_graph(repo_root, config)
    from irminsul.checks.mtime_drift import MtimeDriftCheck

    findings = [f for f in MtimeDriftCheck().run(graph) if "drift" in f.message]
    assert len(findings) == 1
    assert findings[0].doc_id == "core"


def test_topology_b_nested_history_wins_after_outer_repo_migration(tmp_path: Path) -> None:
    repo_root = tmp_path / "migrated-public-repo"
    outer_repo = _init_repo(repo_root)
    components = repo_root / "docs" / "20-components"
    components.mkdir(parents=True)
    doc = components / "core.md"
    doc.write_text(_DOC.format(claim="src/core.py"), encoding="utf-8")
    (components / "INDEX.md").write_text(_INDEX, encoding="utf-8")
    _commit_all(
        outer_repo,
        "docs were once public",
        when=_dt.datetime(2025, 1, 1, tzinfo=_dt.UTC),
    )

    (repo_root / ".gitignore").write_text("/docs/\n", encoding="utf-8")
    outer_repo.index.add([".gitignore"])
    outer_repo.git.rm("-r", "--cached", "docs")
    outer_repo.index.commit(
        "move docs to private history",
        author_date=_dt.datetime(2025, 2, 1, tzinfo=_dt.UTC),
        commit_date=_dt.datetime(2025, 2, 1, tzinfo=_dt.UTC),
    )
    outer_sha = outer_repo.head.commit.hexsha
    outer_repo.close()

    nested_repo = _init_repo(repo_root / "docs")
    _commit_all(
        nested_repo,
        "private docs history",
        when=_dt.datetime(2024, 1, 1, tzinfo=_dt.UTC),
    )
    nested_sha = nested_repo.head.commit.hexsha
    nested_repo.close()

    git_time = last_commit_time_any_repo(doc, repo_root)
    assert git_time is not None
    assert git_time.sha == nested_sha
    assert git_time.sha != outer_sha


def test_topology_b_doc_edits_invisible_to_outer_diff_is_a_known_limit(
    tmp_path: Path,
) -> None:
    """`context --changed` diffs the outer repo only; nested docs-repo edits do
    not appear. This pins the documented limitation so a behavior change shows
    up as a test failure rather than silent drift from the doc."""
    repo_root = _build_topology_b(tmp_path)
    doc = repo_root / "docs" / "20-components" / "core.md"
    doc.write_text(doc.read_text(encoding="utf-8") + "\nEdited.\n", encoding="utf-8")

    result = runner.invoke(app, ["context", "--changed", "--path", str(repo_root)])
    assert result.exit_code == 0, result.output
    assert "core.md" not in result.output
