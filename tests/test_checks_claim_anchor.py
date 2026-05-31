"""Tests for anchored prose claims (RFC 0024)."""

from __future__ import annotations

from pathlib import Path

from irminsul.anchors import Anchor, parse_anchors, repin_text, resolve
from irminsul.checks.base import Severity
from irminsul.checks.claim_anchor import ClaimAnchorCheck
from irminsul.config import load
from irminsul.docgraph import build_graph

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
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
        encoding="utf-8",
    )
    (repo / "src" / "mod.py").write_text(src, encoding="utf-8")
    doc = repo / "docs" / "20-components" / "c.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(
        "---\nid: c\ntitle: C\naudience: explanation\ntier: 3\nstatus: stable\n"
        "describes: [src/mod.py]\n---\n\n# C\n\nAlpha does a thing.\n" + marker + "\n",
        encoding="utf-8",
    )
    return repo


def _run(repo: Path) -> list:
    return ClaimAnchorCheck().run(build_graph(repo, load(repo / "irminsul.toml")))


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
    assert "re-pin" in (findings[0].suggestion or "")


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
    doc = repo / "docs" / "20-components" / "c.md"
    new_text, changed = repin_text(repo, doc.read_text(encoding="utf-8"))
    assert changed == 1
    doc.write_text(new_text, encoding="utf-8")
    # after re-pinning, the check is clean and the anchor is now pinned
    assert _run(repo) == []
    assert parse_anchors(new_text)[0].pinned is not None


def test_hash_is_ast_normalized(tmp_path: Path) -> None:
    # Formatting/comment changes to the symbol must not change the hash.
    reformatted = "def alpha():\n    return 1  # different comment, extra spacing\n\n\ndef beta():\n    return 2\n"
    h1 = _current_hash(_repo(tmp_path / "a", "x", SRC), "alpha")
    h2 = _current_hash(_repo(tmp_path / "b", "x", reformatted), "alpha")
    assert h1 == h2
