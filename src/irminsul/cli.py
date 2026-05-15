"""Irminsul command-line entry point.

Two scripts in `pyproject.toml` (`irminsul` and `irm`) both bind to `app`.
"""

from __future__ import annotations

import datetime as _dt
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from irminsul import __version__
from irminsul.checks import (
    HARD_REGISTRY,
    LLM_REGISTRY,
    SOFT_REGISTRY,
    Check,
    Finding,
    Fix,
    Severity,
    sort_findings,
    summarize,
)
from irminsul.config import IrminsulConfig, find_config, load
from irminsul.docgraph import DocGraph, build_graph
from irminsul.init.command import (
    detect_code_signals,
    run_init,
    run_init_docs_only,
    run_init_fresh,
    run_init_fresh_docs_only,
)
from irminsul.render.mkdocs import MkDocsRenderer, MkDocsRenderError
from irminsul.seed.command import (
    PIB_INTRO,
    gather_answers_from_flags,
    gather_answers_from_json,
    gather_answers_interactive,
    run_seed,
)

app = typer.Typer(
    name="irminsul",
    help="A documentation system for complex codebases.",
    no_args_is_help=True,
    add_completion=False,
)


class Profile(StrEnum):
    hard = "hard"
    configured = "configured"
    advisory = "advisory"
    all_available = "all-available"


class ContextProfile(StrEnum):
    configured = "configured"
    all_available = "all-available"


class FreshTopology(StrEnum):
    same_repo = "same-repo"
    docs_only = "docs-only"


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


def _offer_seed_after_fresh_init(target: Path, *, interactive: bool) -> None:
    """After an interactive fresh-start init, offer to capture the PIB now.

    Non-interactive init gains no new prompts — it stays fully scriptable.
    `irminsul seed` remains the standalone command for capturing or redoing
    the seed later.
    """
    if not interactive:
        return
    typer.echo()
    typer.echo(typer.style(PIB_INTRO, fg="cyan"))
    typer.echo()
    if not typer.confirm("Capture your project's principle, idea, and belief now?", default=False):
        typer.echo("Hint: run `irminsul seed` whenever you're ready.")
        return
    config = load(find_config(target))
    answers = gather_answers_interactive(config.project_name, show_intro=False)
    result = run_seed(target, config, answers)
    typer.echo()
    typer.echo(typer.style("Seeded:", fg="green", bold=True))
    for p in result.written:
        typer.echo(f"  {p.as_posix()}")


@app.command()
def init(
    fresh: Annotated[
        bool,
        typer.Option(
            "--fresh",
            help="Initialize a new project with no existing code.",
        ),
    ] = False,
    topology: Annotated[
        FreshTopology,
        typer.Option(
            "--topology",
            help="Fresh-start topology: same-repo or docs-only.",
        ),
    ] = FreshTopology.same_repo,
    code_repo: Annotated[
        str | None,
        typer.Option(
            "--code-repo",
            help=("Future or existing code repository for `--fresh --topology docs-only`."),
        ),
    ] = None,
    allow_existing_code: Annotated[
        bool,
        typer.Option(
            "--allow-existing-code",
            help="Allow --fresh even when code signals already exist.",
        ),
    ] = False,
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
    has_code = detect_code_signals(target)

    if not fresh and topology != FreshTopology.same_repo:
        typer.echo(
            typer.style(
                "`--topology` is only valid with `--fresh`. "
                "Use `irminsul init-docs-only --code-repo <spec-or-path>` "
                "to adopt existing separate code.",
                fg="red",
            )
        )
        raise typer.Exit(code=2)

    if code_repo is not None and topology != FreshTopology.docs_only:
        typer.echo(
            typer.style(
                "`--code-repo` is only valid with `--fresh --topology docs-only`. "
                "Use `irminsul init-docs-only --code-repo <spec-or-path>` "
                "to adopt existing separate code.",
                fg="red",
            )
        )
        raise typer.Exit(code=2)

    if fresh:
        if has_code and not allow_existing_code:
            typer.echo(
                typer.style(
                    "Code signals already exist in the target directory. "
                    "Use `irminsul init` to adopt existing same-repo code, or pass "
                    "`--allow-existing-code` with `--fresh` if this is intentional.",
                    fg="red",
                )
            )
            raise typer.Exit(code=2)
        if topology == FreshTopology.docs_only:
            run_init_fresh_docs_only(
                target, interactive=interactive, code_repo=code_repo, force=force
            )
        else:
            run_init_fresh(target, interactive=interactive, force=force)
        _offer_seed_after_fresh_init(target, interactive=interactive)
        return

    if interactive and not has_code:
        typer.echo("No code detected here. What are you setting up?")
        typer.echo("  [1] Fresh-start, same repo")
        typer.echo("  [2] Fresh-start, private docs / public code")
        typer.echo("  [3] Docs-only repo for existing separate code")
        typer.echo("  [4] Cancel")
        answer = typer.prompt("Choose", default="1")
        if answer == "1":
            run_init_fresh(target, interactive=interactive, force=force)
            _offer_seed_after_fresh_init(target, interactive=interactive)
            return
        if answer == "2":
            run_init_fresh_docs_only(
                target, interactive=interactive, code_repo=code_repo, force=force
            )
            _offer_seed_after_fresh_init(target, interactive=interactive)
            return
        if answer == "3":
            run_init_docs_only(target, interactive=interactive, code_repo=None, force=force)
            return
        typer.echo("Canceled.")
        raise typer.Exit(code=0)
    elif not interactive and not has_code:
        typer.echo(
            typer.style(
                "No code detected in the target directory.\n"
                "Use `irminsul init --fresh` to start a new project, or\n"
                "`irminsul init-docs-only --code-repo <spec-or-path>` "
                "for a docs-only repo.",
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


@app.command()
def seed(
    principle: Annotated[
        str | None,
        typer.Option("--principle", help="What must stay true even if features change."),
    ] = None,
    idea: Annotated[
        str | None,
        typer.Option("--idea", help="What should be built first."),
    ] = None,
    belief: Annotated[
        str | None,
        typer.Option("--belief", help="Why this direction is worth pursuing."),
    ] = None,
    first_user: Annotated[
        str | None,
        typer.Option("--first-user", help="The first audience the app should serve."),
    ] = None,
    non_goals: Annotated[
        str | None,
        typer.Option("--non-goals", help="What the app should not become; separate with ';'."),
    ] = None,
    direction_risks: Annotated[
        str | None,
        typer.Option(
            "--direction-risks",
            help="What would make the product drift; separate with ';'.",
        ),
    ] = None,
    json_file: Annotated[
        Path | None,
        typer.Option("--json", help="JSON file with the full seed statement."),
    ] = None,
    reseed: Annotated[
        bool,
        typer.Option(
            "--reseed", help="Overwrite foundation docs even if edited away from scaffold."
        ),
    ] = False,
    merge: Annotated[
        bool,
        typer.Option(
            "--merge", help="Append this seed pass under a dated heading instead of overwriting."
        ),
    ] = False,
    no_interactive: Annotated[
        bool,
        typer.Option(
            "--no-interactive", help="Use flags or --json instead of prompting. CI-friendly."
        ),
    ] = False,
    path: Annotated[
        Path,
        typer.Option("--path", help="Root of the codebase. Defaults to current directory."),
    ] = Path("."),
) -> None:
    """Capture the project's principle, idea, and belief into the foundation layer."""
    repo_root = path.resolve()
    config = load(find_config(repo_root))

    if json_file is not None:
        answers = gather_answers_from_json(json_file, project_name=config.project_name)
    elif no_interactive:
        answers = gather_answers_from_flags(
            project_name=config.project_name,
            principle=principle,
            idea=idea,
            belief=belief,
            first_user=first_user,
            non_goals=non_goals,
            direction_risks=direction_risks,
        )
    else:
        answers = gather_answers_interactive(config.project_name)

    result = run_seed(repo_root, config, answers, reseed=reseed, merge=merge)
    typer.echo()
    typer.echo(typer.style("Seeded:", fg="green", bold=True))
    for p in result.written:
        typer.echo(f"  {p.as_posix()}")


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


def _findings_to_json(findings: list[Finding], counts: dict[Severity, int]) -> str:
    import json

    return json.dumps(
        {
            "version": 1,
            "findings": [
                {
                    "check": f.check,
                    "severity": f.severity.value,
                    "message": f.message,
                    "path": f.path.as_posix() if f.path else None,
                    "doc_id": f.doc_id,
                    "line": f.line,
                    "suggestion": f.suggestion,
                    "category": f.category,
                }
                for f in findings
            ],
            "summary": {
                "errors": counts[Severity.error],
                "warnings": counts[Severity.warning],
                "info": counts[Severity.info],
            },
        },
        indent=2,
    )


def _print_summary(counts: dict[Severity, int]) -> None:
    parts: list[str] = [
        f"{counts[Severity.error]} error{'s' if counts[Severity.error] != 1 else ''}",
        f"{counts[Severity.warning]} warning{'s' if counts[Severity.warning] != 1 else ''}",
    ]
    if counts[Severity.info]:
        parts.append(f"{counts[Severity.info]} info")
    typer.echo(", ".join(parts))


def _hard_check_names(profile: Profile, config: IrminsulConfig) -> list[str]:
    if profile == Profile.all_available:
        return list(HARD_REGISTRY)
    return list(config.checks.hard)


def _soft_check_names(profile: Profile, config: IrminsulConfig) -> list[str]:
    if profile == Profile.hard:
        return []
    if profile == Profile.all_available:
        return list(SOFT_REGISTRY)
    return list(config.checks.soft_deterministic)


def _llm_check_names(profile: Profile, config: IrminsulConfig) -> list[str]:
    if profile != Profile.advisory:
        return []
    return list(config.checks.soft_llm)


def _run_registered_checks(
    check_names: list[str],
    registry: dict[str, type[Check]],
    graph: DocGraph,
    *,
    tier: str,
) -> list[Finding]:
    findings: list[Finding] = []
    for check_name in check_names:
        cls = registry.get(check_name)
        if cls is None:
            typer.echo(
                typer.style(
                    f"note: {tier} check '{check_name}' not yet implemented; skipping.",
                    fg="yellow",
                )
            )
            continue
        findings.extend(cls().run(graph))
    return findings


def _run_llm_checks(
    check_names: list[str],
    *,
    repo_root: Path,
    config: IrminsulConfig,
    graph: DocGraph,
    llm_budget: float | None,
    fmt: str,
) -> list[Finding]:
    if not check_names:
        return []

    from irminsul.llm.client import LlmClient

    findings: list[Finding] = []
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
            for check_name in check_names:
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
        return findings

    calls_before = len(llm_client._cache)
    for check_name in check_names:
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
    cache_size = len(llm_client._cache)
    api_calls = max(0, cache_size - calls_before)
    if fmt == "plain":
        typer.echo(
            typer.style(
                f"LLM: ${spent:.4f} / ${budget:.2f} budget used"
                + (f"; {api_calls} API call(s)" if api_calls else ""),
                dim=True,
            )
        )
    return findings


@app.command()
def check(
    profile: Annotated[
        Profile,
        typer.Option("--profile", help="Check profile to run."),
    ] = Profile.hard,
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
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format: plain or json."),
    ] = "plain",
    path: Annotated[
        Path,
        typer.Option(
            "--path",
            help="Root of the codebase to check. Defaults to current directory.",
        ),
    ] = Path("."),
    now: Annotated[
        str | None,
        typer.Option(
            "--now",
            help=(
                "Override today's date (YYYY-MM-DD) for date-sensitive checks. "
                "Intended for deterministic test fixtures and CI runs."
            ),
        ),
    ] = None,
) -> None:
    """Run the configured checks. Errors exit non-zero."""
    if fmt not in ("plain", "json"):
        typer.echo(typer.style(f"unknown --format '{fmt}'; expected plain or json", fg="red"))
        raise typer.Exit(code=2)

    now_date: _dt.date | None = None
    if now is not None:
        try:
            now_date = _dt.date.fromisoformat(now)
        except ValueError:
            typer.echo(
                typer.style(f"unknown --now '{now}'; expected YYYY-MM-DD", fg="red"),
            )
            raise typer.Exit(code=2) from None

    repo_root = path.resolve()
    config_path = find_config(repo_root)
    config = load(config_path)
    graph = build_graph(repo_root, config, now=now_date)

    findings: list[Finding] = []
    findings.extend(
        _run_registered_checks(
            _hard_check_names(profile, config), HARD_REGISTRY, graph, tier="hard"
        )
    )
    findings.extend(
        _run_registered_checks(
            _soft_check_names(profile, config), SOFT_REGISTRY, graph, tier="soft"
        )
    )
    findings.extend(
        _run_llm_checks(
            _llm_check_names(profile, config),
            repo_root=repo_root,
            config=config,
            graph=graph,
            llm_budget=llm_budget,
            fmt=fmt,
        )
    )

    findings = sort_findings(findings)
    counts = summarize(findings)
    fail = counts[Severity.error] > 0 or (strict and counts[Severity.warning] > 0)

    if fmt == "json":
        typer.echo(_findings_to_json(findings, counts))
    else:
        for finding in findings:
            _print_finding(finding)
        _print_summary(counts)

    raise typer.Exit(code=1 if fail else 0)


@app.command("context")
def context_command(
    target: Annotated[
        Path | None,
        typer.Argument(help="Source or doc path to inspect."),
    ] = None,
    topic: Annotated[
        str | None,
        typer.Option("--topic", help="Find docs by deterministic substring search."),
    ] = None,
    changed: Annotated[
        bool,
        typer.Option("--changed", help="Inspect staged, unstaged, and untracked git files."),
    ] = False,
    profile: Annotated[
        ContextProfile,
        typer.Option(
            "--profile",
            help="Deterministic finding breadth: configured or all-available.",
        ),
    ] = ContextProfile.configured,
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format: plain or json."),
    ] = "plain",
    path: Annotated[
        Path,
        typer.Option(
            "--path",
            help="Root of the codebase to inspect. Defaults to current directory.",
        ),
    ] = Path("."),
) -> None:
    """Return task-specific navigation context."""
    from irminsul.context import (
        ContextError,
        build_context_report,
        context_report_should_fail,
        context_report_to_json,
        format_context_plain,
    )

    if fmt not in ("plain", "json"):
        typer.echo(typer.style(f"unknown --format '{fmt}'; expected plain or json", fg="red"))
        raise typer.Exit(code=2)

    repo_root = path.resolve()
    config = load(find_config(repo_root))
    try:
        report = build_context_report(
            repo_root,
            config,
            target_path=target,
            topic=topic,
            changed=changed,
            profile=profile.value,
        )
    except ContextError as exc:
        typer.echo(typer.style(str(exc), fg="red"))
        raise typer.Exit(code=exc.code) from exc

    if fmt == "json":
        typer.echo(context_report_to_json(report))
    else:
        typer.echo(format_context_plain(report))

    raise typer.Exit(code=1 if context_report_should_fail(report) else 0)


@app.command("refs")
def refs_command(
    target: Annotated[
        str | None,
        typer.Argument(help="Doc id or repo-relative doc path to inspect."),
    ] = None,
    symbol: Annotated[
        str | None,
        typer.Option("--symbol", help="Find docs that own or reference a symbol."),
    ] = None,
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format: plain or json."),
    ] = "plain",
    path: Annotated[
        Path,
        typer.Option(
            "--path",
            help="Root of the codebase to inspect. Defaults to current directory.",
        ),
    ] = Path("."),
) -> None:
    """Return doc backlinks or symbol references."""
    from irminsul.refs import (
        RefsError,
        build_doc_refs_report,
        build_symbol_refs_report,
        doc_refs_report_to_json,
        format_doc_refs_plain,
        format_symbol_refs_plain,
        symbol_refs_report_to_json,
    )

    if fmt not in ("plain", "json"):
        typer.echo(typer.style(f"unknown --format '{fmt}'; expected plain or json", fg="red"))
        raise typer.Exit(code=2)
    if (target is None) == (symbol is None):
        typer.echo(
            typer.style("choose exactly one input: <doc-id|path> or --symbol <name>", fg="red")
        )
        raise typer.Exit(code=2)

    repo_root = path.resolve()
    config = load(find_config(repo_root))
    graph = build_graph(repo_root, config)

    try:
        if symbol is not None:
            symbol_report = build_symbol_refs_report(graph, symbol, repo_root)
            typer.echo(
                symbol_refs_report_to_json(symbol_report)
                if fmt == "json"
                else format_symbol_refs_plain(symbol_report)
            )
        elif target is not None:
            doc_report = build_doc_refs_report(repo_root, graph, target)
            typer.echo(
                doc_refs_report_to_json(doc_report)
                if fmt == "json"
                else format_doc_refs_plain(doc_report)
            )
    except RefsError as exc:
        typer.echo(typer.style(str(exc), fg="red"))
        raise typer.Exit(code=exc.code) from exc


@app.command()
def fix(
    profile: Annotated[
        Profile,
        typer.Option("--profile", help="Fix profile to run."),
    ] = Profile.configured,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print planned fixes without writing files."),
    ] = False,
    path: Annotated[
        Path,
        typer.Option(
            "--path",
            help="Root of the codebase to fix. Defaults to current directory.",
        ),
    ] = Path("."),
) -> None:
    """Apply deterministic remediations for fixable findings."""
    from irminsul.fix import apply_fixes

    repo_root = path.resolve()
    config_path = find_config(repo_root)
    config = load(config_path)
    graph = build_graph(repo_root, config)

    fixes: list[Fix] = []

    selected: list[tuple[str, dict[str, type[Check]]]] = [
        *[(name, HARD_REGISTRY) for name in _hard_check_names(profile, config)],
        *[(name, SOFT_REGISTRY) for name in _soft_check_names(profile, config)],
    ]
    for check_name, registry in selected:
        cls = registry.get(check_name)
        if cls is None:
            continue
        check = cls()
        check_findings = check.run(graph)
        maybe_fixes = getattr(check, "fixes", None)
        if maybe_fixes is not None:
            fixes.extend(maybe_fixes(check_findings, graph))

    if not fixes:
        typer.echo("no automatic fixes available")
        raise typer.Exit(code=0)

    result = apply_fixes(repo_root, fixes, dry_run=dry_run)
    for planned in result.planned:
        typer.echo(f"  {planned.path.as_posix()}: {planned.description}")

    if result.errors:
        for error in result.errors:
            typer.echo(typer.style(error, fg="red"))
        raise typer.Exit(code=1)

    if dry_run:
        typer.echo(typer.style(f"planned {len(result.planned)} fix(es)", fg="green"))
    else:
        typer.echo(typer.style(f"updated {len(result.written)} file(s)", fg="green"))

    raise typer.Exit(code=0)


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
    force: Annotated[bool, typer.Option("--force")] = False,
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """Scaffold a new Architecture Decision Record."""
    from irminsul.new.command import NewSpec, write_new

    repo_root = path.resolve()
    config = load(find_config(repo_root))
    spec = NewSpec(kind="adr", title=title, extra={})
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
    force: Annotated[bool, typer.Option("--force")] = False,
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """Scaffold a new component doc."""
    from irminsul.new.command import NewSpec, write_new

    repo_root = path.resolve()
    config = load(find_config(repo_root))
    spec = NewSpec(kind="component", title=title, extra={})
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
    force: Annotated[bool, typer.Option("--force")] = False,
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """Scaffold a new RFC."""
    from irminsul.new.command import NewSpec, write_new

    repo_root = path.resolve()
    config = load(find_config(repo_root))
    spec = NewSpec(kind="rfc", title=title, extra={})
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


_regen_app = typer.Typer(
    name="regen",
    help="Regenerate generated documentation artifacts.",
    no_args_is_help=True,
)
app.add_typer(_regen_app)


def _load_repo(path: Path) -> tuple[Path, IrminsulConfig]:
    repo_root = path.resolve()
    config = load(find_config(repo_root))
    return repo_root, config


def _print_regen_result(repo_root: Path, written: list[Path]) -> None:
    for p in written:
        rel = p.relative_to(repo_root).as_posix()
        typer.echo(f"  {rel}")
    typer.echo(typer.style(f"regenerated {len(written)} artifact(s)", fg="green"))


def _regen_typescript_or_exit(repo_root: Path, config: IrminsulConfig) -> list[Path]:
    from irminsul.regen.typescript import TypeScriptRegenError, regen_typescript

    try:
        return regen_typescript(repo_root, config)
    except TypeScriptRegenError as exc:
        typer.echo(typer.style(str(exc), fg="red"))
        raise typer.Exit(code=1) from exc


@_regen_app.command("python")
def regen_python_command(
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """Regenerate Python reference stubs."""
    from irminsul.regen.python import regen_python

    repo_root, config = _load_repo(path)
    _print_regen_result(repo_root, regen_python(repo_root, config))


@_regen_app.command("typescript")
def regen_typescript_command(
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """Regenerate TypeScript reference stubs."""
    repo_root, config = _load_repo(path)
    _print_regen_result(repo_root, _regen_typescript_or_exit(repo_root, config))


@_regen_app.command("docs-surfaces")
def regen_docs_surfaces_command(
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """Regenerate code-derived documentation surface references."""
    from irminsul.regen.doc_surfaces import regen_doc_surfaces

    repo_root, config = _load_repo(path)
    _print_regen_result(repo_root, regen_doc_surfaces(repo_root, config))


@_regen_app.command("agents-md")
def regen_agents_md_command(
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """Regenerate the docs/AGENTS.md agent navigation manifest."""
    from irminsul.regen.agents_md import regen_agents_md

    repo_root, config = _load_repo(path)
    _print_regen_result(repo_root, regen_agents_md(repo_root, config))


@_regen_app.command("all")
def regen_all_command(
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """Regenerate every configured generated documentation artifact."""
    from irminsul.regen.agents_md import regen_agents_md
    from irminsul.regen.doc_surfaces import regen_doc_surfaces
    from irminsul.regen.python import regen_python

    repo_root, config = _load_repo(path)
    written: list[Path] = []
    written.extend(regen_doc_surfaces(repo_root, config))
    written.extend(regen_python(repo_root, config))
    written.extend(_regen_typescript_or_exit(repo_root, config))
    written.extend(regen_agents_md(repo_root, config))
    _print_regen_result(repo_root, written)


if __name__ == "__main__":  # pragma: no cover
    app()
