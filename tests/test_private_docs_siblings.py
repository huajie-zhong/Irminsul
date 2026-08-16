"""End-to-end tests for the `siblings` layout.

The supported story: an open-source code repository whose Irminsul docs tree
stays private. One layout makes that work — a parent workspace directory
holding two separate git repositories side by side:

    workspace/
      code/     the public repo
      docs/     the private repo; holds irminsul.toml and docs/

`paths.source_roots` reach out through `../code/...`, and git-time lookups
resolve through each file's own nearest enclosing `.git`, which is what lets
every check work across the repository boundary. Files outside the docs repo
carry a source-root-relative display path, so a claim on `../code/src/core.py`
is written `core.py`.

These need real git history, so each test bootstraps both repos in `tmp_path`.
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


def _build_siblings(
    tmp_path: Path,
    *,
    doc_when: _dt.datetime | None = None,
    code_when: _dt.datetime | None = None,
) -> Path:
    """A workspace holding a public `code/` repo and a private `docs/` repo.

    Returns the docs repo root — the directory irminsul is invoked from, and
    the one that owns `irminsul.toml`.
    """
    workspace = tmp_path / "workspace"

    code_repo = _init_repo(workspace / "code")
    src = workspace / "code" / "src"
    src.mkdir(parents=True)
    (src / "core.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    _commit_all(code_repo, "public code", when=code_when)
    code_repo.close()

    docs_repo_root = workspace / "docs"
    docs_repo = _init_repo(docs_repo_root)
    (docs_repo_root / "irminsul.toml").write_text(
        'project_name = "private-docs"\n'
        '[paths]\ndocs_root = "docs"\n'
        'source_roots = ["../code/src"]\n',
        encoding="utf-8",
    )
    (docs_repo_root / "tests").mkdir()
    (docs_repo_root / "tests" / ".keep").write_text("", encoding="utf-8")
    components = docs_repo_root / "docs" / "20-components"
    components.mkdir(parents=True)
    (components / "INDEX.md").write_text(_INDEX, encoding="utf-8")
    (components / "core.md").write_text(_DOC.format(claim="core.py"), encoding="utf-8")
    _commit_all(docs_repo, "private docs repo", when=doc_when)
    docs_repo.close()
    return docs_repo_root


def _write_claim_doc(repo_root: Path, evidence: str) -> None:
    """A foundation doc whose claim cites a file in the sibling code repo.

    `claim-provenance` only inspects `00-foundation/` and `10-architecture/`,
    so the claim has to live there for the evidence spelling to be exercised.
    """
    foundation = repo_root / "docs" / "00-foundation"
    foundation.mkdir(parents=True, exist_ok=True)
    (foundation / "purpose.md").write_text(
        "\n".join(
            [
                "---",
                "id: purpose",
                "title: Purpose",
                "audience: explanation",
                "tier: 2",
                "status: stable",
                "describes: []",
                "claims:",
                "  - id: core-works",
                "    state: implemented",
                "    kind: feature",
                "    claim: The core module exists.",
                "    evidence:",
                f"      - {evidence}",
                "---",
                "",
                "# Purpose",
                "",
                "The core module is real. <!-- claim:core-works -->",
                "",
                "## Scope & Limitations",
                "None.",
            ]
        ),
        encoding="utf-8",
    )


def _claim_findings(repo_root: Path) -> list[str]:
    from irminsul.checks.doc_reality import ClaimProvenanceCheck

    config = load(find_config(repo_root))
    graph = build_graph(repo_root, config)
    return [f.message for f in ClaimProvenanceCheck().run(graph)]


def test_claim_evidence_uses_the_source_root_relative_spelling(tmp_path: Path) -> None:
    """One spelling for the whole tool. `describes:`, the source walk and
    `mtime-drift` all address a sibling source file by its source-root-relative
    display path, and `claims[].evidence` now reads the same spelling — so a
    claim on `../code/src/core.py` is written `core.py`, exactly as the doc
    glob writes it."""
    repo_root = _build_siblings(tmp_path)
    _write_claim_doc(repo_root, "core.py")

    assert _claim_findings(repo_root) == []


def test_claim_evidence_rejects_the_dot_dot_escape(tmp_path: Path) -> None:
    """The escape hatch is gone now that the display spelling resolves. It only
    ever worked by accident — nothing validated it — and it contradicted the
    spelling every other subsystem requires."""
    repo_root = _build_siblings(tmp_path)
    _write_claim_doc(repo_root, "../code/src/core.py")

    messages = _claim_findings(repo_root)

    assert any("must not be absolute or escape the tree with '..'" in m for m in messages)


def test_claim_evidence_drift_crosses_the_repo_boundary(tmp_path: Path) -> None:
    """Resolution is not only for the exists/does-not-exist gate: the drift scan
    reads the same spelling, so it can pull the evidence's commit time from the
    sibling code repo and compare it against the doc's time in the docs repo.
    Before the spelling was unified this silently found nothing, because
    `repo_root / 'core.py'` does not exist."""
    repo_root = _build_siblings(tmp_path, doc_when=_dt.datetime(2024, 1, 1, tzinfo=_dt.UTC))
    _write_claim_doc(repo_root, "core.py")
    docs_repo = Repo(repo_root)
    _commit_all(docs_repo, "claim doc", when=_dt.datetime(2024, 1, 1, tzinfo=_dt.UTC))
    docs_repo.close()

    messages = _claim_findings(repo_root)

    assert messages == ["claim 'core-works' cites evidence changed after the doc: 'core.py'"]


def test_claim_evidence_that_names_nothing_is_still_an_error(tmp_path: Path) -> None:
    """The mirror: widening the spelling must not make every string resolve."""
    repo_root = _build_siblings(tmp_path)
    _write_claim_doc(repo_root, "gone.py")

    messages = _claim_findings(repo_root)

    assert any("evidence path does not exist: 'gone.py'" in m for m in messages)


def test_checks_pass_across_the_repo_boundary(tmp_path: Path) -> None:
    repo_root = _build_siblings(tmp_path)
    result = runner.invoke(app, ["check", "--profile", "configured", "--path", str(repo_root)])
    assert result.exit_code == 0, result.output
    assert "0 errors, 0 warnings" in result.output


def test_claims_resolve_into_the_sibling_code_repo(tmp_path: Path) -> None:
    """A doc's claim is matched against the sibling repo's files, addressed by
    the source-root-relative display path they carry."""
    repo_root = _build_siblings(tmp_path)
    result = runner.invoke(app, ["context", "docs/20-components/core.md", "--path", str(repo_root)])
    assert result.exit_code == 0, result.output
    assert "owner: core" in result.output
    assert "source claims: core.py" in result.output


def test_a_claim_on_a_missing_sibling_file_is_an_error(tmp_path: Path) -> None:
    """The mirror of the resolving case: the glob really is evaluated against
    the sibling repo, so a claim with nothing behind it still fails."""
    repo_root = _build_siblings(tmp_path)
    doc = repo_root / "docs" / "20-components" / "core.md"
    doc.write_text(doc.read_text(encoding="utf-8").replace("- core.py", "- gone.py"))

    result = runner.invoke(app, ["check", "--profile", "hard", "--path", str(repo_root)])
    assert result.exit_code == 1, result.output
    assert "'gone.py' matched zero files" in result.output


def test_sibling_source_paths_map_to_their_display_spelling(tmp_path: Path) -> None:
    """`context ../code/src/core.py` — the spelling a shell tab-completes — is
    the real location of a file the tool addresses as `core.py`. An existing
    path under a configured external source root maps to that display spelling
    instead of being refused as outside the repo."""
    repo_root = _build_siblings(tmp_path)
    result = runner.invoke(app, ["context", "../code/src/core.py", "--path", str(repo_root)])
    assert result.exit_code == 0, result.output
    assert "owner: core" in result.output


def test_paths_outside_every_source_root_are_still_refused(tmp_path: Path) -> None:
    """The mirror: the mapping covers configured external roots only. A real
    file outside the repo and outside every root has no display spelling, so
    it is refused exactly as before."""
    repo_root = _build_siblings(tmp_path)
    stray = repo_root.parent / "stray.py"
    stray.write_text("x = 1\n", encoding="utf-8")
    result = runner.invoke(app, ["context", "../stray.py", "--path", str(repo_root)])
    assert result.exit_code == 2
    assert "outside the repo" in result.output


def test_sibling_source_files_answer_to_their_display_spelling(tmp_path: Path) -> None:
    """The spelling that does work, and the one `describes:` and
    `claims[].evidence` already require: source-root-relative. Without it the
    layout had no spelling at all for its own source files — `../code/...` is
    outside the repo, and `core.py` did not exist under the docs repo."""
    repo_root = _build_siblings(tmp_path)
    result = runner.invoke(app, ["context", "core.py", "--path", str(repo_root)])
    assert result.exit_code == 0, result.output
    assert "owner: core" in result.output


def test_a_display_spelling_that_names_nothing_still_fails(tmp_path: Path) -> None:
    """The mirror: the fallback resolves real files under a configured root, it
    does not accept any string that happens to look like one."""
    repo_root = _build_siblings(tmp_path)
    result = runner.invoke(app, ["context", "gone.py", "--path", str(repo_root)])
    assert result.exit_code == 1
    assert "path does not exist" in result.output


def test_mtime_uses_the_sibling_code_repos_own_history(tmp_path: Path) -> None:
    repo_root = _build_siblings(tmp_path)
    code_repo = Repo(repo_root.parent / "code")
    expected_sha = code_repo.head.commit.hexsha
    code_repo.close()

    git_time = last_commit_time_any_repo(repo_root.parent / "code" / "src" / "core.py", repo_root)
    assert git_time is not None
    assert git_time.sha == expected_sha


def test_mtime_drift_crosses_the_repo_boundary(tmp_path: Path) -> None:
    """The doc's commit time comes from the docs repo and the source's from the
    code repo — drift between them must still be measurable."""
    from irminsul.checks.mtime_drift import MtimeDriftCheck

    repo_root = _build_siblings(tmp_path, doc_when=_dt.datetime(2024, 1, 1, tzinfo=_dt.UTC))

    config = load(find_config(repo_root))
    graph = build_graph(repo_root, config)

    findings = [f for f in MtimeDriftCheck().run(graph) if "drift" in f.message]
    assert len(findings) == 1
    assert findings[0].doc_id == "core"


def test_no_drift_when_both_repos_moved_together(tmp_path: Path) -> None:
    """The mirror of the drift case: a doc and its sibling-repo source that were
    committed at the same time must not be reported."""
    from irminsul.checks.mtime_drift import MtimeDriftCheck

    when = _dt.datetime(2024, 1, 1, tzinfo=_dt.UTC)
    repo_root = _build_siblings(tmp_path, doc_when=when, code_when=when)

    config = load(find_config(repo_root))
    graph = build_graph(repo_root, config)

    assert [f for f in MtimeDriftCheck().run(graph) if "drift" in f.message] == []


def test_code_edits_invisible_to_the_docs_diff_is_a_known_limit(tmp_path: Path) -> None:
    """Git diff-based views inspect only the repository irminsul was invoked
    from. From the docs repo, changes in the sibling code repo do not appear.
    This pins the documented limitation so a behavior change shows up as a test
    failure rather than silent drift from the doc."""
    repo_root = _build_siblings(tmp_path)
    source = repo_root.parent / "code" / "src" / "core.py"
    source.write_text(source.read_text(encoding="utf-8") + "\n\ndef g():\n    return 2\n")

    result = runner.invoke(app, ["context", "--changed", "--path", str(repo_root)])
    assert result.exit_code == 0, result.output
    assert "core.py" not in result.output
