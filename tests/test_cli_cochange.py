"""End-to-end tests for `irminsul check --diff <base>` co-change enforcement.

Each test builds a real tmp git repo: a doc claims source files via
`describes`, commits land, and the CLI is asked whether the diff against a
base ref shipped the owning docs alongside their claimed code.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from irminsul.cli import app

from .conftest import cli_output, commit_all, config_toml, git, git_init

runner = CliRunner()

_DOC_BODY = (
    "---\n"
    "id: alpha\n"
    "title: Alpha\n"
    ""
    "status: stable\n"
    "describes:\n"
    "  - app/alpha.py\n"
    "  - app/beta.py\n"
    "---\n"
    "\n"
    "# Alpha\n"
)

_TOML = config_toml(project_name="cochange", source_roots=["app"], enabled=[])


def _seed_repo(tmp_path: Path) -> tuple[Path, str]:
    """Create a committed repo; return (root, base sha) for diffing against."""
    repo_root = tmp_path / "repo"
    (repo_root / "app").mkdir(parents=True)
    (repo_root / "app" / "alpha.py").write_text("a = 1\n", encoding="utf-8")
    (repo_root / "app" / "beta.py").write_text("b = 1\n", encoding="utf-8")
    (repo_root / "app" / "unclaimed.py").write_text("u = 1\n", encoding="utf-8")
    docs = repo_root / "docs" / "components"
    docs.mkdir(parents=True)
    (docs / "alpha.md").write_text(_DOC_BODY, encoding="utf-8")
    (repo_root / "irminsul.toml").write_text(_TOML, encoding="utf-8")
    git_init(repo_root)
    return repo_root, commit_all(repo_root, "seed")


def test_cochange_fires_when_claimed_source_changes_without_doc(tmp_path: Path) -> None:
    repo_root, base = _seed_repo(tmp_path)
    (repo_root / "app" / "alpha.py").write_text("a = 2\n", encoding="utf-8")
    commit_all(repo_root, "change source only")

    result = runner.invoke(app, ["check", "--diff", base, "--path", str(repo_root)])
    assert result.exit_code == 0  # warning, not error
    assert "[co-change/unreflected-change]" in result.stdout
    assert "docs/components/alpha.md" in result.stdout
    assert "app/alpha.py" in result.stdout
    assert "0 errors, 1 warning" in result.stdout


def test_cochange_silent_when_doc_changed_too(tmp_path: Path) -> None:
    repo_root, base = _seed_repo(tmp_path)
    (repo_root / "app" / "alpha.py").write_text("a = 2\n", encoding="utf-8")
    doc = repo_root / "docs" / "components" / "alpha.md"
    doc.write_text(_DOC_BODY + "\nNow `a` is 2.\n", encoding="utf-8")
    commit_all(repo_root, "change source and doc together")

    result = runner.invoke(app, ["check", "--diff", base, "--path", str(repo_root)])
    assert result.exit_code == 0
    assert "co-change" not in result.stdout
    assert "0 errors, 0 warnings" in result.stdout


def test_cochange_silent_for_unclaimed_files(tmp_path: Path) -> None:
    repo_root, base = _seed_repo(tmp_path)
    (repo_root / "app" / "unclaimed.py").write_text("u = 2\n", encoding="utf-8")
    commit_all(repo_root, "change unclaimed file")

    result = runner.invoke(app, ["check", "--diff", base, "--path", str(repo_root)])
    assert result.exit_code == 0
    assert "co-change" not in result.stdout
    assert "0 errors, 0 warnings" in result.stdout


def test_cochange_groups_files_into_one_finding_per_doc(tmp_path: Path) -> None:
    repo_root, base = _seed_repo(tmp_path)
    (repo_root / "app" / "alpha.py").write_text("a = 2\n", encoding="utf-8")
    (repo_root / "app" / "beta.py").write_text("b = 2\n", encoding="utf-8")
    commit_all(repo_root, "change both claimed sources")

    result = runner.invoke(app, ["check", "--diff", base, "--path", str(repo_root)])
    assert result.exit_code == 0
    assert result.stdout.count("[co-change/unreflected-change]") == 1
    assert "app/alpha.py, app/beta.py" in result.stdout
    assert "0 errors, 1 warning" in result.stdout


def test_cochange_invalid_base_ref_exits_2(tmp_path: Path) -> None:
    repo_root, _base = _seed_repo(tmp_path)

    result = runner.invoke(app, ["check", "--diff", "not-a-ref", "--path", str(repo_root)])
    assert result.exit_code == 2
    assert "not-a-ref" in cli_output(result)


def test_cochange_empty_diff_ref_exits_2(tmp_path: Path) -> None:
    """`--diff ""` must not silently disable the gate.

    A workflow templating `--diff ${{ github.base_ref }}` interpolates to the
    empty string on a `push` event; git resolves `...HEAD` as `HEAD...HEAD` and
    reports no changed files, so the gate would pass vacuously.
    """
    repo_root, _base = _seed_repo(tmp_path)
    (repo_root / "app" / "alpha.py").write_text("a = 2\n", encoding="utf-8")
    commit_all(repo_root, "change source only")

    for blank in ("", "   "):
        result = runner.invoke(app, ["check", "--diff", blank, "--path", str(repo_root)])
        assert result.exit_code == 2
        assert "--diff" in result.output
        assert "empty value" in result.output


def test_cochange_no_git_repository_message_distinguishes_from_bad_ref(tmp_path: Path) -> None:
    repo_root, _base = _seed_repo(tmp_path)
    # An irminsul root that is not itself a git root: refs are fine, git is not.
    nested = repo_root / "nested"
    (nested / "docs").mkdir(parents=True)
    (nested / "irminsul.toml").write_text(_TOML, encoding="utf-8")

    result = runner.invoke(app, ["check", "--diff", "HEAD", "--path", str(nested)])
    assert result.exit_code == 2
    assert "no git repository with commit history found" in result.output
    assert "could not be resolved" not in result.output


def test_cochange_fail_on_hint_promotes_to_exit_1(tmp_path: Path) -> None:
    repo_root, base = _seed_repo(tmp_path)
    (repo_root / "app" / "alpha.py").write_text("a = 2\n", encoding="utf-8")
    commit_all(repo_root, "change source only")

    result = runner.invoke(
        app, ["check", "--diff", base, "--fail-on", "hint", "--path", str(repo_root)]
    )
    assert result.exit_code == 1
    assert "[co-change/unreflected-change]" in result.stdout


def test_cochange_findings_in_json_output(tmp_path: Path) -> None:
    repo_root, base = _seed_repo(tmp_path)
    (repo_root / "app" / "alpha.py").write_text("a = 2\n", encoding="utf-8")
    commit_all(repo_root, "change source only")

    result = runner.invoke(
        app, ["check", "--diff", base, "--format", "json", "--path", str(repo_root)]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    cochange = [f for f in payload["findings"] if f["check"] == "co-change"]
    assert len(cochange) == 1
    assert cochange[0]["severity"] == "warning"
    assert cochange[0]["path"] == "docs/components/alpha.md"
    assert cochange[0]["doc_id"] == "alpha"
    assert cochange[0]["answer"] == "trailer"
    assert cochange[0]["subject"] == "docs/components/alpha.md"
    assert "app/alpha.py" in cochange[0]["message"]
    assert payload["summary"]["warnings"] == 1


def test_cochange_with_github_format(tmp_path: Path) -> None:
    repo_root, base = _seed_repo(tmp_path)
    (repo_root / "app" / "alpha.py").write_text("a = 2\n", encoding="utf-8")
    commit_all(repo_root, "change source only")

    result = runner.invoke(
        app, ["check", "--diff", base, "--format", "github", "--path", str(repo_root)]
    )
    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    annotations = [line for line in lines if line.startswith("::")]
    assert len(annotations) == 1
    assert annotations[0].startswith(
        "::warning file=docs/components/alpha.md,title=irminsul co-change/unreflected-change::"
    )
    assert "app/alpha.py" in annotations[0]
    assert "0 errors, 1 warning" in lines[-1]


def test_cochange_fires_for_deleted_claimed_file(tmp_path: Path) -> None:
    repo_root, base = _seed_repo(tmp_path)
    (repo_root / "app" / "alpha.py").unlink()
    commit_all(repo_root, "delete claimed source")
    result = runner.invoke(
        app, ["check", "--diff", base, "--format", "json", "--path", str(repo_root)]
    )
    data = json.loads(result.output)
    cochange = [f for f in data["findings"] if f["check"] == "co-change"]
    assert len(cochange) == 1
    assert "app/alpha.py" in cochange[0]["message"]


def test_cochange_is_not_satisfied_by_a_whitespace_only_doc_edit(tmp_path: Path) -> None:
    """One blank line in the owning doc used to count as shipping it with the code."""
    repo_root, base = _seed_repo(tmp_path)
    (repo_root / "app" / "alpha.py").write_text("a = 2\n", encoding="utf-8")
    doc = repo_root / "docs" / "components" / "alpha.md"
    doc.write_text(doc.read_text(encoding="utf-8") + "\n\n", encoding="utf-8")
    commit_all(repo_root, "change source, touch the doc cosmetically")

    result = runner.invoke(app, ["check", "--diff", base, "--path", str(repo_root)])
    assert "[co-change/unreflected-change]" in result.stdout
    assert "app/alpha.py" in result.stdout


def _hint_failing_diff(repo_root: Path, base: str) -> tuple[int, list[dict[str, str]]]:
    result = runner.invoke(
        app,
        [
            "check",
            "--diff",
            base,
            "--fail-on",
            "hint",
            "--format",
            "json",
            "--path",
            str(repo_root),
        ],
    )
    findings = json.loads(result.stdout)["findings"]
    return result.exit_code, [f for f in findings if f["check"] in ("co-change", "acknowledgement")]


@pytest.mark.parametrize("check", ["co-change", "co-change/unreflected-change"])
def test_a_reviewed_trailer_acknowledges_the_warning(tmp_path: Path, check: str) -> None:
    repo_root, base = _seed_repo(tmp_path)
    (repo_root / "app" / "alpha.py").write_text("a = 2\n", encoding="utf-8")
    commit_all(
        repo_root,
        f"change source only\n\nIrminsul-Reviewed: {check} docs/components/alpha.md "
        'reason="no value is named"',
    )

    exit_code, cochange = _hint_failing_diff(repo_root, base)
    assert exit_code == 0
    assert [(f["code"], f["severity"]) for f in cochange] == [
        ("co-change/unreflected-change", "info")
    ]
    assert '"no value is named"' in cochange[0]["message"]
    assert "app/alpha.py" in cochange[0]["message"]


@pytest.mark.parametrize(
    ("trailer", "problem"),
    [
        ("co-change docs/components/alpha.md", "gives no reason"),
        ('co-change docs/components/alpha.md reason=" "', "gives no reason"),
        ('co-change reason="still right"', "names no path"),
        ('evidence-drift docs/components/alpha.md reason="x"', "no check or finding code"),
        ("co-change alpha reason=unquoted", "is not written as"),
    ],
)
def test_a_trailer_that_acknowledges_nothing_is_reported(
    tmp_path: Path, trailer: str, problem: str
) -> None:
    repo_root, base = _seed_repo(tmp_path)
    (repo_root / "app" / "alpha.py").write_text("a = 2\n", encoding="utf-8")
    commit_all(repo_root, f"change source only\n\nIrminsul-Reviewed: {trailer}")

    exit_code, cochange = _hint_failing_diff(repo_root, base)
    assert exit_code == 1
    codes = sorted(f["code"] for f in cochange)
    assert codes == ["acknowledgement/invalid", "co-change/unreflected-change"]
    invalid = next(f for f in cochange if f["code"] == "acknowledgement/invalid")
    assert invalid["severity"] == "info"
    assert problem in invalid["message"]


def test_a_trailer_naming_a_doc_id_matches_nothing(tmp_path: Path) -> None:
    repo_root, base = _seed_repo(tmp_path)
    (repo_root / "app" / "alpha.py").write_text("a = 2\n", encoding="utf-8")
    commit_all(repo_root, 'change source only\n\nIrminsul-Reviewed: co-change alpha reason="x"')

    exit_code, cochange = _hint_failing_diff(repo_root, base)
    assert exit_code == 1
    assert sorted(f["code"] for f in cochange) == [
        "acknowledgement/unused",
        "co-change/unreflected-change",
    ]


def test_a_trailer_for_a_doc_with_no_warning_is_unused(tmp_path: Path) -> None:
    repo_root, base = _seed_repo(tmp_path)
    (repo_root / "app" / "alpha.py").write_text("a = 2\n", encoding="utf-8")
    doc = repo_root / "docs" / "components" / "alpha.md"
    doc.write_text(_DOC_BODY + "\nNow `a` is 2.\n", encoding="utf-8")
    commit_all(
        repo_root,
        "change source and doc\n\n"
        'Irminsul-Reviewed: co-change docs/components/alpha.md reason="still right"',
    )

    exit_code, cochange = _hint_failing_diff(repo_root, base)
    assert exit_code == 0, "a trailer cannot be removed without rewriting history"
    assert [(f["code"], f["severity"]) for f in cochange] == [("acknowledgement/unused", "info")]
    assert cochange[0]["path"] == "docs/components/alpha.md"


def test_a_trailer_naming_a_doc_that_is_not_there_is_unused(tmp_path: Path) -> None:
    repo_root, base = _seed_repo(tmp_path)
    (repo_root / "app" / "alpha.py").write_text("a = 2\n", encoding="utf-8")
    commit_all(
        repo_root,
        'change source only\n\nIrminsul-Reviewed: co-change docs/components/gone.md reason="x"',
    )

    exit_code, cochange = _hint_failing_diff(repo_root, base)
    assert exit_code == 1
    assert sorted(f["code"] for f in cochange) == [
        "acknowledgement/unused",
        "co-change/unreflected-change",
    ]


def test_a_trailer_before_the_base_acknowledges_nothing(tmp_path: Path) -> None:
    repo_root, _ = _seed_repo(tmp_path)
    git(
        repo_root,
        "commit",
        "--allow-empty",
        "-m",
        'earlier\n\nIrminsul-Reviewed: co-change docs/components/alpha.md reason="an older change"',
    )
    base = git(repo_root, "rev-parse", "HEAD")
    (repo_root / "app" / "alpha.py").write_text("a = 2\n", encoding="utf-8")
    commit_all(repo_root, "change source only")

    exit_code, cochange = _hint_failing_diff(repo_root, base)
    assert exit_code == 1
    assert [f["code"] for f in cochange] == ["co-change/unreflected-change"]
    assert (
        'Irminsul-Reviewed: co-change/unreflected-change docs/components/alpha.md reason="..."'
        in cochange[0]["suggestion"]
    )


def test_a_trailer_covers_only_the_changes_made_before_it(tmp_path: Path) -> None:
    """A reason written for the first change cannot vouch for one nobody re-read."""
    repo_root, base = _seed_repo(tmp_path)
    (repo_root / "app" / "alpha.py").write_text("a = 2\n", encoding="utf-8")
    commit_all(
        repo_root,
        "rename a value\n\nIrminsul-Reviewed: co-change docs/components/alpha.md "
        'reason="no value is named"',
    )
    (repo_root / "app" / "beta.py").write_text("def gone(): ...\n", encoding="utf-8")
    commit_all(repo_root, "change what beta does")

    exit_code, cochange = _hint_failing_diff(repo_root, base)
    assert exit_code == 1
    assert [f["code"] for f in cochange] == ["co-change/unreflected-change"]
    assert "predates the change to app/beta.py" in cochange[0]["suggestion"]


def test_a_later_change_outside_the_doc_leaves_the_trailer_standing(tmp_path: Path) -> None:
    repo_root, base = _seed_repo(tmp_path)
    (repo_root / "app" / "alpha.py").write_text("a = 2\n", encoding="utf-8")
    commit_all(
        repo_root,
        "rename a value\n\nIrminsul-Reviewed: co-change docs/components/alpha.md "
        'reason="no value is named"',
    )
    (repo_root / "app" / "unclaimed.py").write_text("u = 2\n", encoding="utf-8")
    commit_all(repo_root, "change a file no doc claims")

    exit_code, cochange = _hint_failing_diff(repo_root, base)
    assert exit_code == 0
    assert [(f["code"], f["severity"]) for f in cochange] == [
        ("co-change/unreflected-change", "info")
    ]


def test_what_the_base_gained_is_not_a_later_change(tmp_path: Path) -> None:
    """A pull request's checkout is a merge commit; the base's own commits since the branch
    was cut are not changes of this one, so they cannot outdate its trailer."""
    repo_root, _ = _seed_repo(tmp_path)
    alpha = repo_root / "app" / "alpha.py"
    alpha.write_text("a = 1\n\n\n\nz = 1\n", encoding="utf-8")
    commit_all(repo_root, "spread alpha out")
    main = git(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    git(repo_root, "switch", "-c", "pr")
    alpha.write_text("a = 2\n\n\n\nz = 1\n", encoding="utf-8")
    commit_all(
        repo_root,
        "rename a value\n\nIrminsul-Reviewed: co-change docs/components/alpha.md "
        'reason="no value is named"',
    )
    git(repo_root, "switch", main)
    alpha.write_text("a = 1\n\n\n\nz = 2\n", encoding="utf-8")
    commit_all(repo_root, "the base moves on")
    base = git(repo_root, "rev-parse", "HEAD")
    git(repo_root, "switch", "--detach", base)
    git(repo_root, "merge", "--no-ff", "pr", "-m", "Merge pr into the base")

    exit_code, cochange = _hint_failing_diff(repo_root, base)
    assert exit_code == 0
    assert [(f["code"], f["severity"]) for f in cochange] == [
        ("co-change/unreflected-change", "info")
    ]


_AT = _dt.datetime(2024, 1, 1, tzinfo=_dt.UTC)


def test_the_suggestion_says_the_trailer_goes_after_the_last_change(tmp_path: Path) -> None:
    repo_root, base = _seed_repo(tmp_path)
    (repo_root / "app" / "alpha.py").write_text("a = 2\n", encoding="utf-8")
    commit_all(repo_root, "change source only", when=_AT)

    _, cochange = _hint_failing_diff(repo_root, base)

    assert [f["code"] for f in cochange] == ["co-change/unreflected-change"]
    assert cochange[0]["suggestion"].endswith(
        'reason="..."` on the commit that carries the last change to app/alpha.py, or a later one'
    )


def test_an_overtaken_trailer_is_named_beside_the_same_clause(tmp_path: Path) -> None:
    repo_root, base = _seed_repo(tmp_path)
    (repo_root / "app" / "alpha.py").write_text("a = 2\n", encoding="utf-8")
    commit_all(
        repo_root,
        "rename a value\n\nIrminsul-Reviewed: co-change docs/components/alpha.md "
        'reason="no value is named"',
        when=_AT,
    )
    (repo_root / "app" / "beta.py").write_text("def gone(): ...\n", encoding="utf-8")
    commit_all(repo_root, "change what beta does", when=_AT)

    _, cochange = _hint_failing_diff(repo_root, base)

    suggestion = cochange[0]["suggestion"]
    assert (
        "on the commit that carries the last change to app/alpha.py, app/beta.py, or a later one"
        in suggestion
    )
    assert "predates the change to app/beta.py: that trailer does not count" in suggestion


def test_explain_co_change_names_the_trailer_form() -> None:
    result = runner.invoke(app, ["explain", "co-change/unreflected-change"])

    assert result.exit_code == 0, result.output
    assert (
        "acknowledge with: Irminsul-Reviewed: co-change/unreflected-change <path> [<subject>] "
        'reason="..."' in " ".join(result.output.split())
    )


def test_cochange_unresolvable_base_says_what_to_pass_instead(tmp_path: Path) -> None:
    repo_root, _base = _seed_repo(tmp_path)

    result = runner.invoke(app, ["check", "--diff", "origin/main", "--path", str(repo_root)])

    output = " ".join(cli_output(result).split())
    assert result.exit_code == 2
    assert "could not compute `git diff origin/main...HEAD`" in output
    assert "Pass a ref that exists here, such as the base commit or `HEAD~1`" in output
    assert "fetch `origin/main` first (`fetch-depth: 0` in CI)" in output
