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

from irminsul.init.detector import detect_languages, detect_source_roots

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
    render_target: str
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
        render_target = typer.prompt("Render target [mkdocs|none]", default="mkdocs")
        if render_target not in ("mkdocs", "none"):
            typer.echo(
                typer.style(f"unknown render target '{render_target}', using 'mkdocs'", fg="yellow")
            )
            render_target = "mkdocs"
    else:
        project_name = default_project_name
        render_target = "mkdocs"

    return InitAnswers(
        project_name=project_name,
        render_target=render_target,
        languages=languages,
        source_roots=source_roots,
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
        render_target = typer.prompt("Render target [mkdocs|none]", default="mkdocs")
        if render_target not in ("mkdocs", "none"):
            render_target = "mkdocs"
    else:
        if code_repo is None:
            raise typer.BadParameter(
                "--code-repo is required in non-interactive mode", param_hint="--code-repo"
            )
        project_name = default_project_name
        render_target = "mkdocs"

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
        render_target=render_target,
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
        "render_target": answers.render_target,
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
    typer.echo("  4. git add . && git commit -m 'Adopt Irminsul'")
    typer.echo("  5. Push — CI enforces from PR #1.")


def run_init(target_root: Path, *, interactive: bool, force: bool = False) -> None:
    answers = gather_answers(repo_root=target_root, interactive=interactive)
    written = write_scaffold(target_root, answers, force=force)
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
    written = write_scaffold(target_root, answers, force=force)
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
    typer.echo("  4. git add . && git commit -m 'Adopt Irminsul (docs-only)'")
    typer.echo("  5. Push — CI enforces from PR #1.")
