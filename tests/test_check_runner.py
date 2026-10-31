"""`run_checks` is the one place a run is assembled, and `RunResult.failed` the one rule
that turns it into pass or fail.

Every surface that reaches a verdict used to assemble its run by hand, and they
disagreed: one audited ignore comments and another did not, one applied the baseline and
another did not. These pin what a run is, so a surface that asks for one gets all of it.
"""

from __future__ import annotations

import json
from collections.abc import Collection
from pathlib import Path

import pytest

from irminsul.baseline import BaselineError
from irminsul.checks.base import Finding, FindingClass, Severity
from irminsul.checks.pipeline import RunResult, run_checks
from irminsul.config import load
from irminsul.docgraph import ChangeRange, DocGraph, build_graph

from .conftest import (
    commit_all,
    component_doc,
    config_toml,
    git_init,
    invoke,
    load_graph,
    take_answer_violations,
    write,
    write_config,
)

_CONFIG = config_toml(enabled=["frontmatter", "links"])
_DOC = "---\nid: w\ntitle: W\nstatus: stable\nsummary: A test doc.\n---\n\n# W\n\n{body}\n"


def _repo(tmp_path: Path, body: str = "Fine.") -> Path:
    root = tmp_path / "repo"
    (root / "docs" / "components").mkdir(parents=True)
    (root / "irminsul.toml").write_text(_CONFIG, encoding="utf-8")
    (root / "docs" / "components" / "w.md").write_text(_DOC.format(body=body), encoding="utf-8")
    git_init(root)
    return root


def _run(root: Path, *, only: list[str] | None = None, baseline: bool = True) -> RunResult:
    return run_checks(load_graph(root), only=only, baseline=baseline)


def _finding(code: str, severity: Severity) -> Finding:
    return Finding(check=code.split("/")[0], code=code, severity=severity, message="m")


def test_a_certain_finding_fails_whatever_fail_on_says() -> None:
    result = RunResult([_finding("links/broken-link", Severity.error)])
    assert result.failed()
    assert result.failed({FindingClass.time})


def test_a_hint_fails_only_when_asked_and_info_never() -> None:
    warning = RunResult([_finding("orphans/orphan-doc", Severity.warning)])
    info = RunResult([_finding("claim-anchor/unpinned", Severity.info)])
    assert not warning.failed()
    assert warning.failed({FindingClass.hint})
    assert not info.failed({FindingClass.hint, FindingClass.time})


def test_the_baseline_hides_what_it_records_and_says_so(tmp_path: Path) -> None:
    root = _repo(tmp_path, "See [nothing](nowhere.md).")
    unbaselined = _run(root)
    assert unbaselined.failed()
    (root / ".irminsul-baseline.json").write_text(
        json.dumps(
            {
                "version": 1,
                "findings": [
                    {"check": f.check, "path": f.path.as_posix(), "message": f.message}
                    for f in unbaselined.findings
                    if f.code == "links/broken-link"
                ],
            }
        ),
        encoding="utf-8",
    )

    result = _run(root)

    assert not result.failed()
    assert [f.code for f in result.hidden] == ["links/broken-link"]
    report = result.baseline_report()
    assert report["applied"] is True
    assert report["suppressed"] == 1
    assert report["stale"] == 0
    assert [f.code for f in result.unbaselined] == [f.code for f in unbaselined.findings]
    assert _run(root, baseline=False).failed()


def test_an_unreadable_baseline_is_raised_not_ignored(tmp_path: Path) -> None:
    """A baseline that does not load hides nothing it records and says nothing about it;
    reading that as "no baseline" reports a repository the gate would refuse."""
    root = _repo(tmp_path)
    (root / ".irminsul-baseline.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(BaselineError):
        _run(root)
    assert _run(root, baseline=False).baseline_report()["applied"] is False


def test_every_pass_reads_the_range_from_the_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from irminsul.checks import pipeline

    fired: list[ChangeRange | None] = []

    def sentinel(self: object, graph: DocGraph, selected: Collection[str]) -> list[Finding]:
        fired.append(graph.change)
        return []

    for cls in pipeline.PASSES.values():
        monkeypatch.setattr(cls, "run", sentinel, raising=True)
    root = _repo(tmp_path)
    config = load(root / "irminsul.toml")
    count = len(pipeline.PASSES)

    run_checks(build_graph(root, config))
    assert fired == [None] * count

    fired.clear()
    change = ChangeRange(base="HEAD", head="HEAD", changed=frozenset(), merge_base="HEAD")
    run_checks(build_graph(root, config, change=change))
    assert fired == [change] * count


def test_a_diff_pass_reports_only_for_a_graph_that_carries_a_range(tmp_path: Path) -> None:
    from irminsul.checks.pipeline import CHANGE_PASSES, PASSES

    root = tmp_path / "repo"
    write_config(root, source_roots=["app"], enabled=["frontmatter"])
    write(root, "app/alpha.py", "a = 1\n")
    write(root, "docs/components/alpha.md", component_doc("alpha", "app/alpha.py"))
    git_init(root)
    commit_all(root)
    config = load(root / "irminsul.toml")
    change = ChangeRange(
        base="HEAD", head="HEAD", changed=frozenset({"app/alpha.py"}), merge_base="HEAD"
    )

    seen = PASSES["co-change"]().run(build_graph(root, config, change=change), [])
    assert [f.code for f in seen] == ["co-change/unreflected-change"]

    for name in CHANGE_PASSES:
        assert PASSES[name]().run(build_graph(root, config), []) == [], name


def test_the_change_passes_are_the_passes_that_read_the_graphs_change() -> None:
    """`context --after-edit` names `CHANGE_PASSES` as the checks a run with no base did not
    make, so a pass that reads `graph.change` and is missing from it would go unnamed."""
    import inspect
    import sys

    from irminsul.checks.pipeline import CHANGE_PASSES, PASSES

    reads_change = {
        name
        for name, cls in PASSES.items()
        if "graph.change" in inspect.getsource(sys.modules[cls.__module__])
    }

    assert reads_change, "no pass reads graph.change, so the comparison below proves nothing"
    assert reads_change == set(CHANGE_PASSES)


_W = "docs/components/w.md"


def _copied_block(line: int | None) -> Finding:
    return Finding(
        check="duplicate-block",
        code="duplicate-block/copied-block",
        severity=Severity.warning,
        message="m",
        path=Path(_W),
        doc_id="w",
        line=line,
    )


def _reporting(monkeypatch: pytest.MonkeyPatch, finding: Finding) -> None:
    from irminsul.checks.duplicate_block import DuplicateBlockCheck

    monkeypatch.setattr(DuplicateBlockCheck, "run", lambda self, graph: [finding])


@pytest.mark.parametrize("line", [None, 2], ids=["no-line", "frontmatter"])
def test_the_guard_records_a_line_code_off_every_line_a_comment_covers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, line: int | None
) -> None:
    _reporting(monkeypatch, _copied_block(line))

    _run(_repo(tmp_path), only=["duplicate-block"])

    assert take_answer_violations() == [
        f"duplicate-block/copied-block at {_W}:{line}: no line an ignore comment covers"
    ]


@pytest.mark.parametrize("line", [10, 13], ids=["prose", "fenced"])
def test_the_guard_passes_a_line_code_on_a_line_a_comment_covers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, line: int
) -> None:
    _reporting(monkeypatch, _copied_block(line))

    _run(_repo(tmp_path, "Prose.\n\n```text\nfenced\n```"), only=["duplicate-block"])

    assert take_answer_violations() == []


def test_the_guard_records_what_the_cli_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`invoke` turns an exception into an exit code, which is why the guard records."""
    _reporting(monkeypatch, _copied_block(None))

    invoke(_repo(tmp_path), "check", "--only", "duplicate-block")

    assert take_answer_violations() == [
        f"duplicate-block/copied-block at {_W}:None: no line an ignore comment covers"
    ]


def test_the_guard_records_a_trailer_code_without_a_subject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from irminsul.checks.co_change import CoChangePass

    unsigned = Finding(
        check="co-change",
        code="co-change/unreflected-change",
        severity=Severity.warning,
        message="m",
        path=Path(_W),
        doc_id="w",
    )
    monkeypatch.setattr(CoChangePass, "run", lambda self, graph, selected: [unsigned])

    _run(_repo(tmp_path))

    assert take_answer_violations() == [
        f"co-change/unreflected-change at {_W}:None: no subject for a trailer to name"
    ]


def test_one_run_audits_the_ignore_comments_of_the_checks_it_ran(tmp_path: Path) -> None:
    root = _repo(tmp_path, '<!-- irminsul:ignore links reason="nothing here" -->\nFine.')

    result = _run(root)

    assert "ignore-comment/unused" in {f.code for f in result.findings}
    assert result.ran == ("frontmatter", "links")
    assert "ignore-comment/unused" not in {
        f.code for f in _run(root, only=["frontmatter"]).findings
    }
