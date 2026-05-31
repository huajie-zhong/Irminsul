"""FastapiHttpExtractor — static HTTP route surface from Python source.

AST-walks `.py` files for FastAPI/Starlette-style route decorators
(``@app.get("/x")``, ``@router.post("/y")``, …) and emits ``METHOD /path``
identities.

Static ceiling (documented, out of scope for this RFC): ``APIRouter`` prefixes
applied at ``include_router(..., prefix=...)`` are not resolved, so paths are as
written on the decorator.
"""

from __future__ import annotations

import ast
from pathlib import Path, PurePosixPath
from typing import ClassVar

from irminsul.config import IrminsulConfig
from irminsul.inventory.base import SurfaceItem, dedupe

_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


class FastapiHttpExtractor:
    kind: ClassVar[str] = "http"

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
    return None
