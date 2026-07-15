"""Round-trip frontmatter editing shared by deterministic fixes (RFC 0022).

Every fix that rewrites a doc's YAML frontmatter goes through these helpers so
the contract stays uniform: keys are re-emitted in canonical order, the body is
left byte-for-byte untouched, and the operations are idempotent (a no-op edit
returns the input unchanged so `apply_fixes` skips the write).
"""

from __future__ import annotations

from io import StringIO

from ruamel.yaml import YAML

from irminsul.frontmatter import DocFrontmatter


def _yaml() -> YAML:
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    return yaml


def split_frontmatter(text: str) -> tuple[str, str]:
    """Return (raw_yaml, body). Raises ValueError if the block is malformed."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing YAML frontmatter block")

    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "".join(lines[1:index]), "".join(lines[index + 1 :])

    raise ValueError("missing closing YAML frontmatter delimiter")


def canonicalize_frontmatter(data: object) -> object:
    if not isinstance(data, dict):
        return data

    ordered: dict[object, object] = {}
    canonical = tuple(DocFrontmatter.model_fields)
    for key in canonical:
        if key in data:
            ordered[key] = data[key]
    for key, value in data.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


def _dump(data: object, body: str) -> str:
    yaml = _yaml()
    buf = StringIO()
    yaml.dump(canonicalize_frontmatter(data), buf)
    return f"---\n{buf.getvalue()}---\n{body}"


def set_value(text: str, key: str, value: object) -> str:
    """Set a scalar frontmatter key, preserving body and canonical key order."""
    raw_yaml, body = split_frontmatter(text)
    data = _yaml().load(raw_yaml) or {}
    if data.get(key) == value:
        return text
    data[key] = value
    return _dump(data, body)


def add_to_list(text: str, key: str, value: str) -> str:
    """Append `value` to a list-valued frontmatter key, creating it if absent."""
    raw_yaml, body = split_frontmatter(text)
    data = _yaml().load(raw_yaml) or {}
    existing = data.get(key)
    if isinstance(existing, list):
        if value in existing:
            return text
        existing.append(value)
    else:
        data[key] = [value]
    return _dump(data, body)


def remove_inventory_item(text: str, kind: str, item: str) -> str:
    """Drop `item` from the first `inventory:` entry of `kind` that declares it.

    The entry itself is preserved (even if its `items` list becomes empty); only
    the named item is removed, matching the "curated subset" intent of RFC 0020.
    """
    raw_yaml, body = split_frontmatter(text)
    data = _yaml().load(raw_yaml) or {}
    inventory = data.get("inventory")
    if not isinstance(inventory, list):
        return text

    for entry in inventory:
        if not isinstance(entry, dict) or entry.get("kind") != kind:
            continue
        items = entry.get("items")
        if isinstance(items, list) and item in items:
            items.remove(item)
            return _dump(data, body)

    return text
