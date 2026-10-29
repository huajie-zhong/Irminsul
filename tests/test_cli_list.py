"""Tests for `irminsul list undocumented`, `list lifecycle` and `list review`'s base flag."""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

from typer.testing import CliRunner

from irminsul.checks.base import Finding, Severity
from irminsul.cli import app
from irminsul.listing.command import _to_queue_item

from .conftest import commit_all, git, git_init, seed_repo, write, write_config

runner = CliRunner()

_LIFECYCLE_FIXTURE = Path(__file__).parent / "fixtures" / "repos" / "soft-lifecycle"
_BROWNFIELD_FIXTURE = Path(__file__).parent / "fixtures" / "repos" / "brownfield"


def test_list_undocumented_no_sources(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    write_config(repo)
    (repo / "docs").mkdir()
    result = runner.invoke(app, ["list", "undocumented", "--path", str(repo)])
    assert result.exit_code == 0
    assert "(none)" in result.output


def test_list_undocumented_default_only_covered_dirs() -> None:
    result = runner.invoke(app, ["list", "undocumented", "--path", str(_BROWNFIELD_FIXTURE)])
    assert result.exit_code == 0, result.output
    assert "app/core/helper.py" in result.output
    # Files outside covered directories are invisible without --all.
    assert "app/planner" not in result.output
    assert "app/util" not in result.output


def test_list_undocumented_all_shows_uncovered_files() -> None:
    result = runner.invoke(
        app, ["list", "undocumented", "--all", "--path", str(_BROWNFIELD_FIXTURE)]
    )
    assert result.exit_code == 0, result.output
    for expected in (
        "app/planner/route.py",
        "app/planner/solver.py",
        "app/planner/cost.py",
        "app/util/strings.py",
        "app/util/num.py",
        "app/core/helper.py",
    ):
        assert expected in result.output
    # Claimed and noise files never appear.
    assert "app/core/composer.py" not in result.output
    assert "__init__.py" not in result.output


def test_list_undocumented_all_groups_by_dir_descending() -> None:
    result = runner.invoke(
        app, ["list", "undocumented", "--all", "--path", str(_BROWNFIELD_FIXTURE)]
    )
    assert result.exit_code == 0, result.output
    lines = result.output.strip().splitlines()
    headers = [line for line in lines if not line.startswith("  ")]
    assert headers == [
        "app/planner (3 undocumented)",
        "app/util (2 undocumented)",
        "app/core (1 undocumented)",
    ]
    # Files are indented under their directory header.
    planner_start = lines.index("app/planner (3 undocumented)")
    assert lines[planner_start + 1 : planner_start + 4] == [
        "  app/planner/cost.py",
        "  app/planner/route.py",
        "  app/planner/solver.py",
    ]


def test_list_undocumented_all_json_shape() -> None:
    result = runner.invoke(
        app,
        ["list", "undocumented", "--all", "--format", "json", "--path", str(_BROWNFIELD_FIXTURE)],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert len(data) == 6
    assert all(
        set(entry) == {"check", "severity", "message", "path", "dir", "doc_id", "recorded_debt"}
        for entry in data
    )
    # This fixture never adopted, so nothing here is excepted. The key is present anyway:
    # a caller cannot tell recorded debt from new debt by a missing field.
    assert all(entry["recorded_debt"] is False for entry in data)
    first = data[0]
    assert first["check"] == "uniqueness"
    assert first["severity"] == "warning"
    assert first["dir"] == "app/planner"
    assert first["path"].startswith("app/planner/")
    assert {entry["path"] for entry in data} == {
        "app/planner/route.py",
        "app/planner/solver.py",
        "app/planner/cost.py",
        "app/util/strings.py",
        "app/util/num.py",
        "app/core/helper.py",
    }


def test_list_undocumented_all_cold_start(tmp_path: Path) -> None:
    """Zero claims anywhere: default shows nothing, --all shows everything."""
    repo = tmp_path / "r"
    (repo / "docs").mkdir(parents=True)
    (repo / "app").mkdir()
    write_config(repo, source_roots=["app"])
    (repo / "app" / "a.py").write_text("A = 1\n", encoding="utf-8")
    (repo / "app" / "b.py").write_text("B = 2\n", encoding="utf-8")

    default = runner.invoke(app, ["list", "undocumented", "--path", str(repo)])
    assert default.exit_code == 0, default.output
    assert "(none)" in default.output

    everything = runner.invoke(app, ["list", "undocumented", "--all", "--path", str(repo)])
    assert everything.exit_code == 0, everything.output
    assert "app (2 undocumented)" in everything.output
    assert "app/a.py" in everything.output
    assert "app/b.py" in everything.output


def test_list_undocumented_all_none(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    (repo / "docs").mkdir(parents=True)
    write_config(repo)
    result = runner.invoke(app, ["list", "undocumented", "--all", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    assert "(none)" in result.output


def test_list_lifecycle_queue_uses_required_update_categories() -> None:
    result = runner.invoke(
        app,
        [
            "list",
            "lifecycle",
            "--queue",
            "--format",
            "json",
            "--path",
            str(_LIFECYCLE_FIXTURE),
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert any("required update path" in item["reason"] for item in data)
    assert all("follow-up path" not in item["reason"] for item in data)


def test_lifecycle_queue_quotes_suggested_context_path() -> None:
    finding = Finding(
        check="rfc-follow-through",
        code="rfc-follow-through/update-missing-implements",
        severity=Severity.warning,
        message="required update doc is missing a backlink",
        path=Path("docs/components/doc with spaces.md"),
        doc_id="doc-with-spaces",
    )

    item = _to_queue_item(finding)
    assert item.suggested_command == 'irminsul context "docs/components/doc with spaces.md"'


def test_lifecycle_queue_prioritizes_missing_state() -> None:
    finding = Finding(
        check="rfc-lifecycle",
        code="rfc-lifecycle/missing-rfc-state",
        severity=Severity.error,
        message="RFC has no `rfc_state`",
        path=Path("docs/rfcs/0034-example.md"),
        doc_id="0034-example",
    )

    item = _to_queue_item(finding)
    assert item.priority == 1
    assert item.kind == "classify"


def _repo_with_one_edited_sentence(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "r"
    write_config(root)
    head = "---\nid: note\ntitle: Note\nstatus: stable\ndescribes: []\n---\n\n# Note\n\n"
    write(root, "docs/components/note.md", head + "Nothing here yet.\n")
    base = seed_repo(root, "seed", when=_dt.datetime(2024, 1, 1, tzinfo=_dt.UTC))
    write(root, "docs/components/note.md", head + "Nothing here yet.\n\nThe note was edited.\n")
    commit_all(root, "edit", when=_dt.datetime(2024, 1, 2, tzinfo=_dt.UTC))
    return root, base


def test_list_review_takes_the_base_ref_flag_the_other_commands_take(tmp_path: Path) -> None:
    root, base = _repo_with_one_edited_sentence(tmp_path)

    result = runner.invoke(
        app, ["list", "review", "--base-ref", base, "--format", "json", "--path", str(root)]
    )

    assert result.exit_code == 0, result.output
    assert [item["sentence"] for item in json.loads(result.output)["items"]] == [
        "The note was edited."
    ]


def test_list_review_no_longer_takes_the_shorter_base_flag(tmp_path: Path) -> None:
    root, base = _repo_with_one_edited_sentence(tmp_path)

    result = runner.invoke(app, ["list", "review", "--base", base, "--path", str(root)])

    assert result.exit_code == 2
    assert "No such option" in result.output


_NOTE = "docs/components/note.md"
_NOTE_HEAD = "---\nid: note\ntitle: Note\nstatus: stable\ndescribes: []\n---\n\n# Note\n\n"


def _branch_after_the_base_moved(tmp_path: Path) -> Path:
    """A feature branch that adds one sentence to a note while `main` added another to it."""
    root = tmp_path / "r"
    write_config(root)
    git_init(root, branch="main")
    write(root, _NOTE, _NOTE_HEAD + "Nothing here yet.\n")
    commit_all(root, "seed", when=_dt.datetime(2024, 1, 1, tzinfo=_dt.UTC))
    git(root, "checkout", "-q", "-b", "feature")
    write(root, _NOTE, _NOTE_HEAD + "Nothing here yet.\n\nThe feature sentence.\n")
    commit_all(root, "feature", when=_dt.datetime(2024, 1, 2, tzinfo=_dt.UTC))
    git(root, "checkout", "-q", "main")
    write(root, _NOTE, _NOTE_HEAD + "Nothing here yet.\n\nThe base branch sentence.\n")
    commit_all(root, "main moves on", when=_dt.datetime(2024, 1, 3, tzinfo=_dt.UTC))
    git(root, "checkout", "-q", "feature")
    return root


def _review(root: Path, *flags: str) -> list[dict[str, object]]:
    result = runner.invoke(app, ["list", "review", *flags, "--format", "json", "--path", str(root)])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)["items"]


def test_list_review_reads_the_ref_at_the_merge_base_not_its_moved_tip(tmp_path: Path) -> None:
    root = _branch_after_the_base_moved(tmp_path)

    items = _review(root, "--base-ref", "main")

    assert [(i["sentence"], i["markers"]) for i in items] == [("The feature sentence.", ["edited"])]


def test_list_review_changed_committed_only_without_a_base_ref_runs_no_git(
    tmp_path: Path,
) -> None:
    root = tmp_path / "plain"
    write_config(root)
    write(root, _NOTE, _NOTE_HEAD + "Nothing here yet.\n")

    result = runner.invoke(
        app,
        [
            "list",
            "review",
            "--changed",
            "--committed-only",
            "--format",
            "json",
            "--path",
            str(root),
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["items"] == []


def test_list_review_judges_uncommitted_work_unless_committed_only(tmp_path: Path) -> None:
    root = _branch_after_the_base_moved(tmp_path)
    committed = (root / _NOTE).read_text(encoding="utf-8")
    write(root, _NOTE, committed + "\nAn unsaved thought.\n")

    assert [i["sentence"] for i in _review(root, "--base-ref", "main")] == [
        "The feature sentence.",
        "An unsaved thought.",
    ]
    assert [i["sentence"] for i in _review(root, "--base-ref", "main", "--committed-only")] == [
        "The feature sentence."
    ]


def test_list_review_committed_only_reads_the_documents_at_head(tmp_path: Path) -> None:
    root = _branch_after_the_base_moved(tmp_path)
    committed = (root / _NOTE).read_text(encoding="utf-8")
    write(root, _NOTE, committed.replace("# Note\n\n", "# Note\n\nAn unsaved opener.\n\n"))

    assert [i["sentence"] for i in _review(root, "--base-ref", "main", "--committed-only")] == [
        "The feature sentence."
    ]
    assert "An unsaved opener." in [i["sentence"] for i in _review(root, "--base-ref", "main")]


def test_list_review_changed_committed_only_without_a_base_ref_judges_no_change(
    tmp_path: Path,
) -> None:
    root = _branch_after_the_base_moved(tmp_path)
    committed = (root / _NOTE).read_text(encoding="utf-8")
    write(root, _NOTE, committed + "\nAn unsaved thought.\n")

    result = runner.invoke(
        app,
        [
            "list",
            "review",
            "--changed",
            "--committed-only",
            "--format",
            "json",
            "--path",
            str(root),
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["items"] == []
    assert "nothing uncommitted is read" in result.stderr
    assert [i["sentence"] for i in _review(root, "--changed")] == ["An unsaved thought."]
