"""Unit tests for the tasks section parser (RFC-0031)."""

from __future__ import annotations

from pathlib import Path

from irminsul.docgraph_index import parse_tasks

_BODY = """# RFC

## Tasks

- `T1` Wire the OIDC client. (req: sso-login)
- `T2` Add expired-assertion coverage. (req: sso-login)
- `T3` Document the env var. (component: docgraph)
- `T4` A task with no reference.

## Drawbacks

- not a task item
"""


def test_parses_tasks() -> None:
    section = parse_tasks(_BODY)
    assert section is not None
    tasks = section.tasks
    assert [t.task_id for t in tasks] == ["T1", "T2", "T3", "T4"]
    assert tasks[0].req_ref == "sso-login"
    assert tasks[0].component_ref is None
    assert tasks[0].text == "Wire the OIDC client."
    assert tasks[2].component_ref == "docgraph"
    assert tasks[2].req_ref is None
    assert tasks[3].req_ref is None and tasks[3].component_ref is None
    assert tasks[3].text == "A task with no reference."
    assert section.malformed == ()


def test_no_section_returns_none() -> None:
    assert parse_tasks("# RFC\n\n## Summary\n\nWords.\n") is None


def test_section_bounded_by_next_h2() -> None:
    section = parse_tasks(_BODY)
    assert section is not None
    assert all(t.task_id.startswith("T") for t in section.tasks)
    assert section.malformed == ()


def test_fenced_examples_are_ignored() -> None:
    body = "# RFC\n\n```markdown\n## Tasks\n\n- `T1` Quoted. (req: x)\n```\n"
    assert parse_tasks(body) is None


def test_uppercase_tasks_heading_indexed() -> None:
    from irminsul.docgraph import DocNode
    from irminsul.docgraph_index import build_tasks
    from irminsul.frontmatter import DocFrontmatter

    body = "# RFC\n\n## TASKS\n\n- `T1` Shout the task. (req: x)\n"
    fm = DocFrontmatter.model_validate(
        {"id": "x", "title": "X", "audience": "explanation", "tier": 2, "status": "draft"}
    )
    node = DocNode(id="x", path=Path("docs/x.md"), frontmatter=fm, body=body)
    tasks = build_tasks({"x": node})
    assert [t.task_id for t in tasks["x"].tasks] == ["T1"]


def test_items_without_backtick_id_are_recorded_as_malformed() -> None:
    body = "# RFC\n\n## Tasks\n\n- plain bullet without an id\n- `T1` Real task.\n"
    section = parse_tasks(body)
    assert section is not None
    assert [t.task_id for t in section.tasks] == ["T1"]
    assert [(m.line, m.reason) for m in section.malformed] == [(5, "missing-id")]


def test_section_of_only_unparseable_items_is_empty_not_absent() -> None:
    body = (
        "# RFC\n\n## Tasks\n\n- T1 Wire client (req: sso-login)\n- T2 Cover it (req: sso-login)\n"
    )
    section = parse_tasks(body)
    assert section is not None
    assert section.line == 3
    assert section.tasks == ()
    assert [m.reason for m in section.malformed] == ["missing-id", "missing-id"]


def test_doubly_referenced_item_is_malformed() -> None:
    section = parse_tasks("# RFC\n\n## Tasks\n\n- `T1` Do it. (req: a) (component: b)\n")
    assert section is not None
    assert section.tasks == ()
    assert [m.reason for m in section.malformed] == ["multiple-references"]


def test_mid_line_reference_is_malformed() -> None:
    section = parse_tasks("# RFC\n\n## Tasks\n\n- `T1` (req: a) then more text\n")
    assert section is not None
    assert section.tasks == ()
    assert [m.reason for m in section.malformed] == ["misplaced-reference"]


def test_empty_reference_is_malformed() -> None:
    section = parse_tasks("# RFC\n\n## Tasks\n\n- `T1` Do it. (req: )\n")
    assert section is not None
    assert section.tasks == ()
    assert [m.reason for m in section.malformed] == ["empty-reference"]


def test_trailing_reference_still_parses() -> None:
    section = parse_tasks("# RFC\n\n## Tasks\n\n- `T1` Do it. (component: auth)\n")
    assert section is not None
    [task] = section.tasks
    assert task.component_ref == "auth"
    assert task.text == "Do it."
    assert section.malformed == ()
