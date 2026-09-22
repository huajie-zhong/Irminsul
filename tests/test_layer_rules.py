"""Tests for the rules a layer's config applies to the docs in it."""

from __future__ import annotations

from pathlib import Path

from irminsul.checks.boundary import BoundaryCheck
from irminsul.checks.coverage import CoverageCheck
from irminsul.checks.reality import RealityCheck
from irminsul.config import load
from irminsul.docgraph import build_graph


def _doc(root: Path, rel: str, doc_id: str, body: str) -> None:
    path = root / "docs" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nid: {doc_id}\ntitle: {doc_id}\nstatus: stable\n"
        f"describes:\n  - src/app.py\n---\n\n# {doc_id}\n\n{body}\n",
        encoding="utf-8",
    )


def _repo(root: Path, layers_toml: str) -> Path:
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    (root / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n' + layers_toml,
        encoding="utf-8",
    )
    body = "The roadmap is upcoming."
    _doc(root, "modules/app.md", "app", body)
    _doc(root, "modules/INDEX.md", "modules", body)
    _doc(root, "guides/howto.md", "howto", body)
    _doc(root, "notes/scratch.md", "scratch", body)
    return root


def _flagged(repo: Path) -> dict[str, set[str]]:
    graph = build_graph(repo, load(repo / "irminsul.toml"))
    out: dict[str, set[str]] = {}
    for check in (BoundaryCheck(), CoverageCheck(), RealityCheck()):
        for finding in check.run(graph):
            assert finding.path is not None
            out.setdefault(check.name, set()).add(finding.path.name)
    return out


def test_rules_follow_the_configured_layer_folder(tmp_path: Path) -> None:
    repo = _repo(tmp_path, '[layers.components]\npath = "modules"\n')
    assert _flagged(repo) == {
        "boundary": {"app.md"},
        "coverage": {"app.md"},
        "reality": {"app.md"},
    }


def test_a_layer_can_turn_a_rule_on(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        '[layers.components]\npath = "modules"\n'
        '[layers.guides]\npath = "guides"\nrequire_scope_section = true\n',
    )
    flagged = _flagged(repo)
    assert flagged["boundary"] == {"app.md", "howto.md"}
    assert flagged["coverage"] == {"app.md"}
