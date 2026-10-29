"""FastapiHttpExtractor — static HTTP route surface from Python source.

AST-walks `.py` files for FastAPI/Starlette-style route decorators
(``@app.get("/x")``, ``@router.post("/y")``, …) and emits ``METHOD /path``
identities.

Static ceiling: ``APIRouter`` prefixes applied at ``include_router(..., prefix=...)``
are not resolved, so paths are as written on the decorator.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import ClassVar

from irminsul.inventory.base import SourceReader, SurfaceItem, dedupe

_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


class FastapiHttpExtractor:
    kind: ClassVar[str] = "http"

    def extract(
        self, source_files: list[tuple[Path, str]], reader: SourceReader
    ) -> list[SurfaceItem]:
        items: list[SurfaceItem] = []
        for module, display in reader.python_modules(source_files):
            for node in module.nodes:
                if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                for dec in node.decorator_list:
                    route = _route(dec)
                    if route is None:
                        continue
                    method, path = route
                    items.append(
                        SurfaceItem(
                            identity=f"{method.upper()} {path}",
                            display=display,
                            line=node.lineno,
                        )
                    )
        return dedupe(items)


def _route(dec: ast.expr) -> tuple[str, str] | None:
    if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
        return None
    method = dec.func.attr
    if method not in _HTTP_METHODS:
        return None
    for arg in dec.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return method, arg.value
    for kw in dec.keywords:
        if (
            kw.arg == "path"
            and isinstance(kw.value, ast.Constant)
            and isinstance(kw.value.value, str)
        ):
            return method, kw.value.value
    return None
