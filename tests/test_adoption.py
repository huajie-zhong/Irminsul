"""The adoption record: pre-existing ownership debt, and the lifecycle of one exception.

Every test here answers one row of the adoption contract. The record is a finite list of
exact paths, it excepts one finding and no other, it only shrinks, and an exception that
has retired cannot come back.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from irminsul.adoption import AdoptionError, init_adoption, load_record, shrink_adoption
from irminsul.cli import app

from .conftest import (
    DECISIONS_INDEX,
    check_findings,
    commit_all,
    component_doc,
    config_toml,
    findings_of,
    git,
    git_init,
    invoke,
    reviewed,
    write,
)

runner = CliRunner()

_CONFIG = config_toml(
    project_name="abc", source_roots=["src"], enabled=["uniqueness", "test-ownership"]
)


def _repo(tmp_path: Path, names: tuple[str, ...] = ("a", "b", "c")) -> Path:
    root = tmp_path / "abc"
    root.mkdir()
    git_init(root, branch="main")
    write(root, "irminsul.toml", _CONFIG)
    write(root, "docs/decisions/INDEX.md", DECISIONS_INDEX)
    for name in names:
        write(root, f"src/{name}.py", f"def {name}() -> int:\n    return 1\n")
    commit_all(root, "the repository as it stands")
    return root


def _codes(root: Path, *extra: str) -> list[str]:
    return sorted(f"{f['code']} {f.get('path') or ''}" for f in check_findings(root, *extra))


def _debt(root: Path) -> list[str]:
    path = root / ".irminsul-adoption.json"
    return json.loads(path.read_text(encoding="utf-8"))["unowned"] if path.is_file() else []


def _adopt(root: Path) -> str:
    code, _ = invoke(root, "adoption", "init")
    assert code == 0
    return commit_all(root, "adopt")


def _rewrite(root: Path, unowned: list[str]) -> None:
    """Rewrite the record's entry list by hand — what a stale tool or an author does, and the
    only way to reach the obligations `irminsul adoption init` satisfies by construction."""
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
    invoke(root, "adoption", "init")

    assert _debt(root) == ["src/a.py", "src/b.py", "src/c.py"]


def test_adoption_leaves_the_tree_green_and_every_check_running(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _adopt(root)

    assert invoke(root, "check")[0] == 0
    # Not a reduced mode: a second doc claiming the same file is still a duplicate.
    write(root, "docs/components/one.md", component_doc("one", "src/a.py"))
    write(root, "docs/components/two.md", component_doc("two", "src/a.py"))
    assert any("duplicate-claim" in code for code in _codes(root))


def test_a_second_init_is_refused(tmp_path: Path) -> None:
    """Re-running it after the first documents land would re-record whatever debt exists
    then, which is how a record grows back."""
    root = _repo(tmp_path)
    _adopt(root)

    code, output = invoke(root, "adoption", "init")

    assert code == 1 and "already exists" in output


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
    write(root, "docs/components/alpha.md", component_doc("alpha", "src/a.py"))

    code, output = invoke(root, "context", "src/a.py")

    assert code == 0 and "owner: alpha" in output
    assert invoke(root, "adoption", "update")[0] == 0
    assert _debt(root) == ["src/b.py", "src/c.py"]


def test_a_deleted_file_retires_its_entry(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _adopt(root)
    (root / "src/b.py").unlink()

    invoke(root, "adoption", "update")

    assert _debt(root) == ["src/a.py", "src/c.py"]


def test_a_renamed_file_is_a_new_file(tmp_path: Path) -> None:
    """The record names paths, so a moved file is one the record does not name. Chosen
    deliberately over following the rename: a policy that carried exceptions across moves
    would let a repository rename its way out of ever documenting anything."""
    root = _repo(tmp_path)
    _adopt(root)
    git(root, "mv", "src/b.py", "src/renamed.py")

    assert "uniqueness/undocumented-file src/renamed.py" in _codes(root)
    # The stale entry still names the old path, and excepts nothing that exists. It
    # cannot be retired on its own: the update would have to add the new path to do it,
    # and the record only shrinks, so it refuses and says which file to document.
    code, output = invoke(root, "adoption", "update")
    assert code == 1 and "src/renamed.py" in output
    assert _debt(root) == ["src/a.py", "src/b.py", "src/c.py"]

    # Documenting the moved file settles both halves at once.
    write(root, "docs/components/beta.md", component_doc("beta", "src/renamed.py"))
    assert invoke(root, "adoption", "update")[0] == 0
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
    git(root, "mv", "src/a.py", "src/moved_a.py")
    git(root, "mv", "src/b.py", "src/moved_b.py")

    code, output = invoke(root, "adoption", "update")
    assert code == 1
    assert "src/moved_a.py" in output and "src/moved_b.py" in output
    assert _debt(root) == ["src/a.py", "src/b.py", "src/c.py"]

    write(root, "docs/components/one.md", component_doc("one", "src/moved_a.py"))
    assert invoke(root, "adoption", "update")[0] == 1
    assert _debt(root) == ["src/a.py", "src/b.py", "src/c.py"]

    write(root, "docs/components/two.md", component_doc("two", "src/moved_b.py"))

    assert invoke(root, "adoption", "update")[0] == 0
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
    git(root, "mv", "src/a.py", "src/pkg/a.py")
    git(root, "mv", "src/b.py", "src/pkg/b.py")

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
    commit_all(root, "delete an adopted file")

    code, errors = _gate(root, base)

    assert code == 1
    assert "diff-integrity/adoption-debt-touched src/b.py" in errors
    assert "irminsul adoption update" in invoke(root, "check", "--diff", base)[1]


def test_an_owner_removed_later_is_a_new_violation(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _adopt(root)
    write(root, "docs/components/alpha.md", component_doc("alpha", "src/a.py"))
    invoke(root, "adoption", "update")
    assert "src/a.py" not in _debt(root)

    write(root, "docs/components/alpha.md", component_doc("alpha", "src/nothing.py"))

    assert "uniqueness/undocumented-file src/a.py" in _codes(root)
    # And the record cannot take it back: update only shrinks.
    code, output = invoke(root, "adoption", "update")
    assert code == 1 and "only shrinks" in output
    assert "src/a.py" not in _debt(root)


def test_a_new_file_inherits_no_exception(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _adopt(root)
    write(root, "src/d.py", "def d() -> int:\n    return 1\n")

    assert "uniqueness/undocumented-file src/d.py" in _codes(root)


def test_a_new_directory_does_not_hide_its_files(tmp_path: Path) -> None:
    """The covered-directory guess let a whole undocumented sibling tree disappear. With
    a record in hand the question is answered from the record instead."""
    root = _repo(tmp_path)
    _adopt(root)
    write(root, "src/newpkg/deep/mod.py", "def mod() -> int:\n    return 1\n")

    assert "uniqueness/undocumented-file src/newpkg/deep/mod.py" in _codes(root)


def test_without_a_record_the_progressive_rule_is_untouched(tmp_path: Path) -> None:
    """A repository that never adopted keeps exactly today's behaviour, so this does not
    turn existing trees red."""
    root = _repo(tmp_path)
    write(root, "src/newpkg/mod.py", "def mod() -> int:\n    return 1\n")

    assert _codes(root) == []


# --------------------------------------------------------- the record is not an escape


def test_the_record_excepts_ownership_and_nothing_else(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _adopt(root)
    # A doc that claims a file it should not still collides with another doc's claim.
    write(root, "docs/components/one.md", component_doc("one", "src/b.py"))
    write(root, "docs/components/two.md", component_doc("two", "src/b.py"))

    assert any("duplicate-claim src/b.py" in code for code in _codes(root))


def test_a_recorded_test_still_answers_to_test_ownership(tmp_path: Path) -> None:
    """One list, both rules: `governed_as_test` decides which rule a path answers to, and
    recording a path never moves a file between them."""
    root = tmp_path / "abc"
    root.mkdir()
    git_init(root, branch="main")
    write(
        root,
        "irminsul.toml",
        _CONFIG.replace('source_roots = ["src"]', 'source_roots = ["src"]\ntest_roots = ["tests"]'),
    )
    write(root, "docs/decisions/INDEX.md", DECISIONS_INDEX)
    write(root, "src/a.py", "def a() -> int:\n    return 1\n")
    write(root, "tests/test_a.py", "def test_a() -> None:\n    assert True\n")
    commit_all(root, "base")
    _adopt(root)

    assert _debt(root) == ["src/a.py", "tests/test_a.py"]
    assert invoke(root, "check")[0] == 0

    # A new test is not excepted, and it is reported by the test rule, not the source one.
    write(root, "tests/test_b.py", "def test_b() -> None:\n    assert True\n")
    assert "test-ownership/unowned-test tests/test_b.py" in _codes(root)


def test_owns_tests_cannot_excuse_ordinary_source(tmp_path: Path) -> None:
    """The pre-existing invariant, re-asserted with a record in play."""
    root = _repo(tmp_path)
    _adopt(root)
    write(
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
    write(root, "src/d.py", "def d() -> int:\n    return 1\n")
    record = root / ".irminsul-adoption.json"
    record.write_text(
        json.dumps({"version": 1, "unowned": [*_debt(root), "src/d.py"]}) + "\n", encoding="utf-8"
    )
    commit_all(root, "excuse the new file by widening the record")

    code, errors = _gate(root, base)

    assert code == 1
    assert any("adoption-record-grew" in error for error in errors)


def test_the_adopting_change_may_write_the_record(tmp_path: Path) -> None:
    """The base holds no record, so there is no ratchet to widen — the same allowance a
    first baseline gets."""
    root = _repo(tmp_path)
    base = git(root, "rev-parse", "HEAD")  # the tree before it adopted
    invoke(root, "adoption", "init")
    commit_all(root, "adopt")

    assert _gate(root, base) == (0, [])


def test_editing_recorded_debt_requires_documenting_it(tmp_path: Path) -> None:
    """Touch-to-own, read from the diff's own `base...HEAD` set, so work already
    committed on the branch counts — not only what is still uncommitted."""
    root = _repo(tmp_path)
    base = _adopt(root)
    write(root, "src/b.py", "def b() -> int:\n    return 2\n")
    commit_all(root, "change b.py without documenting it")

    code, errors = _gate(root, base)

    assert code == 1
    assert "diff-integrity/adoption-debt-touched src/b.py" in errors


def test_editing_recorded_debt_and_documenting_it_passes(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    base = _adopt(root)
    write(root, "src/b.py", "def b() -> int:\n    return 2\n")
    write(root, "docs/components/beta.md", component_doc("beta", "src/b.py"))
    invoke(root, "adoption", "update")
    commit_all(root, "change b.py and give it an owner")

    assert _gate(root, base) == (0, [])


def test_leaving_recorded_debt_alone_passes(tmp_path: Path) -> None:
    """The point of the exception: untouched history does not block a change elsewhere."""
    root = _repo(tmp_path)
    base = _adopt(root)
    write(root, "docs/components/alpha.md", component_doc("alpha", "src/a.py"))
    invoke(root, "adoption", "update")
    commit_all(root, "document a.py only")

    assert _gate(root, base) == (0, [])


def test_a_clean_run_still_names_the_debt_it_excepted(tmp_path: Path) -> None:
    """Zero errors is not proof that every file has documentation."""
    root = _repo(tmp_path)
    _adopt(root)

    code, output = invoke(root, "check")
    assert code == 0 and "3 file(s) still have no owning doc" in output

    result = runner.invoke(app, ["check", "--format", "json", "--path", str(root)])
    adoption = json.loads(result.output)["adoption"]
    assert adoption["remaining"] == 3 and adoption["readable"] is True


def _adoption_json(root: Path) -> object:
    result = runner.invoke(app, ["check", "--format", "json", "--path", str(root)])
    return json.loads(result.output).get("adoption")


def test_the_note_and_the_json_say_the_same_things_about_a_stale_record(tmp_path: Path) -> None:
    """One assessment feeds both: the printed note and the `adoption` object count the files
    that still have no owner, not the entries in the file."""
    root = _repo(tmp_path)
    _adopt(root)
    write(root, "docs/components/alpha.md", component_doc("alpha", "src/a.py"))

    _, output = invoke(root, "check")
    adoption = _adoption_json(root)

    assert "2 file(s) still have no owning doc" in output
    assert "1 further entry names a file that is now owned or gone" in output
    assert isinstance(adoption, dict)
    assert (adoption["remaining"], adoption["entries"]) == (2, 3)
    assert adoption["unowned"] == ["src/b.py", "src/c.py"]

    write(root, "docs/components/beta.md", component_doc("beta", "src/b.py", "src/c.py"))
    _, output = invoke(root, "check")

    assert "every file .irminsul-adoption.json names now has an owner" in output
    assert "irminsul adoption update" in output
    adoption = _adoption_json(root)
    assert isinstance(adoption, dict) and adoption["remaining"] == 0


def test_an_unreadable_or_absent_record_has_no_note_and_says_why_in_the_json(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    assert _adoption_json(root) is None
    _adopt(root)
    (root / ".irminsul-adoption.json").write_text("{ not json", encoding="utf-8")

    _, output = invoke(root, "check")
    adoption = _adoption_json(root)

    assert "adoption:" not in output
    assert isinstance(adoption, dict)
    assert adoption["readable"] is False and "could not read" in str(adoption["error"])


def test_the_ownership_checks_take_the_excepted_paths_without_verifying_them_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`verified_debt` reads git for every cross-repository entry, and the excepted paths it
    returns are `record.unowned` whatever it finds, so only the pass that reports its
    problems asks it."""
    import irminsul.adoption as adoption

    root = _repo(tmp_path)
    _adopt(root)
    real = adoption.verified_debt
    calls: list[str] = []

    def counting(*args: object, **kwargs: object) -> object:
        calls.append("asked")
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(adoption, "verified_debt", counting)

    assert invoke(root, "check")[0] == 0
    assert calls == ["asked"]


def test_each_record_blob_is_parsed_once_per_diff_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The base record is a git blob, and the seal asked five readers for the same facts
    about it: the paths, the bindings, the pins and a source map each."""
    from collections import Counter

    root = _repo(tmp_path)
    base = _adopt(root)
    base_text = (root / ".irminsul-adoption.json").read_text(encoding="utf-8")
    write(root, "docs/components/alpha.md", component_doc("alpha", "src/a.py"))
    invoke(root, "adoption", "update")
    commit_all(root, "document a.py only")
    parsed: Counter[str] = Counter()
    real = json.loads

    def counting(text: str | bytes, *args: object, **kwargs: object) -> object:
        if isinstance(text, str) and '"unowned"' in text:
            parsed[text] += 1
        return real(text, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(json, "loads", counting)

    assert _gate(root, base) == (0, [])
    assert parsed[base_text] == 1


# ------------------------------------------- reading a record strictly and tolerantly


def test_a_tolerant_read_keeps_what_a_strict_one_refuses() -> None:
    """The record at the merge base is one this change did not write, so a pass that
    compares against it reads what it can instead of failing on what it cannot."""
    from irminsul.adoption import parse_record

    sha = "a" * 40
    text = json.dumps(
        {
            "version": 7,
            "unowned": ["src/a.py", 3, {"path": "../x/b.py", "source": "x"}, {"path": "c.py"}, ""],
            "sources": [
                {"name": "x", "revision": "HEAD"},
                {"name": "x", "revision": sha},
                {"name": "y"},
            ],
        }
    )

    record = parse_record(text, tolerant=True)

    assert record.unowned == frozenset({"src/a.py", "../x/b.py", "c.py"})
    assert dict(record.bindings) == {"../x/b.py": "x"}
    assert [(pin.source, pin.revision) for pin in record.sources] == [("x", sha)]
    with pytest.raises(AdoptionError, match="unsupported format"):
        parse_record(text)


def test_a_tolerant_read_of_text_that_is_not_a_record_is_empty() -> None:
    from irminsul.adoption import AdoptionRecord, parse_record

    for text in ("{ not json", "[]", "null", '{"unowned": "src/a.py"}'):
        assert parse_record(text, tolerant=True) == AdoptionRecord()
        with pytest.raises(AdoptionError):
            parse_record(text)


def test_both_reads_agree_on_a_record_that_is_well_formed() -> None:
    from irminsul.adoption import parse_record

    sha = "b" * 40
    text = json.dumps(
        {
            "version": 1,
            "adopted_at": "abc",
            "unowned": ["src/a.py", {"path": "../x/b.py", "source": "x"}],
            "sources": [{"name": "x", "revision": sha}],
        }
    )

    assert parse_record(text, tolerant=True) == parse_record(text)


def test_a_record_with_pins_and_no_entries_is_still_a_record() -> None:
    """`irminsul adoption update` keeps the pins when it retires the last entry, so a record can
    hold a boundary and nothing else. It was falsy then, and `record or AdoptionRecord()`
    handed back an empty one without the pins."""
    from irminsul.adoption import AdoptionRecord, parse_record

    sha = "c" * 40
    text = json.dumps({"version": 1, "unowned": [], "sources": [{"name": "x", "revision": sha}]})

    for record in (parse_record(text), parse_record(text, tolerant=True)):
        assert record.unowned == frozenset()
        assert (record or AdoptionRecord()).revision_for("x") == sha


# ------------------------------------------- an exception that retired cannot come back


def test_a_retired_exception_cannot_revive_when_nobody_refreshed_the_record(
    tmp_path: Path,
) -> None:
    """The lifecycle without the housekeeping step.

    `irminsul adoption update` is the polite way to retire an entry, and nothing makes anyone
    run it. So the merged history here is a file that was recorded as debt, then given a
    real owner, with the record left stale. A later change removes that owner. The file
    is unowned again and its path is still written in the record, and the exception must
    not be handed back on the strength of a list nobody refreshed.
    """
    root = _repo(tmp_path)
    _adopt(root)
    write(root, "docs/components/beta.md", component_doc("beta", "src/b.py"))
    base = commit_all(root, "document src/b.py, record left stale")
    assert "src/b.py" in _debt(root)

    (root / "docs/components/beta.md").unlink()
    commit_all(root, "remove the owner of src/b.py")

    code, errors = _gate(root, base)

    assert code == 1
    assert any("src/b.py" in error for error in errors), errors


def test_a_recorded_test_cannot_revive_its_exception_either(tmp_path: Path) -> None:
    """Both ownership rules feed one record, so both have to lose an exception the same
    way. Here the owner is an `owns_tests:` entry rather than a `describes:` claim."""
    root = tmp_path / "abc"
    root.mkdir()
    git_init(root, branch="main")
    write(
        root,
        "irminsul.toml",
        _CONFIG.replace('source_roots = ["src"]', 'source_roots = ["src"]\ntest_roots = ["tests"]'),
    )
    write(root, "docs/decisions/INDEX.md", DECISIONS_INDEX)
    write(root, "src/a.py", "def a() -> int:\n    return 1\n")
    write(root, "tests/test_a.py", "def test_a() -> None:\n    assert True\n")
    commit_all(root, "base")
    _adopt(root)
    assert "tests/test_a.py" in _debt(root)

    owner = (
        '---\nid: alpha\ntitle: "Alpha"\nstatus: stable\ndescribes:\n  - "src/a.py"\n'
        'owns_tests:\n  - "tests/test_a.py"\n---\n\n# Alpha\n\nIt does arithmetic.\n'
    )
    write(root, "docs/components/alpha.md", owner)
    base = commit_all(root, "own the test, record left stale")

    (root / "docs/components/alpha.md").unlink()
    commit_all(root, "remove the owner")

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
    write(root, "docs/components/beta.md", component_doc("beta", "src/b.py"))
    commit_all(root, "document src/b.py")
    (root / "docs/components/beta.md").unlink()
    commit_all(root, "and remove it again")

    assert _gate(root, base) == (0, [])


# -------------------------------------- what the first record is allowed to call history


def test_the_adopting_change_cannot_record_a_file_it_just_added(tmp_path: Path) -> None:
    """The record says "already unowned on the day of adoption", so every path in a first
    record has to have been in the tree that day. A file this very change wrote was not.
    """
    root = _repo(tmp_path)
    base = git(root, "rev-parse", "HEAD")  # the tree before it adopted
    write(root, "src/d.py", "def d() -> int:\n    return 1\n")
    invoke(root, "adoption", "init")
    commit_all(root, "add src/d.py and adopt in one change")
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
    base = git(root, "rev-parse", "HEAD")
    git(root, "mv", "src/c.py", "src/renamed.py")
    invoke(root, "adoption", "init")
    commit_all(root, "move c.py and adopt")
    assert "src/renamed.py" in _debt(root)  # `irminsul adoption init` writes what the walk returns

    code, errors = _gate(root, base)

    assert code == 1
    assert "diff-integrity/adoption-debt-not-historical src/renamed.py" in errors


def test_adopting_without_moving_anything_stays_green(tmp_path: Path) -> None:
    """The other side of the rule above: the ordinary adoption is still a clean run, so the
    reversal costs nothing to anyone who adopts before reorganising."""
    root = _repo(tmp_path)
    base = git(root, "rev-parse", "HEAD")
    invoke(root, "adoption", "init")
    commit_all(root, "adopt")

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
    write(root, "docs/components/beta.md", component_doc("beta", "src/b.py"))
    base = commit_all(root, "document src/b.py before anyone adopts")

    (root / "docs" / "components" / "beta.md").unlink()
    invoke(root, "adoption", "init")
    commit_all(root, "delete the owner and adopt in one change")
    assert "src/b.py" in _debt(root)

    code, errors = _gate(root, base)

    assert code == 1
    assert "diff-integrity/adoption-exception-revived src/b.py" in errors


def test_adopting_cannot_record_a_file_that_already_has_an_owner(tmp_path: Path) -> None:
    """A dormant exception. It buys nothing the day it is written and becomes live the day
    somebody removes the owner, which is the record keeping a claim about history that the
    tree has already answered."""
    root = _repo(tmp_path)
    base = git(root, "rev-parse", "HEAD")
    write(root, "docs/components/beta.md", component_doc("beta", "src/b.py"))
    invoke(root, "adoption", "init")
    _rewrite(root, [*_debt(root), "src/b.py"])
    commit_all(root, "adopt, and name a documented file as debt")

    code, errors = _gate(root, base)

    assert code == 1
    assert "diff-integrity/adoption-debt-already-owned src/b.py" in errors


def test_a_later_change_may_still_hold_an_entry_that_has_since_been_documented(
    tmp_path: Path,
) -> None:
    """The reason the rule above is adopting-only. Nothing obliges anybody to run
    `irminsul adoption update`, so a record naming a file somebody has since documented is the
    ordinary state, and reporting it would make the stale record an error in every
    repository that has made progress."""
    root = _repo(tmp_path)
    base = _adopt(root)
    write(root, "docs/components/beta.md", component_doc("beta", "src/b.py"))
    commit_all(root, "document an adopted file, leave the record alone")
    assert "src/b.py" in _debt(root)

    assert _gate(root, base) == (0, [])


def test_adopting_cannot_record_a_path_no_root_produces(tmp_path: Path) -> None:
    """An entry naming nothing excepts nothing — until a root is widened and it starts
    excepting a file nobody adopted."""
    root = _repo(tmp_path)
    base = git(root, "rev-parse", "HEAD")
    invoke(root, "adoption", "init")
    _rewrite(root, [*_debt(root), "elsewhere/ghost.py"])
    commit_all(root, "adopt, and name a path outside every root")

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
    commit_all(root, "drop the record")

    code, errors = _gate(root, base)

    assert code == 1
    assert "diff-integrity/adoption-record-removed .irminsul-adoption.json" in errors


def test_an_empty_record_may_be_deleted(tmp_path: Path) -> None:
    """The record's own end state. Every entry retired, nothing left to except."""
    root = _repo(tmp_path)
    _adopt(root)
    for name in ("a", "b", "c"):
        write(root, f"docs/components/{name}.md", component_doc(name, f"src/{name}.py"))
    invoke(root, "adoption", "update")
    assert _debt(root) == []
    base = commit_all(root, "document everything")
    (root / ".irminsul-adoption.json").unlink()
    commit_all(root, "drop the spent record")

    assert _gate(root, base) == (0, [])


def test_a_trailer_may_retire_the_whole_record(tmp_path: Path) -> None:
    """Un-adopting is allowed, and it is the kind of choice that gets written down — the
    same sign-off `check-disabled` takes for switching a check off."""
    root = _repo(tmp_path)
    base = _adopt(root)
    (root / ".irminsul-adoption.json").unlink()
    commit_all(
        root,
        "drop the record, with a reason\n\n"
        + reviewed(
            "diff-integrity/adoption-record-removed",
            ".irminsul-adoption.json",
            reason="we go back to the covered-directory rule",
        ),
    )

    _, errors = _gate(root, base)
    assert "diff-integrity/adoption-record-removed .irminsul-adoption.json" not in errors
    removed = findings_of(root, "diff-integrity/adoption-record-removed", "--diff", base)
    assert [f["severity"] for f in removed] == ["info"]


def test_a_trailer_naming_a_moved_record_lapses_when_the_old_file_is_deleted(
    tmp_path: Path,
) -> None:
    """The record moves to the path the config now names, and the trailer names that path.
    Deleting the old file later changes the path the removal is about, so the trailer lapses."""
    root = _repo(tmp_path)
    base = _adopt(root)
    write(root, "irminsul.toml", _CONFIG.replace("[paths]\n", '[paths]\nadoption = "moved.json"\n'))
    commit_all(
        root,
        "move the record's configured path\n\n"
        + reviewed(
            "diff-integrity/adoption-record-removed",
            "moved.json",
            reason="not deleted yet",
        ),
    )
    (root / ".irminsul-adoption.json").unlink()
    commit_all(root, "now delete the record")

    removed = findings_of(root, "diff-integrity/adoption-record-removed", "--diff", base)

    assert [f["severity"] for f in removed] == ["error"]
