"""Static surface extractors.

Each extractor turns source files into a list of `SurfaceItem` identities for one
*kind* of code surface (CLI commands, HTTP endpoints, exports, env vars). They are
**static only** — irminsul must never import or execute a target repo's code, so
extraction is AST/regex over file text, never `import`.

Extractors power three consumers: the `irminsul surface` query, the
`inventory-drift` check, and the boundary lint. Adding a kind = add a module here
and register it in `EXTRACTOR_REGISTRY`; nothing in the checks needs to change.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from irminsul.config import IrminsulConfig


@dataclass(frozen=True)
class SurfaceItem:
    """One extracted surface element.

    `identity` is the diff key (e.g. ``"regen agents-md"``, ``"GET /api/check"``,
    a symbol name, or an env-var name). `display`/`line` are best-effort provenance
    for human-facing output and are never compared. `symbol` is an optional
    ``path#qualname`` ref the anchor hasher can resolve (RFC 0027 fingerprints);
    extractors that cannot point at a defining code symbol leave it ``None``.
    """

    identity: str
    display: str | None = None
    line: int | None = None
    symbol: str | None = None


@runtime_checkable
class Extractor(Protocol):
    @property
    def kind(self) -> str: ...

    def extract(
        self, source_files: list[tuple[Path, str]], config: IrminsulConfig
    ) -> list[SurfaceItem]: ...


def dedupe(items: list[SurfaceItem]) -> list[SurfaceItem]:
    """Keep the first occurrence of each identity, preserving order."""
    seen: set[str] = set()
    out: list[SurfaceItem] = []
    for item in items:
        if item.identity in seen:
            continue
        seen.add(item.identity)
        out.append(item)
    return out
