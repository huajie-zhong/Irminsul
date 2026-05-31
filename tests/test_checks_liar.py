"""Tests for LiarCheck — the boundary lint against hand-enumerating a derivable surface."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from irminsul.checks import Severity
from irminsul.checks.liar import LiarCheck
from irminsul.config import load
from irminsul.docgraph import build_graph

_CLI_SRC = """\
import typer

app = typer.Typer()


@app.command()
def alpha():
    pass


@app.command()
def beta():
    pass


@app.command()
def gamma():
    pass
"""


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "r"
    (repo / "src").mkdir(parents=True)
    (repo / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
        encoding="utf-8",
    )
    (repo / "src" / "cli.py").write_text(_CLI_SRC, encoding="utf-8")
    return repo


def _doc(
    repo: Path,
    rel: str,
    *,
    doc_id: str,
    body: str,
    audience: str = "explanation",
    frontmatter_extra: list[str] | None = None,
) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "---",
                f"id: {doc_id}",
                f"title: {doc_id}",
                f"audience: {audience}",
                "tier: 3",
                "status: stable",
                "describes: []",
                *(frontmatter_extra or []),
                "---",
                "",
                f"# {doc_id}",
                "",
                body,
            ]
        ),
        encoding="utf-8",
    )


def _run(repo: Path) -> list:
    return LiarCheck().run(build_graph(repo, load(repo / "irminsul.toml")))


def test_prose_enumeration_flagged(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _doc(
        repo,
        "docs/20-components/widget.md",
        doc_id="widget",
        body="- `r alpha` runs A\n- `r beta` runs B\n- `r gamma` runs C\n",
    )
    findings = [f for f in _run(repo) if f.doc_id == "widget"]
    assert len(findings) == 1
    assert findings[0].severity == Severity.warning
    assert findings[0].line is not None and findings[0].line > 0
    assert "cli" in findings[0].message


def test_inventory_block_suppresses(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _doc(
        repo,
        "docs/20-components/widget.md",
        doc_id="widget",
        body="- `r alpha` runs A\n- `r beta` runs B\n- `r gamma` runs C\n",
        frontmatter_extra=[
            "inventory:",
            "  - kind: cli",
            "    source: src/cli.py",
            "    items: [alpha]",
        ],
    )
    assert [f for f in _run(repo) if f.doc_id == "widget"] == []


def test_bare_tokens_not_flagged(tmp_path: Path) -> None:
    # Component links like `[alpha](alpha.md)` must not collide with command names.
    repo = _repo(tmp_path)
    _doc(
        repo,
        "docs/20-components/widget.md",
        doc_id="widget",
        body="See `alpha`, `beta`, and `gamma` components.",
    )
    assert [f for f in _run(repo) if f.doc_id == "widget"] == []


def test_tutorial_audience_exempt(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _doc(
        repo,
        "docs/30-guides/tour.md",
        doc_id="tour",
        audience="tutorial",
        body="Run `r alpha`, then `r beta`, then `r gamma`.",
    )
    assert [f for f in _run(repo) if f.doc_id == "tour"] == []


def test_good_fixture_has_no_liar_findings(
    fixture_repo: Callable[[str], Path],
) -> None:
    assert _run(fixture_repo("good")) == []
