"""The adoption record: pre-existing ownership debt, and the lifecycle of one exception.

Every test here answers one row of the adoption contract. The record is a finite list of
exact paths, it excepts one finding and no other, it only shrinks, and an exception that
has retired cannot come back.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from irminsul.adoption import AdoptionError, init_adoption, load_record, shrink_adoption
from irminsul.cli import app

runner = CliRunner()

_CONFIG = (
    'project_name = "abc"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n'
    '[checks]\nenabled = ["uniqueness", "test-ownership"]\n'
)
_INDEX = "---\nid: decisions\ntitle: D\nstatus: stable\n---\n\n# D\n"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _commit(root: Path, message: str) -> str:
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=T", "-c", "user.email=t@e.com", "commit", "-qm", message)
    return _git(root, "rev-parse", "HEAD")


def _component(slug: str, *describes: str) -> str:
    claims = "\n".join(f'  - "{d}"' for d in describes)
    return (
        f'---\nid: {slug}\ntitle: "{slug.title()}"\nstatus: stable\n'
        f"describes:\n{claims}\n---\n\n# {slug.title()}\n\nIt does arithmetic.\n"
    )


def _repo(tmp_path: Path, names: tuple[str, ...] = ("a", "b", "c")) -> Path:
    root = tmp_path / "abc"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _write(root, "irminsul.toml", _CONFIG)
    _write(root, "docs/decisions/INDEX.md", _INDEX)
    for name in names:
        _write(root, f"src/{name}.py", f"def {name}() -> int:\n    return 1\n")
    _commit(root, "the repository as it stands")
    return root


def _run(root: Path, *args: str) -> tuple[int, str]:
    result = runner.invoke(app, [*args, "--path", str(root)])
    return result.exit_code, result.output


def _codes(root: Path, *extra: str) -> list[str]:
    result = runner.invoke(app, ["check", "--format", "json", *extra, "--path", str(root)])
    return sorted(
        f"{f['code']} {f.get('path') or ''}" for f in json.loads(result.output)["findings"]
    )


def _debt(root: Path) -> list[str]:
    path = root / ".irminsul-adoption.json"
    return json.loads(path.read_text(encoding="utf-8"))["unowned"] if path.is_file() else []


def _adopt(root: Path) -> str:
    code, _ = _run(root, "check", "--init-adoption")
    assert code == 0
    return _commit(root, "adopt")


def _rewrite(root: Path, unowned: list[str]) -> None:
    """Rewrite the record's entry list by hand — what a stale tool or an author does, and the
    only way to reach the obligations `--init-adoption` satisfies by construction."""
    path = root / ".irminsul-adoption.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unowned"] = sorted(set(unowned))
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------- what a record records


def test_the_record_names_files_whose_findings_do_not_exist_yet(tmp_path: Path) -> None:
    """The reason a baseline cannot do this job.

    On the day of adoption no document claims anything, so no directory is covered and
    `undocumented-file` fires on nothing. A record built from the findings in hand would
    be empty and would except nothing; this one is built from the configured walk.
    """
    root = _repo(tmp_path)

    assert _codes(root) == []  # nothing to record
    _run(root, "check", "--init-adoption")

    assert _debt(root) == ["src/a.py", "src/b.py", "src/c.py"]


def test_adoption_leaves_the_tree_green_and_every_check_running(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _adopt(root)

    assert _run(root, "check")[0] == 0
    # Not a reduced mode: a second doc claiming the same file is still a duplicate.
    _write(root, "docs/components/one.md", _component("one", "src/a.py"))
    _write(root, "docs/components/two.md", _component("two", "src/a.py"))
    assert any("duplicate-claim" in code for code in _codes(root))


def test_a_second_init_is_refused(tmp_path: Path) -> None:
    """Re-running it after the first documents land would re-record whatever debt exists
    then, which is how a record grows back."""
    root = _repo(tmp_path)
    _adopt(root)

    code, output = _run(root, "check", "--init-adoption")

    assert code == 2 and "already exists" in output


def test_an_unreadable_record_is_reported_and_excepts_nothing(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _adopt(root)
    (root / ".irminsul-adoption.json").write_text("{ not json", encoding="utf-8")

    codes = _codes(root)

    assert any("adoption-record/unreadable" in code for code in codes)


# ------------------------------------------------------------ the lifecycle of an entry


def test_documenting_a_file_governs_it_immediately(tmp_path: Path) -> None:
    """No second activation step: the owner is live in the same run that adds it."""
    root = _repo(tmp_path)
    _adopt(root)
    _write(root, "docs/components/alpha.md", _component("alpha", "src/a.py"))

    code, output = _run(root, "context", "--before-edit", "src/a.py")

    assert code == 0 and "owner: alpha" in output
    assert _run(root, "check", "--update-adoption")[0] == 0
    assert _debt(root) == ["src/b.py", "src/c.py"]


def test_a_deleted_file_retires_its_entry(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _adopt(root)
    (root / "src/b.py").unlink()

    _run(root, "check", "--update-adoption")

    assert _debt(root) == ["src/a.py", "src/c.py"]


def test_a_renamed_file_is_a_new_file(tmp_path: Path) -> None:
    """The record names paths, so a moved file is one the record does not name. Chosen
    deliberately over following the rename: a policy that carried exceptions across moves
    would let a repository rename its way out of ever documenting anything."""
    root = _repo(tmp_path)
    _adopt(root)
    _git(root, "mv", "src/b.py", "src/renamed.py")

    assert "uniqueness/undocumented-file src/renamed.py" in _codes(root)
    # The stale entry still names the old path, and excepts nothing that exists. It
    # cannot be retired on its own: the update would have to add the new path to do it,
    # and the record only shrinks, so it refuses and says which file to document.
    code, output = _run(root, "check", "--update-adoption")
    assert code == 1 and "src/renamed.py" in output
    assert _debt(root) == ["src/a.py", "src/b.py", "src/c.py"]

    # Documenting the moved file settles both halves at once.
    _write(root, "docs/components/beta.md", _component("beta", "src/renamed.py"))
    assert _run(root, "check", "--update-adoption")[0] == 0
    assert _debt(root) == ["src/a.py", "src/c.py"]
    assert "uniqueness/undocumented-file src/renamed.py" not in _codes(root)


def test_documenting_a_moved_file_lets_its_old_entry_retire(tmp_path: Path) -> None:
    """The whole cleanup path after a move, because "the exception does not follow the file"
    is only tolerable if the record can then be tidied.

    Three states, and the middle one is the one worth knowing about. Before the moved file
    is documented the update refuses and names it — not to obstruct the cleanup, but because
    the new path is unowned debt the record does not hold, and adding it is the one thing a
    record may never do. After it is documented there is nothing to add, so the update
    proceeds and the stale entry goes with it. No decision record, no force flag, no
    special case: the ordinary command does it.

    The refusal is all-or-nothing across the record, which the middle assertion pins: two
    moves with one documented retires neither. Removals alone would be safe — a removal
    cannot weaken anything — so this is ergonomics rather than safety, and it is written
    down here so a change either way is deliberate.
    """
    root = _repo(tmp_path)
    _adopt(root)
    _git(root, "mv", "src/a.py", "src/moved_a.py")
    _git(root, "mv", "src/b.py", "src/moved_b.py")

    code, output = _run(root, "check", "--update-adoption")
    assert code == 1
    assert "src/moved_a.py" in output and "src/moved_b.py" in output
    assert _debt(root) == ["src/a.py", "src/b.py", "src/c.py"]

    _write(root, "docs/components/one.md", _component("one", "src/moved_a.py"))
    assert _run(root, "check", "--update-adoption")[0] == 1
    assert _debt(root) == ["src/a.py", "src/b.py", "src/c.py"]

    _write(root, "docs/components/two.md", _component("two", "src/moved_b.py"))

    assert _run(root, "check", "--update-adoption")[0] == 0
    assert _debt(root) == ["src/c.py"]


def test_a_moved_directory_needs_documents_for_the_files_whose_paths_changed(
    tmp_path: Path,
) -> None:
    """The scale at which the rule is tested, because the pressure is what makes it fail.

    One rename is easy to accept. A package move is where somebody reaches for deleting the
    record instead — which is the one move the seal refuses, so the answer has to be that
    every moved file needs a document and the unmoved ones are untouched.
    """
    root = _repo(tmp_path)
    _adopt(root)
    (root / "src" / "pkg").mkdir()
    _git(root, "mv", "src/a.py", "src/pkg/a.py")
    _git(root, "mv", "src/b.py", "src/pkg/b.py")

    codes = _codes(root)

    assert "uniqueness/undocumented-file src/pkg/a.py" in codes
    assert "uniqueness/undocumented-file src/pkg/b.py" in codes
    # The file that did not move is still untouched history.
    assert "uniqueness/undocumented-file src/c.py" not in codes


def test_a_copy_does_not_inherit_the_originals_exception(tmp_path: Path) -> None:
    """Rename detection is never asked, so a copy cannot be mistaken for a move — and the
    original keeps its exception, because nobody went back to it."""
    root = _repo(tmp_path)
    _adopt(root)
    (root / "src" / "copy.py").write_text(
        (root / "src" / "a.py").read_text(encoding="utf-8"), encoding="utf-8"
    )

    codes = _codes(root)

    assert "uniqueness/undocumented-file src/copy.py" in codes
    assert "uniqueness/undocumented-file src/a.py" not in codes


def test_deleting_an_adopted_file_asks_for_the_record_not_a_document(tmp_path: Path) -> None:
    """Deletion is one of the three ways an entry retires. There is no file left to describe,
    so the remedy is the record; asking for a document would ask for a doc about nothing."""
    root = _repo(tmp_path)
    base = _adopt(root)
    (root / "src" / "b.py").unlink()
    _commit(root, "delete an adopted file")

    code, errors = _gate(root, base)

    assert code == 1
    assert "diff-integrity/adoption-debt-touched src/b.py" in errors
    assert "--update-adoption" in _run(root, "check", "--diff", base)[1]


def test_an_owner_removed_later_is_a_new_violation(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _adopt(root)
    _write(root, "docs/components/alpha.md", _component("alpha", "src/a.py"))
    _run(root, "check", "--update-adoption")
    assert "src/a.py" not in _debt(root)

    _write(root, "docs/components/alpha.md", _component("alpha", "src/nothing.py"))

    assert "uniqueness/undocumented-file src/a.py" in _codes(root)
    # And the record cannot take it back: update only shrinks.
    code, output = _run(root, "check", "--update-adoption")
    assert code == 1 and "only shrinks" in output
    assert "src/a.py" not in _debt(root)


def test_a_new_file_inherits_no_exception(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _adopt(root)
    _write(root, "src/d.py", "def d() -> int:\n    return 1\n")

    assert "uniqueness/undocumented-file src/d.py" in _codes(root)


def test_a_new_directory_does_not_hide_its_files(tmp_path: Path) -> None:
    """The covered-directory guess let a whole undocumented sibling tree disappear. With
    a record in hand the question is answered from the record instead."""
    root = _repo(tmp_path)
    _adopt(root)
    _write(root, "src/newpkg/deep/mod.py", "def mod() -> int:\n    return 1\n")

    assert "uniqueness/undocumented-file src/newpkg/deep/mod.py" in _codes(root)


def test_without_a_record_the_progressive_rule_is_untouched(tmp_path: Path) -> None:
    """A repository that never adopted keeps exactly today's behaviour, so this does not
    turn existing trees red."""
    root = _repo(tmp_path)
    _write(root, "src/newpkg/mod.py", "def mod() -> int:\n    return 1\n")

    assert _codes(root) == []


# --------------------------------------------------------- the record is not an escape


def test_the_record_excepts_ownership_and_nothing_else(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _adopt(root)
    # A doc that claims a file it should not still collides with another doc's claim.
    _write(root, "docs/components/one.md", _component("one", "src/b.py"))
    _write(root, "docs/components/two.md", _component("two", "src/b.py"))

    assert any("duplicate-claim src/b.py" in code for code in _codes(root))


def test_a_recorded_test_still_answers_to_test_ownership(tmp_path: Path) -> None:
    """One list, both rules: `governed_as_test` decides which rule a path answers to, and
    recording a path never moves a file between them."""
    root = tmp_path / "abc"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _write(
        root,
        "irminsul.toml",
        _CONFIG.replace('source_roots = ["src"]', 'source_roots = ["src"]\ntest_roots = ["tests"]'),
    )
    _write(root, "docs/decisions/INDEX.md", _INDEX)
    _write(root, "src/a.py", "def a() -> int:\n    return 1\n")
    _write(root, "tests/test_a.py", "def test_a() -> None:\n    assert True\n")
    _commit(root, "base")
    _adopt(root)

    assert _debt(root) == ["src/a.py", "tests/test_a.py"]
    assert _run(root, "check")[0] == 0

    # A new test is not excepted, and it is reported by the test rule, not the source one.
    _write(root, "tests/test_b.py", "def test_b() -> None:\n    assert True\n")
    assert "test-ownership/unowned-test tests/test_b.py" in _codes(root)


def test_owns_tests_cannot_excuse_ordinary_source(tmp_path: Path) -> None:
    """The pre-existing invariant, re-asserted with a record in play."""
    root = _repo(tmp_path)
    _adopt(root)
    _write(
        root,
        "docs/components/alpha.md",
        '---\nid: alpha\ntitle: "Alpha"\nstatus: stable\ndescribes: []\n'
        'owns_tests:\n  - "src/a.py"\n---\n\n# Alpha\n\nIt does arithmetic.\n',
    )

    assert any("not-a-test" in code for code in _codes(root))


# ------------------------------------------------------------------- the module itself


def test_init_refuses_to_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "rec.json"
    init_adoption(path, ["src/a.py"], "abc123")

    with pytest.raises(AdoptionError, match="already exists"):
        init_adoption(path, ["src/a.py", "src/b.py"])


def test_shrink_refuses_to_add(tmp_path: Path) -> None:
    path = tmp_path / "rec.json"
    init_adoption(path, ["src/a.py"])

    result = shrink_adoption(path, {"src/a.py", "src/new.py"})

    assert result.added == ["src/new.py"]
    assert load_record(path).unowned == frozenset({"src/a.py"})  # unchanged on refusal


def test_shrink_retires_what_is_gone(tmp_path: Path) -> None:
    path = tmp_path / "rec.json"
    init_adoption(path, ["src/a.py", "src/b.py"])

    result = shrink_adoption(path, {"src/b.py"})

    assert (result.removed, result.kept) == (1, 1)
    assert load_record(path).unowned == frozenset({"src/b.py"})


def test_a_missing_record_is_not_an_error(tmp_path: Path) -> None:
    assert load_record(tmp_path / "absent.json").unowned == frozenset()


# ------------------------------------------------- the seal, through the diff gate


def _gate(root: Path, base: str) -> tuple[int, list[str]]:
    """What the generated `docs-pr.yml` runs."""
    result = runner.invoke(app, ["check", "--diff", base, "--format", "json", "--path", str(root)])
    return result.exit_code, sorted(
        f"{f['code']} {f.get('path') or ''}"
        for f in json.loads(result.output)["findings"]
        if f["severity"] == "error"
    )


def test_a_pull_request_cannot_record_the_debt_it_just_created(tmp_path: Path) -> None:
    """Refreshing the record is the obvious way to make a new unowned file acceptable."""
    root = _repo(tmp_path)
    base = _adopt(root)
    _write(root, "src/d.py", "def d() -> int:\n    return 1\n")
    record = root / ".irminsul-adoption.json"
    record.write_text(
        json.dumps({"version": 1, "unowned": [*_debt(root), "src/d.py"]}) + "\n", encoding="utf-8"
    )
    _commit(root, "excuse the new file by widening the record")

    code, errors = _gate(root, base)

    assert code == 1
    assert any("adoption-record-grew" in error for error in errors)


def test_the_adopting_change_may_write_the_record(tmp_path: Path) -> None:
    """The base holds no record, so there is no ratchet to widen — the same allowance a
    first baseline gets."""
    root = _repo(tmp_path)
    base = _git(root, "rev-parse", "HEAD")  # the tree before it adopted
    _run(root, "check", "--init-adoption")
    _commit(root, "adopt")

    assert _gate(root, base) == (0, [])


def test_editing_recorded_debt_requires_documenting_it(tmp_path: Path) -> None:
    """Touch-to-own, read from the diff's own `base...HEAD` set, so work already
    committed on the branch counts — not only what is still uncommitted."""
    root = _repo(tmp_path)
    base = _adopt(root)
    _write(root, "src/b.py", "def b() -> int:\n    return 2\n")
    _commit(root, "change b.py without documenting it")

    code, errors = _gate(root, base)

    assert code == 1
    assert "diff-integrity/adoption-debt-touched src/b.py" in errors


def test_editing_recorded_debt_and_documenting_it_passes(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    base = _adopt(root)
    _write(root, "src/b.py", "def b() -> int:\n    return 2\n")
    _write(root, "docs/components/beta.md", _component("beta", "src/b.py"))
    _run(root, "check", "--update-adoption")
    _commit(root, "change b.py and give it an owner")

    assert _gate(root, base) == (0, [])


def test_leaving_recorded_debt_alone_passes(tmp_path: Path) -> None:
    """The point of the exception: untouched history does not block a change elsewhere."""
    root = _repo(tmp_path)
    base = _adopt(root)
    _write(root, "docs/components/alpha.md", _component("alpha", "src/a.py"))
    _run(root, "check", "--update-adoption")
    _commit(root, "document a.py only")

    assert _gate(root, base) == (0, [])


def test_a_clean_run_still_names_the_debt_it_excepted(tmp_path: Path) -> None:
    """Zero errors is not proof that every file has documentation."""
    root = _repo(tmp_path)
    _adopt(root)

    code, output = _run(root, "check")
    assert code == 0 and "3 file(s) still have no owning doc" in output

    result = runner.invoke(app, ["check", "--format", "json", "--path", str(root)])
    adoption = json.loads(result.output)["adoption"]
    assert adoption["remaining"] == 3 and adoption["readable"] is True


# ------------------------------------------- an exception that retired cannot come back


def test_a_retired_exception_cannot_revive_when_nobody_refreshed_the_record(
    tmp_path: Path,
) -> None:
    """The lifecycle without the housekeeping step.

    `--update-adoption` is the polite way to retire an entry, and nothing makes anyone
    run it. So the merged history here is a file that was recorded as debt, then given a
    real owner, with the record left stale. A later change removes that owner. The file
    is unowned again and its path is still written in the record, and the exception must
    not be handed back on the strength of a list nobody refreshed.
    """
    root = _repo(tmp_path)
    _adopt(root)
    _write(root, "docs/components/beta.md", _component("beta", "src/b.py"))
    base = _commit(root, "document src/b.py, record left stale")
    assert "src/b.py" in _debt(root)

    (root / "docs/components/beta.md").unlink()
    _commit(root, "remove the owner of src/b.py")

    code, errors = _gate(root, base)

    assert code == 1
    assert any("src/b.py" in error for error in errors), errors


def test_a_recorded_test_cannot_revive_its_exception_either(tmp_path: Path) -> None:
    """Both ownership rules feed one record, so both have to lose an exception the same
    way. Here the owner is an `owns_tests:` entry rather than a `describes:` claim."""
    root = tmp_path / "abc"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _write(
        root,
        "irminsul.toml",
        _CONFIG.replace('source_roots = ["src"]', 'source_roots = ["src"]\ntest_roots = ["tests"]'),
    )
    _write(root, "docs/decisions/INDEX.md", _INDEX)
    _write(root, "src/a.py", "def a() -> int:\n    return 1\n")
    _write(root, "tests/test_a.py", "def test_a() -> None:\n    assert True\n")
    _commit(root, "base")
    _adopt(root)
    assert "tests/test_a.py" in _debt(root)

    owner = (
        '---\nid: alpha\ntitle: "Alpha"\nstatus: stable\ndescribes:\n  - "src/a.py"\n'
        'owns_tests:\n  - "tests/test_a.py"\n---\n\n# Alpha\n\nIt does arithmetic.\n'
    )
    _write(root, "docs/components/alpha.md", owner)
    base = _commit(root, "own the test, record left stale")

    (root / "docs/components/alpha.md").unlink()
    _commit(root, "remove the owner")

    code, errors = _gate(root, base)

    assert code == 1
    assert "diff-integrity/adoption-exception-revived tests/test_a.py" in errors


def test_an_exception_still_covers_a_file_no_merged_commit_ever_owned(tmp_path: Path) -> None:
    """The other side of the same rule, so it cannot be satisfied by blocking everything.

    Adding an owner and dropping it again inside one pull request leaves the file exactly
    as the base had it: recorded debt that no merged commit ever documented. The
    exception is live, and the change is about something else.
    """
    root = _repo(tmp_path)
    base = _adopt(root)
    _write(root, "docs/components/beta.md", _component("beta", "src/b.py"))
    _commit(root, "document src/b.py")
    (root / "docs/components/beta.md").unlink()
    _commit(root, "and remove it again")

    assert _gate(root, base) == (0, [])


# -------------------------------------- what the first record is allowed to call history


def test_the_adopting_change_cannot_record_a_file_it_just_added(tmp_path: Path) -> None:
    """The record says "already unowned on the day of adoption", so every path in a first
    record has to have been in the tree that day. A file this very change wrote was not.
    """
    root = _repo(tmp_path)
    base = _git(root, "rev-parse", "HEAD")  # the tree before it adopted
    _write(root, "src/d.py", "def d() -> int:\n    return 1\n")
    _run(root, "check", "--init-adoption")
    _commit(root, "add src/d.py and adopt in one change")
    assert "src/d.py" in _debt(root)

    code, errors = _gate(root, base)

    assert code == 1
    assert any("src/d.py" in error for error in errors), errors


def test_the_first_record_may_not_name_a_file_the_change_moved(tmp_path: Path) -> None:
    """A move is a touch, and the exception does not follow the file.

    This reverses an earlier allowance that let the adopting change record a moved file at
    its new path, on the reading that the debt existed at the boundary under another name.
    It does, and that is not the question. Adoption tolerates debt *nobody has gone back
    to*; moving a file is going back to it, and `test_a_renamed_file_is_a_new_file` already
    says so for every change after the first — a policy that carried exceptions across moves
    would let a repository rename its way out of ever documenting anything. Two rules for
    one principle is how the adopting path came to need patching three times, so there is
    now one: the record names what was already unowned, at the path it was unowned at.

    The remedy is cheap and the message says it: adopt, then move.
    """
    root = _repo(tmp_path)
    base = _git(root, "rev-parse", "HEAD")
    _git(root, "mv", "src/c.py", "src/renamed.py")
    _run(root, "check", "--init-adoption")
    _commit(root, "move c.py and adopt")
    assert "src/renamed.py" in _debt(root)  # `--init-adoption` writes what the walk returns

    code, errors = _gate(root, base)

    assert code == 1
    assert "diff-integrity/adoption-debt-not-historical src/renamed.py" in errors


def test_adopting_without_moving_anything_stays_green(tmp_path: Path) -> None:
    """The other side of the rule above: the ordinary adoption is still a clean run, so the
    reversal costs nothing to anyone who adopts before reorganising."""
    root = _repo(tmp_path)
    base = _git(root, "rev-parse", "HEAD")
    _run(root, "check", "--init-adoption")
    _commit(root, "adopt")

    assert _gate(root, base) == (0, [])


def test_adopting_cannot_delete_an_owner_and_record_what_it_owned(tmp_path: Path) -> None:
    """The laundering the adopting change was trusted not to do.

    `src/b.py` has an owning document at the base. The change deletes that document and
    writes a first record naming the file. Every other obligation is satisfied honestly —
    the file really did exist at the base — so historical presence passes it, and the
    revival rule is the only thing that can see it. It used to run after the adopting
    branch returned.
    """
    root = _repo(tmp_path)
    _write(root, "docs/components/beta.md", _component("beta", "src/b.py"))
    base = _commit(root, "document src/b.py before anyone adopts")

    (root / "docs" / "components" / "beta.md").unlink()
    _run(root, "check", "--init-adoption")
    _commit(root, "delete the owner and adopt in one change")
    assert "src/b.py" in _debt(root)

    code, errors = _gate(root, base)

    assert code == 1
    assert "diff-integrity/adoption-exception-revived src/b.py" in errors


def test_adopting_cannot_record_a_file_that_already_has_an_owner(tmp_path: Path) -> None:
    """A dormant exception. It buys nothing the day it is written and becomes live the day
    somebody removes the owner, which is the record keeping a claim about history that the
    tree has already answered."""
    root = _repo(tmp_path)
    base = _git(root, "rev-parse", "HEAD")
    _write(root, "docs/components/beta.md", _component("beta", "src/b.py"))
    _run(root, "check", "--init-adoption")
    _rewrite(root, [*_debt(root), "src/b.py"])
    _commit(root, "adopt, and name a documented file as debt")

    code, errors = _gate(root, base)

    assert code == 1
    assert "diff-integrity/adoption-debt-already-owned src/b.py" in errors


def test_a_later_change_may_still_hold_an_entry_that_has_since_been_documented(
    tmp_path: Path,
) -> None:
    """The reason the rule above is adopting-only. Nothing obliges anybody to run
    `--update-adoption`, so a record naming a file somebody has since documented is the
    ordinary state, and reporting it would make the stale record an error in every
    repository that has made progress."""
    root = _repo(tmp_path)
    base = _adopt(root)
    _write(root, "docs/components/beta.md", _component("beta", "src/b.py"))
    _commit(root, "document an adopted file, leave the record alone")
    assert "src/b.py" in _debt(root)

    assert _gate(root, base) == (0, [])


def test_adopting_cannot_record_a_path_no_root_produces(tmp_path: Path) -> None:
    """An entry naming nothing excepts nothing — until a root is widened and it starts
    excepting a file nobody adopted."""
    root = _repo(tmp_path)
    base = _git(root, "rev-parse", "HEAD")
    _run(root, "check", "--init-adoption")
    _rewrite(root, [*_debt(root), "elsewhere/ghost.py"])
    _commit(root, "adopt, and name a path outside every root")

    code, errors = _gate(root, base)

    assert code == 1
    assert any("adoption-debt-not-managed" in error for error in errors), errors


def test_a_record_that_still_holds_entries_cannot_be_deleted(tmp_path: Path) -> None:
    """Deleting a non-empty record hands back the coarse covered-directory guess it
    replaced, and leaves the next change free to adopt from scratch. Both are the
    exception surface widening, which is the one thing the seal exists to stop.
    """
    root = _repo(tmp_path)
    base = _adopt(root)
    (root / ".irminsul-adoption.json").unlink()
    _commit(root, "drop the record")

    code, errors = _gate(root, base)

    assert code == 1
    assert "diff-integrity/adoption-record-removed .irminsul-adoption.json" in errors


def test_an_empty_record_may_be_deleted(tmp_path: Path) -> None:
    """The record's own end state. Every entry retired, nothing left to except."""
    root = _repo(tmp_path)
    _adopt(root)
    for name in ("a", "b", "c"):
        _write(root, f"docs/components/{name}.md", _component(name, f"src/{name}.py"))
    _run(root, "check", "--update-adoption")
    assert _debt(root) == []
    base = _commit(root, "document everything")
    (root / ".irminsul-adoption.json").unlink()
    _commit(root, "drop the spent record")

    assert _gate(root, base) == (0, [])


def test_a_decision_record_may_retire_the_whole_record(tmp_path: Path) -> None:
    """Un-adopting is allowed, and it is the kind of choice that gets written down — the
    same excuse `check-disabled` takes for switching a check off."""
    root = _repo(tmp_path)
    base = _adopt(root)
    (root / ".irminsul-adoption.json").unlink()
    _write(
        root,
        "docs/decisions/0001-stop-recording-debt.md",
        "\n".join(
            [
                "---",
                "id: stop-recording-debt",
                "title: Stop recording debt",
                "status: stable",
                "---",
                "",
                "# Stop recording debt",
                "",
                "## Decision",
                "",
                "We drop `.irminsul-adoption.json` and go back to the covered-directory rule.",
                "",
            ]
        ),
    )
    _commit(root, "drop the record, with a reason")

    _, errors = _gate(root, base)
    assert "diff-integrity/adoption-record-removed .irminsul-adoption.json" not in errors
