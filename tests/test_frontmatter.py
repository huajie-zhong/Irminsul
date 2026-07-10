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
    RfcStateEnum,
    canonical_rfc_state,
    expected_id_for,
    parse_doc,
)


def _good_payload() -> dict[str, object]:
    return {
        "id": "composer",
        "title": "Composer",
        "audience": "explanation",
        "tier": 3,
        "status": "stable",
    }


def test_doc_frontmatter_accepts_minimal_required_fields() -> None:
    fm = DocFrontmatter.model_validate(_good_payload())
    assert fm.id == "composer"
    assert fm.tier == 3
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
                "path": "docs/20-components/widget.md",
                "reason": "Document the new widget behavior",
                "kind": "update",
            }
        ]
    }
    fm = DocFrontmatter.model_validate(payload)
    assert fm.required_updates is not None
    assert fm.required_updates[0].path == "docs/20-components/widget.md"


def test_doc_frontmatter_treats_followups_as_extra_key() -> None:
    payload = _good_payload() | {"followups": []}
    fm = DocFrontmatter.model_validate(payload)
    assert "followups" not in DocFrontmatter.model_fields
    assert fm.required_updates is None
    assert fm.model_extra is not None
    assert fm.model_extra["followups"] == []


def test_doc_frontmatter_rejects_missing_audience() -> None:
    payload = _good_payload()
    del payload["audience"]
    with pytest.raises(ValidationError):
        DocFrontmatter.model_validate(payload)


def test_doc_frontmatter_rejects_bad_tier() -> None:
    payload = _good_payload() | {"tier": 99}
    with pytest.raises(ValidationError):
        DocFrontmatter.model_validate(payload)


def test_doc_frontmatter_rejects_bad_audience_enum() -> None:
    payload = _good_payload() | {"audience": "marketing"}
    with pytest.raises(ValidationError):
        DocFrontmatter.model_validate(payload)


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
        "resolved_by": "docs/50-decisions/0001-adr.md",
    }
    fm = DocFrontmatter.model_validate(payload)
    assert fm.rfc_state == RfcStateEnum.implemented


def test_deprecated_rfc_states_still_parse() -> None:
    for state in ("open", "fcp", "withdrawn"):
        fm = DocFrontmatter.model_validate(_good_payload() | {"rfc_state": state})
        assert fm.rfc_state is not None and fm.rfc_state.value == state


def test_canonical_rfc_state_mapping() -> None:
    assert canonical_rfc_state(RfcStateEnum.open) == RfcStateEnum.draft
    assert canonical_rfc_state(RfcStateEnum.fcp) == RfcStateEnum.draft
    assert canonical_rfc_state(RfcStateEnum.withdrawn) == RfcStateEnum.rejected
    assert canonical_rfc_state(RfcStateEnum.accepted) == RfcStateEnum.accepted


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
    assert expected_id_for(Path("docs/20-components/composer.md")) == "composer"


def test_expected_id_for_index_uses_folder_name() -> None:
    assert expected_id_for(Path("docs/20-components/planner/INDEX.md")) == "planner"


def test_parse_doc_valid_returns_parsed(tmp_path: Path) -> None:
    md = tmp_path / "docs" / "x.md"
    md.parent.mkdir(parents=True)
    md.write_text(
        "---\nid: x\ntitle: X\naudience: explanation\ntier: 3\nstatus: stable\n---\n\nBody.\n",
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
        "---\nid: x\ntier: 99\n---\n\nbody\n",
        encoding="utf-8",
    )
    result = parse_doc(md, tmp_path)
    assert isinstance(result, ParseFailure)
    # The error message names at least one offending field.
    assert "tier" in result.error or "title" in result.error or "audience" in result.error
