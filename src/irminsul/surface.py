"""On-demand code-surface derivation.

The positive side of "derive, don't materialize": instead of committing a generated
reference that goes stale, `irminsul surface <kind>` derives and aggregates a surface
from code at call time and persists nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

from irminsul.config import IrminsulConfig
from irminsul.errors import UserError
from irminsul.inventory import KNOWN_KINDS_TEXT, get_extractor
from irminsul.inventory.base import SurfaceItem


class UnknownSurfaceKindError(UserError, ValueError):
    """The kind names neither a built-in extractor nor a configured surface rule."""


def derive_surface(
    repo_root: Path,
    config: IrminsulConfig,
    kind: str,
    source: str | None = None,
) -> list[SurfaceItem]:
    """Extract the surface of `kind`, optionally limited to files matching `source`."""
    from irminsul.source_tree import SourceTree

    return list(SourceTree(repo_root, config).surface(kind, (source,) if source else ()))


def surface_items_to_json(items: list[SurfaceItem]) -> str:
    payload = [
        {"identity": item.identity, "display": item.display, "line": item.line} for item in items
    ]
    return json.dumps(payload, indent=2)


def derive_requested_surface(
    repo_root: Path,
    config: IrminsulConfig,
    kind: str,
    source: str | None = None,
) -> list[SurfaceItem]:
    """`derive_surface` for a kind a caller named, where an unknown kind is an error.

    `derive_surface` answers an empty surface for a kind with no extractor, which is right
    for the built-in kinds a framework selection may have narrowed away and wrong for a
    kind somebody typed.
    """
    if get_extractor(kind, config) is None:
        raise UnknownSurfaceKindError(
            f"no extractor for kind '{kind}' "
            f"(built-in: {KNOWN_KINDS_TEXT}; or declare a surface rule)"
        )
    return derive_surface(repo_root, config, kind, source)
