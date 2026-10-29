"""Indexes layered on top of `DocGraph`.

`build_graph` builds these once, at its end:

- `inbound_strong` — for each doc id, the set of doc ids whose frontmatter names it through
  `depends_on`, `implements` or `resolved_by`: an RFC whose `resolved_by` names a decision
  record is inbound to that record.
- `inbound_weak` — for each doc id, the set of doc ids whose body contains a
  markdown link resolving to that doc.
- `headings` — for each doc id, the ordered list of headings in its body.
- `requirements` — for each doc with a `## Requirements` section, the parsed
  requirement/scenario structure. One parser, one representation: every reader
  takes it from this index instead of running its own regexes over the body.
- `tasks` — for each doc with a `## Tasks` section, the static implementation
  task list: ordinary list items with stable ids and requirement or
  component references, never mutable status records.

`DocNode.links` lives on the node rather than the graph: a body's links, read once from its
tokens by `links_of`. Every reader of a link takes its target, anchor and line from there
and resolves it with `resolve_href`.

Builders are pure: they take only the inputs they read and return new dicts. A body's
markdown comes from `DocNode.tokens`, parsed once per node through `parse_markdown`.
`docgraph.build_graph` calls them; checks consume the populated fields.
"""

from __future__ import annotations

import html
import posixpath
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from markdown_it import MarkdownIt
from markdown_it.token import Token

from irminsul.docgraph import DocNode, declared_path
from irminsul.fences import FenceTracker


@dataclass(frozen=True)
class Heading:
    level: int
    text: str
    slug: str
    """What the heading's text slugs to, which is how a section is matched by name."""
    line: int
    anchor: str
    """The fragment that links to this heading: `slug`, numbered when an earlier heading of
    the body has the same slug."""


def slugify(text: str) -> str:
    """The slug GitHub gives a heading's text: lower case, punctuation dropped, each space a hyphen.

    Nothing collapses or trims, so `Scope & Limitations` is `scope--limitations`: the `&` goes
    and the two spaces around it stay. Letters, digits, combining marks, `_` and `-` are kept.
    """
    return "".join(
        "-" if char == " " else char
        for char in text.strip().lower()
        if char in " -" or char.isalnum() or unicodedata.category(char) in _KEPT_CATEGORIES
    )


_KEPT_CATEGORIES = frozenset({"Pc", "Mn", "Mc", "Me"})


def build_inbound_strong(nodes: dict[str, DocNode]) -> dict[str, set[str]]:
    by_path = {node.path: node for node in nodes.values()}
    inbound: dict[str, set[str]] = {doc_id: set() for doc_id in nodes}
    for src_id, node in nodes.items():
        for target_id in node.frontmatter.depends_on:
            inbound.setdefault(target_id, set()).add(src_id)
        for target_id in node.frontmatter.implements:
            inbound.setdefault(target_id, set()).add(src_id)
        if node.frontmatter.resolved_by is not None:
            target = by_path.get(declared_path(node.frontmatter.resolved_by))
            if target is not None:
                inbound.setdefault(target.id, set()).add(src_id)
    return inbound


_MARKDOWN = MarkdownIt("commonmark")


def parse_markdown(text: str) -> list[Token]:
    """CommonMark tokens of `text`; every reader of a doc body parses through here."""
    return _MARKDOWN.parse(text)


@dataclass(frozen=True)
class Link:
    """One link in a body, as the tokens carry it."""

    href: str
    line: int
    """1-based, in the body it was read from."""
    target: str
    """The path part of `href` as written; empty for a link within the same file."""
    anchor: str | None
    """The fragment after `#`; None when there is none or it is empty."""


_SKIP_SCHEMES = {"http", "https", "mailto", "tel", "ftp", "ftps", "data"}
_TAG_HREF_RE = re.compile(
    r"""<a\s[^>]*?(?<![\w-])href\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))""",
    re.IGNORECASE,
)


def is_external(href: str) -> bool:
    """Return True for absolute URLs we don't validate (http, mailto, etc.)."""
    if not href:
        return True
    return urlparse(href).scheme.lower() in _SKIP_SCHEMES


def split_href(href: str) -> tuple[str, str | None]:
    """The path part of `href` and its anchor, which is None when empty or absent."""
    target, _, anchor = href.partition("#")
    return target, unquote(anchor) or None


def resolve_href(source: str, target: str, root: str | None = "") -> Path | None:
    """Where the path `target`, written in the file at `source`, points, or None.

    The rules are GitHub's: percent-escapes are decoded, a leading `/` starts at `root`,
    and `..` cannot climb above it: such a target answers None rather than being clamped
    to the root. `source` and `root` are spelled relative to the same base, which is the
    repository root for a doc; a file in a sibling repository passes the root of its own,
    such as `../code`. A `root` of None sets no limit.
    """
    decoded = unquote(target)
    if decoded.startswith("/"):
        joined = posixpath.join(root or "", decoded.lstrip("/"))
    else:
        joined = posixpath.join(posixpath.dirname(source), decoded)
    resolved = posixpath.normpath(joined)
    if root is not None:
        base = posixpath.normpath(root) if root else "."
        inside = (
            resolved != ".." and not resolved.startswith("../")
            if base == "."
            else resolved == base or resolved.startswith(f"{base}/")
        )
        if not inside:
            return None
    return Path(resolved)


def _tag_links(markup: str, line: int) -> list[Link]:
    out: list[Link] = []
    for match in _TAG_HREF_RE.finditer(markup):
        group = match.lastindex or 1
        href = html.unescape(match.group(group))
        target, anchor = split_href(href)
        out.append(
            Link(
                href=href,
                line=line + markup.count("\n", 0, match.start(group)),
                target=target,
                anchor=anchor,
            )
        )
    return out


def links_of(tokens: list[Token]) -> list[Link]:
    """Every link in a parsed body, the `href` of an `<a>` tag among them.

    Inline tokens carry only the line their block starts on, so the line of a link is that
    plus the line breaks that precede it inside the block. A line break inside a code span,
    where the parser has already turned it into a space, or inside an image's title is not
    counted, so a link after one reads a line early.
    """
    out: list[Link] = []
    for token in tokens:
        if token.type != "inline" or not token.children:
            continue
        line = token.map[0] + 1 if token.map else 1
        for child in token.children:
            if child.type in ("softbreak", "hardbreak"):
                line += 1
            elif child.type == "link_open":
                href = child.attrGet("href")
                if isinstance(href, str):
                    target, anchor = split_href(href)
                    out.append(Link(href=href, line=line, target=target, anchor=anchor))
            elif child.type in ("html_inline", "image"):
                if child.type == "html_inline":
                    out.extend(_tag_links(child.content, line))
                line += child.content.count("\n")
    return out


def linked_path(source: str, link: Link, root: str | None = "") -> Path | None:
    """The path a link in the file at `source` points at, or None for an external or same-file one.

    `source` and `root` are spelled as `resolve_href` takes them.
    """
    if not link.target or is_external(link.href):
        return None
    return resolve_href(source, link.target, root)


def linked_node(node: DocNode, link: Link, by_path: dict[Path, DocNode]) -> DocNode | None:
    """The doc a link in `node` points at, or None for an external, same-file or non-doc one."""
    resolved = linked_path(node.path.as_posix(), link)
    return None if resolved is None else by_path.get(resolved)


def build_inbound_weak(
    nodes: dict[str, DocNode],
    by_path: dict[Path, DocNode],
) -> dict[str, set[str]]:
    inbound: dict[str, set[str]] = {doc_id: set() for doc_id in nodes}
    for src_id, node in nodes.items():
        for link in node.links:
            target = linked_node(node, link, by_path)
            if target is not None and target.id != src_id:
                inbound.setdefault(target.id, set()).add(src_id)
    return inbound


@dataclass(frozen=True)
class Scenario:
    """A `#### Scenario:` block inside a requirement."""

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
    finalization promotes into the owning component doc."""
    has_behavior_keyword: bool
    """Whether the requirement text (outside scenarios) contains SHALL or MUST."""
    scenarios: tuple[Scenario, ...]


def global_requirement_id(rfc_id: str, req_id: str) -> str:
    """`<rfc-id>#<requirement-id>`, the id a requirement keeps once promoted into a claim."""
    return f"{rfc_id}#{req_id}"


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
_REQUIREMENTS_HINT_RE = re.compile(r"^##\s+requirements\b", re.IGNORECASE | re.MULTILINE)


@dataclass(frozen=True)
class SectionBody:
    """The content lines of a `## <slug>` section, with fenced blocks removed."""

    line: int
    lines: tuple[tuple[int, str], ...]
    """`(line number, text)` for every non-fenced line under the heading."""


def extract_section(body: str, slug: str, *, skip_comments: bool = False) -> SectionBody | None:
    """Collect the lines belonging to the `## <slug>` section of a doc body.

    Any heading of level 1 or 2 closes the section, and fenced code blocks are
    dropped, so quoted grammar never contributes headings, ids, or keywords. A repeated
    `## <slug>` heading continues the section. With `skip_comments`, an HTML comment is
    dropped as well, a heading in it included: what a scaffold's example comment shows is
    not declared by the doc.
    """
    fence = FenceTracker()
    section_line: int | None = None
    lines: list[tuple[int, str]] = []
    in_section = False
    in_comment = False

    for lineno, line in enumerate(body.splitlines(), start=1):
        if in_comment:
            in_comment = "-->" not in line
            continue
        if fence.consume(line):
            continue
        if skip_comments and line.lstrip().startswith("<!--"):
            in_comment = "-->" not in line
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
    section = extract_section(body, "requirements", skip_comments=True)
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


@dataclass(frozen=True)
class Task:
    """One `## Tasks` list item: `` - `T1` text (req: id) ``."""

    task_id: str
    line: int
    text: str
    req_ref: str | None
    component_ref: str | None


@dataclass(frozen=True)
class MalformedTask:
    """A `## Tasks` bullet that does not parse as a task.

    Recorded rather than dropped: a task list that silently loses items is
    indistinguishable from a plan that was never written.
    """

    line: int
    text: str
    reason: str
    """missing-id | multiple-references | misplaced-reference | empty-reference"""


@dataclass(frozen=True)
class TasksSection:
    """The parsed `## Tasks` section of one doc."""

    line: int
    tasks: tuple[Task, ...]
    malformed: tuple[MalformedTask, ...]


_TASKS_HINT_RE = re.compile(r"^##\s+tasks\b", re.IGNORECASE | re.MULTILINE)
_TASK_BULLET_RE = re.compile(r"^[-*+]\s+(?P<body>\S.*?)\s*$")
_TASK_ID_RE = re.compile(r"^`(?P<id>[^`]+)`\s*(?P<rest>.*)$")
_TASK_REF_RE = re.compile(r"\((?P<kind>req|component):\s*(?P<value>[^)]*?)\s*\)")


def _parse_task_bullet(body: str, lineno: int) -> Task | MalformedTask:
    id_match = _TASK_ID_RE.match(body)
    if id_match is None:
        return MalformedTask(line=lineno, text=body, reason="missing-id")

    task_id = id_match.group("id").strip()
    rest = id_match.group("rest")
    refs = list(_TASK_REF_RE.finditer(rest))
    if len(refs) > 1:
        return MalformedTask(line=lineno, text=body, reason="multiple-references")
    if not refs:
        return Task(
            task_id=task_id, line=lineno, text=rest.strip(), req_ref=None, component_ref=None
        )

    ref = refs[0]
    if rest[ref.end() :].strip():
        return MalformedTask(line=lineno, text=body, reason="misplaced-reference")
    value = ref.group("value").strip()
    if not value:
        return MalformedTask(line=lineno, text=body, reason="empty-reference")
    is_req = ref.group("kind") == "req"
    return Task(
        task_id=task_id,
        line=lineno,
        text=rest[: ref.start()].strip(),
        req_ref=value if is_req else None,
        component_ref=None if is_req else value,
    )


def parse_tasks(body: str) -> TasksSection | None:
    """Parse the `## Tasks` section of a doc body, if present.

    Returns None when the doc has no section. Bullets that do not match the
    task grammar are kept as `malformed` so the grammar check can report them
    instead of the plan quietly shrinking.
    """
    section = extract_section(body, "tasks", skip_comments=True)
    if section is None:
        return None

    tasks: list[Task] = []
    malformed: list[MalformedTask] = []
    for lineno, line in section.lines:
        bullet = _TASK_BULLET_RE.match(line)
        if bullet is None:
            continue
        parsed = _parse_task_bullet(bullet.group("body"), lineno)
        if isinstance(parsed, Task):
            tasks.append(parsed)
        else:
            malformed.append(parsed)

    return TasksSection(line=section.line, tasks=tuple(tasks), malformed=tuple(malformed))


def build_tasks(nodes: dict[str, DocNode]) -> dict[str, TasksSection]:
    """Parse the `## Tasks` section of every doc that has one."""
    out: dict[str, TasksSection] = {}
    for doc_id, node in nodes.items():
        if not _TASKS_HINT_RE.search(node.body):
            continue
        section = parse_tasks(node.body)
        if section is not None:
            out[doc_id] = section
    return out


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


def _rendered_text(children: list[Token]) -> str:
    """What a reader sees of inline markdown: its text, code and image descriptions, no markup."""
    parts: list[str] = []
    for child in children:
        if child.type in ("text", "code_inline"):
            parts.append(child.content)
        elif child.type in ("softbreak", "hardbreak"):
            parts.append(" ")
        elif child.type == "image":
            parts.append(_rendered_text(child.children or []))
    return "".join(parts)


def headings_of(tokens: list[Token]) -> list[Heading]:
    """Every heading in a parsed body, in reading order.

    A heading's anchor is GitHub's: the slug of the text a reader sees, then `-1`, `-2` and so
    on when the slug (or the numbered form of an earlier one) is already taken in the body.
    """
    out: list[Heading] = []
    taken: dict[str, int] = {}
    for index, token in enumerate(tokens[:-1]):
        # The next inline token holds the heading text.
        if token.type == "heading_open" and tokens[index + 1].type == "inline":
            inline = tokens[index + 1]
            level = int(token.tag[1:]) if token.tag.startswith("h") else 0
            line = (token.map[0] + 1) if token.map else 0
            slug = slugify(_rendered_text(inline.children or []))
            anchor = slug
            while anchor in taken:
                taken[slug] += 1
                anchor = f"{slug}-{taken[slug]}"
            taken[anchor] = 0
            out.append(
                Heading(level=level, text=inline.content, slug=slug, line=line, anchor=anchor)
            )
    return out


def build_headings(nodes: dict[str, DocNode]) -> dict[str, list[Heading]]:
    return {doc_id: headings_of(node.tokens) for doc_id, node in nodes.items()}


def section_lines(
    body: str, headings: list[Heading], accepts: Callable[[Heading], bool]
) -> list[str] | None:
    """The body lines under the first heading `accepts` takes, or None when none is.

    The section runs to the next heading of the same or a higher level, whatever the
    markers around it, so a line that only looks like a heading inside a fence or a comment
    does not end it. Fences and comments stay in the lines.
    """
    lines = body.splitlines()
    for index, heading in enumerate(headings):
        if accepts(heading):
            end = next(
                (h.line - 1 for h in headings[index + 1 :] if h.level <= heading.level),
                len(lines),
            )
            return lines[heading.line : end]
    return None
