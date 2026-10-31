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
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

_DELIMITER_RE = re.compile(r"-{3,}\s*")
_INDENTED_SEQUENCE_RE = re.compile(r"^( *)[^\s#-][^\n]*:[ \t]*\n\1 {2}- ", re.MULTILINE)


def round_trip_yaml(raw_yaml: str) -> YAML:
    """A loader and dumper that writes `raw_yaml` back in its own layout.

    ruamel writes a list flush under its key unless told otherwise, so a doc that indents
    its lists, `key:` then `  - item`, would have every list in its frontmatter moved: a
    one-value edit would read as a rewrite of the whole block.
    """
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    if _INDENTED_SEQUENCE_RE.search(raw_yaml):
        yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


def is_frontmatter_delimiter(line: str) -> bool:
    """Whether a line closes or opens a frontmatter block.

    The rule `read_frontmatter` reads by, so reading and rewriting never disagree about
    where the block ends. An indented `---` is content: it sits inside a block scalar,
    and treating it as the delimiter would truncate the frontmatter and spill the
    remaining keys into the body.
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

    from irminsul.frontmatter import DocFrontmatter

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


def _dump(data: object, body: str, raw_yaml: str) -> str:
    yaml = round_trip_yaml(raw_yaml)
    buf = StringIO()
    yaml.dump(canonicalize_frontmatter(data), buf)
    return f"---\n{buf.getvalue()}---\n{body}"


def set_value(text: str, key: str, value: object) -> str:
    """Set a scalar frontmatter key, preserving body and canonical key order."""
    raw_yaml, body = split_frontmatter(text)
    data = round_trip_yaml(raw_yaml).load(raw_yaml) or {}
    if data.get(key) == value:
        return text
    data[key] = value
    return _dump(data, body, raw_yaml)


def add_to_list(text: str, key: str, value: str) -> str:
    """Append `value` to a list-valued frontmatter key, creating it if absent."""
    raw_yaml, body = split_frontmatter(text)
    data = round_trip_yaml(raw_yaml).load(raw_yaml) or {}
    existing = data.get(key)
    if isinstance(existing, list):
        if value in existing:
            return text
        existing.append(value)
    else:
        data[key] = [value]
    return _dump(data, body, raw_yaml)


def remove_inventory_item(text: str, kind: str, item: str) -> str:
    """Drop `item` from the first `inventory:` entry of `kind` that declares it.

    The entry itself is preserved (even if its `items` list becomes empty); only
    the named item is removed, matching the "curated subset" intent of `inventory:`.
    """
    raw_yaml, body = split_frontmatter(text)
    data = round_trip_yaml(raw_yaml).load(raw_yaml) or {}
    inventory = data.get("inventory")
    if not isinstance(inventory, list):
        return text

    for entry in inventory:
        if not isinstance(entry, dict) or entry.get("kind") != kind:
            continue
        items = entry.get("items")
        if isinstance(items, list) and item in items:
            items.remove(item)
            return _dump(data, body, raw_yaml)

    return text


def _rewrite_claims(text: str, edit: Callable[[dict[str, Any]], bool]) -> str:
    """`text` with `edit` applied to each claim mapping of its frontmatter, which returns
    whether it changed the claim. The delimiters and body come back as they were, and so
    does the whole text when no claim changed or the frontmatter names no claims."""
    raw_yaml, _ = split_frontmatter(text)
    yaml = round_trip_yaml(raw_yaml)
    data = yaml.load(raw_yaml) or {}
    claims = data.get("claims") if isinstance(data, dict) else None
    if not isinstance(claims, list):
        return text
    changed = [edit(claim) for claim in claims if isinstance(claim, dict)]
    if not any(changed):
        return text
    buf = StringIO()
    yaml.dump(data, buf)
    opening = text.splitlines(keepends=True)[0]
    return opening + buf.getvalue() + text[len(opening) + len(raw_yaml) :]


def set_claim_pins(text: str, pins: dict[str, dict[str, str]]) -> str:
    """Set the `pinned` map of each claim `pins` names by id; an empty map removes it.

    Idempotent: when every named claim already holds its map, the input comes back
    unchanged. Keys are not reordered, so a re-pin changes only the pin lines.
    """

    def apply(claim: dict[str, Any]) -> bool:
        if claim.get("id") not in pins:
            return False
        wanted = pins[claim["id"]]
        if dict(claim.get("pinned") or {}) == wanted:
            return False
        if wanted:
            claim["pinned"] = wanted
        else:
            claim.pop("pinned", None)
        return True

    return _rewrite_claims(text, apply)


def strip_claim_pins(text: str) -> str:
    """`text` with the `pinned` map of every claim removed, which is how a doc's words are
    compared without its pins. Text with no frontmatter, or whose YAML does not parse,
    comes back unchanged, since a body fragment has none to strip."""

    def drop(claim: dict[str, Any]) -> bool:
        if "pinned" not in claim:
            return False
        del claim["pinned"]
        return True

    try:
        return _rewrite_claims(text, drop)
    except (ValueError, YAMLError):
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
