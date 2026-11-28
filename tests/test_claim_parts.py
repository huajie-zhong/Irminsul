"""Claim evidence that names a part of a file: the scenarios of the RFC that lets it."""

from __future__ import annotations

import datetime as _dt
import re
import shlex
from pathlib import Path

import pytest

from irminsul.anchors import file_pin
from irminsul.checks.claim_provenance import ClaimProvenanceCheck
from irminsul.frontmatter import read_frontmatter

from .conftest import (
    commit_all,
    git_init,
    invoke,
    load_graph,
    replace_text,
    write,
    write_config,
    write_doc,
)

DOC = "docs/foundation/enforcement.md"
DRIFT = "claim-provenance/evidence-drift"
UNREADABLE = "claim-provenance/evidence-unreadable"
PIPELINE = """\
def apply_classes(findings):
    return [effective_class(finding) for finding in findings]


def effective_class(finding):
    return finding.declared


def failing_findings(findings):
    return [finding for finding in findings if finding.fails]
"""
CLI = """\
def check(path):
    return run(path)


def fix(path):
    return apply(path)


def _failing_classes(flags):
    return set(flags)
"""


def _at(day: int) -> _dt.datetime:
    return _dt.datetime(2025, 1, 1 + day, 12, tzinfo=_dt.UTC)


def _repo(tmp_path: Path, files: dict[str, str], evidence: list[str], *, pin: bool = True) -> Path:
    """A foundation doc whose one claim cites `evidence`, each entry pinned to what it names
    now when `pin`; the files are committed first and the doc a day later."""
    write_config(tmp_path, source_roots=["src", "lib"], enabled=["claim-provenance"])
    for rel, text in files.items():
        write(tmp_path, rel, text)
    git_init(tmp_path)
    commit_all(tmp_path, "files", when=_at(0))
    pins = {entry: _pin(tmp_path, entry) for entry in evidence} if pin else {}
    write_doc(
        tmp_path,
        DOC,
        doc_id="enforcement",
        body="Hints advise. <!-- claim:hints-advise -->",
        frontmatter_extra=[
            "claims:",
            "  - id: hints-advise",
            "    state: implemented",
            "    kind: invariant",
            "    claim: A hint never fails a run.",
            "    evidence:",
            *(f"      - {entry}" for entry in evidence),
            *(["    pinned:"] if any(pins.values()) else []),
            *(f"      {entry}: {value}" for entry, value in pins.items() if value),
        ],
    )
    commit_all(tmp_path, "doc", when=_at(1), paths=[DOC])
    return tmp_path


def _pin(root: Path, entry: str) -> str | None:
    path, _, part = entry.partition("#")
    return file_pin(root / path, part=part or None)


def _findings(root: Path) -> list[tuple[str, str]]:
    graph = load_graph(root, now=_dt.date(2025, 2, 1))
    return [(finding.code, finding.message) for finding in ClaimProvenanceCheck().run(graph)]


def _codes(root: Path) -> list[str]:
    return [code for code, _ in _findings(root)]


def _edit(root: Path, rel: str, old: str, new: str, day: int = 2) -> None:
    replace_text(root, rel, old, new)
    commit_all(root, f"edit {rel}", when=_at(day), paths=[rel])


def _pinned(root: Path) -> dict[str, str]:
    read = read_frontmatter((root / DOC).read_text(encoding="utf-8"))
    assert read is not None
    [claim] = read[0]["claims"]
    return dict(claim.get("pinned") or {})


CHECKS_DOC = """\
---
id: checks
title: Checks
status: stable
describes: []
---

# Checks

## The checks by what they govern

- parent-child validates folder indexes.

## Scope

Checks apply no fixes.
"""


def test_a_section_cited_as_evidence_is_asked_about_when_it_changes_and_not_otherwise(
    tmp_path: Path,
) -> None:
    section = "docs/components/checks.md#the-checks-by-what-they-govern"
    root = _repo(
        tmp_path,
        {"docs/components/checks.md": CHECKS_DOC, "src/pipeline.py": PIPELINE},
        ["src/pipeline.py", section],
    )
    pin = _pin(root, section)

    _edit(root, "docs/components/checks.md", "Checks apply no fixes.", "Checks never fix.")

    assert _pin(root, section) == pin
    assert _codes(root) == []

    _edit(root, "docs/components/checks.md", "validates folder", "reads folder", day=3)

    assert _pin(root, section) != pin
    assert _codes(root) == ["claim-provenance/evidence-drift"]


PYPROJECT = """\
[project]
name = "desk"
dependencies = ["typer", "pydantic"]

[tool.ruff]
line-length = 100
"""


def test_a_key_cited_as_evidence_follows_its_value_and_no_other_table(tmp_path: Path) -> None:
    key = "pyproject.toml#project.dependencies"
    root = _repo(
        tmp_path,
        {"pyproject.toml": PYPROJECT, "src/pipeline.py": PIPELINE},
        ["src/pipeline.py", key],
    )
    pin = _pin(root, key)

    _edit(root, "pyproject.toml", "line-length = 100", "line-length = 88")

    assert _pin(root, key) == pin
    assert _codes(root) == []

    _edit(root, "pyproject.toml", '"pydantic"]', '"pydantic", "rich"]', day=3)

    assert _pin(root, key) != pin
    assert _codes(root) == ["claim-provenance/evidence-drift"]


VAULT = """\
def seal(box):
    return lock(box)


# irminsul:part seal
KEYS = {}
LOCKS = {}
# irminsul:end seal
"""


def test_a_marker_wins_over_the_function_of_its_name_for_evidence_too(tmp_path: Path) -> None:
    """`src/vault.py#seal` is the two marked lines, though a function is named `seal`: an edit
    to the function leaves the claim, and an edit between the markers asks it again."""
    root = _repo(tmp_path, {"src/vault.py": VAULT}, ["src/vault.py#seal"])

    _edit(root, "src/vault.py", "return lock(box)", "return lock(box, hard=True)")

    assert _codes(root) == []

    _edit(root, "src/vault.py", "LOCKS = {}", "LOCKS = {1: 2}", day=3)

    assert _codes(root) == ["claim-provenance/evidence-drift"]


def test_a_part_of_a_file_no_finder_reads_is_unsupported_and_fails_the_run(
    tmp_path: Path,
) -> None:
    ruby = "class Session\n  def fetch_user_session(id)\n    lookup(id)\n  end\nend\n"
    root = _repo(
        tmp_path, {"lib/session.rb": ruby}, ["lib/session.rb#fetch_user_session"], pin=False
    )

    [(code, message)] = _findings(root)

    assert code == "claim-provenance/evidence-part-unsupported"
    assert "'fetch_user_session' cannot be found in 'lib/session.rb'" in message
    exit_code, plain = invoke(root, "check")
    assert exit_code == 1, plain


def test_a_renamed_function_is_a_missing_part_that_names_the_closest_and_asks_no_drift(
    tmp_path: Path,
) -> None:
    """The entry still says `effective_class` after the function became `finding_class`. That
    is certain, the new name is among the closest the file defines, and the entry is not
    also reported as drifted, though its file changed after the doc."""
    root = _repo(tmp_path, {"src/pipeline.py": PIPELINE}, ["src/pipeline.py#effective_class"])
    _edit(root, "src/pipeline.py", "def effective_class", "def finding_class")
    _edit(root, "src/pipeline.py", "[effective_class(", "[finding_class(", day=3)

    [(code, message)] = _findings(root)

    assert code == "claim-provenance/evidence-part-missing"
    assert "'effective_class' is not in 'src/pipeline.py'" in message
    assert "'finding_class'" in message.partition("(closest: ")[2]
    exit_code, plain = invoke(root, "check")
    assert exit_code == 1, plain


def test_a_slug_two_headings_share_is_a_missing_part_that_says_so(tmp_path: Path) -> None:
    notes = "# Notes\n\n## Limits\n\nfive\n\n## Limits\n\nsix\n"
    root = _repo(
        tmp_path,
        {"docs/guides/notes.md": notes, "src/pipeline.py": PIPELINE},
        ["src/pipeline.py", "docs/guides/notes.md#limits"],
        pin=False,
    )

    [(code, message)] = _findings(root)

    assert code == "claim-provenance/evidence-part-missing"
    assert "2 headings share the slug" in message


def test_a_change_to_another_part_of_the_file_does_not_ask_a_pinned_part_again(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path, {"src/cli.py": CLI}, ["src/cli.py#fix"])

    _edit(root, "src/cli.py", "return run(path)", "return run(path, strict=True)")

    assert _codes(root) == []

    _edit(root, "src/cli.py", "return apply(path)", "return apply(path, confirm=True)", day=3)

    assert _codes(root) == ["claim-provenance/evidence-drift"]


def test_a_part_with_no_pin_is_asked_about_as_its_whole_file_is(tmp_path: Path) -> None:
    """Narrowing gains nothing until the re-pin: without a pin the entry is judged by when
    its file was committed, so a change to another function asks."""
    root = _repo(tmp_path, {"src/cli.py": CLI}, ["src/cli.py#fix"], pin=False)

    _edit(root, "src/cli.py", "return run(path)", "return run(path, strict=True)")

    [(code, message)] = _findings(root)
    assert code == "claim-provenance/evidence-drift"
    assert message.endswith("changed after the doc: 'src/cli.py#fix'")


def test_a_doc_committed_after_its_evidence_answers_a_part_whose_pin_no_longer_matches(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path, {"src/cli.py": CLI}, ["src/cli.py#fix"])
    _edit(root, "src/cli.py", "return apply(path)", "return apply(path, confirm=True)")

    assert _codes(root) == ["claim-provenance/evidence-drift"]

    replace_text(root, DOC, "Hints advise.", "Hints advise, and a fix waits for a yes.")
    commit_all(root, "doc follows", when=_at(3), paths=[DOC])

    assert _codes(root) == []


def test_the_drift_suggestion_re_pins_the_part_it_names(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"src/cli.py": CLI}, ["src/cli.py#fix", "src/cli.py#check"])
    _edit(root, "src/cli.py", "return apply(path)", "return apply(path, confirm=True)")
    before = _pinned(root)

    code, plain = invoke(
        root, "anchors", "--re-pin", "--doc", DOC, "--claim", "hints-advise",
        "--evidence", "src/cli.py#fix",
    )  # fmt: skip

    assert code == 0, plain
    assert "claim hints-advise: src/cli.py#fix" in plain
    after = _pinned(root)
    assert after["src/cli.py#fix"] == _pin(root, "src/cli.py#fix") != before["src/cli.py#fix"]
    assert after["src/cli.py#check"] == before["src/cli.py#check"]
    assert _codes(root) == []


def test_the_drift_command_for_a_key_with_a_quoted_segment_runs_as_printed(
    tmp_path: Path,
) -> None:
    """The key `a.b` of the table `tool` is written `tool."a.b"`. A shell would take those
    quotes away, so the command the finding prints quotes the entry, and run through a
    shell's reading it names the entry and clears the drift."""
    key = 'src/conf.toml#tool."a.b"'
    conf = '[tool]\n"a.b" = 1\nother = 2\n'
    root = _repo(tmp_path, {"src/conf.toml": conf, "src/cli.py": CLI}, ["src/cli.py", key])
    _edit(root, "src/conf.toml", '"a.b" = 1', '"a.b" = 7')
    graph = load_graph(root, now=_dt.date(2025, 2, 1))

    [finding] = ClaimProvenanceCheck().run(graph)

    command = re.search(r"`irminsul ([^`]+)`", finding.suggestion or "")
    assert command is not None, finding.suggestion
    code, plain = invoke(root, *shlex.split(command.group(1)))
    assert code == 0, plain
    assert _pinned(root)[key] == _pin(root, key)


def test_an_entry_that_names_no_file_or_no_part_says_how_it_was_read(tmp_path: Path) -> None:
    """An entry is a path up to its first `#`. One whose path leads nowhere is missing as a
    path, and says which path was read; one that ends at its `#` names no part."""
    root = _repo(
        tmp_path, {"src/cli.py": CLI}, ["src/cli.py", "src/gone.py#fix", "src/cli.py#"], pin=False
    )

    found = dict(_findings(root))

    assert set(found) == {
        "claim-provenance/evidence-path-missing",
        "claim-provenance/evidence-part-missing",
    }
    assert "here 'src/gone.py'" in found["claim-provenance/evidence-path-missing"]
    assert "names no part" in found["claim-provenance/evidence-part-missing"]


def test_a_bare_path_selects_every_part_of_that_file_and_no_other(tmp_path: Path) -> None:
    evidence = [
        "src/pipeline.py#apply_classes",
        "src/pipeline.py#effective_class",
        "src/pipeline.py#failing_findings",
        "src/cli.py#_failing_classes",
    ]
    root = _repo(tmp_path, {"src/pipeline.py": PIPELINE, "src/cli.py": CLI}, evidence)
    before = _pinned(root)
    for old in ("finding) for finding", "finding.declared", "if finding.fails"):
        replace_text(root, "src/pipeline.py", old, old + " ")
    replace_text(root, "src/pipeline.py", "return finding.declared ", "return finding.given")
    replace_text(root, "src/pipeline.py", "if finding.fails ", "if finding.blocks")
    replace_text(root, "src/pipeline.py", "finding) for finding ", "finding, 1) for finding ")
    replace_text(root, "src/cli.py", "return set(flags)", "return frozenset(flags)")

    code, plain = invoke(
        root, "anchors", "--re-pin", "--doc", DOC, "--claim", "hints-advise",
        "--evidence", "src/pipeline.py",
    )  # fmt: skip

    assert code == 0, plain
    after = _pinned(root)
    assert [entry for entry in evidence if after[entry] != before[entry]] == evidence[:3]
    assert "3 claim evidence pin(s)" in plain


def test_a_re_pin_follows_a_renamed_part_and_drops_the_pin_of_the_old_spelling(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path, {"src/pipeline.py": PIPELINE}, ["src/pipeline.py#effective_class"])
    replace_text(root, "src/pipeline.py", "def effective_class", "def finding_class")
    replace_text(root, "src/pipeline.py", "[effective_class(", "[finding_class(")
    replace_text(
        root,
        DOC,
        "      - src/pipeline.py#effective_class",
        "      - src/pipeline.py#finding_class",
    )

    code, plain = invoke(root, "anchors", "--re-pin", "--doc", DOC)

    assert code == 0, plain
    assert _pinned(root) == {
        "src/pipeline.py#finding_class": _pin(root, "src/pipeline.py#finding_class")
    }
    assert "claim hints-advise: src/pipeline.py#effective_class (dropped)" in plain


def test_a_narrow_re_pin_also_drops_a_pin_on_a_spelling_the_claim_no_longer_cites(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path, {"src/cli.py": CLI}, ["src/cli.py#fix", "src/cli.py#check"])
    replace_text(root, DOC, "      - src/cli.py#check", "      - src/cli.py#_failing_classes")

    code, plain = invoke(
        root, "anchors", "--re-pin", "--doc", DOC, "--claim", "hints-advise",
        "--evidence", "src/cli.py#fix",
    )  # fmt: skip

    assert code == 0, plain
    assert set(_pinned(root)) == {"src/cli.py#fix"}


def test_a_part_of_a_file_that_does_not_parse_is_unreadable_and_keeps_its_pin(
    tmp_path: Path,
) -> None:
    """Python cannot read the file, so the part may be there or not. The entry is a hint
    that names the cause: no finding says the part is missing, none asks for a re-pin that
    could move nothing, the re-pin leaves the pin, and the hint goes when the file parses."""
    root = _repo(tmp_path, {"src/cli.py": CLI}, ["src/cli.py#fix"])
    before = _pinned(root)
    _edit(root, "src/cli.py", "def check(path):", "def check(path:")

    [(code, message)] = _findings(root)

    assert code == UNREADABLE
    assert "evidence 'src/cli.py#fix'" in message
    assert "its part 'fix' cannot be looked for" in message
    assert invoke(root, "check")[0] == 0
    assert invoke(root, "check", "--fail-on", "hint")[0] == 1
    exit_code, plain = invoke(root, "anchors", "--re-pin", "--doc", DOC)
    assert exit_code == 0, plain
    assert _pinned(root) == before

    _edit(root, "src/cli.py", "def check(path:", "def check(path):", day=3)

    assert _codes(root) == []


@pytest.mark.parametrize(("pin", "code"), [(True, UNREADABLE), (False, DRIFT)])
def test_a_whole_file_that_does_not_parse_is_unreadable_only_where_a_pin_needs_its_hash(
    tmp_path: Path, pin: bool, code: str
) -> None:
    """A pin is compared with the file's hash, which a file Python cannot read has none of;
    an entry with no pin is judged by its file's commit alone and needs no reading."""
    root = _repo(tmp_path, {"src/cli.py": CLI}, ["src/cli.py"], pin=pin)
    _edit(root, "src/cli.py", "def check(path):", "def check(path:")

    assert _codes(root) == [code]


def test_a_key_is_unreadable_while_its_file_writes_another_key_twice(tmp_path: Path) -> None:
    """Which of two values a key written twice holds is not said, so the file is not read
    and no key of it is looked for, the one the claim cites included."""
    conf = '{"a": {"x": 1}, "b": 2}\n'
    files = {"src/conf.json": conf, "src/cli.py": CLI}
    root = _repo(tmp_path, files, ["src/cli.py", "src/conf.json#a"])
    _edit(root, "src/conf.json", '"b": 2', '"b": 2, "b": 3')

    assert _codes(root) == [UNREADABLE]


def test_a_part_of_a_directory_is_unsupported(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"src/cli.py": CLI}, ["src/cli.py", "src#fix"], pin=False)

    [(code, message)] = _findings(root)

    assert code == "claim-provenance/evidence-part-unsupported"
    assert "it is not a file" in message


def test_a_stale_part_pin_is_listed_with_the_command_that_re_pins_it_alone(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path, {"src/cli.py": CLI}, ["src/cli.py#fix", "src/cli.py#check"])
    _edit(root, "src/cli.py", "return apply(path)", "return apply(path, confirm=True)")

    code, plain = invoke(root, "anchors", "--stale")

    assert code == 0, plain
    assert "claim hints-advise: src/cli.py#fix" in plain
    assert "src/cli.py#check" not in plain
    assert "--claim hints-advise --evidence 'src/cli.py#fix'" in plain
