"""Tests for CommandVocabularyCheck — the gate and the no-op on foreign repos."""

from __future__ import annotations

from pathlib import Path

from irminsul.checks.command_vocabulary import CommandVocabularyCheck
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph


def test_check_is_clean_on_the_irminsul_repo() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    config = load(find_config(repo_root))
    graph = build_graph(repo_root, config)
    assert CommandVocabularyCheck().run(graph) == []


def test_check_is_noop_on_a_repo_without_the_vocabulary(tmp_path: Path) -> None:
    repo = tmp_path / "foreign"
    (repo / "src").mkdir(parents=True)
    (repo / "irminsul.toml").write_text(
        'project_name = "foreign"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n',
        encoding="utf-8",
    )
    (repo / "src" / "cli.py").write_text(
        "import typer\n\napp = typer.Typer()\n\n\n@app.command()\ndef hello():\n    pass\n",
        encoding="utf-8",
    )
    (repo / "docs").mkdir()
    config = load(find_config(repo))
    graph = build_graph(repo, config)
    assert CommandVocabularyCheck().run(graph) == []
