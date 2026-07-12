"""Lazy indexes layered on top of `DocGraph`.

Indexes are built once at the end of `build_graph`:

- `inbound_strong` — for each doc id, the set of doc ids whose `depends_on`,
  `implements`, or implicit `resolved_by` relationship points at it. Used by
  orphans, supersession reciprocity, and refs.
- `inbound_weak` — for each doc id, the set of doc ids whose body contains a
  markdown link resolving to that doc. Used by orphans.
- `headings` — for each doc id, the ordered list of headings in its body. Used
  by anchor validation.
- `requirements` — for each doc with a `## Requirements` section, the parsed
  requirement/scenario structure (RFC 0030). One parser, one representation:
  the grammar check, transitions, and change reports all consume this index
  instead of running their own regexes over the body.

Builders are pure: they take only the inputs they read and return new dicts.
`docgraph.build_graph` calls them; checks consume the populated fields.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from markdown_it import MarkdownIt

from irminsul.docgraph import DocNode


@dataclass(frozen=True)
class Heading:
    level: int
    text: str
    slug: str
    line: int


_NON_WORD = re.compile(r"[^\w\s-]")
_WHITESPACE = re.compile(r"[\s]+")
_DASHES = re.compile(r"-+")


def slugify(text: str) -> str:
    """A small, dependency-free slug close to GitHub/MkDocs Material output."""
    s = text.strip().lower()
    s = _NON_WORD.sub("", s)
    s = _WHITESPACE.sub("-", s)
    s = _DASHES.sub("-", s)
    return s.strip("-")


def build_inbound_strong(nodes: dict[str, DocNode]) -> dict[str, set[str]]:
    by_path = {node.path: node for node in nodes.values()}
    inbound: dict[str, set[str]] = {doc_id: set() for doc_id in nodes}
    for src_id, node in nodes.items():
        for target_id in node.frontmatter.depends_on:
            inbound.setdefault(target_id, set()).add(src_id)
        for target_id in node.frontmatter.implements:
            inbound.setdefault(target_id, set()).add(src_id)
        if node.frontmatter.resolved_by is not None:
            target_path = Path(PurePosixPath(node.frontmatter.resolved_by))
            target = by_path.get(target_path)
            if target is not None:
                inbound.setdefault(src_id, set()).add(target.id)
    return inbound


def _resolve_link_to_doc_id(
    src_node: DocNode,
    href: str,
    by_path: dict[Path, DocNode],
) -> str | None:
    """If `href` is a relative path that resolves to a known doc, return that
    doc's id. Otherwise None (external URL, anchor-only, or non-doc target)."""
    if not href or href.startswith("#"):
        return None
    if "://" in href or href.startswith(("mailto:", "tel:")):
        return None

    target = href.split("#", 1)[0]
    if not target:
        return None

    doc_parent = PurePosixPath(src_node.path.as_posix()).parent
    raw = doc_parent / target
    parts: list[str] = []
    for part in raw.parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    resolved = Path(*parts)
    return by_path[resolved].id if resolved in by_path else None


def build_inbound_weak(
    nodes: dict[str, DocNode],
    by_path: dict[Path, DocNode],
    md: MarkdownIt,
) -> dict[str, set[str]]:
    inbound: dict[str, set[str]] = {doc_id: set() for doc_id in nodes}
    for src_id, node in nodes.items():
        tokens = md.parse(node.body)
        for token in tokens:
            if token.type != "inline" or not token.children:
                continue
            for child in token.children:
                if child.type != "link_open":
                    continue
                href = child.attrGet("href")
                if not isinstance(href, str):
                    continue
                target_id = _resolve_link_to_doc_id(node, href, by_path)
                if target_id is None or target_id == src_id:
                    continue
                inbound.setdefault(target_id, set()).add(src_id)
    return inbound


@dataclass(frozen=True)
class Scenario:
    """A `#### Scenario:` block inside a requirement (RFC 0030)."""

    name: str
    line: int
    has_when: bool
    has_then: bool


@dataclass(frozen=True)
class Requirement:
    """A `### Requirement:` block inside a `## Requirements` section."""

    title: str
    line: int
    req_id: str | None
    provenance: str | None
    has_behavior_keyword: bool
    """Whether the requirement text (outside scenarios) contains SHALL or MUST."""
    scenarios: tuple[Scenario, ...]


@dataclass(frozen=True)
class RequirementsSection:
    """The parsed `## Requirements` section of one doc."""

    line: int
    disposition: str | None
    """The explicit no-new-behavior sentence, when the section declares one."""
    requirements: tuple[Requirement, ...]


class _ScenarioDraft:
    def __init__(self, name: str, line: int) -> None:
        self.name = name
        self.line = line
        self.has_when = False
        self.has_then = False

    def build(self) -> Scenario:
        return Scenario(
            name=self.name, line=self.line, has_when=self.has_when, has_then=self.has_then
        )


class _RequirementDraft:
    def __init__(self, title: str, line: int) -> None:
        self.title = title
        self.line = line
        self.req_id: str | None = None
        self.provenance: str | None = None
        self.text_lines: list[str] = []
        self.scenarios: list[Scenario] = []

    def build(self) -> Requirement:
        return Requirement(
            title=self.title,
            line=self.line,
            req_id=self.req_id,
            provenance=self.provenance,
            has_behavior_keyword=bool(_BEHAVIOR_RE.search("\n".join(self.text_lines))),
            scenarios=tuple(self.scenarios),
        )


_SECTION_HEADING_RE = re.compile(r"^(?P<hashes>#{1,2})\s+(?P<title>.+?)\s*$")
_REQUIREMENT_RE = re.compile(r"^###\s+Requirement:\s*(?P<title>.+?)\s*$")
_SCENARIO_RE = re.compile(r"^####\s+Scenario:\s*(?P<name>.+?)\s*$")
_ID_LINE_RE = re.compile(r"^ID:\s*(?P<id>\S+)\s*$")
_PROVENANCE_LINE_RE = re.compile(r"^Provenance:\s*(?P<value>\S+)\s*$")
# `\b` treats `_` as a word character, so `_SHALL_` (underscore emphasis)
# would not match; the lookarounds exclude alphanumerics only.
_BEHAVIOR_RE = re.compile(r"(?<![A-Za-z0-9])(SHALL|MUST)(?![A-Za-z0-9])")
_WHEN_RE = re.compile(r"(?<![A-Za-z0-9])WHEN(?![A-Za-z0-9])")
_THEN_RE = re.compile(r"(?<![A-Za-z0-9])THEN(?![A-Za-z0-9])")
_DISPOSITION_RE = re.compile(r"^no new behavioral requirements\b", re.IGNORECASE)
_FENCE_RE = re.compile(r"^\s*(?P<marker>`{3,}|~{3,})(?P<info>.*)$")
_REQUIREMENTS_HINT_RE = re.compile(r"^##\s+requirements\b", re.IGNORECASE | re.MULTILINE)


class FenceTracker:
    """CommonMark fenced-code-block state, fed one body line at a time.

    A fence closes only on the same character, at least as long as the opening
    marker, and without an info string. So a ````-fenced quote may contain ```
    blocks verbatim, and a stray ``` inside a ~~~ block is content rather than
    a toggle.
    """

    __slots__ = ("_char", "_length")

    def __init__(self) -> None:
        self._char: str | None = None
        self._length = 0

    @property
    def inside(self) -> bool:
        return self._char is not None

    def consume(self, line: str) -> bool:
        """Feed one line; True when it is fence syntax or fenced content."""
        match = _FENCE_RE.match(line)
        if match is None:
            return self.inside

        marker = match.group("marker")
        info = match.group("info")
        if self._char is None:
            if marker[0] == "`" and "`" in info:
                return False
            self._char = marker[0]
            self._length = len(marker)
        elif marker[0] == self._char and len(marker) >= self._length and not info.strip():
            self._char = None
            self._length = 0
        return True


@dataclass(frozen=True)
class SectionBody:
    """The content lines of a `## <slug>` section, with fenced blocks removed."""

    line: int
    lines: tuple[tuple[int, str], ...]
    """`(line number, text)` for every non-fenced line under the heading."""


def extract_section(body: str, slug: str) -> SectionBody | None:
    """Collect the lines belonging to the `## <slug>` section of a doc body.

    Any heading of level 1 or 2 closes the section, and fenced code blocks are
    dropped, so quoted grammar never contributes headings, ids, or keywords.
    """
    fence = FenceTracker()
    section_line: int | None = None
    lines: list[tuple[int, str]] = []
    in_section = False

    for lineno, line in enumerate(body.splitlines(), start=1):
        if fence.consume(line):
            continue
        heading = _SECTION_HEADING_RE.match(line)
        if heading is not None:
            in_section = (
                len(heading.group("hashes")) == 2 and slugify(heading.group("title")) == slug
            )
            if in_section and section_line is None:
                section_line = lineno
            continue
        if in_section:
            lines.append((lineno, line))

    if section_line is None:
        return None
    return SectionBody(line=section_line, lines=tuple(lines))


def parse_requirements(body: str) -> RequirementsSection | None:
    """Parse the `## Requirements` section of a doc body, if present.

    Line-based and fence-aware: fenced code blocks never contribute headings,
    ids, or keywords, so an RFC can *quote* requirement grammar without
    declaring requirements.
    """
    section = extract_section(body, "requirements")
    if section is None:
        return None

    disposition: str | None = None
    requirements: list[Requirement] = []

    current_req: _RequirementDraft | None = None
    current_scenario: _ScenarioDraft | None = None

    def close_scenario() -> None:
        nonlocal current_scenario
        if current_scenario is not None and current_req is not None:
            current_req.scenarios.append(current_scenario.build())
        current_scenario = None

    def close_requirement() -> None:
        nonlocal current_req
        close_scenario()
        if current_req is not None:
            requirements.append(current_req.build())
        current_req = None

    for lineno, line in section.lines:
        req_match = _REQUIREMENT_RE.match(line)
        if req_match is not None:
            close_requirement()
            current_req = _RequirementDraft(req_match.group("title"), lineno)
            continue

        scenario_match = _SCENARIO_RE.match(line)
        if scenario_match is not None:
            close_scenario()
            current_scenario = _ScenarioDraft(scenario_match.group("name"), lineno)
            continue

        # Checked before the requirement/scenario branches consume the line: a
        # disposition appended after the blocks is the contradiction to report.
        if disposition is None and _DISPOSITION_RE.match(line.strip()):
            disposition = line.strip()
            continue

        if current_scenario is not None:
            plain = line.replace("*", "")
            if _WHEN_RE.search(plain):
                current_scenario.has_when = True
            if _THEN_RE.search(plain):
                current_scenario.has_then = True
            continue

        if current_req is not None:
            id_match = _ID_LINE_RE.match(line)
            if id_match is not None and current_req.req_id is None:
                current_req.req_id = id_match.group("id")
                continue
            provenance_match = _PROVENANCE_LINE_RE.match(line)
            if provenance_match is not None and current_req.provenance is None:
                current_req.provenance = provenance_match.group("value")
                continue
            current_req.text_lines.append(line)

    close_requirement()

    return RequirementsSection(
        line=section.line,
        disposition=disposition,
        requirements=tuple(requirements),
    )


def build_requirements(nodes: dict[str, DocNode]) -> dict[str, RequirementsSection]:
    """Parse the `## Requirements` section of every doc that has one."""
    out: dict[str, RequirementsSection] = {}
    for doc_id, node in nodes.items():
        if not _REQUIREMENTS_HINT_RE.search(node.body):
            continue
        section = parse_requirements(node.body)
        if section is not None:
            out[doc_id] = section
    return out


def build_headings(
    nodes: dict[str, DocNode],
    md: MarkdownIt,
) -> dict[str, list[Heading]]:
    headings: dict[str, list[Heading]] = {}
    for doc_id, node in nodes.items():
        h_list: list[Heading] = []
        tokens = md.parse(node.body)
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token.type == "heading_open":
                level = int(token.tag[1:]) if token.tag.startswith("h") else 0
                line = (token.map[0] + 1) if token.map else 0
                # The next inline token holds the heading text.
                if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                    text = tokens[i + 1].content
                    h_list.append(Heading(level=level, text=text, slug=slugify(text), line=line))
            i += 1
        headings[doc_id] = h_list
    return headings
