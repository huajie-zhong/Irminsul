"""Parts of a file, found by name without guessing.

An anchor may name one part of a file as `path#part`, and its pin then hashes that part
alone. A part is the lines between a pair of markers where the file has them, written
`irminsul:part <name>` and `irminsul:end <name>` in comments of the file, and otherwise what
the file's type lets a name mean: a definition its language's reader
finds, a heading's section in Markdown, a key in TOML, YAML or JSON. A name that is absent
or ambiguous does not resolve, and nothing searches the text for it; a file of a type with
no finder has parts only through markers.

Text in, text out: a finder is given a file's text, so a revision read from git is found the
same way, and it returns the text a pin hashes.
"""

from __future__ import annotations

import datetime
import json
import re
import textwrap
import tomllib
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from ruamel.yaml.error import YAMLError

from irminsul.docgraph_index import body_lines, headings_of, parse_markdown, section_end
from irminsul.fences import FenceTracker, mask_code_spans
from irminsul.frontmatter import safe_yaml
from irminsul.frontmatter_edit import split_frontmatter
from irminsul.languages.reader import CodeReading, unmarked

_MARKER_RE = re.compile(r"(?<![\w$])irminsul:(?P<kind>part|end)[ \t]+(?P<name>\S+)")
_COMMENT_END_RE = re.compile(r"(?:-->|\*/|#\})$")
_SEGMENT_RE = re.compile(r'"([^"]*)"|([^."]+)')
_MARKDOWN = (".md",)
_KEYED = (".toml", ".yaml", ".yml", ".json")

Written = Callable[[str], "str | None"]
"""The text a pin hashes for a whole text of the file's type, or None when that type's
reader cannot read it: how a marked region and a heading's section are hashed, since each is
hashed the way a whole file of its type is."""


@dataclass(frozen=True)
class Part:
    status: Literal["ok", "missing", "unreadable", "unsupported"]
    """`missing`: the file's finder knows no such name, or the name is ambiguous.
    `unreadable`: the file did not parse whole, so the name may be in what was not read.
    `unsupported`: no finder reads this type of file and no marker names the part."""
    text: str | None = None
    """What a pin hashes, when the part resolves."""
    known: tuple[str, ...] = ()
    """The names the finder knows in the file, of which the closest can be offered."""
    why: str | None = None
    """What kept a name the file holds from resolving, such as two headings that share it."""


def split_part(spelling: str) -> tuple[str, str | None]:
    """The path and the part an entry `path#part` names, split at its first `#`; the part
    is None for a bare path. Whatever reads only where the entry leads, as its existence
    and its owner are read, reads the path."""
    path, marked, part = spelling.partition("#")
    return path, part if marked else None


def find_part(
    suffix: str, text: str, name: str, reading: CodeReading | None, written: Written
) -> Part:
    """The part `name` of a file with the suffix `suffix` that holds `text`.

    `reading` is the file as its language's reader reads it, None where no reader does. A
    pair of markers wins over a definition, a heading or a key of the same name, because it
    is the author saying where the part is. A byte order mark at the start of the text is
    no part of its first line, a heading or a key included.
    """
    text = unmarked(text)
    marked = _marked(suffix, text, name)
    if marked is not None:
        if marked.status != "ok" or marked.text is None:
            return marked
        region = written(textwrap.dedent(marked.text))
        if region is None:
            return Part("missing", why="its marked lines do not parse on their own")
        return Part("ok", region)
    if reading is not None:
        return _defined(reading, name)
    if suffix in _MARKDOWN:
        return _section(text, name, written)
    if suffix in _KEYED:
        return _keyed(suffix, text, name)
    return Part("unsupported", known=tuple(markers(suffix, text)))


def markers(suffix: str, text: str) -> dict[str, int]:
    """Each name an `irminsul:part` marker opens in a file of this suffix, with the line of
    the first marker that opens it, in the order they open."""
    opened: dict[str, int] = {}
    for kind, name, index in _markers(suffix, unmarked(text)):
        if kind == "part":
            opened.setdefault(name, index + 1)
    return opened


def _markers(suffix: str, text: str) -> list[tuple[str, str, int]]:
    """Each marker as its kind, its name and the index of its line. A name is the run of
    characters after the marker's word, without the end of the comment it is written in when
    that touches it, `-->`, `*/` or `#}`. In Markdown a marker in a fenced block or a code
    span is an example, as an anchor marker there is; in any other file a marker is plain
    text wherever it stands.
    """
    found: list[tuple[str, str, int]] = []
    markdown = suffix in _MARKDOWN
    fence = FenceTracker()
    for index, line in enumerate(text.splitlines()):
        if markdown:
            if fence.consume(line):
                continue
            line = mask_code_spans(line)
        for match in _MARKER_RE.finditer(line):
            name = _COMMENT_END_RE.sub("", match["name"])
            if name:
                found.append((match["kind"], name, index))
    return found


def _marked(suffix: str, text: str, name: str) -> Part | None:
    """The lines between the two markers of `name`, as they stand; None when no marker
    names it, and a part that does not resolve when it is marked twice, never closed or
    closed before it opens."""
    found = _markers(suffix, text)
    opens = [index for kind, marked, index in found if kind == "part" and marked == name]
    ends = [index for kind, marked, index in found if kind == "end" and marked == name]
    if not opens and not ends:
        return None
    if len(opens) > 1:
        return Part("missing", why=f"`irminsul:part {name}` marks {len(opens)} places")
    if len(ends) > 1:
        return Part("missing", why=f"`irminsul:end {name}` closes it {len(ends)} times")
    if not opens:
        return Part(
            "missing", why=f"no `irminsul:part {name}` opens what `irminsul:end {name}` closes"
        )
    if not ends or ends[0] <= opens[0]:
        return Part("missing", why=f"`irminsul:part {name}` has no `irminsul:end {name}` after it")
    lines = text.splitlines()
    return Part("ok", "\n".join(lines[opens[0] + 1 : ends[0]]))


def _defined(reading: CodeReading, name: str) -> Part:
    canonical = reading.canonical(name)
    if canonical is not None:
        return Part("ok", canonical)
    known = tuple(found.symbol for found in reading.definitions() if found.reachable)
    return Part("missing" if reading.parsed else "unreadable", known=known)


def _section(text: str, name: str, written: Written) -> Part:
    """The section of the one heading whose slug is `name`: its line and the lines down to
    the next heading of its level or a higher one. The slug is the heading's own, not the
    numbered fragment a link gives the second heading of one text, which moves when a
    heading is added above it."""
    try:
        _, body = split_frontmatter(text)
    except ValueError:
        body = text
    headings = headings_of(parse_markdown(body))
    known = tuple(dict.fromkeys(heading.slug for heading in headings))
    matches = [index for index, heading in enumerate(headings) if heading.slug == name]
    if not matches:
        return Part("missing", known=known)
    if len(matches) > 1:
        return Part("missing", known=known, why=f"{len(matches)} headings share the slug")
    lines = body_lines(body)
    first = headings[matches[0]].line - 1
    return Part(
        "ok", written("\n".join(lines[first : section_end(headings, matches[0], len(lines))]))
    )


def _keyed(suffix: str, text: str, name: str) -> Part:
    """The value at the dotted key path `name`, written as canonical JSON. The path passes
    through mappings only, so a list is hashed whole; a segment that holds a dot is written
    in double quotes. A file its parser rejects, or whose value cannot be written, as one
    that holds itself cannot, is unreadable."""
    try:
        data = _load(suffix, text)
    except (ValueError, YAMLError, RecursionError):
        return Part("unreadable")
    if data is _SEVERAL:
        return Part("missing", why="the file holds several YAML documents")
    segments = _segments(name)
    if segments is None:
        return Part("missing", why="it is not a dotted key path")
    value: Any = data
    walked: list[str] = []
    for segment in segments:
        keys = {_key(key): key for key in value} if isinstance(value, dict) else {}
        known = tuple(_path([*walked, key]) for key in keys)
        if isinstance(value, dict) and len(keys) != len(value):
            return Part("missing", known=known, why="two keys there are written alike")
        if not isinstance(value, dict):
            holder = f"`{_path(walked)}`" if walked else "the file's top level"
            return Part("missing", why=f"{holder} holds no keys to pass through")
        if segment not in keys:
            return Part("missing", known=known)
        value = value[keys[segment]]
        walked.append(segment)
    try:
        return Part("ok", json.dumps(_plain(value), sort_keys=True, separators=(",", ":")))
    except _Alike:
        return Part("missing", why="two keys in it are written alike")
    except (ValueError, RecursionError):
        return Part("unreadable")


_SEVERAL = object()


class _Alike(ValueError):
    """Two keys of one table are spelled alike, as the number `1` and the text `"1"` are."""


def _load(suffix: str, text: str) -> object:
    if suffix == ".toml":
        return tomllib.loads(text)
    if suffix == ".json":
        return json.loads(text, object_pairs_hook=_once)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        documents = list(safe_yaml().load_all(text))
    return _SEVERAL if len(documents) > 1 else (documents[0] if documents else {})


def _once(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """A JSON object, refused when it writes a key twice, as TOML and YAML refuse one."""
    table = dict(pairs)
    if len(table) != len(pairs):
        raise ValueError("a key is written twice")
    return table


def _segments(name: str) -> list[str] | None:
    """The keys a dotted path names, or None when it is not written as one."""
    segments: list[str] = []
    position = 0
    while position < len(name):
        match = _SEGMENT_RE.match(name, position)
        if match is None:
            return None
        segments.append(match.group(1) if match.group(1) is not None else match.group(2))
        position = match.end()
        if position < len(name):
            if name[position] != "." or position + 1 == len(name):
                return None
            position += 1
    return segments or None


def _path(segments: list[str]) -> str:
    return ".".join(f'"{segment}"' if "." in segment else segment for segment in segments)


def _key(key: object) -> str:
    """A key as a path spells it: a YAML `true` or `null` key as JSON writes the value."""
    if isinstance(key, str):
        return key
    return json.dumps(key) if key is None or isinstance(key, bool) else str(key)


def _plain(value: object) -> object:
    """`value` as JSON can write it, so two files that say the same thing are written alike
    whichever of the three formats holds them."""
    if isinstance(value, dict):
        table = {_key(key): _plain(item) for key, item in value.items()}
        if len(table) != len(value):
            raise _Alike
        return table
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_plain(item) for item in value), key=repr)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
