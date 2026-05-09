"""Frontmatter schema and parser.

Implements Appendix B of `Irminsul-reference.md`: the canonical YAML frontmatter
contract every doc atom must satisfy. Projects may attach additional keys
(`extra="allow"`); strictness comes from validating the canonical fields, not
from rejecting unknown ones.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import frontmatter as _pyfm
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class AudienceEnum(StrEnum):
    tutorial = "tutorial"
    howto = "howto"
    reference = "reference"
    explanation = "explanation"
    adr = "adr"
    runbook = "runbook"
    meta = "meta"


class StatusEnum(StrEnum):
    draft = "draft"
    stable = "stable"
    deprecated = "deprecated"
    removed = "removed"


class DocFrontmatter(BaseModel):
    """Canonical frontmatter for a single doc atom (see Appendix B)."""

    model_config = ConfigDict(extra="allow")

    # Required
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    audience: AudienceEnum
    tier: int = Field(ge=1, le=4)
    status: StatusEnum
    owner: str = Field(min_length=1)
    last_reviewed: _dt.date

    # Optional but recommended
    describes: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    supersedes: list[str] = Field(default_factory=list)
    superseded_by: str | None = None
    tags: list[str] = Field(default_factory=list)
    related_adrs: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class ParsedDoc:
    """A markdown file whose frontmatter parsed and validated cleanly."""

    path: Path  # repo-relative
    frontmatter: DocFrontmatter
    body: str


@dataclass(frozen=True)
class ParseFailure:
    """A markdown file that exists under docs_root but couldn't be loaded.

    Either the YAML block was malformed or the schema rejected it.
    """

    path: Path  # repo-relative
    error: str


def _format_validation_error(exc: ValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err["loc"]) or "<root>"
        parts.append(f"{loc}: {err['msg']}")
    return "; ".join(parts)


def parse_doc(absolute_path: Path, repo_root: Path) -> ParsedDoc | ParseFailure:
    """Read and validate a single doc file.

    `absolute_path` is the file on disk; `repo_root` is the root used to compute
    the repo-relative path stored on the result.
    """
    rel = absolute_path.relative_to(repo_root)
    try:
        with absolute_path.open("r", encoding="utf-8") as f:
            post = _pyfm.load(f)
    except Exception as e:
        return ParseFailure(path=rel, error=f"{type(e).__name__}: {e}")

    raw: dict[str, Any] = dict(post.metadata)
    if not raw:
        return ParseFailure(path=rel, error="missing frontmatter")

    try:
        fm = DocFrontmatter.model_validate(raw)
    except ValidationError as e:
        return ParseFailure(path=rel, error=_format_validation_error(e))

    return ParsedDoc(path=rel, frontmatter=fm, body=post.content)


def expected_id_for(repo_relative_path: Path) -> str:
    """The frontmatter `id` Irminsul expects given a doc's location.

    `INDEX.md` files take the parent folder name; everything else uses the
    filename stem.
    """
    if repo_relative_path.name == "INDEX.md":
        return repo_relative_path.parent.name
    return repo_relative_path.stem
