"""Irminsul command-line entry point."""

from __future__ import annotations

import datetime as _dt
import glob
import os
import re
import sys
from collections.abc import Callable, Mapping
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Final

import typer
from typer.core import TyperGroup

try:
    from typer._click.exceptions import NoSuchOption
except ImportError:  # typer before it bundled click
    from click.exceptions import NoSuchOption  # type: ignore[assignment]

from irminsul import __version__
from irminsul.adoption import assess
from irminsul.anchors import RepinScope
from irminsul.checks import (
    REGISTRY,
    Finding,
    FindingClass,
    FindingSource,
    Fix,
    Severity,
    sort_findings,
    summarize,
)
from irminsul.checks.render import escape_github_data, findings_json, github_annotation
from irminsul.config import IrminsulConfig, find_config, load
from irminsul.docgraph import ChangeRange, DocGraph, build_graph
from irminsul.errors import UserError
from irminsul.fix import FixResult
from irminsul.init.command import (
    SUPPORTED_LANGUAGES,
    Topology,
    detect_code_signals,
    run_init,
    run_init_fresh,
    run_init_siblings,
)
from irminsul.inventory import KNOWN_KINDS_TEXT
from irminsul.seed.command import (
    PIB_INTRO,
    gather_answers_from_flags,
    gather_answers_interactive,
    run_seed,
)

if TYPE_CHECKING:
    from irminsul.docgraph import DocNode
    from irminsul.new.command import NewSpec


_MOVED: Final = {
    ("check", "--init-baseline"): "`irminsul baseline init`",
    ("check", "--update-baseline"): "`irminsul baseline update`",
    ("check", "--init-adoption"): "`irminsul adoption init`",
    ("check", "--update-adoption"): "`irminsul adoption update`",
    ("check", "--strict"): "`--fail-on hint,time`",
    ("context", "--before-edit"): "`irminsul context <path...>`",
}


class IrminsulGroup(TyperGroup):
    """The root command group: a `UserError` from any command is printed in red on stderr
    and becomes the exit status it carries, and an option a command no longer has names
    what replaced it."""

    def invoke(self, ctx: Any) -> Any:
        try:
            try:
                return super().invoke(ctx)
            except NoSuchOption as exc:
                command = (exc.ctx.info_name if exc.ctx is not None else None) or ""
                if (replacement := _MOVED.get((command, exc.option_name))) is None:
                    raise
                raise UserError(f"`{exc.option_name}` is now {replacement}") from exc
        except UserError as exc:
            typer.echo(typer.style(str(exc), fg="red"), err=True)
            raise typer.Exit(code=exc.code) from exc


class OutputFormat(StrEnum):
    plain = "plain"
    json = "json"


class CheckFormat(StrEnum):
    plain = "plain"
    json = "json"
    github = "github"


def _split_commas(values: list[str] | None) -> list[str] | None:
    return [name for value in values for name in value.split(",")] if values else values


PathOpt = Annotated[
    Path,
    typer.Option("--path", help="Root of the codebase."),
]
FormatOpt = Annotated[OutputFormat, typer.Option("--format", help="Output format.")]
CheckFormatOpt = Annotated[
    CheckFormat,
    typer.Option("--format", help="Output format; github prints workflow annotations."),
]
OnlyOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--only",
        callback=_split_commas,
        help=(
            "Registered checks to use instead of checks.enabled, whether or not they are "
            "enabled. Comma-separated or repeated."
        ),
    ),
]
CommittedOnlyOpt = Annotated[
    bool,
    typer.Option(
        "--committed-only",
        help=(
            "Uncommitted work is not a change: a change range ends at HEAD, the files a change "
            "is compared on are read at HEAD, and history times are commit times. Checks that "
            "judge the tree rather than the change still read the disk. With no base there "
            "is no change to judge."
        ),
    ),
]

app = typer.Typer(
    cls=IrminsulGroup,
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
    """Make stdout and stderr UTF-8 on Windows, where a legacy code page cannot print
    the help text and findings.

    `main()` calls it rather than the module import, so using the app as a library or
    through `CliRunner` leaves the streams alone.
    """
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
    # Click expands `*` in arguments on Windows, turning a quoted glob such as
    # `--describes "src/**"` into a list of files.
    app(windows_expand_args=False)


def _load_repo(path: Path) -> tuple[Path, IrminsulConfig]:
    """Where every command but `init` resolves `--path` and loads its config.

    `init` has no `irminsul.toml` yet. A `--path` below the directory holding the config
    is refused, because the doc tree it would read is the wrong one.
    """
    repo_root = path.resolve()
    config_path = find_config(repo_root)
    if config_path.is_file() and config_path.parent.resolve() != repo_root:
        raise UserError(
            f"{config_path.name} is in {config_path.parent}, not {repo_root}; run from "
            f"that directory or pass --path {config_path.parent}"
        )
    return repo_root, load(config_path)


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


def _offer_seed_after_scaffold(target: Path, *, interactive: bool) -> None:
    """After an interactive scaffold of a new project, offer to capture the PIB.

    Both paths that create a project rather than adopt one qualify: a
    fresh-start same-repo init, and the siblings layout, which is only reachable
    in a directory with no code in it.

    Non-interactive init never prompts, so it stays scriptable. `irminsul seed` is
    the standalone command for capturing or redoing the seed later.
    """
    if not interactive:
        return
    typer.echo()
    typer.echo(typer.style(PIB_INTRO, fg="cyan"))
    typer.echo()
    if not typer.confirm("Capture your project's principle, idea, and belief now?", default=False):
        typer.echo("Hint: run `irminsul seed` whenever you're ready.")
        return
    _, config = _load_repo(target)
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
        Topology,
        typer.Option(
            "--topology",
            help=(
                "Repository layout: 'same-repo' (docs/ inside the code repo) or "
                "'siblings' (this docs repo beside a separate code repo)."
            ),
        ),
    ] = Topology.same_repo,
    code_repo: Annotated[
        str | None,
        typer.Option(
            "--code-repo",
            help=(
                "Sibling code repository for `--topology siblings`: GitHub "
                "'owner/repo' or a relative path such as '../code'."
            ),
        ),
    ] = None,
    language: Annotated[
        list[str] | None,
        typer.Option(
            "--language",
            help=(
                "Language profile for code that cannot be detected yet. Repeat for "
                f"multiple profiles. Supported: {', '.join(SUPPORTED_LANGUAGES)}."
            ),
        ),
    ] = None,
    allow_existing_code: Annotated[
        bool,
        typer.Option(
            "--allow-existing-code",
            help="Allow --fresh even when code signals already exist.",
        ),
    ] = False,
    name: Annotated[
        str | None,
        typer.Option(
            "--name",
            help=(
                "Project name for irminsul.toml and the docs; answers the prompt for it. "
                "Without it the name is the directory's."
            ),
        ),
    ] = None,
    no_interactive: Annotated[
        bool,
        typer.Option(
            "--no-interactive",
            help="Do not prompt; pass required choices explicitly. CI-friendly.",
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help=(
                "Overwrite scaffold files that already exist. A file git cannot restore "
                "is first copied to <name>.irminsul-backup. In a root AGENTS.md only "
                "Irminsul's marked section is replaced."
            ),
        ),
    ] = False,
    path: PathOpt = Path("."),
) -> None:
    """Scaffold the docs skeleton, irminsul.toml, and CI workflows.

    Two repository layouts are supported. `--topology same-repo` (the default)
    puts `docs/` inside the code repo. `--topology siblings` scaffolds a docs
    repo that sits beside a separate code repo under a common parent directory,
    which is how a private docs tree pairs with a public code repo.
    """
    target = path.resolve()
    target.mkdir(parents=True, exist_ok=True)
    interactive = not no_interactive

    if code_repo is not None and topology != Topology.siblings:
        raise UserError("`--code-repo` is only valid with `--topology siblings`.")

    if topology == Topology.siblings:
        if fresh:
            raise UserError(
                "`--fresh` is not valid with `--topology siblings`. The sibling "
                "code checkout is detected on disk, so the same command covers a "
                "code repo that already exists and one that does not exist yet. "
                "Run `irminsul init --topology siblings --code-repo <spec-or-path>`."
            )
        _init_siblings(
            target,
            interactive=interactive,
            code_repo=code_repo,
            languages=language,
            name=name,
            force=force,
        )
        _offer_seed_after_scaffold(target, interactive=interactive)
        return

    has_code = detect_code_signals(target)

    if fresh:
        if has_code and not allow_existing_code:
            raise UserError(
                "Code signals already exist in the target directory. "
                "Use `irminsul init` to adopt existing same-repo code, or pass "
                "`--allow-existing-code` with `--fresh` if this is intentional."
            )
        run_init_fresh(target, interactive=interactive, languages=language, name=name, force=force)
        _offer_seed_after_scaffold(target, interactive=interactive)
        return

    if interactive and not has_code:
        typer.echo("No code detected here. What are you setting up?")
        typer.echo("  [1] Fresh-start, same repo")
        typer.echo("  [2] Docs repo beside a separate code repo (siblings)")
        typer.echo("  [3] Cancel")
        answer = typer.prompt("Choose", default="1")
        if answer == "1":
            run_init_fresh(
                target, interactive=interactive, languages=language, name=name, force=force
            )
            _offer_seed_after_scaffold(target, interactive=interactive)
            return
        if answer == "2":
            _init_siblings(
                target,
                interactive=interactive,
                code_repo=code_repo,
                languages=language,
                name=name,
                force=force,
            )
            _offer_seed_after_scaffold(target, interactive=interactive)
            return
        typer.echo("Canceled.")
        raise typer.Exit(code=0)
    elif not interactive and not has_code:
        raise UserError(
            "No code detected in the target directory.\n"
            "Use `irminsul init --fresh` to start a new project, or\n"
            "`irminsul init --topology siblings --code-repo <spec-or-path>` "
            "for a docs repo beside a separate code repo."
        )

    run_init(target, interactive=interactive, languages=language, name=name, force=force)


def _init_siblings(
    target: Path,
    *,
    interactive: bool,
    code_repo: str | None,
    languages: list[str] | None,
    name: str | None,
    force: bool,
) -> None:
    """Guard the siblings scaffold against being run inside a code repo.

    The target of `--topology siblings` is the docs repo; code signals there
    mean the caller wanted the same-repo layout instead.
    """
    if detect_code_signals(target):
        if not interactive:
            raise UserError(
                "This directory contains code signals. The siblings layout "
                "scaffolds a repo that holds only docs, beside the code repo; "
                "for code and docs in one repo use `irminsul init` instead."
            )
        if not typer.confirm(
            "This directory looks like a code repo. Are you sure you want the siblings layout?",
            default=False,
        ):
            typer.echo("Hint: use `irminsul init` for a single-repo setup.")
            raise typer.Exit(code=0)

    run_init_siblings(
        target,
        interactive=interactive,
        code_repo=code_repo,
        languages=languages,
        name=name,
        force=force,
    )


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
        typer.Option("--no-interactive", help="Use the flags instead of prompting. CI-friendly."),
    ] = False,
    path: PathOpt = Path("."),
) -> None:
    """Capture the project's principle, idea, and belief into the foundation layer."""
    repo_root, config = _load_repo(path)

    if no_interactive:
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
    typer.echo(f"{location}  {severity_str}  [{finding.code}]  {finding.message}")
    if finding.suggestion:
        typer.echo(typer.style(f"      → {finding.suggestion}", dim=True))


def _print_adoption_note(graph: DocGraph) -> None:
    """What the run left unreported because the adoption record excepts it."""
    assessment = assess(graph)
    note = assessment.note() if assessment is not None else None
    if note is not None:
        typer.echo(typer.style(note[0], fg=note[1]))


def _print_run_notes(
    baseline_status: Mapping[str, object], delta_status: Mapping[str, object] | None
) -> None:
    """The baseline or delta line that tells a reader what the counts leave out.

    Printed by every human-readable format, github included: without it a run
    whose findings were all suppressed by the baseline looks clean in CI, with
    no sign of the suppression or of stale entries ready to ratchet down.
    """
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
            f" ({stale} fixed entr{'y' if stale == 1 else 'ies'};"
            " run irminsul baseline update to remove them)"
            if isinstance(stale, int) and stale > 0
            else ""
        )
        typer.echo(
            typer.style(
                f"baseline: {baseline_status['suppressed']} certain finding(s) hidden"
                f"{stale_note}; irminsul list baseline shows them",
                fg="cyan",
            )
        )


def _report_hidden_to_github(baseline_status: Mapping[str, object], hidden: list[Finding]) -> None:
    """Make baseline debt visible on the pull request: one warning annotation, and the
    full list in the job summary when GitHub provides one."""
    import os

    if not baseline_status["applied"] or not (hidden or baseline_status["stale"]):
        return
    message = (
        f"{len(hidden)} certain finding(s) are hidden by the baseline "
        f"{baseline_status['path']}; {baseline_status['stale']} entr"
        f"{'y is' if baseline_status['stale'] == 1 else 'ies are'} fixed and can be removed"
    )
    typer.echo(f"::warning title=irminsul baseline::{escape_github_data(message)}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary or not hidden:
        return
    lines = ["## Findings hidden by the Irminsul baseline", ""]
    for finding in hidden:
        where = finding.path.as_posix() if finding.path else "(repository)"
        lines.append(f"- `{finding.code}` {where}: {finding.message}")
    try:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    except OSError:
        pass


def _print_summary(counts: dict[Severity, int]) -> None:
    parts: list[str] = [
        f"{counts[Severity.error]} error{'s' if counts[Severity.error] != 1 else ''}",
        f"{counts[Severity.warning]} warning{'s' if counts[Severity.warning] != 1 else ''}",
    ]
    if counts[Severity.info]:
        parts.append(f"{counts[Severity.info]} info")
    typer.echo(", ".join(parts))


def _source_diff_refs(values: list[str], config: IrminsulConfig) -> dict[str | None, str]:
    """Parse `--source-diff` into a ref per declared source, or one for all of them.

    A bare ref keys on `None` and applies everywhere, which is the single-source case the
    generated workflow produces and stays the default. `name=ref` names one declared source.
    The two spellings do not mix: one says "every repository is at this ref" and the other
    says "this repository is under review", and a run holding both has not decided which.
    An unknown name exits rather than being ignored — a selector nobody matches is a gate
    reading an empty change set, which passes everything.
    """
    declared = {source.name for source in config.paths.sources}
    named: dict[str | None, str] = {}
    bare: list[str] = []
    for value in values:
        source, sep, ref = value.partition("=")
        if not sep:
            bare.append(value)
            continue
        if not ref:
            raise typer.BadParameter(f"--source-diff {value!r} names a source with no ref")
        if source not in declared:
            known = ", ".join(sorted(declared)) or "none are declared"
            raise typer.BadParameter(
                f"--source-diff names source {source!r}, which `paths.sources` does not "
                f"declare (declared: {known})"
            )
        named[source] = ref
    if bare and named:
        raise typer.BadParameter(
            "--source-diff was given both a bare ref and a SOURCE=REF one. The first says "
            "every source repository is at that ref and the second says one repository is "
            "under review; a run cannot mean both"
        )
    if len(bare) > 1:
        raise typer.BadParameter(
            "--source-diff was given more than one bare ref; name the source each belongs to"
        )
    if bare:
        return {None: bare[0]}
    return named


@app.command()
def check(
    only: OnlyOpt = None,
    fail_on: Annotated[
        str | None,
        typer.Option(
            "--fail-on",
            help=(
                "Finding classes that fail the run beyond certain, which always fails: "
                "comma-separated hint, time. Defaults to certain alone."
            ),
        ),
    ] = None,
    fmt: CheckFormatOpt = CheckFormat.plain,
    diff: Annotated[
        str | None,
        typer.Option(
            "--diff",
            help=(
                "Base git ref for the diff passes: co-change warns when source files "
                "changed between the merge base of <base> and HEAD and the working tree "
                "without their owning docs, and diff-integrity fails a change that weakens "
                "the gate. Uncommitted work counts: staged and unstaged edits, deletions "
                "and untracked files that gitignore does not exclude. Time findings are "
                "left out."
            ),
        ),
    ] = None,
    committed_only: CommittedOnlyOpt = False,
    path: PathOpt = Path("."),
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
    no_baseline: Annotated[
        bool,
        typer.Option("--no-baseline", help="Ignore an existing baseline file for this run."),
    ] = False,
    source_diff: Annotated[
        list[str] | None,
        typer.Option(
            "--source-diff",
            metavar="REF|SOURCE=REF",
            help=(
                "Base ref to read in a cross-repository source's own repository, for a gate "
                "running on a source-repository pull request. The docs repository's diff "
                "cannot see another repository's commits, so without this a source change "
                "to recorded ownership debt reads as untouched. A bare REF applies to every "
                "declared source and every one must resolve it; SOURCE=REF names one "
                "declared source and may be repeated, which is what a pull request in one "
                "repository needs when two of them spell their default branch differently. "
                "Needs --diff as well; the source range is a second axis, not a replacement."
            ),
        ),
    ] = None,
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
    from irminsul.checks.change_range import resolve_change_range
    from irminsul.checks.pipeline import run_checks, run_delta, select_checks

    if source_diff and diff is None:
        raise UserError(
            "--source-diff names a base in the source repository and needs a base in "
            "this one too: pass --diff <ref>. On a "
            "source-repository pull request the docs checkout sits on its default "
            "branch, so `--diff origin/<default>` is an empty docs range and the source "
            "range is what the run judges."
        )

    failing = _failing_classes(fail_on)

    if delta_base is not None:
        delta = True

    if no_baseline and delta:
        raise UserError("--no-baseline and --delta are mutually exclusive")

    now_date: _dt.date | None = None
    if now is not None:
        try:
            now_date = _dt.date.fromisoformat(now)
        except ValueError:
            raise UserError(f"unknown --now '{now}'; expected YYYY-MM-DD") from None

    repo_root, config = _load_repo(path)
    # An unregistered --only name exits 2 here, before any graph is built.
    select_checks(config, only)

    if diff is not None and not diff.strip():
        raise UserError("--diff was given an empty value; pass a git ref or omit the flag")

    change: ChangeRange | None = None
    if diff is not None:
        source_refs = _source_diff_refs(source_diff, config) if source_diff else None
        change = resolve_change_range(
            repo_root, config, diff, source_refs, committed_only=committed_only
        )

    graph = build_graph(
        repo_root, config, now=now_date, change=change, committed_only=committed_only
    )

    from dataclasses import replace

    # The delta compares the run with the base, so it reads the run as if no baseline existed.
    result = run_checks(graph, only=only, baseline=not (no_baseline or delta))

    delta_status: dict[str, object] | None = None

    if delta:
        delta_base_rev = delta_base or "HEAD"
        delta_result = run_delta(
            result,
            graph,
            delta_base_rev,
            remedy="run `irminsul check`, or pass an earlier --delta-base <rev>",
        )
        result = replace(result, findings=delta_result.new)
        delta_status = {
            "applied": True,
            "base": delta_base_rev,
            "new": len(delta_result.new),
            "pre_existing_suppressed": delta_result.pre_existing,
        }

    findings = result.findings
    baseline_status = result.baseline_report()
    hidden = result.hidden

    counts = summarize(findings)
    fail = result.failed(failing)

    if fmt == CheckFormat.json:
        typer.echo(findings_json(findings, graph, run=result, delta=delta_status))
    elif fmt == CheckFormat.github:
        for finding in findings:
            typer.echo(github_annotation(finding))
        _report_hidden_to_github(baseline_status, hidden)
        _print_run_notes(baseline_status, delta_status)
        _print_adoption_note(graph)
        _print_summary(counts)
    else:
        for finding in findings:
            _print_finding(finding)
        _print_run_notes(baseline_status, delta_status)
        _print_adoption_note(graph)
        _print_summary(counts)

    raise typer.Exit(code=1 if fail else 0)


def _failing_classes(fail_on: str | None) -> set[FindingClass]:
    if fail_on is None:
        return {FindingClass.certain}
    chosen = {value.strip() for value in fail_on.split(",") if value.strip()}
    unknown = sorted(chosen - {"certain", "hint", "time"})
    if unknown or not chosen:
        raise UserError(
            f"unknown --fail-on '{fail_on}'; expected a comma-separated list of certain, hint, time"
        )
    # Certain findings prove the tree breaks a rule, so no invocation can stop them
    # failing the run; --fail-on widens the set and never narrows it.
    return {FindingClass(value) for value in chosen} | {FindingClass.certain}


_baseline_app = typer.Typer(
    name="baseline",
    help="Create or shrink the baseline of certain findings.",
    no_args_is_help=True,
)
app.add_typer(_baseline_app)


def _run_without_baseline(repo_root: Path, config: IrminsulConfig) -> list[Finding]:
    """Every finding of the enabled checks, as if no baseline existed."""
    from irminsul.checks.pipeline import run_checks

    return run_checks(build_graph(repo_root, config), baseline=False).unbaselined


@_baseline_app.command("init")
def baseline_init(path: PathOpt = Path(".")) -> None:
    """Create the baseline file from the current certain findings. Refuses when one exists."""
    from irminsul.baseline import init_baseline

    repo_root, config = _load_repo(path)
    count = init_baseline(
        repo_root / config.paths.baseline, _run_without_baseline(repo_root, config)
    )
    typer.echo(
        typer.style(
            f"baseline: recorded {count} certain finding(s) in {config.paths.baseline}",
            fg="green",
        )
    )


@_baseline_app.command("update")
def baseline_update(path: PathOpt = Path(".")) -> None:
    """Remove baseline entries that no longer match.

    Exits 1 without writing when a certain finding the baseline does not record is present.
    """
    from irminsul.baseline import shrink_baseline

    repo_root, config = _load_repo(path)
    shrunk = shrink_baseline(
        repo_root / config.paths.baseline, _run_without_baseline(repo_root, config)
    )
    if shrunk.new:
        for finding in shrunk.new:
            _print_finding(finding)
        typer.echo(
            typer.style(
                f"baseline: {len(shrunk.new)} certain finding(s) are not in "
                f"{config.paths.baseline}; a baseline only shrinks, so fix them",
                fg="red",
            ),
            err=True,
        )
        raise typer.Exit(code=1)
    typer.echo(
        typer.style(
            f"baseline: removed {shrunk.removed} fixed entr"
            f"{'y' if shrunk.removed == 1 else 'ies'}, {shrunk.kept} remain",
            fg="green",
        )
    )


_adoption_app = typer.Typer(
    name="adoption",
    help="Create or shrink the record of managed files with no owning doc.",
    no_args_is_help=True,
)
app.add_typer(_adoption_app)


@_adoption_app.command("init")
def adoption_init(path: PathOpt = Path(".")) -> None:
    """Adopt Irminsul in an existing repository, recording every managed file with no owning doc.

    Those files alone are excepted from the ownership finding. Refuses when a record exists.
    """
    from irminsul.adoption import record_adoption

    repo_root, config = _load_repo(path)
    adopted = record_adoption(build_graph(repo_root, config), repo_root, config)
    typer.echo(
        typer.style(
            f"adoption: recorded {adopted.count} file(s) with no owning doc in "
            f"{config.paths.adoption}. Every check runs from now on; these files alone are "
            "excepted from the ownership finding, and each exception retires the moment its "
            "file gains an owner.",
            fg="green",
        )
    )
    for source in adopted.sources:
        typer.echo(
            typer.style(
                f"  adoption boundary: source '{source.source}' is history at "
                f"{source.revision[:12]} in its own repository",
                fg="cyan",
            )
        )


@_adoption_app.command("update")
def adoption_update(path: PathOpt = Path(".")) -> None:
    """Retire adoption-record entries whose file is now owned, deleted or moved.

    Exits 1 without writing when a file has no owner and no entry, since the record only shrinks.
    """
    from irminsul.adoption import retire_adoption

    repo_root, config = _load_repo(path)
    name = config.paths.adoption
    result = retire_adoption(build_graph(repo_root, config), repo_root, config)
    if result.added:
        for item in result.added:
            typer.echo(f"  {item}")
        typer.echo(
            typer.style(
                f"adoption: {len(result.added)} managed file(s) have no owner and no entry "
                f"in {name}; the record only shrinks, so document them",
                fg="red",
            ),
            err=True,
        )
        raise typer.Exit(code=1)
    remaining = (
        "full ownership coverage: every managed file has an owning doc. The record is "
        f"empty and you can delete {name}."
        if result.kept == 0
        else f"{result.kept} file(s) remain as recorded ownership debt"
    )
    typer.echo(
        typer.style(
            f"adoption: retired {result.removed} entr"
            f"{'y' if result.removed == 1 else 'ies'}; {remaining}",
            fg="green",
        )
    )


@app.command("context")
def context_command(
    targets: Annotated[
        list[Path] | None,
        typer.Argument(
            help=(
                "Source or doc paths to package before editing: owners, tests, active "
                "RFCs, requirements and excerpts. Runs no checks."
            )
        ),
    ] = None,
    after_edit: Annotated[
        bool,
        typer.Option(
            "--after-edit",
            help=(
                "Map the change to its owners and run the checks: what the repository "
                "fails on, and what this change introduced. With a base, the change runs "
                "from its merge base with HEAD to the working tree, and the passes "
                "`check --diff` adds run too."
            ),
        ),
    ] = False,
    base_ref: Annotated[
        str | None,
        typer.Option(
            "--base-ref",
            help=(
                "Branch point --after-edit measures this change against, such as "
                "origin/main; IRMINSUL_BASE_REF and GITHUB_BASE_REF name one when this "
                "is not given. Without a base the working tree is compared with HEAD, "
                "which says nothing about work this branch already committed, and the "
                "diff passes do not run."
            ),
        ),
    ] = None,
    committed_only: CommittedOnlyOpt = False,
    topic: Annotated[
        str | None,
        typer.Option(
            "--topic",
            help=(
                "Find docs by quoted topic keywords; every whitespace-separated term must "
                "match. Runs no checks."
            ),
        ),
    ] = None,
    include: Annotated[
        str | None,
        typer.Option(
            "--include",
            help=(
                "Content categories: owner, boundary, claims, requirements, dependencies, "
                "all, or none."
            ),
        ),
    ] = None,
    fmt: FormatOpt = OutputFormat.plain,
    path: PathOpt = Path("."),
) -> None:
    """Return task-specific navigation context; only --after-edit runs the checks."""
    from irminsul.context import (
        build_context_report,
        context_report_should_fail,
        context_report_to_json,
        format_context_plain,
        parse_content_categories,
    )

    repo_root, config = _load_repo(path)

    content_categories = parse_content_categories(include) if include is not None else None
    report = build_context_report(
        repo_root,
        config,
        target_paths=targets or None,
        topic=topic,
        after_edit=after_edit,
        content_categories=content_categories,
        base_ref=base_ref,
        committed_only=committed_only,
    )

    if fmt == OutputFormat.json:
        typer.echo(context_report_to_json(report))
    else:
        typer.echo(format_context_plain(report))

    raise typer.Exit(code=1 if context_report_should_fail(report) else 0)


@app.command("orient")
def orient_command(
    fmt: FormatOpt = OutputFormat.plain,
    path: PathOpt = Path("."),
) -> None:
    """Orient an agent in this repo: structure, doc totals, entry docs, and commands.

    The recommended first call for agents. Builds the doc graph once and runs
    no checks, so it is fast; every field is also available as stable JSON via
    `--format json`.
    """
    from irminsul.orient import build_orient_report, format_orient_plain, orient_report_to_json

    repo_root, config = _load_repo(path)
    report = build_orient_report(repo_root, config)
    typer.echo(
        orient_report_to_json(report) if fmt == OutputFormat.json else format_orient_plain(report)
    )


@app.command("refs")
def refs_command(
    target: Annotated[
        str,
        typer.Argument(help="Doc id, or repo-relative path of a doc or guidance file, to inspect."),
    ],
    fmt: FormatOpt = OutputFormat.plain,
    path: PathOpt = Path("."),
) -> None:
    """Return the docs that depend on or link to a doc."""
    from irminsul.refs import (
        build_doc_refs_report,
        doc_refs_report_to_json,
        format_doc_refs_plain,
    )

    repo_root, config = _load_repo(path)
    graph = build_graph(repo_root, config)

    report = build_doc_refs_report(repo_root, graph, target)
    typer.echo(
        doc_refs_report_to_json(report)
        if fmt == OutputFormat.json
        else format_doc_refs_plain(report)
    )


def _fix_result_to_json(result: FixResult, *, dry_run: bool, notes: list[str] | None = None) -> str:
    """The versioned JSON shape of a fix run.

    `written` is empty on a dry run by construction; `planned` is what the run
    would attempt. `notes` carries what the plain output says about a run that
    harvested nothing, so an all-empty envelope cannot be mistaken for a resolved
    finding.
    """
    import json

    def _fix_records(fixes: list[Fix]) -> list[dict[str, str]]:
        return [{"path": f.path.as_posix(), "description": f.description} for f in fixes]

    return json.dumps(
        {
            "version": 1,
            "dry_run": dry_run,
            "written": [p.as_posix() for p in result.written],
            "planned": _fix_records(result.planned),
            "held": _fix_records(result.held),
            "errors": list(result.errors),
            "notes": list(notes or []),
        },
        indent=2,
    )


def _echo_fix_result(result: FixResult, *, dry_run: bool) -> None:
    """List what a fix run did, in plain output.

    A dry run reports what it would attempt; a live run reports what actually
    changed. `apply_fixes` groups fixes by path and skips a path whose content
    is unchanged, so listing `planned` after a live run overstates the result.
    Shared by `fix` and the `change` commands that apply plans through the
    same machinery.
    """
    if dry_run:
        for planned in result.planned:
            typer.echo(f"  {planned.path.as_posix()}: {planned.description}")
    else:
        for written in result.written:
            typer.echo(f"  {written.as_posix()}")
    for held in result.held:
        typer.echo(typer.style(f"  held: {held.path.as_posix()}: {held.description}", fg="yellow"))


def _check_summary(cls: type[FindingSource]) -> str:
    """First line of the check class's docstring, falling back to its module's.

    The fallback alone is not enough: a module may host several checks, and its
    docstring would describe them all with the same generic line.
    """
    doc: str | None = cls.__doc__
    if not doc:
        module = sys.modules.get(cls.__module__)
        doc = getattr(module, "__doc__", None) if module else None
    if not doc:
        return ""
    return doc.strip().splitlines()[0]


_CLASS_BLURB: dict[FindingClass, str] = {
    # A baseline, `--delta` and a draft doc's own `drafts_exempt` codes each demote a
    # certain finding, so the blurb cannot say it fails every run.
    FindingClass.certain: (
        "the tree provably breaks a rule; an error unless a baseline or --delta "
        "filters it out, or it reports a draft doc as unfinished — in which case it "
        "enforces as a hint"
    ),
    # No flag reaches a code reported at info severity, so a run cannot be made to fail
    # on one.
    FindingClass.hint: (
        "needs judgment; a warning fails under --fail-on hint, while a "
        "hint reported at info severity never fails a run"
    ),
    FindingClass.time: "caused by elapsed time; left out of a run given --diff",
}


def _list_all_codes() -> None:
    from irminsul.checks.pipeline import finding_sources

    for check_name, cls in sorted(finding_sources().items()):
        if not cls.explanations:
            continue
        typer.echo(typer.style(f"[{check_name}]", fg="cyan", bold=True))
        for known_code in sorted(cls.explanations):
            typer.echo(f"  {known_code}")


def _first_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s+(?=[A-Z])", " ".join(text.split()), maxsplit=1)[0]


def _explain_check(check_name: str, cls: type[FindingSource]) -> None:
    from irminsul.checks.pipeline import class_of

    typer.echo(typer.style(check_name, fg="cyan", bold=True))
    summary = _check_summary(cls)
    typer.echo(f"check: {check_name}" + (f" — {summary}" if summary else ""))
    typer.echo()
    for known_code in sorted(cls.explanations):
        finding_class = class_of(known_code)
        label = f" ({finding_class.value})" if finding_class is not None else ""
        typer.echo(f"  {known_code}{label}")
        typer.echo(f"    {_first_sentence(cls.explanations[known_code])}")
    typer.echo()
    typer.echo("`irminsul explain <code>` gives one code's full explanation.")


@app.command("explain")
def explain_command(
    code: Annotated[
        str | None,
        typer.Argument(
            help=(
                "Finding code to explain, e.g. links/broken-link, or a check name, "
                "e.g. links, to list that check's codes."
            )
        ),
    ] = None,
) -> None:
    """Explain a finding code: what it means and how to fix it.

    A check name lists that check's codes with their classes. With no argument, lists
    every known code grouped by check.
    """
    if code is None:
        _list_all_codes()
        return

    from irminsul.checks.pipeline import class_of, finding_sources

    checks = finding_sources()
    for check_name, cls in sorted(checks.items()):
        explanation = cls.explanations.get(code)
        if explanation is None:
            continue
        typer.echo(typer.style(code, fg="cyan", bold=True))
        summary = _check_summary(cls)
        typer.echo(f"check: {check_name}" + (f" — {summary}" if summary else ""))
        finding_class = class_of(code)
        if finding_class is not None:
            typer.echo(f"class: {finding_class.value} — {_CLASS_BLURB[finding_class]}")
        typer.echo()
        typer.echo(explanation)
        return
    if code in checks and checks[code].explanations:
        _explain_check(code, checks[code])
        return

    from irminsul.checks.pipeline import did_you_mean

    known = [*checks, *(known_code for cls in checks.values() for known_code in cls.explanations)]
    raise UserError(
        f"unknown code '{code}'{did_you_mean(code, known, limit=2)}\n"
        "`irminsul explain` with no argument lists every code."
    )


@app.command()
def fix(
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
    only: OnlyOpt = None,
    fmt: FormatOpt = OutputFormat.plain,
    path: PathOpt = Path("."),
) -> None:
    """Apply deterministic remediations for fixable findings."""
    from irminsul.checks.pipeline import run_check, select_checks
    from irminsul.fix import apply_fixes

    repo_root, config = _load_repo(path)
    selected = select_checks(config, only)
    graph = build_graph(repo_root, config)

    fixes: list[Fix] = []
    for name in selected:
        maybe_fixes = getattr(REGISTRY[name](), "fixes", None)
        if maybe_fixes is not None:
            fixes.extend(maybe_fixes(run_check(REGISTRY[name], graph), graph))

    if not fixes:
        note = "no automatic fixes available"
        if fmt == OutputFormat.json:
            typer.echo(_fix_result_to_json(FixResult(), dry_run=dry_run, notes=[note]))
        else:
            typer.echo(note)
        raise typer.Exit(code=0)

    result = apply_fixes(repo_root, fixes, dry_run=dry_run, confirm=confirm)

    if fmt == OutputFormat.json:
        typer.echo(_fix_result_to_json(result, dry_run=dry_run))
        raise typer.Exit(code=1 if result.errors else 0)

    _echo_fix_result(result, dry_run=dry_run)

    if result.errors:
        for error in result.errors:
            typer.echo(typer.style(error, fg="red"), err=True)
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
            help=f"Surface kind: {KNOWN_KINDS_TEXT} (or a kind a configured surface rule declares)."
        ),
    ],
    source: Annotated[
        str | None,
        typer.Option("--source", help="Glob limiting which source files to scan."),
    ] = None,
    fmt: FormatOpt = OutputFormat.plain,
    path: PathOpt = Path("."),
) -> None:
    """Derive a code surface on demand — commands, endpoints, exports, or env vars.

    Nothing is written: the surface is recomputed from source each call, so it is
    fresh by construction and cannot drift.
    """
    from irminsul.surface import derive_requested_surface, surface_items_to_json

    repo_root, config = _load_repo(path)
    items = derive_requested_surface(repo_root, config, kind, source)
    if fmt == OutputFormat.json:
        typer.echo(surface_items_to_json(items))
    else:
        for item in items:
            typer.echo(item.identity)


@app.command("mcp")
def mcp_command(
    path: PathOpt = Path("."),
    probe: Annotated[
        bool,
        typer.Option(
            "--probe",
            help=(
                "Exit 0 if this installation can serve MCP, nonzero with the reason "
                "otherwise, without starting a server. `irminsul init` asks this of the "
                "launcher on PATH, which is the one the harness will run."
            ),
        ),
    ] = False,
) -> None:
    """Serve the doc graph to AI agents over the Model Context Protocol (stdio).

    Read-only: every tool returns the same JSON the CLI prints with
    `--format json`. Requires the optional `mcp` extra.
    """
    import importlib.util

    if importlib.util.find_spec("mcp") is None:
        raise UserError(
            "The MCP server needs the optional 'mcp' dependency. "
            "Install it with: pip install 'irminsul[mcp]'",
            code=1,
        )

    from irminsul.mcp_server import create_server

    if probe:
        # Everything that can fail before a client connects has now run: the optional
        # dependency resolves and the server module imports. Nothing is served.
        raise typer.Exit(code=0)

    repo_root, _ = _load_repo(path)
    create_server(repo_root).run()


@app.command("anchors")
def anchors_command(
    re_pin: Annotated[
        bool,
        typer.Option(
            "--re-pin",
            help=(
                "Rewrite anchor hashes and claim evidence pins to the current code "
                "(acknowledge after re-reading)."
            ),
        ),
    ] = False,
    suggest: Annotated[
        bool,
        typer.Option(
            "--suggest",
            help="List code names no anchor binds, with source files that contain them.",
        ),
    ] = False,
    doc: Annotated[
        str | None,
        typer.Option(
            "--doc", help="Only this doc, by id or repo-relative path, for --suggest or --re-pin."
        ),
    ] = None,
    every: Annotated[
        bool,
        typer.Option("--all", help="With --re-pin, re-pin every doc rather than one."),
    ] = False,
    claim: Annotated[
        list[str] | None,
        typer.Option(
            "--claim",
            help=(
                "With --re-pin --doc, re-pin only this claim's evidence pins, by claim id. "
                "Repeatable."
            ),
        ),
    ] = None,
    evidence: Annotated[
        list[str] | None,
        typer.Option(
            "--evidence",
            help=(
                "With --claim, re-pin only this evidence file, as the claim spells it. "
                "Applies to every --claim given. Repeatable."
            ),
        ),
    ] = None,
    anchor: Annotated[
        list[str] | None,
        typer.Option(
            "--anchor",
            help=(
                "With --re-pin --doc, re-pin only this anchor, spelled path#symbol as its "
                "marker spells it. Repeatable."
            ),
        ),
    ] = None,
    fmt: FormatOpt = OutputFormat.plain,
    path: PathOpt = Path("."),
) -> None:
    """Report or re-pin anchored prose claims, or suggest anchors for unbound code names.

    Re-pinning is a deliberate acknowledgement that you re-read the prose and it is
    still true; it is never done automatically by `irminsul fix`. `--doc` alone re-pins
    every drifted pin in the doc and names each one it moves; `--claim` and `--anchor`
    re-pin only what you re-read.
    """
    from irminsul.checks.claim_anchor import ClaimAnchorCheck
    from irminsul.checks.pipeline import run_check

    if re_pin and suggest:
        raise UserError("--re-pin and --suggest are mutually exclusive")
    scope = RepinScope(frozenset(claim or ()), frozenset(evidence or ()), frozenset(anchor or ()))
    problem = _repin_scope_problem(scope, re_pin=re_pin, doc=doc)
    if problem is not None:
        raise UserError(problem)

    repo_root, config = _load_repo(path)
    graph = build_graph(repo_root, config)

    wanted: str | None = None
    if doc is not None:
        from irminsul.docgraph import resolve_doc_target

        wanted = resolve_doc_target(graph, doc)
        if wanted is None or Path(wanted) not in graph.by_path:
            # Filtering by a doc that matches nothing suggests or re-pins nothing and exits
            # 0, which reads as success: an empty answer to a typo.
            raise UserError(f"--doc: no doc with id or path {doc}")

    if suggest:
        _suggest_anchors(repo_root, config, graph, doc=wanted, fmt=fmt)
        return

    if re_pin:
        # Re-pinning asserts "I re-read this prose and it is still true", which nobody
        # can honestly say about a whole repository at once, so the sweep is opt-in.
        if doc is None and not every:
            raise UserError(
                "--re-pin rewrites the drift signal you are meant to answer; name the "
                "doc you re-read with --doc <id|path>, or pass --all to re-pin every doc"
            )
        raise typer.Exit(code=_re_pin(repo_root, config, graph, wanted=wanted, scope=scope))

    findings = sort_findings(run_check(ClaimAnchorCheck, graph))
    if fmt == OutputFormat.json:
        typer.echo(findings_json(findings, graph))
        return
    for finding in findings:
        _print_finding(finding)
    typer.echo(f"{len(findings)} anchor finding(s)")


def _repin_scope_problem(scope: RepinScope, *, re_pin: bool, doc: str | None) -> str | None:
    """Why the selectors cannot narrow this invocation, or None when they can."""
    if not (scope.selective or scope.evidence):
        return None
    if not re_pin:
        return "--claim, --evidence and --anchor narrow --re-pin"
    if doc is None:
        return "--claim, --evidence and --anchor name pins inside one doc; add --doc <id|path>"
    if scope.evidence and not scope.claims:
        return "--evidence narrows a claim; name it with --claim <id>"
    return None


def _re_pin(
    repo_root: Path,
    config: IrminsulConfig,
    graph: DocGraph,
    *,
    wanted: str | None,
    scope: RepinScope,
) -> int:
    """Re-pin the docs `wanted` allows within `scope`, print what moved, and return the
    exit code.

    A selector that names nothing in the doc is refused before anything is written, so a
    typo in one of several does not leave the rest applied.
    """
    from irminsul.anchors import repin_doc, unknown_selectors
    from irminsul.checks.globs import resolve_display_path
    from irminsul.fix import apply_fixes

    if wanted is not None and (scope.selective or scope.evidence):
        node = graph.by_path[Path(wanted)]
        unknown = unknown_selectors(node.body, node.frontmatter.claims, scope)
        for message in unknown:
            typer.echo(typer.style(f"{wanted}: {message}", fg="red"), err=True)
        if unknown:
            typer.echo(typer.style("nothing was re-pinned", fg="red"), err=True)
            return 2

    def locate(spelling: str) -> Path | None:
        return resolve_display_path(repo_root, config.paths.source_roots, spelling)

    moved: dict[Path, tuple[list[str], list[str]]] = {}

    def re_pinner(node: DocNode) -> Callable[[str], str]:
        def apply(text: str) -> str:
            text, anchors, pins = repin_doc(repo_root, text, node.frontmatter.claims, locate, scope)
            moved[node.path] = (anchors, pins)
            return text

        return apply

    # The writer `fix` uses: through a temp file, since a plain `write_text` truncates
    # before it writes and `--re-pin --all` opens that window once per doc, and with each
    # file's own line endings. A failed write is collected rather than raised, so the sweep
    # finishes and names every doc it could not re-pin.
    result = apply_fixes(
        repo_root,
        [
            Fix(node.path, f"re-pin {node.path.as_posix()}", re_pinner(node))
            for node in graph.nodes.values()
            if wanted is None or node.path.as_posix() == wanted
        ],
        dry_run=False,
    )
    anchors_written = 0
    pins_written = 0
    for rel in result.written:
        anchors, pins = moved[rel]
        typer.echo(rel.as_posix())
        for label in [*anchors, *pins]:
            typer.echo(f"  {label}")
        anchors_written += len(anchors)
        pins_written += len(pins)
    typer.echo(
        typer.style(
            f"re-pinned {anchors_written} anchor(s), {pins_written} claim evidence pin(s)",
            fg="green",
        )
    )
    for failure in result.errors:
        typer.echo(typer.style(f"could not re-pin {failure}", fg="red"), err=True)
    return 2 if result.errors else 0


def _suggest_anchors(
    repo_root: Path,
    config: IrminsulConfig,
    graph: DocGraph,
    *,
    doc: str | None,
    fmt: OutputFormat,
) -> None:
    import json

    from irminsul.binding import bound_names, load_sources, suggest, unbound_names
    from irminsul.checks.code_spans import code_spans, is_live_doc
    from irminsul.code_references import CodeResolver

    resolver = CodeResolver(graph.source)
    sources = load_sources(graph.source)
    wanted = doc.replace("\\", "/") if doc else None
    rows: list[dict[str, object]] = []
    for node in sorted(graph.nodes.values(), key=lambda n: n.path.as_posix()):
        if wanted is not None and node.path.as_posix() != wanted:
            continue
        if wanted is None and not is_live_doc(node, config):
            continue
        bound = bound_names(node.body)
        seen: set[str] = set()
        for span in code_spans(node.body):
            for name in unbound_names([span.text], resolver, bound):
                if name in seen:
                    continue
                seen.add(name)
                found = suggest(repo_root, sources, name)
                rows.append(
                    {
                        "path": node.path.as_posix(),
                        "line": node.file_line(span.body_line),
                        "name": name,
                        "candidates": [
                            {
                                "path": c.path,
                                "line": c.line,
                                "definition": c.definition,
                                "marker": c.marker(name),
                            }
                            for c in found.candidates
                        ],
                        "unreachable": [
                            {"path": c.path, "line": c.line, "symbol": c.symbol}
                            for c in found.unreachable
                        ],
                    }
                )
    if fmt == OutputFormat.json:
        typer.echo(json.dumps({"version": 1, "unbound": rows}, indent=2))
        return
    for row in rows:
        typer.echo(f"{row['path']}:{row['line']} `{row['name']}`")
        candidates = row["candidates"]
        unreachable = row["unreachable"]
        assert isinstance(candidates, list) and isinstance(unreachable, list)
        for c in candidates:
            kind = "definition" if c["definition"] else "mention"
            typer.echo(f"  {c['path']}:{c['line']} ({kind})  {c['marker']}")
        for c in unreachable:
            typer.echo(
                f"  {c['path']}:{c['line']} defines it as `{c['symbol']}`, inside a function "
                "or block, where no anchor can reach it"
            )
        if not candidates and not unreachable:
            typer.echo("  no source file defines it; reword it if it is not this repo's code")
    typer.echo(f"{len(rows)} unbound code name(s)")


_change_app = typer.Typer(
    name="change",
    help="Bound-change lifecycle for RFCs: status, verification, and transitions.",
    no_args_is_help=True,
)
app.add_typer(_change_app)

_CHANGE_BASE_HELP = (
    "Git ref the change is measured from: its merge base with HEAD to the working tree, "
    "so uncommitted work counts. Defaults to IRMINSUL_BASE_REF or GITHUB_BASE_REF, then "
    "to HEAD."
)


class TransitionTarget(StrEnum):
    accepted = "accepted"
    rejected = "rejected"


@_change_app.command("status")
def change_status(
    change_id: Annotated[str, typer.Argument(help="RFC id, number, or repo-relative path.")],
    base_ref: Annotated[
        str | None,
        typer.Option("--base-ref", help=_CHANGE_BASE_HELP),
    ] = None,
    committed_only: CommittedOnlyOpt = False,
    fmt: FormatOpt = OutputFormat.plain,
    path: PathOpt = Path("."),
) -> None:
    """Show a change's lifecycle, declared scope, evidence summary, and next actions."""
    from irminsul.change.report import (
        build_change_report,
        change_report_to_json,
        format_change_status_plain,
    )

    repo_root, config = _load_repo(path)
    report = build_change_report(
        repo_root,
        config,
        change_id,
        base_ref=base_ref,
        next_step=True,
        committed_only=committed_only,
    )
    typer.echo(
        change_report_to_json(report)
        if fmt == OutputFormat.json
        else format_change_status_plain(report)
    )


@_change_app.command("verify")
def change_verify(
    change_id: Annotated[str, typer.Argument(help="RFC id, number, or repo-relative path.")],
    base_ref: Annotated[
        str | None,
        typer.Option("--base-ref", help=_CHANGE_BASE_HELP),
    ] = None,
    committed_only: CommittedOnlyOpt = False,
    fmt: FormatOpt = OutputFormat.plain,
    path: PathOpt = Path("."),
) -> None:
    """Report implementation evidence, mechanical blockers, and semantic-review clues.

    Read-only. The result can say a change is mechanically ready; it never
    claims the behavior is correct — that judgment stays with the reviewer.
    """
    from irminsul.change.report import (
        build_change_report,
        change_report_to_json,
        format_change_verify_plain,
    )

    repo_root, config = _load_repo(path)
    report = build_change_report(
        repo_root, config, change_id, base_ref=base_ref, committed_only=committed_only
    )
    typer.echo(
        change_report_to_json(report)
        if fmt == OutputFormat.json
        else format_change_verify_plain(report)
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
    path: PathOpt = Path("."),
) -> None:
    """Validate and apply a lifecycle decision atomically.

    `implemented` is not a valid target here: only `change finalize` may write
    it, after verification.
    """
    from irminsul.change.transition import plan_transition
    from irminsul.fix import apply_fixes

    repo_root, config = _load_repo(path)
    graph = build_graph(repo_root, config)
    plan = plan_transition(graph, config, change_id, target.value, resolved_by=resolved_by)

    typer.echo(f"{plan.change}: {plan.current_state} -> {plan.target_state}")
    if plan.blockers:
        for blocker in plan.blockers:
            typer.echo(
                typer.style(f"  blocker [{blocker.code}]: {blocker.message}", fg="red"), err=True
            )
            if blocker.suggestion:
                typer.echo(typer.style(f"    -> {blocker.suggestion}", dim=True))
        raise typer.Exit(code=1)

    for note in plan.notes:
        typer.echo(typer.style(f"  note: {note}", fg="yellow"))

    plan_only = not confirm
    result = apply_fixes(repo_root, list(plan.fixes), dry_run=plan_only, confirm=True)
    _echo_fix_result(result, dry_run=plan_only)
    if result.errors:
        for error in result.errors:
            typer.echo(typer.style(error, fg="red"), err=True)
        raise typer.Exit(code=1)

    if plan_only:
        typer.echo(
            typer.style(
                f"planned {len(result.planned)} edit(s); re-run with --confirm to apply",
                fg="green",
            )
        )
    else:
        typer.echo(typer.style(f"updated {len(result.written)} file(s)", fg="green"))
    raise typer.Exit(code=0)


@_change_app.command("finalize")
def change_finalize(
    change_id: Annotated[str, typer.Argument(help="RFC id, number, or repo-relative path.")],
    anchor: Annotated[
        list[str] | None,
        typer.Option(
            "--anchor",
            help=(
                "Confirmed requirement binding: <requirement-id>=<path>#<symbol>, or "
                "<requirement-id>=<path> to bind the whole file. Repeatable; code and test "
                "anchors may both be given."
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
        typer.Option("--confirm", help="Apply the plan. Without it, only the plan prints."),
    ] = False,
    path: PathOpt = Path("."),
) -> None:
    """Verify, promote confirmed claims, and transition accepted -> implemented atomically.

    Prints the plan by default. `--confirm` asserts the caller reviewed the
    semantic clues; it cannot override mechanical blockers. Component-doc writes
    are applied before the RFC transition, so a failed write never leaves an
    implemented RFC without its promoted claims. A working tree with uncommitted
    work is refused, with or without `--confirm`: commit or stash first.
    """
    from irminsul.change.finalize import parse_binding_flags, plan_finalize, refuse_uncommitted_work
    from irminsul.fix import apply_fixes
    from irminsul.git.reader import GitReader

    repo_root, config = _load_repo(path)
    refuse_uncommitted_work(GitReader(), repo_root)
    graph = build_graph(repo_root, config)
    bindings = parse_binding_flags(anchor or [], "--anchor")
    owners = parse_binding_flags(owner or [], "--owner")
    plan = plan_finalize(
        graph,
        config,
        repo_root,
        change_id,
        bindings=bindings,
        owners=owners,
        base_ref=base_ref,
    )

    typer.echo(f"{plan.change}: {plan.current_state} -> implemented")
    if plan.blockers:
        for blocker in plan.blockers:
            typer.echo(
                typer.style(f"  blocker [{blocker.code}]: {blocker.message}", fg="red"), err=True
            )
            if blocker.suggestion:
                typer.echo(typer.style(f"    -> {blocker.suggestion}", dim=True))
        raise typer.Exit(code=1)

    if plan.report.semantic_review:
        typer.echo("  semantic review (--confirm asserts you reviewed these):")
        for clue in plan.report.semantic_review:
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

    plan_only = not confirm
    component_result = apply_fixes(
        repo_root, list(plan.component_fixes), dry_run=plan_only, confirm=True
    )
    _echo_fix_result(component_result, dry_run=plan_only)
    if component_result.errors:
        for error in component_result.errors:
            typer.echo(typer.style(error, fg="red"), err=True)
        typer.echo(
            typer.style("aborted before the lifecycle transition; rfc_state unchanged", fg="red"),
            err=True,
        )
        raise typer.Exit(code=1)

    rfc_result = apply_fixes(repo_root, list(plan.rfc_fixes), dry_run=plan_only, confirm=True)
    _echo_fix_result(rfc_result, dry_run=plan_only)
    if rfc_result.errors:
        for error in rfc_result.errors:
            typer.echo(typer.style(error, fg="red"), err=True)
        raise typer.Exit(code=1)

    total_planned = len(component_result.planned) + len(rfc_result.planned)
    total_written = len(component_result.written) + len(rfc_result.written)
    if plan_only:
        typer.echo(
            typer.style(
                f"planned {total_planned} write(s); re-run with --confirm to apply", fg="green"
            )
        )
    else:
        typer.echo(typer.style(f"updated {total_written} file(s)", fg="green"))
    raise typer.Exit(code=0)


_new_app = typer.Typer(name="new", help="Scaffold a new doc atom.", no_args_is_help=True)
app.add_typer(_new_app)


def _write_new_doc(repo_root: Path, config: IrminsulConfig, spec: NewSpec, *, force: bool) -> None:
    from irminsul.new.command import write_new

    try:
        dest = write_new(repo_root, spec, config, force=force)
    except FileExistsError as e:
        typer.echo(typer.style(f"already exists: {e}", fg="yellow"))
        raise typer.Exit(1) from e
    rel = dest.relative_to(repo_root).as_posix()
    typer.echo(typer.style(f"created: {rel}", fg="green"))


@_new_app.command("adr")
def new_adr(
    title: Annotated[str, typer.Argument(help="Title of the ADR.")],
    force: Annotated[bool, typer.Option("--force")] = False,
    path: PathOpt = Path("."),
) -> None:
    """Scaffold a new Architecture Decision Record."""
    from irminsul.new.command import NewSpec

    repo_root, config = _load_repo(path)
    _write_new_doc(repo_root, config, NewSpec(kind="adr", title=title, extra={}), force=force)


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
            help=(
                "Test path to recommend for the component (repeatable, stored "
                "repo-relative under recommended_tests)."
            ),
        ),
    ] = None,
    from_surface: Annotated[
        bool,
        typer.Option(
            "--from-surface",
            help="Pre-fill a Surface section derived from the --describes paths.",
        ),
    ] = False,
    split_from: Annotated[
        list[str] | None,
        typer.Option(
            "--split-from",
            help="Doc id that owns --describes files today (repeatable); links the new doc to it.",
        ),
    ] = None,
    force: Annotated[bool, typer.Option("--force")] = False,
    path: PathOpt = Path("."),
) -> None:
    """Scaffold a new component doc."""
    from irminsul.new.command import (
        NewSpec,
        current_owners,
        normalize_claim_path,
        resolve_destination,
        resolve_id,
        split_links,
    )

    repo_root, config = _load_repo(path)
    from irminsul.checks.globs import external_display_for_path, resolve_display_path

    roots = config.paths.source_roots

    def claim(value: str) -> str:
        rel = normalize_claim_path(repo_root, value)
        external = external_display_for_path(repo_root, roots, repo_root / rel)
        return external if external is not None and rel.startswith("../") else rel

    describes_rel = [claim(value) for value in describes or []]
    tests_rel = [normalize_claim_path(repo_root, value) for value in tests or []]
    for rel in [*describes_rel, *tests_rel]:
        # describes/tests values may be glob patterns; a literal existence
        # check would false-warn on every wildcard.
        if (
            not (repo_root / rel).exists()
            and resolve_display_path(repo_root, roots, rel) is None
            and not glob.glob(str(repo_root / rel), recursive=True)
        ):
            typer.echo(typer.style(f"warning: path does not exist: {rel}", fg="yellow"))

    probe = NewSpec(kind="component", title=title, extra={})
    # Ahead of the two uses below, not only around `create`: an unnameable title reaches
    # `resolve_destination` here first and must be reported as a usage error, as `new adr`
    # reports it.
    resolve_destination(repo_root, probe, config)
    graph = build_graph(repo_root, config)
    owned = current_owners(graph, describes_rel)
    owned.pop(resolve_id(resolve_destination(repo_root, probe, config)), None)
    unnamed = {doc: files for doc, files in owned.items() if doc not in (split_from or [])}
    if unnamed:
        typer.echo(
            typer.style("refusing: these files are already described by another doc:", fg="red"),
            err=True,
        )
        for doc, files in unnamed.items():
            typer.echo(f"  {doc}: {', '.join(files)}")
        typer.echo(
            "Extend that doc instead, or split it: pass --split-from <doc-id>, then remove "
            "the files from its describes and its prose."
        )
        raise typer.Exit(code=1)
    split_refs = split_links(graph, repo_root, config, probe, split_from or [])

    surface_groups: list[dict[str, object]] = []
    if from_surface:
        if not describes_rel:
            raise UserError("--from-surface requires at least one --describes path")
        tree = graph.source
        doc_dir = resolve_destination(repo_root, probe, config).parent
        contributing: set[str] = set()
        for kind in ("cli", "http", "env-vars", "exports"):
            seen: set[str] = set()
            rows: list[dict[str, str]] = []
            for rel in describes_rel:
                for item in tree.surface(kind, (rel,)):
                    if item.identity in seen:
                        continue
                    seen.add(item.identity)
                    contributing.add(rel)
                    display = item.display or rel
                    target = resolve_display_path(repo_root, roots, display) or (
                        repo_root / display
                    )
                    rows.append(
                        {
                            "identity": item.identity,
                            "display": display,
                            "link": os.path.relpath(target, doc_dir).replace("\\", "/"),
                        }
                    )
            if rows:
                surface_groups.append({"kind": kind, "rows": rows})
        bare = [rel for rel in describes_rel if rel not in contributing]
        if bare:
            typer.echo(
                typer.style(
                    f"note: no derivable surface for: {', '.join(bare)} (a surface is the "
                    "commands, options, routes, exports or environment variables a file declares)",
                    fg="yellow",
                )
            )

    spec = NewSpec(
        kind="component",
        title=title,
        extra={
            "describes": describes_rel,
            "tests": tests_rel,
            "surface": surface_groups,
            "split_from": split_refs,
        },
    )
    _write_new_doc(repo_root, config, spec, force=force)
    for doc, files in owned.items():
        typer.echo(
            f"next: remove {', '.join(files)} from {doc}'s describes and prose; "
            "irminsul list review --changed lists its sentences that name them"
        )


@_new_app.command("rfc")
def new_rfc(
    title: Annotated[str, typer.Argument(help="Title of the RFC.")],
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite an existing file."),
    ] = False,
    small: Annotated[
        bool,
        typer.Option(
            "--small",
            help="Write the small shape: Summary and Decisions, read in 5 to 30 seconds.",
        ),
    ] = False,
    path: PathOpt = Path("."),
) -> None:
    """Scaffold a new RFC. Run `irminsul check` first to see what the tree fails on."""
    from irminsul.new.command import NewSpec

    repo_root, config = _load_repo(path)
    weight = "small" if small else "large"
    spec = NewSpec(kind="rfc", title=title, extra={"weight": weight})
    _write_new_doc(repo_root, config, spec, force=force)


_list_app = typer.Typer(name="list", help="List docs by condition.", no_args_is_help=True)
app.add_typer(_list_app)


@_list_app.command("baseline")
def list_baseline(
    fmt: FormatOpt = OutputFormat.plain,
    path: PathOpt = Path("."),
) -> None:
    """List baseline entries and whether each still hides a finding."""
    from irminsul.listing.command import list_baseline as _list_baseline

    repo_root, config = _load_repo(path)
    _list_baseline(repo_root, config, fmt=fmt)


@_list_app.command("undocumented")
def list_undocumented(
    fmt: FormatOpt = OutputFormat.plain,
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
    path: PathOpt = Path("."),
) -> None:
    """List source files in covered directories that no doc claims.

    With --all, list every unclaimed source file regardless of coverage.
    """
    from irminsul.listing.command import list_undocumented as _list_undocumented

    repo_root, config = _load_repo(path)
    _list_undocumented(repo_root, config, fmt=fmt, all_files=all_files)


@_list_app.command("lifecycle")
def list_lifecycle(
    fmt: FormatOpt = OutputFormat.plain,
    queue: Annotated[bool, typer.Option("--queue")] = False,
    path: PathOpt = Path("."),
) -> None:
    """List unfinished RFC lifecycle work."""
    from irminsul.listing.command import list_lifecycle as _list_lifecycle

    repo_root, config = _load_repo(path)
    _list_lifecycle(repo_root, config, fmt=fmt, queue=queue)


@_list_app.command("review")
def list_review(
    fmt: FormatOpt = OutputFormat.plain,
    doc: Annotated[
        str | None, typer.Option("--doc", help="Only this doc, by id or repo-relative path.")
    ] = None,
    show_all: Annotated[
        bool,
        typer.Option(
            "--all", help="Every sentence that names code, not only those whose code changed."
        ),
    ] = False,
    changed: Annotated[
        bool,
        typer.Option(
            "--changed",
            help="What a change asks to re-read: edited and deleted sentences in the working "
            "tree vs HEAD, and the claims, moved files and summaries it touched.",
        ),
    ] = False,
    base_ref: Annotated[
        str | None,
        typer.Option(
            "--base-ref",
            help="As --changed, for the changes since the merge base of this git ref and HEAD.",
        ),
    ] = None,
    committed_only: CommittedOnlyOpt = False,
    path: PathOpt = Path("."),
) -> None:
    """List the sentences to re-read, each with the code it names, selected by facts."""
    from irminsul.git.changes import changed_line_numbers, merge_base
    from irminsul.git.reader import GitReader
    from irminsul.listing.review import list_review as _list_review

    repo_root, config = _load_repo(path)

    git = GitReader()
    changed_lines = None
    since: str | None = None
    if base_ref is not None:
        since = merge_base(git, repo_root, base_ref, "HEAD") or base_ref
        changed_lines = changed_line_numbers(git, repo_root, since, committed_only=committed_only)
    elif changed and committed_only:
        typer.echo(
            "--committed-only without --base-ref ends the change where it starts, so no "
            "change is judged and nothing uncommitted is read",
            err=True,
        )
        changed_lines = {}
    elif changed:
        changed_lines = changed_line_numbers(git, repo_root)
    _list_review(
        repo_root,
        config,
        fmt=fmt,
        doc=doc,
        show_all=show_all,
        changed=changed_lines,
        base_ref=since or "HEAD",
        committed_only=committed_only,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
