"""Framework packs, identity templates, and kind capabilities.

A pack bundles what one framework exposes as code surfaces: AST extractors where
Irminsul has them, and regex rules otherwise. Rules carry a file guard so a pack
reads only files that use its framework.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from pathspec import GitIgnoreSpec

from irminsul.config import IrminsulConfig
from irminsul.inventory.base import Extractor, SurfaceItem, dedupe
from irminsul.inventory.cli_options import CliOptionsExtractor
from irminsul.inventory.cli_typer import CliTyperExtractor
from irminsul.inventory.env_vars import EnvVarsExtractor
from irminsul.inventory.exports_ts import TypeScriptExportsExtractor
from irminsul.inventory.http_fastapi import FastapiHttpExtractor
from irminsul.inventory.mcp import McpToolExtractor

_TEMPLATE_RE = re.compile(r"\{(\d+)(?:\|(upper|lower))?(?:\?([^}]*))?\}")


def render_identity(template: str, match: re.Match[str]) -> str | None:
    """Fill `{N}`, `{N|upper}`, and `{N?default}` from a match; None when a group is empty."""

    def sub(m: re.Match[str]) -> str:
        index = int(m.group(1))
        value = match.group(index) if index <= (match.re.groups or 0) else None
        if value is None:
            if m.group(3) is None:
                raise _MissingGroup
            value = m.group(3)
        if m.group(2) == "upper":
            value = value.upper()
        elif m.group(2) == "lower":
            value = value.lower()
        return value

    try:
        return _TEMPLATE_RE.sub(sub, template)
    except _MissingGroup:
        return None


class _MissingGroup(Exception):
    pass


@dataclass(frozen=True)
class PackRule:
    kind: str
    globs: tuple[str, ...]
    pattern: re.Pattern[str]
    identity: str = "{1}"
    guard: re.Pattern[str] | None = None


@dataclass(frozen=True)
class Pack:
    name: str
    extractors: tuple[Extractor, ...] = ()
    rules: tuple[PackRule, ...] = ()


@dataclass(frozen=True)
class KindCapabilities:
    mention_patterns: tuple[re.Pattern[str], ...] = ()
    prose_named: bool = False
    command_path: bool = False


def _rule(
    kind: str, globs: str, pattern: str, identity: str = "{1}", guard: str | None = None
) -> PackRule:
    return PackRule(
        kind=kind,
        globs=tuple(globs.split()),
        pattern=re.compile(pattern),
        identity=identity,
        guard=re.compile(guard, re.MULTILINE) if guard else None,
    )


_PY = "*.py"
_JS = "*.js *.mjs *.cjs *.ts *.mts *.cts"

PACKS: dict[str, Pack] = {
    pack.name: pack
    for pack in (
        Pack("typer", extractors=(CliTyperExtractor(), CliOptionsExtractor())),
        Pack("fastapi", extractors=(FastapiHttpExtractor(),)),
        Pack("mcp-python", extractors=(McpToolExtractor(),)),
        Pack(
            "click",
            rules=(
                _rule(
                    "cli",
                    _PY,
                    r"@\w+\.(?:command|group)\(\s*(?:name\s*=\s*)?[\"']([\w-]+)[\"']",
                    guard=r"^\s*(?:import click|from click import)",
                ),
                _rule(
                    "cli-options",
                    _PY,
                    r"click\.option\(.*?[\"'](--[a-z][\w-]*)[\"']",
                    guard=r"^\s*(?:import click|from click import)",
                ),
            ),
        ),
        Pack(
            "argparse",
            rules=(
                _rule(
                    "cli",
                    _PY,
                    r"add_parser\(\s*[\"']([\w-]+)[\"']",
                    guard=r"^\s*(?:import argparse|from argparse import)",
                ),
                _rule(
                    "cli-options",
                    _PY,
                    r"add_argument\(.*?[\"'](--[a-z][\w-]*)[\"']",
                    guard=r"^\s*(?:import argparse|from argparse import)",
                ),
            ),
        ),
        Pack(
            "flask",
            rules=(
                _rule(
                    "http",
                    _PY,
                    r"@\w+\.route\(\s*[\"']([^\"']+)[\"'](?:[^)]*methods\s*=\s*\[\s*[\"'](\w+)[\"'])?",
                    "{2|upper?GET} {1}",
                    guard=r"^\s*(?:import flask|from flask import)",
                ),
            ),
        ),
        Pack(
            "cobra",
            rules=(
                _rule("cli", "*.go", r"\bUse:\s*\"([\w-]+)", guard=r"github\.com/spf13/cobra"),
                _rule(
                    "cli-options",
                    "*.go",
                    r"Flags\(\)\.\w+\(\s*(?:&[\w.\[\]]+\s*,\s*)?\"([a-z][\w-]*)\"",
                    "--{1}",
                    guard=r"github\.com/spf13/cobra",
                ),
            ),
        ),
        Pack(
            "clap",
            rules=(
                _rule(
                    "cli",
                    "*.rs",
                    r"\.subcommand\(\s*Command::new\(\s*\"([\w-]+)\"",
                    guard=r"\bclap\b",
                ),
                _rule(
                    "cli-options",
                    "*.rs",
                    r"\.long\(\s*\"([a-z][\w-]*)\"\s*\)",
                    "--{1}",
                    guard=r"\bclap\b",
                ),
                _rule(
                    "cli-options",
                    "*.rs",
                    r"\blong\s*=\s*\"([a-z][\w-]*)\"",
                    "--{1}",
                    guard=r"\bclap\b",
                ),
            ),
        ),
        Pack(
            "commander",
            rules=(
                _rule("cli", _JS, r"\.command\(\s*[\"'`]([\w-]+)", guard=r"[\"']commander[\"']"),
                _rule(
                    "cli-options",
                    _JS,
                    r"\.option\(\s*[\"'`](?:-\w,\s*)?(--[a-z][\w-]*)",
                    guard=r"[\"']commander[\"']",
                ),
            ),
        ),
        Pack(
            "express",
            rules=(
                _rule(
                    "http",
                    _JS,
                    r"\b\w+\.(get|post|put|patch|delete)\(\s*[\"'`](/[^\"'`]*)",
                    "{1|upper} {2}",
                    guard=r"[\"']express[\"']",
                ),
            ),
        ),
    )
}

CORE_EXTRACTORS: tuple[Extractor, ...] = (TypeScriptExportsExtractor(), EnvVarsExtractor())

BUILTIN_CAPABILITIES: dict[str, KindCapabilities] = {
    "cli": KindCapabilities(command_path=True),
    "cli-options": KindCapabilities(
        mention_patterns=(re.compile(r"--[a-z][a-z0-9-]*"),), prose_named=True
    ),
    "mcp": KindCapabilities(prose_named=True),
}


def enabled_packs(config: IrminsulConfig) -> list[Pack]:
    names = config.frameworks.enabled
    if names is None:
        return list(PACKS.values())
    return [PACKS[name] for name in names if name in PACKS]


@dataclass
class _Source:
    extractors: list[Extractor] = field(default_factory=list)
    rules: list[PackRule] = field(default_factory=list)


def _sources(config: IrminsulConfig) -> dict[str, _Source]:
    by_kind: dict[str, _Source] = {}
    for extractor in CORE_EXTRACTORS:
        by_kind.setdefault(extractor.kind, _Source()).extractors.append(extractor)
    for pack in enabled_packs(config):
        for extractor in pack.extractors:
            by_kind.setdefault(extractor.kind, _Source()).extractors.append(extractor)
        for rule in pack.rules:
            by_kind.setdefault(rule.kind, _Source()).rules.append(rule)
    for generic in config.checks.inventory_drift.generic:
        by_kind.setdefault(generic.kind, _Source()).rules.append(
            PackRule(
                kind=generic.kind,
                globs=(generic.glob,),
                pattern=re.compile(generic.pattern),
                identity=generic.identity,
            )
        )
    return by_kind


class CompositeExtractor:
    def __init__(self, kind: str, source: _Source) -> None:
        self.kind = kind
        self._source = source

    def extract(
        self, source_files: list[tuple[Path, str]], config: IrminsulConfig
    ) -> list[SurfaceItem]:
        items: list[SurfaceItem] = []
        for extractor in self._source.extractors:
            items.extend(extractor.extract(source_files, config))
        for rule in self._source.rules:
            items.extend(_extract_rule(rule, source_files))
        return dedupe(items)


def _extract_rule(rule: PackRule, source_files: list[tuple[Path, str]]) -> list[SurfaceItem]:
    spec = GitIgnoreSpec.from_lines(list(rule.globs))
    items: list[SurfaceItem] = []
    for abs_path, display in source_files:
        if not spec.match_file(display):
            continue
        try:
            text = abs_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if rule.guard is not None and not rule.guard.search(text):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in rule.pattern.finditer(line):
                identity = render_identity(rule.identity, match)
                if identity:
                    items.append(SurfaceItem(identity=identity, display=display, line=lineno))
    return items


def get_extractor(kind: str, config: IrminsulConfig) -> Extractor | None:
    source = _sources(config).get(kind)
    if source is None:
        return None
    return CompositeExtractor(kind, source)


def available_kinds(config: IrminsulConfig) -> list[str]:
    return sorted(_sources(config))


def kind_capabilities(kind: str, config: IrminsulConfig) -> KindCapabilities:
    builtin = BUILTIN_CAPABILITIES.get(kind, KindCapabilities())
    patterns = list(builtin.mention_patterns)
    prose_named = builtin.prose_named
    for generic in config.checks.inventory_drift.generic:
        if generic.kind != kind:
            continue
        if generic.mention_pattern:
            patterns.append(re.compile(generic.mention_pattern))
        prose_named = prose_named or generic.prose_named
    return KindCapabilities(
        mention_patterns=tuple(patterns),
        prose_named=prose_named,
        command_path=builtin.command_path,
    )
