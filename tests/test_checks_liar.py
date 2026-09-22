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
        "docs/components/widget.md",
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
        "docs/components/widget.md",
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


def test_another_programs_command_is_not_counted(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "r"\n\n[project.scripts]\nr = "r.cli:app"\n', encoding="utf-8"
    )
    _doc(
        repo,
        "docs/components/widget.md",
        doc_id="widget",
        body="Run `git alpha`, `hg beta`, and `svn gamma` first.",
    )
    assert [f for f in _run(repo) if f.doc_id == "widget"] == []

    _doc(
        repo,
        "docs/components/widget.md",
        doc_id="widget",
        body="Run `r alpha`, `r beta`, and `r gamma` first.",
    )
    assert len([f for f in _run(repo) if f.doc_id == "widget"]) == 1


def test_bare_tokens_not_flagged(tmp_path: Path) -> None:
    # Component links like `[alpha](alpha.md)` must not collide with command names.
    repo = _repo(tmp_path)
    _doc(
        repo,
        "docs/components/widget.md",
        doc_id="widget",
        body="See `alpha`, `beta`, and `gamma` components.",
    )
    assert [f for f in _run(repo) if f.doc_id == "widget"] == []


def test_guides_are_not_scanned(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _doc(
        repo,
        "docs/guides/tour.md",
        doc_id="tour",
        body="Run `r alpha`, then `r beta`, then `r gamma`.",
    )
    assert [f for f in _run(repo) if f.doc_id == "tour"] == []


_MCP_SRC = """\
def create_server(root):
    server = MCPServer("x")

    @server.tool()
    def alpha() -> str:
        return ""

    @server.tool()
    def beta() -> str:
        return ""

    @server.tool()
    def gamma() -> str:
        return ""

    return server
"""


def test_mcp_kind_excluded_from_prose_scan(tmp_path: Path) -> None:
    # MCP tool identities are function names that shadow CLI commands; docs bare-
    # backtick them legitimately. The mcp kind must not drive liar.
    repo = _repo(tmp_path)
    (repo / "src" / "mcp_server.py").write_text(_MCP_SRC, encoding="utf-8")
    _doc(
        repo,
        "docs/components/widget.md",
        doc_id="widget",
        body="The tools are `alpha`, `beta`, and `gamma`.",
    )
    findings = [f for f in _run(repo) if f.doc_id == "widget"]
    assert all("mcp" not in f.message for f in findings)
    assert findings == []


def test_good_fixture_has_no_liar_findings(
    fixture_repo: Callable[[str], Path],
) -> None:
    assert _run(fixture_repo("good")) == []


def _named_kind_repo(root: Path, body: str) -> Path:
    (root / "src").mkdir(parents=True)
    names = [
        "schema-leak",
        "rfc-lifecycle",
        "prose-file-reference",
        "retired-references",
        "agents-manifest",
        "links",
    ]
    (root / "src" / "checks.txt").write_text(
        "".join(f'name = "{name}"\n' for name in names), encoding="utf-8"
    )
    (root / "irminsul.toml").write_text(
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n'
        "[[checks.inventory_drift.generic]]\n"
        'kind = "checks"\nglob = "*.txt"\npattern = \'^name = "([a-z-]+)"\'\nprose_named = true\n',
        encoding="utf-8",
    )
    doc = root / "docs" / "components" / "gate.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        f"---\nid: gate\ntitle: Gate\nstatus: stable\n---\n\n# Gate\n\n{body}\n",
        encoding="utf-8",
    )
    return root


def test_a_table_hand_listing_named_items_is_flagged(tmp_path: Path) -> None:
    table = "\n".join(
        f"| `{name}` | blocks |"
        for name in [
            "schema-leak",
            "rfc-lifecycle",
            "prose-file-reference",
            "retired-references",
            "agents-manifest",
            "links",
        ]
    )
    repo = _named_kind_repo(tmp_path, "| Check | Effect |\n|---|---|\n" + table)
    [finding] = LiarCheck().run(build_graph(repo, load(repo / "irminsul.toml")))
    assert "a list or table enumerates 5 'checks' items" in finding.message


def test_named_items_mentioned_in_passing_are_not_flagged(tmp_path: Path) -> None:
    body = (
        "`schema-leak` runs first. Then `rfc-lifecycle`.\n\n"
        "- `prose-file-reference` and `retired-references`\n\n`agents-manifest` is opt-in."
    )
    repo = _named_kind_repo(tmp_path, body)
    assert LiarCheck().run(build_graph(repo, load(repo / "irminsul.toml"))) == []
