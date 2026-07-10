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
- `tasks` — for each doc with a `## Tasks` section, the static implementation
  task list (RFC 0031): ordinary list items with stable ids and requirement or
  component references, never mutable status records.

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
    text: str
    """The requirement prose outside scenarios — the behavioral invariant that
    finalization promotes into the owning component doc (RFC 0032)."""
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
        text = "\n".join(self.text_lines).strip()
        return Requirement(
            title=self.title,
            line=self.line,
            req_id=self.req_id,
            provenance=self.provenance,
            text=text,
            has_behavior_keyword=bool(_BEHAVIOR_RE.search(text)),
            scenarios=tuple(self.scenarios),
        )


_H2_RE = re.compile(r"^##\s+(?P<title>.+?)\s*$")
_REQUIREMENT_RE = re.compile(r"^###\s+Requirement:\s*(?P<title>.+?)\s*$")
_SCENARIO_RE = re.compile(r"^####\s+Scenario:\s*(?P<name>.+?)\s*$")
_ID_LINE_RE = re.compile(r"^ID:\s*(?P<id>\S+)\s*$")
_PROVENANCE_LINE_RE = re.compile(r"^Provenance:\s*(?P<value>\S+)\s*$")
_BEHAVIOR_RE = re.compile(r"\b(SHALL|MUST)\b")
_DISPOSITION_RE = re.compile(r"^no new behavioral requirements\b", re.IGNORECASE)
_REQ_FENCE_RE = re.compile(r"^\s*(```|~~~)")


def parse_requirements(body: str) -> RequirementsSection | None:
    """Parse the `## Requirements` section of a doc body, if present.

    Line-based and fence-aware: fenced code blocks never contribute headings,
    ids, or keywords, so an RFC can *quote* requirement grammar without
    declaring requirements.
    """
    section_line: int | None = None
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

    in_fence = False
    in_section = False
    for lineno, line in enumerate(body.splitlines(), start=1):
        if _REQ_FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        h2 = _H2_RE.match(line)
        if h2 is not None:
            if in_section:
                close_requirement()
                in_section = False
            if slugify(h2.group("title")) == "requirements":
                in_section = True
                section_line = lineno
            continue
        if not in_section:
            continue

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

        if current_scenario is not None:
            plain = line.replace("*", "")
            if re.search(r"\bWHEN\b", plain):
                current_scenario.has_when = True
            if re.search(r"\bTHEN\b", plain):
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
            continue

        if disposition is None and _DISPOSITION_RE.match(line.strip()):
            disposition = line.strip()

    if in_section:
        close_requirement()

    if section_line is None:
        return None
    return RequirementsSection(
        line=section_line,
        disposition=disposition,
        requirements=tuple(requirements),
    )


@dataclass(frozen=True)
class Task:
    """One `## Tasks` list item (RFC 0031): `` - `T1` text (req: id) ``."""

    task_id: str
    line: int
    text: str
    req_ref: str | None
    component_ref: str | None


_TASK_ITEM_RE = re.compile(
    r"^-\s+`(?P<id>[^`]+)`\s+(?P<text>.*?)"
    r"(?:\s*\((?:req:\s*(?P<req>[^)]+?)|component:\s*(?P<comp>[^)]+?))\s*\))?\s*$"
)


def parse_tasks(body: str) -> tuple[Task, ...] | None:
    """Parse the `## Tasks` section of a doc body, if present.

    Returns None when the doc has no section; an empty tuple means the section
    exists but declares no parseable task items.
    """
    section_found = False
    tasks: list[Task] = []

    in_fence = False
    in_section = False
    for lineno, line in enumerate(body.splitlines(), start=1):
        if _REQ_FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        h2 = _H2_RE.match(line)
        if h2 is not None:
            in_section = slugify(h2.group("title")) == "tasks"
            section_found = section_found or in_section
            continue
        if not in_section:
            continue

        item = _TASK_ITEM_RE.match(line)
        if item is None:
            continue
        req = item.group("req")
        comp = item.group("comp")
        tasks.append(
            Task(
                task_id=item.group("id").strip(),
                line=lineno,
                text=item.group("text").strip(),
                req_ref=req.strip() if req else None,
                component_ref=comp.strip() if comp else None,
            )
        )

    if not section_found:
        return None
    return tuple(tasks)


def build_tasks(nodes: dict[str, DocNode]) -> dict[str, tuple[Task, ...]]:
    """Parse the `## Tasks` section of every doc that has one."""
    out: dict[str, tuple[Task, ...]] = {}
    for doc_id, node in nodes.items():
        if "## Tasks" not in node.body and "## tasks" not in node.body:
            continue
        tasks = parse_tasks(node.body)
        if tasks is not None:
            out[doc_id] = tasks
    return out


def build_requirements(nodes: dict[str, DocNode]) -> dict[str, RequirementsSection]:
    """Parse the `## Requirements` section of every doc that has one."""
    out: dict[str, RequirementsSection] = {}
    for doc_id, node in nodes.items():
        if "## Requirements" not in node.body and "## requirements" not in node.body:
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
