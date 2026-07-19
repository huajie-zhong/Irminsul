"""Irminsul command-line entry point."""

from __future__ import annotations

import datetime as _dt
import glob
import sys
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from irminsul import __version__
from irminsul.checks import (
    HARD_REGISTRY,
    SOFT_REGISTRY,
    Check,
    Finding,
    Fix,
    Severity,
    finding_records,
    fix_commands,
    sort_findings,
    summarize,
)
from irminsul.config import IrminsulConfig, find_config, load
from irminsul.docgraph import DocGraph, build_graph
from irminsul.git.mtime import diff_name_only, has_history
from irminsul.init.command import (
    detect_code_signals,
    run_init,
    run_init_docs_only,
    run_init_fresh,
    run_init_fresh_docs_only,
)
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


def _configure_console_encoding(
    streams: tuple[object, ...] | None = None,
    *,
    platform: str | None = None,
) -> None:
    current_platform = sys.platform if platform is None else platform
    if current_platform != "win32":
        return
    targets = (sys.stdout, sys.stderr) if streams is None else streams
    for stream in targets:
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def main() -> None:
    _configure_console_encoding()
    app()


class Profile(StrEnum):
    hard = "hard"
    configured = "configured"
    all_available = "all-available"


class ContextProfile(StrEnum):
    hard = "hard"
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


def _findings_to_json(
    findings: list[Finding],
    counts: dict[Severity, int],
    commands: list[str | None],
    baseline: dict[str, object] | None = None,
    delta: dict[str, object] | None = None,
) -> str:
    import json

    payload: dict[str, object] = {
        "version": 1,
        "findings": finding_records(findings, commands),
        "summary": {
            "errors": counts[Severity.error],
            "warnings": counts[Severity.warning],
            "info": counts[Severity.info],
        },
    }
    if baseline is not None:
        payload["baseline"] = baseline
    if delta is not None:
        payload["delta"] = delta
    return json.dumps(payload, indent=2)


_GITHUB_COMMAND = {
    Severity.error: "error",
    Severity.warning: "warning",
    Severity.info: "notice",
}


def _escape_github_data(value: str) -> str:
    """Escape workflow-command message data per the GitHub Actions spec."""
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_github_property(value: str) -> str:
    """Escape workflow-command property values (data escapes plus ',' and ':')."""
    return _escape_github_data(value).replace(",", "%2C").replace(":", "%3A")


def _github_annotation(finding: Finding) -> str:
    """One `::error|::warning|::notice` workflow command per finding."""
    props: list[str] = []
    if finding.path is not None:
        props.append(f"file={_escape_github_property(finding.path.as_posix())}")
    if finding.line is not None:
        props.append(f"line={finding.line}")
    props.append("title=" + _escape_github_property(f"irminsul {finding.check}"))
    data = finding.message
    if finding.suggestion:
        data = f"{data} — {finding.suggestion}"
    return f"::{_GITHUB_COMMAND[finding.severity]} {','.join(props)}::{_escape_github_data(data)}"


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


def _diff_failure_reason(repo_root: Path, co_change_range: tuple[str, str]) -> str:
    base, head = co_change_range
    if not has_history(repo_root):
        return (
            f"no git repository with commit history found at {repo_root}; "
            "co-change needs one to diff against"
        )
    return (
        f"could not compute `git diff {base}...{head}`; "
        "at least one ref could not be resolved in this repository"
    )


def _run_registered_checks(
    check_names: list[str],
    registry: dict[str, type[Check]],
    graph: DocGraph,
    *,
    tier: str,
    announce: bool = True,
) -> list[Finding]:
    findings: list[Finding] = []
    for check_name in check_names:
        cls = registry.get(check_name)
        if cls is None:
            if announce:
                typer.echo(
                    typer.style(
                        f"note: {tier} check '{check_name}' not yet implemented; skipping.",
                        fg="yellow",
                    )
                )
            continue
        findings.extend(cls().run(graph))
    return findings


def _run_configured_checks(
    profile: Profile,
    config: IrminsulConfig,
    graph: DocGraph,
    *,
    announce: bool = True,
) -> list[Finding]:
    """Hard + soft findings for one profile/graph pair — the unit `--delta`
    runs twice (once for the working tree, once for the base-rev checkout)."""
    findings: list[Finding] = []
    findings.extend(
        _run_registered_checks(
            _hard_check_names(profile, config), HARD_REGISTRY, graph, tier="hard", announce=announce
        )
    )
    findings.extend(
        _run_registered_checks(
            _soft_check_names(profile, config), SOFT_REGISTRY, graph, tier="soft", announce=announce
        )
    )
    return findings


@app.command()
def check(
    profile: Annotated[
        Profile,
        typer.Option("--profile", help="Check profile to run."),
    ] = Profile.hard,
    strict: Annotated[
        bool,
        typer.Option(
            "--strict",
            help="Promote warnings to errors for the exit code. Hard checks always block.",
        ),
    ] = False,
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format: plain, json, or github."),
    ] = "plain",
    diff: Annotated[
        str | None,
        typer.Option(
            "--diff",
            help=(
                "Base git ref for co-change enforcement: warn when source files "
                "changed in <base>...HEAD without their owning docs."
            ),
        ),
    ] = None,
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
    base_ref: Annotated[
        str | None,
        typer.Option(
            "--base-ref",
            help="Base git ref for diff-aware checks. Use together with --head-ref.",
        ),
    ] = None,
    head_ref: Annotated[
        str | None,
        typer.Option(
            "--head-ref",
            help="Head git ref for diff-aware checks. Use together with --base-ref.",
        ),
    ] = None,
    update_baseline: Annotated[
        bool,
        typer.Option(
            "--update-baseline",
            help=(
                "Write the current error/warning findings to the baseline file "
                "and exit 0. Subsequent runs suppress exactly these findings."
            ),
        ),
    ] = False,
    no_baseline: Annotated[
        bool,
        typer.Option("--no-baseline", help="Ignore an existing baseline file for this run."),
    ] = False,
    delta: Annotated[
        bool,
        typer.Option(
            "--delta",
            help=(
                "Report only findings introduced relative to a base rev "
                "(default HEAD; see --delta-base)."
            ),
        ),
    ] = False,
    delta_base: Annotated[
        str | None,
        typer.Option(
            "--delta-base",
            help="Base git rev for --delta. Passing this implies --delta. Defaults to HEAD.",
        ),
    ] = None,
) -> None:
    """Run the configured checks. Errors exit non-zero."""
    if fmt not in ("plain", "json", "github"):
        typer.echo(
            typer.style(f"unknown --format '{fmt}'; expected plain, json, or github", fg="red")
        )
        raise typer.Exit(code=2)

    if (base_ref is None) != (head_ref is None):
        typer.echo(typer.style("--base-ref and --head-ref must be provided together", fg="red"))
        raise typer.Exit(code=2)

    if update_baseline and no_baseline:
        typer.echo(
            typer.style("--update-baseline and --no-baseline are mutually exclusive", fg="red")
        )
        raise typer.Exit(code=2)

    if delta_base is not None:
        delta = True

    if delta and update_baseline:
        typer.echo(typer.style("--delta and --update-baseline are mutually exclusive", fg="red"))
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

    if diff is not None and base_ref is not None:
        typer.echo(typer.style("--diff and --base-ref/--head-ref are mutually exclusive", fg="red"))
        raise typer.Exit(code=2)

    for flag, value in (("--diff", diff), ("--base-ref", base_ref), ("--head-ref", head_ref)):
        if value is not None and not value.strip():
            typer.echo(
                typer.style(
                    f"{flag} was given an empty value; pass a git ref or omit the flag",
                    fg="red",
                )
            )
            raise typer.Exit(code=2)

    co_change_paths: frozenset[str] | None = None
    co_change_range: tuple[str, str] | None = None
    if diff is not None:
        co_change_range = (diff, "HEAD")
    elif base_ref is not None and head_ref is not None:
        co_change_range = (base_ref, head_ref)
    if co_change_range is not None:
        co_change_paths = diff_name_only(repo_root, *co_change_range)
        if co_change_paths is None:
            reason = _diff_failure_reason(repo_root, co_change_range)
            # --diff is an explicit opt-in gate: failing to compute its diff means
            # the gate would silently pass, so exit. --base-ref/--head-ref predate
            # it and degrade gracefully so a shallow clone still reports findings.
            if diff is not None:
                typer.echo(typer.style(reason, fg="red"))
                raise typer.Exit(code=2)
            typer.echo(
                typer.style(f"{reason}; skipping diff-aware checks", fg="yellow"),
                err=True,
            )

    graph = build_graph(repo_root, config, now=now_date, diff_changed_paths=co_change_paths)

    findings = _run_configured_checks(profile, config, graph)

    if co_change_paths is not None:
        from irminsul.checks.co_change import run_co_change

        findings.extend(run_co_change(graph, co_change_paths))

    findings = sort_findings(findings)

    baseline_status: dict[str, object] = {
        "applied": False,
        "path": None,
        "suppressed": 0,
        "stale": 0,
    }
    delta_status: dict[str, object] | None = None

    if delta:
        from irminsul.delta import DeltaError, compute_delta, pristine_checkout

        delta_base_rev = delta_base or "HEAD"
        try:
            with pristine_checkout(repo_root, delta_base_rev) as base_root:
                base_graph = build_graph(
                    base_root, config, now=now_date, diff_changed_paths=co_change_paths
                )
                base_findings = _run_configured_checks(profile, config, base_graph, announce=False)
        except DeltaError as e:
            typer.echo(typer.style(str(e), fg="red"))
            raise typer.Exit(code=2) from None

        delta_result = compute_delta(findings, base_findings)
        findings = delta_result.new
        delta_status = {
            "applied": True,
            "base": delta_base_rev,
            "new": len(delta_result.new),
            "pre_existing_suppressed": delta_result.pre_existing,
        }
    else:
        from irminsul.baseline import (
            BaselineError,
            apply_baseline,
            load_baseline,
            write_baseline,
        )

        baseline_file = repo_root / config.paths.baseline
        if update_baseline:
            count = write_baseline(baseline_file, findings)
            typer.echo(
                typer.style(
                    f"baseline: wrote {count} finding(s) to {config.paths.baseline}", fg="green"
                )
            )
            raise typer.Exit(code=0)

        if not no_baseline and baseline_file.is_file():
            try:
                fingerprints = load_baseline(baseline_file)
            except BaselineError as e:
                typer.echo(typer.style(str(e), fg="red"))
                raise typer.Exit(code=2) from None
            application = apply_baseline(findings, fingerprints)
            findings = application.remaining
            baseline_status = {
                "applied": True,
                "path": config.paths.baseline,
                "suppressed": application.suppressed,
                "stale": application.stale,
            }

    counts = summarize(findings)
    fail = counts[Severity.error] > 0 or (strict and counts[Severity.warning] > 0)

    if fmt == "json":
        typer.echo(
            _findings_to_json(
                findings,
                counts,
                fix_commands(findings, graph, profile=profile.value),
                baseline=baseline_status,
                delta=delta_status,
            )
        )
    elif fmt == "github":
        for finding in findings:
            typer.echo(_github_annotation(finding))
        _print_summary(counts)
    else:
        for finding in findings:
            _print_finding(finding)
        if delta_status is not None:
            typer.echo(
                typer.style(
                    f"{delta_status['new']} new finding(s) vs {delta_status['base']} "
                    f"({delta_status['pre_existing_suppressed']} pre-existing suppressed)",
                    fg="cyan",
                )
            )
        elif baseline_status["applied"]:
            stale = baseline_status["stale"]
            stale_note = (
                f" ({stale} stale entr{'y' if stale == 1 else 'ies'};"
                " run --update-baseline to ratchet down)"
                if isinstance(stale, int) and stale > 0
                else ""
            )
            typer.echo(
                typer.style(
                    f"baseline: {baseline_status['suppressed']} finding(s) suppressed{stale_note}",
                    fg="cyan",
                )
            )
        _print_summary(counts)

    raise typer.Exit(code=1 if fail else 0)


@app.command("status")
def status_command(
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
    """Show a one-glance digest of the doc system's health."""
    from irminsul.status import (
        build_status_report,
        format_status_plain,
        status_report_to_json,
    )

    if fmt not in ("plain", "json"):
        typer.echo(typer.style(f"unknown --format '{fmt}'; expected plain or json", fg="red"))
        raise typer.Exit(code=2)

    repo_root = path.resolve()
    config = load(find_config(repo_root))
    report = build_status_report(repo_root, config)
    typer.echo(status_report_to_json(report) if fmt == "json" else format_status_plain(report))


@app.command("context")
def context_command(
    targets: Annotated[
        list[Path] | None,
        typer.Argument(help="Source or doc paths to inspect."),
    ] = None,
    before_edit: Annotated[
        bool,
        typer.Option(
            "--before-edit",
            help="Package context for one or more paths before editing.",
        ),
    ] = False,
    after_edit: Annotated[
        bool,
        typer.Option(
            "--after-edit",
            help="Inspect changed paths and validate the repository after editing.",
        ),
    ] = False,
    topic: Annotated[
        str | None,
        typer.Option(
            "--topic",
            help=(
                "Find docs by quoted topic keywords; every whitespace-separated term must match."
            ),
        ),
    ] = None,
    changed: Annotated[
        bool,
        typer.Option("--changed", help="Inspect staged, unstaged, and untracked git files."),
    ] = False,
    change: Annotated[
        str | None,
        typer.Option(
            "--change",
            help="Present the change-aware evidence report for one RFC (alias of `change status`).",
        ),
    ] = None,
    profile: Annotated[
        ContextProfile | None,
        typer.Option(
            "--profile",
            help="Finding breadth: hard, configured, or all-available.",
        ),
    ] = None,
    include: Annotated[
        str | None,
        typer.Option(
            "--include",
            help="Content categories: owner, claims, requirements, dependencies, all, or none.",
        ),
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
    """Return task-specific navigation context."""
    from irminsul.context import (
        ContextError,
        WorkflowStage,
        build_context_report,
        context_report_should_fail,
        context_report_to_json,
        format_context_plain,
        parse_content_categories,
    )
    from irminsul.context import (
        ContextProfile as ContextProfileValue,
    )

    if fmt not in ("plain", "json"):
        typer.echo(typer.style(f"unknown --format '{fmt}'; expected plain or json", fg="red"))
        raise typer.Exit(code=2)

    repo_root = path.resolve()
    config = load(find_config(repo_root))
    requested_targets = list(targets or [])

    if change is not None:
        if (
            requested_targets
            or topic is not None
            or changed
            or before_edit
            or after_edit
            or include is not None
        ):
            typer.echo(typer.style("--change cannot be combined with other input modes", fg="red"))
            raise typer.Exit(code=2)
        from irminsul.change.report import (
            ChangeError,
            build_change_report,
            change_report_to_json,
            format_change_status_plain,
        )

        try:
            change_report = build_change_report(repo_root, config, change)
        except ChangeError as exc:
            typer.echo(typer.style(str(exc), fg="red"))
            raise typer.Exit(code=exc.code) from exc
        typer.echo(
            change_report_to_json(change_report)
            if fmt == "json"
            else format_change_status_plain(change_report)
        )
        return

    if before_edit and after_edit:
        typer.echo(typer.style("--before-edit and --after-edit cannot be combined", fg="red"))
        raise typer.Exit(code=2)

    workflow: WorkflowStage | None = None
    target_path = None
    target_paths = None
    effective_changed = changed
    if before_edit:
        if topic is not None or changed:
            typer.echo(
                typer.style("--before-edit cannot be combined with --topic or --changed", fg="red")
            )
            raise typer.Exit(code=2)
        if not requested_targets:
            typer.echo(typer.style("--before-edit requires one or more paths", fg="red"))
            raise typer.Exit(code=2)
        workflow = "before-edit"
        target_paths = requested_targets
    elif after_edit:
        if requested_targets or topic is not None or changed:
            typer.echo(
                typer.style(
                    "--after-edit cannot be combined with paths, --topic, or --changed",
                    fg="red",
                )
            )
            raise typer.Exit(code=2)
        workflow = "after-edit"
        effective_changed = True
    else:
        if len(requested_targets) > 1:
            typer.echo(typer.style("multiple paths require the --before-edit workflow", fg="red"))
            raise typer.Exit(code=2)
        target_path = requested_targets[0] if requested_targets else None

    effective_profile: ContextProfileValue = (
        profile.value
        if profile is not None
        else (
            ContextProfile.hard.value if workflow is not None else ContextProfile.configured.value
        )
    )

    try:
        content_categories = parse_content_categories(include) if include is not None else None
        report = build_context_report(
            repo_root,
            config,
            target_path=target_path,
            target_paths=target_paths,
            topic=topic,
            changed=effective_changed,
            profile=effective_profile,
            workflow=workflow,
            content_categories=content_categories,
        )
    except ContextError as exc:
        typer.echo(typer.style(str(exc), fg="red"))
        raise typer.Exit(code=exc.code) from exc

    if fmt == "json":
        typer.echo(context_report_to_json(report))
    else:
        typer.echo(format_context_plain(report))

    raise typer.Exit(code=1 if context_report_should_fail(report) else 0)


@app.command("orient")
def orient_command(
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
    """Orient an agent in this repo: structure, doc totals, entry docs, and commands.

    The recommended first call for agents. Builds the doc graph once and runs
    no checks, so it is fast; every field is also available as stable JSON via
    `--format json`.
    """
    from irminsul.orient import build_orient_report, format_orient_plain, orient_report_to_json

    if fmt not in ("plain", "json"):
        typer.echo(typer.style(f"unknown --format '{fmt}'; expected plain or json", fg="red"))
        raise typer.Exit(code=2)

    repo_root, config = _load_repo(path)
    report = build_orient_report(repo_root, config)
    typer.echo(orient_report_to_json(report) if fmt == "json" else format_orient_plain(report))


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
    confirm: Annotated[
        bool,
        typer.Option(
            "--confirm",
            help="Apply irreversible fixes (metadata/prose rewrites) that are otherwise held.",
        ),
    ] = False,
    check_name: Annotated[
        str | None,
        typer.Option("--check", help="Harvest fixes from a single check by name."),
    ] = None,
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
    if check_name is not None:
        selected = [(name, registry) for name, registry in selected if name == check_name]
        if not selected:
            typer.echo(f"check '{check_name}' is not active under profile '{profile.value}'")
            raise typer.Exit(code=0)
    for name, registry in selected:
        cls = registry.get(name)
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

    result = apply_fixes(repo_root, fixes, dry_run=dry_run, confirm=confirm)
    for planned in result.planned:
        typer.echo(f"  {planned.path.as_posix()}: {planned.description}")
    for held in result.held:
        typer.echo(typer.style(f"  held: {held.path.as_posix()}: {held.description}", fg="yellow"))

    if result.errors:
        for error in result.errors:
            typer.echo(typer.style(error, fg="red"))
        raise typer.Exit(code=1)

    if dry_run:
        typer.echo(typer.style(f"planned {len(result.planned)} fix(es)", fg="green"))
    else:
        typer.echo(typer.style(f"updated {len(result.written)} file(s)", fg="green"))
    if result.held:
        typer.echo(
            typer.style(
                f"held {len(result.held)} fix(es); re-run with --confirm to apply",
                fg="yellow",
            )
        )

    raise typer.Exit(code=0)


@app.command("surface")
def surface_command(
    kind: Annotated[
        str,
        typer.Argument(
            help="Surface kind: cli, http, exports, env-vars, mcp (or a configured generic kind)."
        ),
    ],
    source: Annotated[
        str | None,
        typer.Option("--source", help="Glob limiting which source files to scan."),
    ] = None,
    fmt: Annotated[str, typer.Option("--format", help="Output format: plain or json.")] = "plain",
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """Derive a code surface on demand — commands, endpoints, exports, or env vars.

    Nothing is written: the surface is recomputed from source each call, so it is
    fresh by construction and cannot drift.
    """
    from irminsul.surface import run_surface

    repo_root, config = _load_repo(path)
    run_surface(repo_root, config, kind, source, fmt)


@app.command("mcp")
def mcp_command(
    path: Annotated[
        Path,
        typer.Option(
            "--path",
            help="Root of the codebase to serve. Defaults to current directory.",
        ),
    ] = Path("."),
) -> None:
    """Serve the doc graph to AI agents over the Model Context Protocol (stdio).

    Read-only: every tool returns the same JSON the CLI prints with
    `--format json`. Requires the optional `mcp` extra.
    """
    import importlib.util

    if importlib.util.find_spec("mcp") is None:
        typer.echo(
            typer.style(
                "The MCP server needs the optional 'mcp' dependency. "
                "Install it with: pip install 'irminsul[mcp]'",
                fg="red",
            ),
            err=True,
        )
        raise typer.Exit(code=1)

    from irminsul.mcp_server import create_server

    repo_root, _ = _load_repo(path)
    create_server(repo_root).run()


@app.command("anchors")
def anchors_command(
    re_pin: Annotated[
        bool,
        typer.Option(
            "--re-pin",
            help="Rewrite anchor hashes to the current code (acknowledge after re-reading).",
        ),
    ] = False,
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format for the report: plain or json."),
    ] = "plain",
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """Report or re-pin anchored prose claims.

    Re-pinning is a deliberate acknowledgement that you re-read the prose and it is
    still true; it is never done automatically by `irminsul fix`.
    """
    from irminsul.anchors import repin_text
    from irminsul.checks.claim_anchor import ClaimAnchorCheck

    if fmt not in ("plain", "json"):
        typer.echo(typer.style(f"unknown --format '{fmt}'; expected plain or json", fg="red"))
        raise typer.Exit(code=2)

    repo_root, config = _load_repo(path)
    graph = build_graph(repo_root, config)

    if re_pin:
        from irminsul.checks.globs import walk_configured_source_files
        from irminsul.inventory.fingerprint import repin_node

        source_files = walk_configured_source_files(repo_root, config).files
        anchors_written = 0
        surfaces_written = 0
        for node in graph.nodes.values():
            abs_path = repo_root / node.path
            try:
                text = abs_path.read_text(encoding="utf-8")
            except OSError:
                continue
            text, anchor_changed = repin_text(repo_root, text)
            text, surface_changed = repin_node(
                repo_root, config, source_files, node.frontmatter, text
            )
            if anchor_changed or surface_changed:
                abs_path.write_text(text, encoding="utf-8")
            anchors_written += anchor_changed
            surfaces_written += surface_changed
        typer.echo(
            typer.style(
                f"re-pinned {anchors_written} anchor(s), {surfaces_written} surface fingerprint(s)",
                fg="green",
            )
        )
        raise typer.Exit(code=0)

    findings = sort_findings(ClaimAnchorCheck().run(graph))
    if fmt == "json":
        commands = fix_commands(findings, graph, profile=Profile.all_available.value)
        typer.echo(_findings_to_json(findings, summarize(findings), commands))
        return
    for finding in findings:
        _print_finding(finding)
    typer.echo(f"{len(findings)} anchor finding(s)")


_change_app = typer.Typer(
    name="change",
    help="Bound-change lifecycle for RFCs: status, verification, and transitions.",
    no_args_is_help=True,
)
app.add_typer(_change_app)


class TransitionTarget(StrEnum):
    accepted = "accepted"
    rejected = "rejected"


class MigrationTarget(StrEnum):
    draft = "draft"
    accepted = "accepted"
    implemented = "implemented"
    rejected = "rejected"


@_change_app.command("migrate")
def change_migrate(
    change_id: Annotated[
        str | None,
        typer.Argument(help="Optional pre-lifecycle RFC id, number, or path."),
    ] = None,
    state: Annotated[
        MigrationTarget | None,
        typer.Option("--state", help="Explicit human-selected lifecycle state."),
    ] = None,
    resolved_by: Annotated[
        str | None,
        typer.Option("--resolved-by", help="Existing stable ADR path for accepted/implemented."),
    ] = None,
    affects: Annotated[
        list[str] | None,
        typer.Option("--affects", help="Affected component id. Repeatable."),
    ] = None,
    affects_none: Annotated[
        bool,
        typer.Option("--affects-none", help="Explicitly declare that no components are affected."),
    ] = False,
    required_update: Annotated[
        list[str] | None,
        typer.Option("--required-update", help="Required downstream doc path. Repeatable."),
    ] = None,
    no_required_updates: Annotated[
        bool,
        typer.Option("--no-required-updates", help="Explicitly declare no required doc updates."),
    ] = False,
    reason: Annotated[
        str | None,
        typer.Option("--reason", help="Human rejection rationale (rejected only)."),
    ] = None,
    attest_implemented: Annotated[
        bool,
        typer.Option(
            "--attest-implemented",
            help="Human attestation that a legacy RFC was historically implemented.",
        ),
    ] = False,
    fmt: Annotated[str, typer.Option("--format", help="Output format: plain or json.")] = "plain",
    confirm: Annotated[
        bool,
        typer.Option("--confirm", help="Apply the migration. Without it, only the plan prints."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print the plan without writing even with --confirm."),
    ] = False,
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """Inventory or explicitly classify RFCs created before lifecycle metadata.

    Evidence is never converted into a state recommendation. Mutations are
    one-RFC-at-a-time, dry-run by default, and require human-selected inputs.
    """
    from irminsul.change.migrate import (
        format_inventory_plain,
        format_plan_plain,
        get_candidate,
        inventory_candidates,
        inventory_to_json,
        plan_migration,
        plan_to_json,
    )
    from irminsul.change.report import ChangeError
    from irminsul.fix import apply_fixes

    if fmt not in ("plain", "json"):
        typer.echo(typer.style(f"unknown --format '{fmt}'; expected plain or json", fg="red"))
        raise typer.Exit(code=2)

    repo_root, config = _load_repo(path)
    graph = build_graph(repo_root, config)
    mutation_flags = any(
        (
            state is not None,
            resolved_by is not None,
            bool(affects),
            affects_none,
            bool(required_update),
            no_required_updates,
            reason is not None,
            attest_implemented,
            confirm,
            dry_run,
        )
    )
    try:
        if change_id is None:
            if mutation_flags:
                raise ChangeError("an RFC argument is required for migration planning", code=2)
            candidates = inventory_candidates(graph, config)
            typer.echo(
                inventory_to_json(candidates)
                if fmt == "json"
                else format_inventory_plain(candidates)
            )
            return

        if state is None:
            if mutation_flags:
                raise ChangeError(
                    "--state is required before migration options can be used", code=2
                )
            _, candidate = get_candidate(graph, config, change_id)
            typer.echo(
                inventory_to_json([candidate])
                if fmt == "json"
                else format_inventory_plain([candidate])
            )
            return

        plan = plan_migration(
            graph,
            config,
            change_id,
            state.value,
            resolved_by=resolved_by,
            affects=affects,
            affects_none=affects_none,
            required_updates=required_update,
            no_required_updates=no_required_updates,
            reason=reason,
            attest_implemented=attest_implemented,
        )
    except ChangeError as exc:
        typer.echo(typer.style(str(exc), fg="red"))
        raise typer.Exit(code=exc.code) from exc

    if plan.blockers:
        typer.echo(plan_to_json(plan) if fmt == "json" else format_plan_plain(plan))
        raise typer.Exit(code=1)

    assert plan.fix is not None
    result = apply_fixes(
        repo_root,
        [plan.fix],
        dry_run=dry_run or not confirm,
        confirm=True,
    )
    if result.errors:
        for error in result.errors:
            typer.echo(typer.style(error, fg="red"))
        raise typer.Exit(code=1)

    applied = confirm and not dry_run
    if fmt == "json":
        typer.echo(plan_to_json(plan, applied=applied, written=bool(result.written)))
    else:
        typer.echo(format_plan_plain(plan))
        if applied:
            typer.echo(typer.style(f"updated {len(result.written)} file(s)", fg="green"))
        else:
            typer.echo(
                typer.style("planned 1 migration; re-run with --confirm to apply", fg="green")
            )


class RelationSelection(StrEnum):
    all = "all"
    dependency = "dependency"
    supersession = "supersession"


@_change_app.command("status")
def change_status(
    change_id: Annotated[str, typer.Argument(help="RFC id, number, or repo-relative path.")],
    fmt: Annotated[str, typer.Option("--format", help="Output format: plain or json.")] = "plain",
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """Show a change's lifecycle, declared scope, evidence summary, and next actions."""
    from irminsul.change.report import (
        ChangeError,
        build_change_report,
        change_report_to_json,
        format_change_status_plain,
    )

    if fmt not in ("plain", "json"):
        typer.echo(typer.style(f"unknown --format '{fmt}'; expected plain or json", fg="red"))
        raise typer.Exit(code=2)

    repo_root, config = _load_repo(path)
    try:
        report = build_change_report(repo_root, config, change_id)
    except ChangeError as exc:
        typer.echo(typer.style(str(exc), fg="red"))
        raise typer.Exit(code=exc.code) from exc
    typer.echo(
        change_report_to_json(report) if fmt == "json" else format_change_status_plain(report)
    )


@_change_app.command("graph")
def change_graph(
    change_id: Annotated[
        str | None,
        typer.Argument(help="Optional RFC id, number, or repo-relative path."),
    ] = None,
    relation: Annotated[
        RelationSelection,
        typer.Option("--relation", help="Relationship kind: all, dependency, or supersession."),
    ] = RelationSelection.all,
    fmt: Annotated[str, typer.Option("--format", help="Output format: plain or json.")] = "plain",
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """Show the repository RFC relation graph or one connected component."""
    from irminsul.change.relations import (
        build_relation_graph,
        format_relation_graph_plain,
        relation_graph_to_json,
    )
    from irminsul.change.report import ChangeError

    if fmt not in ("plain", "json"):
        typer.echo(typer.style(f"unknown --format '{fmt}'; expected plain or json", fg="red"))
        raise typer.Exit(code=2)

    repo_root, config = _load_repo(path)
    try:
        report = build_relation_graph(
            repo_root,
            config,
            focus=change_id,
            relation=relation.value,
        )
    except ChangeError as exc:
        typer.echo(typer.style(str(exc), fg="red"))
        raise typer.Exit(code=exc.code) from exc
    typer.echo(
        relation_graph_to_json(report) if fmt == "json" else format_relation_graph_plain(report)
    )


@_change_app.command("verify")
def change_verify(
    change_id: Annotated[str, typer.Argument(help="RFC id, number, or repo-relative path.")],
    base_ref: Annotated[
        str | None,
        typer.Option(
            "--base-ref",
            help="Base git ref for implementation evidence (compared against HEAD).",
        ),
    ] = None,
    fmt: Annotated[str, typer.Option("--format", help="Output format: plain or json.")] = "plain",
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """Report implementation evidence, mechanical blockers, and semantic-review clues.

    Read-only. The result can say a change is mechanically ready; it never
    claims the behavior is correct — that judgment stays with the reviewer.
    """
    from irminsul.change.report import (
        ChangeError,
        build_change_report,
        change_report_to_json,
        format_change_verify_plain,
    )

    if fmt not in ("plain", "json"):
        typer.echo(typer.style(f"unknown --format '{fmt}'; expected plain or json", fg="red"))
        raise typer.Exit(code=2)

    repo_root, config = _load_repo(path)
    try:
        report = build_change_report(repo_root, config, change_id, base_ref=base_ref)
    except ChangeError as exc:
        typer.echo(typer.style(str(exc), fg="red"))
        raise typer.Exit(code=exc.code) from exc
    typer.echo(
        change_report_to_json(report) if fmt == "json" else format_change_verify_plain(report)
    )


@_change_app.command("transition")
def change_transition(
    change_id: Annotated[str, typer.Argument(help="RFC id, number, or repo-relative path.")],
    target: Annotated[
        TransitionTarget,
        typer.Argument(help="Human-authorized decision: accepted or rejected."),
    ],
    resolved_by: Annotated[
        str | None,
        typer.Option(
            "--resolved-by",
            help="Repo-relative path of the decision doc resolving this RFC (accepted only).",
        ),
    ] = None,
    confirm: Annotated[
        bool,
        typer.Option("--confirm", help="Apply the transition. Without it, only the plan prints."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print the planned edits without writing files."),
    ] = False,
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """Validate and apply a lifecycle decision atomically.

    `implemented` is not a valid target here: only `change finalize` may write
    it, after verification.
    """
    from irminsul.change.report import ChangeError
    from irminsul.change.transition import plan_transition
    from irminsul.fix import apply_fixes

    repo_root, config = _load_repo(path)
    graph = build_graph(repo_root, config)
    try:
        plan = plan_transition(graph, config, change_id, target.value, resolved_by=resolved_by)
    except ChangeError as exc:
        typer.echo(typer.style(str(exc), fg="red"))
        raise typer.Exit(code=exc.code) from exc

    typer.echo(f"{plan.change}: {plan.current_state} -> {plan.target_state}")
    if plan.blockers:
        for blocker in plan.blockers:
            typer.echo(typer.style(f"  blocker [{blocker.code}]: {blocker.message}", fg="red"))
            if blocker.suggestion:
                typer.echo(typer.style(f"    -> {blocker.suggestion}", dim=True))
        raise typer.Exit(code=1)

    for note in plan.notes:
        typer.echo(typer.style(f"  note: {note}", fg="yellow"))

    result = apply_fixes(repo_root, list(plan.fixes), dry_run=dry_run or not confirm, confirm=True)
    for planned in result.planned:
        typer.echo(f"  {planned.path.as_posix()}: {planned.description}")
    if result.errors:
        for error in result.errors:
            typer.echo(typer.style(error, fg="red"))
        raise typer.Exit(code=1)

    if dry_run or not confirm:
        suffix = "" if confirm else "; re-run with --confirm to apply"
        typer.echo(typer.style(f"planned {len(result.planned)} edit(s){suffix}", fg="green"))
    else:
        typer.echo(typer.style(f"updated {len(result.written)} file(s)", fg="green"))
    raise typer.Exit(code=0)


@_change_app.command("impact")
def change_impact(
    change_id: Annotated[str, typer.Argument(help="RFC id, number, or repo-relative path.")],
    base_ref: Annotated[
        str | None,
        typer.Option("--base-ref", help="Base git ref for observed impact (compared to HEAD)."),
    ] = None,
    all_layers: Annotated[
        bool,
        typer.Option("--all-layers", help="Include layers with no observations."),
    ] = False,
    fmt: Annotated[str, typer.Option("--format", help="Output format: plain or json.")] = "plain",
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """Show where a change reached, layer by layer, with review routes.

    Derived on demand from the diff and the doc graph — never stored on the
    RFC. Without a resolvable diff the report is plan-level impact, stated
    explicitly rather than rendered as an empty observed impact.
    """
    from irminsul.change.impact import (
        build_impact_report,
        format_impact_plain,
        impact_report_to_json,
    )
    from irminsul.change.report import ChangeError

    if fmt not in ("plain", "json"):
        typer.echo(typer.style(f"unknown --format '{fmt}'; expected plain or json", fg="red"))
        raise typer.Exit(code=2)

    repo_root, config = _load_repo(path)
    try:
        report = build_impact_report(repo_root, config, change_id, base_ref=base_ref)
    except ChangeError as exc:
        typer.echo(typer.style(str(exc), fg="red"))
        raise typer.Exit(code=exc.code) from exc
    typer.echo(
        impact_report_to_json(report, all_layers=all_layers)
        if fmt == "json"
        else format_impact_plain(report, all_layers=all_layers)
    )


@_change_app.command("finalize")
def change_finalize(
    change_id: Annotated[str, typer.Argument(help="RFC id, number, or repo-relative path.")],
    anchor: Annotated[
        list[str] | None,
        typer.Option(
            "--anchor",
            help=(
                "Confirmed requirement binding: <requirement-id>=<path>[#<symbol>]. "
                "Repeatable; code and test anchors may both be given."
            ),
        ),
    ] = None,
    owner: Annotated[
        list[str] | None,
        typer.Option(
            "--owner",
            help="Explicit owner choice: <requirement-id>=<component id>. Repeatable.",
        ),
    ] = None,
    base_ref: Annotated[
        str | None,
        typer.Option("--base-ref", help="Base git ref covering the implementation range."),
    ] = None,
    confirm: Annotated[
        bool,
        typer.Option("--confirm", help="Apply the plan. Without it, only the dry-run prints."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print the planned writes without touching files."),
    ] = False,
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """Verify, promote confirmed claims, and transition accepted -> implemented atomically.

    Prints a dry-run plan by default. `--confirm` asserts the caller reviewed the
    semantic clues; it cannot override mechanical blockers. Component-doc writes
    are applied before the RFC transition, so a failed write never leaves an
    implemented RFC without its promoted claims.
    """
    from irminsul.change.finalize import parse_binding_flags, plan_finalize
    from irminsul.change.report import ChangeError, build_change_report
    from irminsul.fix import apply_fixes

    repo_root, config = _load_repo(path)
    graph = build_graph(repo_root, config)
    try:
        bindings = parse_binding_flags(anchor or [], "--anchor")
        owners = parse_binding_flags(owner or [], "--owner")
        report = build_change_report(repo_root, config, change_id, base_ref=base_ref, graph=graph)
        plan = plan_finalize(
            graph,
            config,
            repo_root,
            change_id,
            bindings=bindings,
            owners=owners,
            base_ref=base_ref,
        )
    except ChangeError as exc:
        typer.echo(typer.style(str(exc), fg="red"))
        raise typer.Exit(code=exc.code) from exc

    typer.echo(f"{plan.change}: {plan.current_state} -> implemented")
    if plan.blockers:
        for blocker in plan.blockers:
            typer.echo(typer.style(f"  blocker [{blocker.code}]: {blocker.message}", fg="red"))
            if blocker.suggestion:
                typer.echo(typer.style(f"    -> {blocker.suggestion}", dim=True))
        raise typer.Exit(code=1)

    if report.semantic_review:
        typer.echo("  semantic review (--confirm asserts you reviewed these):")
        for clue in report.semantic_review:
            typer.echo(typer.style(f"    - {clue.question}", fg="yellow"))
    else:
        typer.echo("  semantic review: (no remaining clues)")

    for note in plan.notes:
        typer.echo(typer.style(f"  note: {note}", fg="yellow"))
    for promotion in plan.promotions:
        if not promotion.already_promoted:
            typer.echo(
                f"  promote {promotion.global_id} -> {promotion.owner_path.as_posix()} "
                f"({len(promotion.anchors)} anchor(s))"
            )

    plan_only = dry_run or not confirm
    component_result = apply_fixes(
        repo_root, list(plan.component_fixes), dry_run=plan_only, confirm=True
    )
    for planned in component_result.planned:
        typer.echo(f"  {planned.path.as_posix()}: {planned.description}")
    if component_result.errors:
        for error in component_result.errors:
            typer.echo(typer.style(error, fg="red"))
        typer.echo(
            typer.style("aborted before the lifecycle transition; rfc_state unchanged", fg="red")
        )
        raise typer.Exit(code=1)

    rfc_result = apply_fixes(repo_root, list(plan.rfc_fixes), dry_run=plan_only, confirm=True)
    for planned in rfc_result.planned:
        typer.echo(f"  {planned.path.as_posix()}: {planned.description}")
    if rfc_result.errors:
        for error in rfc_result.errors:
            typer.echo(typer.style(error, fg="red"))
        raise typer.Exit(code=1)

    total_planned = len(component_result.planned) + len(rfc_result.planned)
    total_written = len(component_result.written) + len(rfc_result.written)
    if plan_only:
        suffix = "" if confirm else "; re-run with --confirm to apply"
        typer.echo(typer.style(f"planned {total_planned} write(s){suffix}", fg="green"))
    else:
        typer.echo(typer.style(f"updated {total_written} file(s)", fg="green"))
    raise typer.Exit(code=0)


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
    describes: Annotated[
        list[str] | None,
        typer.Option(
            "--describes",
            help="Source path the component claims (repeatable, stored repo-relative).",
        ),
    ] = None,
    tests: Annotated[
        list[str] | None,
        typer.Option(
            "--tests",
            help="Test path for the component (repeatable, stored repo-relative).",
        ),
    ] = None,
    from_surface: Annotated[
        bool,
        typer.Option(
            "--from-surface",
            help="Pre-fill a Surface section derived from the --describes paths.",
        ),
    ] = False,
    force: Annotated[bool, typer.Option("--force")] = False,
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """Scaffold a new component doc."""
    from irminsul.new.command import NewSpec, normalize_claim_path, write_new

    repo_root = path.resolve()
    config = load(find_config(repo_root))
    describes_rel = [normalize_claim_path(repo_root, value) for value in describes or []]
    tests_rel = [normalize_claim_path(repo_root, value) for value in tests or []]
    for rel in [*describes_rel, *tests_rel]:
        # describes/tests values may be glob patterns; a literal existence
        # check would false-warn on every wildcard.
        if not (repo_root / rel).exists() and not glob.glob(str(repo_root / rel), recursive=True):
            typer.echo(typer.style(f"warning: path does not exist: {rel}", fg="yellow"))

    surface_groups: list[dict[str, object]] = []
    if from_surface:
        if not describes_rel:
            typer.echo(
                typer.style("--from-surface requires at least one --describes path", fg="red")
            )
            raise typer.Exit(code=2)
        from irminsul.surface import derive_surface

        # Component docs live at <docs_root>/<layer>/<slug>.md, so the link
        # back to repo root climbs the docs_root depth plus the layer folder.
        # Resolve relative to repo_root so absolute or dotted docs_root values
        # still yield the right depth.
        try:
            docs_rel = (
                (repo_root / config.paths.docs_root).resolve().relative_to(repo_root.resolve())
            )
            docs_depth = len(docs_rel.parts)
        except ValueError:
            docs_depth = len(Path(config.paths.docs_root).parts)
        link_prefix = "../" * (docs_depth + 1)
        contributing: set[str] = set()
        for kind in ("cli", "http", "env-vars", "exports"):
            seen: set[str] = set()
            rows: list[dict[str, str]] = []
            for rel in describes_rel:
                for item in derive_surface(repo_root, config, kind, rel):
                    if item.identity in seen:
                        continue
                    seen.add(item.identity)
                    contributing.add(rel)
                    display = item.display or rel
                    rows.append(
                        {
                            "identity": item.identity,
                            "display": display,
                            "link": f"{link_prefix}{display}",
                        }
                    )
            if rows:
                surface_groups.append({"kind": kind, "rows": rows})
        for rel in describes_rel:
            if rel not in contributing:
                typer.echo(typer.style(f"note: no derivable surface for: {rel}", fg="yellow"))

    spec = NewSpec(
        kind="component",
        title=title,
        extra={"describes": describes_rel, "tests": tests_rel, "surface": surface_groups},
    )
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
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Overwrite an existing file and scaffold despite hard-check blockers.",
        ),
    ] = False,
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """Scaffold a new RFC.

    Runs the repository binding-readiness summary first (RFC 0034): hard-check
    errors block drafting because the base graph is structurally invalid, while
    drift clues and unrelated warnings are reported without preventing a new
    idea from being recorded.
    """
    from irminsul.change.readiness import (
        build_binding_readiness_report,
        format_binding_readiness_plain,
    )
    from irminsul.new.command import NewSpec, write_new

    repo_root = path.resolve()
    config = load(find_config(repo_root))

    readiness = build_binding_readiness_report(repo_root, config)
    if not readiness.ready or readiness.clues or readiness.repository_debt:
        typer.echo(format_binding_readiness_plain(readiness))
    if not readiness.ready and not force:
        typer.echo(
            typer.style(
                "hard checks fail; fix the graph before drafting (or pass --force)",
                fg="red",
            )
        )
        raise typer.Exit(code=1)

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
    all_files: Annotated[
        bool,
        typer.Option(
            "--all",
            help=(
                "List every source file with no doc claim, ignoring the "
                "covered-directory heuristic, grouped by directory."
            ),
        ),
    ] = False,
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """List source files in covered directories that no doc claims.

    With --all, list every unclaimed source file regardless of coverage.
    """
    from irminsul.listing.command import list_undocumented as _list_undocumented

    _list_undocumented(path.resolve(), fmt=fmt, all_files=all_files)


@_list_app.command("lifecycle")
def list_lifecycle(
    fmt: Annotated[str, typer.Option("--format")] = "plain",
    queue: Annotated[bool, typer.Option("--queue")] = False,
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """List unfinished decision update work."""
    from irminsul.listing.command import list_lifecycle as _list_lifecycle

    _list_lifecycle(path.resolve(), fmt=fmt, queue=queue)


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


@_regen_app.command("agents-md")
def regen_agents_md_command(
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """Regenerate the docs/AGENTS.md agent navigation manifest."""
    from irminsul.regen.agents_md import regen_agents_md

    repo_root, config = _load_repo(path)
    _print_regen_result(repo_root, regen_agents_md(repo_root, config))


if __name__ == "__main__":  # pragma: no cover
    app()
