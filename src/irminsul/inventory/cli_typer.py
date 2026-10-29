"""CliTyperExtractor — static Typer command surface from Python source.

AST-walks `.py` files (never imports them) and reconstructs the full command
paths Typer would register, including nested sub-apps. It replicates Typer's
implicit naming (function name → lowercased, ``_`` → ``-``) so its output matches
the commands Typer registers for the same code; an agreement test pins that
equivalence against the live app.

Static ceiling: only statically-decorated commands and ``add_typer`` edges are
seen — commands registered in a loop or via dynamic dispatch are out of scope.
"""

from __future__ import annotations

import ast
from collections import deque
from pathlib import Path
from typing import ClassVar

from irminsul.inventory.base import PythonModule, SourceReader, SurfaceItem, dedupe


def _command_name(explicit: str | None, func_name: str) -> str:
    if explicit:
        return explicit
    return func_name.lower().replace("_", "-")


def _str_arg(call: ast.Call) -> str | None:
    for arg in call.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
    return None


def _kw_str(call: ast.Call, name: str) -> str | None:
    for kw in call.keywords:
        if (
            kw.arg == name
            and isinstance(kw.value, ast.Constant)
            and isinstance(kw.value.value, str)
        ):
            return kw.value.value
    return None


class CliTyperExtractor:
    kind: ClassVar[str] = "cli"

    def extract(
        self, source_files: list[tuple[Path, str]], reader: SourceReader
    ) -> list[SurfaceItem]:
        # app var -> constructor name= (or None)
        apps: dict[str, str | None] = {}
        # parent var -> list of (child var, group name)
        edges: dict[str, list[tuple[str, str]]] = {}
        # (app var, command name, defining function name, display, line)
        commands: list[tuple[str, str, str, int]] = []

        for module, display in reader.python_modules(source_files):
            self._scan_module(module, display, apps, edges, commands)

        prefixes = self._resolve_prefixes(apps, edges)

        items: list[SurfaceItem] = []
        for app_var, cmd, display, line in commands:
            # Click, Flask, and others share the `@x.command()` shape; only a variable
            # built by `typer.Typer()` is a Typer app.
            if app_var not in apps:
                continue
            prefix = prefixes.get(app_var, [])
            identity = " ".join([*prefix, cmd])
            items.append(
                SurfaceItem(
                    identity=identity,
                    display=display,
                    line=line,
                )
            )
        return dedupe(items)

    def _scan_module(
        self,
        module: PythonModule,
        display: str,
        apps: dict[str, str | None],
        edges: dict[str, list[tuple[str, str]]],
        commands: list[tuple[str, str, str, int]],
    ) -> None:
        for node in module.nodes:
            # Typer() construction: X = typer.Typer(name=...)
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Call)
                and _is_typer_ctor(node.value)
            ):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        apps[target.id] = _kw_str(node.value, "name")

            # add_typer: parent.add_typer(child, name=...)
            if isinstance(node, ast.Call) and _attr_call(node, "add_typer"):
                assert isinstance(node.func, ast.Attribute)
                if isinstance(node.func.value, ast.Name) and node.args:
                    parent = node.func.value.id
                    child_arg = node.args[0]
                    if isinstance(child_arg, ast.Name):
                        child = child_arg.id
                        explicit = _kw_str(node, "name")
                        group = explicit or apps.get(child) or child
                        edges.setdefault(parent, []).append((child, group))

            # @app.command("name") on a function def
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                for dec in node.decorator_list:
                    parsed = _command_decorator(dec)
                    if parsed is None:
                        continue
                    app_var, explicit = parsed
                    name = _command_name(explicit, node.name)
                    commands.append((app_var, name, display, node.lineno))

    def _resolve_prefixes(
        self,
        apps: dict[str, str | None],
        edges: dict[str, list[tuple[str, str]]],
    ) -> dict[str, list[str]]:
        children = {child for kids in edges.values() for child, _ in kids}
        roots = [var for var in {*apps, *edges} if var not in children]

        prefixes: dict[str, list[str]] = {root: [] for root in roots}
        queue: deque[str] = deque(roots)
        while queue:
            parent = queue.popleft()
            for child, group in edges.get(parent, []):
                if child in prefixes:
                    continue
                prefixes[child] = [*prefixes[parent], group]
                queue.append(child)
        return prefixes


def _is_typer_ctor(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr == "Typer"
    if isinstance(func, ast.Name):
        return func.id == "Typer"
    return False


def _attr_call(call: ast.Call, attr: str) -> bool:
    return isinstance(call.func, ast.Attribute) and call.func.attr == attr


def _command_decorator(dec: ast.expr) -> tuple[str, str | None] | None:
    """Return (app_var, explicit_name|None) for a Typer command decorator."""
    if not isinstance(dec, ast.Call):
        return None
    func = dec.func
    if not isinstance(func, ast.Attribute) or func.attr != "command":
        return None
    if not isinstance(func.value, ast.Name):
        return None
    return func.value.id, _str_arg(dec)
