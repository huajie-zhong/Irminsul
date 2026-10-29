"""`irminsul seed` — capture a project's principle, idea, and belief.

A fresh-start project begins with intent, not code. `seed` collects that intent
(the PIB statement plus first user, non-goals, and direction risks) and writes
it into `principles.md` and `overview.md`, rendered from the scaffolds `irminsul init`
writes them from.

The command is idempotent: while the foundation docs still carry the prompts
`irminsul init` marked, it replaces only the marked text; it refuses to clobber a doc
with no marker left unless `--reseed`, and appends under a dated heading with `--merge`.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import typer

from irminsul.atomic import write_atomic
from irminsul.config import IrminsulConfig, layer_dir
from irminsul.errors import UserError
from irminsul.fences import FenceTracker
from irminsul.frontmatter_edit import is_frontmatter_delimiter
from irminsul.init.command import render_scaffold
from irminsul.init.placeholders import placeholder_lines

PIB_INTRO = (
    "A PIB statement is your project's root intent — the thing agents expand "
    "into docs and code:\n"
    "  - Principle: what must stay true even if features change.\n"
    "  - Idea: what should be built first.\n"
    "  - Belief: why this direction is worth pursuing."
)

FoundationState = Literal["pristine", "edited"]


class SeedError(UserError):
    """A seed that cannot proceed."""


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
        raise SeedError(f"non-interactive seed requires {', '.join(missing)}")
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


# --- idempotency ----------------------------------------------------------


def _seed_doc_targets(repo_root: Path, config: IrminsulConfig) -> tuple[Path, Path]:
    return (
        layer_dir(repo_root, config, "foundation") / "principles.md",
        layer_dir(repo_root, config, "architecture") / "overview.md",
    )


def foundation_state(repo_root: Path, config: IrminsulConfig) -> FoundationState:
    """Classify the foundation docs `seed` would write.

    "pristine" means every existing target still carries a placeholder marker (or does
    not exist yet), so seeding replaces only the marked prompts. "edited" means a target
    carries none, so there is nothing marked to replace and overwriting it would lose
    real work.
    """
    for target in _seed_doc_targets(repo_root, config):
        if target.exists() and not placeholder_lines(target.read_text(encoding="utf-8")):
            return "edited"
    return "pristine"


Block = list[str]


def fill_placeholders(existing: str, rendered: str) -> str:
    """`existing` with the text its placeholder markers cover replaced by `rendered`'s.

    Only covered lines are removed, so an authored paragraph survives a seed. Each `##`
    section of `rendered` joins the section with the same heading, or is inserted after the
    section placed before it; a paragraph the doc already holds is not repeated, and a
    section the removal left empty is dropped. The frontmatter is `existing`'s.
    """
    head, body = _split_frontmatter(existing)
    covered = set(placeholder_lines(body))
    kept = "\n".join(
        line for number, line in enumerate(body.splitlines(), start=1) if number not in covered
    )
    preamble, sections = _sections(kept)
    new_preamble, new_sections = _sections(_split_frontmatter(rendered)[1])
    present = {_flat(block) for block in preamble}
    present.update(_flat(block) for _, blocks in sections for block in blocks)
    preamble.extend(block for block in new_preamble if _flat(block) not in present)
    cursor = 0
    for heading, blocks in new_sections:
        index = next(
            (i for i, (h, _) in enumerate(sections) if _flat([h]) == _flat([heading])), None
        )
        if index is None:
            sections.insert(cursor, (heading, []))
            index = cursor
        sections[index][1].extend(block for block in blocks if _flat(block) not in present)
        cursor = index + 1
    parts = ["\n".join(block) for block in preamble]
    for heading, blocks in sections:
        if blocks:
            parts.append(heading)
            parts.extend("\n".join(block) for block in blocks)
    return head + "\n\n".join(parts) + "\n"


def _split_frontmatter(text: str) -> tuple[str, str]:
    """(frontmatter with its delimiters and the blank line after, body)."""
    lines = text.splitlines()
    if lines and is_frontmatter_delimiter(lines[0]):
        for index, line in enumerate(lines[1:], start=1):
            if is_frontmatter_delimiter(line):
                return "\n".join(lines[: index + 1]) + "\n\n", "\n".join(lines[index + 1 :])
    return "", text


def _sections(body: str) -> tuple[list[Block], list[tuple[str, list[Block]]]]:
    """The paragraphs before the first `##` heading, then each `##` section's paragraphs.

    A paragraph runs to the next blank line outside a fence, so a fenced block is one
    paragraph with whatever directly precedes it.
    """
    preamble: list[Block] = []
    sections: list[tuple[str, list[Block]]] = []
    blocks = preamble
    current: Block = []
    fence = FenceTracker()
    for line in body.splitlines():
        if fence.classify(line) != "outside":
            current.append(line)
            continue
        if line.startswith("## "):
            if current:
                blocks.append(current)
            current = []
            sections.append((line.rstrip(), []))
            blocks = sections[-1][1]
        elif not line.strip():
            if current:
                blocks.append(current)
            current = []
        else:
            current.append(line)
    if current:
        blocks.append(current)
    return preamble, sections


def _flat(block: Block) -> str:
    return " ".join(" ".join(block).split())


# --- rendering & writing --------------------------------------------------


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

    Raises `SeedError` if the foundation docs have been edited away from
    scaffold defaults and neither `reseed` nor `merge` was requested.
    """
    principles_path, overview_path = _seed_doc_targets(repo_root, config)
    state = foundation_state(repo_root, config)
    written: list[Path] = []

    if state == "edited" and not reseed and not merge:
        raise SeedError(
            "Foundation docs have been edited away from scaffold defaults.\n"
            "Re-run with --reseed to overwrite them, or --merge to append "
            "this seed pass under a dated heading.",
            code=1,
        )

    if state == "edited" and merge:
        existing = principles_path.read_text(encoding="utf-8")
        sep = "" if existing.endswith("\n") else "\n"
        write_atomic(principles_path, existing + sep + _merge_block(answers))
        written.append(principles_path.relative_to(repo_root))
        return SeedResult(written=written)

    # "pristine" fills the marked prompts of each existing doc; --reseed on an "edited"
    # tree writes the docs fresh from the seed answers.
    context = {"project_name": answers.project_name, "seed": answers}
    for target, scaffold in (
        (principles_path, "docs/foundation/principles.md.j2"),
        (overview_path, "docs/architecture/overview.md.j2"),
    ):
        rendered = render_scaffold(scaffold, context)
        if state == "pristine" and target.exists():
            rendered = fill_placeholders(target.read_text(encoding="utf-8"), rendered)
        write_atomic(target, rendered)
        written.append(target.relative_to(repo_root))

    return SeedResult(written=written)
