"""On-demand code-surface derivation.

The positive side of "derive, don't materialize": instead of committing a generated
reference that goes stale, `irminsul surface <kind>` derives and aggregates a surface
from code at call time and persists nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from pathspec import GitIgnoreSpec

from irminsul.checks.globs import walk_source_files
from irminsul.config import IrminsulConfig
from irminsul.inventory import get_extractor
from irminsul.inventory.base import SurfaceItem


def derive_surface(
    repo_root: Path,
    config: IrminsulConfig,
    kind: str,
    source: str | None = None,
) -> list[SurfaceItem]:
    """Extract the surface of `kind`, optionally limited to files matching `source`."""
    extractor = get_extractor(kind, config)
    if extractor is None:
        return []
    files, _ = walk_source_files(repo_root, config.paths.source_roots)
    if source:
        spec = GitIgnoreSpec.from_lines([source])
        files = [(p, d) for p, d in files if spec.match_file(d)]
    return extractor.extract(files, config)


def surface_items_to_json(items: list[SurfaceItem]) -> str:
    payload = [
        {"identity": item.identity, "display": item.display, "line": item.line} for item in items
    ]
    return json.dumps(payload, indent=2)


def run_surface(
    repo_root: Path,
    config: IrminsulConfig,
    kind: str,
    source: str | None,
    fmt: str,
) -> None:
    if get_extractor(kind, config) is None:
        typer.echo(
            typer.style(
                f"no extractor for kind '{kind}' "
                "(built-in: cli, http, exports, env-vars; or declare a generic rule)",
                fg="red",
            )
        )
        raise typer.Exit(code=2)

    items = derive_surface(repo_root, config, kind, source)
    if fmt == "json":
        typer.echo(surface_items_to_json(items))
    else:
        for item in items:
            typer.echo(item.identity)
