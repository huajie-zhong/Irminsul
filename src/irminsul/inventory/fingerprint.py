"""Surface fingerprinting for watched inventories (RFC 0027 freshness).

A watched `inventory:` entry can pin each item's *code shape* so a behavior change
to a still-named item is flagged. The hash reuses the AST-normalized hashing in
`irminsul.anchors` (the same one behind `claim-anchor`), resolved through each
`SurfaceItem.symbol` (`path#qualname`). The `anchors --re-pin` command refreshes the
pins (`set_fingerprints`); the check compares them.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from pathspec import GitIgnoreSpec
from ruamel.yaml import YAML

from irminsul.anchors import Anchor, resolve
from irminsul.config import IrminsulConfig
from irminsul.frontmatter import DocFrontmatter
from irminsul.inventory import get_extractor
from irminsul.inventory.base import SurfaceItem


def extract_surface(
    config: IrminsulConfig,
    source_files: list[tuple[Path, str]],
    kind: str,
    globs: list[str],
) -> dict[str, SurfaceItem]:
    """Live surface for `kind` over `globs`, keyed by identity (empty if no extractor)."""
    extractor = get_extractor(kind, config)
    if extractor is None:
        return {}
    spec = GitIgnoreSpec.from_lines(globs)
    matched = [(p, d) for p, d in source_files if spec.match_file(d)]
    return {item.identity: item for item in extractor.extract(matched, config)}


def current_hash(repo_root: Path, item: SurfaceItem) -> str | None:
    """The item's current AST-normalized hash, or None if its symbol can't resolve."""
    if item.symbol is None:
        return None
    sym_path, _, sym_name = item.symbol.partition("#")
    resolution = resolve(
        repo_root, Anchor(line=0, raw="", path=sym_path, symbol=sym_name or None, pinned=None)
    )
    return resolution.current if resolution.status == "ok" else None


def _split_frontmatter(text: str) -> tuple[str, str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing YAML frontmatter block")
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "".join(lines[1:index]), "".join(lines[index + 1 :])
    raise ValueError("missing closing YAML frontmatter delimiter")


def set_fingerprints(text: str, kind: str, source: str | None, fingerprints: dict[str, str]) -> str:
    """Refresh the `fingerprints:` map of the inventory entry matching kind+source.

    Round-trips frontmatter via ruamel so body and key order are preserved. Keys not
    in `fingerprints` are dropped; an empty map removes the `fingerprints` key.
    Idempotent — an unchanged map returns the input unchanged. The entry must exist.
    """
    yaml = YAML()
    yaml.preserve_quotes = True
    raw_yaml, body = _split_frontmatter(text)
    data = yaml.load(raw_yaml) or {}
    inventory = data.get("inventory")
    if not isinstance(inventory, list):
        return text

    for entry in inventory:
        if not isinstance(entry, dict) or entry.get("kind") != kind:
            continue
        if entry.get("source") != source:
            continue
        if dict(entry.get("fingerprints") or {}) == fingerprints:
            return text
        if fingerprints:
            entry["fingerprints"] = fingerprints
        else:
            entry.pop("fingerprints", None)
        buf = StringIO()
        yaml.dump(data, buf)
        return f"---\n{buf.getvalue()}---\n{body}"

    return text


def repin_node(
    repo_root: Path,
    config: IrminsulConfig,
    source_files: list[tuple[Path, str]],
    frontmatter: DocFrontmatter,
    text: str,
) -> tuple[str, int]:
    """Refresh every existing inventory fingerprint in one doc to its current hash.

    Returns (new_text, number_of_pins_refreshed). Walks each `inventory:` entry that
    declares `fingerprints`, recomputes the live hash for each pinned identity, and
    rewrites the map. Identities that no longer resolve keep their old pin (the check
    reports them).
    """
    refreshed = 0
    new_text = text
    for entry in frontmatter.inventory:
        if not entry.fingerprints:
            continue
        globs = [entry.source] if entry.source else list(frontmatter.describes)
        if not globs:
            continue
        surface = extract_surface(config, source_files, entry.kind, globs)
        updated: dict[str, str] = {}
        for identity, pinned in entry.fingerprints.items():
            item = surface.get(identity)
            fresh = current_hash(repo_root, item) if item is not None else None
            if fresh is None:
                updated[identity] = pinned
                continue
            if fresh != pinned:
                refreshed += 1
            updated[identity] = fresh
        new_text = set_fingerprints(new_text, entry.kind, entry.source, updated)
    return new_text, refreshed
