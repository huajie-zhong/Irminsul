"""Unit tests for the requirements section parser (RFC-0030)."""

from __future__ import annotations

from pathlib import Path

from irminsul.docgraph_index import parse_requirements

_GOOD = """# RFC

## Summary

Words.

## Requirements

### Requirement: SSO login
ID: sso-login
Provenance: code

Users SHALL authenticate through the identity provider.

#### Scenario: Valid assertion
- **WHEN** the provider returns a valid assertion
- **THEN** a session is established

#### Scenario: Expired assertion
- **WHEN** the provider returns an expired assertion
- **THEN** authentication is rejected

### Requirement: Audit trail
ID: audit-trail
Provenance: adr

Logins MUST be recorded.

#### Scenario: Login recorded
- **WHEN** a session is established
- **THEN** an audit event is written

## Drawbacks

None.
"""


def test_parses_requirements_and_scenarios() -> None:
    section = parse_requirements(_GOOD)
    assert section is not None
    assert section.disposition is None
    assert [r.req_id for r in section.requirements] == ["sso-login", "audit-trail"]

    sso = section.requirements[0]
    assert sso.title == "SSO login"
    assert sso.provenance == "code"
    assert sso.has_behavior_keyword
    assert [s.name for s in sso.scenarios] == ["Valid assertion", "Expired assertion"]
    assert all(s.has_when and s.has_then for s in sso.scenarios)

    audit = section.requirements[1]
    assert audit.provenance == "adr"
    assert audit.has_behavior_keyword  # MUST counts


def test_no_section_returns_none() -> None:
    assert parse_requirements("# RFC\n\n## Summary\n\nWords.\n") is None


def test_section_ends_at_next_h2() -> None:
    body = _GOOD + "\n### Requirement: After the section\nID: late\n"
    section = parse_requirements(body)
    assert section is not None
    assert [r.req_id for r in section.requirements] == ["sso-login", "audit-trail"]


def test_fenced_examples_are_ignored() -> None:
    body = (
        "# RFC\n\n## Design\n\n"
        "```markdown\n## Requirements\n\n### Requirement: Quoted\nID: quoted\n```\n\n"
        "## Drawbacks\n"
    )
    assert parse_requirements(body) is None


def test_disposition_sentence() -> None:
    body = (
        "# RFC\n\n## Requirements\n\n"
        "No new behavioral requirements: this refactor preserves the existing contract.\n"
    )
    section = parse_requirements(body)
    assert section is not None
    assert section.disposition is not None
    assert section.disposition.startswith("No new behavioral requirements")
    assert section.requirements == ()


def test_missing_when_then_detected() -> None:
    body = (
        "# RFC\n\n## Requirements\n\n"
        "### Requirement: Half a scenario\nID: half\nProvenance: code\n\n"
        "It SHALL work.\n\n"
        "#### Scenario: Only when\n- **WHEN** something happens\n"
    )
    section = parse_requirements(body)
    assert section is not None
    [req] = section.requirements
    [scenario] = req.scenarios
    assert scenario.has_when and not scenario.has_then


def test_underscore_emphasis_keywords_count() -> None:
    body = (
        "# RFC\n\n## Requirements\n\n"
        "### Requirement: Emphasised\nID: emphasised\nProvenance: code\n\n"
        "It _SHALL_ work.\n\n"
        "#### Scenario: Emphasised too\n- _WHEN_ something happens\n- _THEN_ it works\n"
    )
    section = parse_requirements(body)
    assert section is not None
    [req] = section.requirements
    assert req.has_behavior_keyword
    [scenario] = req.scenarios
    assert scenario.has_when and scenario.has_then


def test_uppercase_section_heading_is_parsed() -> None:
    from irminsul.docgraph import DocNode
    from irminsul.docgraph_index import build_requirements
    from irminsul.frontmatter import DocFrontmatter

    body = "# RFC\n\n## REQUIREMENTS\n\nNo new behavioral requirements: nothing changes.\n"
    section = parse_requirements(body)
    assert section is not None
    assert section.disposition is not None

    fm = DocFrontmatter.model_validate(
        {"id": "x", "title": "X", "audience": "explanation", "tier": 2, "status": "draft"}
    )
    node = DocNode(id="x", path=Path("docs/x.md"), frontmatter=fm, body=body)
    assert "x" in build_requirements({"x": node})


def test_lowercase_keywords_do_not_count() -> None:
    body = (
        "# RFC\n\n## Requirements\n\n"
        "### Requirement: Weak wording\nID: weak\nProvenance: code\n\n"
        "It shall probably work, and it must be nice.\n\n"
        "#### Scenario: Weak\n- when something\n- then something\n"
    )
    section = parse_requirements(body)
    assert section is not None
    [req] = section.requirements
    assert not req.has_behavior_keyword
    [scenario] = req.scenarios
    assert not scenario.has_when and not scenario.has_then
