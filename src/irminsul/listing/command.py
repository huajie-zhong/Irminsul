"""`irminsul list` — enumerate docs by condition."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from irminsul.checks.base import Finding, Severity
from irminsul.checks.orphans import OrphansCheck
from irminsul.checks.stale_reaper import StaleReaperCheck
from irminsul.checks.uniqueness import UniquenessCheck
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph


def list_orphans(repo_root: Path, *, fmt: str) -> None:
    graph = build_graph(repo_root, load(find_config(repo_root)))
    _print(OrphansCheck().run(graph), fmt)


def list_stale(repo_root: Path, *, fmt: str) -> None:
    graph = build_graph(repo_root, load(find_config(repo_root)))
    _print(StaleReaperCheck().run(graph), fmt)


def list_undocumented(repo_root: Path, *, fmt: str) -> None:
    graph = build_graph(repo_root, load(find_config(repo_root)))
    findings = [
        f
        for f in UniquenessCheck().run(graph)
        if f.severity == Severity.warning and "no doc claims it" in f.message
    ]
    _print(findings, fmt)


def _print(findings: list[Finding], fmt: str) -> None:
    if fmt == "json":
        data = [
            {
                "check": f.check,
                "severity": f.severity.value,
                "message": f.message,
                "path": f.path.as_posix() if f.path else None,
                "doc_id": f.doc_id,
            }
            for f in findings
        ]
        typer.echo(json.dumps(data, indent=2))
    else:
        for f in findings:
            loc = f.path.as_posix() if f.path else "<repo>"
            typer.echo(f"{loc}: {f.message}")
        if not findings:
            typer.echo("(none)")
