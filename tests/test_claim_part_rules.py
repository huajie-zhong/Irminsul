"""Claim evidence that names a part of a file, one test per rule of its design."""

from __future__ import annotations

import datetime as _dt
import json
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import pytest

from irminsul.anchors import file_pin
from irminsul.checks.base import Finding
from irminsul.checks.claim_provenance import ClaimProvenanceCheck
from irminsul.frontmatter import read_frontmatter

from .conftest import (
    commit_all,
    git_init,
    invoke,
    invoke_json,
    load_graph,
    replace_text,
    write,
    write_config,
    write_doc,
)

DOC = "docs/foundation/enforcement.md"
DRIFT = "claim-provenance/evidence-drift"
PART_MISSING = "claim-provenance/evidence-part-missing"
PART_UNSUPPORTED = "claim-provenance/evidence-part-unsupported"
UNREADABLE = "claim-provenance/evidence-unreadable"
PATH_MISSING = "claim-provenance/evidence-path-missing"
NOT_REPO_RELATIVE = "claim-provenance/evidence-not-repo-relative"
STATE_MISMATCH = "claim-provenance/evidence-state-mismatch"

CLI = """\
def check(path):
    return run(path)


def fix(path):
    return apply(path)


def _failing_classes(flags):
    return set(flags)
"""
UTIL = """\
def helper(value):
    return value - 1


def other(value):
    return value + 1
"""
PIPELINE = "def apply_classes(findings):\n    return list(findings)\n"
BASE = "src/pipeline.py"
FIXED_PIN = "sha256:aaaaaaaaaaaa"


def _at(day: int) -> _dt.datetime:
    return _dt.datetime(2025, 1, 1 + day, 12, tzinfo=_dt.UTC)


@dataclass(frozen=True)
class _Claim:
    """One claim of the doc under test: `pin` names the entries pinned to what they name when
    the doc is written (or "all"), `pinned` adds pins that are written exactly as given."""

    id: str
    evidence: tuple[str, ...]
    state: str = "implemented"
    pin: tuple[str, ...] | Literal["all"] = ()
    pinned: dict[str, str] = field(default_factory=dict)


def _scalar(text: str) -> str:
    return json.dumps(text) if ":" in text else text


def _pin(root: Path, entry: str) -> str | None:
    path, _, part = entry.partition("#")
    return file_pin(root / path, part=part or None)


def _build(
    root: Path,
    files: dict[str, str],
    claims: list[_Claim],
    *,
    doc: str = DOC,
    status: str = "stable",
) -> Path:
    """The files committed on day 0 and the doc, whose claims cite them, on day 1."""
    write_config(root, source_roots=["src", "lib"], enabled=["claim-provenance"])
    for rel, text in files.items():
        write(root, rel, text)
    git_init(root)
    commit_all(root, "files", when=_at(0))
    lines = ["claims:"]
    body: list[str] = []
    for claim in claims:
        entries = claim.evidence if claim.pin == "all" else claim.pin
        pins = {entry: pin for entry in entries if (pin := _pin(root, entry)) is not None}
        pins.update(claim.pinned)
        lines += [
            f"  - id: {claim.id}",
            f"    state: {claim.state}",
            "    kind: invariant",
            "    claim: A hint never fails a run.",
            "    evidence:",
            *(f"      - {_scalar(entry)}" for entry in claim.evidence),
            *(["    pinned:"] if pins else []),
            *(f"      {entry}: {pin}" for entry, pin in pins.items()),
        ]
        body.append(f"Hints advise. <!-- claim:{claim.id} -->")
    write_doc(
        root,
        doc,
        doc_id=Path(doc).stem,
        body="\n\n".join(body),
        status=status,
        frontmatter_extra=lines,
    )
    commit_all(root, "doc", when=_at(1), paths=[doc])
    return root


def _run(root: Path) -> list[Finding]:
    return ClaimProvenanceCheck().run(load_graph(root, now=_dt.date(2025, 2, 1)))


def _codes(root: Path) -> list[str]:
    return [finding.code for finding in _run(root)]


def _edit(root: Path, rel: str, old: str, new: str, day: int = 2) -> None:
    replace_text(root, rel, old, new)
    commit_all(root, f"edit {rel}", when=_at(day), paths=[rel])


def _pinned(root: Path, claim_id: str = "a") -> dict[str, str]:
    read = read_frontmatter((root / DOC).read_text(encoding="utf-8"))
    assert read is not None
    [claim] = [claim for claim in read[0]["claims"] if claim["id"] == claim_id]
    return dict(claim.get("pinned") or {})


def _lone(root: Path, files: dict[str, str], entry: str) -> list[Finding]:
    """The findings of a claim that cites `entry` beside a source file that backs its state."""
    _build(root, {BASE: PIPELINE, **files}, [_Claim("a", (BASE, entry))])
    return _run(root)


def _suggested(finding: Finding) -> list[str]:
    """The arguments of the `irminsul ...` command a finding's suggestion offers, run through
    `invoke` as printed."""
    assert finding.suggestion is not None
    command = shlex.split(finding.suggestion.split("`")[1])
    assert command[:2] == ["irminsul", "anchors"]
    return command[1:]


def test_an_entry_splits_at_its_first_hash_and_the_rest_is_the_part(tmp_path: Path) -> None:
    """`src/seal.py#a#b` is the part `a#b` of `src/seal.py`, not the part `b` of a file named
    `src/seal.py#a`: it is found, pinned by its marked lines and asked about when they change."""
    source = "# irminsul:part a#b\nKEY = 1\n# irminsul:end a#b\nOTHER = 2\n"
    entry = "src/seal.py#a#b"
    root = _build(tmp_path, {"src/seal.py": source}, [_Claim("a", (entry,), pin=(entry,))])

    assert _codes(root) == []
    assert _pinned(root) == {entry: file_pin(root / "src/seal.py", part="a#b")}

    _edit(root, "src/seal.py", "OTHER = 2", "OTHER = 3")
    assert _codes(root) == []

    _edit(root, "src/seal.py", "KEY = 1", "KEY = 2", day=3)
    assert _codes(root) == [DRIFT]


def test_a_bare_path_is_the_whole_file_so_a_change_anywhere_in_it_asks(tmp_path: Path) -> None:
    """With no part the entry means the whole file, as it did before parts: its pin matches
    until any function of the file changes after the doc."""
    root = _build(tmp_path, {"src/cli.py": CLI}, [_Claim("a", ("src/cli.py",), pin="all")])
    assert _pinned(root) == {"src/cli.py": file_pin(root / "src/cli.py")}

    _edit(root, "src/cli.py", "return set(flags)", "return frozenset(flags)")

    [finding] = _run(root)
    assert finding.code == DRIFT
    assert "'src/cli.py'" in finding.message


@pytest.mark.parametrize(
    ("entry", "code"),
    [
        ("src/gone.py#fix", PATH_MISSING),
        ("src/gone.py", PATH_MISSING),
        ("../outside.py#x", NOT_REPO_RELATIVE),
        ("ABSOLUTE#fix", NOT_REPO_RELATIVE),
    ],
)
def test_where_an_entry_leads_is_read_from_its_path_with_the_part_stripped(
    tmp_path: Path, entry: str, code: str
) -> None:
    """A missing path, an absolute one and one that escapes with `..` are reported for the
    path alone, as they are with no part, and the part is not also reported."""
    root = tmp_path / "repo"
    write(tmp_path, "outside.py", CLI)
    if entry.startswith("ABSOLUTE"):
        entry = (root / "src" / "cli.py").as_posix() + "#fix"

    assert [finding.code for finding in _lone(root, {"src/cli.py": CLI}, entry)] == [code]


_RFC = "---\nid: x\ntitle: X\nstatus: draft\ndescribes: []\n---\n\n# X\n\n## Summary\n\nPlanned.\n"
_GUIDE = "---\nid: g\ntitle: G\nstatus: stable\ndescribes: []\n---\n\n# G\n\n## Intro\n\nUse it.\n"
_STATE_FILES = {
    "src/cli.py": CLI,
    "docs/rfcs/x.md": _RFC,
    "docs/components/checks.md": (
        "---\nid: checks\ntitle: Checks\nstatus: stable\ndescribes: []\n---\n\n"
        "# Checks\n\n## Scope\n\nChecks apply no fixes.\n"
    ),
    "docs/guides/g.md": _GUIDE,
    ".github/workflows/ci.yml": "name: ci\njobs:\n  test:\n    runs-on: ubuntu-latest\n",
    "action.yml": "name: irminsul\n",
}


@pytest.mark.parametrize(
    ("state", "evidence", "codes"),
    [
        ("planned", ("docs/rfcs/x.md#summary",), []),
        ("planned", ("src/cli.py#fix",), [STATE_MISMATCH]),
        ("planned", ("docs/guides/g.md#intro",), [STATE_MISMATCH]),
        ("implemented", ("src/cli.py#fix",), []),
        ("implemented", ("docs/components/checks.md#scope",), []),
        ("implemented", ("docs/guides/g.md#intro",), [STATE_MISMATCH]),
        ("implemented", ("docs/rfcs/x.md#summary",), [STATE_MISMATCH]),
        ("available", ("src/cli.py#fix", "docs/guides/g.md#intro"), []),
        ("available", ("src/cli.py#fix",), [STATE_MISMATCH]),
        ("available", ("docs/guides/g.md#intro",), [STATE_MISMATCH]),
        ("enabled", ("irminsul.toml#checks.enabled",), []),
        ("enabled", (".github/workflows/ci.yml#jobs.test",), []),
        ("enabled", ("action.yml#name",), []),
        ("enabled", ("src/cli.py#fix",), [STATE_MISMATCH]),
    ],
)
def test_the_state_a_claim_may_have_is_read_from_the_path_of_an_entry_with_a_part(
    tmp_path: Path, state: str, evidence: tuple[str, ...], codes: list[str]
) -> None:
    """Which state an entry can back depends on its path and not on its part: an RFC section
    backs `planned`, source `implemented`, source plus a doc `available`, the config or a
    workflow `enabled`."""
    root = _build(tmp_path, _STATE_FILES, [_Claim("a", evidence, state=state)])

    assert _codes(root) == codes


_LANG_FILES = {
    "lib/s.rb": "class S\n  def go\n    1\n  end\nend\n",
    "lib/run.sh": "echo go\n",
    "lib/note.txt": "go\n",
    "lib/style.css": "a { color: red }\n",
}


@pytest.mark.parametrize("rel", list(_LANG_FILES))
def test_a_part_of_a_file_no_finder_reads_is_unsupported_and_the_suggestion_names_the_markers(
    tmp_path: Path, rel: str
) -> None:
    """A Ruby, shell, text or CSS file has no finder, so `path#go` is unsupported, with no
    drift, and the suggestion names the two markers that would make it a part."""
    findings = _lone(tmp_path, {rel: _LANG_FILES[rel]}, f"{rel}#go")

    [finding] = findings
    assert finding.code == PART_UNSUPPORTED
    assert "'go'" in finding.message
    assert rel in finding.message
    assert finding.suggestion is not None
    assert "irminsul:part go" in finding.suggestion
    assert "irminsul:end go" in finding.suggestion


@pytest.mark.parametrize(
    ("rel", "opening", "closing"),
    [
        ("lib/s.rb", "# irminsul:part auth", "# irminsul:end auth"),
        ("lib/run.sh", "# irminsul:part auth", "# irminsul:end auth"),
        ("lib/style.css", "/* irminsul:part auth */", "/* irminsul:end auth */"),
        ("lib/note.txt", "irminsul:part auth", "irminsul:end auth"),
    ],
)
def test_a_marker_pair_makes_a_part_of_a_file_no_finder_reads(
    tmp_path: Path, rel: str, opening: str, closing: str
) -> None:
    """Where a pair of markers names a part, a file of any type has it: it resolves, its pin
    follows the lines between the markers, and a change outside them does not move it."""
    text = f"before one\n{opening}\ninside one\n{closing}\nafter one\n"
    entry = f"{rel}#auth"
    root = _build(tmp_path, {BASE: PIPELINE, rel: text}, [_Claim("a", (BASE, entry), pin=(entry,))])
    assert _codes(root) == []
    before = _pin(root, entry)
    assert before is not None

    _edit(root, rel, "after one", "after two")
    assert _pin(root, entry) == before
    assert _codes(root) == []

    _edit(root, rel, "inside one", "inside two", day=3)
    assert _pin(root, entry) != before
    assert _codes(root) == [DRIFT]


def test_a_marker_for_another_name_does_not_make_a_part_of_a_file_no_finder_reads(
    tmp_path: Path,
) -> None:
    """A file that holds the markers of `auth` still has no part `go`."""
    text = "# irminsul:part auth\nx\n# irminsul:end auth\n"

    [finding] = _lone(tmp_path, {"lib/s.rb": text}, "lib/s.rb#go")

    assert finding.code == PART_UNSUPPORTED


@pytest.mark.parametrize(
    ("rel", "text", "part", "closest"),
    [
        ("src/m.ts", "export function alpha() {}\nexport function beta() {}\n", "alfa", "alpha"),
        ("src/m.go", "package m\n\nfunc Alpha() {}\n\nfunc Beta() {}\n", "Alfa", "Alpha"),
        ("src/m.rs", "pub fn alpha() {}\n\npub fn beta() {}\n", "alfa", "alpha"),
        (
            "docs/guides/n.md",
            "# N\n\n## Limits\n\nfive\n\n## Scope\n\nsix\n",
            "the-limts",
            "limits",
        ),
        (
            "lib/p.toml",
            "[project]\nname = 'd'\ndependencies = []\n",
            "project.dependancies",
            "project.dependencies",
        ),
        ("lib/p.yaml", "jobs:\n  test:\n    a: 1\n  lint:\n    a: 2\n", "jobs.tset", "jobs.test"),
        (
            "lib/p.json",
            '{"scripts": {"build": "tsc", "test": "jest"}}',
            "scripts.biuld",
            "scripts.build",
        ),
    ],
)
def test_a_part_the_finder_does_not_know_is_missing_and_the_message_offers_the_closest(
    tmp_path: Path, rel: str, text: str, part: str, closest: str
) -> None:
    """A misspelt definition, slug or key path is a certain error that names the part and the
    path and offers the names the finder does know, the right one among them."""
    [finding] = _lone(tmp_path, {rel: text}, f"{rel}#{part}")

    assert finding.code == PART_MISSING
    assert finding.severity.value == "error"
    assert f"'{part}'" in finding.message
    assert rel in finding.message
    assert f"'{closest}'" in finding.message.partition("closest")[2]


def _head(message: str) -> str:
    return message.partition(" (closest")[0]


@pytest.mark.parametrize(
    ("rel", "ambiguous", "plain", "part"),
    [
        (
            "src/m.py",
            "# irminsul:part seal\nA = 1\n# irminsul:end seal\n"
            "# irminsul:part seal\nB = 2\n# irminsul:end seal\n",
            "A = 1\n",
            "seal",
        ),
        ("src/m.py", "# irminsul:part seal\nA = 1\n", "A = 1\n", "seal"),
        ("src/m.py", "# irminsul:end seal\nA = 1\n", "A = 1\n", "seal"),
        ("lib/p.yaml", "a: 1\n---\nb: 2\n", "b: 2\n", "a"),
        (
            "docs/guides/n.md",
            "# N\n\n## Limits\n\n1\n\n## Limits\n\n2\n",
            "# N\n\n## Scope\n\n1\n",
            "limits",
        ),
    ],
)
def test_an_ambiguous_part_is_missing_and_the_message_says_why(
    tmp_path: Path, rel: str, ambiguous: str, plain: str, part: str
) -> None:
    """A marker opened twice, opened and never closed, closed and never opened, a YAML file of
    several documents and two headings of one slug each resolve to nothing, and the finding
    says more than it does for a name that is merely absent."""
    [found] = _lone(tmp_path / "a", {rel: ambiguous}, f"{rel}#{part}")
    [absent] = _lone(tmp_path / "b", {rel: plain}, f"{rel}#{part}")

    assert found.code == absent.code == PART_MISSING
    assert len(_head(found.message)) > len(_head(absent.message))


@pytest.mark.parametrize(
    "files_part",
    [
        ("src/broken.py", "def fix(path:\n", "fix"),
        ("lib/broken.toml", "[project\nname = \n", "project.name"),
        ("lib/broken.json", '{"a": ', "a"),
        ("lib/broken.yaml", "key: [unclosed\n", "key"),
    ],
    ids=["python", "toml", "json", "yaml"],
)
def test_a_part_of_a_file_that_could_not_be_read_whole_is_unreadable_and_not_absent(
    tmp_path: Path, files_part: tuple[str, str, str]
) -> None:
    """The name may be in what did not parse, so no finding says it is missing or
    unsupported: one hint says the file could not be read, and names the entry."""
    rel, text, part = files_part

    [finding] = _lone(tmp_path, {rel: text}, f"{rel}#{part}")

    assert finding.code == UNREADABLE
    assert f"'{rel}#{part}'" in finding.message


@pytest.mark.parametrize(
    ("doc", "status"),
    [
        (DOC, "stable"),
        (DOC, "draft"),
        ("docs/components/enforcement.md", "stable"),
    ],
)
def test_evidence_that_could_not_be_read_is_reported_in_every_doc_and_asks_no_drift(
    tmp_path: Path, doc: str, status: str
) -> None:
    """Like a part that is not there, a part that cannot be looked for is reported
    wherever the claim is, and where drift is judged the entry raises none: the claim's
    other entry, whose file changed too, is the only one asked about."""
    claim = _Claim("a", ("src/cli.py#fix", "lib/util.py"), pin="all")
    root = _build(
        tmp_path, {"src/cli.py": CLI, "lib/util.py": UTIL}, [claim], doc=doc, status=status
    )
    _edit(root, "src/cli.py", "def check(path):", "def check(path:")
    _edit(root, "lib/util.py", "value + 1", "value + 2")
    judged = doc == DOC and status == "stable"

    findings = _run(root)

    assert sorted(f.code for f in findings) == sorted([UNREADABLE, *([DRIFT] if judged else [])])
    drift = [f.message for f in findings if f.code == DRIFT]
    assert all("lib/util.py" in message and "src/cli.py" not in message for message in drift)


@pytest.mark.parametrize(
    ("rel", "text", "outside", "inside"),
    [
        (
            "src/m.ts",
            "export const A = 1;\n// irminsul:part seal\nconst KEYS = {};\n"
            "// irminsul:end seal\nexport function seal() { return 1; }\n",
            ("return 1;", "return 2;"),
            ("const KEYS = {};", "const KEYS = {a: 1};"),
        ),
        (
            "docs/guides/n.md",
            "# N\n\n## Seal\n\nthe heading\n\n<!-- irminsul:part seal -->\nmarked words\n"
            "<!-- irminsul:end seal -->\n",
            ("the heading", "the title"),
            ("marked words", "marked words here"),
        ),
        (
            "lib/p.toml",
            "seal = 'section'\n# irminsul:part seal\nkeys = 'one'\n# irminsul:end seal\n",
            ("seal = 'section'", "seal = 'other'"),
            ("keys = 'one'", "keys = 'two'"),
        ),
    ],
    ids=["typescript", "markdown", "toml"],
)
def test_a_marker_pair_wins_over_a_definition_heading_or_key_of_its_name(
    tmp_path: Path,
    rel: str,
    text: str,
    outside: tuple[str, str],
    inside: tuple[str, str],
) -> None:
    """When a pair of markers and a definition, heading or key share a name, the part is the
    marked lines: a change in the other leaves the pin, and one between the markers moves it."""
    entry = f"{rel}#seal"
    root = _build(tmp_path, {BASE: PIPELINE, rel: text}, [_Claim("a", (BASE, entry), pin=(entry,))])
    before = _pin(root, entry)

    _edit(root, rel, *outside)
    assert _pin(root, entry) == before
    assert _codes(root) == []

    _edit(root, rel, *inside, day=3)
    assert _pin(root, entry) != before
    assert _codes(root) == [DRIFT]


@pytest.mark.parametrize(
    ("entry", "code", "old", "new"),
    [
        ("src/cli.py#gone", PART_MISSING, "return set(", "return list("),
        ("lib/s.rb#gone", PART_UNSUPPORTED, "x = 1", "x = 2"),
    ],
)
def test_an_entry_whose_part_is_not_there_is_reported_for_that_and_the_others_are_still_judged(
    tmp_path: Path, entry: str, code: str, old: str, new: str
) -> None:
    """The file of a missing or unsupported part changed after the doc, yet only the part is
    reported for it; the claim's other entry, a file that changed after the doc, drifts."""
    files = {"src/cli.py": CLI, "lib/s.rb": "x = 1\n", "lib/util.py": UTIL}
    root = _build(tmp_path, files, [_Claim("a", (entry, "lib/util.py"))])
    _edit(root, entry.partition("#")[0], old, new)
    _edit(root, "lib/util.py", "value + 1", "value + 2", day=3)

    findings = _run(root)

    assert sorted(finding.code for finding in findings) == sorted([code, DRIFT])
    [drift] = [finding for finding in findings if finding.code == DRIFT]
    assert "'lib/util.py'" in drift.message
    assert "gone" not in drift.message


@pytest.mark.parametrize(
    ("doc", "status", "codes"),
    [
        (DOC, "stable", [PART_MISSING, DRIFT]),
        (DOC, "draft", [PART_MISSING]),
        ("docs/components/enforcement.md", "stable", [PART_MISSING]),
    ],
)
def test_a_part_that_is_not_there_is_reported_in_every_doc_but_drift_is_judged_in_stable_ones(
    tmp_path: Path, doc: str, status: str, codes: list[str]
) -> None:
    """The certain code is judged in a draft and in a component doc; the drift hint only in
    a stable foundation or architecture doc."""
    claim = _Claim("a", ("src/cli.py#gone", "lib/util.py"))
    root = _build(
        tmp_path, {"src/cli.py": CLI, "lib/util.py": UTIL}, [claim], doc=doc, status=status
    )
    _edit(root, "lib/util.py", "value + 1", "value + 2")

    assert sorted(_codes(root)) == sorted(codes)


@dataclass(frozen=True)
class _Lang:
    rel: str
    source: str
    part: str
    comment: tuple[str, str]
    layout: tuple[str, str]
    code: tuple[str, str]
    other: tuple[str, str]


_LANGS = [
    _Lang(
        "src/mod.py",
        "def alpha(x):\n    return x + 1\n\n\ndef beta(x):\n    return x * 2\n",
        "alpha",
        ("return x + 1", "return x + 1  # one more"),
        ("return x + 1", "return x  +  1"),
        ("return x + 1", "return x + 2"),
        ("return x * 2", "return x * 3"),
    ),
    _Lang(
        "src/mod.ts",
        "export function alpha(x: number): number {\n  return x + 1;\n}\n\n"
        "export function beta(x: number): number {\n  return x * 2;\n}\n",
        "alpha",
        ("return x + 1;", "return x + 1; // one more"),
        ("return x + 1;", "return   x  +  1;"),
        ("return x + 1;", "return x + 2;"),
        ("return x * 2;", "return x * 3;"),
    ),
    _Lang(
        "src/mod.go",
        "package mod\n\nfunc Alpha(x int) int {\n\treturn x + 1\n}\n\n"
        "func Beta(x int) int {\n\treturn x * 2\n}\n",
        "Alpha",
        ("return x + 1", "return x + 1 // one more"),
        ("return x + 1", "return   x  +  1"),
        ("return x + 1", "return x + 2"),
        ("return x * 2", "return x * 3"),
    ),
    _Lang(
        "src/mod.rs",
        "pub fn alpha(x: i32) -> i32 {\n    x + 1\n}\n\npub fn beta(x: i32) -> i32 {\n    x * 2\n}\n",
        "alpha",
        ("    x + 1", "    x + 1 // one more"),
        ("    x + 1", "    x  +  1"),
        ("    x + 1", "    x + 2"),
        ("    x * 2", "    x * 3"),
    ),
]
_LANG_IDS = [lang.rel.rpartition(".")[2] for lang in _LANGS]


@pytest.mark.parametrize("lang", _LANGS, ids=_LANG_IDS)
@pytest.mark.parametrize("kind", ["comment", "layout", "other"])
def test_a_comment_a_layout_change_or_another_part_leaves_a_pinned_part_alone(
    tmp_path: Path, lang: _Lang, kind: str
) -> None:
    """In Python, TypeScript, Go and Rust a comment or a change of layout inside the pinned
    function, and any change to the file's other function, leave the pin and ask nothing."""
    entry = f"{lang.rel}#{lang.part}"
    root = _build(tmp_path, {lang.rel: lang.source}, [_Claim("a", (entry,), pin=(entry,))])
    before = _pin(root, entry)
    assert before is not None

    old, new = getattr(lang, kind)
    _edit(root, lang.rel, old, new)

    assert _pin(root, entry) == before
    assert _codes(root) == []


@pytest.mark.parametrize("lang", _LANGS, ids=_LANG_IDS)
def test_a_code_change_inside_a_pinned_part_moves_the_pin_and_asks(
    tmp_path: Path, lang: _Lang
) -> None:
    """A changed expression inside the pinned function moves its pin, and the claim is asked."""
    entry = f"{lang.rel}#{lang.part}"
    root = _build(tmp_path, {lang.rel: lang.source}, [_Claim("a", (entry,), pin=(entry,))])
    before = _pin(root, entry)

    _edit(root, lang.rel, *lang.code)

    assert _pin(root, entry) != before
    assert _codes(root) == [DRIFT]


_SETTINGS_YAML = (
    "name: desk\njobs:\n  test:\n    runs-on: ubuntu-test\n  lint:\n    runs-on: ubuntu-lint\n"
)
_SETTINGS_JSON = (
    '{\n  "name": "desk",\n  "scripts": {\n    "build": "tsc",\n    "test": "jest"\n  }\n}\n'
)


@pytest.mark.parametrize(
    ("rel", "text", "part", "unrelated", "own"),
    [
        (
            "lib/settings.yaml",
            _SETTINGS_YAML,
            "jobs.test",
            [("name: desk", "name: other"), ("ubuntu-lint", "macos-lint")],
            ("ubuntu-test", "macos-test"),
        ),
        (
            "lib/settings.json",
            _SETTINGS_JSON,
            "scripts.build",
            [('"desk"', '"other"'), ('"jest"', '"vitest"')],
            ('"tsc"', '"esbuild"'),
        ),
    ],
    ids=["yaml", "json"],
)
def test_a_pinned_key_is_asked_again_only_when_its_own_value_changes(
    tmp_path: Path,
    rel: str,
    text: str,
    part: str,
    unrelated: list[tuple[str, str]],
    own: tuple[str, str],
) -> None:
    """While a pinned key still has its pinned value no commit to the file asks the claim,
    whatever else it changed and however much later; its own value asks it."""
    entry = f"{rel}#{part}"
    root = _build(tmp_path, {BASE: PIPELINE, rel: text}, [_Claim("a", (BASE, entry), pin=(entry,))])
    before = _pin(root, entry)
    for day, (old, new) in enumerate(unrelated, start=2):
        _edit(root, rel, old, new, day=day)

    assert _pin(root, entry) == before
    assert _codes(root) == []

    _edit(root, rel, *own, day=5)

    assert _codes(root) == [DRIFT]


def test_an_entry_with_no_pin_is_judged_by_its_file_and_a_pinned_one_beside_it_is_not(
    tmp_path: Path,
) -> None:
    """Two parts of one file, one pinned and one not: a change to a third function after the
    doc asks about the unpinned entry only, and names it as the claim spells it."""
    entries = ("src/cli.py#fix", "src/cli.py#check")
    root = _build(tmp_path, {"src/cli.py": CLI}, [_Claim("a", entries, pin=("src/cli.py#fix",))])
    _edit(root, "src/cli.py", "return set(flags)", "return frozenset(flags)")

    [finding] = _run(root)

    assert finding.code == DRIFT
    assert "'src/cli.py#check'" in finding.message
    assert "src/cli.py#fix" not in finding.message


def test_the_drift_command_runs_as_printed_for_a_doc_with_a_space_and_a_claim_with_an_apostrophe(
    tmp_path: Path,
) -> None:
    """Every word of the command is quoted where it needs it, the doc's path and the
    claim's id as the entry is: read as a shell reads it, the command moves the pin."""
    doc = "docs/foundation/hints advise.md"
    root = _build(tmp_path, {BASE: PIPELINE}, [_Claim("it's", (BASE,), pin="all")], doc=doc)
    _edit(root, BASE, "list(findings)", "sorted(findings)")

    [finding] = [found for found in _run(root) if found.code == DRIFT]
    code, plain = invoke(root, *_suggested(finding))

    assert code == 0, plain
    read = read_frontmatter((root / doc).read_text(encoding="utf-8"))
    assert read is not None
    assert read[0]["claims"][0]["pinned"] == {BASE: _pin(root, BASE)}


def test_a_bare_entry_and_a_part_entry_of_one_file_have_two_pins_and_two_verdicts(
    tmp_path: Path,
) -> None:
    """`src/cli.py` and `src/cli.py#fix` are pinned apart: a change to another function moves
    the first pin and not the second, so only the bare entry is asked about."""
    entries = ("src/cli.py", "src/cli.py#fix")
    root = _build(tmp_path, {"src/cli.py": CLI}, [_Claim("a", entries, pin="all")])
    pinned = _pinned(root)
    assert pinned["src/cli.py"] != pinned["src/cli.py#fix"]
    assert pinned == {entry: _pin(root, entry) for entry in entries}

    _edit(root, "src/cli.py", "return run(path)", "return run(path, strict=True)")

    [finding] = _run(root)
    assert finding.code == DRIFT
    assert "'src/cli.py'" in finding.message
    assert "src/cli.py#fix" not in finding.message


def test_an_unpinned_entry_whose_file_was_committed_before_the_doc_asks_nothing(
    tmp_path: Path,
) -> None:
    """With no pin the commit times decide: the doc was committed after the file, so the part
    is not asked about."""
    root = _build(tmp_path, {"src/cli.py": CLI}, [_Claim("a", ("src/cli.py#fix",))])

    assert _codes(root) == []


def test_the_drift_finding_names_every_drifted_entry_and_its_command_re_pins_them(
    tmp_path: Path,
) -> None:
    """Each drifted entry is named as the claim spells it, part included, and the suggested
    command carries `--evidence` for each; running it as printed clears the finding."""
    entries = ("src/cli.py#fix", "lib/util.py", "src/cli.py#check")
    root = _build(tmp_path, {"src/cli.py": CLI, "lib/util.py": UTIL}, [_Claim("a", entries)])
    _edit(root, "src/cli.py", "return set(flags)", "return frozenset(flags)")
    _edit(root, "lib/util.py", "value + 1", "value + 2", day=3)

    [finding] = _run(root)

    assert finding.code == DRIFT
    for entry in entries:
        assert f"'{entry}'" in finding.message
    assert finding.suggestion is not None
    for entry in entries:
        assert f" --evidence {entry}" in finding.suggestion
    code, plain = invoke(root, *_suggested(finding))
    assert code == 0, plain
    assert _codes(root) == []


def test_two_claims_of_one_doc_cite_two_parts_and_only_the_one_that_changed_is_asked(
    tmp_path: Path,
) -> None:
    """Claim `a` cites `fix` and claim `b` cites `check`, each pinned: a change to `fix` asks
    `a` and not `b`."""
    claims = [
        _Claim("a", ("src/cli.py#fix",), pin="all"),
        _Claim("b", ("src/cli.py#check",), pin="all"),
    ]
    root = _build(tmp_path, {"src/cli.py": CLI}, claims)
    _edit(root, "src/cli.py", "return apply(path)", "return apply(path, confirm=True)")

    [finding] = _run(root)

    assert finding.code == DRIFT
    assert "claim 'a'" in finding.message
    assert "src/cli.py#fix" in finding.message


def test_a_re_pin_of_one_claim_leaves_another_claims_pin_of_the_same_part(
    tmp_path: Path,
) -> None:
    """Two claims cite `src/cli.py#fix`; re-pinning `a` moves a's pin alone, and `b` is still
    the one whose pin is stale."""
    claims = [
        _Claim("a", ("src/cli.py#fix",), pin="all"),
        _Claim("b", ("src/cli.py#fix",), pin="all"),
    ]
    root = _build(tmp_path, {"src/cli.py": CLI}, claims)
    old = _pinned(root, "b")
    _edit(root, "src/cli.py", "return apply(path)", "return apply(path, confirm=True)")

    code, plain = invoke(
        root, "anchors", "--re-pin", "--doc", DOC, "--claim", "a", "--evidence", "src/cli.py#fix"
    )

    assert code == 0, plain
    assert _pinned(root, "a") == {"src/cli.py#fix": _pin(root, "src/cli.py#fix")}
    assert _pinned(root, "b") == old
    assert [row["claim"] for row in invoke_json(root, "anchors", "--stale")["stale"]] == ["b"]


def test_a_re_pin_writes_one_pin_per_entry_keyed_by_its_spelling(tmp_path: Path) -> None:
    """A claim that cites a file whole and two of its parts, and a part of another file, gets
    four pins keyed as written, each the hash of what that entry names."""
    entries = ("src/cli.py", "src/cli.py#fix", "src/cli.py#check", "lib/util.py#helper")
    root = _build(tmp_path, {"src/cli.py": CLI, "lib/util.py": UTIL}, [_Claim("a", entries)])

    code, plain = invoke(root, "anchors", "--re-pin", "--doc", DOC)

    assert code == 0, plain
    pinned = _pinned(root)
    assert set(pinned) == set(entries)
    assert pinned["src/cli.py"] == file_pin(root / "src/cli.py")
    assert pinned["src/cli.py#fix"] == file_pin(root / "src/cli.py", part="fix")
    assert pinned["src/cli.py#check"] == file_pin(root / "src/cli.py", part="check")
    assert pinned["lib/util.py#helper"] == file_pin(root / "lib/util.py", part="helper")
    assert len(set(pinned.values())) == 4


def _stale_cli(root: Path) -> None:
    for old, new in [
        ("return run(path)", "return run(path, strict=True)"),
        ("return apply(path)", "return apply(path, confirm=True)"),
        ("return set(flags)", "return frozenset(flags)"),
    ]:
        replace_text(root, "src/cli.py", old, new)


def test_a_bare_path_selects_the_bare_entry_and_each_part_of_its_file_and_no_other_file(
    tmp_path: Path,
) -> None:
    """`--evidence src/cli.py` re-pins `src/cli.py` itself and both of its parts and leaves
    the part of `lib/util.py` as it was, though that one is stale too."""
    entries = ("src/cli.py", "src/cli.py#fix", "src/cli.py#check", "lib/util.py#helper")
    root = _build(
        tmp_path, {"src/cli.py": CLI, "lib/util.py": UTIL}, [_Claim("a", entries, pin="all")]
    )
    before = _pinned(root)
    _stale_cli(root)
    replace_text(root, "lib/util.py", "value - 1", "value - 2")

    code, plain = invoke(
        root, "anchors", "--re-pin", "--doc", DOC, "--claim", "a", "--evidence", "src/cli.py"
    )

    assert code == 0, plain
    after = _pinned(root)
    for entry in entries[:3]:
        assert after[entry] == _pin(root, entry) != before[entry]
    assert (
        after["lib/util.py#helper"]
        == before["lib/util.py#helper"]
        != _pin(root, "lib/util.py#helper")
    )


def test_an_entry_spelled_with_its_part_moves_that_pin_and_not_the_bare_entry_of_its_file(
    tmp_path: Path,
) -> None:
    """`--evidence src/cli.py#fix` is that spelling alone: the claim's bare `src/cli.py`, which
    is stale as well, keeps its pin."""
    entries = ("src/cli.py", "src/cli.py#fix")
    root = _build(tmp_path, {"src/cli.py": CLI}, [_Claim("a", entries, pin="all")])
    before = _pinned(root)
    _stale_cli(root)

    code, plain = invoke(
        root, "anchors", "--re-pin", "--doc", DOC, "--claim", "a", "--evidence", "src/cli.py#fix"
    )

    assert code == 0, plain
    after = _pinned(root)
    assert after["src/cli.py#fix"] == _pin(root, "src/cli.py#fix") != before["src/cli.py#fix"]
    assert after["src/cli.py"] == before["src/cli.py"]


@pytest.mark.parametrize(
    ("selectors", "named"),
    [
        (["src/gone.py"], "src/gone.py"),
        (["src/cli.py#check"], "src/cli.py#check"),
        (["src/cli.py#fix", "lib/util.py#nope"], "lib/util.py#nope"),
        (["lib/util.py"], "lib/util.py"),
    ],
)
def test_an_evidence_selector_no_selected_claim_cites_exits_2_and_writes_nothing(
    tmp_path: Path, selectors: list[str], named: str
) -> None:
    """A path nobody cites, a part of a file the claim cites only whole, a typo beside a valid
    entry, and evidence only the unselected claim `b` cites: the run says so, exits 2 and
    changes no pin, the valid selector's included."""
    claims = [
        _Claim("a", ("src/cli.py", "src/cli.py#fix")),
        _Claim("b", ("lib/util.py#helper",)),
    ]
    root = _build(tmp_path, {"src/cli.py": CLI, "lib/util.py": UTIL}, claims)
    before = (root / DOC).read_bytes()
    args: list[str] = []
    for selector in selectors:
        args += ["--evidence", selector]

    code, plain = invoke(root, "anchors", "--re-pin", "--doc", DOC, "--claim", "a", *args)

    assert code == 2, plain
    assert named in plain
    assert (root / DOC).read_bytes() == before


def test_a_part_that_does_not_resolve_and_a_file_that_cannot_be_read_keep_the_pin_they_had(
    tmp_path: Path,
) -> None:
    """An entry whose part is not in its file, whose file is gone or does not parse keeps the
    pin written in the doc; one that had none gets none; the entry that resolves is pinned."""
    entries = (
        "src/cli.py#fix",
        "src/cli.py#gone",
        "src/cli.py#gone2",
        "src/ghost.py#x",
        "src/broken.py",
        "src/broken.py#alpha",
    )
    keep = {
        "src/cli.py#gone": FIXED_PIN,
        "src/ghost.py#x": "sha256:bbbbbbbbbbbb",
        "src/broken.py": "sha256:cccccccccccc",
    }
    files = {"src/cli.py": CLI, "src/broken.py": "def alpha(:\n"}
    root = _build(tmp_path, files, [_Claim("a", entries, pinned=keep)])

    code, plain = invoke(root, "anchors", "--re-pin", "--doc", DOC)

    assert code == 0, plain
    assert _pinned(root) == {**keep, "src/cli.py#fix": _pin(root, "src/cli.py#fix")}


def test_a_re_pin_narrowed_to_a_whole_file_drops_the_pin_of_a_part_the_claim_no_longer_cites(
    tmp_path: Path,
) -> None:
    """The claim cited `src/cli.py#fix` and now cites `src/cli.py` whole; a re-pin narrowed to
    `--evidence src/cli.py` writes the whole file's pin and drops the old spelling's."""
    root = _build(
        tmp_path,
        {"src/cli.py": CLI},
        [_Claim("a", ("src/cli.py#fix",), pin="all")],
    )
    replace_text(root, DOC, "      - src/cli.py#fix", "      - src/cli.py")

    code, plain = invoke(
        root, "anchors", "--re-pin", "--doc", DOC, "--claim", "a", "--evidence", "src/cli.py"
    )

    assert code == 0, plain
    assert _pinned(root) == {"src/cli.py": file_pin(root / "src/cli.py")}
    assert "claim a: src/cli.py#fix (dropped)" in plain


def test_stale_lists_a_part_pin_that_moved_and_not_one_that_still_matches(
    tmp_path: Path,
) -> None:
    """After a change to `fix` alone, `anchors --stale` lists the pin of `src/cli.py#fix`
    with the command that re-pins that entry, which runs as printed and empties the list; the
    pin of `check` and no other is left out, though its file changed."""
    entries = ("src/cli.py#fix", "src/cli.py#check")
    root = _build(tmp_path, {"src/cli.py": CLI}, [_Claim("a", entries, pin="all")])
    replace_text(root, "src/cli.py", "return apply(path)", "return apply(path, confirm=True)")

    [stale] = invoke_json(root, "anchors", "--stale")["stale"]

    assert stale["kind"] == "claim-evidence"
    assert stale["claim"] == "a"
    assert stale["target"] == "src/cli.py#fix"
    assert stale["current"] == _pin(root, "src/cli.py#fix")
    code, plain = invoke(root, *shlex.split(stale["re_pin"])[1:])
    assert code == 0, plain
    assert invoke_json(root, "anchors", "--stale")["stale"] == []


def test_stale_lists_a_whole_file_pin_and_not_the_part_pin_of_the_same_file(
    tmp_path: Path,
) -> None:
    """A change to a function other than `fix` moves the pin of the bare `src/cli.py` and not
    that of `src/cli.py#fix`."""
    entries = ("src/cli.py", "src/cli.py#fix")
    root = _build(tmp_path, {"src/cli.py": CLI}, [_Claim("a", entries, pin="all")])
    replace_text(root, "src/cli.py", "return run(path)", "return run(path, strict=True)")

    stale = invoke_json(root, "anchors", "--stale")["stale"]

    assert [row["target"] for row in stale] == ["src/cli.py"]
