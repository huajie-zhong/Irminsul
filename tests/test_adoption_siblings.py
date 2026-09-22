"""The adoption boundary when the source code is a separate git repository.

Every test here builds two independently initialized repositories with their own
histories, because the thing under test is exactly what one repository's history cannot
say about another's. A sibling *directory* inside one repository would pass these tests
while proving nothing.

The single-repository half of the contract lives in `test_adoption.py`; the boundary there
is the diff's merge base, and it stays that way. Here the boundary is a revision the record
pins, and what these tests pin down is that it is verified, immutable, and fails closed.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from irminsul.adoption import AdoptionError, load_record
from irminsul.cli import app

runner = CliRunner()

#: `refs/heads/main` rather than `origin/main`: the fixtures build the code repository with
#: `git init` and no remote, so there is no remote-tracking ref to name. Both spellings are
#: accepted for the same reason — they are unambiguous — and
#: `test_a_remote_tracking_ref_resolves` covers the remote form against a real one.
_CONFIG = (
    'project_name = "ws"\n[paths]\ndocs_root = "docs"\nsource_roots = ["../code/src"]\n'
    '[[paths.sources]]\nname = "engine"\npath = "../code"\nref = "refs/heads/main"\n'
    '[checks]\nenabled = ["uniqueness", "test-ownership"]\n'
)
_INDEX = "---\nid: decisions\ntitle: D\nstatus: stable\n---\n\n# D\n"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=T", "-c", "user.email=t@e.com", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _commit(root: Path, message: str) -> str:
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", message)
    return _git(root, "rev-parse", "HEAD")


def _component(slug: str, *describes: str) -> str:
    claims = "\n".join(f'  - "{d}"' for d in describes)
    return (
        f'---\nid: {slug}\ntitle: "{slug.title()}"\nstatus: stable\n'
        f"describes:\n{claims}\n---\n\n# {slug.title()}\n\nIt does arithmetic.\n"
    )


@pytest.fixture
def workspace(tmp_path: Path) -> tuple[Path, Path]:
    """`(docs repo, code repo)`, side by side under one parent, each its own repository."""
    code, docs = tmp_path / "code", tmp_path / "docs"
    (code / "src").mkdir(parents=True)
    docs.mkdir()
    for name in ("a", "b", "c"):
        _write(code, f"src/{name}.py", f"def {name}() -> int:\n    return 1\n")
    _git(code, "init", "-q", "-b", "main")
    _commit(code, "the code repository as it stands")

    _write(docs, "irminsul.toml", _CONFIG)
    _write(docs, "docs/decisions/INDEX.md", _INDEX)
    _git(docs, "init", "-q", "-b", "main")
    _commit(docs, "the docs repository as it stands")
    return docs, code


def _run(root: Path, *args: str) -> tuple[int, str]:
    result = runner.invoke(app, [*args, "--path", str(root)])
    return result.exit_code, result.output


def _codes(root: Path, *extra: str) -> list[str]:
    result = runner.invoke(app, ["check", "--format", "json", *extra, "--path", str(root)])
    return sorted(
        f"{f['code']} {f.get('path') or ''}"
        for f in json.loads(result.output)["findings"]
        if f["severity"] == "error"
    )


def _add_entry(docs: Path, display: str, source: str = "engine") -> None:
    """Hand-add one cross-repository entry, which the record's own writer never would.

    An entry from another repository is an object naming its source, so a test that reaches
    for the raw JSON has to write one — and doing it through a helper is what keeps a format
    change from quietly turning these attacks into no-ops."""
    path = docs / ".irminsul-adoption.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unowned"] = [*payload["unowned"], {"path": display, "source": source}]
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _repin(docs: Path, revision: str | None, source: str = "engine") -> None:
    """Rewrite the record's boundary by hand, the way an attacker or a stale tool would."""
    path = docs / ".irminsul-adoption.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if revision is None:
        payload.pop("sources", None)
    else:
        payload["sources"] = [{"name": source, "revision": revision}]
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


# ------------------------------------------------------------- the boundary gets recorded


def test_adopting_pins_the_source_repository_revision(workspace: tuple[Path, Path]) -> None:
    """The docs repository's merge base cannot answer for the code repository, so the
    revision that one was at becomes part of the record."""
    docs, code = workspace
    head = _git(code, "rev-parse", "HEAD")

    code_exit, output = _run(docs, "check", "--init-adoption")

    assert code_exit == 0, output
    record = load_record(docs / ".irminsul-adoption.json")
    assert record.unowned == frozenset({"a.py", "b.py", "c.py"})
    assert record.revision_for("engine") == head
    # Every entry states the source it came from, so no later configuration edit re-derives
    # a different one for it.
    assert record.bindings == {"a.py": "engine", "b.py": "engine", "c.py": "engine"}
    # And the boundary is stated where somebody reviewing the adoption will read it.
    assert head[:12] in output


def test_a_pinned_record_leaves_the_tree_green(workspace: tuple[Path, Path]) -> None:
    docs, _ = workspace
    _run(docs, "check", "--init-adoption")

    assert _codes(docs) == []
    # The debt does not become invisible for having been verified.
    listing = _run(docs, "list", "undocumented", "--all")[1]
    assert "recorded debt" in listing


def test_adoption_refuses_a_source_repository_with_no_commit(tmp_path: Path) -> None:
    """A root with no history cannot supply a boundary, so no record is written at all."""
    code, docs = tmp_path / "code", tmp_path / "docs"
    (code / "src").mkdir(parents=True)
    _write(code, "src/a.py", "def a() -> int:\n    return 1\n")
    _git(code, "init", "-q", "-b", "main")  # initialized, never committed
    docs.mkdir()
    _write(docs, "irminsul.toml", _CONFIG)
    _write(docs, "docs/decisions/INDEX.md", _INDEX)
    _git(docs, "init", "-q", "-b", "main")
    _commit(docs, "docs")

    code_exit, output = _run(docs, "check", "--init-adoption")

    assert code_exit == 2
    assert "no commit to adopt at" in output
    assert not (docs / ".irminsul-adoption.json").exists()


# --------------------------------------------------- a file added after the boundary is new


def test_an_entry_absent_at_the_pinned_revision_is_not_debt(
    workspace: tuple[Path, Path],
) -> None:
    """The laundering case, and the reason the pin exists. `d.py` is in the record and in
    the working tree, and the code repository did not hold it at the adopted revision."""
    docs, code = workspace
    boundary = _git(code, "rev-parse", "HEAD")
    _write(code, "src/d.py", "def d() -> int:\n    return 4\n")
    _commit(code, "add d.py after the boundary")
    _run(docs, "check", "--init-adoption")
    _repin(docs, boundary)

    codes = _codes(docs)

    assert "adoption-record/debt-not-at-source-revision d.py" in codes
    # One finding for one file: the entry keeps excepting, so the generic ownership finding
    # does not also fire and say the same thing in weaker words.
    assert "uniqueness/undocumented-file d.py" not in codes


def test_a_file_present_at_the_pinned_revision_stays_excepted(
    workspace: tuple[Path, Path],
) -> None:
    """The other side of the rule. Deleting a recorded file later does not un-verify it:
    it was there at the boundary, which is the only question asked."""
    docs, code = workspace
    _run(docs, "check", "--init-adoption")
    (code / "src" / "b.py").unlink()
    _commit(code, "retire b.py")

    assert _codes(docs) == []


# --------------------------------------------------------------- failing closed, out loud


def test_an_absent_source_checkout_is_a_verification_failure_not_a_missing_file(
    workspace: tuple[Path, Path], tmp_path: Path
) -> None:
    """The adopting obligation that every entry match the configured walk must not fire here.

    With the sibling repository absent, every path under its root looks like a path no root
    produces — so the rule that catches a hand-written entry naming nothing would accuse the
    whole record, and it would be wrong about every line. Which files exist is *unknown*, and
    the honest finding says so. Nothing is quietly accepted either: the run still fails.
    """
    docs, code = workspace
    base = _git(docs, "rev-parse", "HEAD")
    _write(
        docs,
        ".irminsul-adoption.json",
        json.dumps(
            {
                "version": 1,
                "unowned": ["a.py"],
                "sources": [{"name": "engine", "revision": _git(code, "rev-parse", "HEAD")}],
            }
        )
        + "\n",
    )
    _commit(docs, "adopt")
    (code / ".git").rename(tmp_path / "git-moved-away")
    for path in sorted((code / "src").iterdir()):
        path.unlink()
    (code / "src").rmdir()

    codes = _codes(docs, "--diff", base)

    assert "adoption-record/source-unverifiable .irminsul-adoption.json" in codes
    assert not [c for c in codes if "adoption-debt-not-managed" in c], codes


def test_an_unpinned_cross_repo_record_fails_closed(workspace: tuple[Path, Path]) -> None:
    """What a record written before the boundary existed looks like. It is not accepted
    quietly, and it is not reported as verified history either."""
    docs, _ = workspace
    _run(docs, "check", "--init-adoption")
    _repin(docs, None)

    codes = _codes(docs)

    assert "adoption-record/source-unverifiable .irminsul-adoption.json" in codes


def test_a_pin_the_source_repository_does_not_hold_fails_closed(
    workspace: tuple[Path, Path],
) -> None:
    docs, _ = workspace
    _run(docs, "check", "--init-adoption")
    _repin(docs, "0" * 40)

    assert "adoption-record/source-unverifiable .irminsul-adoption.json" in _codes(docs)


def test_a_source_repository_with_no_git_fails_closed(workspace: tuple[Path, Path]) -> None:
    """Dropping the root from the boundary list was a way to fail open: with no `.git`
    above it, nothing checked its entries and they went on excepting."""
    docs, code = workspace
    _run(docs, "check", "--init-adoption")
    for child in sorted((code / ".git").rglob("*"), reverse=True):
        child.chmod(0o700)
    subprocess.run(["rm", "-rf", str(code / ".git")], check=False)

    if (code / ".git").exists():  # pragma: no cover - platform dependent
        pytest.skip("could not remove the source repository's .git")
    assert "adoption-record/source-unverifiable .irminsul-adoption.json" in _codes(docs)


def test_a_pinned_root_the_config_stopped_declaring_still_answers(
    workspace: tuple[Path, Path],
) -> None:
    """Dropping the root from `source_roots` must not be the way an exception stops being
    checked while its entries stay in the record."""
    docs, _ = workspace
    _run(docs, "check", "--init-adoption")
    _write(docs, "irminsul.toml", _CONFIG.replace('["../code/src"]', '["../code/nothing"]'))
    _repin(docs, "0" * 40, source="gone")

    assert "adoption-record/source-unverifiable .irminsul-adoption.json" in _codes(docs)


# ------------------------------------------------------------------ the boundary is a pin


def test_the_pin_cannot_move_in_a_pull_request(workspace: tuple[Path, Path]) -> None:
    """Moving the boundary forward turns everything the source gained since into debt,
    which is the record growing with no line added to it."""
    docs, code = workspace
    _run(docs, "check", "--init-adoption")
    base = _commit(docs, "adopt")
    _write(code, "src/z.py", "def z() -> int:\n    return 9\n")
    _commit(code, "the code repository moves on")
    _repin(docs, _git(code, "rev-parse", "HEAD"))
    _commit(docs, "move the boundary forward")

    codes = _codes(docs, "--diff", base)

    assert "diff-integrity/adoption-source-rebound .irminsul-adoption.json" in codes


def test_pointing_the_root_at_another_repository_is_reported(
    workspace: tuple[Path, Path], tmp_path: Path
) -> None:
    """The move no pin comparison can see, and the reason the entry-to-boundary resolution is
    stated once rather than approached from three sides.

    An entry is not bound to a root; it is bound to whichever root the walk resolves its
    display to. Swapping `../code/src` for another repository that spells its files the same
    way re-points every existing entry at a different history — while the recorded pin is
    untouched, its root is untouched, and no pin is added. The three pin rules compare shared
    pins, pins that went away, and pins that arrived, and this is none of those.
    """
    docs, _ = workspace
    other = tmp_path / "other"
    (other / "src").mkdir(parents=True)
    for name in ("a", "b", "c"):
        _write(other, f"src/{name}.py", f"def {name}() -> int:\n    return 2\n")
    _git(other, "init", "-q", "-b", "main")
    _commit(other, "an unrelated repository spelling its files the same way")

    _run(docs, "check", "--init-adoption")
    base = _commit(docs, "adopt")
    _write(docs, "irminsul.toml", _CONFIG.replace('["../code/src"]', '["../other/src"]'))
    _commit(docs, "point the root at another repository, leaving the pin alone")

    assert "diff-integrity/adoption-source-rebound .irminsul-adoption.json" in _codes(
        docs, "--diff", base
    )


def test_dropping_the_root_with_no_replacement_is_reported_by_the_gate(
    workspace: tuple[Path, Path],
) -> None:
    """The quietest version of the same move, and the one the entry comparison cannot see.

    Stop configuring the root and add nothing in its place: the pin stays, so every pin rule
    is satisfied, and the entries leave the walk entirely, so they read as a stale record
    rather than as a boundary that moved. Their exceptions are still honoured and nothing is
    checking them, which is the state the seal exists to refuse.
    """
    docs, _ = workspace
    _run(docs, "check", "--init-adoption")
    base = _commit(docs, "adopt")
    _write(
        docs,
        "irminsul.toml",
        _CONFIG.replace('source_roots = ["../code/src"]', "source_roots = []"),
    )
    _commit(docs, "stop configuring the root, keep the pin and the entries")

    assert "diff-integrity/adoption-source-rebound .irminsul-adoption.json" in _codes(
        docs, "--diff", base
    )


def test_a_documented_entry_retiring_is_not_a_rebound(workspace: tuple[Path, Path]) -> None:
    """The invariant is about the boundary moving, not about the record changing. Retiring an
    entry the ordinary way leaves every surviving entry answering to the same pair."""
    docs, _ = workspace
    _run(docs, "check", "--init-adoption")
    base = _commit(docs, "adopt")
    _write(docs, "docs/components/alpha.md", _component("alpha", "a.py"))
    _run(docs, "check", "--update-adoption")
    _commit(docs, "document a.py and retire its entry")

    assert not [code for code in _codes(docs, "--diff", base) if "adoption-source-rebound" in code]


def test_removing_the_pin_in_a_pull_request_is_reported(workspace: tuple[Path, Path]) -> None:
    docs, _ = workspace
    _run(docs, "check", "--init-adoption")
    base = _commit(docs, "adopt")
    _repin(docs, None)
    _commit(docs, "drop the boundary")

    assert "diff-integrity/adoption-source-rebound .irminsul-adoption.json" in _codes(
        docs, "--diff", base
    )


def test_pin_adoption_sources_repairs_a_legacy_record_once(
    workspace: tuple[Path, Path],
) -> None:
    """The upgrade path for a record written before the boundary was recorded — and it is
    a one-way door, because a pin that moves is a boundary that moves."""
    docs, code = workspace
    _run(docs, "check", "--init-adoption")
    _repin(docs, None)
    assert "adoption-record/source-unverifiable .irminsul-adoption.json" in _codes(docs)

    exit_code, output = _run(docs, "check", "--pin-adoption-sources")
    assert exit_code == 0 and "pinned" in output
    assert _codes(docs) == []

    _write(code, "src/z.py", "def z() -> int:\n    return 9\n")
    _commit(code, "the code repository moves on")
    pinned = load_record(docs / ".irminsul-adoption.json").revision_for("../code/src")

    exit_code, output = _run(docs, "check", "--pin-adoption-sources")

    assert exit_code == 0 and "already pinned" in output
    assert load_record(docs / ".irminsul-adoption.json").revision_for("../code/src") == pinned


def test_update_adoption_does_not_move_the_boundary(workspace: tuple[Path, Path]) -> None:
    """Retiring entries is housekeeping; the revision they were history at is not a thing
    that retires."""
    docs, _ = workspace
    _run(docs, "check", "--init-adoption")
    pinned = load_record(docs / ".irminsul-adoption.json").revision_for("../code/src")
    _write(docs, "docs/components/bee.md", _component("bee", "b.py"))

    exit_code, output = _run(docs, "check", "--update-adoption")

    assert exit_code == 0, output
    record = load_record(docs / ".irminsul-adoption.json")
    assert "b.py" not in record.unowned
    assert record.revision_for("../code/src") == pinned


def test_a_duplicate_pin_is_refused(workspace: tuple[Path, Path]) -> None:
    """One root has one adoption revision; two would make which one applies a coin toss."""
    docs, _ = workspace
    _run(docs, "check", "--init-adoption")
    path = docs / ".irminsul-adoption.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["sources"] = [
        {"name": "engine", "revision": "a" * 40},
        {"name": "engine", "revision": "b" * 40},
    ]
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(AdoptionError, match="pins the same source twice"):
        load_record(path)


# ------------------------------------------- the rest of the contract, across the boundary


def test_an_exception_cannot_revive_across_the_boundary(workspace: tuple[Path, Path]) -> None:
    """The audit's rule, on a file in the other repository: owned at the base, unowned
    now, and a record that still names it."""
    docs, _ = workspace
    _run(docs, "check", "--init-adoption")
    _commit(docs, "adopt")
    _write(docs, "docs/components/bee.md", _component("bee", "b.py"))
    base = _commit(docs, "document b.py, record left stale")
    (docs / "docs/components/bee.md").unlink()
    _commit(docs, "remove the owner")

    assert "diff-integrity/adoption-exception-revived b.py" in _codes(docs, "--diff", base)


def test_a_new_file_in_the_source_repository_inherits_no_exception(
    workspace: tuple[Path, Path],
) -> None:
    docs, code = workspace
    _run(docs, "check", "--init-adoption")
    _write(code, "src/newpkg/deep/mod.py", "def mod() -> int:\n    return 1\n")
    _commit(code, "a whole new package, undocumented")

    assert "uniqueness/undocumented-file newpkg/deep/mod.py" in _codes(docs)


# ------------------------------------------- the source repository's own changes, judged


def _origin(repo: Path, bare: Path) -> None:
    """Give a repository an `origin` so `origin/main` resolves, as CI's checkout does."""
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "push", "-q", "origin", "main")
    _git(repo, "fetch", "-q", "origin")


def test_a_source_pull_request_that_edits_recorded_debt_is_caught(
    workspace: tuple[Path, Path], tmp_path: Path
) -> None:
    """Touch-to-own, across the boundary. Editing a recorded unowned file means
    documenting it, and the docs repository's own diff cannot see that the edit happened."""
    docs, code = workspace
    _run(docs, "check", "--init-adoption")
    _commit(docs, "adopt")
    _origin(code, tmp_path / "code.git")
    _write(code, "src/b.py", "def b() -> int:\n    return 99\n")
    _commit(code, "edit recorded debt without documenting it")

    # What the docs-repo gate alone sees: nothing. This is the gap, stated as a test.
    assert "diff-integrity/adoption-debt-touched b.py" not in _codes(docs, "--diff", "HEAD")
    # What the code-repo gate sees, with the source range supplied.
    codes = _codes(docs, "--diff", "HEAD", "--source-diff", "origin/main")

    assert "diff-integrity/adoption-debt-touched b.py" in codes


def test_a_source_change_that_documents_the_file_passes(
    workspace: tuple[Path, Path], tmp_path: Path
) -> None:
    docs, code = workspace
    _run(docs, "check", "--init-adoption")
    _origin(code, tmp_path / "code.git")
    _write(code, "src/b.py", "def b() -> int:\n    return 99\n")
    _commit(code, "edit b.py")
    _write(docs, "docs/components/bee.md", _component("bee", "b.py"))
    _run(docs, "check", "--update-adoption")

    codes = _codes(docs, "--diff", "HEAD", "--source-diff", "origin/main")

    assert "diff-integrity/adoption-debt-touched b.py" not in codes


def test_a_source_change_elsewhere_does_not_trip_touch_to_own(
    workspace: tuple[Path, Path], tmp_path: Path
) -> None:
    """The exception is for code nobody has gone back to; a change somewhere else in the
    source repository is not somebody going back to it."""
    docs, code = workspace
    _run(docs, "check", "--init-adoption")
    _origin(code, tmp_path / "code.git")
    _write(code, "README.md", "hello\n")
    _commit(code, "a readme, nothing managed")

    assert _codes(docs, "--diff", "HEAD", "--source-diff", "origin/main") == []


def test_source_diff_without_a_range_in_this_repository_is_a_usage_error(
    workspace: tuple[Path, Path],
) -> None:
    """`diff-integrity` runs only when this repository has a range too, so accepting
    `--source-diff` alone would report a clean run having judged nothing."""
    docs, _ = workspace
    _run(docs, "check", "--init-adoption")

    exit_code, output = _run(docs, "check", "--source-diff", "origin/main")

    assert exit_code == 2
    assert "needs a base in this one too" in output


def test_a_source_range_that_cannot_be_read_exits_rather_than_passing(
    workspace: tuple[Path, Path],
) -> None:
    """An empty change set and an unreadable one look identical to the rule that reads it,
    and one of them means every source change goes unjudged."""
    docs, _ = workspace
    _run(docs, "check", "--init-adoption")

    exit_code, output = _run(docs, "check", "--diff", "HEAD", "--source-diff", "origin/nope")

    assert exit_code == 2
    assert "could not read a source change set" in output


def test_an_uncommitted_same_repo_project_still_adopts(tmp_path: Path) -> None:
    """A project in no git at all is an ordinary state here — `history-depth/no-history` is
    only a hint — and its own source roots are not another repository's files.

    The cross-repo test is "outside this repository", and with no `.git` to anchor that,
    the invocation directory has to stand in for it. Anchoring on the git root alone made
    every root of an uncommitted project look foreign, and `--init-adoption` refused.
    """
    (tmp_path / "src").mkdir()
    _write(tmp_path, "src/a.py", "def a() -> int:\n    return 1\n")
    _write(
        tmp_path,
        "irminsul.toml",
        'project_name = "solo"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n'
        '[checks]\nenabled = ["uniqueness"]\n',
    )
    _write(tmp_path, "docs/decisions/INDEX.md", _INDEX)

    exit_code, output = _run(tmp_path, "check", "--init-adoption")

    assert exit_code == 0, output
    record = load_record(tmp_path / ".irminsul-adoption.json")
    assert record.unowned == frozenset({"src/a.py"})
    # Nothing to pin: the root is this project's own, so no cross-repository boundary exists.
    assert record.sources == ()


def test_a_root_outside_an_uncommitted_project_is_still_cross_repo(tmp_path: Path) -> None:
    """The other half of that fallback. Outside the invocation directory and in no git is
    exactly the shape that cannot be verified, so it must not pass as same-repo."""
    docs, code = tmp_path / "docs", tmp_path / "code"
    (code / "src").mkdir(parents=True)
    _write(code, "src/a.py", "def a() -> int:\n    return 1\n")
    docs.mkdir()
    _write(docs, "irminsul.toml", _CONFIG)
    _write(docs, "docs/decisions/INDEX.md", _INDEX)

    exit_code, output = _run(docs, "check", "--init-adoption")

    assert exit_code == 2
    assert "no git repository was found" in output
    assert not (docs / ".irminsul-adoption.json").exists()


# ------------------------------------------------- a declared test root in the other repo


_TEST_ROOT_CONFIG = (
    'project_name = "ws"\n[paths]\ndocs_root = "docs"\nsource_roots = ["../code/src"]\n'
    'test_roots = ["../code/tests"]\n'
    '[[paths.sources]]\nname = "engine"\npath = "../code"\nref = "refs/heads/main"\n'
    '[checks]\nenabled = ["uniqueness", "test-ownership"]\n'
)


def _workspace_with_cross_repo_tests(tmp_path: Path) -> tuple[Path, Path]:
    code, docs = tmp_path / "code", tmp_path / "docs"
    (code / "src").mkdir(parents=True)
    (code / "tests").mkdir(parents=True)
    docs.mkdir()
    _write(code, "src/a.py", "def a() -> int:\n    return 1\n")
    _write(code, "tests/test_a.py", "def test_a() -> None:\n    assert True\n")
    _git(code, "init", "-q", "-b", "main")
    _commit(code, "the code repository as it stands")
    _write(docs, "irminsul.toml", _TEST_ROOT_CONFIG)
    _write(docs, "docs/decisions/INDEX.md", _INDEX)
    _git(docs, "init", "-q", "-b", "main")
    _commit(docs, "the docs repository as it stands")
    return docs, code


def test_a_cross_repo_test_root_is_pinned_too(tmp_path: Path) -> None:
    """`paths.test_roots` is not a source root, and the record covers tests, so a declared
    test tree in the other repository needs a boundary of its own."""
    docs, code = _workspace_with_cross_repo_tests(tmp_path)

    exit_code, output = _run(docs, "check", "--init-adoption")

    assert exit_code == 0, output
    record = load_record(docs / ".irminsul-adoption.json")
    assert record.unowned == frozenset({"a.py", "test_a.py"})
    head = _git(code, "rev-parse", "HEAD")
    # One pin, not two. The source root and the test root are two directories in one
    # repository, so they share one history and one boundary; a pin each could drift apart
    # and there would be no answer to which of them the entries were adopted against.
    assert [(item.source, item.revision) for item in record.sources] == [("engine", head)]
    assert record.bindings == {"a.py": "engine", "test_a.py": "engine"}


def test_a_new_cross_repo_test_cannot_be_recorded_as_debt(tmp_path: Path) -> None:
    """The fail-open this closed. The test tree was outside the boundary list, so its
    entries resolved to no repository, nothing checked them, and a brand-new test
    hand-added to the record was accepted in silence.
    """
    docs, code = _workspace_with_cross_repo_tests(tmp_path)
    _run(docs, "check", "--init-adoption")
    _write(code, "tests/test_new.py", "def test_new() -> None:\n    assert True\n")
    _commit(code, "a brand new test, after the boundary")
    _add_entry(docs, "test_new.py")

    codes = _codes(docs)

    assert "adoption-record/debt-not-at-source-revision test_new.py" in codes


# ------------------------------------------- an absent checkout is the quietest state there is


def test_an_absent_source_checkout_fails_closed(workspace: tuple[Path, Path]) -> None:
    """The one that mattered most. A configured root outside this repository used to be
    dropped from the boundary list when its directory was missing, so nothing resolved to
    it, nothing was pinned or checked, and the gate went green on a tree it could not see —
    making a failed checkout *quieter* than a present one. A wrong `path:` in the copied
    workflow is enough to reach it.
    """
    docs, code = workspace
    _run(docs, "check", "--init-adoption")
    _repin(docs, None)  # a record written before pins existed
    code.rename(code.parent / "code-elsewhere")

    codes = _codes(docs)

    assert "adoption-record/source-unverifiable .irminsul-adoption.json" in codes


def test_an_absent_source_checkout_does_not_empty_the_record(
    workspace: tuple[Path, Path],
) -> None:
    """`--update-adoption` reads "no unowned files" off the managed walk, and an absent tree
    makes that walk smaller rather than louder. Following the advice the note used to print
    retired every entry and left recovery to git."""
    docs, code = workspace
    _run(docs, "check", "--init-adoption")
    before = load_record(docs / ".irminsul-adoption.json").unowned
    code.rename(code.parent / "code-elsewhere")

    exit_code, output = _run(docs, "check", "--update-adoption")

    assert exit_code == 2
    assert "not on disk" in output
    assert load_record(docs / ".irminsul-adoption.json").unowned == before
    # And the note does not recommend the command that would have done it.
    note = _run(docs, "check")[1]
    assert "--update-adoption" not in note.split("adoption:")[-1].split("Do not run")[0]
    assert "how much debt is left is unknown" in note


def test_a_pinned_root_with_nothing_recorded_from_it_is_not_a_finding(
    workspace: tuple[Path, Path],
) -> None:
    """A boundary with nothing resting on it must not fail a run. A shallow clone or a
    commit a squash-merge rewrote is enough to make the pin unreadable, and if every entry
    from that root has been documented there is nothing the answer would change."""
    docs, code = workspace
    _run(docs, "check", "--init-adoption")
    # Document every file the root contributed, and retire the entries.
    _write(docs, "docs/components/all.md", _component("all", "*.py"))
    _run(docs, "check", "--update-adoption")
    _write(code, "src/d.py", "def d() -> int:\n    return 4\n")
    _commit(code, "something else entirely")
    _repin(docs, "0" * 40)

    codes = _codes(docs)

    assert "adoption-record/source-unverifiable .irminsul-adoption.json" not in codes


def test_pinning_keeps_a_pin_whose_source_has_no_configured_root(
    workspace: tuple[Path, Path], tmp_path: Path
) -> None:
    """`--pin-adoption-sources` built the new record from what is configured *now*, so a pin
    whose source had stopped being walked disappeared without a word — and a record that
    loses a pin is what `diff-integrity/adoption-source-rebound` calls a weakening, so the
    repair command produced a state this branch's own gate rejects.

    Under declared sources the scenario is sharper than it was: the pin is keyed by the
    source, so it survives a root being renamed inside the same repository, and the only way
    to strand one is to stop configuring any root in that repository at all. That is what
    this does — the roots move to a second repository, and `engine`'s pin has to stay.
    """
    docs, _ = workspace
    extra = tmp_path / "extra"
    (extra / "src").mkdir(parents=True)
    _write(extra, "src/z.py", "def z() -> int:\n    return 1\n")
    _git(extra, "init", "-q", "-b", "main")
    _commit(extra, "a second repository")
    _run(docs, "check", "--init-adoption")
    pinned = load_record(docs / ".irminsul-adoption.json").revision_for("engine")
    _write(
        docs,
        "irminsul.toml",
        _CONFIG.replace(
            'source_roots = ["../code/src"]', 'source_roots = ["../extra/src"]'
        ).replace(
            '[[paths.sources]]\nname = "engine"\npath = "../code"\nref = "refs/heads/main"\n',
            '[[paths.sources]]\nname = "engine"\npath = "../code"\nref = "refs/heads/main"\n'
            '[[paths.sources]]\nname = "extra"\npath = "../extra"\nref = "refs/heads/main"\n',
        ),
    )

    exit_code, output = _run(docs, "check", "--pin-adoption-sources")

    assert exit_code == 0, output
    record = load_record(docs / ".irminsul-adoption.json")
    assert record.revision_for("engine") == pinned
    # And `extra` is *not* pinned, because no entry is bound to it. A pin grants nothing on
    # its own and every pin is preserved for ever, so recording one for a repository the
    # record says nothing about would couple it here permanently with no way to remove it.
    assert record.revision_for("extra") is None
    assert "no longer has a configured root" in output


def test_a_failed_record_write_leaves_the_record_intact(workspace: tuple[Path, Path]) -> None:
    """The record is replaced, not unlinked-then-written. `--init-adoption` refuses to
    overwrite, so a half-finished write would have left nothing it could rebuild."""
    import irminsul.adoption as adoption

    docs, _ = workspace
    _run(docs, "check", "--init-adoption")
    path = docs / ".irminsul-adoption.json"
    before = path.read_text(encoding="utf-8")

    original = adoption.os.replace  # type: ignore[attr-defined]
    try:
        adoption.os.replace = lambda *a, **k: (_ for _ in ()).throw(OSError("disk full"))  # type: ignore[attr-defined]
        with pytest.raises(OSError):
            adoption.shrink_adoption(path, set())
    finally:
        adoption.os.replace = original  # type: ignore[attr-defined]

    assert path.read_text(encoding="utf-8") == before


# ------------------------------------------- test ownership across the repository boundary


def _workspace_with_cross_repo_tests_and_helper(tmp_path: Path) -> tuple[Path, Path]:
    """Two repositories, the code one holding a declared test root with a helper in it."""
    code, docs = tmp_path / "code", tmp_path / "docs"
    (code / "src").mkdir(parents=True)
    (code / "tests").mkdir(parents=True)
    docs.mkdir()
    _write(code, "src/a.py", "def a() -> int:\n    return 1\n")
    _write(code, "tests/test_a.py", "def test_a() -> None:\n    assert True\n")
    _write(code, "tests/helpers.py", "def helper() -> int:\n    return 1\n")
    _git(code, "init", "-q", "-b", "main")
    _commit(code, "the code repository as it stands")
    _write(docs, "irminsul.toml", _TEST_ROOT_CONFIG)
    _write(docs, "docs/decisions/INDEX.md", _INDEX)
    _git(docs, "init", "-q", "-b", "main")
    _commit(docs, "the docs repository as it stands")
    return docs, code


def _owner(slug: str, describes: str, *owns: str) -> str:
    owned = "\n".join(f'  - "{item}"' for item in owns)
    return (
        f'---\nid: {slug}\ntitle: "{slug.title()}"\nstatus: stable\n'
        f'describes:\n  - "{describes}"\nowns_tests:\n{owned}\n---\n\n'
        f"# {slug.title()}\n\nIt does arithmetic.\n\n## Scope & Limitations\n\nNothing.\n"
    )


def test_a_cross_repo_test_can_actually_be_owned(tmp_path: Path) -> None:
    """The siblings layout mandates a code root, so Irminsul knows where a declared test
    lives. `owns_tests: [test_a.py]` used to be resolved against *this* repository — it
    looked for `docs/test_a.py`, found nothing, and reported both `owned-test-missing` on
    the doc and `unowned-test` on the file. There was no declaration that made it green.
    """
    docs, _ = _workspace_with_cross_repo_tests_and_helper(tmp_path)
    _write(docs, "docs/components/alpha.md", _owner("alpha", "a.py", "test_a.py", "helpers.py"))

    assert _codes(docs) == []


def test_a_helper_in_a_declared_cross_repo_test_root_must_be_claimed(tmp_path: Path) -> None:
    """A non-test-shaped file inside a *declared* test root answers to the test policy —
    declaring the root is the act of agreeing to that. Membership was matched by comparing
    the display with the root's spelling, which cannot work across the boundary: `helpers.py`
    from `../code/tests` matched nothing, so it answered to neither policy and no document
    was ever asked to claim it.
    """
    docs, _ = _workspace_with_cross_repo_tests_and_helper(tmp_path)
    _write(docs, "docs/components/alpha.md", _owner("alpha", "a.py", "test_a.py"))

    codes = _codes(docs)

    assert "test-ownership/unowned-test helpers.py" in codes


def test_the_two_policies_still_partition_a_cross_repo_helper(tmp_path: Path) -> None:
    """Governed by one rule, not both and not neither. A file the test policy took is
    exempt from `describes:` ownership — that is the partition `uniqueness` waives for —
    so exactly one finding names it, and `list undocumented` is not where to look for it.
    """
    docs, _ = _workspace_with_cross_repo_tests_and_helper(tmp_path)

    codes = _codes(docs)

    assert "test-ownership/unowned-test helpers.py" in codes
    assert "uniqueness/undocumented-file helpers.py" not in codes


# ------------------------------------------- what the second review round found in this work


def test_a_symbolic_pin_is_refused(workspace: tuple[Path, Path]) -> None:
    """A boundary has to be a fixed point, and a name is not one. `rev-parse --verify` is
    happy with `HEAD` and with a branch, so a record pinned that way verified against
    whatever the sibling repository happened to be — and because the recorded string never
    changed, nothing could see the boundary moving forward.
    """
    docs, code = workspace
    _run(docs, "check", "--init-adoption")
    _write(code, "src/brand_new.py", "def brand_new() -> int:\n    return 9\n")
    _commit(code, "a file committed after any sane boundary")
    path = docs / ".irminsul-adoption.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["sources"] = [{"name": "engine", "revision": "HEAD"}]
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _add_entry(docs, "brand_new.py")

    with pytest.raises(AdoptionError, match="not a commit id"):
        load_record(path)
    # And the run says so rather than accepting the brand-new file as debt.
    assert "adoption-record/unreadable .irminsul-adoption.json" in _codes(docs)


def test_the_record_is_validated_without_uniqueness_enabled(workspace: tuple[Path, Path]) -> None:
    """The pass has to run wherever the enabled checks run. Registering it only gave it a
    class and an explanation; it executed from `cli.check` alone, so the change lifecycle
    gates and `list` read an unverifiable record as a clean one.
    """
    from irminsul.checks.pipeline import enabled_findings
    from irminsul.config import load
    from irminsul.docgraph import build_graph

    docs, _ = workspace
    _run(docs, "check", "--init-adoption")
    _repin(docs, None)

    graph = build_graph(docs, load(docs / "irminsul.toml"))
    codes = [finding.code for finding in enabled_findings(graph)]

    assert "adoption-record/source-unverifiable" in codes


def test_owns_tests_cannot_buy_a_source_file_out_of_touch_to_own(
    workspace: tuple[Path, Path], tmp_path: Path
) -> None:
    """`owns_tests` naming ordinary source is rejected by `test-ownership` — a check a
    repository may leave out of `checks.enabled`. While the declaration counted as ownership
    regardless, editing recorded debt and declaring it bought its way out of touch-to-own,
    and the record went on excepting the file.
    """
    docs, code = workspace
    _run(docs, "check", "--init-adoption")
    _commit(docs, "adopt")
    _write(docs, "irminsul.toml", _CONFIG.replace('"uniqueness", "test-ownership"', '"uniqueness"'))
    _origin(code, tmp_path / "code.git")
    _write(code, "src/b.py", "def b() -> int:\n    return 99\n")
    _commit(code, "edit recorded debt")
    _write(
        docs,
        "docs/components/bee.md",
        '---\nid: bee\ntitle: "Bee"\nstatus: stable\ndescribes:\n  - "nothing.py"\n'
        'owns_tests:\n  - "b.py"\n---\n\n# Bee\n\nIt returns one.\n',
    )
    _commit(docs, "declare an ordinary source file as an owned test")

    codes = _codes(docs, "--diff", "HEAD", "--source-diff", "origin/main")

    assert "diff-integrity/adoption-debt-touched b.py" in codes


def test_replacing_a_root_cannot_move_the_boundary(workspace: tuple[Path, Path]) -> None:
    """The reported shape: `--pin-adoption-sources` keeps the old pin, because dropping one
    is reported, and adds the new one. The existing entries then resolve to the new root and
    are judged against a different repository's revision — a boundary move that comparing
    only shared and removed roots could not see.
    """
    docs, code = workspace
    _run(docs, "check", "--init-adoption")
    base = _commit(docs, "adopt")
    other = code.parent / "newcode"
    (other / "src").mkdir(parents=True)
    for name in ("a", "b", "c"):
        _write(other, f"src/{name}.py", f"def {name}() -> int:\n    return 2\n")
    _git(other, "init", "-q", "-b", "main")
    _commit(other, "a different repository entirely")
    _write(docs, "irminsul.toml", _CONFIG.replace("../code/src", "../newcode/src"))
    _run(docs, "check", "--pin-adoption-sources")
    _commit(docs, "point the root at another repository")

    codes = _codes(docs, "--diff", base)

    assert "diff-integrity/adoption-source-rebound .irminsul-adoption.json" in codes


# ------------------------------------------ the boundary has to be on the declared history


def test_a_side_branch_commit_cannot_become_the_boundary(workspace: tuple[Path, Path]) -> None:
    """The attack the declared ref exists to stop, refused where it is cheapest to refuse.

    Pushing a branch needs no review, so an author can put a file anywhere in the source
    repository and have a real commit id for it. Pinning that commit would record the file as
    debt the declared history already had, and every later run would agree — the commit
    resolves, the file is in it, nothing is inconsistent. The only thing wrong with it is that
    `main` never had the file, which is a question about *which* history counts.

    `--init-adoption` pins the merge base of the source checkout and the declared ref, so a
    checkout sitting on a side branch pins its branch point and the files added on that branch
    are simply new. Nothing has to be reviewed for this to hold.
    """
    docs, code = workspace
    mainline = _git(code, "rev-parse", "HEAD")
    _git(code, "checkout", "-q", "-b", "side")
    _write(code, "src/evil.py", "def evil() -> int:\n    return 0\n")
    side = _commit(code, "a file nobody reviewed, on a branch anybody can push")
    assert side != mainline

    exit_code, output = _run(docs, "check", "--init-adoption")

    assert exit_code == 2, output
    assert "not in the revision being pinned" in output
    assert "evil.py" in output
    assert not (docs / ".irminsul-adoption.json").exists()


def test_the_same_file_is_adoptable_once_it_is_on_the_declared_history(
    workspace: tuple[Path, Path],
) -> None:
    """The other side of it, and the cutoff stated: whatever the declared history holds when
    the record is written is the approved snapshot, and is eligible. Merging is the act that
    makes the difference, and merging is what the source repository reviews."""
    docs, code = workspace
    _git(code, "checkout", "-q", "-b", "side")
    _write(code, "src/feature.py", "def feature() -> int:\n    return 1\n")
    _commit(code, "a feature")
    _git(code, "checkout", "-q", "main")
    _git(code, "merge", "-q", "--no-ff", "-m", "merge the feature", "side")

    exit_code, output = _run(docs, "check", "--init-adoption")

    assert exit_code == 0, output
    record = load_record(docs / ".irminsul-adoption.json")
    assert "feature.py" in record.unowned
    assert record.revision_for("engine") == _git(code, "rev-parse", "HEAD")


def test_the_boundary_does_not_advance_when_the_source_branch_does(
    workspace: tuple[Path, Path],
) -> None:
    """Once established, the boundary is a fixed point. The source repository going on with
    its life is exactly the case the record is not allowed to absorb."""
    docs, code = workspace
    _run(docs, "check", "--init-adoption")
    boundary = load_record(docs / ".irminsul-adoption.json").revision_for("engine")
    _write(code, "src/later.py", "def later() -> int:\n    return 2\n")
    _commit(code, "the source repository moves on, on the declared history")

    codes = _codes(docs)

    assert load_record(docs / ".irminsul-adoption.json").revision_for("engine") == boundary
    # The new file is new: it is not in the record, and the record does not grow to take it.
    assert "uniqueness/undocumented-file later.py" in codes


def test_a_hand_pinned_side_branch_is_caught_by_the_gate(workspace: tuple[Path, Path]) -> None:
    """The write-time refusal above is not the only guard, because a record can be written by
    hand. The adopting change is judged on the same obligation."""
    docs, code = workspace
    base = _git(docs, "rev-parse", "HEAD")
    _git(code, "checkout", "-q", "-b", "side")
    _write(code, "src/evil.py", "def evil() -> int:\n    return 0\n")
    side = _commit(code, "on a branch")
    _write(
        docs,
        ".irminsul-adoption.json",
        json.dumps(
            {
                "version": 1,
                "unowned": [{"path": "evil.py", "source": "engine"}],
                "sources": [{"name": "engine", "revision": side}],
            }
        )
        + "\n",
    )
    _commit(docs, "adopt against a side branch by hand")

    codes = _codes(docs, "--diff", base)

    assert "diff-integrity/adoption-pin-not-on-ref .irminsul-adoption.json" in codes


def test_a_remote_tracking_ref_resolves(workspace: tuple[Path, Path]) -> None:
    """The spelling a real clone has, and the one the generated workflows produce. Resolution
    tries exactly one candidate, `refs/remotes/origin/main`, so a local branch of the same
    name cannot answer in its place."""
    docs, code = workspace
    _git(code, "update-ref", "refs/remotes/origin/main", _git(code, "rev-parse", "HEAD"))
    _write(docs, "irminsul.toml", _CONFIG.replace('ref = "refs/heads/main"', 'ref = "origin/main"'))

    exit_code, output = _run(docs, "check", "--init-adoption")

    assert exit_code == 0, output


def test_a_declared_ref_this_checkout_lacks_fails_closed(workspace: tuple[Path, Path]) -> None:
    """A ref that is not here is not a boundary, and the refusal says which ref. Falling back
    to `HEAD` would pin whatever the checkout happened to be."""
    docs, _ = workspace
    _write(
        docs,
        "irminsul.toml",
        _CONFIG.replace('ref = "refs/heads/main"', 'ref = "origin/release"'),
    )

    exit_code, output = _run(docs, "check", "--init-adoption")

    assert exit_code == 2
    assert "origin/release" in output
    assert not (docs / ".irminsul-adoption.json").exists()


def test_an_undeclared_cross_repository_root_cannot_be_adopted_from(
    workspace: tuple[Path, Path],
) -> None:
    """Reading a root needs no declaration; adopting from it does. Without one there is no
    name for the record to bind an entry to and no ref to check a boundary against."""
    docs, _ = workspace
    _write(
        docs,
        "irminsul.toml",
        'project_name = "ws"\n[paths]\ndocs_root = "docs"\nsource_roots = ["../code/src"]\n'
        '[checks]\nenabled = ["uniqueness", "test-ownership"]\n',
    )

    exit_code, output = _run(docs, "check", "--init-adoption")

    assert exit_code == 2
    assert "no `[[paths.sources]]` entry declares them" in output


# ----------------------------------------------- the record's binding is checked, not trusted


def test_an_entry_bound_to_an_undeclared_source_fails_closed(
    workspace: tuple[Path, Path],
) -> None:
    docs, _ = workspace
    _run(docs, "check", "--init-adoption")
    path = docs / ".irminsul-adoption.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unowned"] = [{"path": "a.py", "source": "ghost"}]
    path.write_text(json.dumps(payload, indent=2) + chr(10), encoding="utf-8")

    assert "adoption-record/source-unverifiable a.py" in _codes(docs)


def test_an_entry_bound_to_the_wrong_source_fails_closed(
    workspace: tuple[Path, Path], tmp_path: Path
) -> None:
    """Two independent statements about one entry — what the record says, and what the
    configured roots resolve — and disagreement is a refusal rather than a choice."""
    docs, _ = workspace
    other = tmp_path / "other"
    (other / "src").mkdir(parents=True)
    _write(other, "src/z.py", "def z() -> int:\n    return 1\n")
    _git(other, "init", "-q", "-b", "main")
    _commit(other, "another repository")
    _write(
        docs,
        "irminsul.toml",
        _CONFIG.replace(
            '[[paths.sources]]\nname = "engine"\npath = "../code"\nref = "refs/heads/main"\n',
            '[[paths.sources]]\nname = "engine"\npath = "../code"\nref = "refs/heads/main"\n'
            '[[paths.sources]]\nname = "other"\npath = "../other"\nref = "refs/heads/main"\n',
        ),
    )
    _run(docs, "check", "--init-adoption")
    path = docs / ".irminsul-adoption.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unowned"] = [{"path": "a.py", "source": "other"}]
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    codes = _codes(docs)

    assert "adoption-record/source-unverifiable a.py" in codes


def test_a_cross_repository_entry_written_as_a_plain_path_fails_closed(
    workspace: tuple[Path, Path],
) -> None:
    """A plain path means a file in this repository. An entry from elsewhere written that way
    is the pre-binding format, and the message points at the migration rather than guessing."""
    docs, _ = workspace
    _run(docs, "check", "--init-adoption")
    path = docs / ".irminsul-adoption.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unowned"] = ["a.py"]
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    assert "adoption-record/source-unverifiable a.py" in _codes(docs)


# ---------------------------------------------------- migrating a record written before this


def _legacy_record(docs: Path, code: Path, revision: str | None = None) -> None:
    """The shape a record had before entries and pins named their source."""
    (docs / ".irminsul-adoption.json").write_text(
        json.dumps(
            {
                "version": 1,
                "unowned": ["a.py", "b.py", "c.py"],
                "sources": [
                    {
                        "root": "../code/src",
                        "revision": revision or _git(code, "rev-parse", "HEAD"),
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_a_legacy_record_is_migrated_without_moving_anything(
    workspace: tuple[Path, Path],
) -> None:
    """Explicit, reviewable, and inert. The pin keeps its revision, the entries keep their
    paths, and what changes is that both now say which repository they mean instead of
    leaving it to be re-derived from configuration that can move."""
    docs, code = workspace
    boundary = _git(code, "rev-parse", "HEAD")
    _legacy_record(docs, code)

    exit_code, output = _run(docs, "check", "--pin-adoption-sources")

    assert exit_code == 0, output
    record = load_record(docs / ".irminsul-adoption.json")
    assert record.revision_for("engine") == boundary
    assert record.unowned == frozenset({"a.py", "b.py", "c.py"})
    assert record.bindings == {"a.py": "engine", "b.py": "engine", "c.py": "engine"}
    assert "migrated" in output
    # And the migrated record is a clean run, which is the point of migrating it.
    assert _codes(docs) == []


def test_migration_refuses_a_pin_no_declared_source_covers(
    workspace: tuple[Path, Path],
) -> None:
    """A clear failure rather than a guessed conversion. Choosing a source for an
    undeclared root would be inventing the boundary the pin is supposed to be."""
    docs, code = workspace
    _legacy_record(docs, code)
    path = docs / ".irminsul-adoption.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["sources"] = [{"root": "../elsewhere/src", "revision": "a" * 40}]
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    exit_code, output = _run(docs, "check", "--pin-adoption-sources")

    assert exit_code == 2
    assert "../elsewhere/src" in output
    assert "inventing the boundary" in output


def test_migration_refuses_two_roots_of_one_source_pinned_apart(
    tmp_path: Path,
) -> None:
    """One repository has one boundary. Picking between two revisions would move it for
    half the entries, which is precisely the drift keying by root allowed."""
    docs, code = _workspace_with_cross_repo_tests(tmp_path)
    head = _git(code, "rev-parse", "HEAD")
    (docs / ".irminsul-adoption.json").write_text(
        json.dumps(
            {
                "version": 1,
                "unowned": ["a.py", "test_a.py"],
                "sources": [
                    {"root": "../code/src", "revision": head},
                    {"root": "../code/tests", "revision": "b" * 40},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code, output = _run(docs, "check", "--pin-adoption-sources")

    assert exit_code == 2
    assert "one repository has one boundary" in output.lower()


# ------------------------------------------------- the boundary's own security assumptions


def test_migration_refuses_a_legacy_pin_off_the_declared_history(
    workspace: tuple[Path, Path],
) -> None:
    """Migration copies a revision across rather than choosing one, which is what makes it
    safe — and would make it the way round the anchoring rule if it copied without asking.

    A record written before refs existed was never checked against one, so a legacy pin can
    sit on a branch nobody reviewed. Anchoring is checked when a record is *written* and not
    again, because afterwards the pin cannot move; so if migration carried this pin forward
    the boundary would be permanently off the declared history, having been refused had it
    been written today.
    """
    docs, code = workspace
    _git(code, "checkout", "-q", "-b", "side")
    _write(code, "src/evil.py", "def evil() -> int:\n    return 0\n")
    side = _commit(code, "a commit on a branch anybody can push")
    _git(code, "checkout", "-q", "main")
    _legacy_record(docs, code, revision=side)

    exit_code, output = _run(docs, "check", "--pin-adoption-sources")

    assert exit_code == 2
    assert side[:12] in output
    assert "refs/heads/main" in output
    assert "--init-adoption" in output
    # And nothing was written: the record is still the legacy one, not a converted boundary.
    assert "sources" in json.loads((docs / ".irminsul-adoption.json").read_text())
    assert json.loads((docs / ".irminsul-adoption.json").read_text())["sources"][0]["root"]


def test_changing_a_sources_ref_is_reported_by_the_gate(workspace: tuple[Path, Path]) -> None:
    """Anchoring is checked when the record is written and not afterwards, so the ref a
    future adoption is measured against has to be a change somebody sees. Nothing compared
    `paths.sources` before this."""
    docs, code = workspace
    _git(code, "update-ref", "refs/remotes/origin/main", _git(code, "rev-parse", "HEAD"))
    _run(docs, "check", "--init-adoption")
    base = _commit(docs, "adopt")
    _write(docs, "irminsul.toml", _CONFIG.replace('ref = "refs/heads/main"', 'ref = "origin/main"'))
    _commit(docs, "quietly change which history counts")

    codes = _codes(docs, "--diff", base)

    assert "diff-integrity/setting-weakened irminsul.toml" in codes


def test_changing_a_sources_path_is_reported_by_the_gate(
    workspace: tuple[Path, Path], tmp_path: Path
) -> None:
    """The adoption docs promise the gate reports this. It did not."""
    docs, _ = workspace
    other = tmp_path / "other"
    (other / "src").mkdir(parents=True)
    _write(other, "src/a.py", "def a() -> int:\n    return 1\n")
    _git(other, "init", "-q", "-b", "main")
    _commit(other, "another repository")
    _run(docs, "check", "--init-adoption")
    base = _commit(docs, "adopt")
    _write(
        docs,
        "irminsul.toml",
        _CONFIG.replace('path = "../code"', 'path = "../other"').replace(
            'source_roots = ["../code/src"]', 'source_roots = ["../other/src"]'
        ),
    )
    _commit(docs, "point the declared source at another repository")

    codes = _codes(docs, "--diff", base)

    assert "diff-integrity/setting-weakened irminsul.toml" in codes


def test_removing_a_declared_source_is_reported_by_the_gate(
    workspace: tuple[Path, Path],
) -> None:
    """The strongest version: the entries keep their binding and it names nothing."""
    docs, _ = workspace
    _run(docs, "check", "--init-adoption")
    base = _commit(docs, "adopt")
    _write(
        docs,
        "irminsul.toml",
        _CONFIG.replace(
            '[[paths.sources]]\nname = "engine"\npath = "../code"\nref = "refs/heads/main"\n',
            "",
        ),
    )
    _commit(docs, "drop the declaration and keep the entries")

    codes = _codes(docs, "--diff", base)

    assert "diff-integrity/setting-weakened irminsul.toml" in codes


# -------------------------------------------- why the pinned revision cannot be read here


def test_a_shallow_source_clone_says_so_and_says_how(tmp_path: Path) -> None:
    """The overwhelmingly common cause, because `actions/checkout` clones to depth 1. One
    message used to carry this, a rewritten history, and a wrong repository, with one remedy
    that only fitted this one."""
    origin, docs = tmp_path / "origin", tmp_path / "docs"
    (origin / "src").mkdir(parents=True)
    _write(origin, "src/a.py", "def a() -> int:\n    return 1\n")
    _git(origin, "init", "-q", "-b", "main")
    first = _commit(origin, "first")
    _write(origin, "src/b.py", "def b() -> int:\n    return 2\n")
    _commit(origin, "second")
    docs.mkdir()
    _write(docs, "irminsul.toml", _CONFIG)
    _write(docs, "docs/decisions/INDEX.md", _INDEX)
    _git(docs, "init", "-q", "-b", "main")
    _commit(docs, "docs")
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", origin.resolve().as_uri(), str(tmp_path / "code")],
        check=True,
        capture_output=True,
    )
    assert (tmp_path / "code" / ".git" / "shallow").exists(), "the fixture is not shallow"
    _write(
        docs,
        ".irminsul-adoption.json",
        json.dumps(
            {
                "version": 1,
                "unowned": [{"path": "a.py", "source": "engine"}],
                "sources": [{"name": "engine", "revision": first}],
            }
        )
        + "\n",
    )

    output = _run(docs, "check")[1]

    assert "shallow and does not reach it" in output
    assert "fetch-depth: 0" in output
    assert "--unshallow" in output


def test_a_complete_clone_missing_the_pin_does_not_claim_the_history_is_gone(
    workspace: tuple[Path, Path],
) -> None:
    """The honest limit. A commit this clone does not have may still exist in that repository,
    and only that repository can say — so the message reports what it knows, names the fetch,
    and does not conclude."""
    docs, _ = workspace
    _run(docs, "check", "--init-adoption")
    _repin(docs, "0" * 40)

    output = _run(docs, "check")[1]

    assert "does not contain that commit" in output
    assert "only it can answer" in output
    assert "fetch origin" in output


# ------------------------------------------- what a second pair of eyes found on the boundary


def _two_repo_workspace(tmp_path: Path) -> Path:
    """A docs repo whose roots reach into *two* sibling repositories."""
    docs = tmp_path / "docs"
    for name in ("alpha", "beta"):
        repo = tmp_path / name
        (repo / "src").mkdir(parents=True)
        _write(repo, "src/shared.py", f"def {name}() -> int:\n    return 1\n")
        _git(repo, "init", "-q", "-b", "main")
        _commit(repo, f"the {name} repository")
    docs.mkdir()
    _write(docs, "docs/decisions/INDEX.md", _INDEX)
    _git(docs, "init", "-q", "-b", "main")
    _commit(docs, "docs")
    return docs


def test_a_declared_source_may_not_span_two_repositories(tmp_path: Path) -> None:
    """One pin is one history, so one source is one repository.

    `path = "."` — or any common ancestor — matches every root beneath it by prefix, and then
    a single pin stands for two histories. The second repository's entries would be read
    against the first repository's commit, so `src/shared.py`, which exists in both, would
    read as history the second one never had. Refused rather than resolved: choosing one of
    the two repositories is the guess that verifies an exception against the wrong history.
    """
    docs = _two_repo_workspace(tmp_path)
    _write(
        docs,
        "irminsul.toml",
        'project_name = "ws"\n[paths]\ndocs_root = "docs"\n'
        'source_roots = ["../alpha/src", "../beta/src"]\n'
        '[[paths.sources]]\nname = "both"\npath = ".."\nref = "refs/heads/main"\n'
        '[checks]\nenabled = ["uniqueness"]\n',
    )

    exit_code, output = _run(docs, "check", "--init-adoption")

    assert exit_code == 2
    assert "more than one git repository" in output
    assert not (docs / ".irminsul-adoption.json").exists()


def test_a_record_bound_to_a_split_source_fails_closed(tmp_path: Path) -> None:
    """And a record that already names one is refused on every run, not only at adoption."""
    docs = _two_repo_workspace(tmp_path)
    _write(
        docs,
        "irminsul.toml",
        'project_name = "ws"\n[paths]\ndocs_root = "docs"\n'
        'source_roots = ["../alpha/src", "../beta/src"]\n'
        '[[paths.sources]]\nname = "both"\npath = ".."\nref = "refs/heads/main"\n'
        '[checks]\nenabled = ["uniqueness"]\n',
    )
    _write(
        docs,
        ".irminsul-adoption.json",
        json.dumps(
            {
                "version": 1,
                "unowned": [{"path": "shared.py", "source": "both"}],
                "sources": [{"name": "both", "revision": "a" * 40}],
            }
        )
        + "\n",
    )

    assert any("source-unverifiable" in code for code in _codes(docs))


def test_migration_anchors_a_pin_that_already_names_its_source(
    workspace: tuple[Path, Path],
) -> None:
    """A partially migrated record holds both spellings, and the named one was trusted.

    Seeding the revision from it unchecked meant the later `{root, revision}` entry found the
    revision already held and skipped the anchoring check too — so a side-branch commit could
    be rewritten into the valid schema. After that the gate never asks again: it is not a
    first record, and the pin string did not change.
    """
    docs, code = workspace
    _git(code, "checkout", "-q", "-b", "side")
    _write(code, "src/evil.py", "def evil() -> int:\n    return 0\n")
    side = _commit(code, "on a branch nobody reviewed")
    _git(code, "checkout", "-q", "main")
    _write(
        docs,
        ".irminsul-adoption.json",
        json.dumps(
            {
                "version": 1,
                "unowned": ["a.py"],
                "sources": [
                    {"name": "engine", "revision": side},
                    {"root": "../code/src", "revision": side},
                ],
            }
        )
        + "\n",
    )

    exit_code, output = _run(docs, "check", "--pin-adoption-sources")

    assert exit_code == 2
    assert side[:12] in output
    assert "not on" in output


def test_a_source_side_deletion_does_not_demand_a_record_the_pr_cannot_change(
    workspace: tuple[Path, Path],
) -> None:
    """The gate the code repository could never satisfy.

    Touching recorded debt is answered by retiring the entry in the same change, and a pull
    request in the *other* repository cannot: the record lives here. Requiring it would make
    deleting a recorded source file unmergeable once that workflow is required — a gate nobody
    can pass rather than a gate. The entry goes stale instead, which this design tolerates
    everywhere, and re-creating the path is still caught because the file then exists.
    """
    docs, code = workspace
    _run(docs, "check", "--init-adoption")
    base = _commit(docs, "adopt")
    source_base = _git(code, "rev-parse", "HEAD")
    (code / "src" / "b.py").unlink()
    _commit(code, "delete a recorded file in the code repository")

    codes = _codes(docs, "--diff", base, "--source-diff", source_base)

    assert not [code_ for code_ in codes if "adoption-debt-touched" in code_], codes


def test_a_source_side_edit_still_demands_a_document(workspace: tuple[Path, Path]) -> None:
    """The other side of it: editing recorded debt is a touch the docs repository can answer,
    and the exemption above is for deletions alone."""
    docs, code = workspace
    _run(docs, "check", "--init-adoption")
    base = _commit(docs, "adopt")
    source_base = _git(code, "rev-parse", "HEAD")
    _write(code, "src/b.py", "def b() -> int:\n    return 99\n")
    _commit(code, "edit a recorded file in the code repository")

    codes = _codes(docs, "--diff", base, "--source-diff", source_base)

    assert "diff-integrity/adoption-debt-touched b.py" in codes


def test_a_source_that_contributes_no_entry_is_not_pinned(
    workspace: tuple[Path, Path], tmp_path: Path
) -> None:
    """A pin grants nothing on its own, and every pin is preserved for ever — so recording one
    for a repository whose files are all documented coupled it to this record permanently,
    with no way to remove it, because dropping a pin is a weakening the seal reports."""
    docs, _ = workspace
    spare = tmp_path / "spare"
    (spare / "src").mkdir(parents=True)
    _write(spare, "src/z.py", "def z() -> int:\n    return 1\n")
    _git(spare, "init", "-q", "-b", "main")
    _commit(spare, "a repository with nothing undocumented")
    _write(
        docs,
        "irminsul.toml",
        _CONFIG.replace(
            'source_roots = ["../code/src"]', 'source_roots = ["../code/src", "../spare/src"]'
        ).replace(
            '[[paths.sources]]\nname = "engine"\npath = "../code"\nref = "refs/heads/main"\n',
            '[[paths.sources]]\nname = "engine"\npath = "../code"\nref = "refs/heads/main"\n'
            '[[paths.sources]]\nname = "spare"\npath = "../spare"\nref = "refs/heads/main"\n',
        ),
    )
    _write(docs, "docs/components/z.md", _component("z", "z.py"))

    exit_code, output = _run(docs, "check", "--init-adoption")

    assert exit_code == 0, output
    record = load_record(docs / ".irminsul-adoption.json")
    assert record.revision_for("engine") is not None
    assert record.revision_for("spare") is None


# ------------------------------------------ round two: what the second pass of eyes found


def test_gitignoring_recorded_debt_is_not_a_deletion(workspace: tuple[Path, Path]) -> None:
    """The exemption for source-side deletions, turned into a way through it.

    `honor_gitignore` is on by default, so a source pull request that adds a recorded file to
    `.gitignore` drops it out of the managed walk while leaving it on disk. Reading absence
    from the walk as deletion exempted the change from touch-to-own, let it edit recorded debt
    unchallenged, and handed the exception back the day the ignore rule came off. Deletion is
    a fact about the disk, so that is what is asked.
    """
    docs, code = workspace
    _run(docs, "check", "--init-adoption")
    base = _commit(docs, "adopt")
    source_base = _git(code, "rev-parse", "HEAD")
    _write(code, ".gitignore", "src/b.py\n")
    _write(code, "src/b.py", "def b() -> int:\n    return 99\n")
    _commit(code, "ignore a recorded file and edit it in one change")

    codes = _codes(docs, "--diff", base, "--source-diff", source_base)

    assert "diff-integrity/adoption-debt-touched b.py" in codes


def test_a_root_inside_this_repository_but_outside_the_walk_is_refused(tmp_path: Path) -> None:
    """A monorepo root that is neither local nor cross-repository, and verified by neither.

    Irminsul runs from a subdirectory and the root points at a sibling of that subdirectory:
    same git worktree, outside the tree walked from. No boundary is made, so its files read as
    locally verifiable — but the walk spells them relative to the root while git reports them
    under the worktree, so a first record could name a file the same change added with neither
    the historical-presence check nor touch-to-own matching it.
    """
    worktree = tmp_path / "mono"
    (worktree / "project" / "docs" / "decisions").mkdir(parents=True)
    (worktree / "code" / "src").mkdir(parents=True)
    _write(worktree, "code/src/a.py", "def a() -> int:\n    return 1\n")
    docs = worktree / "project"
    _write(docs, "docs/decisions/INDEX.md", _INDEX)
    _write(
        docs,
        "irminsul.toml",
        'project_name = "mono"\n[paths]\ndocs_root = "docs"\n'
        'source_roots = ["../code/src"]\n[checks]\nenabled = ["uniqueness"]\n',
    )
    _git(worktree, "init", "-q", "-b", "main")
    _commit(worktree, "one repository, two directories")

    exit_code, output = _run(docs, "check", "--init-adoption")

    assert exit_code == 2
    assert "outside the tree Irminsul walks from" in output
    assert not (docs / ".irminsul-adoption.json").exists()


def test_source_diff_can_name_the_repository_under_review(
    workspace: tuple[Path, Path], tmp_path: Path
) -> None:
    """One ref for every source made the gate unusable as soon as two of them spelled their
    default branch differently: a pull request in one supplies its ref, the other cannot
    resolve it, and the whole run exits 2. A named ref diffs the repository under review."""
    docs, code = workspace
    other = tmp_path / "other"
    (other / "src").mkdir(parents=True)
    _write(other, "src/z.py", "def z() -> int:\n    return 1\n")
    _git(other, "init", "-q", "-b", "trunk")
    _commit(other, "a second repository whose branch is spelled differently")
    _write(
        docs,
        "irminsul.toml",
        _CONFIG.replace(
            'source_roots = ["../code/src"]', 'source_roots = ["../code/src", "../other/src"]'
        ).replace(
            '[[paths.sources]]\nname = "engine"\npath = "../code"\nref = "refs/heads/main"\n',
            '[[paths.sources]]\nname = "engine"\npath = "../code"\nref = "refs/heads/main"\n'
            '[[paths.sources]]\nname = "other"\npath = "../other"\nref = "refs/heads/trunk"\n',
        ),
    )
    _write(docs, "docs/components/z.md", _component("z", "z.py"))
    _run(docs, "check", "--init-adoption")
    base = _commit(docs, "adopt")
    source_base = _git(code, "rev-parse", "HEAD")
    _write(code, "src/b.py", "def b() -> int:\n    return 99\n")
    _commit(code, "edit recorded debt in the repository under review")

    # The bare form asks every source for `refs/heads/main`, which `other` does not have.
    bare = runner.invoke(
        app, ["check", "--diff", base, "--source-diff", source_base, "--path", str(docs)]
    )
    assert bare.exit_code == 2
    assert "could not read a source change set" in bare.output

    # Named, it diffs the one repository the pull request is in.
    codes = _codes(docs, "--diff", base, "--source-diff", f"engine={source_base}")

    assert "diff-integrity/adoption-debt-touched b.py" in codes


def test_source_diff_refuses_a_source_it_cannot_place(workspace: tuple[Path, Path]) -> None:
    """A selector nobody matches is a gate reading an empty change set, which passes
    everything — so an undeclared name exits rather than being ignored, and the two spellings
    do not mix."""
    docs, code = workspace
    _run(docs, "check", "--init-adoption")
    base = _commit(docs, "adopt")
    head = _git(code, "rev-parse", "HEAD")

    unknown = runner.invoke(
        app, ["check", "--diff", base, "--source-diff", f"ghost={head}", "--path", str(docs)]
    )
    assert unknown.exit_code == 2
    assert "does not " in unknown.output and "declare" in unknown.output

    mixed = runner.invoke(
        app,
        [
            "check",
            "--diff",
            base,
            "--source-diff",
            head,
            "--source-diff",
            f"engine={head}",
            "--path",
            str(docs),
        ],
    )
    assert mixed.exit_code == 2
    assert "cannot mean both" in mixed.output
