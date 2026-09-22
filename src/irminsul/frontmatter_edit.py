"""Round-trip frontmatter editing shared by deterministic fixes.

Every fix that rewrites a doc's YAML frontmatter goes through these helpers so
the contract stays uniform: keys are re-emitted in canonical order, the body is
left byte-for-byte untouched, and the operations are idempotent (a no-op edit
returns the input unchanged so `apply_fixes` skips the write).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from io import StringIO

from ruamel.yaml import YAML

from irminsul.frontmatter import DocFrontmatter

_DELIMITER_RE = re.compile(r"-{3,}\s*")


def _yaml() -> YAML:
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    return yaml


def is_frontmatter_delimiter(line: str) -> bool:
    """Whether a line closes or opens a frontmatter block.

    The same rule the reader uses (`python-frontmatter`'s `^-{3,}\\s*$`), so the two
    never disagree about where the block ends. An indented `---` is content: it sits
    inside a block scalar, and treating it as the delimiter used to truncate the
    frontmatter and spill the remaining keys into the body.
    """
    return _DELIMITER_RE.fullmatch(line.rstrip("\r\n")) is not None


def split_frontmatter(text: str) -> tuple[str, str]:
    """Return (raw_yaml, body). Raises ValueError if the block is malformed."""
    lines = text.splitlines(keepends=True)
    if not lines or not is_frontmatter_delimiter(lines[0]):
        raise ValueError("missing YAML frontmatter block")

    for index, line in enumerate(lines[1:], start=1):
        if is_frontmatter_delimiter(line):
            return "".join(lines[1:index]), "".join(lines[index + 1 :])

    raise ValueError("missing closing YAML frontmatter delimiter")


def canonicalize_frontmatter(data: object) -> object:
    if not isinstance(data, dict):
        return data

    canonical = tuple(DocFrontmatter.model_fields)
    if hasattr(data, "move_to_end"):
        # Reorder in place: copying into a plain dict would drop the comments
        # ruamel attaches to the mapping, silently deleting them from the file.
        for key in reversed(canonical):
            if key in data:
                data.move_to_end(key, last=False)
        return data

    ordered: dict[object, object] = {}
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
    the named item is removed, matching the "curated subset" intent of `inventory:`.
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


def setter(key: str, value: object) -> Callable[[str], str]:
    """A `Fix.apply` that sets one frontmatter key."""

    def apply(text: str) -> str:
        return set_value(text, key, value)

    return apply


def list_adder(key: str, value: str) -> Callable[[str], str]:
    """A `Fix.apply` that adds one value to a frontmatter list."""

    def apply(text: str) -> str:
        return add_to_list(text, key, value)

    return apply
