"""Context keeps no session: each call re-derives what it reports from the repository.

These pin the observable half of the `context-is-stateless` contract. A change to the docs
or to git history made between two calls in one process shows up in the second call, and a
call writes nothing into the repository. They cannot show that no future code path holds
hidden state; that stays a question for review.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from git import Repo

from irminsul.config import find_config, load
from irminsul.context import build_context_report

_OLD = _dt.datetime(2024, 1, 1, tzinfo=_dt.UTC)


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


def _commit_all(root: Path, message: str, when: _dt.datetime | None = None) -> None:
    repo = Repo.init(root)
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "Test")
        cw.set_value("user", "email", "test@example.com")
    repo.git.add("-A")
    if when is None:
        repo.index.commit(message)
    else:
        repo.index.commit(message, author_date=when, commit_date=when)
    repo.close()


def _before_edit(root: Path):
    return build_context_report(
        root,
        load(find_config(root)),
        target_paths=[root / "src" / "thing.py"],
        workflow="before-edit",
    )


def _with_checks(root: Path):
    """A plain path lookup, which does run the checks. `--before-edit` deliberately does
    not, so it is no longer the call that can observe a finding appear."""
    return build_context_report(
        root,
        load(find_config(root)),
        target_paths=[root / "src" / "thing.py"],
    )


def test_a_second_call_sees_ownership_moved_between_calls(tmp_path: Path) -> None:
    root = _repo(tmp_path / "r", checks='["frontmatter"]')
    assert [r.owner.id for r in _before_edit(root).results] == ["alpha"]

    components = root / "docs" / "components"
    (components / "alpha.md").write_text(_doc("alpha", []), encoding="utf-8")
    (components / "beta.md").write_text(_doc("beta", ["src/thing.py"]), encoding="utf-8")

    assert [r.owner.id for r in _before_edit(root).results] == ["beta"]


def test_a_second_call_sees_a_commit_made_between_calls(tmp_path: Path) -> None:
    """Git history is repository state too: a commit that makes the owning doc lag its
    source must reach the next call in the same process, as it does in the MCP server."""
    root = _repo(tmp_path / "r", checks='["mtime-drift"]')
    _commit_all(root, "seed", when=_OLD)

    def drift() -> list[str]:
        findings = _with_checks(root).results[0].findings
        assert findings is not None
        return [f.code for f in findings]

    assert drift() == []

    (root / "src" / "thing.py").write_text("X = 2\n", encoding="utf-8")
    _commit_all(root, "change the source without the doc")

    assert drift() == ["mtime-drift/drift-detected"]


def test_context_calls_write_nothing_into_the_repository(tmp_path: Path) -> None:
    root = _repo(tmp_path / "r", checks='["frontmatter", "mtime-drift", "external-links"]')
    _commit_all(root, "seed")

    def snapshot() -> dict[str, tuple[int, int]]:
        return {
            path.relative_to(root).as_posix(): (path.stat().st_size, path.stat().st_mtime_ns)
            for path in sorted(root.rglob("*"))
            if path.is_file() and ".git" not in path.relative_to(root).parts
        }

    before = snapshot()
    config = load(find_config(root))
    _before_edit(root)
    build_context_report(root, config, changed=True, workflow="after-edit")
    build_context_report(root, config, topic="alpha")

    assert snapshot() == before
