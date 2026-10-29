"""Frontmatter schema and parser.

The canonical YAML frontmatter contract every doc atom must satisfy. Projects may attach additional keys
(`extra="allow"`); strictness comes from validating the canonical fields, not
from rejecting unknown ones.
"""

from __future__ import annotations

import datetime as _dt
import threading
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from ruamel.yaml import YAML
from ruamel.yaml.constructor import ConstructorError, DuplicateKeyError
from ruamel.yaml.error import MarkedYAMLError, YAMLError
from ruamel.yaml.nodes import MappingNode, ScalarNode, SequenceNode

from irminsul.frontmatter_edit import is_frontmatter_delimiter, split_frontmatter


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
#: Decided to be built: such an RFC declares `affects`, `resolved_by` and `required_updates`.
RFC_COMMITTED_STATES = frozenset({RfcStateEnum.accepted, RfcStateEnum.implemented})
#: Still open, so its plan and requirements are live work.
RFC_OPEN_STATES = frozenset({RfcStateEnum.draft, RfcStateEnum.accepted})
#: The states a person decides; `change finalize` alone writes `implemented`.
RFC_DECIDED_STATES = frozenset({RfcStateEnum.accepted, RfcStateEnum.rejected})
RFC_TERMINAL_STATES = frozenset({RfcStateEnum.implemented, RfcStateEnum.rejected})
RFC_RESOLVED_STATES = RFC_COMMITTED_STATES | {RfcStateEnum.rejected}


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
    """A phrase a stable decision record retires, and what to use instead.

    `matches` are the exact phrases `retired-references` refuses in current guidance,
    `guidance` says what replaces them, and a `cli-command` also names `surface_identity`,
    the identity `irminsul surface cli` prints without the executable name, so the check can
    tell when the command is live again. The schema validates the record, its unique `matches`
    and the uniqueness of its `id` within a doc; `retired-references` decides whether the
    owner is an authoritative record.
    """

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
    pinned: dict[str, str] = Field(default_factory=dict)
    """Each evidence file's normalized hash when the claim was last checked against it.

    Written by `anchors --re-pin`, never by hand. While a file still has the hash it was
    pinned at, a commit to it does not re-ask the claim. Deliberately unvalidated beyond
    its shape: a pin that matches nothing only stops suppressing drift, while a schema
    error here would unparse the doc and so put it out of reach of the re-pin that
    repairs it.
    """

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

    `kind` selects the extractor (cli/http/exports/env-vars/mcp, or a surface rule's kind);
    `source` is an optional glob pointing at the code that defines the surface
    (defaults to the doc's `describes`); `items` are the identities the doc claims
    exist. The check verifies each item still exists in code — it never demands the
    list be complete.

    Opt-in *watched surface* fields extend this to completeness without changing the
    accuracy-only default: `complete: true` asks the check to flag any live identity
    that is neither in `items` nor `omit`; `omit` lists identities deliberately
    excluded.

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
    explained_in: Literal["self", "any"] | None = None
    foreign: list[str] = Field(default_factory=list)


class DocFrontmatter(BaseModel):
    model_config = ConfigDict(extra="allow")

    # Required
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)

    status: StatusEnum

    # Optional but recommended
    describes: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    supersedes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    #: Test targets an agent editing this component should run — a recommendation, not an
    #: inventory and not proof of anything. Several docs may recommend one shared
    #: integration test. Left unset, the recommendations default to `owns_tests`.
    recommended_tests: list[str] = Field(default_factory=list)
    #: Test implementation files this doc maintains. Exactly one doc may own a test file,
    #: and recommending a test never confers ownership of it.
    owns_tests: list[str] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    rfc_state: RfcStateEnum | None = None
    #: The component ids a proposal intends to change; `[]` means intentionally none.
    affects: list[str] | None = None
    #: Whether a proposal `extends` the foundation layer or `revises` it.
    direction: DirectionEnum | None = None
    resolved_by: str | None = None
    #: `YYYY-MM-DD`; on a draft RFC, `rfc-follow-through` warns once it has passed.
    target_decision_date: str | None = None
    #: The one sentence the agent manifest shows for the doc and `context --topic` searches.
    summary: str | None = None
    required_updates: list[RequiredUpdateEntry] | None = None
    #: `small` or `large` on an RFC, how much of its owner's part the owner reads. Left a
    #: string, so `rfc-structure` reports a value it does not know instead of the doc
    #: failing to parse and leaving the graph.
    weight: str | None = None

    implements: list[str] = Field(default_factory=list)
    inventory: list[InventoryEntry] = Field(default_factory=list)
    retires: list[RetirementEntry] = Field(default_factory=list)

    @property
    def effective_recommended_tests(self) -> list[str]:
        """What this doc recommends running: `recommended_tests`, and otherwise the tests
        it owns — so an ordinary component declares one list, not two identical ones."""
        if self.recommended_tests:
            return list(self.recommended_tests)
        return list(self.owns_tests)

    @model_validator(mode="after")
    def _validate_test_fields(self) -> DocFrontmatter:
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
        if self.rfc_state in RFC_COMMITTED_STATES and not self.resolved_by:
            raise ValueError(f"resolved_by is required when rfc_state is {self.rfc_state.value}")
        if self.target_decision_date is not None:
            try:
                _dt.date.fromisoformat(self.target_decision_date)
            except ValueError as exc:
                raise ValueError(f"target_decision_date must be YYYY-MM-DD ({exc})") from exc
        return self


RETIRED_FIELDS: Final[dict[str, str]] = {
    "tests": "rename it to `recommended_tests`",
    "superseded_by": "delete it; the newer doc's `supersedes` states the relation",
    "requires_env": (
        "declare an `inventory:` entry of kind `env-vars`, which `inventory-drift` checks "
        "against the code"
    ),
}
"""Top-level keys no longer read, each with what replaces it.

A doc that still sets one is reported by `frontmatter/retired-field` instead of being
ignored, because a key that does nothing reads as if it works. A project's own keys are
still allowed; only these, which Irminsul once read, are refused."""

RETIRED_INVENTORY_FIELDS: Final[dict[str, str]] = {
    "fingerprints": (
        "delete it and bind the symbol with an anchor, which pins its normalized shape; "
        "`irminsul anchors --suggest` names the file"
    ),
}
"""Keys of an `inventory:` entry no longer read, each with what replaces it."""


@dataclass(frozen=True)
class ParsedDoc:
    """A markdown file whose frontmatter parsed and validated cleanly."""

    path: Path  # repo-relative
    frontmatter: DocFrontmatter
    body: str
    body_offset: int = 1
    retired_fields: tuple[str, ...] = ()
    """Retired keys the doc set, set aside before validation: a top-level key by name,
    an inventory entry's as `inventory.<key>`."""


@dataclass(frozen=True)
class ParseFailure:
    """A markdown file that exists under docs_root but couldn't be loaded.

    Either the YAML block was malformed or the schema rejected it. `data` is a
    machine-readable decomposition of the first error for findings JSON: its "kind" is
    `parse-error`, `missing-field` or `invalid-value`, with the offending field and value.
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
    err = exc.errors()[0]
    field = ".".join(str(x) for x in err["loc"]) or "<root>"
    if err["type"] == "missing":
        return {"kind": "missing-field", "field": field}
    data = {"kind": "invalid-value", "field": field}
    if "input" in err:
        data["value"] = str(err["input"])
    return data


class FrontmatterError(ValueError):
    """A frontmatter block that exists but cannot be read; the message says where and why."""


_FIRST_YAML_LINE = 2
"""The file line the block's first YAML line sits on: the opening delimiter is line 1."""


_loaders = threading.local()


def _safe_yaml() -> YAML:
    """A YAML 1.2 loader that builds plain Python values.

    Pure Python, so an error reads the same whether or not the optional C parser is
    installed. The message is part of a finding's identity. One per thread, because
    building one costs more than reading a typical block and a loader is not safe to
    share between threads.
    """
    if not hasattr(_loaders, "yaml"):
        _loaders.yaml = YAML(typ="safe", pure=True)
    return cast("YAML", _loaders.yaml)


def _describe_yaml_error(error: MarkedYAMLError) -> str:
    mark = error.problem_mark or error.context_mark
    where = f"line {mark.line + _FIRST_YAML_LINE}, column {mark.column + 1}: " if mark else ""
    problem = error.problem or "invalid YAML"
    if error.context and not isinstance(error, DuplicateKeyError):
        problem = f"{error.context}: {problem}"
    if isinstance(error, ConstructorError) and mark is not None and _opens_with_tag(mark):
        problem += "; a value that starts with `!` is read as a YAML tag, so put it in quotes"
    return f"{where}{problem}"


def _opens_with_tag(mark: Any) -> bool:
    """Whether the YAML text at `mark` starts with `!`, which the loader reads as a tag.

    A node with an anchor ahead of its tag is marked at the anchor, so that spelling is not
    recognised.
    """
    buffer = getattr(mark, "buffer", None)
    return isinstance(buffer, str) and buffer[mark.pointer : mark.pointer + 1] == "!"


def read_frontmatter(text: str) -> tuple[dict[str, Any], str, int] | None:
    """A doc's metadata, body and the file line its body starts on; None without frontmatter.

    The block opens on line 1 and ends at the next delimiter line. An opening `---`
    anywhere else, even after a blank line or a byte order mark, is an error and not an
    absent block, because GitHub and the fixes that rewrite a block both require line 1.
    YAML is read as 1.2, so `no` is a string and `0123` is the number 123. A duplicate key is
    an error, because the loader would keep the last and leave the first as dead text. The
    body is what follows the block with its surrounding whitespace removed, which is why its
    start line is measured here, against the original text. Raises `FrontmatterError`,
    naming the file line, for a block that cannot be used.
    """
    lines = text.splitlines()
    if not lines or not is_frontmatter_delimiter(lines[0]):
        displaced = text.lstrip("\ufeff").lstrip()
        if displaced and is_frontmatter_delimiter(displaced.splitlines()[0]):
            lead = text[: len(text) - len(displaced)]
            bom = " (a byte order mark precedes it)" if lead.startswith("\ufeff") else ""
            raise FrontmatterError(
                "frontmatter must start on line 1, column 1; the opening `---` is at "
                f"line {lead.count('\n') + 1}, column {len(lead) - lead.rfind('\n')}{bom}"
            )
        return None

    try:
        raw_yaml, rest = split_frontmatter(text)
    except ValueError as exc:
        raise FrontmatterError(
            "the frontmatter block never closes: no second `---` line follows it"
        ) from exc
    try:
        data = _safe_yaml().load(raw_yaml)
    except MarkedYAMLError as exc:
        raise FrontmatterError(_describe_yaml_error(exc)) from exc
    if data is None or data == {}:
        return None
    if not isinstance(data, dict):
        raise FrontmatterError(
            f"frontmatter must be a mapping of keys, not a {type(data).__name__}"
        )

    body = rest.strip()
    if not body:
        return data, body, text.count("\n") + 1
    return data, body, text.count("\n", 0, len(text) - len(rest.lstrip())) + 1


def entry_line(path: Path, key: str, value: str | None = None) -> int | None:
    """The file line of `key` in the frontmatter of the file at `path`.

    Given `value`, the line of that entry in the key's list instead, or of the key's own
    value when it is a scalar. None when the file cannot be read, or has no such key or
    entry: a caller picks its own fallback line.
    """
    try:
        raw_yaml, _ = split_frontmatter(path.read_text(encoding="utf-8"))
        root = _safe_yaml().compose(raw_yaml)
    except (OSError, ValueError, YAMLError):
        return None
    if not isinstance(root, MappingNode):
        return None
    for key_node, value_node in root.value:
        if not (isinstance(key_node, ScalarNode) and key_node.value == key):
            continue
        if value is None:
            return int(key_node.start_mark.line) + _FIRST_YAML_LINE
        entries = value_node.value if isinstance(value_node, SequenceNode) else [value_node]
        for entry in entries:
            if isinstance(entry, ScalarNode) and entry.value == value:
                return int(entry.start_mark.line) + _FIRST_YAML_LINE
        return None
    return None


def parse_doc(absolute_path: Path, repo_root: Path) -> ParsedDoc | ParseFailure:
    """Read and validate a single doc file.

    `absolute_path` is the file on disk; `repo_root` is the root used to compute
    the repo-relative path stored on the result.
    """
    rel = absolute_path.relative_to(repo_root)
    try:
        parsed = read_frontmatter(absolute_path.read_text(encoding="utf-8"))
    except Exception as e:
        return ParseFailure(
            path=rel,
            error=str(e) if isinstance(e, FrontmatterError) else f"{type(e).__name__}: {e}",
            data={"kind": "parse-error"},
        )
    if parsed is None:
        return ParseFailure(path=rel, error="missing frontmatter")
    raw, body, offset = parsed
    retired = _set_aside_retired(raw)

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
        body=body,
        body_offset=offset,
        retired_fields=retired,
    )


def _set_aside_retired(raw: dict[str, Any]) -> tuple[str, ...]:
    """Remove every retired key from `raw` and name what was removed.

    Removed rather than left for the schema: an inventory entry forbids unknown keys, so
    a retired one there would fail validation and drop the doc from the graph, and the
    finding that names its replacement would never be reached.
    """
    found = [key for key in raw if key in RETIRED_FIELDS]
    for key in found:
        del raw[key]
    inventory = raw.get("inventory")
    if isinstance(inventory, list):
        cleaned: list[Any] = []
        for entry in inventory:
            if isinstance(entry, dict):
                retired = [key for key in entry if key in RETIRED_INVENTORY_FIELDS]
                entry = {k: v for k, v in entry.items() if k not in retired}
                found.extend(
                    f"inventory.{key}" for key in retired if f"inventory.{key}" not in found
                )
            cleaned.append(entry)
        raw["inventory"] = cleaned
    return tuple(found)


def expected_id_for(repo_relative_path: Path) -> str:
    """The frontmatter `id` Irminsul expects given a doc's location.

    `INDEX.md` files take the parent folder name; everything else uses the
    filename stem.
    """
    if repo_relative_path.name == "INDEX.md":
        return repo_relative_path.parent.name
    return repo_relative_path.stem
