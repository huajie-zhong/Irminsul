"""Tests for `irminsul list review` and the possibly-shipped draft queue entry."""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from irminsul import mcp_server
from irminsul.cli import app
from irminsul.config import load
from irminsul.git.changes import changed_line_numbers
from irminsul.git.reader import GitReader
from irminsul.listing.review import build_review, review_json

from .conftest import commit_all, git_init, load_graph, seed_repo, write, write_config

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

This sentence names no code at all.

```text
check exits 2 inside a fence and is ignored.
```
"""


def _doc(doc_id: str, body: str, *, status: str = "stable", extra: str = "") -> str:
    return (
        f"---\nid: {doc_id}\ntitle: {doc_id}\n"
        f"status: {status}\ndescribes: []\n{extra}---\n\n# {doc_id}\n\n{body}"
    )


def _repo(root: Path) -> Path:
    write_config(root, source_roots=["src"])
    write(root, "src/cli.py", CLI_SRC)
    write(root, "docs/components/pipeline.md", _doc("pipeline", DOC_BODY))
    write(
        root,
        "docs/components/draft.md",
        _doc("draft", "`check` exits 1 always.", status="draft"),
    )
    return root


def _items(root: Path, doc: str | None = None, *, show_all: bool = True) -> list[dict]:
    report = review_json(root, load(root / "irminsul.toml"), doc, show_all=show_all)
    return json.loads(report)["items"]


def test_sentences_naming_code_are_queued_with_resolved_code(tmp_path: Path) -> None:
    items = _items(_repo(tmp_path))
    doc_lines = (tmp_path / "docs/components/pipeline.md").read_text(encoding="utf-8").splitlines()

    assert len(items) == 2
    assert all(item["markers"] == ["names-code"] for item in items)
    exit_item = next(i for i in items if i["sentence"].startswith("`find_config()`"))
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
    format_item = next(i for i in items if i["sentence"].startswith("`check --format"))
    assert {(r["kind"], r["identity"]) for r in format_item["references"]} == {
        ("cli", "check"),
        ("cli-options", "--format"),
    }


def test_drafts_fences_and_sentences_naming_no_code_are_left_out(tmp_path: Path) -> None:
    sentences = [item["sentence"] for item in _items(_repo(tmp_path))]
    assert not any("names no code" in s or "inside a fence" in s for s in sentences)
    assert all(item["path"] == "docs/components/pipeline.md" for item in _items(tmp_path))


def test_doc_filter_and_cli_exit_code(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    assert _items(root, "docs/components/draft.md") == []

    result = runner.invoke(
        app,
        ["list", "review", "--all", "--doc", "docs/components/pipeline.md", "--path", str(root)],
    )
    assert result.exit_code == 0, result.output
    assert "(names-code)" in result.output

    result = runner.invoke(app, ["list", "review", "--path", str(root)])
    assert result.exit_code == 0, result.output
    assert "0 of 2 sentences naming code" in result.output

    result = runner.invoke(app, ["list", "review", "--format", "json", "--path", str(root)])
    assert json.loads(result.output)["version"] == 1


def test_doc_filter_takes_an_id_and_refuses_an_unknown_doc(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    assert _items(root, "pipeline") == _items(root, "docs/components/pipeline.md") != []

    result = runner.invoke(app, ["list", "review", "--doc", "no-such-doc", "--path", str(root)])
    assert result.exit_code == 2
    assert "no doc with id or path no-such-doc" in result.output


def _commit_all_in_the_past(root: Path) -> None:
    git_init(root)
    old = _dt.datetime(2020, 1, 1, tzinfo=_dt.UTC)
    commit_all(root, "init", when=old, paths=["irminsul.toml", "src/cli.py", "docs"])


def _edit_cli(root: Path, old: str, new: str) -> None:
    path = root / "src" / "cli.py"
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")


def _marked(root: Path) -> dict[str, bool]:
    return {item["sentence"][:14]: item["code_changed_after_doc"] for item in _items(root)}


def _marked_graph(root: Path, **graph_kwargs: object) -> dict[str, bool]:
    items = build_review(root, load(root / "irminsul.toml"), load_graph(root, **graph_kwargs))
    return {item.sentence[:14]: item.code_changed_after_doc for item in items}


def _edit_doc(root: Path) -> None:
    doc = root / "docs" / "components" / "pipeline.md"
    doc.write_text(doc.read_text(encoding="utf-8") + "\nRead again.\n", encoding="utf-8")


def test_a_doc_edited_beside_its_code_is_not_behind_it(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _commit_all_in_the_past(root)
    _edit_cli(root, "    return start\n", "    return start.parent\n")
    assert _marked_graph(root)["`find_config()"] is True

    _edit_doc(root)

    assert _marked_graph(root) == {"`find_config()": False, "`check --forma": False}
    assert _marked_graph(root, committed_only=True)["`find_config()"] is True


def test_review_json_reads_the_doc_at_its_commit_time_under_committed_only(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    _commit_all_in_the_past(root)
    _edit_cli(root, "    return start\n", "    return start.parent\n")
    commit_all(root, "change find_config", paths=["src/cli.py"])
    _edit_doc(root)
    config = load(root / "irminsul.toml")

    def marked(**kwargs: bool) -> dict[str, bool]:
        items = json.loads(review_json(root, config, show_all=True, **kwargs))["items"]
        return {item["sentence"][:14]: item["code_changed_after_doc"] for item in items}

    assert marked()["`find_config()"] is False
    assert marked(committed_only=True)["`find_config()"] is True


def test_editing_the_doc_answers_committed_code_change_before_the_commit(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _commit_all_in_the_past(root)
    _edit_cli(root, "    return start\n", "    return start.parent\n")
    commit_all(root, "change find_config", paths=["src/cli.py"])
    assert _marked_graph(root)["`find_config()"] is True

    _edit_doc(root)

    assert _marked_graph(root)["`find_config()"] is False
    assert _marked_graph(root, committed_only=True)["`find_config()"] is True


def test_an_edit_elsewhere_in_the_same_file_does_not_mark(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _commit_all_in_the_past(root)
    _edit_cli(root, "    pass\n", "    return None\n")
    commit_all(root, "change check's body", paths=["src/cli.py"])

    assert _marked(root) == {"`find_config()": False, "`check --forma": False}


def test_an_edit_inside_the_named_function_marks(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _commit_all_in_the_past(root)
    _edit_cli(root, "    return start\n", "    return start.parent\n")
    commit_all(root, "change find_config", paths=["src/cli.py"])

    assert _marked(root) == {"`find_config()": True, "`check --forma": False}
    shown = json.loads(review_json(root, load(root / "irminsul.toml")))
    assert (shown["total"], shown["shown"]) == (2, 1)
    assert shown["items"][0]["references"][0]["line_end"] == 9


def test_uncommitted_lines_count_as_changed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _commit_all_in_the_past(root)
    _edit_cli(root, "    return start\n", "    return start.parent\n")

    assert _marked(root)["`find_config()"] is True


def test_review_is_available_over_mcp(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    data = json.loads(mcp_server.list_docs_json(root, load(root / "irminsul.toml"), "review"))
    assert (data["version"], data["total"], data["shown"]) == (1, 2, 0)


def test_draft_naming_only_live_identities_is_queued_as_possibly_shipped(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    write(
        root,
        "docs/rfcs/0001-shipped.md",
        _doc(
            "0001-shipped",
            "Adds `--strict` and `irminsul check --format json`.",
            status="draft",
            extra="rfc_state: draft\naffects: []\n",
        ),
    )
    write(
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


def test_an_identity_named_in_plain_prose_is_code(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    write(
        root,
        "docs/components/pipeline.md",
        _doc("pipeline", "Passing --strict catches every warning.\n\nThe tool strictly passes.\n"),
    )
    [item] = _items(root, "docs/components/pipeline.md")
    assert item["sentence"] == "Passing --strict catches every warning."
    assert {(r["kind"], r["identity"]) for r in item["references"]} == {("cli-options", "--strict")}


def test_a_repo_file_outside_source_roots_is_a_reference(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    write(root, ".pre-commit-config.yaml", "repos: []\n")
    write(
        root,
        "docs/components/pipeline.md",
        _doc("pipeline", "`.pre-commit-config.yaml` always runs the hard profile.\n"),
    )
    _commit_all_in_the_past(root)
    write(root, ".pre-commit-config.yaml", "repos:\n  - local\n")
    commit_all(root, "change hooks", paths=[".pre-commit-config.yaml"])

    [item] = _items(root, "docs/components/pipeline.md", show_all=False)
    assert item["references"][0]["kind"] == "path"
    assert item["code_changed_after_doc"] is True


def test_decision_sections_and_glossary_definitions_are_reviewed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    write(
        root,
        "docs/decisions/0001-choice.md",
        "---\nid: 0001-choice\ntitle: Choice\nstatus: stable\n---\n\n# Choice\n\n"
        "## Context\n\nThe old `check` never warns.\n\n## Decision\n\n`check` always exits 1 on "
        "errors.\n\n## Consequences\n\n`check` will be stricter.\n",
    )
    write(
        root,
        "docs/GLOSSARY.md",
        '# Glossary\n\n## Strict mode\n\nmatch: ["strict mode"]\n\nStrict mode is `--strict`.\n',
    )
    items = _items(root)
    decision = [i["sentence"] for i in items if i["path"] == "docs/decisions/0001-choice.md"]
    assert decision == ["`check` always exits 1 on errors."]
    glossary = [i for i in items if i["path"] == "docs/GLOSSARY.md"]
    assert [(i["line"], i["sentence"]) for i in glossary] == [(7, "Strict mode is `--strict`.")]


def test_the_whole_tree_queue_reads_no_vocabulary(tmp_path: Path) -> None:
    """A word list guessed which sentences were claims: "always" queued a sentence, and the
    same claim worded without it was dropped. The queue now selects what names code."""
    root = _repo(tmp_path)
    write(
        root,
        "docs/components/pipeline.md",
        _doc(
            "pipeline",
            "The cache is always rebuilt.\n\nThe cache is rebuilt per run.\n\n"
            "Support for YAML is planned.\n\n`check` rebuilds the cache.\n",
        ),
    )
    sentences = {i["sentence"]: i["markers"] for i in _items(root, "docs/components/pipeline.md")}
    assert sentences == {"`check` rebuilds the cache.": ["names-code"]}


_MANIFEST_START = "<!-- agents-manifest:generated-start -->"
_MANIFEST_END = "<!-- agents-manifest:generated-end -->"


def _manifest_sentences(root: Path, text: str) -> list[str]:
    write(root, "docs/AGENTS.md", text)
    return [item["sentence"] for item in _items(root, "docs/AGENTS.md")]


def test_the_manifests_generated_region_is_not_queued(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    sentences = _manifest_sentences(
        root,
        f"Curated: `check` exits 1.\n\n{_MANIFEST_START}\n\nDerived: `check` exits 2.\n\n"
        f"{_MANIFEST_END}\n\nCurated: `check` exits 3.\n",
    )

    assert sentences == ["Curated: `check` exits 1.", "Curated: `check` exits 3."]


def test_a_fenced_marker_does_not_hide_the_prose_after_it(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    sentences = _manifest_sentences(
        root,
        f"```text\n{_MANIFEST_START}\n```\n\nCurated: `check` exits 1.\n\n"
        f"{_MANIFEST_START}\n\nDerived: `check` exits 2.\n\n{_MANIFEST_END}\n",
    )

    assert sentences == ["Curated: `check` exits 1."]


def test_a_manifest_with_two_generated_pairs_is_read_whole(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    pair = f"{_MANIFEST_START}\n\nDerived: `check` exits 2.\n\n{_MANIFEST_END}\n"

    sentences = _manifest_sentences(root, f"{pair}\n{pair}")

    assert sentences == ["Derived: `check` exits 2."] * 2


def test_table_rows_are_reviewed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    write(
        root,
        "docs/components/pipeline.md",
        _doc(
            "pipeline", "| Key | Default |\n|-----|---------|\n| `--strict` | defaults to off |\n"
        ),
    )
    [item] = _items(root, "docs/components/pipeline.md")
    assert item["sentence"] == "`--strict` | defaults to off"
    assert item["markers"] == ["names-code"]


def test_every_new_sentence_is_queued_whatever_it_says(tmp_path: Path) -> None:
    """A new sentence is the reason to look, so no word in it decides whether it is
    shown: both wordings of one claim are queued, and the untouched sentences are not."""
    from irminsul.git.changes import changed_line_numbers

    root = _repo(tmp_path)
    _commit_all_in_the_past(root)
    doc = root / "docs/components/pipeline.md"
    doc.write_text(
        doc.read_text(encoding="utf-8")
        + "\nThe cache is always rebuilt.\n\nThe cache is rebuilt per run.\n",
        encoding="utf-8",
    )

    changed = changed_line_numbers(GitReader(), root)
    report = json.loads(review_json(root, load(root / "irminsul.toml"), changed=changed))
    assert [(i["sentence"], i["markers"]) for i in report["items"]] == [
        ("The cache is always rebuilt.", ["edited"]),
        ("The cache is rebuilt per run.", ["edited"]),
    ]
    assert report["shown"] == report["total"] == 2

    result = runner.invoke(app, ["list", "review", "--changed", "--path", str(root)])
    assert result.exit_code == 0, result.output
    assert "2 items this change asks to re-read" in result.output


def test_a_body_edit_that_leaves_the_summary_lists_the_summary(tmp_path: Path) -> None:

    from irminsul.listing.review import build_review

    root = tmp_path
    write_config(root)
    doc = (
        "---\nid: store\ntitle: Store\nstatus: stable\nsummary: The store keeps sessions.\n"
        "---\n\n# Store\n\nThe store keeps sessions in memory.\n"
    )
    write(root, "docs/components/store.md", doc)
    seed_repo(root, "i")

    body_only = {"docs/components/store.md": {10}}
    with_summary = {"docs/components/store.md": {5, 10}}
    graph = load_graph(root)

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
    git_init(root)
    result = runner.invoke(app, ["list", "review", "--changed", "--path", str(root)])
    assert result.exit_code == 0, result.output


def test_a_deleted_claim_is_queued_rather_than_vanishing(tmp_path: Path) -> None:
    """Gutting a doc used to empty the queue along with the doc."""
    from irminsul.git.changes import changed_line_numbers

    root = _repo(tmp_path)
    _commit_all_in_the_past(root)

    doc = root / "docs/components/pipeline.md"
    kept = [
        line
        for line in doc.read_text(encoding="utf-8").splitlines()
        if "exits" not in line and "every" not in line.lower()
    ]
    doc.write_text("\n".join(kept) + "\n", encoding="utf-8")

    report = json.loads(
        review_json(
            root, load(root / "irminsul.toml"), changed=changed_line_numbers(GitReader(), root)
        )
    )
    removed = [i for i in report["items"] if "removed-sentence" in i["markers"]]
    assert removed, "deleting the claims removed them from the review queue too"
    assert all(i["path"] == "docs/components/pipeline.md" for i in removed)


def test_every_deleted_sentence_is_queued_whatever_it_says(tmp_path: Path) -> None:
    """A deletion was queued only when the sentence held a listed word, so removing a
    plainly worded claim left nothing to re-read."""
    root = _repo(tmp_path)
    _commit_all_in_the_past(root)
    doc = root / "docs/components/pipeline.md"
    text = doc.read_text(encoding="utf-8")
    doc.write_text(text.replace("This sentence names no code at all.\n", ""), encoding="utf-8")

    report = json.loads(
        review_json(
            root, load(root / "irminsul.toml"), changed=changed_line_numbers(GitReader(), root)
        )
    )
    assert [(i["sentence"], i["markers"]) for i in report["items"]] == [
        ("This sentence names no code at all.", ["removed-sentence"])
    ]


def test_a_deletion_from_a_file_the_queue_does_not_read_is_not_queued(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    write(root, "notes/scratch.md", "A scratch note says something.\n")
    write(
        root,
        "docs/rfcs/0001-idea.md",
        _doc("0001-idea", "The idea says something.\n", status="draft", extra="rfc_state: draft\n"),
    )
    _commit_all_in_the_past(root)
    commit_all(root, "notes", paths=["notes/scratch.md"])
    write(root, "notes/scratch.md", "\n")
    rfc = root / "docs/rfcs/0001-idea.md"
    rfc_text = rfc.read_text(encoding="utf-8")
    rfc.write_text(rfc_text.replace("The idea says something.\n", ""), encoding="utf-8")

    report = json.loads(
        review_json(
            root, load(root / "irminsul.toml"), changed=changed_line_numbers(GitReader(), root)
        )
    )
    assert report["items"] == []


def test_an_untouched_doc_reports_no_removed_sentences(tmp_path: Path) -> None:
    from irminsul.git.changes import changed_line_numbers

    root = _repo(tmp_path)
    _commit_all_in_the_past(root)
    (root / "src" / "extra.py").write_text("def extra(): pass\n", encoding="utf-8")

    report = json.loads(
        review_json(
            root, load(root / "irminsul.toml"), changed=changed_line_numbers(GitReader(), root)
        )
    )
    assert not [i for i in report["items"] if "removed-sentence" in i["markers"]]


REWRITTEN = "A sentence the edit rewrites."
STRAY_BRACKET_SHAPES = {
    "across paragraphs": (
        "A `[` that never closes ends with its paragraph.\n\n",
        "The rule is specified by\n[Finding classes decide what blocks](../decisions/finding-classes-decide-what-blocks.md).\n\n",
        "The rule is specified by [Finding classes decide what blocks](../decisions/finding-classes-decide-what-blocks.md).",
    ),
    "within a paragraph": (
        "A `[` that never closes. ",
        "Read [the guide](guide.md) first.\n\n",
        "Read [the guide](guide.md) first.",
    ),
}


def _review_file_edit(root: Path, rel: str, before: str, after: str) -> list[dict]:
    """The review queue of rewriting `rel` from `before` to `after`."""
    write(root, rel, before)
    _commit_all_in_the_past(root)
    write(root, rel, after)
    report = json.loads(
        review_json(
            root, load(root / "irminsul.toml"), changed=changed_line_numbers(GitReader(), root)
        )
    )
    return report["items"]


def _review_pipeline_edit(root: Path, before: str, after: str) -> list[dict]:
    """The review queue of rewriting `pipeline.md`'s body from `before` to `after`."""
    return _review_file_edit(
        root, "docs/components/pipeline.md", _doc("pipeline", before), _doc("pipeline", after)
    )


def _removed(items: list[dict]) -> list[str]:
    return [i["sentence"] for i in items if "removed-sentence" in i["markers"]]


@pytest.mark.parametrize("shape", sorted(STRAY_BRACKET_SHAPES))
def test_a_stray_bracket_does_not_make_the_sentences_after_it_read_as_deleted(
    tmp_path: Path, shape: str
) -> None:
    """A `[` that never closes and the next link's brackets, matched across the whole
    file, hid sentences the change never touched."""
    stray, link, _ = STRAY_BRACKET_SHAPES[shape]
    items = _review_pipeline_edit(
        _repo(tmp_path),
        stray + link + REWRITTEN + "\n",
        stray + link + "A sentence the edit rewrote.\n",
    )
    assert _removed(items) == [REWRITTEN]


@pytest.mark.parametrize("shape", sorted(STRAY_BRACKET_SHAPES))
def test_deleting_the_link_a_stray_bracket_precedes_is_still_queued(
    tmp_path: Path, shape: str
) -> None:
    stray, link, link_sentence = STRAY_BRACKET_SHAPES[shape]
    items = _review_pipeline_edit(
        _repo(tmp_path), stray + link + REWRITTEN + "\n", stray + "\n\n" + REWRITTEN + "\n"
    )
    assert _removed(items) == [link_sentence]


def test_re_pinning_an_anchor_does_not_delete_the_sentence_it_trails(tmp_path: Path) -> None:
    """The marker after a sentence is not part of what the sentence claims, so changing
    its hash queued the sentence as edited and as deleted at once."""
    sentence = "`find_config()` exits 1 when no config exists."
    marker = " <!-- anchor: src/cli.py#find_config @sha256:{} -->"
    items = _review_pipeline_edit(
        _repo(tmp_path),
        sentence + marker.format("a" * 12) + "\n",
        sentence + marker.format("b" * 12) + "\n",
    )
    assert items == []


def test_deleting_an_anchored_sentence_is_still_queued(tmp_path: Path) -> None:
    sentence = "`find_config()` exits 1 when no config exists."
    marker = " <!-- anchor: src/cli.py#find_config @sha256:" + "a" * 12 + " -->"
    items = _review_pipeline_edit(
        _repo(tmp_path), sentence + marker + "\n", "Nothing is claimed.\n"
    )
    assert _removed(items) == [sentence + marker]


def test_rewriting_a_comment_quoted_in_a_code_span_is_still_queued(tmp_path: Path) -> None:
    """A comment shown as an example is prose, unlike the marker that trails a sentence."""
    items = _review_pipeline_edit(
        _repo(tmp_path),
        "A comment such as `<!-- irminsul:ignore reality -->` covers its line.\n",
        "A comment such as `<!-- irminsul:ignore liar -->` covers its line.\n",
    )
    assert _removed(items) == [
        "A comment such as `<!-- irminsul:ignore reality -->` covers its line."
    ]


def test_retargeting_a_link_does_not_delete_the_sentence_around_it(tmp_path: Path) -> None:
    items = _review_pipeline_edit(
        _repo(tmp_path),
        "The rule is specified by [Enforcement](../decisions/old.md).\n",
        "The rule is specified by [Deterministic enforcement](../decisions/new.md).\n",
    )
    assert items == []


PARAGRAPH = (
    "`find_config()` exits 1 when no config exists. `check --format json` emits a JSON array. "
    "This sentence names no code at all."
)


def _edited(items: list[dict]) -> list[str]:
    return [i["sentence"] for i in items if "edited" in i["markers"]]


def test_a_sentence_added_to_a_paragraph_queues_only_that_sentence(tmp_path: Path) -> None:
    """A paragraph on one line is one changed line, but only the new sentence changed."""
    added = "`check --strict` fails on warnings."
    items = _review_pipeline_edit(_repo(tmp_path), PARAGRAPH + "\n", PARAGRAPH + " " + added + "\n")
    assert _edited(items) == [added]
    assert _removed(items) == []


def test_reflowing_a_paragraph_queues_nothing(tmp_path: Path) -> None:
    items = _review_pipeline_edit(
        _repo(tmp_path), PARAGRAPH.replace(". ", ".\n") + "\n", PARAGRAPH + "\n"
    )
    assert items == []


def test_a_sentence_rewritten_in_place_is_edited_and_removed(tmp_path: Path) -> None:
    rewritten = PARAGRAPH.replace("exits 1", "exits 2")
    items = _review_pipeline_edit(_repo(tmp_path), PARAGRAPH + "\n", rewritten + "\n")
    assert _edited(items) == ["`find_config()` exits 2 when no config exists."]
    assert _removed(items) == ["`find_config()` exits 1 when no config exists."]


def test_every_sentence_of_a_new_doc_is_edited_even_when_another_doc_says_it(
    tmp_path: Path,
) -> None:
    """A sentence is new to the doc that gained it, whatever another doc already says."""
    root = _repo(tmp_path)
    _commit_all_in_the_past(root)
    write(
        root,
        "docs/components/fresh.md",
        _doc("fresh", "This sentence names no code at all. `check` exits 1.\n"),
    )
    report = json.loads(
        review_json(
            root, load(root / "irminsul.toml"), changed=changed_line_numbers(GitReader(), root)
        )
    )
    assert sorted(_edited(report["items"])) == [
        "This sentence names no code at all.",
        "`check` exits 1.",
    ]
    assert _removed(report["items"]) == []


def test_a_numbered_list_marker_is_not_a_sentence_of_its_own(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _commit_all_in_the_past(root)
    write(
        root,
        "docs/components/fresh.md",
        _doc(
            "fresh",
            "1. Run `check` first. It is fast.\n2. Fix what it names.\n10) Run it again.\n",
        ),
    )
    report = json.loads(
        review_json(
            root, load(root / "irminsul.toml"), changed=changed_line_numbers(GitReader(), root)
        )
    )
    assert _edited(report["items"]) == [
        "1. Run `check` first.",
        "It is fast.",
        "2. Fix what it names.",
        "10) Run it again.",
    ]


def _decision_record(context: str, decision: str) -> str:
    return (
        "---\nid: choice\ntitle: Choice\nstatus: stable\n---\n\n# Choice\n\n"
        f"## Context\n\n{context}\n\n## Decision\n\n{decision}\n\n## Consequences\n\nNone.\n"
    )


def _review_decision_edit(
    root: Path, before: tuple[str, str], after: tuple[str, str]
) -> list[dict]:
    """The review queue of a decision record whose (context, decision) went from `before` to `after`."""
    return _review_file_edit(
        _repo(root),
        "docs/decisions/choice.md",
        _decision_record(*before),
        _decision_record(*after),
    )


def test_a_sentence_deleted_from_a_decision_records_decision_is_queued(tmp_path: Path) -> None:
    items = _review_decision_edit(
        tmp_path,
        ("None.", "`check` exits 1. `check` warns."),
        ("None.", "`check` exits 1."),
    )
    assert _removed(items) == ["`check` warns."]


def test_a_sentence_deleted_from_a_decision_records_context_is_not_queued(
    tmp_path: Path,
) -> None:
    """The queue reads a decision record's `## Decision` only, so deleting from any other
    section left a removed sentence that no edit there could have queued."""
    items = _review_decision_edit(
        tmp_path, ("The old way never warns.", "`check` exits 1."), ("None.", "`check` exits 1.")
    )
    assert items == []


def test_a_sentence_edited_outside_a_decision_records_decision_is_not_queued(
    tmp_path: Path,
) -> None:
    items = _review_decision_edit(
        tmp_path,
        ("The old way never warns.", "`check` exits 1."),
        ("The old way warned.", "`check` exits 1."),
    )
    assert items == []


def test_a_sentence_moved_into_the_decision_is_queued_as_edited(tmp_path: Path) -> None:
    items = _review_decision_edit(
        tmp_path,
        ("`check` warns.", "`check` exits 1."),
        ("None.", "`check` exits 1. `check` warns."),
    )
    assert _edited(items) == ["`check` warns."]
    assert _removed(items) == []


def test_a_sentence_moved_out_of_the_decision_is_queued_as_removed(tmp_path: Path) -> None:
    items = _review_decision_edit(
        tmp_path,
        ("None.", "`check` exits 1. `check` warns."),
        ("`check` warns.", "`check` exits 1."),
    )
    assert _removed(items) == ["`check` warns."]
    assert _edited(items) == []


def test_a_governing_claim_is_queued_when_only_its_code_changed(tmp_path: Path) -> None:
    """The review queue reaches a claim through changed code, not just changed prose.

    Every other entry starts from a doc line the change touched. This one cannot: the
    document was never opened, which is the case where nobody would re-read the
    contract on their own.
    """
    root = _repo(tmp_path)
    write(
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
    _commit_all_in_the_past(root)
    _edit_cli(root, "    return start\n", "    return start.parent\n")

    changed = changed_line_numbers(GitReader(), root)
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


def _legend(output: str) -> list[str]:
    """The lines under `markers:`, one for each marker the output explains."""
    lines = output.splitlines()
    return lines[lines.index("markers:") + 1 :]


def _review_changed_plain(root: Path) -> str:
    result = runner.invoke(app, ["list", "review", "--changed", "--path", str(root)])
    assert result.exit_code == 0, result.output
    return result.output


def _rewrite_one_sentence_and_delete_another(root: Path) -> None:
    _commit_all_in_the_past(root)
    doc = root / "docs/components/pipeline.md"
    text = doc.read_text(encoding="utf-8")
    text = text.replace("exits 1 when", "exits 2 when")
    doc.write_text(text.replace("This sentence names no code at all.\n", ""), encoding="utf-8")


def test_plain_review_explains_each_marker_it_shows_once(tmp_path: Path) -> None:
    from irminsul.listing.review import MARKER_MEANINGS

    root = _repo(tmp_path)
    _rewrite_one_sentence_and_delete_another(root)

    legend = _legend(_review_changed_plain(root))

    assert [line.split()[0] for line in legend] == ["edited", "removed-sentence"]
    assert MARKER_MEANINGS["edited"] in legend[0]
    assert MARKER_MEANINGS["removed-sentence"] in legend[1]


def test_json_review_carries_the_meaning_of_each_marker_it_shows(tmp_path: Path) -> None:
    from irminsul.listing.review import MARKER_MEANINGS

    root = _repo(tmp_path)
    write(
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
    _rewrite_one_sentence_and_delete_another(root)
    _edit_cli(root, "    return start\n", "    return start.parent\n")

    result = runner.invoke(
        app, ["list", "review", "--changed", "--format", "json", "--path", str(root)]
    )

    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    shown = {name.split(":")[0] for item in report["items"] for name in item["markers"]}
    assert shown == {"edited", "removed-sentence", "governing-claim", "evidence"}
    assert report["markers"] == {name: MARKER_MEANINGS[name] for name in sorted(shown)}


def test_review_explains_only_the_markers_of_the_items_it_shows(tmp_path: Path) -> None:
    from irminsul.listing.review import MARKER_MEANINGS

    root = _repo(tmp_path)

    assert json.loads(review_json(root, load(root / "irminsul.toml")))["markers"] == {}
    everything = json.loads(review_json(root, load(root / "irminsul.toml"), show_all=True))
    assert everything["markers"] == {"names-code": MARKER_MEANINGS["names-code"]}


def test_every_marker_meaning_is_short() -> None:
    from irminsul.listing.review import MARKER_MEANINGS

    assert set(MARKER_MEANINGS) == {
        "names-code",
        "edited",
        "unbound-name",
        "governing-claim",
        "evidence",
        "stale-summary",
        "moved-file",
        "removed-sentence",
    }
    assert all(len(meaning.split()) <= 35 for meaning in MARKER_MEANINGS.values())


def test_a_marker_with_no_meaning_cannot_be_shown(tmp_path: Path) -> None:
    from irminsul.listing.review import ReviewItem, review_to_json

    item = ReviewItem(path="a.md", line=1, sentence="A sentence.", markers=["invented-marker"])

    with pytest.raises(KeyError, match="invented-marker"):
        review_to_json([item], show_all=True)
