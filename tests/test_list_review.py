"""Tests for `irminsul list review` and the possibly-shipped draft queue entry."""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

from git import Repo
from typer.testing import CliRunner

from irminsul import mcp_server
from irminsul.cli import app
from irminsul.config import load
from irminsul.git.changes import changed_line_numbers
from irminsul.listing.review import review_json

runner = CliRunner()

CLI_SRC = """\
from typing import Annotated

import typer

app = typer.Typer()


def find_config(start):
    return start


@app.command()
def check(
    fmt: Annotated[str, typer.Option("--format")] = "plain",
    strict: Annotated[bool, typer.Option("--strict")] = False,
) -> None:
    pass
"""

DOC_BODY = """\
`find_config()` exits 1 when no config exists.

`check --format json` emits a JSON array of findings.

This sentence names `check` but asserts nothing checkable.

```text
check exits 2 inside a fence and is ignored.
```
"""


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _doc(doc_id: str, body: str, *, status: str = "stable", extra: str = "") -> str:
    return (
        f"---\nid: {doc_id}\ntitle: {doc_id}\n"
        f"status: {status}\ndescribes: []\n{extra}---\n\n# {doc_id}\n\n{body}"
    )


def _repo(root: Path) -> Path:
    _write(
        root,
        "irminsul.toml",
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
    )
    _write(root, "src/cli.py", CLI_SRC)
    _write(root, "docs/components/pipeline.md", _doc("pipeline", DOC_BODY))
    _write(
        root,
        "docs/components/draft.md",
        _doc("draft", "`check` exits 1 always.", status="draft"),
    )
    return root


def _items(root: Path, doc: str | None = None, *, show_all: bool = True) -> list[dict]:
    report = review_json(root, load(root / "irminsul.toml"), doc, show_all=show_all)
    return json.loads(report)["items"]


def test_assertions_are_queued_with_resolved_code(tmp_path: Path) -> None:
    items = _items(_repo(tmp_path))
    by_line = {item["line"]: item for item in items}
    doc_lines = (tmp_path / "docs/components/pipeline.md").read_text(encoding="utf-8").splitlines()

    assert len(items) == 2
    exit_item = next(i for i in items if "exit-code" in i["markers"])
    assert doc_lines[exit_item["line"] - 1].startswith("`find_config()` exits 1")
    assert exit_item["references"] == [
        {
            "span": "find_config()",
            "kind": "symbol",
            "identity": "find_config",
            "defined_at": "src/cli.py",
            "line": 8,
            "line_end": 9,
        }
    ]
    format_item = next(i for i in by_line.values() if "output-format" in i["markers"])
    assert {(r["kind"], r["identity"]) for r in format_item["references"]} == {
        ("cli", "check"),
        ("cli-options", "--format"),
    }


def test_drafts_fences_and_non_assertions_are_left_out(tmp_path: Path) -> None:
    sentences = [item["sentence"] for item in _items(_repo(tmp_path))]
    assert not any("asserts nothing" in s or "inside a fence" in s for s in sentences)
    assert all(item["path"] == "docs/components/pipeline.md" for item in _items(tmp_path))


def test_doc_filter_and_cli_exit_code(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    assert _items(root, "docs/components/other.md") == []

    result = runner.invoke(
        app,
        ["list", "review", "--all", "--doc", "docs/components/pipeline.md", "--path", str(root)],
    )
    assert result.exit_code == 0, result.output
    assert "exit-code" in result.output

    result = runner.invoke(app, ["list", "review", "--path", str(root)])
    assert result.exit_code == 0, result.output
    assert "0 of 2 assertion sentences" in result.output

    result = runner.invoke(app, ["list", "review", "--format", "json", "--path", str(root)])
    assert json.loads(result.output)["version"] == 1


def _commit_all_in_the_past(root: Path) -> Repo:
    repo = Repo.init(root)
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "Test")
        cw.set_value("user", "email", "test@example.com")
    old = _dt.datetime(2020, 1, 1, tzinfo=_dt.UTC)
    repo.index.add(["irminsul.toml", "src/cli.py", "docs"])
    repo.index.commit("init", author_date=old, commit_date=old)
    return repo


def _edit_cli(root: Path, old: str, new: str) -> None:
    path = root / "src" / "cli.py"
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")


def _marked(root: Path) -> dict[str, bool]:
    return {item["sentence"][:14]: item["code_changed_after_doc"] for item in _items(root)}


def test_an_edit_elsewhere_in_the_same_file_does_not_mark(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    repo = _commit_all_in_the_past(root)
    _edit_cli(root, "    pass\n", "    return None\n")
    repo.index.add(["src/cli.py"])
    repo.index.commit("change check's body")
    repo.close()

    assert _marked(root) == {"`find_config()": False, "`check --forma": False}


def test_an_edit_inside_the_named_function_marks(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    repo = _commit_all_in_the_past(root)
    _edit_cli(root, "    return start\n", "    return start.parent\n")
    repo.index.add(["src/cli.py"])
    repo.index.commit("change find_config")
    repo.close()

    assert _marked(root) == {"`find_config()": True, "`check --forma": False}
    shown = json.loads(review_json(root, load(root / "irminsul.toml")))
    assert (shown["total"], shown["shown"]) == (2, 1)
    assert shown["items"][0]["references"][0]["line_end"] == 9


def test_uncommitted_lines_count_as_changed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    repo = _commit_all_in_the_past(root)
    repo.close()
    _edit_cli(root, "    return start\n", "    return start.parent\n")

    assert _marked(root)["`find_config()"] is True


def test_review_is_available_over_mcp(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    data = json.loads(mcp_server.list_docs_json(root, load(root / "irminsul.toml"), "review"))
    assert (data["version"], data["total"], data["shown"]) == (1, 2, 0)


def test_draft_naming_only_live_identities_is_queued_as_possibly_shipped(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(
        root,
        "docs/rfcs/0001-shipped.md",
        _doc(
            "0001-shipped",
            "Adds `--strict` and `irminsul check --format json`.",
            status="draft",
            extra="rfc_state: draft\naffects: []\n",
        ),
    )
    _write(
        root,
        "docs/rfcs/0002-unshipped.md",
        _doc(
            "0002-unshipped",
            "Adds `--strict` and `--brand-new`.",
            status="draft",
            extra="rfc_state: draft\naffects: []\n",
        ),
    )
    result = runner.invoke(
        app, ["list", "lifecycle", "--queue", "--format", "json", "--path", str(root)]
    )
    assert result.exit_code == 0, result.output
    shipped = [i for i in json.loads(result.output) if i["kind"] == "review-shipped"]
    assert [i["related_id"] for i in shipped] == ["0001-shipped"]
    assert "--strict" in shipped[0]["reason"]


def test_enforcement_claims_name_identities_in_plain_prose(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(
        root,
        "docs/components/pipeline.md",
        _doc("pipeline", "Passing --strict catches every warning.\n\nThe tool strictly passes.\n"),
    )
    [item] = [i for i in _items(root, "docs/components/pipeline.md") if "catches" in i["sentence"]]
    assert "enforcement" in item["markers"]
    assert {(r["kind"], r["identity"]) for r in item["references"]} == {("cli-options", "--strict")}


def test_a_repo_file_outside_source_roots_is_a_reference(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, ".pre-commit-config.yaml", "repos: []\n")
    _write(
        root,
        "docs/components/pipeline.md",
        _doc("pipeline", "`.pre-commit-config.yaml` always runs the hard profile.\n"),
    )
    repo = _commit_all_in_the_past(root)
    _write(root, ".pre-commit-config.yaml", "repos:\n  - local\n")
    repo.index.add([".pre-commit-config.yaml"])
    repo.index.commit("change hooks")
    repo.close()

    [item] = _items(root, "docs/components/pipeline.md", show_all=False)
    assert item["references"][0]["kind"] == "path"
    assert item["code_changed_after_doc"] is True


def test_decision_sections_and_glossary_definitions_are_reviewed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(
        root,
        "docs/decisions/0001-choice.md",
        "---\nid: 0001-choice\ntitle: Choice\nstatus: stable\n---\n\n# Choice\n\n"
        "## Context\n\nThe old tool never warns.\n\n## Decision\n\n`check` always exits 1 on errors.\n\n"
        "## Consequences\n\nIt will be stricter.\n",
    )
    _write(
        root,
        "docs/GLOSSARY.md",
        '# Glossary\n\n## Strict mode\n\nmatch: ["strict mode"]\n\nStrict mode never fails a run.\n',
    )
    items = _items(root)
    decision = [i["sentence"] for i in items if i["path"] == "docs/decisions/0001-choice.md"]
    assert decision == ["`check` always exits 1 on errors."]
    glossary = [i for i in items if i["path"] == "docs/GLOSSARY.md"]
    assert [(i["line"], i["sentence"]) for i in glossary] == [(7, "Strict mode never fails a run.")]


def test_ordinary_english_verbs_need_a_code_reference(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(
        root,
        "docs/components/pipeline.md",
        _doc(
            "pipeline",
            "Unchecked docs fail readers.\n\nThe team will decide later.\n\n"
            "Support for YAML is planned.\n\n`check` fails on errors.\n",
        ),
    )
    sentences = {i["sentence"]: i["markers"] for i in _items(root, "docs/components/pipeline.md")}
    assert sentences == {
        "Support for YAML is planned.": ["future"],
        "`check` fails on errors.": ["enforcement"],
    }


def test_table_rows_are_reviewed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(
        root,
        "docs/components/pipeline.md",
        _doc(
            "pipeline", "| Key | Default |\n|-----|---------|\n| `--strict` | defaults to off |\n"
        ),
    )
    [item] = _items(root, "docs/components/pipeline.md")
    assert item["sentence"] == "`--strict` | defaults to off"
    assert item["markers"] == ["default"]


def test_changed_lines_queue_new_claims_without_code_names(tmp_path: Path) -> None:
    from irminsul.git.changes import changed_line_numbers

    root = _repo(tmp_path)
    repo = _commit_all_in_the_past(root)
    repo.close()
    doc = root / "docs/components/pipeline.md"
    doc.write_text(
        doc.read_text(encoding="utf-8") + "\nEvery soft check only warns.\n", encoding="utf-8"
    )

    changed = changed_line_numbers(root)
    report = json.loads(review_json(root, load(root / "irminsul.toml"), changed=changed))
    assert [(i["sentence"], i["markers"]) for i in report["items"]] == [
        ("Every soft check only warns.", ["enforcement", "scope"])
    ]
    assert report["shown"] == report["total"] == 1

    result = runner.invoke(app, ["list", "review", "--changed", "--path", str(root)])
    assert result.exit_code == 0, result.output
    assert "1 assertion sentences on changed lines" in result.output


def test_a_body_edit_that_leaves_the_summary_lists_the_summary(tmp_path: Path) -> None:
    import subprocess

    from irminsul.docgraph import build_graph
    from irminsul.listing.review import build_review

    root = tmp_path
    _write(
        root,
        "irminsul.toml",
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = []\n',
    )
    doc = (
        "---\nid: store\ntitle: Store\nstatus: stable\nsummary: The store keeps sessions.\n"
        "---\n\n# Store\n\nThe store keeps sessions in memory.\n"
    )
    _write(root, "docs/components/store.md", doc)
    for args in (
        ["init", "-q"],
        ["add", "-A"],
        ["-c", "user.name=T", "-c", "user.email=t@e", "commit", "-qm", "i"],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True)

    body_only = {"docs/components/store.md": {10}}
    with_summary = {"docs/components/store.md": {5, 10}}
    graph = build_graph(root, load(root / "irminsul.toml"))

    stale = [
        i
        for i in build_review(root, load(root / "irminsul.toml"), graph, body_only)
        if "stale-summary" in i.markers
    ]
    assert [(i.line, i.sentence) for i in stale] == [(5, "The store keeps sessions.")]
    assert not [
        i
        for i in build_review(root, load(root / "irminsul.toml"), graph, with_summary)
        if "stale-summary" in i.markers
    ]


def test_review_changed_works_before_the_first_commit(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    Repo.init(root).close()
    result = runner.invoke(app, ["list", "review", "--changed", "--path", str(root)])
    assert result.exit_code == 0, result.output


def test_a_deleted_claim_is_queued_rather_than_vanishing(tmp_path: Path) -> None:
    """Gutting a doc used to empty the queue along with the doc."""
    from irminsul.git.changes import changed_line_numbers

    root = _repo(tmp_path)
    _commit_all_in_the_past(root).close()

    doc = root / "docs/components/pipeline.md"
    kept = [
        line
        for line in doc.read_text(encoding="utf-8").splitlines()
        if "exits" not in line and "every" not in line.lower()
    ]
    doc.write_text("\n".join(kept) + "\n", encoding="utf-8")

    report = json.loads(
        review_json(root, load(root / "irminsul.toml"), changed=changed_line_numbers(root))
    )
    removed = [i for i in report["items"] if "removed-sentence" in i["markers"]]
    assert removed, "deleting the claims removed them from the review queue too"
    assert all(i["path"] == "docs/components/pipeline.md" for i in removed)


def test_an_untouched_doc_reports_no_removed_sentences(tmp_path: Path) -> None:
    from irminsul.git.changes import changed_line_numbers

    root = _repo(tmp_path)
    _commit_all_in_the_past(root).close()
    (root / "src" / "extra.py").write_text("def extra(): pass\n", encoding="utf-8")

    report = json.loads(
        review_json(root, load(root / "irminsul.toml"), changed=changed_line_numbers(root))
    )
    assert not [i for i in report["items"] if "removed-sentence" in i["markers"]]


def test_a_governing_claim_is_queued_when_only_its_code_changed(tmp_path: Path) -> None:
    """The review queue reaches a claim through changed code, not just changed prose.

    Every other entry starts from a doc line the change touched. This one cannot: the
    document was never opened, which is the case where nobody would re-read the
    contract on their own.
    """
    root = _repo(tmp_path)
    _write(
        root,
        "docs/components/pipeline.md",
        _doc(
            "pipeline",
            DOC_BODY,
            extra=(
                "claims:\n"
                "  - id: config-lookup-walks-up\n"
                "    state: implemented\n"
                "    kind: invariant\n"
                "    relation: governs-evidence\n"
                "    claim: Config lookup walks upward and never reads a sibling tree.\n"
                "    evidence:\n"
                "      - src/cli.py\n"
            ),
        ),
    )
    repo = _commit_all_in_the_past(root)
    repo.close()
    _edit_cli(root, "    return start\n", "    return start.parent\n")

    changed = changed_line_numbers(root)
    items = json.loads(
        review_json(root, load(root / "irminsul.toml"), changed=changed, show_all=True)
    )["items"]

    queued = [item for item in items if "governing-claim" in item["markers"]]
    assert len(queued) == 1
    assert queued[0]["path"] == "docs/components/pipeline.md"
    assert queued[0]["sentence"].startswith("Config lookup walks upward")
    assert "evidence:src/cli.py" in queued[0]["markers"]
    doc_lines = (root / "docs/components/pipeline.md").read_text(encoding="utf-8").splitlines()
    assert doc_lines[queued[0]["line"] - 1].strip() == "- id: config-lookup-walks-up"
