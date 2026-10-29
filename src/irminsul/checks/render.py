"""Findings rendered for machines: the `--format json` envelope and GitHub workflow commands."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from irminsul.adoption import assess
from irminsul.checks.base import Finding, Severity, finding_records, summarize

if TYPE_CHECKING:
    from irminsul.checks.pipeline import RunResult
    from irminsul.docgraph import DocGraph


def findings_json(
    findings: list[Finding],
    graph: DocGraph,
    run: RunResult | None = None,
    delta: dict[str, object] | None = None,
) -> str:
    """The `--format json` envelope `check` and `anchors` print, and their MCP tools return.

    Given the run the findings came from, it also reports what that run left unreported,
    the `baseline` object and, in a repository that has an adoption record, the `adoption`
    object, so no surface that reports a run can leave either out.
    """
    counts = summarize(findings)
    payload: dict[str, object] = {
        "version": 1,
        "findings": finding_records(findings, graph),
        "summary": {
            "errors": counts[Severity.error],
            "warnings": counts[Severity.warning],
            "info": counts[Severity.info],
        },
    }
    if run is not None:
        payload["baseline"] = run.baseline_report()
    if delta is not None:
        payload["delta"] = delta
    if run is not None and (assessment := assess(graph)) is not None:
        payload["adoption"] = assessment.as_json()
    return json.dumps(payload, indent=2)


_GITHUB_COMMAND = {
    Severity.error: "error",
    Severity.warning: "warning",
    Severity.info: "notice",
}


def escape_github_data(value: str) -> str:
    """Escape workflow-command message data per the GitHub Actions spec."""
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_github_property(value: str) -> str:
    """Escape workflow-command property values (data escapes plus ',' and ':')."""
    return escape_github_data(value).replace(",", "%2C").replace(":", "%3A")


def github_annotation(finding: Finding) -> str:
    """One `::error|::warning|::notice` workflow command per finding."""
    props: list[str] = []
    if finding.path is not None:
        props.append(f"file={_escape_github_property(finding.path.as_posix())}")
    if finding.line is not None:
        props.append(f"line={finding.line}")
    # The code rides in `title=`: the Actions runner only recognizes
    # file/line/col/endLine/endColumn/title on issue commands and silently
    # drops unknown properties, so a dedicated `code=` property would never
    # reach the PR annotation.
    props.append("title=" + _escape_github_property(f"irminsul {finding.code}"))
    data = finding.message
    if finding.suggestion:
        data = f"{data} — {finding.suggestion}"
    return f"::{_GITHUB_COMMAND[finding.severity]} {','.join(props)}::{escape_github_data(data)}"
