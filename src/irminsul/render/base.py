"""Renderer Protocol — pluggable doc-site backends."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from irminsul.docgraph import DocGraph


@runtime_checkable
class Renderer(Protocol):
    name: str

    def build(self, graph: DocGraph, out_dir: Path) -> None: ...
