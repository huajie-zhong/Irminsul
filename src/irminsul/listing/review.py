"""`irminsul list review` — assertions that state current truth, paired with the code they name."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import typer

from irminsul.checks.code_spans import is_live_doc
from irminsul.code_references import CodeResolver, Reference
from irminsul.config import IrminsulConfig, docs_root_prefix, find_config, in_layer, load
from irminsul.docgraph import DocGraph, DocNode, build_graph, guidance_files
from irminsul.frontmatter_edit import is_frontmatter_delimiter
from irminsul.git.blame import LineTimes

REVIEW_VERSION = 1

_NUMBER = r"(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)"
_MARKERS: dict[str, re.Pattern[str]] = {
    "exit-code": re.compile(
        r"\bexits?\s+(?:with\s+)?(?:code\s+)?(?:\d+|non-?zero|zero)\b|\bexit\s+code\s+\d+",
        re.IGNORECASE,
    ),
    "output-format": re.compile(
        r"\b(?:emits?|prints?|returns?|outputs?)\s+(?:a\s+|an\s+|the\s+)?(?:versioned\s+)?"
        r"(?:json|array|object|envelope|table)\b",
        re.IGNORECASE,
    ),
    "default": re.compile(r"\bby default\b|\bdefaults?\s+to\b", re.IGNORECASE),
    "absolute": re.compile(r"\b(?:always|never|there (?:is|are) no)\b", re.IGNORECASE),
    "count": re.compile(
        rf"\b{_NUMBER}\s+(?:checks|commands|consumers|kinds|fields|options|flags|modes|tools|"
        r"profiles|layers|steps|sidebands|categories|surfaces)\b",
        re.IGNORECASE,
    ),
    "future": re.compile(
        r"\b(?:will|planned|not yet|arrives? with|in the future)\b", re.IGNORECASE
    ),
    "enforcement": re.compile(
        r"\b(?:catch(?:es)?|enforce[sd]?|reject(?:s|ed)?|detect(?:s|ed)?|warns?|fails?)\b",
        re.IGNORECASE,
    ),
    "scope": re.compile(r"\b(?:every|each|only)\b", re.IGNORECASE),
}
_GLOSSARY_META_RE = re.compile(r"^\s*(?:match|forbidden_synonyms|case_sensitive):")
_NEEDS_REFERENCE = frozenset({"enforcement", "future", "scope"})
_FUTURE_WORK_RE = re.compile(r"\b(?:planned|not yet|arrives? with|in the future)\b", re.IGNORECASE)
_ENUMERATION_MIN = 3
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_SPAN_RE = re.compile(r"(`+)(.+?)\1")
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z`\[*(])")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$")
_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
ChangedLines = dict[str, set[int] | None]
"""Changed line numbers by repo-relative path; None means every line of the file."""


@dataclass
class ReviewItem:
    path: str
    line: int
    sentence: str
    markers: list[str]
    references: list[Reference] = field(default_factory=list)
    code_changed_after_doc: bool = False
    unbound: list[str] = field(default_factory=list)


def shipped_draft_evidence(
    resolver: CodeResolver, node: DocNode, foreign: frozenset[str] = frozenset()
) -> list[str] | None:
    """Live identities a draft names, or None when it names something absent or too little."""
    from irminsul.checks.code_spans import code_spans

    present: set[str] = set()
    for span in code_spans(node.body):
        text, invoked = resolver.strip_program(span.text)
        for kind, regexes in resolver.mentions.items():
            live = resolver.surfaces.get(kind, {})
            named = [m.group(0) for regex in regexes for m in regex.finditer(text)]
            named = [identity for identity in named if identity not in foreign]
            if any(identity not in live for identity in named):
                return None
            present.update(named)
        refs = resolver.resolve(span.text)
        if invoked:
            commands = [ref for ref in refs if ref.kind in resolver.command_kinds]
            if not commands:
                return None
            present.update(ref.identity for ref in commands)
        for ref in refs:
            if (
                ref.kind not in resolver.mentions
                and ref.kind not in resolver.command_kinds
                and ref.kind not in ("symbol", "path")
            ):
                present.add(ref.identity)
    return sorted(present) if len(present) >= 2 else None


def _sentences(node: DocNode) -> list[tuple[int, int, str]]:
    """(first body line, last body line, sentence) for prose and table rows outside fenced code."""
    return _text_sentences(node.body)


def _text_sentences(text_body: str) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    block: list[tuple[int, str]] = []

    def flush() -> None:
        if not block:
            return
        start = block[0][0]
        text = "\n".join(line for _, line in block)
        offset = 0
        for piece in _SENTENCE_END_RE.split(text):
            index = text.find(piece, offset)
            offset = index + len(piece)
            sentence = " ".join(piece.split())
            if sentence:
                first = start + text.count("\n", 0, index)
                out.append((first, first + piece.count("\n"), sentence))
        block.clear()

    in_fence = False
    for lineno, line in enumerate(text_body.splitlines(), start=1):
        if _FENCE_RE.match(line):
            flush()
            in_fence = not in_fence
            continue
        if not in_fence and line.lstrip().startswith("|"):
            flush()
            if not _TABLE_SEPARATOR_RE.match(line):
                cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
                row = " | ".join(cell for cell in cells if cell)
                if row:
                    out.append((lineno, lineno, row))
            continue
        if in_fence or not line.strip() or line.lstrip().startswith(("#", "<!--")):
            flush()
            continue
        if re.match(r"^\s*(?:[-*+]|\d+[.)])\s+", line):
            flush()
        block.append((lineno, line))
    flush()
    return out


def _review_sentences(
    repo_root: Path, config: IrminsulConfig, graph: DocGraph
) -> list[tuple[str, int, int, str]]:
    """(repo-relative path, first file line, last file line, sentence) for every sentence
    that states current truth.

    That is all prose in live docs, the `## Decision` section of each decision record,
    and the definitions in the glossary.
    """
    out: list[tuple[str, int, int, str]] = []
    for node in sorted(graph.nodes.values(), key=lambda n: n.path.as_posix()):
        if is_live_doc(node, config):
            span = None
        elif in_layer(config, node.path, "decisions"):
            span = _section_span(graph, node, "decision")
            if span is None:
                continue
        else:
            continue
        for body_line, body_end, sentence in _sentences(node):
            if span is None or span[0] < body_line < span[1]:
                out.append(
                    (
                        node.path.as_posix(),
                        node.file_line(body_line),
                        node.file_line(body_end),
                        sentence,
                    )
                )

    manifest = f"{docs_root_prefix(config)}/AGENTS.md"
    for display, absolute in guidance_files(repo_root, config):
        try:
            text = absolute.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if display == manifest:
            text = _without_generated_region(text)
        prose = "\n".join(
            "" if _GLOSSARY_META_RE.match(line) else line for line in text.splitlines()
        )
        out.extend((display, line, end, sentence) for line, end, sentence in _text_sentences(prose))
    return out


def _without_generated_region(text: str) -> str:
    """Blank the manifest's generated table, keeping line numbers."""
    from irminsul.regen.agents_md import GENERATED_END, GENERATED_START

    lines = text.splitlines()
    inside = False
    for index, line in enumerate(lines):
        if GENERATED_START in line:
            inside = True
        if inside:
            lines[index] = ""
        if GENERATED_END in line:
            inside = False
    return "\n".join(lines)


def _section_span(graph: DocGraph, node: DocNode, slug: str) -> tuple[int, int] | None:
    """Body lines strictly inside the section headed `slug`: (heading line, next heading line)."""
    headings = graph.headings.get(node.id, [])
    target = next((h for h in headings if h.slug == slug), None)
    if target is None:
        return None
    end = next(
        (h.line for h in headings if h.line > target.line and h.level <= target.level),
        len(node.body.splitlines()) + 1,
    )
    return target.line, end


def build_review(
    repo_root: Path,
    config: IrminsulConfig,
    graph: DocGraph,
    changed: ChangedLines | None = None,
    base_ref: str = "HEAD",
) -> list[ReviewItem]:
    """Assertion sentences with the code they name.

    With `changed`, only sentences on changed lines are kept, and a marker word counts
    even when the sentence names no code: the edit itself is the reason to look. A
    changed sentence that names code nothing resolves and no anchor in its doc binds is
    kept too, with those names as `unbound`, so the writer binds them. A source file
    whose owning doc the change moved lists the old owner's sentences that name it.
    """
    from irminsul.binding import bound_names, unbound_names

    resolver = CodeResolver(repo_root, config)
    lines = LineTimes()
    items: list[ReviewItem] = []
    bound_by_path: dict[str, set[str]] = {}
    for path, file_line, last_line, sentence in _review_sentences(repo_root, config, graph):
        if changed is not None and not _touches(changed, path, file_line, last_line):
            continue
        markers = [name for name, pattern in _MARKERS.items() if pattern.search(sentence)]
        unbound: list[str] = []
        if changed is not None:
            if path not in bound_by_path:
                try:
                    bound_by_path[path] = bound_names(
                        (repo_root / path).read_text(encoding="utf-8")
                    )
                except (OSError, UnicodeDecodeError):
                    bound_by_path[path] = set()
            spans = [m.group(2) for m in _SPAN_RE.finditer(sentence)]
            unbound = unbound_names(spans, resolver, bound_by_path[path])
            if unbound:
                markers.append("unbound-name")
        references = [
            ref for m in _SPAN_RE.finditer(sentence) for ref in resolver.resolve(m.group(2))
        ]
        references.extend(resolver.resolve_prose(_SPAN_RE.sub(" ", sentence)))
        by_kind: dict[str, set[str]] = {}
        for ref in references:
            if ref.kind not in ("symbol", "path"):
                by_kind.setdefault(ref.kind, set()).add(ref.identity)
        if any(len(identities) >= _ENUMERATION_MIN for identities in by_kind.values()):
            markers.append("enumeration")
        if not references and changed is None:
            # These words are ordinary English too; they mark a claim only when the
            # sentence names something in the code.
            markers = [m for m in markers if m not in _NEEDS_REFERENCE]
            if _FUTURE_WORK_RE.search(sentence) and "future" not in markers:
                markers.append("future")
        if not markers:
            continue
        item = ReviewItem(
            path=path,
            line=file_line,
            sentence=sentence,
            markers=markers,
            references=references,
            unbound=unbound,
        )
        if references:
            item.code_changed_after_doc = resolver.changed_after(
                repo_root / path, references, lines
            )
        items.append(item)
    if changed is not None:
        items.extend(_stale_summaries(repo_root, graph, changed))
        items.extend(_governing_claims_over_changed_code(repo_root, graph, changed))
        items.extend(_moved_file_sentences(graph, changed, base_ref))
        items.extend(_removed_sentences(repo_root, config, changed, base_ref))
    return sorted(
        items,
        key=lambda i: (not i.code_changed_after_doc, not i.references, i.path, i.line),
    )


def _governing_claims_over_changed_code(
    repo_root: Path, graph: DocGraph, changed: ChangedLines
) -> list[ReviewItem]:
    """`governs-evidence` claims whose evidence this change touched.

    The rest of this queue is reached from a changed doc line. These are reached from
    changed *code*, which is the only way a contract whose document nobody opened gets
    re-read: the queue would otherwise be empty for exactly the change that most needs
    a reader.
    """
    from irminsul.context import claim_reviews_for_paths

    out: list[ReviewItem] = []
    for review in claim_reviews_for_paths(graph, changed, after_change=True):
        line = _claim_line(repo_root, review.doc.path, review.claim_id)
        out.append(
            ReviewItem(
                path=review.doc.path,
                line=line,
                sentence=review.claim,
                markers=["governing-claim", *(f"evidence:{path}" for path in review.evidence)],
            )
        )
    return out


def _claim_line(repo_root: Path, doc_path: str, claim_id: str) -> int:
    """The frontmatter line declaring this claim's id, or 1 when it cannot be read."""
    try:
        text = (repo_root / doc_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 1
    for number, line in enumerate(text.splitlines(), start=1):
        if line.strip() in (f"- id: {claim_id}", f"id: {claim_id}"):
            return number
    return 1


def _stale_summaries(repo_root: Path, graph: DocGraph, changed: ChangedLines) -> list[ReviewItem]:
    """A doc's `summary` when the change rewrote its body but not the summary line.

    The summary is what the manifest, `orient`, and MCP show every agent, so a body edit
    that leaves it untouched is worth a second look.
    """
    out: list[ReviewItem] = []
    for node in sorted(graph.nodes.values(), key=lambda n: n.path.as_posix()):
        path = node.path.as_posix()
        summary = node.frontmatter.summary
        lines = changed.get(path) if path in changed else set()
        if not summary or lines is None or not lines:
            continue
        try:
            text = (repo_root / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        text_lines = text.splitlines()
        summary_line = next(
            (n for n, line in enumerate(text_lines, start=1) if line.startswith("summary:")),
            None,
        )
        if summary_line is None:
            continue
        summary_end = summary_line
        while summary_end < len(text_lines) and text_lines[summary_end].startswith((" ", "\t")):
            summary_end += 1
        if any(summary_line <= line <= summary_end for line in lines):
            continue
        if not any(line >= node.body_offset for line in lines):
            continue
        out.append(
            ReviewItem(path=path, line=summary_line, sentence=summary, markers=["stale-summary"])
        )
    return out


def _moved_file_sentences(
    graph: DocGraph, changed: ChangedLines, base_ref: str
) -> list[ReviewItem]:
    """The sentences a file's previous owner still has about a file the change moved away."""
    from irminsul.ownership_moves import file_names, owner_moves

    out: list[ReviewItem] = []
    names_by_doc: dict[str, set[str]] = {}
    for move in owner_moves(graph, set(changed), base_ref):
        for doc in move.before:
            if doc not in move.after:
                names_by_doc.setdefault(doc, set()).update(file_names(move.file))
    for doc, names in sorted(names_by_doc.items()):
        node = graph.by_path.get(Path(doc))
        if node is None:
            continue
        pattern = re.compile(
            "|".join(rf"(?<![\w/.-]){re.escape(name)}(?![\w-])" for name in sorted(names))
        )
        for body_line, _, sentence in _sentences(node):
            if pattern.search(sentence):
                out.append(
                    ReviewItem(
                        path=doc,
                        line=node.file_line(body_line),
                        sentence=sentence,
                        markers=["moved-file"],
                    )
                )
    return out


def _removed_sentences(
    repo_root: Path, config: IrminsulConfig, changed: ChangedLines, base_ref: str
) -> list[ReviewItem]:
    """Assertion sentences the change deleted, which no surviving line can carry.

    Every other item here is built from a line that still exists, so deleting a sentence
    removed it from the queue as well as from the doc — the one edit that makes a doc say
    less was the one edit nothing asked about. Whether the deletion was right is a
    judgment: the code it described may be gone too. So it is queued, not reported as a
    finding.
    """
    from irminsul.git.changes import GitChangesError, file_at_ref

    out: list[ReviewItem] = []
    manifest = f"{docs_root_prefix(config)}/AGENTS.md"
    for path in sorted(changed):
        if not path.endswith(".md"):
            continue
        try:
            before = file_at_ref(repo_root, base_ref, path)
        except GitChangesError:
            continue
        if before is None:
            continue
        try:
            after = (repo_root / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            after = ""
        surviving = _comparable(after)
        body = _body_of(before)
        if path == manifest:
            # The manifest's table is generated; a regenerated row is not a deletion.
            body = _without_generated_region(body)
        for line, _, sentence in _text_sentences(body):
            if not [name for name, pattern in _MARKERS.items() if pattern.search(sentence)]:
                continue
            if _comparable(sentence) in surviving:
                continue
            out.append(
                ReviewItem(path=path, line=line, sentence=sentence, markers=["removed-sentence"])
            )
    return out


def _comparable(text: str) -> str:
    """`text` reduced to what a claim asserts, for telling a deletion from a rewording.

    A markdown link is reduced to a placeholder, so renaming a document — which rewrites
    both the label and the target of every link to it — does not read as deleting every
    sentence that links it. What the queue asks is whether the claim is gone, and the
    claim is the prose around the link rather than the file it points at.
    """
    return " ".join(_LINK_RE.sub("[]", text).split())


def _body_of(text: str) -> str:
    """`text` with its frontmatter blanked, keeping line numbers."""
    lines = text.splitlines()
    if not lines or not is_frontmatter_delimiter(lines[0]):
        return text
    for index, line in enumerate(lines[1:], start=1):
        if is_frontmatter_delimiter(line):
            return "\n".join([""] * (index + 1) + lines[index + 1 :])
    return text


def review_to_json(items: list[ReviewItem], *, show_all: bool = False) -> str:
    shown = items if show_all else [item for item in items if item.code_changed_after_doc]
    return json.dumps(
        {
            "version": REVIEW_VERSION,
            "total": len(items),
            "shown": len(shown),
            "items": [asdict(item) for item in shown],
        },
        indent=2,
    )


def _touches(changed: ChangedLines, path: str, first: int, last: int) -> bool:
    if path not in changed:
        return False
    lines = changed[path]
    return lines is None or any(first <= line <= last for line in lines)


def review_json(
    repo_root: Path,
    config: IrminsulConfig,
    doc: str | None = None,
    *,
    show_all: bool = False,
    changed: ChangedLines | None = None,
    base_ref: str = "HEAD",
) -> str:
    graph = build_graph(repo_root, config)
    items = build_review(repo_root, config, graph, changed, base_ref)
    if changed is not None:
        show_all = True
    if doc is not None:
        wanted = doc.replace("\\", "/")
        items = [item for item in items if item.path == wanted]
    return review_to_json(items, show_all=show_all)


def list_review(
    repo_root: Path,
    *,
    fmt: str,
    doc: str | None,
    show_all: bool = False,
    changed: ChangedLines | None = None,
    base_ref: str = "HEAD",
) -> None:
    config = load(find_config(repo_root))
    report = review_json(
        repo_root, config, doc, show_all=show_all, changed=changed, base_ref=base_ref
    )
    if fmt == "json":
        typer.echo(report)
        return
    data = json.loads(report)
    items = data["items"]
    if changed is not None:
        typer.echo(f"{data['shown']} assertion sentences on changed lines")
    elif not show_all:
        typer.echo(
            f"{data['shown']} of {data['total']} assertion sentences name code changed since "
            "their doc was last committed; pass --all for every sentence"
        )
    for item in items:
        flag = " [code changed after doc]" if item["code_changed_after_doc"] else ""
        typer.echo(f"{item['path']}:{item['line']} ({', '.join(item['markers'])}){flag}")
        typer.echo(f"  {item['sentence']}")
        for ref in item["references"]:
            if ref["line"] and ref["line_end"] and ref["line_end"] != ref["line"]:
                where = f"{ref['defined_at']}:{ref['line']}-{ref['line_end']}"
            elif ref["line"]:
                where = f"{ref['defined_at']}:{ref['line']}"
            else:
                where = ref["defined_at"]
            typer.echo(f"    `{ref['span']}` -> {ref['kind']} {ref['identity']} ({where})")
        for name in item.get("unbound", []):
            typer.echo(
                f"    `{name}` -> unbound; bind it with an anchor (irminsul anchors --suggest)"
            )
    if not items:
        typer.echo("(none)")
