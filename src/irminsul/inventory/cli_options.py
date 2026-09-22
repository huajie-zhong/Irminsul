"""CliOptionsExtractor — static Typer long-option surface from Python source.

Identities are bare flags (``--profile``), unscoped by command, because that is how
prose names them.
"""

from __future__ import annotations

import ast
from pathlib import Path, PurePosixPath
from typing import ClassVar

from irminsul.config import IrminsulConfig
from irminsul.inventory.base import SurfaceItem, dedupe


def _is_option_call(node: ast.expr | None) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr == "Option"
    return isinstance(func, ast.Name) and func.id == "Option"


def _annotated_option(annotation: ast.expr | None) -> ast.Call | None:
    if not isinstance(annotation, ast.Subscript):
        return None
    base = annotation.value
    name = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", None)
    if name != "Annotated" or not isinstance(annotation.slice, ast.Tuple):
        return None
    for element in annotation.slice.elts[1:]:
        if _is_option_call(element):
            assert isinstance(element, ast.Call)
            return element
    return None


def _long_flags(call: ast.Call, param_name: str) -> list[str]:
    flags: list[str] = []
    for arg in call.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            for part in arg.value.split("/"):
                part = part.strip()
                if part.startswith("--"):
                    flags.append(part)
    if flags:
        return flags
    named = any(
        isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.startswith("-")
        for arg in call.args
    )
    if named:
        return []
    return [f"--{param_name.replace('_', '-')}"]


class CliOptionsExtractor:
    kind: ClassVar[str] = "cli-options"

    def extract(
        self, source_files: list[tuple[Path, str]], config: IrminsulConfig
    ) -> list[SurfaceItem]:
        items: list[SurfaceItem] = []
        for abs_path, display in source_files:
            if PurePosixPath(display).suffix != ".py":
                continue
            try:
                tree = ast.parse(abs_path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                items.extend(_function_options(node, display))
        if items:
            # Typer adds `--help` to every command without declaring it.
            items.append(SurfaceItem(identity="--help", display=items[0].display, line=None))
        return dedupe(sorted(items, key=lambda item: (item.display or "", item.line or 0)))


def _function_options(
    node: ast.FunctionDef | ast.AsyncFunctionDef, display: str
) -> list[SurfaceItem]:
    params = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
    positional_defaults = [None] * (
        len(node.args.posonlyargs) + len(node.args.args) - len(node.args.defaults)
    ) + list(node.args.defaults)
    defaults: list[ast.expr | None] = [*positional_defaults, *node.args.kw_defaults]
    out: list[SurfaceItem] = []
    for param, default in zip(params, defaults, strict=True):
        call = _annotated_option(param.annotation)
        if call is None and _is_option_call(default):
            assert isinstance(default, ast.Call)
            call = default
        if call is None:
            continue
        for flag in _long_flags(call, param.arg):
            out.append(SurfaceItem(identity=flag, display=display, line=call.lineno))
    return out
