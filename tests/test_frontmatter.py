"""Tests for the frontmatter schema and parse_doc helper."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from irminsul.frontmatter import (
    RFC_STATE_TRANSITIONS,
    DocFrontmatter,
    ParsedDoc,
    ParseFailure,
    RetirementKindEnum,
    RfcStateEnum,
    expected_id_for,
    parse_doc,
)


def _good_payload() -> dict[str, object]:
    return {
        "id": "composer",
        "title": "Composer",
        "status": "stable",
    }


def test_doc_frontmatter_accepts_minimal_required_fields() -> None:
    fm = DocFrontmatter.model_validate(_good_payload())
    assert fm.id == "composer"

    assert fm.describes == []
    assert fm.depends_on == []


def test_doc_frontmatter_allows_extra_keys() -> None:
    payload = _good_payload() | {"custom_company_field": "ok"}
    fm = DocFrontmatter.model_validate(payload)
    # Extra keys are preserved on the model under model_extra.
    assert fm.model_extra is not None
    assert fm.model_extra["custom_company_field"] == "ok"


def test_doc_frontmatter_accepts_required_updates() -> None:
    payload = _good_payload() | {
        "required_updates": [
            {
                "path": "docs/components/widget.md",
                "reason": "Document the new widget behavior",
                "kind": "update",
            }
        ]
    }
    fm = DocFrontmatter.model_validate(payload)
    assert fm.required_updates is not None
    assert fm.required_updates[0].path == "docs/components/widget.md"


def test_doc_frontmatter_accepts_retirement_tombstones() -> None:
    payload = _good_payload() | {
        "retires": [
            {
                "id": "old-render-command",
                "kind": "cli-command",
                "surface_identity": "render",
                "matches": ["irminsul   render", "irm render"],
                "guidance": "Use irminsul surface instead.",
            }
        ]
    }

    fm = DocFrontmatter.model_validate(payload)

    assert fm.retires[0].kind == RetirementKindEnum.cli_command
    assert fm.retires[0].surface_identity == "render"
    assert fm.retires[0].matches == ["irminsul render", "irm render"]


@pytest.mark.parametrize(
    "entry",
    [
        {
            "id": "Uppercase",
            "kind": "concept",
            "matches": ["old idea"],
            "guidance": "Use the new idea.",
        },
        {
            "id": "old-idea",
            "kind": "other",
            "matches": ["old idea"],
            "guidance": "Use the new idea.",
        },
        {
            "id": "old-command",
            "kind": "cli-command",
            "matches": ["irminsul old"],
            "guidance": "Use irminsul new.",
        },
        {
            "id": "old-idea",
            "kind": "concept",
            "surface_identity": "old",
            "matches": ["old idea"],
            "guidance": "Use the new idea.",
        },
        {
            "id": "old-idea",
            "kind": "concept",
            "matches": [],
            "guidance": "Use the new idea.",
        },
        {
            "id": "old-idea",
            "kind": "concept",
            "matches": ["old idea", "old   idea"],
            "guidance": "Use the new idea.",
        },
        {
            "id": "old-idea",
            "kind": "concept",
            "matches": ["old idea"],
            "guidance": "",
        },
    ],
)
def test_doc_frontmatter_rejects_invalid_retirement_tombstone(
    entry: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        DocFrontmatter.model_validate(_good_payload() | {"retires": [entry]})


def test_doc_frontmatter_rejects_duplicate_retirement_ids() -> None:
    entry = {
        "id": "old-idea",
        "kind": "concept",
        "matches": ["old idea"],
        "guidance": "Use the new idea.",
    }
    with pytest.raises(ValidationError, match="duplicate retirement"):
        DocFrontmatter.model_validate(_good_payload() | {"retires": [entry, entry]})


def test_doc_frontmatter_treats_followups_as_extra_key() -> None:
    payload = _good_payload() | {"followups": []}
    fm = DocFrontmatter.model_validate(payload)
    assert "followups" not in DocFrontmatter.model_fields
    assert fm.required_updates is None
    assert fm.model_extra is not None
    assert fm.model_extra["followups"] == []


def test_rfc_state_accepted_requires_resolved_by() -> None:
    payload = _good_payload() | {"rfc_state": "accepted"}
    with pytest.raises(ValidationError, match="resolved_by"):
        DocFrontmatter.model_validate(payload)


def test_rfc_state_implemented_requires_resolved_by() -> None:
    payload = _good_payload() | {"rfc_state": "implemented"}
    with pytest.raises(ValidationError, match="resolved_by"):
        DocFrontmatter.model_validate(payload)


def test_rfc_state_implemented_with_resolved_by_parses() -> None:
    payload = _good_payload() | {
        "rfc_state": "implemented",
        "resolved_by": "docs/decisions/0001-adr.md",
    }
    fm = DocFrontmatter.model_validate(payload)
    assert fm.rfc_state == RfcStateEnum.implemented


def test_retired_rfc_state_aliases_are_rejected() -> None:
    for state in ("open", "fcp", "withdrawn"):
        with pytest.raises(ValidationError):
            DocFrontmatter.model_validate(_good_payload() | {"rfc_state": state})


def test_rfc_state_transitions_shape() -> None:
    assert RFC_STATE_TRANSITIONS[RfcStateEnum.draft] == frozenset(
        {RfcStateEnum.accepted, RfcStateEnum.rejected}
    )
    assert RFC_STATE_TRANSITIONS[RfcStateEnum.accepted] == frozenset(
        {RfcStateEnum.implemented, RfcStateEnum.rejected}
    )
    assert RFC_STATE_TRANSITIONS[RfcStateEnum.implemented] == frozenset()
    assert RFC_STATE_TRANSITIONS[RfcStateEnum.rejected] == frozenset()


def test_affects_and_direction_parse() -> None:
    payload = _good_payload() | {"affects": ["auth"], "direction": "extends"}
    fm = DocFrontmatter.model_validate(payload)
    assert fm.affects == ["auth"]
    assert fm.direction is not None and fm.direction.value == "extends"


def test_affects_defaults_to_none() -> None:
    fm = DocFrontmatter.model_validate(_good_payload())
    assert fm.affects is None
    assert fm.direction is None


def test_direction_rejects_unknown_value() -> None:
    payload = _good_payload() | {"direction": "sideways"}
    with pytest.raises(ValidationError):
        DocFrontmatter.model_validate(payload)


def test_expected_id_for_filename_stem() -> None:
    assert expected_id_for(Path("docs/components/composer.md")) == "composer"


def test_expected_id_for_index_uses_folder_name() -> None:
    assert expected_id_for(Path("docs/components/planner/INDEX.md")) == "planner"


def test_parse_doc_valid_returns_parsed(tmp_path: Path) -> None:
    md = tmp_path / "docs" / "x.md"
    md.parent.mkdir(parents=True)
    md.write_text(
        "---\nid: x\ntitle: X\nstatus: stable\n---\n\nBody.\n",
        encoding="utf-8",
    )
    result = parse_doc(md, tmp_path)
    assert isinstance(result, ParsedDoc)
    assert result.frontmatter.id == "x"
    assert result.body.strip() == "Body."


def test_parse_doc_missing_frontmatter(tmp_path: Path) -> None:
    md = tmp_path / "docs" / "x.md"
    md.parent.mkdir(parents=True)
    md.write_text("# just a body\n", encoding="utf-8")
    result = parse_doc(md, tmp_path)
    assert isinstance(result, ParseFailure)
    assert "missing frontmatter" in result.error


def test_parse_doc_invalid_frontmatter(tmp_path: Path) -> None:
    md = tmp_path / "docs" / "x.md"
    md.parent.mkdir(parents=True)
    md.write_text(
        "---\nid: x\n---\n\nbody\n",
        encoding="utf-8",
    )
    result = parse_doc(md, tmp_path)
    assert isinstance(result, ParseFailure)
    # The error message names at least one offending field.
    assert "title" in result.error


def test_a_planned_claim_cannot_follow_its_evidence() -> None:
    """A report cannot describe behaviour that does not exist yet."""
    import pytest

    from irminsul.frontmatter import DocFrontmatter

    with pytest.raises(Exception) as caught:
        DocFrontmatter(
            id="d",
            title="D",
            status="stable",
            claims=[
                {
                    "id": "future",
                    "state": "planned",
                    "kind": "feature",
                    "relation": "follows-evidence",
                    "claim": "It will do the thing.",
                    "evidence": ["src/a.py"],
                }
            ],
        )
    assert "planned" in str(caught.value)


def test_an_omitted_relation_means_review_on_divergence() -> None:
    """Nothing should infer an authority nobody declared."""
    from irminsul.frontmatter import ClaimRelationEnum, DocFrontmatter

    doc = DocFrontmatter(
        id="d",
        title="D",
        status="stable",
        claims=[
            {
                "id": "c",
                "state": "implemented",
                "kind": "invariant",
                "claim": "It holds.",
                "evidence": ["src/a.py"],
            }
        ],
    )
    assert doc.claims[0].relation is ClaimRelationEnum.review_on_divergence
