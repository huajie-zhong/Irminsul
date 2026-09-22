"""Irminsul command-line entry point."""

from __future__ import annotations

import datetime as _dt
import difflib
import glob
import os
import sys
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from irminsul import __version__
from irminsul.checks import (
    REGISTRY,
    Check,
    Finding,
    FindingClass,
    Fix,
    Severity,
    finding_records,
    fix_commands,
    sort_findings,
    summarize,
)
from irminsul.config import ConfigError, IrminsulConfig, find_config, load
from irminsul.docgraph import DocGraph, build_graph
from irminsul.fix import FixResult
from irminsul.git.mtime import diff_name_only, has_history
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
    # Click expands `*` in arguments on Windows, turning a quoted glob such as
    # `--describes "src/**"` into a list of files.
    app(windows_expand_args=False)


def _load_config(repo_root: Path) -> IrminsulConfig:
    config_path = find_config(repo_root)
    if config_path.is_file() and config_path.parent.resolve() != repo_root.resolve():
        typer.echo(
            typer.style(
                f"{config_path.name} is in {config_path.parent}, not {repo_root}; run from "
                f"that directory or pass --path {config_path.parent}",
                fg="red",
            ),
            err=True,
        )
        raise typer.Exit(code=2)
    try:
        return load(config_path)
    except ConfigError as exc:
        typer.echo(typer.style(str(exc), fg="red"), err=True)
        raise typer.Exit(code=exc.code) from exc


def _require_plain_or_json(fmt: str) -> None:
    if fmt not in ("plain", "json"):
        typer.echo(
            typer.style(f"unknown --format '{fmt}'; expected plain or json", fg="red"), err=True
        )
        raise typer.Exit(code=2)


class Profile(StrEnum):
    enabled = "enabled"
    all_available = "all-available"


class ContextProfile(StrEnum):
    enabled = "enabled"
    all_available = "all-available"


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
    config = _load_config(target)
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
                "is first copied to <name>.irminsul-backup."
            ),
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
        typer.echo(
            typer.style(
                "`--code-repo` is only valid with `--topology siblings`.",
                fg="red",
            ),
            err=True,
        )
        raise typer.Exit(code=2)

    if topology == Topology.siblings:
        if fresh:
            typer.echo(
                typer.style(
                    "`--fresh` is not valid with `--topology siblings`. The sibling "
                    "code checkout is detected on disk, so the same command covers a "
                    "code repo that already exists and one that does not exist yet. "
                    "Run `irminsul init --topology siblings --code-repo <spec-or-path>`.",
                    fg="red",
                ),
                err=True,
            )
            raise typer.Exit(code=2)
        _init_siblings(
            target,
            interactive=interactive,
            code_repo=code_repo,
            languages=language,
            force=force,
        )
        _offer_seed_after_scaffold(target, interactive=interactive)
        return

    has_code = detect_code_signals(target)

    if fresh:
        if has_code and not allow_existing_code:
            typer.echo(
                typer.style(
                    "Code signals already exist in the target directory. "
                    "Use `irminsul init` to adopt existing same-repo code, or pass "
                    "`--allow-existing-code` with `--fresh` if this is intentional.",
                    fg="red",
                ),
                err=True,
            )
            raise typer.Exit(code=2)
        run_init_fresh(target, interactive=interactive, languages=language, force=force)
        _offer_seed_after_scaffold(target, interactive=interactive)
        return

    if interactive and not has_code:
        typer.echo("No code detected here. What are you setting up?")
        typer.echo("  [1] Fresh-start, same repo")
        typer.echo("  [2] Docs repo beside a separate code repo (siblings)")
        typer.echo("  [3] Cancel")
        answer = typer.prompt("Choose", default="1")
        if answer == "1":
            run_init_fresh(target, interactive=interactive, languages=language, force=force)
            _offer_seed_after_scaffold(target, interactive=interactive)
            return
        if answer == "2":
            _init_siblings(
                target,
                interactive=interactive,
                code_repo=code_repo,
                languages=language,
                force=force,
            )
            _offer_seed_after_scaffold(target, interactive=interactive)
            return
        typer.echo("Canceled.")
        raise typer.Exit(code=0)
    elif not interactive and not has_code:
        typer.echo(
            typer.style(
                "No code detected in the target directory.\n"
                "Use `irminsul init --fresh` to start a new project, or\n"
                "`irminsul init --topology siblings --code-repo <spec-or-path>` "
                "for a docs repo beside a separate code repo.",
                fg="red",
            ),
            err=True,
        )
        raise typer.Exit(code=2)

    run_init(target, interactive=interactive, languages=language, force=force)


def _init_siblings(
    target: Path,
    *,
    interactive: bool,
    code_repo: str | None,
    languages: list[str] | None,
    force: bool,
) -> None:
    """Guard the siblings scaffold against being run inside a code repo.

    The target of `--topology siblings` is the docs repo; code signals there
    mean the caller wanted the same-repo layout instead.
    """
    if detect_code_signals(target):
        if not interactive:
            typer.echo(
                typer.style(
                    "This directory contains code signals. The siblings layout "
                    "scaffolds a repo that holds only docs, beside the code repo; "
                    "for code and docs in one repo use `irminsul init` instead.",
                    fg="red",
                ),
                err=True,
            )
            raise typer.Exit(code=2)
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
    config = _load_config(repo_root)

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
    typer.echo(f"{location}  {severity_str}  [{finding.code}]  {finding.message}")
    if finding.suggestion:
        typer.echo(typer.style(f"      → {finding.suggestion}", dim=True))


def _findings_to_json(
    findings: list[Finding],
    counts: dict[Severity, int],
    commands: list[str | None],
    baseline: dict[str, object] | None = None,
    delta: dict[str, object] | None = None,
    adoption: dict[str, object] | None = None,
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
    if adoption is not None:
        payload["adoption"] = adoption
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
    # The code rides in `title=`: the Actions runner only recognizes
    # file/line/col/endLine/endColumn/title on issue commands and silently
    # drops unknown properties, so a dedicated `code=` property would never
    # reach the PR annotation.
    props.append("title=" + _escape_github_property(f"irminsul {finding.code}"))
    data = finding.message
    if finding.suggestion:
        data = f"{data} — {finding.suggestion}"
    return f"::{_GITHUB_COMMAND[finding.severity]} {','.join(props)}::{_escape_github_data(data)}"


def _adoption_status(
    repo_root: Path, config: IrminsulConfig, graph: DocGraph
) -> dict[str, object] | None:
    """The machine-readable half of the adoption note, or `None` with no record.

    A parser reading `summary.errors == 0` has to be able to tell full coverage from a
    run that excepted files, so `remaining` is stated rather than left to be inferred.

    `remaining` counts entries whose file still has no owner, not entries in the file.
    Retiring one needs `--update-adoption`, which nobody is obliged to run, so a live
    record is usually stale and the two numbers drift apart — and it was the entry count
    that got printed, which said "3 files have no owning doc" while `list undocumented`
    listed two. `entries` keeps the raw count for anyone who wants it.
    """
    from irminsul.adoption import (
        AdoptionError,
        load_record,
        missing_configured_roots,
        record_path,
    )

    path = record_path(repo_root, config)
    if not path.is_file():
        return None
    try:
        record = load_record(path)
    except AdoptionError as exc:
        return {"path": config.paths.adoption, "readable": False, "error": str(exc)}
    if absent := missing_configured_roots(repo_root, config):
        # The counts below are read off the managed walk, which cannot see these roots.
        # Publishing `remaining: 0` here said full coverage to every parser while the plain
        # formatter was saying the amount was unknown.
        return {
            "path": config.paths.adoption,
            "readable": True,
            "assessable": False,
            "absent_roots": absent,
            "entries": len(record.unowned),
            "recorded": sorted(record.unowned),
            "adopted_at": record.adopted_at,
            "sources": [
                {"source": source.source, "revision": source.revision} for source in record.sources
            ],
        }
    live = _live_adoption_debt(record.unowned, graph)
    return {
        "path": config.paths.adoption,
        "readable": True,
        "assessable": True,
        "remaining": len(live),
        "entries": len(record.unowned),
        "unowned": sorted(live),
        "recorded": sorted(record.unowned),
        "adopted_at": record.adopted_at,
        "sources": [
            {"source": source.source, "revision": source.revision} for source in record.sources
        ],
    }


def _live_adoption_debt(recorded: frozenset[str], graph: DocGraph) -> frozenset[str]:
    """Recorded entries whose file is still a managed file with no owner.

    An entry whose file gained an owner, or went away, excepts nothing; counting it as
    outstanding debt overstates what the run hid.
    """
    from irminsul.adoption import unowned_managed_files

    return recorded & frozenset(unowned_managed_files(graph))


def _print_adoption_note(repo_root: Path, config: IrminsulConfig, graph: DocGraph) -> None:
    """How much pre-existing ownership debt the run left unreported.

    Zero errors means nothing provable is broken, and while a record holds entries it
    does not mean every file has documentation. Saying so is the same duty the baseline
    line discharges: what a run hides, it names — and the number has to be what it says it
    is, which is files without an owner, not lines in a file nobody has tidied.
    """
    from irminsul.adoption import AdoptionError, load_record, record_path

    path = record_path(repo_root, config)
    if not path.is_file():
        return
    try:
        record = load_record(path)
    except AdoptionError:
        return
    from irminsul.adoption import missing_configured_roots

    if absent := missing_configured_roots(repo_root, config):
        # Every number below is read off the managed walk, and the walk cannot see these.
        # Saying "0 remaining" here is how a run whose gate already failed went on to
        # recommend `--update-adoption`, which empties the record.
        typer.echo(
            typer.style(
                f"adoption: {config.paths.adoption} names files under "
                + ", ".join(repr(root) for root in absent)
                + ", which are not on disk, so how much debt is left is unknown. Do not run "
                "`--update-adoption` until they are checked out.",
                fg="yellow",
            )
        )
        return
    remaining = len(_live_adoption_debt(record.unowned, graph))
    stale = len(record.unowned) - remaining
    if not remaining:
        if stale:
            typer.echo(
                typer.style(
                    f"adoption: every file {config.paths.adoption} names now has an owner. "
                    "Run `irminsul check --update-adoption` to retire the entries.",
                    fg="cyan",
                )
            )
        return
    tail = (
        f" {stale} further entr{'y names a file' if stale == 1 else 'ies name files'} that is "
        "now owned or gone; `check --update-adoption` retires them."
        if stale
        else ""
    )
    typer.echo(
        typer.style(
            f"adoption: {remaining} file(s) still have no owning doc and are excepted by "
            f"{config.paths.adoption}; `irminsul list undocumented --all` lists them.{tail}",
            fg="cyan",
        )
    )


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
            " run --update-baseline to remove them)"
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
    typer.echo(f"::warning title=irminsul baseline::{_escape_github_data(message)}")
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


def _check_names(profile: Profile, config: IrminsulConfig) -> list[str]:
    if profile == Profile.all_available:
        return list(REGISTRY)
    return list(config.checks.enabled)


def _whitespace_only(
    repo_root: Path, changed: frozenset[str], co_change_range: tuple[str, str]
) -> frozenset[str]:
    """The changed docs whose content differs from the base only in whitespace."""
    from irminsul.git.changes import GitChangesError, file_at_ref, merge_base

    base, head = co_change_range
    try:
        base = merge_base(repo_root, base, head) or base
    except GitChangesError:
        return frozenset()

    def words(text: str) -> str:
        return " ".join(text.split())

    out: set[str] = set()
    for path in changed:
        if not path.endswith(".md"):
            continue
        try:
            before = file_at_ref(repo_root, base, path)
            after = (
                (repo_root / path).read_text(encoding="utf-8")
                if head == "HEAD"
                else file_at_ref(repo_root, head, path)
            )
        except (GitChangesError, OSError, UnicodeDecodeError):
            continue
        if before is not None and after is not None and words(before) == words(after):
            out.add(path)
    return frozenset(out)


def _working_tree_dirty(repo_root: Path) -> bool:
    """Whether the working tree differs from HEAD, so `--delta` has something to compare."""
    from irminsul.git.changes import GitChangesError, working_tree_changed_paths

    try:
        return bool(working_tree_changed_paths(repo_root))
    except GitChangesError:
        # No usable git information: let the delta machinery report that itself.
        return True


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


def _pin_adoption_sources(repo_root: Path, config: IrminsulConfig) -> NoReturn:
    """`--pin-adoption-sources`, which records the cross-repo boundary and ends the run.

    A record written before this existed names files from another repository with nothing
    saying which revision of it they were history at, so nothing can confirm they were not
    added by the same change. This writes that revision.

    It only ever *adds* a pin. Moving one already recorded would walk the adoption boundary
    forward, and everything committed to the source repository since would become
    pre-existing debt — the growth move, wearing a maintenance command.
    """
    from irminsul.adoption import (
        AdoptionError,
        AdoptionSource,
        cross_repo_source_boundaries,
        load_record,
        migrate_record,
        pin_source_revisions,
        record_path,
        rewrite_sources,
    )

    path = record_path(repo_root, config)
    name = config.paths.adoption
    if not path.is_file():
        typer.echo(
            typer.style(
                f"no adoption record at {name}; create one with --init-adoption, which "
                "pins the boundary itself",
                fg="red",
            ),
            err=True,
        )
        raise typer.Exit(code=2)
    try:
        try:
            record = load_record(path)
        except AdoptionError as stale:
            # The one shape this command converts rather than refuses: a record written
            # before entries and pins named their source. Explicit, reviewable, and it moves
            # nothing — the revisions are copied across and the entries are the same entries.
            if "`name` and `revision`" not in str(stale):
                raise
            for line in migrate_record(repo_root, config, path):
                typer.echo(typer.style(line, fg="green"))
            typer.echo(
                typer.style(
                    f"migrated {name} to name its sources. Nothing moved: every pin keeps its "
                    "revision and every entry its path. Review the diff.",
                    fg="green",
                )
            )
            record = load_record(path)
        boundaries = cross_repo_source_boundaries(repo_root, config)
        if not boundaries:
            typer.echo(
                typer.style(
                    "no source root belongs to another git repository, so there is no "
                    f"cross-repository boundary to pin. {name} is unchanged; entries inside "
                    "this repository are verified against the diff's own merge base.",
                    fg="cyan",
                )
            )
            raise typer.Exit(code=0)
        already = {source.source: source.revision for source in record.sources}
        from irminsul.source_map import build_source_map

        resolution = build_source_map(repo_root, config, record)
        contributing = {
            binding.source
            for display in record.unowned
            if (binding := resolution.binding(display)).source is not None
        }
        fresh = {
            source.source: source.revision
            for source in pin_source_revisions(repo_root, config)
            if source.source in contributing
        }
        # Seeded from what is already pinned, not from what is configured now. Building it
        # from `fresh` alone silently dropped the pin of a root the config had since moved
        # or renamed — and a record that loses a pin is what this branch's own
        # `diff-integrity/adoption-source-rebound` calls a weakening, so the repair command
        # produced a state the gate rejects.
        merged = {**already, **{name: rev for name, rev in fresh.items() if name not in already}}
        kept = [AdoptionSource(source=name, revision=merged[name]) for name in sorted(merged)]
        unchanged = [root for root in sorted(fresh) if root in already]
        added = [root for root in sorted(fresh) if root not in already]
        orphaned = [root for root in sorted(already) if root not in fresh]
        if not added:
            # The orphan note first, because it is the one thing the operator cannot see for
            # themselves and the reason there was nothing to add. Exiting quietly here told
            # somebody whose pinned source had lost its configured root that everything was
            # already pinned, which is true and is not the useful half.
            for stranded in orphaned:
                typer.echo(
                    typer.style(
                        f"  source '{stranded}' is pinned at {already[stranded][:12]} but no "
                        "longer has a configured root; the pin is kept, because dropping one "
                        "is a weakening the gate reports. Remove it by hand once its entries "
                        "are gone.",
                        fg="yellow",
                    )
                )
            typer.echo(
                typer.style(
                    f"every source that contributes an entry to {name} is already pinned; a "
                    "pin does not move, so nothing was written",
                    fg="cyan",
                )
            )
            raise typer.Exit(code=0)
        # Replaced in place. Unlinking first and calling `init_adoption` — which refuses to
        # overwrite — left a window where a failed write meant no record at all, and nothing
        # rebuilds one.
        rewrite_sources(path, record, kept)
    except AdoptionError as e:
        typer.echo(typer.style(str(e), fg="red"), err=True)
        raise typer.Exit(code=2) from None
    for root in added:
        typer.echo(
            typer.style(
                f"adoption boundary: pinned '{root}' at {fresh[root][:12]}",
                fg="green",
            )
        )
    for root in unchanged:
        typer.echo(f"  '{root}' was already pinned at {already[root][:12]}; left alone")
    for root in orphaned:
        typer.echo(
            typer.style(
                f"  source '{root}' is pinned at {already[root][:12]} but no longer has a "
                "configured root; the pin is kept, because dropping one is a weakening the "
                "gate reports. Remove it by hand once its entries are gone.",
                fg="yellow",
            )
        )
    typer.echo(
        typer.style(
            "Check that revision is the one this repository adopted at. It is what decides "
            "which files count as pre-existing debt, and a later one would adopt whatever "
            "landed in between.",
            fg="yellow",
        )
    )
    raise typer.Exit(code=0)


def _adoption_command(
    repo_root: Path, config: IrminsulConfig, graph: DocGraph, *, create: bool
) -> NoReturn:
    """`--init-adoption` and `--update-adoption`, which both end the run.

    Neither reads the findings. The record's whole purpose is to name the files whose
    ownership findings do not exist yet — on the day of adoption the covered-directory
    rule is silent, so a record built from findings would be empty and would except
    nothing. It is built from the configured walk instead.
    """
    from irminsul.adoption import (
        AdoptionError,
        init_adoption,
        missing_configured_roots,
        pin_source_revisions,
        record_path,
        shrink_adoption,
        unowned_managed_files,
        unpinnable_entries,
    )

    path = record_path(repo_root, config)
    if absent := missing_configured_roots(repo_root, config):
        # The walk cannot see these, so "has no owner" has no answer for anything under
        # them. `--update-adoption` would read that silence as work completed and retire
        # every entry it covers; `--init-adoption` would record a tree it cannot see.
        listed = ", ".join(repr(root) for root in absent)
        typer.echo(
            typer.style(
                f"configured root(s) {listed} are not on disk, so which managed files have "
                "no owner cannot be determined. Refusing rather than reading an absent tree "
                "as a documented one — that would empty the record. Check the source "
                "repository out where `paths.source_roots` says it is.",
                fg="red",
            ),
            err=True,
        )
        raise typer.Exit(code=2)
    unowned = unowned_managed_files(graph)
    name = config.paths.adoption
    try:
        if create:
            head = _head_sha(repo_root)
            # A source root in another repository has a history of its own, and this
            # repository's merge base says nothing about it. The revision that root is at
            # now is the boundary its entries are history at, and it goes in the record so
            # every later run can ask that repository the same question.
            # Only the sources some entry is bound to. A pin grants nothing on its own, and
            # `--update-adoption` preserves every pin it finds, so recording one for a source
            # whose files are all documented coupled an unrelated repository to this record
            # permanently — the pin could not be removed either, because dropping one is a
            # weakening the seal reports.
            contributing = {
                binding.source
                for display in unowned
                if (binding := graph.source_map.binding(display)).source is not None
            }
            sources = [
                source
                for source in pin_source_revisions(repo_root, config)
                if source.source in contributing
            ]
            if stranded := unpinnable_entries(repo_root, config, unowned, sources):
                listed = ", ".join(repr(item) for item in stranded[:5])
                more = f" and {len(stranded) - 5} more" if len(stranded) > 5 else ""
                typer.echo(
                    typer.style(
                        f"{len(stranded)} managed file(s) are not in the revision being "
                        f"pinned: {listed}{more}. The walk reads the source working tree and "
                        "the boundary is its committed HEAD, so these are uncommitted — "
                        "recording them would write a record the next run disproves. Commit "
                        "the source repository first.",
                        fg="red",
                    ),
                    err=True,
                )
                raise typer.Exit(code=2)
            # Each entry from another repository states the source it came from, so no later
            # configuration edit can re-derive a different one for it.
            smap = graph.source_map
            bindings = {
                display: binding.source
                for display in unowned
                if (binding := smap.binding(display)).source is not None
            }
            count = init_adoption(path, unowned, head, sources, bindings)
            typer.echo(
                typer.style(
                    f"adoption: recorded {count} file(s) with no owning doc in {name}. "
                    "Every check runs from now on; these files alone are excepted from "
                    "the ownership finding, and each exception retires the moment its "
                    "file gains an owner.",
                    fg="green",
                )
            )
            for source in sources:
                typer.echo(
                    typer.style(
                        f"  adoption boundary: source '{source.source}' is history at "
                        f"{source.revision[:12]} in its own repository",
                        fg="cyan",
                    )
                )
            raise typer.Exit(code=0)
        result = shrink_adoption(path, set(unowned))
    except AdoptionError as e:
        typer.echo(typer.style(str(e), fg="red"), err=True)
        raise typer.Exit(code=2) from None
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
    raise typer.Exit(code=0)


def _head_sha(repo_root: Path) -> str | None:
    from irminsul.git.mtime import _git_text

    # A repository with no commit yet still adopts; the record simply records no origin.
    return (_git_text(repo_root, "rev-parse", "HEAD") or "").strip() or None


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


def _run_configured_checks(
    profile: Profile,
    config: IrminsulConfig,
    graph: DocGraph,
    *,
    diff: bool = False,
) -> list[Finding]:
    """Findings for one profile/graph pair, the unit `--delta` runs twice: once for the
    working tree and once for the base-rev checkout."""
    from irminsul.checks.pipeline import finish

    names = _check_names(profile, config)
    findings: list[Finding] = []
    for check_name in names:
        cls = REGISTRY.get(check_name)
        if cls is None:
            # Config validation rejects names outside config.py's known-check tuples, which
            # mirror this registry. Reaching this is a codebase bug, so fail loudly.
            raise AssertionError(
                f"check '{check_name}' passed config validation but has no registered Check "
                "class; config.py's known checks and checks/__init__.py's registry disagree"
            )
        findings.extend(cls().run(graph))
    return finish(findings, graph, ran=names, diff=diff)


@app.command()
def check(
    profile: Annotated[
        Profile,
        typer.Option("--profile", help="Checks to run: enabled (checks.enabled) or all-available."),
    ] = Profile.enabled,
    strict: Annotated[
        bool,
        typer.Option(
            "--strict",
            help="Fail on hint and time findings too. Certain findings always fail.",
        ),
    ] = False,
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
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format: plain, json, or github."),
    ] = "plain",
    diff: Annotated[
        str | None,
        typer.Option(
            "--diff",
            help=(
                "Base git ref for the diff passes: co-change warns when source files "
                "changed in <base>...HEAD without their owning docs, and diff-integrity "
                "fails a change that weakens the gate. Time findings are left out."
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
    init_baseline: Annotated[
        bool,
        typer.Option(
            "--init-baseline",
            help=(
                "Create the baseline file from the current certain findings and exit 0. "
                "Refuses when a baseline already exists."
            ),
        ),
    ] = False,
    update_baseline: Annotated[
        bool,
        typer.Option(
            "--update-baseline",
            help=(
                "Remove baseline entries that no longer match and exit 0. Exits 1 without "
                "writing when a certain finding the baseline does not record is present."
            ),
        ),
    ] = False,
    no_baseline: Annotated[
        bool,
        typer.Option("--no-baseline", help="Ignore an existing baseline file for this run."),
    ] = False,
    init_adoption: Annotated[
        bool,
        typer.Option(
            "--init-adoption",
            help=(
                "Adopt Irminsul in an existing repository: record every managed file that "
                "has no owning doc today, so those files alone are excepted from the "
                "ownership finding while every other check runs normally. Refuses when a "
                "record already exists."
            ),
        ),
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
                "Needs --diff or --base-ref/--head-ref as well; the source range is a second "
                "axis, not a replacement."
            ),
        ),
    ] = None,
    pin_adoption_sources: Annotated[
        bool,
        typer.Option(
            "--pin-adoption-sources",
            help=(
                "Record the revision each cross-repository source root is at now, as the "
                "boundary its adoption entries are history at, and exit 0. For a record "
                "written before the boundary was recorded; it refuses to move a pin that "
                "already exists."
            ),
        ),
    ] = False,
    update_adoption: Annotated[
        bool,
        typer.Option(
            "--update-adoption",
            help=(
                "Retire adoption-record entries whose file is now owned, deleted or moved, "
                "and exit 0. Exits 1 without writing when a managed file has no owner and "
                "no entry, since the record only shrinks."
            ),
        ),
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
            typer.style(f"unknown --format '{fmt}'; expected plain, json, or github", fg="red"),
            err=True,
        )
        raise typer.Exit(code=2)

    if (base_ref is None) != (head_ref is None):
        typer.echo(
            typer.style("--base-ref and --head-ref must be provided together", fg="red"), err=True
        )
        raise typer.Exit(code=2)

    if source_diff and diff is None and base_ref is None:
        typer.echo(
            typer.style(
                "--source-diff names a base in the source repository and needs a base in "
                "this one too: pass --diff <ref> (or --base-ref/--head-ref). On a "
                "source-repository pull request the docs checkout sits on its default "
                "branch, so `--diff origin/<default>` is an empty docs range and the source "
                "range is what the run judges.",
                fg="red",
            ),
            err=True,
        )
        raise typer.Exit(code=2)

    failing = _failing_classes(fail_on, strict)

    if delta_base is not None:
        delta = True

    exclusive = [
        flag
        for flag, given in (
            ("--init-baseline", init_baseline),
            ("--update-baseline", update_baseline),
            ("--no-baseline", no_baseline),
            ("--delta", delta),
            ("--init-adoption", init_adoption),
            ("--update-adoption", update_adoption),
            ("--pin-adoption-sources", pin_adoption_sources),
        )
        if given
    ]
    if len(exclusive) > 1:
        typer.echo(
            typer.style(f"{' and '.join(exclusive)} are mutually exclusive", fg="red"), err=True
        )
        raise typer.Exit(code=2)

    now_date: _dt.date | None = None
    if now is not None:
        try:
            now_date = _dt.date.fromisoformat(now)
        except ValueError:
            typer.echo(
                typer.style(f"unknown --now '{now}'; expected YYYY-MM-DD", fg="red"), err=True
            )
            raise typer.Exit(code=2) from None

    repo_root = path.resolve()
    config = _load_config(repo_root)

    if diff is not None and base_ref is not None:
        typer.echo(
            typer.style("--diff and --base-ref/--head-ref are mutually exclusive", fg="red"),
            err=True,
        )
        raise typer.Exit(code=2)

    for flag, value in (("--diff", diff), ("--base-ref", base_ref), ("--head-ref", head_ref)):
        if value is not None and not value.strip():
            typer.echo(
                typer.style(
                    f"{flag} was given an empty value; pass a git ref or omit the flag",
                    fg="red",
                ),
                err=True,
            )
            raise typer.Exit(code=2)

    co_change_paths: frozenset[str] | None = None
    co_change_range: tuple[str, str] | None = None
    degraded: str | None = None
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
                typer.echo(typer.style(reason, fg="red"), err=True)
                raise typer.Exit(code=2)
            typer.echo(
                typer.style(f"{reason}; skipping diff-aware checks", fg="yellow"),
                err=True,
            )
            degraded = reason

    graph = build_graph(repo_root, config, now=now_date, diff_changed_paths=co_change_paths)

    if pin_adoption_sources:
        _pin_adoption_sources(repo_root, config)
    if init_adoption or update_adoption:
        _adoption_command(repo_root, config, graph, create=init_adoption)

    source_changed: frozenset[str] = frozenset()
    if source_diff:
        from irminsul.adoption import source_changed_displays

        source_refs = _source_diff_refs(source_diff, config)
        source_changed, unreadable_roots = source_changed_displays(repo_root, config, source_refs)
        if unreadable_roots:
            typer.echo(
                typer.style(
                    "could not read a source change set for "
                    + ", ".join(repr(root) for root in unreadable_roots)
                    + ". A gate that reads an empty change set passes "
                    "everything, so this exits rather than reporting a clean run; check the "
                    "checkout has that ref and full history.",
                    fg="red",
                ),
                err=True,
            )
            raise typer.Exit(code=2)

    diff_given = co_change_paths is not None and co_change_range is not None
    findings = _run_configured_checks(profile, config, graph, diff=diff_given)

    from irminsul.checks.history_depth import diff_unavailable
    from irminsul.checks.pipeline import finish, mandatory_findings

    selected = _check_names(profile, config)
    # The passes that judge the run rather than the graph, named in one place so every
    # command that runs checks runs the same set. `diff_unavailable` is not one of them: it
    # reports on this invocation's flags, which only this command has.
    run_findings = mandatory_findings(graph, selected)
    if degraded is not None:
        run_findings.append(diff_unavailable(degraded))
    findings.extend(finish(run_findings, graph, diff=diff_given))

    if co_change_paths is not None and co_change_range is not None:
        from irminsul.checks.co_change import run_co_change
        from irminsul.checks.diff_integrity import run_diff_integrity
        from irminsul.checks.new_dependency import run_new_dependency
        from irminsul.checks.pipeline import finish

        diff_findings = [
            *run_co_change(
                graph,
                co_change_paths,
                _whitespace_only(repo_root, co_change_paths, co_change_range),
            ),
            *run_diff_integrity(graph, co_change_paths, *co_change_range, source_changed),
            *run_new_dependency(graph, co_change_range[0], co_change_paths),
        ]
        findings.extend(finish(diff_findings, graph, diff=True))

    findings = sort_findings(findings)

    baseline_status: dict[str, object] = {
        "applied": False,
        "path": None,
        "suppressed": 0,
        "stale": 0,
        "hidden": [],
    }
    hidden: list[Finding] = []
    delta_status: dict[str, object] | None = None

    if delta:
        from irminsul.delta import (
            DeltaError,
            base_is_the_working_tree,
            compute_delta,
            pristine_checkout,
            verify_single_repo_topology,
        )

        delta_base_rev = delta_base or "HEAD"
        # The topology refusal comes first: it says this repository shape cannot be
        # compared at all, which outranks having nothing to compare in this run.
        try:
            verify_single_repo_topology(repo_root, config)
        except DeltaError as e:
            typer.echo(typer.style(str(e), fg="red"), err=True)
            raise typer.Exit(code=2) from None
        if base_is_the_working_tree(repo_root, config, delta_base_rev):
            # Against an unchanged tree every finding is "pre-existing", so the run
            # suppresses all of them and exits 0 while checking nothing. That is a
            # meaningless invocation, not a passing one.
            typer.echo(
                typer.style(
                    f"the working tree is identical to {delta_base_rev}, so --delta has "
                    "nothing to compare; run `irminsul check`, or pass an earlier "
                    "--delta-base <rev>",
                    fg="red",
                ),
                err=True,
            )
            raise typer.Exit(code=2)
        try:
            with pristine_checkout(repo_root, delta_base_rev) as base_root:
                base_graph = build_graph(
                    base_root,
                    config,
                    now=now_date,
                    diff_changed_paths=co_change_paths,
                    # The scratch worktree is deleted on teardown; persistent
                    # check state (the external-links cache) belongs in the
                    # user's real repo, shared with the working-tree pass.
                    state_root=repo_root,
                )
                base_findings = _run_configured_checks(profile, config, base_graph, diff=diff_given)
        except DeltaError as e:
            typer.echo(typer.style(str(e), fg="red"), err=True)
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
            shrink_baseline,
        )
        from irminsul.baseline import (
            init_baseline as create_baseline,
        )

        baseline_file = repo_root / config.paths.baseline
        if init_baseline:
            try:
                count = create_baseline(baseline_file, findings)
            except BaselineError as e:
                typer.echo(typer.style(str(e), fg="red"), err=True)
                raise typer.Exit(code=2) from None
            typer.echo(
                typer.style(
                    f"baseline: recorded {count} certain finding(s) in {config.paths.baseline}",
                    fg="green",
                )
            )
            raise typer.Exit(code=0)
        if update_baseline:
            try:
                result = shrink_baseline(baseline_file, findings)
            except BaselineError as e:
                typer.echo(typer.style(str(e), fg="red"), err=True)
                raise typer.Exit(code=2) from None
            if result.new:
                for finding in result.new:
                    _print_finding(finding)
                typer.echo(
                    typer.style(
                        f"baseline: {len(result.new)} certain finding(s) are not in "
                        f"{config.paths.baseline}; a baseline only shrinks, so fix them",
                        fg="red",
                    ),
                    err=True,
                )
                raise typer.Exit(code=1)
            typer.echo(
                typer.style(
                    f"baseline: removed {result.removed} fixed entr"
                    f"{'y' if result.removed == 1 else 'ies'}, {result.kept} remain",
                    fg="green",
                )
            )
            raise typer.Exit(code=0)

        if not no_baseline and baseline_file.is_file():
            try:
                fingerprints = load_baseline(baseline_file)
            except BaselineError as e:
                typer.echo(typer.style(str(e), fg="red"), err=True)
                raise typer.Exit(code=2) from None
            application = apply_baseline(findings, fingerprints)
            findings = application.remaining
            hidden = application.hidden
            baseline_status = {
                "applied": True,
                "path": config.paths.baseline,
                "suppressed": application.suppressed,
                "stale": application.stale,
                "hidden": [
                    {
                        "check": f.check,
                        "code": f.code,
                        "path": f.path.as_posix() if f.path else None,
                        "message": f.message,
                    }
                    for f in hidden
                ],
            }

    counts = summarize(findings)
    fail = any(_class_name(finding) in failing for finding in findings)

    if fmt == "json":
        typer.echo(
            _findings_to_json(
                findings,
                counts,
                fix_commands(findings, graph, profile=profile.value),
                baseline=baseline_status,
                delta=delta_status,
                adoption=_adoption_status(repo_root, config, graph),
            )
        )
    elif fmt == "github":
        for finding in findings:
            typer.echo(_github_annotation(finding))
        _report_hidden_to_github(baseline_status, hidden)
        _print_run_notes(baseline_status, delta_status)
        _print_adoption_note(repo_root, config, graph)
        _print_summary(counts)
    else:
        for finding in findings:
            _print_finding(finding)
        _print_run_notes(baseline_status, delta_status)
        _print_adoption_note(repo_root, config, graph)
        _print_summary(counts)

    raise typer.Exit(code=1 if fail else 0)


def _failing_classes(fail_on: str | None, strict: bool) -> set[str]:
    if fail_on is None:
        return {"certain", "hint", "time"} if strict else {"certain"}
    if strict:
        typer.echo(typer.style("--strict and --fail-on are mutually exclusive", fg="red"), err=True)
        raise typer.Exit(code=2)
    chosen = {value.strip() for value in fail_on.split(",") if value.strip()}
    unknown = sorted(chosen - {"certain", "hint", "time"})
    if unknown or not chosen:
        typer.echo(
            typer.style(
                f"unknown --fail-on '{fail_on}'; expected a comma-separated list of "
                "certain, hint, time",
                fg="red",
            ),
            err=True,
        )
        raise typer.Exit(code=2)
    # Certain findings prove the tree breaks a rule, so no invocation can stop them
    # failing the run; --fail-on widens the set and never narrows it.
    return chosen | {"certain"}


def _class_name(finding: Finding) -> str | None:
    """The class a reported finding fails as: its effective class, which the draft
    exemption can pull below the class its code declares."""
    from irminsul.checks.pipeline import effective_class

    finding_class = effective_class(finding)
    return finding_class.value if finding_class is not None else None


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

    _require_plain_or_json(fmt)

    repo_root = path.resolve()
    config = _load_config(repo_root)
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
    base_ref: Annotated[
        str | None,
        typer.Option(
            "--base-ref",
            help=(
                "Branch point --after-edit measures this change against, such as "
                "origin/main. Without it the working tree is compared with HEAD, which "
                "says nothing about work this branch already committed."
            ),
        ),
    ] = None,
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
    profile: Annotated[
        ContextProfile | None,
        typer.Option(
            "--profile",
            help="Finding breadth: enabled or all-available.",
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

    _require_plain_or_json(fmt)

    repo_root = path.resolve()
    config = _load_config(repo_root)
    requested_targets = list(targets or [])

    if before_edit and after_edit:
        typer.echo(
            typer.style("--before-edit and --after-edit cannot be combined", fg="red"), err=True
        )
        raise typer.Exit(code=2)

    workflow: WorkflowStage | None = None
    target_path = None
    target_paths = None
    effective_changed = changed
    if before_edit:
        if topic is not None or changed:
            typer.echo(
                typer.style("--before-edit cannot be combined with --topic or --changed", fg="red"),
                err=True,
            )
            raise typer.Exit(code=2)
        if not requested_targets:
            typer.echo(typer.style("--before-edit requires one or more paths", fg="red"), err=True)
            raise typer.Exit(code=2)
        workflow = "before-edit"
        target_paths = requested_targets
    elif after_edit:
        if requested_targets or topic is not None or changed:
            typer.echo(
                typer.style(
                    "--after-edit cannot be combined with paths, --topic, or --changed",
                    fg="red",
                ),
                err=True,
            )
            raise typer.Exit(code=2)
        workflow = "after-edit"
        effective_changed = True
    else:
        if len(requested_targets) > 1:
            typer.echo(
                typer.style("multiple paths require the --before-edit workflow", fg="red"), err=True
            )
            raise typer.Exit(code=2)
        target_path = requested_targets[0] if requested_targets else None

    effective_profile: ContextProfileValue = (
        profile.value if profile is not None else ContextProfile.enabled.value
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
            base_ref=base_ref,
        )
    except ContextError as exc:
        typer.echo(typer.style(str(exc), fg="red"), err=True)
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

    _require_plain_or_json(fmt)

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

    _require_plain_or_json(fmt)
    if (target is None) == (symbol is None):
        typer.echo(
            typer.style("choose exactly one input: <doc-id|path> or --symbol <name>", fg="red"),
            err=True,
        )
        raise typer.Exit(code=2)

    repo_root = path.resolve()
    config = _load_config(repo_root)
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
        typer.echo(typer.style(str(exc), fg="red"), err=True)
        raise typer.Exit(code=exc.code) from exc


def _fix_result_to_json(result: FixResult, *, dry_run: bool, notes: list[str] | None = None) -> str:
    """The versioned JSON shape of a fix run.

    `written` is empty on a dry run by construction; `planned` is what the run
    would attempt. `notes` carries what the plain output says about a run that
    harvested nothing — an inactive `--check` name, or no fixable findings —
    so an all-empty envelope cannot be mistaken for a resolved finding.
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


def _check_summary(cls: type[Check]) -> str:
    """First line of the check class's docstring, falling back to its module's.

    The fallback alone is not enough: several checks share one module (e.g.
    `doc_reality.py` hosts four), and the module docstring would describe them
    all with the same generic line.
    """
    doc: str | None = cls.__doc__
    if not doc:
        module = sys.modules.get(cls.__module__)
        doc = getattr(module, "__doc__", None) if module else None
    if not doc:
        return ""
    return doc.strip().splitlines()[0]


_CLASS_BLURB: dict[FindingClass, str] = {
    # "fails every run" was wrong: a baseline, `--delta`, and a draft doc's own
    # `drafts_exempt` codes each demote a certain finding, and 23 codes are exempt.
    FindingClass.certain: (
        "the tree provably breaks a rule; an error unless a baseline or --delta "
        "filters it out, or it reports a draft doc as unfinished — in which case it "
        "enforces as a hint"
    ),
    # "fails under --strict or --fail-on" was wrong for the codes reported at info
    # severity: no flag reaches those, so a run cannot be made to fail on one.
    FindingClass.hint: (
        "needs judgment; a warning fails under --strict or --fail-on hint, while a "
        "hint reported at info severity never fails a run"
    ),
    FindingClass.time: "caused by elapsed time; left out of a run given --diff",
}


def _explainable_checks() -> dict[str, type[Check]]:
    """Every check whose codes the CLI can print.

    From `_all_checks`, the one place that knows the registry plus the passes the CLI
    calls directly, so a new unregistered check is explainable without being added to
    a second list here.
    """
    from irminsul.checks.pipeline import _all_checks

    return {cls.name: cls for cls in _all_checks()}


def _list_all_codes() -> None:
    for check_name, cls in sorted(_explainable_checks().items()):
        if not cls.explanations:
            continue
        typer.echo(typer.style(f"[{check_name}]", fg="cyan", bold=True))
        for known_code in sorted(cls.explanations):
            typer.echo(f"  {known_code}")


@app.command("explain")
def explain_command(
    code: Annotated[
        str | None,
        typer.Argument(help="Finding code to explain, e.g. links/broken-link."),
    ] = None,
) -> None:
    """Explain a finding code: what it means and how to fix it.

    With no code, or an unknown code, lists every known code grouped by check.
    """
    if code is not None:
        for check_name, cls in sorted(_explainable_checks().items()):
            explanation = cls.explanations.get(code)
            if explanation is None:
                continue
            from irminsul.checks.pipeline import class_of

            typer.echo(typer.style(code, fg="cyan", bold=True))
            summary = _check_summary(cls)
            typer.echo(f"check: {check_name}" + (f" — {summary}" if summary else ""))
            finding_class = class_of(code)
            if finding_class is not None:
                typer.echo(f"class: {finding_class.value} — {_CLASS_BLURB[finding_class]}")
            typer.echo()
            typer.echo(explanation)
            return
        typer.echo(typer.style(f"unknown code '{code}'", fg="red"), err=True)
        typer.echo()
        _list_all_codes()
        raise typer.Exit(code=1)

    _list_all_codes()


@app.command()
def fix(
    profile: Annotated[
        Profile,
        typer.Option("--profile", help="Checks to fix: enabled or all-available."),
    ] = Profile.enabled,
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
    fmt: Annotated[str, typer.Option("--format", help="Output format: plain or json.")] = "plain",
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

    _require_plain_or_json(fmt)

    repo_root = path.resolve()
    config = _load_config(repo_root)
    graph = build_graph(repo_root, config)

    fixes: list[Fix] = []

    selected: list[tuple[str, dict[str, type[Check]]]] = [
        (name, REGISTRY) for name in _check_names(profile, config)
    ]
    if check_name is not None:
        # An unknown name must fail here; otherwise it would get the same "not active
        # under profile" note as a real check outside the profile.
        known = sorted(REGISTRY)
        if check_name not in known:
            match = difflib.get_close_matches(check_name, known, n=1)
            hint = f" (did you mean '{match[0]}'?)" if match else ""
            typer.echo(typer.style(f"unknown check '{check_name}'{hint}", fg="red"), err=True)
            raise typer.Exit(code=2)
        selected = [(name, registry) for name, registry in selected if name == check_name]
        if not selected:
            note = f"check '{check_name}' is not active under profile '{profile.value}'"
            if fmt == "json":
                typer.echo(_fix_result_to_json(FixResult(), dry_run=dry_run, notes=[note]))
            else:
                typer.echo(note)
            raise typer.Exit(code=0)
    for name, registry in selected:
        cls = registry.get(name)
        if cls is None:
            continue
        from irminsul.checks.pipeline import finish

        check = cls()
        check_findings = finish(check.run(graph), graph)
        maybe_fixes = getattr(check, "fixes", None)
        if maybe_fixes is not None:
            fixes.extend(maybe_fixes(check_findings, graph))

    if not fixes:
        note = "no automatic fixes available"
        if fmt == "json":
            typer.echo(_fix_result_to_json(FixResult(), dry_run=dry_run, notes=[note]))
        else:
            typer.echo(note)
        raise typer.Exit(code=0)

    result = apply_fixes(repo_root, fixes, dry_run=dry_run, confirm=confirm)

    if fmt == "json":
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
        typer.Argument(help=f"Surface kind: {KNOWN_KINDS_TEXT} (or a configured generic kind)."),
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

    _require_plain_or_json(fmt)
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
            help="Rewrite anchor hashes to the current code (acknowledge after re-reading).",
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
        typer.Option("--doc", help="Only this repo-relative doc, for --suggest or --re-pin."),
    ] = None,
    every: Annotated[
        bool,
        typer.Option("--all", help="With --re-pin, re-pin every doc rather than one."),
    ] = False,
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format for the report: plain or json."),
    ] = "plain",
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """Report or re-pin anchored prose claims, or suggest anchors for unbound code names.

    Re-pinning is a deliberate acknowledgement that you re-read the prose and it is
    still true; it is never done automatically by `irminsul fix`.
    """
    from irminsul.anchors import repin_text
    from irminsul.checks.claim_anchor import ClaimAnchorCheck

    _require_plain_or_json(fmt)
    if re_pin and suggest:
        typer.echo(typer.style("--re-pin and --suggest are mutually exclusive", fg="red"), err=True)
        raise typer.Exit(code=2)

    repo_root, config = _load_repo(path)
    graph = build_graph(repo_root, config)

    if suggest:
        _suggest_anchors(repo_root, config, graph, doc=doc, fmt=fmt)
        return

    if re_pin:
        from irminsul.checks.globs import walk_configured_source_files
        from irminsul.inventory.fingerprint import repin_node

        # Re-pinning asserts "I re-read this prose and it is still true", which nobody
        # can honestly say about a whole repository at once, so the sweep is opt-in.
        if doc is None and not every:
            typer.echo(
                typer.style(
                    "--re-pin rewrites the drift signal you are meant to answer; name the "
                    "doc you re-read with --doc <path>, or pass --all to re-pin every doc",
                    fg="red",
                ),
                err=True,
            )
            raise typer.Exit(code=2)
        wanted = doc.replace("\\", "/") if doc is not None else None
        if wanted is not None and not any(
            node.path.as_posix() == wanted for node in graph.nodes.values()
        ):
            # A --doc that matches nothing re-pinned nothing and exited 0, which reads
            # as success and defeats the refusal above: the flag exists to make you name
            # the doc you re-read, and a typo answered for you.
            typer.echo(
                typer.style(f"--doc: no doc at {wanted}", fg="red"),
                err=True,
            )
            raise typer.Exit(code=2)
        source_files = walk_configured_source_files(repo_root, config).files
        anchors_written = 0
        surfaces_written = 0
        repin_errors: list[str] = []
        for node in graph.nodes.values():
            if wanted is not None and node.path.as_posix() != wanted:
                continue
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
                # Through a temp file, as `fix` and `seed` write: a plain `write_text`
                # truncates before it writes, and `--re-pin --all` opens that window
                # once per doc. A failed write is collected rather than raised, so the
                # sweep finishes and names every doc it could not re-pin.
                try:
                    tmp_path = abs_path.with_name(f"{abs_path.name}.tmp")
                    tmp_path.write_text(text, encoding="utf-8", newline="\n")
                    os.replace(tmp_path, abs_path)
                except OSError as exc:
                    repin_errors.append(f"{node.path.as_posix()}: {type(exc).__name__}: {exc}")
                    continue
            anchors_written += anchor_changed
            surfaces_written += surface_changed
        typer.echo(
            typer.style(
                f"re-pinned {anchors_written} anchor(s), {surfaces_written} surface fingerprint(s)",
                fg="green",
            )
        )
        for failure in repin_errors:
            typer.echo(typer.style(f"could not re-pin {failure}", fg="red"), err=True)
        raise typer.Exit(code=2 if repin_errors else 0)

    findings = sort_findings(ClaimAnchorCheck().run(graph))
    if fmt == "json":
        commands = fix_commands(findings, graph, profile=Profile.all_available.value)
        typer.echo(_findings_to_json(findings, summarize(findings), commands))
        return
    for finding in findings:
        _print_finding(finding)
    typer.echo(f"{len(findings)} anchor finding(s)")


def _suggest_anchors(
    repo_root: Path, config: IrminsulConfig, graph: DocGraph, *, doc: str | None, fmt: str
) -> None:
    import json

    from irminsul.binding import bound_names, load_sources, suggest, unbound_names
    from irminsul.checks.code_spans import code_spans, is_live_doc
    from irminsul.code_references import CodeResolver

    resolver = CodeResolver(repo_root, config)
    sources = load_sources(repo_root, config)
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
                            for c in suggest(repo_root, sources, name)
                        ],
                    }
                )
    if fmt == "json":
        typer.echo(json.dumps({"version": 1, "unbound": rows}, indent=2))
        return
    for row in rows:
        typer.echo(f"{row['path']}:{row['line']} `{row['name']}`")
        candidates = row["candidates"]
        assert isinstance(candidates, list)
        if not candidates:
            typer.echo("  no source file contains it; reword it if it is not this repo's code")
        for c in candidates:
            kind = "definition" if c["definition"] else "mention"
            typer.echo(f"  {c['path']}:{c['line']} ({kind})  {c['marker']}")
    typer.echo(f"{len(rows)} unbound code name(s)")


_change_app = typer.Typer(
    name="change",
    help="Bound-change lifecycle for RFCs: status, verification, and transitions.",
    no_args_is_help=True,
)
app.add_typer(_change_app)


class TransitionTarget(StrEnum):
    accepted = "accepted"
    rejected = "rejected"


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

    _require_plain_or_json(fmt)

    repo_root, config = _load_repo(path)
    try:
        report = build_change_report(repo_root, config, change_id)
    except ChangeError as exc:
        typer.echo(typer.style(str(exc), fg="red"), err=True)
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

    _require_plain_or_json(fmt)

    repo_root, config = _load_repo(path)
    try:
        report = build_relation_graph(
            repo_root,
            config,
            focus=change_id,
            relation=relation.value,
        )
    except ChangeError as exc:
        typer.echo(typer.style(str(exc), fg="red"), err=True)
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

    _require_plain_or_json(fmt)

    repo_root, config = _load_repo(path)
    try:
        report = build_change_report(repo_root, config, change_id, base_ref=base_ref)
    except ChangeError as exc:
        typer.echo(typer.style(str(exc), fg="red"), err=True)
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
        typer.echo(typer.style(str(exc), fg="red"), err=True)
        raise typer.Exit(code=exc.code) from exc

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

    plan_only = dry_run or not confirm
    result = apply_fixes(repo_root, list(plan.fixes), dry_run=plan_only, confirm=True)
    _echo_fix_result(result, dry_run=plan_only)
    if result.errors:
        for error in result.errors:
            typer.echo(typer.style(error, fg="red"), err=True)
        raise typer.Exit(code=1)

    if plan_only:
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

    _require_plain_or_json(fmt)

    repo_root, config = _load_repo(path)
    try:
        report = build_impact_report(repo_root, config, change_id, base_ref=base_ref)
    except ChangeError as exc:
        typer.echo(typer.style(str(exc), fg="red"), err=True)
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
        typer.echo(typer.style(str(exc), fg="red"), err=True)
        raise typer.Exit(code=exc.code) from exc

    typer.echo(f"{plan.change}: {plan.current_state} -> implemented")
    if plan.blockers:
        for blocker in plan.blockers:
            typer.echo(
                typer.style(f"  blocker [{blocker.code}]: {blocker.message}", fg="red"), err=True
            )
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
    config = _load_config(repo_root)
    spec = NewSpec(kind="adr", title=title, extra={})
    try:
        dest = write_new(repo_root, spec, config, force=force)
    except FileExistsError as e:
        typer.echo(typer.style(f"already exists: {e}", fg="yellow"))
        raise typer.Exit(1) from e
    except ValueError as e:
        typer.echo(typer.style(str(e), fg="red"), err=True)
        raise typer.Exit(2) from e
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
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """Scaffold a new component doc."""
    from irminsul.new.command import (
        NewSpec,
        current_owners,
        normalize_claim_path,
        resolve_destination,
        resolve_id,
        split_links,
        write_new,
    )

    repo_root = path.resolve()
    config = _load_config(repo_root)
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
    try:
        # Ahead of the two uses below, not only around `create`: an unnameable title
        # reaches `resolve_destination` here first, where it was a raw traceback while
        # `new adr` reported the same title as a usage error.
        resolve_destination(repo_root, probe, config)
    except ValueError as e:
        typer.echo(typer.style(str(e), fg="red"), err=True)
        raise typer.Exit(2) from e
    owned = current_owners(repo_root, config, describes_rel)
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
    try:
        split_refs = split_links(repo_root, config, probe, split_from or [])
    except KeyError as exc:
        typer.echo(typer.style(f"--split-from: no doc with id {exc.args[0]}", fg="red"), err=True)
        raise typer.Exit(code=2) from exc

    surface_groups: list[dict[str, object]] = []
    if from_surface:
        if not describes_rel:
            typer.echo(
                typer.style("--from-surface requires at least one --describes path", fg="red"),
                err=True,
            )
            raise typer.Exit(code=2)
        from irminsul.surface import derive_surface

        doc_dir = resolve_destination(repo_root, probe, config).parent
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
        for rel in describes_rel:
            if rel not in contributing:
                typer.echo(typer.style(f"note: no derivable surface for: {rel}", fg="yellow"))

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
    try:
        dest = write_new(repo_root, spec, config, force=force)
    except FileExistsError as e:
        typer.echo(typer.style(f"already exists: {e}", fg="yellow"))
        raise typer.Exit(1) from e
    except ValueError as e:
        typer.echo(typer.style(str(e), fg="red"), err=True)
        raise typer.Exit(2) from e
    rel = dest.relative_to(repo_root).as_posix()
    typer.echo(typer.style(f"created: {rel}", fg="green"))
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
        typer.Option(
            "--force",
            help="Overwrite an existing file and scaffold despite blocking errors.",
        ),
    ] = False,
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """Scaffold a new RFC.

    Runs the repository binding-readiness summary first: errors, which are certain
    findings, block drafting, while drift clues and unrelated warnings are reported
    without preventing a new idea from being recorded.
    """
    from irminsul.change.readiness import (
        build_binding_readiness_report,
        format_binding_readiness_plain,
    )
    from irminsul.new.command import NewSpec, write_new

    repo_root = path.resolve()
    config = _load_config(repo_root)

    readiness = build_binding_readiness_report(repo_root, config)
    if not readiness.ready or readiness.clues or readiness.repository_debt:
        typer.echo(format_binding_readiness_plain(readiness))
    if not readiness.ready and not force:
        typer.echo(
            typer.style(
                "checks report errors; fix them before drafting (or pass --force)",
                fg="red",
            ),
            err=True,
        )
        raise typer.Exit(code=1)

    spec = NewSpec(kind="rfc", title=title, extra={})
    try:
        dest = write_new(repo_root, spec, config, force=force)
    except FileExistsError as e:
        typer.echo(typer.style(f"already exists: {e}", fg="yellow"))
        raise typer.Exit(1) from e
    except ValueError as e:
        typer.echo(typer.style(str(e), fg="red"), err=True)
        raise typer.Exit(2) from e
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
    _require_plain_or_json(fmt)
    _load_config(path.resolve())
    from irminsul.listing.command import list_orphans as _list_orphans

    _list_orphans(path.resolve(), fmt=fmt)


@_list_app.command("baseline")
def list_baseline(
    fmt: Annotated[str, typer.Option("--format", help="Output format: plain or json.")] = "plain",
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """List baseline entries and whether each still hides a finding."""
    _require_plain_or_json(fmt)
    _load_config(path.resolve())
    from irminsul.listing.command import list_baseline as _list_baseline

    _list_baseline(path.resolve(), fmt=fmt)


@_list_app.command("stale")
def list_stale(
    fmt: Annotated[str, typer.Option("--format")] = "plain",
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """List deprecated docs that are past the stale threshold."""
    _require_plain_or_json(fmt)
    _load_config(path.resolve())
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
    _require_plain_or_json(fmt)
    _load_config(path.resolve())
    from irminsul.listing.command import list_undocumented as _list_undocumented

    _list_undocumented(path.resolve(), fmt=fmt, all_files=all_files)


@_list_app.command("lifecycle")
def list_lifecycle(
    fmt: Annotated[str, typer.Option("--format")] = "plain",
    queue: Annotated[bool, typer.Option("--queue")] = False,
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """List unfinished RFC lifecycle work."""
    _require_plain_or_json(fmt)
    _load_config(path.resolve())
    from irminsul.listing.command import list_lifecycle as _list_lifecycle

    _list_lifecycle(path.resolve(), fmt=fmt, queue=queue)


@_list_app.command("review")
def list_review(
    fmt: Annotated[str, typer.Option("--format")] = "plain",
    doc: Annotated[
        str | None, typer.Option("--doc", help="Only this doc (repo-relative path).")
    ] = None,
    show_all: Annotated[
        bool,
        typer.Option("--all", help="List every assertion, not only those whose code changed."),
    ] = False,
    changed: Annotated[
        bool,
        typer.Option(
            "--changed", help="Only assertions on lines changed in the working tree, vs HEAD."
        ),
    ] = False,
    base: Annotated[
        str | None,
        typer.Option("--base", help="Only assertions on lines changed since this git ref."),
    ] = None,
    path: Annotated[Path, typer.Option("--path")] = Path("."),
) -> None:
    """List assertions that state current truth with the code they name, for review."""
    _require_plain_or_json(fmt)
    repo_root = path.resolve()
    _load_config(repo_root)
    from irminsul.git.changes import GitChangesError, changed_line_numbers
    from irminsul.listing.review import list_review as _list_review

    changed_lines = None
    if changed or base is not None:
        from irminsul.git.changes import merge_base

        try:
            since = (merge_base(repo_root, base, "HEAD") or base) if base is not None else None
            changed_lines = changed_line_numbers(repo_root, since)
        except GitChangesError as exc:
            typer.echo(typer.style(str(exc), fg="red"), err=True)
            raise typer.Exit(code=2) from exc
    _list_review(
        repo_root,
        fmt=fmt,
        doc=doc,
        show_all=show_all,
        changed=changed_lines,
        base_ref=base or "HEAD",
    )


_regen_app = typer.Typer(
    name="regen",
    help="Regenerate generated documentation artifacts.",
    no_args_is_help=True,
)
app.add_typer(_regen_app)


def _load_repo(path: Path) -> tuple[Path, IrminsulConfig]:
    repo_root = path.resolve()
    config = _load_config(repo_root)
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
    from irminsul.regen.agents_md import RegenError, regen_agents_md

    repo_root, config = _load_repo(path)
    try:
        written = regen_agents_md(repo_root, config)
    except RegenError as e:
        typer.echo(typer.style(str(e), fg="red"), err=True)
        raise typer.Exit(code=2) from e
    _print_regen_result(repo_root, written)


if __name__ == "__main__":  # pragma: no cover
    main()
