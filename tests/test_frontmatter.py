"""Tests for the frontmatter schema and parse_doc helper."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from irminsul.frontmatter import (
    DocFrontmatter,
    ParsedDoc,
    ParseFailure,
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


def test_expected_id_for_filename_stem() -> None:
    assert expected_id_for(Path("docs/20-components/composer.md")) == "composer"


def test_expected_id_for_index_uses_folder_name() -> None:
    assert expected_id_for(Path("docs/20-components/planner/INDEX.md")) == "planner"


def test_parse_doc_valid_returns_parsed(tmp_path: Path) -> None:
    md = tmp_path / "docs" / "x.md"
    md.parent.mkdir(parents=True)
    md.write_text(
        "---\n"
        "id: x\n"
        "title: X\n"
        "audience: explanation\n"
        "tier: 3\n"
        "status: stable\n"
        "---\n\n"
        "Body.\n",
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
