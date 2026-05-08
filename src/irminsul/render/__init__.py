"""Rendering layer: take a DocGraph, produce a static site."""

from __future__ import annotations

from irminsul.render.base import Renderer
from irminsul.render.mkdocs import MkDocsRenderer

__all__ = ["MkDocsRenderer", "Renderer"]
