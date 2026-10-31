"""The acknowledgement step: an `Irminsul-Reviewed` trailer accepts a finding whose code is
declared `trailer`, by code, path and subject, and reports misuse as info."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

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
from irminsul.git import changes

from .conftest import (
    check_findings,
    commit_all,
    component_doc,
    config_toml,
    findings_of,
    git,
    invoke,
    load_graph,
    reviewed,
    seed_repo,
    severities_of,
    write,
    write_config,
)

_DOC = "docs/components/alpha.md"
_NOTHING_TO_DO = (
    "nothing to do unless it names the wrong path or subject; then add a trailer naming the "
    "right one to a later commit"
)
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


def test_a_code_declared_fix_is_invalid_and_explain_is_named(graph: DocGraph) -> None:
    code = "claim-anchor/missing-file"
    assert answer_of(code).kind is AnswerKind.fix

    found = acknowledge([], [_trailer(f'{code} {_DOC} reason="x"')], graph, ran=("claim-anchor",))

    [invalid] = found
    assert invalid.code == CODE_INVALID
    assert f"`irminsul explain {code}` says how" in (invalid.suggestion or "")


def test_a_doc_id_names_no_finding_and_is_unused(graph: DocGraph) -> None:
    found = acknowledge(
        [_finding()],
        [_trailer('co-change alpha reason="still right"')],
        graph,
        ran=("co-change",),
    )

    assert CODE_INVALID not in [f.code for f in found]
    assert _only(found, CODE_UNUSED).severity is Severity.info
    assert _only(found, _CO_CHANGE).severity is Severity.warning


def test_a_trailer_naming_a_baseline_whose_path_is_also_a_doc_id_accepts_it(
    tmp_path: Path,
) -> None:
    write_config(tmp_path, project_name="ack", source_roots=["app"], extra='baseline = "thebase"\n')
    write(
        tmp_path,
        "docs/components/thebase.md",
        "---\nid: thebase\ntitle: Base\nstatus: stable\nsummary: A test doc.\ndescribes: []\n"
        "---\n\n# Base\n\nIt holds the baseline.\n",
    )
    grew = _finding(
        code="diff-integrity/baseline-grew",
        path="thebase",
        subject="thebase",
        about=("thebase",),
        suggestion="fix the new findings instead of recording them",
    )

    [accepted] = acknowledge(
        [grew],
        [_trailer('diff-integrity/baseline-grew thebase reason="the upgrade waits"')],
        load_graph(tmp_path),
        ran=("diff-integrity",),
    )

    assert accepted.code == "diff-integrity/baseline-grew"
    assert accepted.severity is Severity.info


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


def test_an_unused_trailer_says_it_does_nothing_and_names_the_fix(graph: DocGraph) -> None:
    trailer = _trailer('co-change docs/components/gone.md reason="x"')

    [unused] = acknowledge([], [trailer], graph, ran=("co-change",))

    assert unused.message == (
        "the Irminsul-Reviewed trailer in abc1234 matches no finding in this change, so it does "
        'nothing: co-change docs/components/gone.md reason="x"'
    )
    assert unused.suggestion == _NOTHING_TO_DO


def test_an_unused_trailer_names_the_other_code_its_path_and_subject_carry(graph: DocGraph) -> None:
    finding = _finding(
        code="diff-integrity/governing-claim-changed",
        path="docs/components/widget.md",
        subject="governs",
        about=("src/widget.py",),
    )
    trailer = _trailer('diff-integrity/claim-reworded docs/components/widget.md governs reason="x"')

    unused = _only(acknowledge([finding], [trailer], graph, ran=("diff-integrity",)), CODE_UNUSED)

    assert unused.message.endswith(
        "; the finding on `docs/components/widget.md` `governs` is "
        "`diff-integrity/governing-claim-changed`, not `diff-integrity/claim-reworded`"
    )
    assert unused.suggestion == (
        "add a trailer naming `diff-integrity/governing-claim-changed` to a later commit, if the "
        "finding is acceptable"
    )


def test_an_unused_trailer_asks_for_each_other_code_its_target_carries(graph: DocGraph) -> None:
    findings = [
        _finding(
            code="diff-integrity/governing-claim-changed",
            path="docs/components/widget.md",
            subject="governs",
            about=("src/widget.py",),
        ),
        _finding(
            code="diff-integrity/claim-reworded",
            path="docs/components/widget.md",
            subject="governs",
            about=("src/widget.py",),
        ),
    ]
    trailer = _trailer('diff-integrity/claim-removed docs/components/widget.md governs reason="x"')

    unused = _only(acknowledge(findings, [trailer], graph, ran=("diff-integrity",)), CODE_UNUSED)

    assert unused.suggestion == (
        "add a trailer naming each of `diff-integrity/claim-reworded`, "
        "`diff-integrity/governing-claim-changed` to a later commit, if the findings are acceptable"
    )


def test_an_unused_trailer_names_no_other_code_that_a_fix_answers(graph: DocGraph) -> None:
    finding = _finding(code="glossary-discipline/unlinked-term", path=_DOC, subject=_DOC)
    trailer = _trailer(f'co-change {_DOC} {_DOC} reason="x"')

    unused = _only(acknowledge([finding], [trailer], graph, ran=("co-change",)), CODE_UNUSED)

    assert "the finding on" not in unused.message
    assert unused.suggestion == _NOTHING_TO_DO


def test_an_unused_trailer_on_a_path_with_no_finding_names_no_other_code(graph: DocGraph) -> None:
    finding = _finding(code="diff-integrity/governing-claim-changed", subject="governs")
    trailer = _trailer('diff-integrity/claim-reworded docs/components/gone.md governs reason="x"')

    unused = _only(acknowledge([finding], [trailer], graph, ran=("diff-integrity",)), CODE_UNUSED)

    assert "the finding on" not in unused.message


def test_a_placeholder_reason_is_no_reason() -> None:
    assert parse('diff-integrity/claim-reworded docs/x.md reason="..."') == "gives no reason"
    assert parse('diff-integrity/claim-reworded docs/x.md reason=" ... "') == "gives no reason"


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


def test_the_suggestion_composes_the_trailer_clause(graph: DocGraph) -> None:
    finding = _finding()

    [out] = pipeline.finish([finding], graph)

    assert out.suggestion == (
        "update the doc; if you re-read the doc and it is still right, add this trailer: "
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
        == "on the commit that carries the last change to app/alpha.py, app/beta.py, or a later one"
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

    assert severities_of(tmp_path, _WEAKENED, "--diff", base) == ["error"]


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
    assert severities_of(tmp_path, _WEAKENED, "--diff", base) == ["error"]


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

    assert severities_of(tmp_path, _WEAKENED, "--diff", base) == ["error"]


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
    assert severities_of(tmp_path, _WEAKENED, "--diff", base) == ["info"]

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

    assert severities_of(tmp_path, _REWRITTEN, "--diff", base) == ["warning"]


def test_a_later_commit_to_the_record_brings_a_reviewed_typo_back_as_a_warning(
    tmp_path: Path,
) -> None:
    base = _record_repo(tmp_path, _TYPO)
    write(tmp_path, _RECORD, _record(_TYPO_FIXED))
    commit_all(tmp_path, "fix a typo\n\n" + reviewed(_REWRITTEN, _RECORD, reason="typo"))
    write(tmp_path, _RECORD, _record(_TYPO_FIXED).replace("Fine.", "Fine enough."))
    commit_all(tmp_path, "edit the consequences")

    assert severities_of(tmp_path, _REWRITTEN, "--diff", base) == ["warning"]


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


def test_a_later_delete_of_a_renamed_records_old_path_lapses_its_trailer(tmp_path: Path) -> None:
    """A copy with the typo fixed and then a delete of the original reads at the base as one
    rename. The trailer on the copy names the new path, and the delete changes the old one,
    which the finding is about too."""
    base = _record_repo(tmp_path, _TYPO)
    write(tmp_path, _REWRITTEN_TO, _record(_TYPO_FIXED, record_id="pick-a-lane"))
    commit_all(
        tmp_path,
        "copy the record and fix a typo\n\n" + reviewed(_REWRITTEN, _REWRITTEN_TO, reason="typo"),
    )
    git(tmp_path, "rm", "-q", _RECORD)
    commit_all(tmp_path, "remove the original record")

    assert severities_of(tmp_path, _REWRITTEN, "--diff", base) == ["warning"]


def test_a_trailer_whose_later_changes_git_cannot_read_acknowledges_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(tmp_path, project_name="ack", source_roots=["app"])
    write(tmp_path, "app/alpha.py", "a = 1\n")
    write(tmp_path, _DOC, component_doc("alpha", "app/alpha.py"))
    base = seed_repo(tmp_path, "seed")
    write(tmp_path, "app/alpha.py", "a = 2\n")
    commit_all(tmp_path, f"change the source\n\n{reviewed(_CO_CHANGE, _DOC)}")
    monkeypatch.setattr(changes, "files_changed_after", lambda *args: None)

    assert severities_of(tmp_path, _CO_CHANGE, "--diff", base) == ["warning"]


_GOVERNS_CLAIM = (
    "  - id: governs\n    state: implemented\n    kind: invariant\n"
    "    relation: governs-evidence\n    claim: The widget runs.\n"
    "    evidence:\n      - src/widget.py\n"
)
_NOTES_CLAIM = (
    "  - id: notes\n    state: implemented\n    kind: invariant\n"
    "    claim: The widget keeps notes.\n    evidence:\n      - src/widget.py\n"
)
_GOVERNED = (
    "---\nid: widget\ntitle: Widget\nstatus: stable\nsummary: A test doc.\n"
    "describes: [src/widget.py]\nclaims:\n"
    + _GOVERNS_CLAIM
    + _NOTES_CLAIM
    + "inventory:\n  - kind: cli-options\n    source: src/widget.py\n    complete: true\n"
    "---\n\n# Widget\n\nIt runs.\n"
)
_WORKFLOW_PATH = ".github/workflows/docs-pr.yml"
_RENAMED_WORKFLOW = ".github/workflows/docs-renamed.yml"
_WORKFLOW = (
    "name: docs\n\non: pull_request\n\njobs:\n  check:\n    runs-on: ubuntu-latest\n"
    "    steps:\n      - run: irminsul check --diff origin/main\n"
)
_BASELINE_PATH = ".irminsul-baseline.json"
_BASELINE_EMPTY = '{"version":1,"findings":[]}'
_BASELINE_GROWN = (
    '{"version":1,"findings":[{"check":"links","path":"a.md","message":"m","code":"links/x"}]}'
)
_ADOPTION_PATH = ".irminsul-adoption.json"
_ADOPTION = '{"version":1,"unowned":["src/old.py"],"sources":[],"bindings":{}}'
_THEBASE_DOC = (
    "---\nid: thebase\ntitle: Base\nstatus: stable\nsummary: A test doc.\ndescribes: []\n"
    "---\n\n# Base\n\nIt holds the baseline.\n"
)

Arrange = Callable[[Path], str]


def _seeded(root: Path, *, extra: str = "", files: dict[str, str] | None = None) -> str:
    write_config(root, project_name="ack", source_roots=["src"], extra=extra)
    write(root, "src/widget.py", "def run():\n    return 1\n")
    write(root, _WIDGET, _GOVERNED)
    write(root, _RECORD, _record(_TYPO))
    write(root, _WORKFLOW_PATH, _WORKFLOW)
    for path, text in (files or {}).items():
        write(root, path, text)
    return seed_repo(root, "adopted")


def _changed(
    changes: dict[str, str | None],
    *,
    extra: str = "",
    files: dict[str, str] | None = None,
    moves: dict[str, str] | None = None,
) -> Arrange:
    """A repository whose base is the commit before one change: `moves` are `git mv`s, and
    `changes` writes each file, or deletes it when its text is None, and commits the lot."""

    def arrange(root: Path) -> str:
        base = _seeded(root, extra=extra, files=files)
        for old, new in (moves or {}).items():
            git(root, "mv", old, new)
        for path, text in changes.items():
            if text is None:
                (root / path).unlink()
            else:
                write(root, path, text)
        commit_all(root, "the change")
        return base

    return arrange


_PRINTED = re.compile(r"`(Irminsul-Reviewed: [^`]*)`")


def _printed_trailer(finding: dict[str, Any]) -> str | None:
    found = _PRINTED.search(finding.get("suggestion") or "")
    return found.group(1) if found else None


_ROUNDTRIP: list[Any] = [
    pytest.param(
        "diff-integrity/baseline-grew",
        _changed({_BASELINE_PATH: _BASELINE_GROWN}, files={_BASELINE_PATH: _BASELINE_EMPTY}),
        id="baseline-grew",
    ),
    pytest.param(
        "diff-integrity/adoption-record-removed",
        _changed({_ADOPTION_PATH: None}, files={_ADOPTION_PATH: _ADOPTION}),
        id="adoption-record-removed",
    ),
    pytest.param(
        "diff-integrity/claim-reworded",
        _changed({_WIDGET: _GOVERNED.replace("keeps notes.", "keeps every note.")}),
        id="claim-reworded",
    ),
    pytest.param(
        "diff-integrity/claim-removed",
        _changed({_WIDGET: _GOVERNED.replace(_NOTES_CLAIM, "")}),
        id="claim-removed",
    ),
    pytest.param(
        "diff-integrity/governing-claim-removed",
        _changed({_WIDGET: _GOVERNED.replace(_GOVERNS_CLAIM, "")}),
        id="governing-claim-removed",
    ),
    pytest.param(
        "diff-integrity/governing-claim-changed",
        _changed({_WIDGET: _GOVERNED.replace("The widget runs.", "The widget halts.")}),
        id="governing-claim-changed",
    ),
    pytest.param(
        "diff-integrity/inventory-weakened",
        _changed({_WIDGET: _GOVERNED.replace("    complete: true\n", "")}),
        id="inventory-weakened",
    ),
    pytest.param(
        "diff-integrity/gate-file-changed",
        _changed({_WORKFLOW_PATH: _WORKFLOW + "# c\n"}),
        id="gate-file-changed",
    ),
    pytest.param(
        "diff-integrity/check-disabled",
        _changed(
            {
                "irminsul.toml": config_toml(
                    project_name="ack",
                    source_roots=["src"],
                    extra='[checks]\nenabled = ["frontmatter"]\n',
                )
            },
            extra='[checks]\nenabled = ["frontmatter", "links"]\n',
        ),
        id="check-disabled",
    ),
    pytest.param(
        "diff-integrity/layer-rule-disabled",
        _changed(
            {
                "irminsul.toml": config_toml(
                    project_name="ack",
                    source_roots=["src"],
                    extra="[layers.components]\nrequire_tests = false\n",
                )
            },
            extra="[layers.components]\nrequire_tests = true\n",
        ),
        id="layer-rule-disabled",
    ),
    pytest.param(
        "diff-integrity/setting-weakened",
        _changed(
            {
                "irminsul.toml": config_toml(
                    project_name="ack",
                    source_roots=["src"],
                    extra="[checks.parent_child]\nlength_warning_lines = 3000\n",
                )
            },
            extra="[checks.parent_child]\nlength_warning_lines = 300\n",
        ),
        id="setting-weakened",
    ),
    pytest.param(
        "diff-integrity/source-excluded",
        _changed(
            {
                "irminsul.toml": config_toml(
                    project_name="ack",
                    source_roots=["src"],
                    extra='source_excludes = ["src/a/**", "src/b/**"]\n',
                )
            }
        ),
        id="source-excluded",
    ),
    pytest.param(
        "diff-integrity/extra-doc-removed",
        _changed(
            {"irminsul.toml": config_toml(project_name="ack", source_roots=["src"])},
            extra='extra_docs = ["NOTES.md"]\n',
            files={"NOTES.md": "Notes.\n"},
        ),
        id="extra-doc-removed",
    ),
    pytest.param(
        "diff-integrity/rules-narrowed",
        _changed(
            {"irminsul.toml": config_toml(project_name="ack", source_roots=["src"])},
            extra='[[surface.rules]]\nkind = "k"\nglobs = ["src/**"]\npattern = "x"\nidentity = "i"\n',
        ),
        id="rules-narrowed",
    ),
    pytest.param(
        "diff-integrity/unreviewed-setting-change",
        _changed(
            {
                "irminsul.toml": config_toml(
                    project_name="ack",
                    source_roots=["src"],
                    extra='[frameworks]\ncommand_names = ["tool"]\n',
                )
            }
        ),
        id="unreviewed-setting-change",
    ),
    pytest.param(
        "diff-integrity/decision-rewritten",
        _changed({_RECORD: _record(_TYPO_FIXED)}),
        id="decision-rewritten",
    ),
    pytest.param(
        "co-change/unreflected-change",
        _changed({"src/widget.py": "def run():\n    return 2\n"}),
        id="co-change",
    ),
    pytest.param(
        "diff-integrity/gate-file-changed",
        _changed({}, moves={_WORKFLOW_PATH: _RENAMED_WORKFLOW}),
        id="gate-file-renamed",
    ),
    pytest.param(
        "diff-integrity/gate-file-changed",
        _changed({_WORKFLOW_PATH: None}),
        id="gate-file-deleted",
    ),
    pytest.param(
        "diff-integrity/baseline-grew",
        _changed(
            {"thebase": _BASELINE_GROWN},
            extra='baseline = "thebase"\n',
            files={"thebase": _BASELINE_EMPTY, "docs/components/thebase.md": _THEBASE_DOC},
        ),
        id="configured-baseline-path-is-a-doc-id",
    ),
    pytest.param(
        "diff-integrity/decision-rewritten",
        _changed(
            {_REWRITTEN_TO: _record(_TYPO_FIXED, record_id="pick-a-lane")},
            moves={_RECORD: _REWRITTEN_TO},
        ),
        id="decision-renamed",
    ),
]


@pytest.mark.parametrize(("code", "arrange"), _ROUNDTRIP)
def test_the_trailer_a_finding_prints_accepts_that_finding(
    tmp_path: Path, code: str, arrange: Arrange
) -> None:
    """The printed trailer, with a reason, on a later commit accepts the finding at info."""
    base = arrange(tmp_path)
    raised = findings_of(tmp_path, code, "--diff", base)
    printed = [_printed_trailer(finding) for finding in raised]

    assert raised and all(finding["severity"] != "info" for finding in raised)
    assert None not in printed
    git(
        tmp_path,
        "commit",
        "--allow-empty",
        "-qm",
        "acknowledge what the findings print\n\n"
        + "\n".join(line.replace('reason="..."', 'reason="re-read"') for line in printed if line),
    )

    assert severities_of(tmp_path, code, "--diff", base) == ["info"] * len(raised)


def test_an_unused_trailer_names_the_code_the_claims_finding_carries(tmp_path: Path) -> None:
    base = _changed({_WIDGET: _GOVERNED.replace("The widget runs.", "The widget halts.")})(tmp_path)
    git(
        tmp_path,
        "commit",
        "--allow-empty",
        "-qm",
        "re-read the claim\n\n" + reviewed("diff-integrity/claim-reworded", _WIDGET, "governs"),
    )

    [unused] = findings_of(tmp_path, CODE_UNUSED, "--diff", base)

    assert (
        "the finding on `docs/components/widget.md` `governs` is "
        "`diff-integrity/governing-claim-changed`, not `diff-integrity/claim-reworded`"
    ) in unused["message"]


@pytest.mark.parametrize(("code", "arrange"), _ROUNDTRIP)
def test_a_printed_trailer_pasted_unedited_accepts_nothing(
    tmp_path: Path, code: str, arrange: Arrange
) -> None:
    """The placeholder reason is what `trailer_for` prints, so a trailer pasted as printed
    must not acknowledge the finding it came from."""
    base = arrange(tmp_path)
    raised = findings_of(tmp_path, code, "--diff", base)
    printed = [_printed_trailer(finding) for finding in raised]
    assert raised and None not in printed
    git(
        tmp_path,
        "commit",
        "--allow-empty",
        "-qm",
        "paste the printed trailers unedited\n\n" + "\n".join(line for line in printed if line),
    )

    assert severities_of(tmp_path, code, "--diff", base) == [
        finding["severity"] for finding in raised
    ]
    assert findings_of(tmp_path, CODE_INVALID, "--diff", base)


_TRAILER_HEADING = (
    "1 finding(s) can be answered by a trailer, if you have judged them acceptable; each goes "
    "on the commit that carries the last change to its files, or a later one:"
)
_CLAIM_TRAILER = (
    "Irminsul-Reviewed: diff-integrity/governing-claim-changed docs/components/widget.md governs "
    'reason="..."'
)


def test_check_lists_the_trailer_an_open_finding_can_take_before_the_summary(
    tmp_path: Path,
) -> None:
    base = _changed({_WIDGET: _GOVERNED.replace("The widget runs.", "The widget halts.")})(tmp_path)

    _, output = invoke(tmp_path, "check", "--diff", base)

    lines = output.splitlines()
    [heading] = [index for index, line in enumerate(lines) if line == _TRAILER_HEADING]
    assert lines[heading + 1] == f"  {_CLAIM_TRAILER}"
    assert re.fullmatch(r"\d+ errors?, \d+ warnings?.*", lines[-1]), lines[-1]


def test_check_lists_no_trailers_when_no_open_finding_takes_one(tmp_path: Path) -> None:
    base = _seeded(tmp_path)

    _, output = invoke(tmp_path, "check", "--diff", base)

    assert _TRAILER_HEADING not in output


def test_an_accepted_finding_is_not_listed_for_a_trailer(tmp_path: Path) -> None:
    base = _changed({_WIDGET: _GOVERNED.replace("The widget runs.", "The widget halts.")})(tmp_path)
    git(
        tmp_path,
        "commit",
        "--allow-empty",
        "-qm",
        "re-read the claim\n\n"
        + reviewed("diff-integrity/governing-claim-changed", _WIDGET, "governs"),
    )

    _, output = invoke(tmp_path, "check", "--diff", base)

    assert _TRAILER_HEADING not in output


def test_the_github_format_does_not_list_the_trailers(tmp_path: Path) -> None:
    base = _changed({_WIDGET: _GOVERNED.replace("The widget runs.", "The widget halts.")})(tmp_path)

    _, output = invoke(tmp_path, "check", "--diff", base, "--format", "github")

    assert _TRAILER_HEADING not in output


def test_check_json_gives_each_finding_its_trailer_or_none(tmp_path: Path) -> None:
    base = _changed({_WIDGET: _GOVERNED.replace("The widget runs.", "The widget halts.")})(tmp_path)

    records = check_findings(tmp_path, "--diff", base)

    assert all("trailer" in record for record in records)
    [claim] = [r for r in records if r["code"] == "diff-integrity/governing-claim-changed"]
    assert claim["trailer"] == _CLAIM_TRAILER
    assert [r["trailer"] for r in records if r is not claim] == [None] * (len(records) - 1)


def test_context_after_edit_lists_the_trailers_before_its_next_actions(tmp_path: Path) -> None:
    base = _changed({_WIDGET: _GOVERNED.replace("The widget runs.", "The widget halts.")})(tmp_path)

    _, output = invoke(tmp_path, "context", "--after-edit", "--base-ref", base)

    lines = output.splitlines()
    assert _TRAILER_HEADING in lines
    assert f"  {_CLAIM_TRAILER}" in lines
    assert lines.index(_TRAILER_HEADING) < lines.index("Next actions:")
