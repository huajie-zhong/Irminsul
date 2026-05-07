"""Irminsul command-line entry point.

Two scripts in `pyproject.toml` (`irminsul` and `irm`) both bind to `app`.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from irminsul import __version__

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
    path: Annotated[
        Path,
        typer.Option(
            "--path",
            help="Root of the codebase to scaffold. Defaults to current directory.",
        ),
    ] = Path("."),
) -> None:
    """Scaffold the docs skeleton, irminsul.toml, and CI workflows."""
    typer.echo(f"[init] path={path.resolve()} interactive={not no_interactive}")
    typer.echo("init: not yet implemented (Sprint 1, Week 4)")
    raise typer.Exit(code=2)


@app.command()
def check(
    scope: Annotated[
        Scope,
        typer.Option("--scope", help="Which check tier to run."),
    ] = Scope.hard,
    llm: Annotated[
        bool,
        typer.Option("--llm", help="Include LLM advisory checks (Phase 2)."),
    ] = False,
    path: Annotated[
        Path,
        typer.Option(
            "--path",
            help="Root of the codebase to check. Defaults to current directory.",
        ),
    ] = Path("."),
) -> None:
    """Run the configured checks. Hard findings exit non-zero."""
    typer.echo(f"[check] scope={scope.value} llm={llm} path={path.resolve()}")
    typer.echo("check: not yet implemented (Sprint 1, Weeks 2-3)")
    raise typer.Exit(code=2)


@app.command()
def render(
    path: Annotated[
        Path,
        typer.Option(
            "--path",
            help="Root of the codebase to render. Defaults to current directory.",
        ),
    ] = Path("."),
) -> None:
    """Build the rendered docs site."""
    typer.echo(f"[render] path={path.resolve()}")
    typer.echo("render: not yet implemented (Sprint 1, Week 4)")
    raise typer.Exit(code=2)


if __name__ == "__main__":  # pragma: no cover
    app()
