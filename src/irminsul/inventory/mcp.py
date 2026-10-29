"""McpToolExtractor — static MCP tool surface from Python source.

AST-walks `.py` files (never imports them) and collects every function decorated
with ``@<server>.tool(...)`` — the MCP tool registrations in
`mcp_server.py`. The tool's identity is its function name, which is exactly the
tool name the server exposes. Symmetric with the other extractors: adding the kind
is "add a file here," and the surface becomes queryable via `irminsul surface mcp`
and governable via a watched `inventory:` block.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import ClassVar

from irminsul.inventory.base import SourceReader, SurfaceItem, dedupe


class McpToolExtractor:
    kind: ClassVar[str] = "mcp"

    def extract(
        self, source_files: list[tuple[Path, str]], reader: SourceReader
    ) -> list[SurfaceItem]:
        items: list[SurfaceItem] = []
        for module, display in reader.python_modules(source_files):
            for node in module.nodes:
                if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                if any(_is_tool_decorator(dec) for dec in node.decorator_list):
                    items.append(
                        SurfaceItem(
                            identity=node.name,
                            display=display,
                            line=node.lineno,
                        )
                    )
        return dedupe(items)


def _is_tool_decorator(dec: ast.expr) -> bool:
    """Match ``@<x>.tool`` and ``@<x>.tool(...)`` (the MCP registration form).

    Keyed on the attribute name, not the server class, so it is unaffected by an
    SDK rename such as FastMCP -> MCPServer.
    """
    if isinstance(dec, ast.Call):
        dec = dec.func
    return isinstance(dec, ast.Attribute) and dec.attr == "tool"
