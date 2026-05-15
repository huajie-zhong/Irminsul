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
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


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


class ClaimStateEnum(StrEnum):
    planned = "planned"
    implemented = "implemented"
    available = "available"
    enabled = "enabled"
    external = "external"


class RfcStateEnum(StrEnum):
    draft = "draft"
    open = "open"
    fcp = "fcp"
    accepted = "accepted"
    rejected = "rejected"
    withdrawn = "withdrawn"


class FollowupKindEnum(StrEnum):
    create = "create"
    update = "update"
    review = "review"


class FollowupEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    reason: str = ""
    kind: FollowupKindEnum = FollowupKindEnum.update


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    state: ClaimStateEnum
    kind: str = Field(min_length=1)
    claim: str = Field(min_length=1)
    evidence: list[str] = Field(min_length=1)


class DocFrontmatter(BaseModel):
    """Canonical frontmatter for a single doc atom (see Appendix B)."""

    model_config = ConfigDict(extra="allow")

    # Required
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    audience: AudienceEnum
    tier: int = Field(ge=1, le=4)
    status: StatusEnum

    # Optional but recommended
    describes: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    supersedes: list[str] = Field(default_factory=list)
    superseded_by: str | None = None
    tags: list[str] = Field(default_factory=list)
    related_adrs: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    requires_env: list[str] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    rfc_state: RfcStateEnum | None = None
    resolved_by: str | None = None
    decision_owner: str | None = None
    target_decision_date: str | None = None
    summary: str | None = None
    followups: list[FollowupEntry] | None = None
    implements: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_structured_claims(self) -> DocFrontmatter:
        claim_ids = [claim.id for claim in self.claims]
        duplicate_ids = sorted(
            {claim_id for claim_id in claim_ids if claim_ids.count(claim_id) > 1}
        )
        if duplicate_ids:
            raise ValueError(f"duplicate claim id(s): {duplicate_ids}")
        if self.rfc_state == RfcStateEnum.accepted and not self.resolved_by:
            raise ValueError("resolved_by is required when rfc_state is accepted")
        if self.target_decision_date is not None:
            try:
                _dt.date.fromisoformat(self.target_decision_date)
            except ValueError as exc:
                raise ValueError(f"target_decision_date must be YYYY-MM-DD ({exc})") from exc
        return self


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
