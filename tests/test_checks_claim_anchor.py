"""Tests for anchored prose claims."""

from __future__ import annotations

from pathlib import Path

from irminsul.anchors import Anchor, file_pin, parse_anchors, repin_text, resolve
from irminsul.checks.base import Severity
from irminsul.checks.claim_anchor import ClaimAnchorCheck

from .conftest import run_check, write_config

SRC = """\
def alpha():
    # a comment
    return 1


def beta():
    return 2
"""


def _repo(tmp_path: Path, marker: str, src: str = SRC) -> Path:
    repo = tmp_path / "r"
    (repo / "src").mkdir(parents=True)
    write_config(repo, source_roots=["src"])
    (repo / "src" / "mod.py").write_text(src, encoding="utf-8")
    doc = repo / "docs" / "components" / "c.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(
        "---\nid: c\ntitle: C\nstatus: stable\n"
        "describes: [src/mod.py]\n---\n\n# C\n\nAlpha does a thing.\n" + marker + "\n",
        encoding="utf-8",
    )
    return repo


def _run(repo: Path) -> list:
    return run_check(ClaimAnchorCheck, repo)


def _current_hash(repo: Path, symbol: str) -> str:
    res = resolve(repo, Anchor(line=0, raw="", path="src/mod.py", symbol=symbol, pinned=None))
    assert res.current is not None
    return res.current


def test_fresh_pin_is_clean(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "<!-- anchor: src/mod.py#alpha @sha256:PLACEHOLDER -->")
    digest = _current_hash(repo, "alpha")
    marker = f"<!-- anchor: src/mod.py#alpha @sha256:{digest} -->"
    repo = _repo(tmp_path / "fresh", marker)
    assert _run(repo) == []


def test_drifted_pin_warns(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "<!-- anchor: src/mod.py#alpha @sha256:deadbeef0000 -->")
    findings = _run(repo)
    assert len(findings) == 1
    assert findings[0].severity == Severity.warning
    assert "`irminsul anchors --re-pin --doc docs/components/c.md --anchor src/mod.py#alpha`" in (
        findings[0].suggestion or ""
    )


def test_missing_symbol_errors(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "<!-- anchor: src/mod.py#ghost @sha256:abc123abc123 -->")
    findings = _run(repo)
    assert len(findings) == 1
    assert findings[0].severity == Severity.error
    assert "ghost" in findings[0].message


def test_missing_file_errors(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "<!-- anchor: src/gone.py#alpha @sha256:abc123abc123 -->")
    findings = _run(repo)
    assert len(findings) == 1
    assert findings[0].severity == Severity.error
    assert "does not exist" in findings[0].message


def test_unpinned_is_info(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "<!-- anchor: src/mod.py#alpha -->")
    findings = _run(repo)
    assert len(findings) == 1
    assert findings[0].severity == Severity.info


def test_repin_updates_hash(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "<!-- anchor: src/mod.py#alpha -->")
    doc = repo / "docs" / "components" / "c.md"
    new_text, changed = repin_text(repo, doc.read_text(encoding="utf-8"))
    assert changed == ["anchor src/mod.py#alpha"]
    doc.write_text(new_text, encoding="utf-8")
    # after re-pinning, the check is clean and the anchor is now pinned
    assert _run(repo) == []
    assert parse_anchors(new_text)[0].pinned is not None


def test_file_level_anchor_is_ast_normalized(tmp_path: Path) -> None:
    # A file-level anchor (no #symbol) hashes the AST, so reformatting the file
    # must not change the hash.
    reformatted = "def alpha():\n    return 1  # changed comment\n\n\ndef beta():\n    return 2\n"
    file_anchor = Anchor(line=0, raw="", path="src/mod.py", symbol=None, pinned=None)
    a = resolve(_repo(tmp_path / "a", "x", SRC), file_anchor)
    b = resolve(_repo(tmp_path / "b", "x", reformatted), file_anchor)
    assert a.current == b.current is not None


CITED_DOC = """\
---
id: cited
title: Cited
status: stable
summary: A cited doc.
claims:
  - id: holds
    state: implemented
    kind: invariant
    claim: The thing holds.
    evidence:
      - src/mod.py
    pinned:
      src/mod.py: sha256:0123456789ab
---

# Cited

See <!-- anchor: src/mod.py#alpha @sha256:0123456789ab --> for it.
"""


def test_a_re_pin_in_a_cited_doc_does_not_move_its_hash(tmp_path: Path) -> None:
    doc = tmp_path / "cited.md"
    doc.write_text(CITED_DOC, encoding="utf-8")
    before = file_pin(doc)
    doc.write_text(
        CITED_DOC.replace("src/mod.py: sha256:0123456789ab\n", "src/mod.py: sha256:ffffffffffff\n"),
        encoding="utf-8",
    )

    assert before == "sha256:baae072ee90c"
    assert file_pin(doc) == before


def test_a_file_level_anchor_on_a_doc_follows_its_words_not_its_pins(tmp_path: Path) -> None:
    doc = "docs/components/cited.md"
    repo = tmp_path / "r"
    (repo / "docs" / "components").mkdir(parents=True)
    (repo / doc).write_text(CITED_DOC, encoding="utf-8")
    anchor = Anchor(line=0, raw="", path=doc, symbol=None, pinned=None)
    before = resolve(repo, anchor).current

    (repo / doc).write_text(
        CITED_DOC.replace("sha256:0123456789ab", "sha256:ffffffffffff"), encoding="utf-8"
    )
    assert resolve(repo, anchor).current == before

    (repo / doc).write_text(
        CITED_DOC.replace("The thing holds.", "The thing breaks."), encoding="utf-8"
    )
    assert resolve(repo, anchor).current != before


def test_a_pinned_line_in_a_summary_block_moves_the_hash_when_edited(tmp_path: Path) -> None:
    doc = tmp_path / "summary.md"
    text = CITED_DOC.replace(
        "summary: A cited doc.", "summary: |\n  A cited doc.\n  pinned: this line is prose"
    )
    doc.write_text(text, encoding="utf-8")
    before = file_pin(doc)

    doc.write_text(text.replace("this line is prose", "this line is not"), encoding="utf-8")

    assert file_pin(doc) != before


def test_a_doc_whose_frontmatter_does_not_parse_still_has_a_hash(tmp_path: Path) -> None:
    doc = tmp_path / "broken.md"
    doc.write_text("---\nid: x\nclaims: [unclosed\n---\n\nBody.\n", encoding="utf-8")

    assert file_pin(doc) is not None


def test_unreadable_target_warns(tmp_path: Path) -> None:
    # A symbol anchor whose target file has a syntax error is reported, not skipped.
    repo = _repo(tmp_path, "<!-- anchor: src/mod.py#alpha @sha256:abc123abc123 -->", "def (:\n")
    findings = _run(repo)
    assert len(findings) == 1
    assert findings[0].severity == Severity.warning
    assert "could not be read or parsed" in findings[0].message


def test_hash_is_ast_normalized(tmp_path: Path) -> None:
    # Formatting/comment changes to the symbol must not change the hash.
    reformatted = "def alpha():\n    return 1  # different comment, extra spacing\n\n\ndef beta():\n    return 2\n"
    h1 = _current_hash(_repo(tmp_path / "a", "x", SRC), "alpha")
    h2 = _current_hash(_repo(tmp_path / "b", "x", reformatted), "alpha")
    assert h1 == h2


PRINTED_DIFFERENTLY = '''\
def render(name, width, items):
    """Render a row."""
    a = f"{name!r} said '{width:>{width}}'"
    b = f'{name} wrote "{items[0]!s:^10}"'
    c = f"{'-'.join(f'{item!r}' for item in items)}"
    d = f'{f"{name:{width}}"!r:>20}'
    return a + b + c + d + "⿼"
'''


def test_hash_is_the_same_on_every_python(tmp_path: Path) -> None:
    # A constant, so each leg of the CI matrix checks its own interpreter against it. On
    # 3.12.3 `ast.unparse` prints these f-strings differently and the parser closes
    # `{name:{width}}` with an empty literal; on 3.13 `repr` stops escaping U+2FFC.
    repo = _repo(tmp_path, "x", PRINTED_DIFFERENTLY)
    assert _current_hash(repo, "render") == "b1abf3867582"
