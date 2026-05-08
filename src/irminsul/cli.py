"""Irminsul command-line entry point.

Two scripts in `pyproject.toml` (`irminsul` and `irm`) both bind to `app`.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from irminsul import __version__
from irminsul.checks import (
    HARD_REGISTRY,
    LLM_REGISTRY,
    SOFT_REGISTRY,
    Finding,
    Severity,
    sort_findings,
    summarize,
)
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph
from irminsul.init.command import (
    detect_code_signals,
    run_init,
    run_init_docs_only,
)
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
    """Scaffold the docs skeleton, irminsul.toml, and CI workflows (single-repo)."""
    target = path.resolve()
    target.mkdir(parents=True, exist_ok=True)
    interactive = not no_interactive

    if interactive and not detect_code_signals(target):
        answer = typer.confirm(
            "No code detected here. Is this a docs-only repo with code in a separate repo?",
            default=False,
        )
        if answer:
            code_repo = typer.prompt(
                "Code repo (GitHub owner/repo or local path, e.g. acme/my-public-code)"
            )
            run_init_docs_only(target, interactive=interactive, code_repo=code_repo, force=force)
            return
    elif not interactive and not detect_code_signals(target):
        typer.echo(
            typer.style(
                "No code detected in the target directory. "
                "If this is a docs-only repo, use `irminsul init-docs-only --code-repo <spec-or-path>` instead.",
                fg="red",
            )
        )
        raise typer.Exit(code=2)

    run_init(target, interactive=interactive, force=force)


@app.command("init-docs-only")
def init_docs_only(
    code_repo: Annotated[
        str | None,
        typer.Option(
            "--code-repo",
            help=(
                "Code repository spec: GitHub 'owner/repo' or a local path. "
                "The code is cloned/placed as a gitignored subfolder inside this docs repo."
            ),
        ),
    ] = None,
    no_interactive: Annotated[
        bool,
        typer.Option("--no-interactive", help="Use defaults instead of prompting."),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite scaffold files that already exist."),
    ] = False,
    path: Annotated[
        Path,
        typer.Option("--path", help="Root of the docs-only repo. Defaults to current directory."),
    ] = Path("."),
) -> None:
    """Scaffold a docs-only repo where code lives in a separate repository (Topology A).

    The code repo is cloned as a gitignored subfolder inside this docs repo so
    that all source-coverage checks work without cross-repo filesystem access.
    Topology B (code at a sibling filesystem path) is not yet supported.
    """
    target = path.resolve()
    target.mkdir(parents=True, exist_ok=True)
    interactive = not no_interactive

    if interactive and detect_code_signals(target):
        answer = typer.confirm(
            "This directory looks like a code repo. Are you sure you want two-repo (docs-only) mode?",
            default=False,
        )
        if not answer:
            typer.echo("Hint: use `irminsul init` for a single-repo setup.")
            raise typer.Exit(code=0)
    elif not interactive and detect_code_signals(target):
        typer.echo(
            typer.style(
                "This directory contains code signals. "
                "For a single-repo setup use `irminsul init` instead.",
                fg="red",
            )
        )
        raise typer.Exit(code=2)

    run_init_docs_only(target, interactive=interactive, code_repo=code_repo, force=force)


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
    if finding.suggestion:
        typer.echo(typer.style(f"      → {finding.suggestion}", dim=True))


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
        typer.Option("--llm", help="Include LLM advisory checks."),
    ] = False,
    llm_budget: Annotated[
        float | None,
        typer.Option("--llm-budget", help="Override the LLM cost ceiling (USD) for this run."),
    ] = None,
    strict: Annotated[
        bool,
        typer.Option(
            "--strict",
            help="Promote warnings to errors for the exit code. Hard checks always block.",
        ),
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
                typer.echo(
                    typer.style(
                        f"note: hard check '{check_name}' not yet implemented; skipping.",
                        fg="yellow",
                    )
                )
                continue
            findings.extend(cls().run(graph))

    if scope in (Scope.soft, Scope.all):
        for check_name in config.checks.soft_deterministic:
            cls = SOFT_REGISTRY.get(check_name)
            if cls is None:
                typer.echo(
                    typer.style(
                        f"note: soft check '{check_name}' not yet implemented; skipping.",
                        fg="yellow",
                    )
                )
                continue
            findings.extend(cls().run(graph))

    if llm:
        from irminsul.llm.client import LlmClient

        budget = llm_budget if llm_budget is not None else config.llm.max_cost_usd
        llm_client = LlmClient(
            provider=config.llm.provider,
            model=config.llm.model,
            max_cost_usd=budget,
            cache_path=repo_root / config.llm.cache_path,
            required_in_ci=config.llm.required_in_ci,
        )

        if not llm_client.is_available():
            if config.llm.required_in_ci:
                findings.append(
                    Finding(
                        check="llm",
                        severity=Severity.error,
                        message=(
                            f"LLM checks required (required_in_ci=true) "
                            f"but no API key found for provider '{config.llm.provider}'"
                        ),
                    )
                )
            else:
                for check_name in config.checks.soft_llm:
                    if check_name in LLM_REGISTRY:
                        findings.append(
                            Finding(
                                check=check_name,
                                severity=Severity.info,
                                message=(
                                    f"LLM check skipped: no API key configured "
                                    f"for provider '{config.llm.provider}'"
                                ),
                            )
                        )
        else:
            calls_before = sum(1 for e in llm_client._cache.values())
            for check_name in config.checks.soft_llm:
                cls_llm = LLM_REGISTRY.get(check_name)
                if cls_llm is None:
                    typer.echo(
                        typer.style(
                            f"note: LLM check '{check_name}' not yet implemented; skipping.",
                            fg="yellow",
                        )
                    )
                    continue
                findings.extend(cls_llm(llm_client=llm_client).run(graph))

            spent = budget - llm_client.remaining_budget()
            cache_size = sum(1 for e in llm_client._cache.values())
            hits = max(0, cache_size - calls_before)
            typer.echo(
                typer.style(
                    f"LLM: ${spent:.4f} / ${budget:.2f} budget used"
                    + (f"; {hits} cache hit(s)" if hits else ""),
                    dim=True,
                )
            )

    findings = sort_findings(findings)
    for finding in findings:
        _print_finding(finding)

    counts = summarize(findings)
    _print_summary(counts)

    fail = counts[Severity.error] > 0 or (strict and counts[Severity.warning] > 0)
    raise typer.Exit(code=1 if fail else 0)


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


_new_app = typer.Typer(name="new", help="Scaffold a new doc atom.", no_args_is_help=True)
app.add_typer(_new_app)


@_new_app.command("adr")
def new_adr(
    title: Annotated[str, typer.Argument(help="Title of the ADR.")],
    owner: Annotated[
        str,
        typer.Option("--owner", help="Doc owner (GitHub handle). Defaults to @TODO."),
    ] = "@TODO",
    force: Annotated[bool, typer.Option("--force")] = False,
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """Scaffold a new Architecture Decision Record."""
    from irminsul.new.command import NewSpec, write_new

    repo_root = path.resolve()
    config = load(find_config(repo_root))
    spec = NewSpec(kind="adr", title=title, owner=owner, extra={})
    try:
        dest = write_new(repo_root, spec, config, force=force)
    except FileExistsError as e:
        typer.echo(typer.style(f"already exists: {e}", fg="yellow"))
        raise typer.Exit(1) from e
    rel = dest.relative_to(repo_root).as_posix()
    typer.echo(typer.style(f"created: {rel}", fg="green"))


@_new_app.command("component")
def new_component(
    title: Annotated[str, typer.Argument(help="Name of the component.")],
    owner: Annotated[str, typer.Option("--owner")] = "@TODO",
    force: Annotated[bool, typer.Option("--force")] = False,
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """Scaffold a new component doc."""
    from irminsul.new.command import NewSpec, write_new

    repo_root = path.resolve()
    config = load(find_config(repo_root))
    spec = NewSpec(kind="component", title=title, owner=owner, extra={})
    try:
        dest = write_new(repo_root, spec, config, force=force)
    except FileExistsError as e:
        typer.echo(typer.style(f"already exists: {e}", fg="yellow"))
        raise typer.Exit(1) from e
    rel = dest.relative_to(repo_root).as_posix()
    typer.echo(typer.style(f"created: {rel}", fg="green"))


@_new_app.command("rfc")
def new_rfc(
    title: Annotated[str, typer.Argument(help="Title of the RFC.")],
    owner: Annotated[str, typer.Option("--owner")] = "@TODO",
    force: Annotated[bool, typer.Option("--force")] = False,
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """Scaffold a new RFC."""
    from irminsul.new.command import NewSpec, write_new

    repo_root = path.resolve()
    config = load(find_config(repo_root))
    spec = NewSpec(kind="rfc", title=title, owner=owner, extra={})
    try:
        dest = write_new(repo_root, spec, config, force=force)
    except FileExistsError as e:
        typer.echo(typer.style(f"already exists: {e}", fg="yellow"))
        raise typer.Exit(1) from e
    rel = dest.relative_to(repo_root).as_posix()
    typer.echo(typer.style(f"created: {rel}", fg="green"))


_list_app = typer.Typer(name="list", help="List docs by condition.", no_args_is_help=True)
app.add_typer(_list_app)


@_list_app.command("orphans")
def list_orphans(
    fmt: Annotated[str, typer.Option("--format", help="Output format: plain or json.")] = "plain",
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """List docs with no inbound references."""
    from irminsul.listing.command import list_orphans as _list_orphans

    _list_orphans(path.resolve(), fmt=fmt)


@_list_app.command("stale")
def list_stale(
    fmt: Annotated[str, typer.Option("--format")] = "plain",
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """List deprecated docs that are past the stale threshold."""
    from irminsul.listing.command import list_stale as _list_stale

    _list_stale(path.resolve(), fmt=fmt)


@_list_app.command("undocumented")
def list_undocumented(
    fmt: Annotated[str, typer.Option("--format")] = "plain",
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """List source files in covered directories that no doc claims."""
    from irminsul.listing.command import list_undocumented as _list_undocumented

    _list_undocumented(path.resolve(), fmt=fmt)


@app.command()
def regen(
    language: Annotated[
        str,
        typer.Option("--language", help="Language to regenerate reference docs for."),
    ] = "python",
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """Regenerate reference docs from source (currently Python only)."""
    if language != "python":
        typer.echo(
            typer.style(
                f"TypeScript reference regeneration deferred to Sprint 3 "
                f"(got --language={language})",
                fg="yellow",
            )
        )
        raise typer.Exit(code=0)

    from irminsul.regen.python import regen_python

    repo_root = path.resolve()
    config = load(find_config(repo_root))
    written = regen_python(repo_root, config)
    for p in written:
        rel = p.relative_to(repo_root).as_posix()
        typer.echo(f"  {rel}")
    typer.echo(typer.style(f"regenerated {len(written)} reference stub(s)", fg="green"))


if __name__ == "__main__":  # pragma: no cover
    app()
