"""MkDocs Material renderer.

Generates `mkdocs.yml` from the DocGraph (nav grouped by layer prefix), then
shells out to `mkdocs build`. MkDocs is an optional dependency; if it isn't on
PATH we print a clear install hint instead of crashing.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from ruamel.yaml import YAML

from irminsul.docgraph import DocGraph

_LAYER_TITLES = {
    "00-foundation": "Foundation",
    "10-architecture": "Architecture",
    "20-components": "Components",
    "30-workflows": "Workflows",
    "40-reference": "Reference",
    "50-decisions": "Decisions",
    "60-operations": "Operations",
    "70-knowledge": "Knowledge",
    "80-evolution": "Evolution",
    "90-meta": "Meta",
}


class MkDocsRenderError(RuntimeError):
    """Raised when MkDocs is unavailable or `mkdocs build` fails."""


class MkDocsRenderer:
    name: str = "mkdocs"

    def build(self, graph: DocGraph, out_dir: Path) -> None:
        if graph.config is None or graph.repo_root is None:
            raise MkDocsRenderError("graph is missing config/repo_root")

        if importlib.util.find_spec("mkdocs") is None:
            raise MkDocsRenderError(
                "mkdocs is not installed. Install with: pip install 'irminsul[mkdocs]'"
            )

        config_path = graph.repo_root / "mkdocs.yml"
        self._write_config(graph, config_path)

        out_dir.mkdir(parents=True, exist_ok=True)

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "mkdocs",
                "build",
                "--config-file",
                str(config_path),
                "--site-dir",
                str(out_dir),
                "--clean",
            ],
            cwd=graph.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise MkDocsRenderError(
                f"mkdocs build failed (exit {result.returncode}):\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )

    def _write_config(self, graph: DocGraph, config_path: Path) -> None:
        assert graph.config is not None
        docs_dir = graph.config.paths.docs_root
        nav = self._build_nav(graph, docs_dir)

        config: dict[str, object] = {
            "site_name": graph.config.project_name,
            "docs_dir": docs_dir,
            "theme": {
                "name": "material",
                "features": [
                    "navigation.indexes",
                    "navigation.sections",
                    "content.code.copy",
                ],
            },
            "markdown_extensions": [
                "admonition",
                "pymdownx.details",
                "pymdownx.superfences",
                "tables",
                "toc",
            ],
            "nav": nav,
        }

        yaml = YAML()
        yaml.default_flow_style = False
        with config_path.open("w", encoding="utf-8") as f:
            yaml.dump(config, f)

    def _build_nav(self, graph: DocGraph, docs_dir: str) -> list[dict[str, object]]:
        # Group docs by their first path segment under docs_dir.
        by_layer: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for node in graph.nodes.values():
            path_str = node.path.as_posix()
            if not path_str.startswith(f"{docs_dir}/"):
                continue
            rel = path_str[len(docs_dir) + 1 :]
            parts = rel.split("/", 1)
            layer = parts[0]
            title = node.frontmatter.title
            by_layer[layer].append((title, rel))

        nav: list[dict[str, object]] = []
        for layer in sorted(by_layer.keys()):
            entries = sorted(by_layer[layer], key=lambda item: item[1])
            section_title = _LAYER_TITLES.get(layer, layer)
            nav.append({section_title: [{title: rel} for title, rel in entries]})
        return nav
