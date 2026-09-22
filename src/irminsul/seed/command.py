"""`irminsul seed` — capture a project's principle, idea, and belief.

A fresh-start project begins with intent, not code. `seed` collects that intent
(the PIB statement plus first user, non-goals, and direction risks) and writes
it into the foundation layer: `principles.md`, `overview.md`, an anchoring ADR
titled from the user's idea, and an anchoring RFC that records the original
direction so later drift can be compared against it.

The command is idempotent: it writes freely while the foundation docs are still
scaffold placeholders, refuses to clobber edited docs unless `--reseed`, and
appends under a dated heading with `--merge`.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import typer
from jinja2 import Environment, FileSystemLoader

from irminsul.checks.parent_child import link_from_folder_index
from irminsul.config import IrminsulConfig, layer_dir
from irminsul.init.placeholders import SCAFFOLD_PLACEHOLDER_PHRASES
from irminsul.new.command import _slugify

_TEMPLATES_DIR = Path(__file__).parent / "templates"

PIB_INTRO = (
    "A PIB statement is your project's root intent — the thing agents expand "
    "into docs and code:\n"
    "  - Principle: what must stay true even if features change.\n"
    "  - Idea: what should be built first.\n"
    "  - Belief: why this direction is worth pursuing."
)

FoundationState = Literal["pristine", "edited"]


@dataclass(frozen=True)
class SeedAnswers:
    principle: str
    idea: str
    belief: str
    first_user: str
    project_name: str
    today: str
    non_goals: list[str] = field(default_factory=list)
    direction_risks: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SeedResult:
    written: list[Path]
    """Repo-relative paths created or overwritten."""


# --- gathering ------------------------------------------------------------


def _split_list(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(";") if item.strip()]


def gather_answers_interactive(project_name: str, *, show_intro: bool = True) -> SeedAnswers:
    if show_intro:
        typer.echo()
        typer.echo(typer.style(PIB_INTRO, fg="cyan"))
        typer.echo()
    principle = typer.prompt("Principle (what must stay true)")
    idea = typer.prompt("Idea (what to build first)")
    belief = typer.prompt("Belief (why this is worth pursuing)")
    first_user = typer.prompt("First user (who this should serve first)")
    non_goals = _split_list(
        typer.prompt(
            "Non-goals (what this should not become; separate with ';')",
            default="",
        )
    )
    direction_risks = _split_list(
        typer.prompt(
            "Direction risks (what would make this drift; separate with ';')",
            default="",
        )
    )
    return SeedAnswers(
        principle=principle,
        idea=idea,
        belief=belief,
        first_user=first_user,
        project_name=project_name,
        today=_dt.date.today().isoformat(),
        non_goals=non_goals,
        direction_risks=direction_risks,
    )


def gather_answers_from_flags(
    *,
    project_name: str,
    principle: str | None,
    idea: str | None,
    belief: str | None,
    first_user: str | None,
    non_goals: str | None,
    direction_risks: str | None,
) -> SeedAnswers:
    missing = [
        name
        for name, value in (
            ("--principle", principle),
            ("--idea", idea),
            ("--belief", belief),
            ("--first-user", first_user),
        )
        if not value
    ]
    if missing or principle is None or idea is None or belief is None or first_user is None:
        typer.echo(
            typer.style(
                "Error: "
                + (
                    f"non-interactive seed requires {', '.join(missing)} "
                    "(or pass --json with a complete seed file)"
                ),
                fg="red",
            )
        )
        raise typer.Exit(code=2)
    return SeedAnswers(
        principle=principle,
        idea=idea,
        belief=belief,
        first_user=first_user,
        project_name=project_name,
        today=_dt.date.today().isoformat(),
        non_goals=_split_list(non_goals or ""),
        direction_risks=_split_list(direction_risks or ""),
    )


def gather_answers_from_json(json_path: Path, *, project_name: str) -> SeedAnswers:
    try:
        raw = json.loads(json_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise typer.BadParameter(f"seed JSON file not found: {json_path}") from exc
    except UnicodeDecodeError as exc:
        raise typer.BadParameter(f"could not decode seed JSON file {json_path}: {exc}") from exc
    except OSError as exc:
        raise typer.BadParameter(f"could not read seed JSON file {json_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"invalid JSON in {json_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise typer.BadParameter(f"seed JSON must be an object, got {type(raw).__name__}")

    missing = [k for k in ("principle", "idea", "belief", "first_user") if not raw.get(k)]
    if missing:
        raise typer.BadParameter(f"seed JSON missing required key(s): {', '.join(missing)}")

    def _as_list(value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return _split_list(str(value))

    return SeedAnswers(
        principle=str(raw["principle"]),
        idea=str(raw["idea"]),
        belief=str(raw["belief"]),
        first_user=str(raw["first_user"]),
        project_name=project_name,
        today=_dt.date.today().isoformat(),
        non_goals=_as_list(raw.get("non_goals")),
        direction_risks=_as_list(raw.get("direction_risks")),
    )


# --- idempotency ----------------------------------------------------------


def _seed_doc_targets(repo_root: Path, config: IrminsulConfig) -> tuple[Path, Path]:
    return (
        layer_dir(repo_root, config, "foundation") / "principles.md",
        layer_dir(repo_root, config, "architecture") / "overview.md",
    )


_STATUS_RE = re.compile(r"(?m)^status:\s*\S")
_DRAFT_STATUS_RE = re.compile(r"(?m)^status:\s*draft\s*$")


def foundation_state(repo_root: Path, config: IrminsulConfig) -> FoundationState:
    """Classify the foundation docs `seed` would write.

    "pristine" means every existing target still contains scaffold placeholder
    text (or does not exist yet). "edited" means at least one target has been
    edited away from scaffold defaults, so overwriting it would lose real work.
    """
    for target in _seed_doc_targets(repo_root, config):
        if not target.exists():
            continue
        body = target.read_text(encoding="utf-8")
        if not any(phrase in body for phrase in SCAFFOLD_PLACEHOLDER_PHRASES):
            return "edited"
        # Holding one scaffold phrase is not enough to call a doc untouched: several of
        # them are bare prompts the scaffold suggests keeping as section headings, so a
        # fully authored doc that kept "Who should it serve first?" read as pristine and
        # was overwritten — by the very command the blocking finding tells you to run.
        # Both the scaffold and `seed` write `status: draft`, so a promoted doc is
        # authored by definition.
        if _STATUS_RE.search(body) and not _DRAFT_STATUS_RE.search(body):
            return "edited"
    return "pristine"


# --- rendering & writing --------------------------------------------------


_ENV = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    keep_trailing_newline=True,
)


def _render(template_name: str, **context: object) -> str:
    return _ENV.get_template(template_name).render(**context)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _merge_block(answers: SeedAnswers) -> str:
    lines = [
        "",
        f"## Seed pass — {answers.today}",
        "",
        f"- **Principle** — {answers.principle}",
        f"- **Idea** — {answers.idea}",
        f"- **Belief** — {answers.belief}",
        f"- **First user** — {answers.first_user}",
    ]
    for ng in answers.non_goals:
        lines.append(f"- **Non-goal** — {ng}")
    for dr in answers.direction_risks:
        lines.append(f"- **Direction risk** — {dr}")
    lines.append("")
    return "\n".join(lines)


def run_seed(
    repo_root: Path,
    config: IrminsulConfig,
    answers: SeedAnswers,
    *,
    reseed: bool = False,
    merge: bool = False,
) -> SeedResult:
    """Materialize a PIB statement into the foundation layer.

    Raises `typer.Exit` if the foundation docs have been edited away from
    scaffold defaults and neither `reseed` nor `merge` was requested.
    """
    principles_path, overview_path = _seed_doc_targets(repo_root, config)
    state = foundation_state(repo_root, config)
    written: list[Path] = []

    if state == "edited" and not reseed and not merge:
        typer.echo(
            typer.style(
                "Foundation docs have been edited away from scaffold defaults.\n"
                "Re-run with --reseed to overwrite them, or --merge to append "
                "this seed pass under a dated heading.",
                fg="red",
            )
        )
        raise typer.Exit(code=1)

    if state == "edited" and merge:
        existing = principles_path.read_text(encoding="utf-8")
        sep = "" if existing.endswith("\n") else "\n"
        _atomic_write(principles_path, existing + sep + _merge_block(answers))
        written.append(principles_path.relative_to(repo_root))
        return SeedResult(written=written)

    # state == "pristine", or "edited" with --reseed: write the foundation docs
    # fresh from the seed answers.
    _atomic_write(
        principles_path,
        _render(
            "principles.md.j2",
            project_name=answers.project_name,
            principle=answers.principle,
            idea=answers.idea,
            belief=answers.belief,
            first_user=answers.first_user,
            non_goals=answers.non_goals,
            direction_risks=answers.direction_risks,
        ),
    )
    written.append(principles_path.relative_to(repo_root))

    _atomic_write(
        overview_path,
        _render(
            "overview.md.j2",
            project_name=answers.project_name,
            idea=answers.idea,
            first_user=answers.first_user,
        ),
    )
    written.append(overview_path.relative_to(repo_root))

    # The anchoring ADR and RFC are the project's first change record. They
    # are created once, on the initial seed; a --reseed refreshes the foundation
    # docs but does not re-anchor an already-anchored project.
    if state == "pristine":
        adr_dir = layer_dir(repo_root, config, "decisions")
        rfc_dir = layer_dir(repo_root, config, "rfcs")
        adr_title = " ".join(answers.idea.replace('"', "'").splitlines()).strip()
        from irminsul.docgraph import build_graph

        taken = set(build_graph(repo_root, config).nodes)
        adr_id = _unused_id(_slugify(answers.idea) or "initial-direction-decision", taken, adr_dir)
        taken.add(adr_id)
        rfc_id = _unused_id("initial-direction", taken, rfc_dir)

        adr_path = adr_dir / f"{adr_id}.md"
        rfc_path = rfc_dir / f"{rfc_id}.md"
        _atomic_write(
            adr_path,
            _render(
                "seed-adr.md.j2",
                id=adr_id,
                title=adr_title,
                rfc_id=rfc_id,
                rfc_link=os.path.relpath(rfc_path, adr_dir).replace("\\", "/"),
                project_name=answers.project_name,
                principle=answers.principle,
                idea=answers.idea,
                belief=answers.belief,
                first_user=answers.first_user,
                non_goals=answers.non_goals,
                direction_risks=answers.direction_risks,
            ),
        )
        written.append(adr_path.relative_to(repo_root))

        _atomic_write(
            rfc_path,
            _render(
                "seed-rfc.md.j2",
                id=rfc_id,
                title="Initial direction",
                adr_id=adr_id,
                adr_path=adr_path.relative_to(repo_root).as_posix(),
                adr_link=os.path.relpath(adr_path, rfc_dir).replace("\\", "/"),
                project_name=answers.project_name,
                principle=answers.principle,
                idea=answers.idea,
                belief=answers.belief,
                first_user=answers.first_user,
                non_goals=answers.non_goals,
                direction_risks=answers.direction_risks,
            ),
        )
        written.append(rfc_path.relative_to(repo_root))

        for doc_path, doc_id, description in (
            (adr_path, adr_id, adr_title),
            (rfc_path, rfc_id, "Initial direction"),
        ):
            index_written = link_from_folder_index(doc_path, doc_id, description)
            if index_written is not None:
                written.append(index_written.relative_to(repo_root))

    return SeedResult(written=written)


def _unused_id(base: str, taken: set[str], folder: Path) -> str:
    """`base`, or `base-2`, `base-3`, ... when a doc id or a file already uses it."""
    candidate, n = base, 1
    while candidate in taken or (folder / f"{candidate}.md").exists():
        n += 1
        candidate = f"{base}-{n}"
    return candidate
