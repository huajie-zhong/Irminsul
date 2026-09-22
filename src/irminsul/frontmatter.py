"""Frontmatter schema and parser.

The canonical YAML frontmatter contract every doc atom must satisfy. Projects may attach additional keys
(`extra="allow"`); strictness comes from validating the canonical fields, not
from rejecting unknown ones.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import frontmatter as _pyfm
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


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
    accepted = "accepted"
    implemented = "implemented"
    rejected = "rejected"


RFC_STATE_TRANSITIONS: dict[RfcStateEnum, frozenset[RfcStateEnum]] = {
    RfcStateEnum.draft: frozenset({RfcStateEnum.accepted, RfcStateEnum.rejected}),
    RfcStateEnum.accepted: frozenset({RfcStateEnum.implemented, RfcStateEnum.rejected}),
    RfcStateEnum.implemented: frozenset(),
    RfcStateEnum.rejected: frozenset(),
}


class DirectionEnum(StrEnum):
    extends = "extends"
    revises = "revises"


class RequiredUpdateKindEnum(StrEnum):
    create = "create"
    update = "update"
    review = "review"


class RetirementKindEnum(StrEnum):
    cli_command = "cli-command"
    concept = "concept"


class RequiredUpdateEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    reason: str = ""
    kind: RequiredUpdateKindEnum = RequiredUpdateKindEnum.update


class RetirementEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9-]*$")
    kind: RetirementKindEnum
    surface_identity: str | None = Field(default=None, min_length=1)
    matches: list[str] = Field(min_length=1)
    guidance: str = Field(min_length=1)

    @field_validator("matches")
    @classmethod
    def _validate_matches(cls, value: list[str]) -> list[str]:
        normalized = [" ".join(match.split()) for match in value]
        if any(not match for match in normalized):
            raise ValueError("retirement matches must not be blank")
        if len(set(normalized)) != len(normalized):
            raise ValueError("retirement matches must be unique")
        return normalized

    @model_validator(mode="after")
    def _validate_surface_identity(self) -> RetirementEntry:
        if self.kind == RetirementKindEnum.cli_command and self.surface_identity is None:
            raise ValueError("surface_identity is required for cli-command retirements")
        if self.kind == RetirementKindEnum.concept and self.surface_identity is not None:
            raise ValueError("surface_identity is only valid for cli-command retirements")
        return self


class ClaimRelationEnum(StrEnum):
    """What happens when a claim and the evidence it cites disagree.

    Deliberately about conflict, not subject matter: the same sentence can be a mental
    model and a contract at once, and asking which it *is* invites an argument that
    asking who wins does not.
    """

    follows_evidence = "follows-evidence"
    """A report. The evidence wins; correcting the claim is routine maintenance.

    Reserved for reports that are expensive to derive. Cheap mechanical state belongs in
    `inventory:`, or nowhere — a pile of these is implementation state materialized
    through the claims field.
    """

    review_on_divergence = "review-on-divergence"
    """A semantic model. Neither side wins automatically; a reader decides."""

    governs_evidence = "governs-evidence"
    """A contract or invariant. The claim wins, so a violating implementation is
    suspect, and changing the claim is a change of intent rather than maintenance."""


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    state: ClaimStateEnum
    kind: str = Field(min_length=1)
    """What the claim is about. Free text, and orthogonal to `relation`."""
    relation: ClaimRelationEnum = ClaimRelationEnum.review_on_divergence
    """Who wins when this claim and its evidence disagree.

    Omitted means `review-on-divergence`: absent a declared authority, nothing infers a
    winner ([authority follows the kind of claim]).
    """
    claim: str = Field(min_length=1)
    evidence: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _relation_fits_state(self) -> Claim:
        if self.state == ClaimStateEnum.planned and self.relation == (
            ClaimRelationEnum.follows_evidence
        ):
            raise ValueError(
                f"claim '{self.id}' is planned and follows-evidence: a report cannot "
                "describe behaviour that does not exist yet. Planned behaviour the code "
                "must eventually have is governs-evidence."
            )
        return self


class InventoryEntry(BaseModel):
    """A curated *subset* of a code surface a doc deliberately calls out.

    `kind` selects the extractor (cli/http/exports/env-vars/mcp, or a generic kind);
    `source` is an optional glob pointing at the code that defines the surface
    (defaults to the doc's `describes`); `items` are the identities the doc claims
    exist. The check verifies each item still exists in code — it never demands the
    list be complete.

    Opt-in *watched surface* fields extend this to both other directions
    without changing the accuracy-only default: `complete: true` asks the check to
    flag any live identity that is neither in `items` nor `omit` (completeness);
    `omit` lists identities deliberately excluded; `fingerprints` pins each item's
    AST-normalized code shape (identity → hash) so a behavior change to a still-named
    item is flagged for re-read and re-pin (freshness).

    `explained_in` checks the prose instead of the frontmatter: each live identity must
    be named in a code span of this doc (`self`) or of any live doc (`any`).
    `foreign` lists flags that belong to other tools.
    """

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1)
    source: str | None = None
    items: list[str] = Field(default_factory=list)
    complete: bool = False
    omit: list[str] = Field(default_factory=list)
    fingerprints: dict[str, str] = Field(default_factory=dict)
    explained_in: Literal["self", "any"] | None = None
    foreign: list[str] = Field(default_factory=list)


class DocFrontmatter(BaseModel):
    """Canonical frontmatter for a single doc atom."""

    model_config = ConfigDict(extra="allow")

    # Required
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)

    status: StatusEnum

    # Optional but recommended
    describes: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    supersedes: list[str] = Field(default_factory=list)
    superseded_by: str | None = None
    tags: list[str] = Field(default_factory=list)
    #: The older spelling of `recommended_tests`, still read. Its name suggested it listed
    #: the tests covering the component, which no check establishes and nothing here runs.
    tests: list[str] = Field(default_factory=list)
    #: Test targets an agent editing this component should run — a recommendation, not an
    #: inventory and not proof of anything. Several docs may recommend one shared
    #: integration test. Left unset, the recommendations default to `owns_tests`.
    recommended_tests: list[str] = Field(default_factory=list)
    #: Test implementation files this doc maintains. Exactly one doc may own a test file,
    #: and recommending a test never confers ownership of it.
    owns_tests: list[str] = Field(default_factory=list)
    requires_env: list[str] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    rfc_state: RfcStateEnum | None = None
    affects: list[str] | None = None
    direction: DirectionEnum | None = None
    resolved_by: str | None = None
    target_decision_date: str | None = None
    summary: str | None = None
    required_updates: list[RequiredUpdateEntry] | None = None

    implements: list[str] = Field(default_factory=list)
    inventory: list[InventoryEntry] = Field(default_factory=list)
    retires: list[RetirementEntry] = Field(default_factory=list)

    @property
    def effective_recommended_tests(self) -> list[str]:
        """What this doc recommends running, whichever way it was written.

        `recommended_tests` wins, then the legacy `tests`, and otherwise the tests this
        doc owns — so an ordinary component declares one list, not two identical ones.
        A doc that sets both spellings is rejected rather than merged: they would be two
        sources of truth for one answer, and quietly combining them hides the drift.
        """
        if self.recommended_tests:
            return list(self.recommended_tests)
        if self.tests:
            return list(self.tests)
        return list(self.owns_tests)

    @model_validator(mode="after")
    def _validate_test_fields(self) -> DocFrontmatter:
        if self.tests and self.recommended_tests:
            raise ValueError(
                "tests and recommended_tests are the same field under two names; keep "
                "recommended_tests and delete tests"
            )
        duplicated = sorted(set(self.owns_tests) & set(self.describes))
        if duplicated:
            raise ValueError(
                f"owns_tests and describes both claim: {duplicated}; a file is owned as "
                "source or as a test, not both"
            )
        return self

    @model_validator(mode="after")
    def _validate_structured_claims(self) -> DocFrontmatter:
        claim_ids = [claim.id for claim in self.claims]
        duplicate_ids = sorted(
            {claim_id for claim_id in claim_ids if claim_ids.count(claim_id) > 1}
        )
        if duplicate_ids:
            raise ValueError(f"duplicate claim id(s): {duplicate_ids}")
        retirement_ids = [entry.id for entry in self.retires]
        duplicate_retirement_ids = sorted(
            {
                retirement_id
                for retirement_id in retirement_ids
                if retirement_ids.count(retirement_id) > 1
            }
        )
        if duplicate_retirement_ids:
            raise ValueError(f"duplicate retirement id(s): {duplicate_retirement_ids}")
        if (
            self.rfc_state in (RfcStateEnum.accepted, RfcStateEnum.implemented)
            and not self.resolved_by
        ):
            raise ValueError(f"resolved_by is required when rfc_state is {self.rfc_state.value}")
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
    body_offset: int = 1


@dataclass(frozen=True)
class ParseFailure:
    """A markdown file that exists under docs_root but couldn't be loaded.

    Either the YAML block was malformed or the schema rejected it. `data` is a
    machine-readable decomposition of the first error (always carries a
    "problem" key) for findings JSON.
    """

    path: Path  # repo-relative
    error: str
    data: dict[str, str] | None = None


def _format_validation_error(exc: ValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err["loc"]) or "<root>"
        parts.append(f"{loc}: {err['msg']}")
    return "; ".join(parts)


def _validation_error_data(exc: ValidationError) -> dict[str, str]:
    """Decompose the first validation error into string key/value pairs."""
    err = exc.errors()[0]
    field = ".".join(str(x) for x in err["loc"]) or "<root>"
    if err["type"] == "missing":
        return {"problem": "missing-field", "field": field}
    data = {"problem": "invalid-value", "field": field}
    if "input" in err:
        data["value"] = str(err["input"])
    return data


_FM_BOUNDARY_RE = re.compile(r"^-{3,}\s*$", re.MULTILINE)


def body_offset(text: str, body: str) -> int:
    # The parser also strips the blank lines after the closing delimiter, so the
    # offset can't be derived from the frontmatter's length.
    if not body:
        return text.count("\n") + 1
    boundaries = list(_FM_BOUNDARY_RE.finditer(text))
    search_from = boundaries[1].end() if len(boundaries) >= 2 else 0
    index = text.find(body, search_from)
    if index < 0:
        index = text.find(body)
    if index < 0:
        return 1
    return text.count("\n", 0, index) + 1


def parse_doc(absolute_path: Path, repo_root: Path) -> ParsedDoc | ParseFailure:
    """Read and validate a single doc file.

    `absolute_path` is the file on disk; `repo_root` is the root used to compute
    the repo-relative path stored on the result.
    """
    rel = absolute_path.relative_to(repo_root)
    try:
        text = absolute_path.read_text(encoding="utf-8")
        post = _pyfm.loads(text)
    except Exception as e:
        return ParseFailure(
            path=rel,
            error=f"{type(e).__name__}: {e}",
            data={"problem": "parse-error"},
        )

    raw: dict[str, Any] = dict(post.metadata)
    if not raw:
        return ParseFailure(path=rel, error="missing frontmatter")

    try:
        fm = DocFrontmatter.model_validate(raw)
    except ValidationError as e:
        return ParseFailure(
            path=rel,
            error=_format_validation_error(e),
            data=_validation_error_data(e),
        )

    return ParsedDoc(
        path=rel,
        frontmatter=fm,
        body=post.content,
        body_offset=body_offset(text, post.content),
    )


def expected_id_for(repo_relative_path: Path) -> str:
    """The frontmatter `id` Irminsul expects given a doc's location.

    `INDEX.md` files take the parent folder name; everything else uses the
    filename stem.
    """
    if repo_relative_path.name == "INDEX.md":
        return repo_relative_path.parent.name
    return repo_relative_path.stem
