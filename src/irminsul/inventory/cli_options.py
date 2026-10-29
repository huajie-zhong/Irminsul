"""CliOptionsExtractor — static Typer long-option surface from Python source.

Identities are bare flags (``--format``), unscoped by command, because that is how
prose names them.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import ClassVar

from irminsul.inventory.base import PythonModule, SourceReader, SurfaceItem, dedupe


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


def _option_aliases(tree: ast.Module) -> dict[str, ast.Call]:
    """Module-level `Name = Annotated[T, typer.Option(...)]`, which declares the option once
    for every parameter annotated `Name`."""
    aliases: dict[str, ast.Call] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and (call := _annotated_option(node.value)) is not None
        ):
            aliases[node.targets[0].id] = call
    return aliases


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
        self, source_files: list[tuple[Path, str]], reader: SourceReader
    ) -> list[SurfaceItem]:
        items: list[SurfaceItem] = []
        for module, display in reader.python_modules(source_files):
            aliases = _option_aliases(module.tree)
            for node in module.nodes:
                if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                items.extend(
                    SurfaceItem(identity=flag, display=display, line=call.lineno)
                    for flag, call in _function_options(node, aliases)
                )
        if items:
            # Typer adds `--help` to every command without declaring it.
            items.append(SurfaceItem(identity="--help", display=items[0].display, line=None))
        return dedupe(sorted(items, key=lambda item: (item.display or "", item.line or 0)))


def command_options(module: PythonModule, line: int) -> frozenset[str] | None:
    """The long options the function defined at `line` declares, read as the extractor reads
    them: inline, through a module-level alias, or by default value. None when no function
    is defined at `line`."""
    for node in module.nodes:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.lineno == line:
            aliases = _option_aliases(module.tree)
            return frozenset(flag for flag, _ in _function_options(node, aliases))
    return None


def _function_options(
    node: ast.FunctionDef | ast.AsyncFunctionDef, aliases: dict[str, ast.Call]
) -> list[tuple[str, ast.Call]]:
    params = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
    positional_defaults = [None] * (
        len(node.args.posonlyargs) + len(node.args.args) - len(node.args.defaults)
    ) + list(node.args.defaults)
    defaults: list[ast.expr | None] = [*positional_defaults, *node.args.kw_defaults]
    out: list[tuple[str, ast.Call]] = []
    for param, default in zip(params, defaults, strict=True):
        call = _annotated_option(param.annotation)
        if call is None and isinstance(param.annotation, ast.Name):
            call = aliases.get(param.annotation.id)
        if call is None and _is_option_call(default):
            assert isinstance(default, ast.Call)
            call = default
        if call is None:
            continue
        out.extend((flag, call) for flag in _long_flags(call, param.arg))
    return out
