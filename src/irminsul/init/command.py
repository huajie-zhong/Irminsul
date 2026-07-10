"""`irminsul init` / `irminsul init-docs-only` — scaffold a new codebase.

Walks the Jinja templates under `init/scaffolds/` and `init/workflows/` and
writes them out into the target repo, substituting in the answers gathered
either from the interactive prompts or from sensible defaults.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from irminsul.config import find_config, load
from irminsul.init.detector import detect_languages, detect_source_roots
from irminsul.regen.agents_md import manifest_rel_path, regen_agents_md

_GITHUB_USER_PLACEHOLDER = "huajie-zhong"

_SCAFFOLDS_DIR = Path(__file__).parent / "scaffolds"
_WORKFLOWS_DIR = Path(__file__).parent / "workflows"

_CODE_SIGNAL_FILES = (
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "package.json",
    "Cargo.toml",
    "go.mod",
)
_CODE_SIGNAL_DIRS = ("src", "app", "lib")


@dataclass(frozen=True)
class InitAnswers:
    project_name: str
    languages: list[str]
    source_roots: list[str]
    github_user: str
    today: str
    # Two-repo fields (None for single-repo init)
    code_repo_spec: str | None = None
    code_subfolder: str | None = None


def detect_code_signals(repo_root: Path) -> bool:
    if any((repo_root / name).exists() for name in _CODE_SIGNAL_FILES):
        return True
    return any((repo_root / name).is_dir() for name in _CODE_SIGNAL_DIRS)


def parse_code_repo(value: str) -> tuple[str | None, str]:
    """Return (github_spec, subfolder_name). github_spec is None for local paths."""
    if value.startswith(("./", "../", "/")) or "://" in value:
        return None, Path(value).name or "code"
    parts = value.split("/")
    if len(parts) == 2 and all(parts):
        return value, parts[1]
    return None, Path(value).name or "code"


def update_gitignore(target_root: Path, subfolder: str) -> None:
    """Idempotently append /<subfolder>/ to .gitignore with a marker comment."""
    gitignore = target_root / ".gitignore"
    entry = f"/{subfolder}/"
    marker = "# Irminsul: external code subfolder"

    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        if entry in content:
            return
        sep = "\n" if content.endswith("\n") else "\n\n"
        gitignore.write_text(content + sep + marker + "\n" + entry + "\n", encoding="utf-8")
    else:
        gitignore.write_text(marker + "\n" + entry + "\n", encoding="utf-8")


def gather_answers(
    *,
    repo_root: Path,
    interactive: bool,
) -> InitAnswers:
    languages = detect_languages(repo_root) or ["python"]
    source_roots = detect_source_roots(repo_root, languages)
    today = _dt.date.today().isoformat()

    default_project_name = repo_root.resolve().name or "untitled"

    if interactive:
        project_name = typer.prompt("Project name", default=default_project_name)
    else:
        project_name = default_project_name

    return InitAnswers(
        project_name=project_name,
        languages=languages,
        source_roots=source_roots,
        github_user=_GITHUB_USER_PLACEHOLDER,
        today=today,
    )


def gather_answers_fresh(
    *,
    repo_root: Path,
    interactive: bool,
) -> InitAnswers:
    """Gather answers for a language-neutral same-repo fresh start."""
    today = _dt.date.today().isoformat()
    default_project_name = repo_root.resolve().name or "untitled"

    if interactive:
        project_name = typer.prompt("Project name", default=default_project_name)
    else:
        project_name = default_project_name

    return InitAnswers(
        project_name=project_name,
        languages=[],
        source_roots=["src"],
        github_user=_GITHUB_USER_PLACEHOLDER,
        today=today,
    )


def gather_answers_docs_only(
    *,
    repo_root: Path,
    interactive: bool,
    code_repo: str | None,
) -> InitAnswers:
    """Gather answers for init-docs-only (two-repo / Topology A)."""
    today = _dt.date.today().isoformat()
    default_project_name = repo_root.resolve().name or "untitled"

    if interactive:
        if code_repo is None:
            code_repo = typer.prompt(
                "Code repo (GitHub owner/repo or local path, e.g. acme/my-public-code)"
            )
        project_name = typer.prompt("Project name", default=default_project_name)
    else:
        if code_repo is None:
            raise typer.BadParameter(
                "--code-repo is required in non-interactive mode", param_hint="--code-repo"
            )
        project_name = default_project_name

    github_spec, subfolder = parse_code_repo(code_repo)

    # Detect source roots from subfolder if it already exists on disk
    subfolder_path = repo_root / subfolder
    if subfolder_path.is_dir():
        languages = detect_languages(subfolder_path) or ["python"]
        source_roots = [f"{subfolder}/{r}" for r in detect_source_roots(subfolder_path, languages)]
    else:
        languages = ["python"]
        source_roots = [f"{subfolder}/src"]

    return InitAnswers(
        project_name=project_name,
        languages=languages,
        source_roots=source_roots,
        github_user=_GITHUB_USER_PLACEHOLDER,
        today=today,
        code_repo_spec=github_spec,
        code_subfolder=subfolder,
    )


def gather_answers_fresh_docs_only(
    *,
    repo_root: Path,
    interactive: bool,
    code_repo: str | None,
) -> InitAnswers:
    """Gather answers for a future-code private-docs/public-code fresh start."""
    today = _dt.date.today().isoformat()
    default_project_name = repo_root.resolve().name or "untitled"

    if interactive:
        if code_repo is None:
            code_repo = typer.prompt(
                "Code repo (GitHub owner/repo or local path, e.g. acme/my-public-code)"
            )
        project_name = typer.prompt("Project name", default=default_project_name)
    else:
        if code_repo is None:
            raise typer.BadParameter(
                "--code-repo is required for fresh docs-only topology", param_hint="--code-repo"
            )
        project_name = default_project_name

    github_spec, subfolder = parse_code_repo(code_repo)

    subfolder_path = repo_root / subfolder
    if subfolder_path.is_dir():
        languages = detect_languages(subfolder_path)
        source_roots = [f"{subfolder}/{r}" for r in detect_source_roots(subfolder_path, languages)]
    else:
        languages = []
        source_roots = [f"{subfolder}/src"]

    return InitAnswers(
        project_name=project_name,
        languages=languages,
        source_roots=source_roots,
        github_user=_GITHUB_USER_PLACEHOLDER,
        today=today,
        code_repo_spec=github_spec,
        code_subfolder=subfolder,
    )


def _render_template(template_path: Path, base_dir: Path, context: Mapping[str, Any]) -> str:
    env = Environment(
        loader=FileSystemLoader(base_dir),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    template_rel = template_path.relative_to(base_dir).as_posix()
    template = env.get_template(template_rel)
    return template.render(**context)


def _scaffold_pairs() -> list[tuple[Path, Path, Path]]:
    """Return (template, base_dir, output_relative) tuples for every file written."""
    pairs: list[tuple[Path, Path, Path]] = []
    for tpl in sorted(_SCAFFOLDS_DIR.rglob("*.j2")):
        rel = tpl.relative_to(_SCAFFOLDS_DIR)
        # Strip the trailing .j2 to derive the output path.
        output_rel = rel.with_suffix("")  # foo.md.j2 → foo.md
        pairs.append((tpl, _SCAFFOLDS_DIR, output_rel))

    for tpl in sorted(_WORKFLOWS_DIR.rglob("*.j2")):
        rel = tpl.relative_to(_WORKFLOWS_DIR)
        output_rel = Path(".github") / "workflows" / rel.with_suffix("")
        pairs.append((tpl, _WORKFLOWS_DIR, output_rel))

    return pairs


def write_scaffold(target_root: Path, answers: InitAnswers, *, force: bool = False) -> list[Path]:
    """Render every scaffold template into `target_root`. Returns the list of
    files written (repo-relative)."""
    context = {
        "project_name": answers.project_name,
        "languages": answers.languages,
        "source_roots": answers.source_roots,
        "github_user": answers.github_user,
        "today": answers.today,
        "code_repo_spec": answers.code_repo_spec,
        "code_subfolder": answers.code_subfolder,
    }

    written: list[Path] = []
    for template_path, base_dir, output_rel in _scaffold_pairs():
        out_abs = target_root / output_rel
        if out_abs.exists() and not force:
            continue
        out_abs.parent.mkdir(parents=True, exist_ok=True)
        rendered = _render_template(template_path, base_dir, context)
        out_abs.write_text(rendered, encoding="utf-8")
        written.append(output_rel)

    return written


def generate_agents_manifest(target_root: Path, *, force: bool = False) -> list[Path]:
    """Generate `docs/AGENTS.md` from the freshly scaffolded tree.

    Reuses the `irminsul regen agents-md` machinery: a missing manifest is
    scaffolded in full; a pre-existing manifest is never clobbered — without
    `force` it is left untouched, and with `force` only the marked generated
    section is rewritten (curated sections survive regeneration).
    """
    config = load(find_config(target_root))
    rel_path = manifest_rel_path(config)
    if (target_root / rel_path).exists() and not force:
        return []
    regen_agents_md(target_root, config)
    return [rel_path]


def _scaffold_with_agent_wiring(
    target_root: Path, answers: InitAnswers, *, force: bool
) -> list[Path]:
    """Render the scaffold, then wire the repo for agent harnesses.

    Writes `docs/AGENTS.md` (the navigation manifest) via the regen machinery.
    The root `AGENTS.md` pointer is part of the scaffold templates; if one
    already exists it is skipped (with a note) unless `force` is given.
    """
    root_manifest_preexisting = (target_root / "AGENTS.md").exists()
    written = write_scaffold(target_root, answers, force=force)
    written.extend(generate_agents_manifest(target_root, force=force))
    if root_manifest_preexisting and not force:
        typer.echo(
            typer.style(
                "note: AGENTS.md already exists at the repo root; leaving it untouched.",
                fg="yellow",
            )
        )
    return written


def print_next_steps(answers: InitAnswers, written: list[Path]) -> None:
    typer.echo()
    typer.echo(typer.style("Created:", fg="green", bold=True))
    for p in written:
        typer.echo(f"  {p.as_posix()}")
    typer.echo()
    typer.echo(typer.style("Next steps:", fg="green", bold=True))
    typer.echo("  1. Edit docs/00-foundation/principles.md")
    typer.echo("  2. Edit docs/10-architecture/overview.md")
    typer.echo("  3. Add CODEOWNERS coverage for /docs (project-specific; not auto-generated).")
    typer.echo(
        "  4. Point your coding agent at AGENTS.md (repo root) — "
        "it routes to docs/AGENTS.md and the agent loop."
    )
    typer.echo("  5. git add . && git commit -m 'Adopt Irminsul'")
    typer.echo("  6. Push — CI enforces from PR #1.")


def run_init(target_root: Path, *, interactive: bool, force: bool = False) -> None:
    answers = gather_answers(repo_root=target_root, interactive=interactive)
    written = _scaffold_with_agent_wiring(target_root, answers, force=force)
    print_next_steps(answers, written)


def run_init_fresh(target_root: Path, *, interactive: bool, force: bool = False) -> None:
    answers = gather_answers_fresh(repo_root=target_root, interactive=interactive)
    written = _scaffold_with_agent_wiring(target_root, answers, force=force)
    for root in answers.source_roots:
        (target_root / root).mkdir(parents=True, exist_ok=True)
    print_next_steps(answers, written)


def run_init_docs_only(
    target_root: Path,
    *,
    interactive: bool,
    code_repo: str | None,
    force: bool = False,
) -> None:
    answers = gather_answers_docs_only(
        repo_root=target_root, interactive=interactive, code_repo=code_repo
    )
    written = _scaffold_with_agent_wiring(target_root, answers, force=force)
    if answers.code_subfolder:
        update_gitignore(target_root, answers.code_subfolder)
    _print_docs_only_next_steps(answers, written)


def run_init_fresh_docs_only(
    target_root: Path,
    *,
    interactive: bool,
    code_repo: str | None,
    force: bool = False,
) -> None:
    answers = gather_answers_fresh_docs_only(
        repo_root=target_root, interactive=interactive, code_repo=code_repo
    )
    written = _scaffold_with_agent_wiring(target_root, answers, force=force)
    if answers.code_subfolder:
        update_gitignore(target_root, answers.code_subfolder)
    _print_docs_only_next_steps(answers, written)


def _print_docs_only_next_steps(answers: InitAnswers, written: list[Path]) -> None:
    typer.echo()
    typer.echo(typer.style("Created:", fg="green", bold=True))
    for p in written:
        typer.echo(f"  {p.as_posix()}")
    typer.echo()
    typer.echo(typer.style("Next steps:", fg="green", bold=True))
    if answers.code_repo_spec:
        typer.echo(
            f"  1. Clone the code repo locally: "
            f"git clone https://github.com/{answers.code_repo_spec} {answers.code_subfolder}"
        )
    else:
        typer.echo(f"  1. Clone or place the code repo at ./{answers.code_subfolder}/")
    typer.echo("  2. Edit docs/00-foundation/principles.md")
    typer.echo("  3. Edit docs/10-architecture/overview.md")
    typer.echo(
        "  4. Point your coding agent at AGENTS.md (repo root) — "
        "it routes to docs/AGENTS.md and the agent loop."
    )
    typer.echo("  5. git add . && git commit -m 'Adopt Irminsul (docs-only)'")
    typer.echo("  6. Push — CI enforces from PR #1.")
