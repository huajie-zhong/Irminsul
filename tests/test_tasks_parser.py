"""Unit tests for the tasks section parser (RFC-0031)."""

from __future__ import annotations

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
    tasks = parse_tasks(_BODY)
    assert tasks is not None
    assert [t.task_id for t in tasks] == ["T1", "T2", "T3", "T4"]
    assert tasks[0].req_ref == "sso-login"
    assert tasks[0].component_ref is None
    assert tasks[0].text == "Wire the OIDC client."
    assert tasks[2].component_ref == "docgraph"
    assert tasks[2].req_ref is None
    assert tasks[3].req_ref is None and tasks[3].component_ref is None
    assert tasks[3].text == "A task with no reference."


def test_no_section_returns_none() -> None:
    assert parse_tasks("# RFC\n\n## Summary\n\nWords.\n") is None


def test_section_bounded_by_next_h2() -> None:
    tasks = parse_tasks(_BODY)
    assert tasks is not None
    assert all(t.task_id.startswith("T") for t in tasks)


def test_fenced_examples_are_ignored() -> None:
    body = "# RFC\n\n```markdown\n## Tasks\n\n- `T1` Quoted. (req: x)\n```\n"
    assert parse_tasks(body) is None


def test_items_without_backtick_id_are_skipped() -> None:
    body = "# RFC\n\n## Tasks\n\n- plain bullet without an id\n- `T1` Real task.\n"
    tasks = parse_tasks(body)
    assert tasks is not None
    assert [t.task_id for t in tasks] == ["T1"]
