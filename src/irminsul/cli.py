"""Irminsul command-line entry point.

Two scripts in `pyproject.toml` (`irminsul` and `irm`) both bind to `app`.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from irminsul import __version__
from irminsul.checks import HARD_REGISTRY, Finding, Severity, sort_findings, summarize
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph
from irminsul.init.command import run_init
from irminsul.render.mkdocs import MkDocsRenderer, MkDocsRenderError

app = typer.Typer(
    name="irminsul",
    help="A documentation system for complex codebases.",
    no_args_is_help=True,
    add_completion=False,
)


class Scope(StrEnum):
    hard = "hard"
    soft = "soft"
    all = "all"


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"irminsul {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Irminsul — enforce a documentation system in CI."""


@app.command()
def init(
    no_interactive: Annotated[
        bool,
        typer.Option(
            "--no-interactive",
            help="Use defaults instead of prompting. CI-friendly.",
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Overwrite scaffold files that already exist.",
        ),
    ] = False,
    path: Annotated[
        Path,
        typer.Option(
            "--path",
            help="Root of the codebase to scaffold. Defaults to current directory.",
        ),
    ] = Path("."),
) -> None:
    """Scaffold the docs skeleton, irminsul.toml, and CI workflows."""
    target = path.resolve()
    target.mkdir(parents=True, exist_ok=True)
    run_init(target, interactive=not no_interactive, force=force)


_SEVERITY_STYLE = {
    Severity.error: ("red", True),
    Severity.warning: ("yellow", True),
    Severity.info: ("cyan", False),
}


def _format_location(finding: Finding) -> str:
    if finding.path is None:
        return "<repo>"
    posix = finding.path.as_posix()
    if finding.line is None:
        return posix
    return f"{posix}:{finding.line}"


def _print_finding(finding: Finding) -> None:
    color, bold = _SEVERITY_STYLE[finding.severity]
    severity_str = typer.style(finding.severity.value.ljust(7), fg=color, bold=bold)
    location = _format_location(finding)
    typer.echo(f"{location}  {severity_str}  [{finding.check}]  {finding.message}")


def _print_summary(counts: dict[Severity, int]) -> None:
    parts: list[str] = [
        f"{counts[Severity.error]} error{'s' if counts[Severity.error] != 1 else ''}",
        f"{counts[Severity.warning]} warning{'s' if counts[Severity.warning] != 1 else ''}",
    ]
    if counts[Severity.info]:
        parts.append(f"{counts[Severity.info]} info")
    typer.echo(", ".join(parts))


@app.command()
def check(
    scope: Annotated[
        Scope,
        typer.Option("--scope", help="Which check tier to run."),
    ] = Scope.hard,
    llm: Annotated[
        bool,
        typer.Option("--llm", help="Include LLM advisory checks (Phase 2; no-op for now)."),
    ] = False,
    path: Annotated[
        Path,
        typer.Option(
            "--path",
            help="Root of the codebase to check. Defaults to current directory.",
        ),
    ] = Path("."),
) -> None:
    """Run the configured checks. Errors exit non-zero."""
    repo_root = path.resolve()
    config_path = find_config(repo_root)
    config = load(config_path)
    graph = build_graph(repo_root, config)

    findings: list[Finding] = []

    if scope in (Scope.hard, Scope.all):
        for check_name in config.checks.hard:
            cls = HARD_REGISTRY.get(check_name)
            if cls is None:
                # Configured check not implemented yet — note it but don't fail.
                typer.echo(
                    typer.style(
                        f"note: hard check '{check_name}' not yet implemented; skipping.",
                        fg="yellow",
                    )
                )
                continue
            findings.extend(cls().run(graph))

    if scope in (Scope.soft, Scope.all):
        # Sprint 1 ships no soft-deterministic checks; Sprint 2 will populate this.
        pass

    if llm:
        typer.echo(
            typer.style(
                "note: --llm is a Phase 2 feature; no LLM checks ran.",
                fg="yellow",
            )
        )

    findings = sort_findings(findings)
    for finding in findings:
        _print_finding(finding)

    counts = summarize(findings)
    _print_summary(counts)

    raise typer.Exit(code=1 if counts[Severity.error] else 0)


@app.command()
def render(
    path: Annotated[
        Path,
        typer.Option(
            "--path",
            help="Root of the codebase to render. Defaults to current directory.",
        ),
    ] = Path("."),
    out_dir: Annotated[
        Path | None,
        typer.Option(
            "--out-dir",
            help="Override the site output directory (default from irminsul.toml).",
        ),
    ] = None,
) -> None:
    """Build the rendered docs site."""
    repo_root = path.resolve()
    config_path = find_config(repo_root)
    config = load(config_path)
    graph = build_graph(repo_root, config)

    target_out = (out_dir or repo_root / config.render.site_dir).resolve()

    if config.render.target == "none":
        typer.echo("render.target = 'none' in irminsul.toml; nothing to render.")
        raise typer.Exit(code=0)

    if config.render.target != "mkdocs":
        typer.echo(
            typer.style(
                f"unknown render target '{config.render.target}'; only 'mkdocs' is implemented.",
                fg="red",
            )
        )
        raise typer.Exit(code=2)

    renderer = MkDocsRenderer()
    try:
        renderer.build(graph, target_out)
    except MkDocsRenderError as e:
        typer.echo(typer.style(str(e), fg="red"))
        raise typer.Exit(code=1) from e

    typer.echo(typer.style(f"site built at {target_out}", fg="green"))


if __name__ == "__main__":  # pragma: no cover
    app()
