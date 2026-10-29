"""The one Jinja environment `init`, `seed` and `new` render their templates in."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

_YAML_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}

_TOML_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\f": "\\f",
    "\r": "\\r",
}


def yaml_scalar(value: object) -> str:
    """`value` as a YAML double-quoted scalar.

    Not `tojson`: `json.dumps` escapes non-ASCII as surrogate pairs by default, and YAML
    has no surrogate escape, so an emoji in a title would write frontmatter the parser
    rejects. A YAML file is UTF-8, so the character belongs in it literally; only the
    quote, the backslash and the control characters need escaping — and a newline must,
    or a value carrying one injects whatever keys follow it.
    """
    return '"' + "".join(_YAML_ESCAPES.get(ch, ch) for ch in str(value)) + '"'


def toml_string(value: object) -> str:
    """`value` as a TOML basic string.

    Not `tojson` for the same reason as `yaml_scalar`: TOML has no surrogate escape either,
    so a character outside the Basic Multilingual Plane written as a surrogate pair is a
    file that does not load. Everything but the quote, the backslash and the control
    characters stays literal.
    """
    return '"' + "".join(_toml_char(ch) for ch in str(value)) + '"'


def _toml_char(ch: str) -> str:
    escaped = _TOML_ESCAPES.get(ch)
    if escaped is not None:
        return escaped
    if ord(ch) < 0x20 or ord(ch) == 0x7F:
        return f"\\u{ord(ch):04X}"
    return ch


def environment(templates_dir: Path) -> Environment:
    """A strict environment over `templates_dir`: a variable a template names and the caller
    did not pass is an error, not an empty string."""
    env = Environment(
        loader=FileSystemLoader(templates_dir),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    env.filters["yaml_scalar"] = yaml_scalar
    env.filters["toml_string"] = toml_string
    return env
