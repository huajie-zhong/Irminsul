"""The acknowledgement step: an `Irminsul-Reviewed` trailer accepts a finding whose code is
declared `trailer`, by code, path and subject, and reports misuse as info."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from irminsul.checks import pipeline
from irminsul.checks.acknowledgement import (
    CODE_INVALID,
    CODE_UNUSED,
    Trailer,
    acknowledge,
    parse,
    placement,
    trailer_for,
    trailer_form,
)
from irminsul.checks.base import AnswerKind, Finding, Severity
from irminsul.checks.pipeline import answer_of
from irminsul.docgraph import DocGraph

from .conftest import (
    check_findings,
    commit_all,
    component_doc,
    config_toml,
    findings_of,
    git,
    load_graph,
    reviewed,
    seed_repo,
    write,
    write_config,
)

_DOC = "docs/components/alpha.md"
_CO_CHANGE = "co-change/unreflected-change"
_WIDGET = "docs/components/widget.md"
_REWRITTEN = "diff-integrity/decision-rewritten"
_RECORD = "docs/decisions/choice.md"
_REWRITTEN_TO = "docs/decisions/pick-a-lane.md"
_REWORDED = "diff-integrity/claim-reworded"
_WEAKENED = "diff-integrity/setting-weakened"
_LENGTH = "checks.parent_child.length_warning_lines"


@pytest.fixture
def graph(tmp_path: Path) -> DocGraph:
    write_config(tmp_path, project_name="ack", source_roots=["app"])
    write(tmp_path, _DOC, component_doc("alpha", "app/alpha.py"))
    return load_graph(tmp_path)


def _finding(
    *,
    code: str = _CO_CHANGE,
    path: str = _DOC,
    subject: str | None = _DOC,
    about: tuple[str, ...] = ("app/alpha.py",),
    suggestion: str | None = "update the doc",
    data: dict[str, str] | None = None,
) -> Finding:
    return Finding(
        check=code.split("/", 1)[0],
        code=code,
        severity=Severity.warning,
        message="source changed",
        path=Path(path),
        doc_id="alpha",
        suggestion=suggestion,
        subject=subject,
        about=about,
        data=data,
    )


def _trailer(
    value: str, changed_after: frozenset[str] = frozenset(), commit: str = "abc1234"
) -> Trailer:
    return Trailer(commit, value, changed_after)


def _only(findings: list[Finding], code: str) -> Finding:
    [found] = [f for f in findings if f.code == code]
    return found


def test_parse_reads_a_code_a_path_a_subject_and_a_reason() -> None:
    read = parse(
        "diff-integrity/setting-weakened irminsul.toml checks.external_links.ttl_hours "
        'reason="slower is fine"'
    )

    assert not isinstance(read, str)
    assert (read.code, read.path, read.subject, read.reason) == (
        "diff-integrity/setting-weakened",
        "irminsul.toml",
        "checks.external_links.ttl_hours",
        "slower is fine",
    )


@pytest.mark.parametrize(
    ("value", "problem"),
    [
        ('co-change reason="still right"', "names no path"),
        ("co-change docs/components/alpha.md", "gives no reason"),
        ('co-change docs/components/alpha.md reason=" "', "gives no reason"),
        ("co-change docs/components/alpha.md reason=unquoted", "is not written as"),
        ('co-change docs/components/alpha.md a b reason="x"', "is not written as"),
    ],
)
def test_parse_names_what_is_missing(value: str, problem: str) -> None:
    read = parse(value)

    assert isinstance(read, str)
    assert problem in read


def test_a_bare_check_name_with_one_code_names_that_code(graph: DocGraph) -> None:
    found = acknowledge(
        [_finding()],
        [_trailer(f'co-change {_DOC} reason="still right"')],
        graph,
        ran=("co-change",),
    )

    [accepted] = found
    assert accepted.code == _CO_CHANGE
    assert accepted.severity is Severity.info
    assert 'acknowledged in abc1234: "still right"' in accepted.message


def test_a_bare_name_of_a_check_with_several_codes_is_refused(graph: DocGraph) -> None:
    found = acknowledge(
        [_finding()],
        [_trailer(f'diff-integrity {_DOC} reason="x"')],
        graph,
        ran=("co-change",),
    )

    invalid = _only(found, CODE_INVALID)
    assert invalid.severity is Severity.info
    assert "several codes" in invalid.message
    assert _only(found, _CO_CHANGE).severity is Severity.warning


def test_an_unknown_code_is_invalid(graph: DocGraph) -> None:
    found = acknowledge(
        [_finding()],
        [_trailer(f'evidence-drift {_DOC} reason="x"')],
        graph,
        ran=("co-change",),
    )

    assert "no check or finding code" in _only(found, CODE_INVALID).message


def test_a_code_declared_fix_is_invalid_and_its_answer_is_named(graph: DocGraph) -> None:
    code = "claim-anchor/unreadable"
    assert answer_of(code).kind is AnswerKind.fix

    found = acknowledge([], [_trailer(f'{code} {_DOC} reason="x"')], graph, ran=("claim-anchor",))

    [invalid] = found
    assert invalid.code == CODE_INVALID
    assert answer_of(code).how in (invalid.suggestion or "")


def test_a_doc_id_is_invalid_and_the_path_is_named(graph: DocGraph) -> None:
    found = acknowledge(
        [_finding()],
        [_trailer('co-change alpha reason="still right"')],
        graph,
        ran=("co-change",),
    )

    invalid = _only(found, CODE_INVALID)
    assert f"write its path, {_DOC}" in invalid.message
    assert _only(found, _CO_CHANGE).severity is Severity.warning


def test_a_subject_defaults_to_the_path(graph: DocGraph) -> None:
    found = acknowledge(
        [_finding()],
        [_trailer(f'{_CO_CHANGE} {_DOC} reason="x"')],
        graph,
        ran=("co-change",),
    )

    assert [(f.code, f.severity) for f in found] == [(_CO_CHANGE, Severity.info)]


def test_a_trailer_naming_another_subject_accepts_nothing(graph: DocGraph) -> None:
    found = acknowledge(
        [_finding()],
        [_trailer(f'{_CO_CHANGE} {_DOC} app/alpha.py reason="x"')],
        graph,
        ran=("co-change",),
    )

    assert _only(found, CODE_UNUSED).severity is Severity.info
    assert _only(found, _CO_CHANGE).severity is Severity.warning


def test_a_later_change_to_a_file_the_finding_is_about_lapses_the_trailer(graph: DocGraph) -> None:
    found = acknowledge(
        [_finding()],
        [_trailer(f'co-change {_DOC} reason="x"', frozenset({"app/alpha.py"}))],
        graph,
        ran=("co-change",),
    )

    kept = _only(found, _CO_CHANGE)
    assert kept.severity is Severity.warning
    assert "abc1234, which predates the change to app/alpha.py: that trailer does not count" in (
        kept.suggestion or ""
    )
    assert CODE_UNUSED not in [f.code for f in found]


def test_a_later_change_to_an_unrelated_file_leaves_the_trailer_standing(graph: DocGraph) -> None:
    found = acknowledge(
        [_finding()],
        [_trailer(f'co-change {_DOC} reason="x"', frozenset({"app/other.py"}))],
        graph,
        ran=("co-change",),
    )

    assert [(f.code, f.severity) for f in found] == [(_CO_CHANGE, Severity.info)]


def test_without_about_the_finding_path_is_what_a_later_change_lapses(graph: DocGraph) -> None:
    found = acknowledge(
        [_finding(about=())],
        [_trailer(f'co-change {_DOC} reason="x"', frozenset({_DOC}))],
        graph,
        ran=("co-change",),
    )

    assert _only(found, _CO_CHANGE).severity is Severity.warning


def test_a_trailer_matching_nothing_is_unused_only_when_the_run_says_so(graph: DocGraph) -> None:
    trailer = _trailer('co-change docs/components/gone.md reason="x"')

    assert acknowledge([], [trailer], graph, ran=None) == []
    [unused] = acknowledge([], [trailer], graph, ran=("co-change",))
    assert unused.code == CODE_UNUSED
    assert unused.severity is Severity.info


def test_misuse_is_reported_only_when_the_run_says_so(graph: DocGraph) -> None:
    assert acknowledge([], [_trailer('evidence-drift alpha reason="x"')], graph, ran=None) == []


def test_an_accepted_finding_keeps_its_code_and_quotes_its_reason(graph: DocGraph) -> None:
    [accepted] = acknowledge(
        [_finding()],
        [_trailer(f'co-change {_DOC} reason="no value is named"')],
        graph,
        ran=("co-change",),
    )

    assert accepted.code == _CO_CHANGE
    assert accepted.severity is Severity.info
    assert accepted.message.endswith('; acknowledged in abc1234: "no value is named"')
    assert accepted.data == {"acknowledged_in": "abc1234", "reason": "no value is named"}
    assert accepted.suggestion is None


def test_several_trailers_accepting_one_finding_are_all_quoted(graph: DocGraph) -> None:
    [accepted] = acknowledge(
        [_finding()],
        [
            _trailer(f'co-change {_DOC} reason="one"', commit="aaa1111"),
            _trailer(f'co-change {_DOC} reason="two"', commit="bbb2222"),
        ],
        graph,
        ran=("co-change",),
    )

    assert accepted.message.endswith('; acknowledged in aaa1111: "one"; bbb2222: "two"')
    assert accepted.data == {"acknowledged_in": "aaa1111, bbb2222", "reason": "one; two"}


@pytest.mark.parametrize("spelling", ["./docs/components/alpha.md", "docs\\components\\alpha.md"])
def test_a_trailer_path_is_normalized_before_it_is_matched(graph: DocGraph, spelling: str) -> None:
    found = acknowledge(
        [_finding()],
        [_trailer(f'{_CO_CHANGE} {spelling} reason="x"')],
        graph,
        ran=("co-change",),
    )

    assert [(f.code, f.severity) for f in found] == [(_CO_CHANGE, Severity.info)]


def test_the_suggestion_composes_the_trailer_clause_once(graph: DocGraph) -> None:
    finding = _finding()

    once = pipeline.finish([finding], graph)
    twice = pipeline.finish(once, graph)

    assert twice[0].suggestion == once[0].suggestion
    assert (once[0].suggestion or "").endswith(
        f"`{trailer_for(finding)}` on the commit that carries the last change to app/alpha.py, "
        "or a later one"
    )


def test_an_accepted_finding_gets_no_trailer_clause(graph: DocGraph) -> None:
    accepted = replace(
        _finding(suggestion=None), severity=Severity.info, data={"acknowledged_in": "abc1234"}
    )

    [out] = pipeline.finish([accepted], graph)

    assert out.suggestion is None


def test_placement_names_an_uncommitted_file_or_the_last_change() -> None:
    assert (
        placement(_finding(), frozenset({"app/alpha.py"}))
        == "in the message of the commit that carries app/alpha.py"
    )
    assert (
        placement(_finding(), frozenset())
        == "on the commit that carries the last change to app/alpha.py, or a later one"
    )
    assert (
        placement(_finding(about=("app/alpha.py", "app/beta.py")), frozenset())
        == "on the commit that carries the last change to those files, or a later one"
    )


def test_the_printed_trailer_leaves_out_a_subject_equal_to_the_path() -> None:
    assert trailer_for(_finding()) == (f'Irminsul-Reviewed: {_CO_CHANGE} {_DOC} reason="..."')
    assert trailer_for(_finding(subject="app/alpha.py")) == (
        f'Irminsul-Reviewed: {_CO_CHANGE} {_DOC} app/alpha.py reason="..."'
    )


def test_the_form_explain_prints_has_placeholders() -> None:
    assert trailer_form(_CO_CHANGE) == (
        f'Irminsul-Reviewed: {_CO_CHANGE} <path> [<subject>] reason="..."'
    )


def test_a_reviewed_trailer_on_one_doc_leaves_another_docs_warning_a_warning(
    tmp_path: Path,
) -> None:
    write_config(tmp_path, project_name="ack", source_roots=["app"])
    write(tmp_path, "app/alpha.py", "a = 1\n")
    write(tmp_path, "app/beta.py", "b = 1\n")
    write(tmp_path, "docs/components/alpha.md", component_doc("alpha", "app/alpha.py"))
    write(tmp_path, "docs/components/beta.md", component_doc("beta", "app/beta.py"))
    base = seed_repo(tmp_path, "seed")
    write(tmp_path, "app/alpha.py", "a = 2\n")
    write(tmp_path, "app/beta.py", "b = 2\n")
    commit_all(
        tmp_path,
        f"change both sources\n\n{reviewed(_CO_CHANGE, 'docs/components/alpha.md')}",
    )

    cochange = {
        f["path"]: (f["code"], f["severity"])
        for f in check_findings(tmp_path, "--diff", base)
        if f["check"] == "co-change"
    }

    assert cochange == {
        "docs/components/alpha.md": (_CO_CHANGE, "info"),
        "docs/components/beta.md": (_CO_CHANGE, "warning"),
    }


def _widget(first: str, second: str) -> str:
    """A stable doc with two claims a change may reword; neither is `governs-evidence`, so a
    rewording is a hint rather than a contract change."""
    return (
        "---\nid: widget\ntitle: Widget\nstatus: stable\nsummary: A test doc.\nclaims:\n"
        f"  - id: widget-runs\n    state: implemented\n    kind: invariant\n    claim: {first}\n"
        "    evidence:\n      - src/widget.py\n"
        f"  - id: widget-stops\n    state: implemented\n    kind: invariant\n    claim: {second}\n"
        "    evidence:\n      - src/widget.py\n"
        "---\n\n# Widget\n\nIt runs and stops.\n"
    )


def _widget_repo(root: Path) -> str:
    write_config(root, project_name="ack")
    write(root, "src/widget.py", "def run():\n    return 1\n")
    write(root, _WIDGET, _widget("The widget runs.", "The widget stops."))
    return seed_repo(root, "adopted")


def test_a_reviewed_claim_rewording_is_info_and_the_other_claim_still_warns(
    tmp_path: Path,
) -> None:
    base = _widget_repo(tmp_path)
    write(tmp_path, _WIDGET, _widget("The widget runs once.", "The widget halts."))
    commit_all(
        tmp_path,
        "reword both claims\n\n"
        + reviewed(_REWORDED, _WIDGET, "widget-runs", reason="re-read: still runs"),
    )

    severities = {
        f["subject"]: f["severity"] for f in findings_of(tmp_path, _REWORDED, "--diff", base)
    }

    assert severities == {"widget-runs": "info", "widget-stops": "warning"}


def test_a_later_commit_to_the_doc_makes_a_reviewed_rewording_a_warning_again(
    tmp_path: Path,
) -> None:
    base = _widget_repo(tmp_path)
    write(tmp_path, _WIDGET, _widget("The widget runs once.", "The widget halts."))
    commit_all(
        tmp_path,
        "reword both claims\n\n"
        + reviewed(_REWORDED, _WIDGET, "widget-runs", reason="re-read: still runs"),
    )
    accepted = {
        f["subject"]: f["severity"] for f in findings_of(tmp_path, _REWORDED, "--diff", base)
    }
    assert accepted == {"widget-runs": "info", "widget-stops": "warning"}

    write(tmp_path, _WIDGET, _widget("The widget runs once.", "The widget halts.") + "\nMore.\n")
    commit_all(tmp_path, "add a sentence to the doc")

    severities = {
        f["subject"]: f["severity"] for f in findings_of(tmp_path, _REWORDED, "--diff", base)
    }
    assert severities == {"widget-runs": "warning", "widget-stops": "warning"}


def _length_repo(root: Path) -> str:
    write(root, "irminsul.toml", config_toml(project_name="ack", extra=_length(300)))
    return seed_repo(root, "adopted")


def _length(value: int) -> str:
    return f"[checks.parent_child]\nlength_warning_lines = {value}\n"


def test_a_reviewed_widening_of_a_setting_is_info_quoting_its_reason(tmp_path: Path) -> None:
    base = _length_repo(tmp_path)
    write(tmp_path, "irminsul.toml", config_toml(project_name="ack", extra=_length(3000)))
    commit_all(
        tmp_path,
        "raise the length warning\n\n"
        + reviewed(_WEAKENED, "irminsul.toml", _LENGTH, reason="long files are deliberate"),
    )

    [found] = findings_of(tmp_path, _WEAKENED, "--diff", base)

    assert found["severity"] == "info"
    assert found["data"]["reason"] == "long files are deliberate"


def test_the_same_widening_with_no_trailer_is_an_error(tmp_path: Path) -> None:
    base = _length_repo(tmp_path)
    write(tmp_path, "irminsul.toml", config_toml(project_name="ack", extra=_length(3000)))
    commit_all(tmp_path, "raise the length warning")

    assert [f["severity"] for f in findings_of(tmp_path, _WEAKENED, "--diff", base)] == ["error"]


def test_a_trailer_for_a_fix_code_is_invalid_and_accepts_nothing(tmp_path: Path) -> None:
    base = _length_repo(tmp_path)
    write(tmp_path, "irminsul.toml", config_toml(project_name="ack", extra=_length(3000)))
    commit_all(
        tmp_path,
        "raise the length warning\n\n"
        + reviewed("diff-integrity/adoption-record-grew", ".irminsul-adoption.json"),
    )

    [invalid] = findings_of(tmp_path, CODE_INVALID, "--diff", base)

    assert invalid["severity"] == "info"
    assert [f["severity"] for f in findings_of(tmp_path, _WEAKENED, "--diff", base)] == ["error"]


def test_a_decision_record_alone_leaves_the_widening_an_error(tmp_path: Path) -> None:
    base = _length_repo(tmp_path)
    write(tmp_path, "irminsul.toml", config_toml(project_name="ack", extra=_length(3000)))
    write(
        tmp_path,
        "docs/decisions/long-files.md",
        "---\nid: long-files\ntitle: Long files\nstatus: stable\nsummary: A test record.\n---\n\n"
        "# Long files\n\n## Decision\n\nLong files are deliberate: raise "
        "`checks.parent_child.length_warning_lines`.\n",
    )
    commit_all(tmp_path, "raise it, and explain in a record")

    assert [f["severity"] for f in findings_of(tmp_path, _WEAKENED, "--diff", base)] == ["error"]


def test_an_uncommitted_config_edit_after_the_trailer_brings_the_error_back(
    tmp_path: Path,
) -> None:
    base = _length_repo(tmp_path)
    write(tmp_path, "irminsul.toml", config_toml(project_name="ack", extra=_length(3000)))
    commit_all(
        tmp_path,
        "raise the length warning\n\n"
        + reviewed(_WEAKENED, "irminsul.toml", _LENGTH, reason="long files are deliberate"),
    )
    assert [f["severity"] for f in findings_of(tmp_path, _WEAKENED, "--diff", base)] == ["info"]

    write(tmp_path, "irminsul.toml", config_toml(project_name="ack", extra=_length(30000)))

    [found] = findings_of(tmp_path, _WEAKENED, "--diff", base)
    assert found["severity"] == "error"
    assert "that trailer does not count" in str(found["suggestion"])


_TYPO = "Run the chcek on every pull request."
_TYPO_FIXED = "Run the check on every pull request."


def _record(decision: str, *, record_id: str = "choice") -> str:
    return (
        f"---\nid: {record_id}\ntitle: Choice\nstatus: stable\nsummary: A test record.\n---\n\n"
        f"# Choice\n\n## Status\n\nAccepted.\n\n## Decision\n\n{decision}\n\n"
        "## Consequences\n\nFine.\n"
    )


def _record_repo(root: Path, decision: str) -> str:
    write_config(root, project_name="ack")
    write(root, _RECORD, _record(decision))
    return seed_repo(root, "adopted")


def test_a_reviewed_typo_fix_in_a_decision_is_info_under_its_own_code(tmp_path: Path) -> None:
    base = _record_repo(tmp_path, _TYPO)
    write(tmp_path, _RECORD, _record(_TYPO_FIXED))
    commit_all(tmp_path, "fix a typo\n\n" + reviewed(_REWRITTEN, _RECORD, reason="typo"))

    [found] = findings_of(tmp_path, _REWRITTEN, "--diff", base)

    assert found["severity"] == "info"
    assert found["data"]["reason"] == "typo"


def test_the_same_typo_fix_with_no_trailer_is_a_warning(tmp_path: Path) -> None:
    base = _record_repo(tmp_path, _TYPO)
    write(tmp_path, _RECORD, _record(_TYPO_FIXED))
    commit_all(tmp_path, "fix a typo")

    assert [f["severity"] for f in findings_of(tmp_path, _REWRITTEN, "--diff", base)] == ["warning"]


def test_a_later_commit_to_the_record_brings_a_reviewed_typo_back_as_a_warning(
    tmp_path: Path,
) -> None:
    base = _record_repo(tmp_path, _TYPO)
    write(tmp_path, _RECORD, _record(_TYPO_FIXED))
    commit_all(tmp_path, "fix a typo\n\n" + reviewed(_REWRITTEN, _RECORD, reason="typo"))
    write(tmp_path, _RECORD, _record(_TYPO_FIXED).replace("Fine.", "Fine enough."))
    commit_all(tmp_path, "edit the consequences")

    assert [f["severity"] for f in findings_of(tmp_path, _REWRITTEN, "--diff", base)] == ["warning"]


def test_a_reviewed_typo_fix_in_a_renamed_record_names_its_new_path(tmp_path: Path) -> None:
    base = _record_repo(tmp_path, _TYPO)
    git(tmp_path, "mv", _RECORD, _REWRITTEN_TO)
    write(tmp_path, _REWRITTEN_TO, _record(_TYPO_FIXED, record_id="pick-a-lane"))
    commit_all(
        tmp_path,
        "rename the record and fix a typo\n\n" + reviewed(_REWRITTEN, _REWRITTEN_TO, reason="typo"),
    )

    [found] = findings_of(tmp_path, _REWRITTEN, "--diff", base)

    assert found["severity"] == "info"
    assert found["path"] == _REWRITTEN_TO
