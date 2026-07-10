"""Surface-extractor registry.

`EXTRACTOR_REGISTRY` maps a surface `kind` to its built-in extractor. `get_extractor`
resolves a kind to an extractor, falling back to a config-declared
`GenericRegexExtractor` when no built-in matches.
"""

from __future__ import annotations

from irminsul.config import IrminsulConfig
from irminsul.inventory.base import Extractor, SurfaceItem
from irminsul.inventory.cli_typer import CliTyperExtractor
from irminsul.inventory.env_vars import EnvVarsExtractor
from irminsul.inventory.exports_ts import TypeScriptExportsExtractor
from irminsul.inventory.generic_regex import GenericRegexExtractor
from irminsul.inventory.http_fastapi import FastapiHttpExtractor
from irminsul.inventory.mcp import McpToolExtractor

EXTRACTOR_REGISTRY: dict[str, Extractor] = {
    CliTyperExtractor.kind: CliTyperExtractor(),
    FastapiHttpExtractor.kind: FastapiHttpExtractor(),
    TypeScriptExportsExtractor.kind: TypeScriptExportsExtractor(),
    EnvVarsExtractor.kind: EnvVarsExtractor(),
    McpToolExtractor.kind: McpToolExtractor(),
}

KNOWN_KINDS = tuple(EXTRACTOR_REGISTRY)


def get_extractor(kind: str, config: IrminsulConfig) -> Extractor | None:
    built_in = EXTRACTOR_REGISTRY.get(kind)
    if built_in is not None:
        return built_in
    return GenericRegexExtractor.for_kind(kind, config)


__all__ = [
    "EXTRACTOR_REGISTRY",
    "KNOWN_KINDS",
    "CliTyperExtractor",
    "EnvVarsExtractor",
    "Extractor",
    "FastapiHttpExtractor",
    "GenericRegexExtractor",
    "McpToolExtractor",
    "SurfaceItem",
    "TypeScriptExportsExtractor",
    "get_extractor",
]
