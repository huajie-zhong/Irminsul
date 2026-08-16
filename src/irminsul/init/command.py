"""`irminsul init` — scaffold a new codebase.

Walks the Jinja templates under `init/scaffolds/` and `init/workflows/<topology>/`
and writes them out into the target repo, substituting in the answers gathered
either from the interactive prompts or from sensible defaults.

Two repository layouts are supported, and `Topology` names them:

- `same-repo` — `docs/` is a plain subfolder of the code repo.
- `siblings` — a docs repo and a code repo sit side by side under a common
  parent directory, so `source_roots` point out through `../`.
"""

from __future__ import annotations

import datetime as _dt
import posixpath
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

import typer
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from irminsul.config import find_config, load
from irminsul.init.detector import detect_languages, detect_source_roots
from irminsul.regen.agents_md import manifest_rel_path, regen_agents_md

_GITHUB_USER_PLACEHOLDER = "huajie-zhong"

_SCAFFOLDS_DIR = Path(__file__).parent / "scaffolds"
_WORKFLOWS_DIR = Path(__file__).parent / "workflows"

#: Directory the sibling repos are checked out under in generated CI.
CI_WORKSPACE = "workspace"
#: Path the docs repo is checked out to in generated sibling CI.
CI_DOCS_PATH = f"{CI_WORKSPACE}/docs"

_CODE_SIGNAL_FILES = (
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "package.json",
    "Cargo.toml",
    "go.mod",
)
_CODE_SIGNAL_DIRS = ("src", "app", "lib")


class Topology(StrEnum):
    """The repository layouts Irminsul scaffolds and supports."""

    same_repo = "same-repo"
    siblings = "siblings"


@dataclass(frozen=True)
class InitAnswers:
    project_name: str
    languages: list[str]
    source_roots: list[str]
    github_user: str
    today: str
    topology: Topology = Topology.same_repo
    # Siblings-only fields (None for the same-repo layout).
    code_repo_spec: str | None = None
    code_dir: str | None = None


def detect_code_signals(repo_root: Path) -> bool:
    if any((repo_root / name).exists() for name in _CODE_SIGNAL_FILES):
        return True
    return any((repo_root / name).is_dir() for name in _CODE_SIGNAL_DIRS)


def parse_code_repo(value: str, *, docs_root: Path) -> tuple[str | None, str]:
    """Resolve `--code-repo` into `(github_spec, code_dir)` for the siblings layout.

    `github_spec` is the `owner/repo` GitHub coordinate when the value names
    one, and `None` for a local path — CI can only generate a checkout step for
    the former. `code_dir` is the docs-repo-relative POSIX path of the sibling
    code checkout, always of the form `../<name>`: "siblings" means one parent
    directory holding both repos, so anything else is rejected here rather than
    silently scaffolding a layout the tool does not support.
    """
    if "://" in value:
        name = PurePosixPath(urlsplit(value).path.rstrip("/")).name
        return None, _sibling_dir(f"../{name or 'code'}", docs_root, value)

    parts = value.split("/")
    is_path = value.startswith(("./", "../", "~", "/")) or Path(value).is_absolute()
    if not is_path and len(parts) == 2 and all(parts) and "." not in parts:
        return value, _sibling_dir(f"../{parts[1]}", docs_root, value)

    if not is_path and len(parts) == 1 and value not in {".", ".."}:
        # A bare name normally means the sibling `../<name>`. But when a
        # directory of that name already sits inside the docs repo, the value is
        # ambiguous, and the nested reading is the one the deleted layout used —
        # so resolve it literally and let `_sibling_dir` reject it, which names
        # the sibling rule and the exact spelling that satisfies it. Silently
        # picking the other reading would configure a layout the user did not
        # ask for and skip the message written for this mistake.
        if (docs_root / value).is_dir():
            return None, _sibling_dir(value, docs_root, value)
        return None, _sibling_dir(f"../{value}", docs_root, value)

    return None, _sibling_dir(value, docs_root, value)


def _sibling_dir(candidate: str, docs_root: Path, original: str) -> str:
    """Normalize `candidate` to `../<name>` or reject it.

    Rejection is the point: a path that lands inside the docs repo is the
    deleted nested layout, and one further away than a sibling is a shape the
    generated CI workspace cannot express.
    """
    docs_abs = docs_root.resolve()
    code_abs = (docs_root / candidate).resolve()
    if code_abs.parent == docs_abs.parent and code_abs != docs_abs:
        return f"../{code_abs.name}"
    raise typer.BadParameter(
        f"{original!r} resolves to {code_abs}, which is not a sibling of the docs "
        f"repo at {docs_abs}. The siblings layout puts both repos under one "
        "parent directory — pass a GitHub 'owner/repo' or a path like '../code'.",
        param_hint="--code-repo",
    )


def ci_code_checkout_path(code_dir: str) -> str:
    """Where generated sibling CI checks the code repo out.

    The docs repo is checked out at `workspace/docs`, so the code repo has to
    land wherever `code_dir` points relative to it for `source_roots` to
    resolve identically in CI and on a developer's machine.
    """
    return posixpath.normpath(posixpath.join(CI_DOCS_PATH, code_dir))


def _posix_join(prefix: str, rel: str) -> str:
    """Join a detected source root onto `code_dir`, POSIX-normalized.

    Normalization is not cosmetic: a language profile may offer `.` as a source
    root candidate (Go does, for a flat module), and the unnormalized join
    would write `../code/.` into `paths.source_roots`.
    """
    return posixpath.normpath(posixpath.join(prefix, rel))


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


def gather_answers_siblings(
    *,
    repo_root: Path,
    interactive: bool,
    code_repo: str | None,
) -> InitAnswers:
    """Gather answers for the siblings layout.

    One gatherer covers both a code repo that already exists and one that does
    not exist yet: presence on disk is what decides whether languages and source
    roots can be detected, so there is nothing for the caller to declare.
    """
    today = _dt.date.today().isoformat()
    default_project_name = repo_root.resolve().name or "untitled"

    if interactive:
        if code_repo is None:
            code_repo = typer.prompt(
                "Sibling code repo (GitHub owner/repo or path, e.g. acme/my-public-code)"
            )
        project_name = typer.prompt("Project name", default=default_project_name)
    else:
        if code_repo is None:
            raise typer.BadParameter(
                "--code-repo is required in non-interactive mode", param_hint="--code-repo"
            )
        project_name = default_project_name

    github_spec, code_dir = parse_code_repo(code_repo, docs_root=repo_root)

    code_path = repo_root / code_dir
    if code_path.is_dir():
        languages = detect_languages(code_path)
        source_roots = [_posix_join(code_dir, r) for r in detect_source_roots(code_path, languages)]
    else:
        languages = []
        source_roots = [_posix_join(code_dir, "src")]

    return InitAnswers(
        project_name=project_name,
        languages=languages,
        source_roots=source_roots,
        github_user=_GITHUB_USER_PLACEHOLDER,
        today=today,
        topology=Topology.siblings,
        code_repo_spec=github_spec,
        code_dir=code_dir,
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


def _scaffold_pairs(topology: Topology) -> list[tuple[Path, Path, Path]]:
    """Return (template, base_dir, output_relative) tuples for every file written.

    The docs/config scaffold is shared; CI workflows are per-topology, because
    the sibling gate needs two checkouts under a common parent and a
    `working-directory`, which the composite Action cannot express.
    """
    pairs: list[tuple[Path, Path, Path]] = []
    for tpl in sorted(_SCAFFOLDS_DIR.rglob("*.j2")):
        rel = tpl.relative_to(_SCAFFOLDS_DIR)
        # Strip the trailing .j2 to derive the output path.
        output_rel = rel.with_suffix("")  # foo.md.j2 → foo.md
        pairs.append((tpl, _SCAFFOLDS_DIR, output_rel))

    workflows_dir = _WORKFLOWS_DIR / topology.value
    for tpl in sorted(workflows_dir.rglob("*.j2")):
        rel = tpl.relative_to(workflows_dir)
        output_rel = Path(".github") / "workflows" / rel.with_suffix("")
        pairs.append((tpl, workflows_dir, output_rel))

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
        "docs_checkout_path": CI_DOCS_PATH,
        "code_checkout_path": (
            ci_code_checkout_path(answers.code_dir) if answers.code_dir else None
        ),
    }

    written: list[Path] = []
    for template_path, base_dir, output_rel in _scaffold_pairs(answers.topology):
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


def run_init_siblings(
    target_root: Path,
    *,
    interactive: bool,
    code_repo: str | None,
    force: bool = False,
) -> None:
    answers = gather_answers_siblings(
        repo_root=target_root, interactive=interactive, code_repo=code_repo
    )
    written = _scaffold_with_agent_wiring(target_root, answers, force=force)
    _print_siblings_next_steps(answers, written)


def _print_siblings_next_steps(answers: InitAnswers, written: list[Path]) -> None:
    typer.echo()
    typer.echo(typer.style("Created:", fg="green", bold=True))
    for p in written:
        typer.echo(f"  {p.as_posix()}")
    typer.echo()
    typer.echo(typer.style("Next steps:", fg="green", bold=True))
    if answers.code_repo_spec:
        typer.echo(
            f"  1. Clone the code repo beside this one: "
            f"git clone https://github.com/{answers.code_repo_spec} {answers.code_dir}"
        )
    else:
        typer.echo(f"  1. Clone or place the code repo at {answers.code_dir}/")
    typer.echo("  2. Edit docs/00-foundation/principles.md")
    typer.echo("  3. Edit docs/10-architecture/overview.md")
    typer.echo(
        "  4. Point your coding agent at AGENTS.md (repo root) — "
        "it routes to docs/AGENTS.md and the agent loop."
    )
    typer.echo("  5. git add . && git commit -m 'Adopt Irminsul (siblings)'")
    typer.echo("  6. Push — CI enforces from PR #1.")
    if answers.code_repo_spec is None:
        typer.echo()
        typer.echo(
            typer.style(
                "note: the generated workflows cannot check out a code repo given as a "
                "local path; fill in the `repository:` of the second checkout step.",
                fg="yellow",
            )
        )
