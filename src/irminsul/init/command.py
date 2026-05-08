"""`irminsul init` — scaffold a new codebase.

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

from irminsul.init.detector import detect_languages, detect_source_roots

_GITHUB_USER_PLACEHOLDER = "<github-user>"

_SCAFFOLDS_DIR = Path(__file__).parent / "scaffolds"
_WORKFLOWS_DIR = Path(__file__).parent / "workflows"


@dataclass(frozen=True)
class InitAnswers:
    project_name: str
    owner: str
    render_target: str
    languages: list[str]
    source_roots: list[str]
    github_user: str
    today: str


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
        owner = typer.prompt("Default doc owner (GitHub handle, e.g. @anson)", default="@TODO")
        render_target = typer.prompt("Render target [mkdocs|none]", default="mkdocs")
        if render_target not in ("mkdocs", "none"):
            typer.echo(
                typer.style(f"unknown render target '{render_target}', using 'mkdocs'", fg="yellow")
            )
            render_target = "mkdocs"
    else:
        project_name = default_project_name
        owner = "@TODO"
        render_target = "mkdocs"

    return InitAnswers(
        project_name=project_name,
        owner=owner,
        render_target=render_target,
        languages=languages,
        source_roots=source_roots,
        github_user=_GITHUB_USER_PLACEHOLDER,
        today=today,
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
        "owner": answers.owner,
        "render_target": answers.render_target,
        "languages": answers.languages,
        "source_roots": answers.source_roots,
        "github_user": answers.github_user,
        "today": answers.today,
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
        f"  4. Replace {_GITHUB_USER_PLACEHOLDER} in .github/workflows/docs-*.yml "
        "with your GitHub user/org."
    )
    typer.echo("  5. git add . && git commit -m 'Adopt Irminsul'")
    typer.echo("  6. Push — CI enforces from PR #1.")


def run_init(target_root: Path, *, interactive: bool, force: bool = False) -> None:
    answers = gather_answers(repo_root=target_root, interactive=interactive)
    written = write_scaffold(target_root, answers, force=force)
    print_next_steps(answers, written)
