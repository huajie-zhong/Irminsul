"""Context keeps no session: each call re-derives what it reports from the repository.

These pin the observable half of the `context-is-stateless` contract. A change to the docs,
to git history or to a manifest a reader places imports through, made between two calls in
one process, shows up in the second call, and a call writes nothing into the repository. They cannot show that no future code path holds
hidden state; that stays a question for review.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from irminsul.config import find_config, load
from irminsul.context import build_context_report

from .conftest import commit_all, git_init, seed_repo

_OLD = _dt.datetime(2024, 1, 1, tzinfo=_dt.UTC)
_LATER = _dt.datetime(2025, 1, 1, tzinfo=_dt.UTC)


def _doc(doc_id: str, describes: list[str]) -> str:
    claimed = "".join(f"  - {path}\n" for path in describes)
    return (
        f"---\nid: {doc_id}\ntitle: {doc_id.title()}\nstatus: stable\n"
        f"describes:{' []' if not describes else ''}\n{claimed}---\n\n# {doc_id.title()}\n\n"
        f"The {doc_id} component.\n"
    )


def _repo(root: Path, *, checks: str) -> Path:
    (root / "src").mkdir(parents=True)
    (root / "src" / "thing.py").write_text("X = 1\n", encoding="utf-8")
    components = root / "docs" / "components"
    components.mkdir(parents=True)
    (components / "alpha.md").write_text(_doc("alpha", ["src/thing.py"]), encoding="utf-8")
    (components / "beta.md").write_text(_doc("beta", []), encoding="utf-8")
    (root / "irminsul.toml").write_text(
        'project_name = "stateless"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n'
        f"[checks]\nenabled = {checks}\n[overrides]\nmtime_drift_days = 30\n",
        encoding="utf-8",
    )
    return root


def _packet(root: Path):
    return build_context_report(
        root,
        load(find_config(root)),
        target_paths=[root / "src" / "thing.py"],
    )


def _after_edit(root: Path):
    """The one mode that runs the checks, so the call that can observe a finding appear."""
    return build_context_report(root, load(find_config(root)), after_edit=True)


def test_a_second_call_sees_ownership_moved_between_calls(tmp_path: Path) -> None:
    root = _repo(tmp_path / "r", checks='["frontmatter"]')
    assert [r.owner.id for r in _packet(root).results] == ["alpha"]

    components = root / "docs" / "components"
    (components / "alpha.md").write_text(_doc("alpha", []), encoding="utf-8")
    (components / "beta.md").write_text(_doc("beta", ["src/thing.py"]), encoding="utf-8")

    assert [r.owner.id for r in _packet(root).results] == ["beta"]


def test_a_second_call_sees_a_commit_made_between_calls(tmp_path: Path) -> None:
    """Git history is repository state too: a commit that makes the owning doc lag its
    source must reach the next call in the same process, as it does in the MCP server."""
    root = _repo(tmp_path / "r", checks='["mtime-drift"]')
    seed_repo(root, "seed", when=_OLD)

    def drift() -> list[str]:
        findings = _after_edit(root).findings
        assert findings is not None
        return [f.code for f in findings]

    assert drift() == []

    # Committed, so the tree is clean on both calls and neither judges a change. An
    # uncommitted edit is a change judged against HEAD, in which `co-change` reports the
    # source its doc did not follow, so the findings would not be the drift alone.
    source = root / "src" / "thing.py"
    source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    commit_all(root, "the source alone, a year on", when=_LATER, paths=["src/thing.py"])

    assert drift() == ["mtime-drift/drift-detected"]


def test_context_calls_write_nothing_into_the_repository(tmp_path: Path) -> None:
    root = _repo(tmp_path / "r", checks='["frontmatter", "mtime-drift", "external-links"]')
    seed_repo(root, "seed")

    def snapshot() -> dict[str, tuple[int, int]]:
        return {
            path.relative_to(root).as_posix(): (path.stat().st_size, path.stat().st_mtime_ns)
            for path in sorted(root.rglob("*"))
            if path.is_file() and ".git" not in path.relative_to(root).parts
        }

    before = snapshot()
    config = load(find_config(root))
    _packet(root)
    build_context_report(root, config, after_edit=True)
    build_context_report(root, config, topic="alpha")

    assert snapshot() == before


def test_a_second_call_sees_a_manifest_rewritten_between_calls(tmp_path: Path) -> None:
    """A reader places a Go import through `go.mod`, which it reads once for a run. The next
    call is another run: once the module is renamed, the test's import leads out of the
    repository and the test is no longer ranked for the file."""
    root = tmp_path / "r"
    (root / "desk").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "docs" / "components").mkdir(parents=True)
    (root / "go.mod").write_text("module example.com/lib\n\ngo 1.22\n", encoding="utf-8")
    (root / "desk" / "desk.go").write_text(
        "package desk\n\nfunc Renew() int {\n\treturn 1\n}\n", encoding="utf-8"
    )
    (root / "tests" / "desk_test.go").write_text(
        'package tests\n\nimport (\n\t"testing"\n\n\t"example.com/lib/desk"\n)\n\n'
        "func TestRenew(t *testing.T) {\n\tif desk.Renew() != 1 {\n\t\tt.Fail()\n\t}\n}\n",
        encoding="utf-8",
    )
    (root / "docs" / "components" / "desk.md").write_text(
        _doc("desk", ["desk/desk.go"]), encoding="utf-8"
    )
    (root / "irminsul.toml").write_text(
        'project_name = "stateless"\n[paths]\ndocs_root = "docs"\nsource_roots = ["desk"]\n'
        'test_roots = ["tests"]\n[checks]\nenabled = ["frontmatter"]\n',
        encoding="utf-8",
    )
    git_init(root)

    def ranked() -> dict[str, list[str]]:
        report = build_context_report(
            root, load(find_config(root)), target_paths=[root / "desk" / "desk.go"]
        )
        [result] = report.results
        return result.test_reasons

    assert ranked() == {"tests/desk_test.go": ["imports desk/desk.go"]}

    (root / "go.mod").write_text("module example.com/moved\n\ngo 1.22\n", encoding="utf-8")

    assert ranked() == {}
