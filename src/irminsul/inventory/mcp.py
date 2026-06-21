"""McpToolExtractor — static MCP tool surface from Python source.

AST-walks `.py` files (never imports them) and collects every function decorated
with ``@<server>.tool(...)`` — the FastMCP tool registrations in
`mcp_server.py`. The tool's identity is its function name, which is exactly the
tool name FastMCP exposes. Symmetric with the other extractors: adding the kind
is "add a file here," and the surface becomes queryable via `irminsul surface mcp`
and governable via a watched `inventory:` block (RFC 0028).
"""

from __future__ import annotations

import ast
from pathlib import Path, PurePosixPath
from typing import ClassVar

from irminsul.config import IrminsulConfig
from irminsul.inventory.base import SurfaceItem, dedupe


class McpToolExtractor:
    kind: ClassVar[str] = "mcp"

    def extract(
        self, source_files: list[tuple[Path, str]], config: IrminsulConfig
    ) -> list[SurfaceItem]:
        items: list[SurfaceItem] = []
        for abs_path, display in source_files:
            if PurePosixPath(display).suffix != ".py":
                continue
            try:
                text = abs_path.read_text(encoding="utf-8")
            except OSError:
                continue
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                if any(_is_tool_decorator(dec) for dec in node.decorator_list):
                    items.append(
                        SurfaceItem(
                            identity=node.name,
                            display=display,
                            line=node.lineno,
                            symbol=f"{display}#{node.name}",
                        )
                    )
        return dedupe(items)


def _is_tool_decorator(dec: ast.expr) -> bool:
    """Match ``@<x>.tool`` and ``@<x>.tool(...)`` (FastMCP's registration)."""
    if isinstance(dec, ast.Call):
        dec = dec.func
    return isinstance(dec, ast.Attribute) and dec.attr == "tool"
