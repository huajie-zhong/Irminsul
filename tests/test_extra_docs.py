"""Tests for guidance files outside the doc graph (`paths.extra_docs`)."""

from __future__ import annotations

import json
from pathlib import Path

from irminsul.checks.links import LinksCheck
from irminsul.config import load
from irminsul.docgraph import build_graph, guidance_files
from irminsul.listing.review import review_json


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _docs_repo(root: Path, extra: str = "") -> Path:
    _write(
        root,
        "irminsul.toml",
        f'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = []\n{extra}',
    )
    _write(
        root,
        "docs/components/INDEX.md",
        "---\nid: components\ntitle: C\nstatus: stable\n---\n\n# C\n",
    )
    return root


def test_readme_links_are_checked(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    _write(
        repo,
        "README.md",
        "See [the guide](docs/guides/missing.md) and [C](docs/components/INDEX.md).\n",
    )

    findings = LinksCheck().run(build_graph(repo, load(repo / "irminsul.toml")))

    assert [(f.path, (f.data or {}).get("resolved")) for f in findings] == [
        (Path("README.md"), "docs/guides/missing.md")
    ]


def test_readme_sentences_are_reviewed(tmp_path: Path) -> None:
    repo = _docs_repo(tmp_path)
    _write(repo, "README.md", "# Tool\n\nThe check always exits 1 on errors.\n")

    items = json.loads(review_json(repo, load(repo / "irminsul.toml"), show_all=True))["items"]

    assert [(i["path"], i["line"]) for i in items] == [("README.md", 3)]


def test_siblings_can_name_the_code_repositorys_files(tmp_path: Path) -> None:
    docs = _docs_repo(tmp_path / "docs-repo", 'extra_docs = ["README.md", "../code/README.md"]\n')
    _write(tmp_path, "code/README.md", "Code readme.\n")
    _write(docs, "README.md", "Docs readme.\n")

    displays = [display for display, _ in guidance_files(docs, load(docs / "irminsul.toml"))]

    assert displays == ["../code/README.md", "README.md"]
