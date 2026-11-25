"""Context keeps no session: each call re-derives what it reports from the repository.

These pin the observable half of the `context-is-stateless` contract. A change to the docs
or to git history made between two calls in one process shows up in the second call, and a
call writes nothing into the repository. They cannot show that no future code path holds
hidden state; that stays a question for review.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from irminsul.config import find_config, load
from irminsul.context import build_context_report

from .conftest import commit_all, seed_repo

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

    # Committed, so the tree is clean on both calls: uncommitted work would be a change
    # judged against HEAD, and a run that judges a change leaves out what time caused.
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
