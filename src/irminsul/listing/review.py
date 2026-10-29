"""`irminsul list review` — sentences to re-read, each paired with the code it names.

Items are selected by facts alone, and each label names the fact: a line the change edited
or deleted, a claim whose evidence it touched, a file it moved to another doc, a summary it
left behind, or, across the whole tree, a sentence that names code. What a sentence means
is the reader's to judge, so no list of words decides what is shown. The output explains
each label it shows from `MARKER_MEANINGS`, the one place a label's meaning is written.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Final

import typer

from irminsul.checks.change_range import after_text
from irminsul.checks.code_spans import is_live_doc
from irminsul.code_references import CodeResolver, Reference
from irminsul.config import IrminsulConfig, docs_root_prefix, in_layer
from irminsul.docgraph import (
    DocGraph,
    DocNode,
    build_graph,
    resolve_doc_target,
)
from irminsul.docgraph_index import extract_section
from irminsul.errors import UserError
from irminsul.fences import FenceTracker
from irminsul.frontmatter_edit import is_frontmatter_delimiter
from irminsul.git.blame import LineTimes
from irminsul.marked_region import MalformedRegion, find_region

REVIEW_VERSION = 1

UNBOUND_ADVICE: Final = "bind it with an anchor (irminsul anchors --suggest)"

MARKER_MEANINGS: Final[dict[str, str]] = {
    "names-code": (
        "a sentence naming code, which is listed under it; [code changed after doc] marks "
        "code that changed after the doc's last commit"
    ),
    "edited": (
        "a sentence this change added or reworded, whatever it says; re-read it against the "
        "code it names, and correct the doc if it is wrong"
    ),
    "unbound-name": (
        f"a code name nothing resolves and no anchor binds; {UNBOUND_ADVICE}, reword the "
        "sentence if it is not this repository's code, leave it if no anchor can reach it"
    ),
    "governing-claim": (
        "a claim whose evidence this change touched. Under governs-evidence ask whether the "
        "code still obeys it (the claim wins; changing it takes a decision record); under "
        "review-on-divergence, which side is now wrong"
    ),
    "evidence": "a file this change touched that the claim cites as its evidence",
    "stale-summary": (
        "a doc's summary: line, left unchanged by an edit to its body; the manifest, orient "
        "and MCP show it to every agent, so check it still fits"
    ),
    "moved-file": (
        "a sentence an old owning doc still has about a file this change moved to another "
        "doc; delete it or rewrite it"
    ),
    "removed-sentence": (
        "a sentence this change deleted. Keep the deletion only if the behaviour is gone or "
        "the sentence repeated a surface query, one file or another doc, with no reason or "
        "gotcha of its own"
    ),
}


class UnknownDocError(UserError, ValueError):
    """`--doc` named no doc atom and no guidance file."""


_GLOSSARY_META_RE = re.compile(r"^\s*(?:match|forbidden_synonyms|case_sensitive):")
_SPAN_RE = re.compile(r"(`+)(.+?)\1")
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z`\[*(])")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$")
_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
_CODE_OR_COMMENT_RE = re.compile(r"(`+).+?\1|<!--.*?-->")
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


def _text_sentences(text_body: str) -> list[tuple[int, int, str]]:
    """(first line, last line, sentence) for each sentence of prose in `text_body`.

    A table row is one sentence, and a fenced block, a heading and a comment line hold none.
    """
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

    fence = FenceTracker()
    for lineno, line in enumerate(text_body.splitlines(), start=1):
        if fence.consume(line):
            flush()
            continue
        if line.lstrip().startswith("|"):
            flush()
            if not _TABLE_SEPARATOR_RE.match(line):
                cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
                row = " | ".join(cell for cell in cells if cell)
                if row:
                    out.append((lineno, lineno, row))
            continue
        if not line.strip() or line.lstrip().startswith(("#", "<!--")):
            flush()
            continue
        if re.match(r"^\s*(?:[-*+]|\d+[.)])\s+", line):
            flush()
        block.append((lineno, line))
    flush()
    return out


def _review_sentences(
    config: IrminsulConfig, graph: DocGraph, read: Callable[[str], str | None]
) -> list[tuple[str, int, int, str]]:
    """(repo-relative path, first file line, last file line, sentence) for every sentence
    the queue reads, from the text `read` returns for each file.

    That is all prose in live docs, the `## Decision` section of each decision record,
    and the guidance files, the glossary's definitions among them.
    """
    guidance = {file.display for file in graph.guidance_files}
    paths = [
        node.path.as_posix()
        for node in sorted(graph.nodes.values(), key=lambda n: n.path.as_posix())
        if is_live_doc(node, config) or in_layer(config, node.path, "decisions")
    ]
    paths.extend(file.display for file in graph.guidance_files)
    out: list[tuple[str, int, int, str]] = []
    for path in paths:
        text = read(path)
        if text is None:
            continue
        out.extend(
            (path, line, end, sentence)
            for line, end, sentence in _text_sentences(_reviewed_text(text, path, guidance, config))
        )
    return out


def _guidance_prose(display: str, text: str, config: IrminsulConfig) -> str:
    """A guidance file's prose: the manifest's generated table and the glossary's metadata
    lines blanked, keeping line numbers."""
    if display == f"{docs_root_prefix(config)}/AGENTS.md":
        text = _without_generated_region(text)
    return "\n".join("" if _GLOSSARY_META_RE.match(line) else line for line in text.splitlines())


def _reviewed_path(path: str, graph: DocGraph, config: IrminsulConfig, guidance: set[str]) -> bool:
    """Whether the queue reads this file's sentences: a guidance file, a live doc, or a
    decision record."""
    if path in guidance:
        return True
    node = graph.by_path.get(Path(path))
    return node is not None and (
        is_live_doc(node, config) or in_layer(config, node.path, "decisions")
    )


def _without_generated_region(text: str) -> str:
    """Blank the manifest's generated table, keeping line numbers. Markers that do not make
    one region blank nothing."""
    from irminsul.regen.agents_md import GENERATED_END, GENERATED_START

    lines = text.splitlines()
    try:
        region = find_region(text, GENERATED_START, GENERATED_END)
    except MalformedRegion:
        region = None
    if region is not None:
        lines[region.start_line : region.end_line + 1] = [""] * (
            region.end_line - region.start_line + 1
        )
    return "\n".join(lines)


def _decision_prose(body: str) -> str:
    """`body` with every line outside its `## Decision` section blanked, keeping line numbers."""
    section = extract_section(body, "decision")
    kept = {number for number, _ in section.lines} if section is not None else set()
    return "\n".join(
        line if number in kept else "" for number, line in enumerate(body.splitlines(), start=1)
    )


def _reviewed_text(text: str, path: str, guidance: set[str], config: IrminsulConfig) -> str:
    """`text` as the queue reads that file, keeping line numbers.

    Frontmatter is blanked, and so is whatever the queue does not read: a decision record
    outside its `## Decision`, and in a guidance file the manifest's generated table and the
    glossary's metadata lines, which a regeneration rewrites without deleting prose.
    """
    body = _body_of(text)
    if path in guidance:
        return _guidance_prose(path, body, config)
    if in_layer(config, Path(path), "decisions"):
        return _decision_prose(body)
    return body


def build_review(
    repo_root: Path,
    config: IrminsulConfig,
    graph: DocGraph,
    changed: ChangedLines | None = None,
    base_ref: str = "HEAD",
    *,
    committed_only: bool = False,
) -> list[ReviewItem]:
    """The sentences to re-read, each with the code it names.

    With `changed`, every sentence on a changed line that its doc did not already say at
    `base_ref` is kept as `edited`, with every sentence the change deleted, each claim whose
    evidence it touched, the sentences an old owner still has about a file it moved, and a
    summary its body edit left behind. A doc the change added has no base, so all its
    sentences are `edited`. An edited sentence naming code that nothing resolves and no
    anchor in its doc binds lists those names as `unbound`, so the writer binds them. Without
    `changed`, every sentence that names code is kept as `names-code`, and marked when that
    code changed after the doc.

    The prose is read from the working tree, or from `HEAD` under `committed_only`.
    """
    from irminsul.binding import bound_names, unbound_names

    head = "HEAD" if committed_only else None

    def read(path: str) -> str | None:
        return after_text(graph.git, repo_root, head, path)

    resolver = CodeResolver(graph.source)
    lines = LineTimes(graph.git)
    guidance = {guidance.display for guidance in graph.guidance_files}
    items: list[ReviewItem] = []
    bound_by_path: dict[str, set[str]] = {}
    base_index: dict[str, str | None] = {}
    for path, file_line, last_line, sentence in _review_sentences(config, graph, read):
        if changed is not None:
            if not _touches(changed, path, file_line, last_line):
                continue
            if path not in base_index:
                base = _prose_at_ref(repo_root, config, graph, base_ref, path, guidance)
                base_index[path] = None if base is None else _prose_index(base)
            index = base_index[path]
            if index is not None and _comparable(sentence) in index:
                continue
        spans = [m.group(2) for m in _SPAN_RE.finditer(sentence)]
        references = [ref for span in spans for ref in resolver.resolve(span)]
        references.extend(resolver.resolve_prose(_SPAN_RE.sub(" ", sentence)))
        unbound: list[str] = []
        if changed is None:
            if not references:
                continue
            markers = ["names-code"]
        else:
            markers = ["edited"]
            if path not in bound_by_path:
                bound_by_path[path] = bound_names(read(path) or "")
            unbound = unbound_names(spans, resolver, bound_by_path[path])
            if unbound:
                markers.append("unbound-name")
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
                graph.git, repo_root / path, references, lines
            )
        items.append(item)
    if changed is not None:
        items.extend(_stale_summaries(graph, changed, read))
        items.extend(_governing_claims_over_changed_code(graph, changed, read))
        items.extend(_moved_file_sentences(graph, changed, base_ref, read))
        items.extend(
            _removed_sentences(repo_root, config, graph, changed, base_ref, guidance, read)
        )
    return sorted(
        items,
        key=lambda i: (not i.code_changed_after_doc, not i.references, i.path, i.line),
    )


def _governing_claims_over_changed_code(
    graph: DocGraph, changed: ChangedLines, read: Callable[[str], str | None]
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
        line = _claim_line(read(review.doc.path), review.claim_id)
        out.append(
            ReviewItem(
                path=review.doc.path,
                line=line,
                sentence=review.claim,
                markers=["governing-claim", *(f"evidence:{path}" for path in review.evidence)],
            )
        )
    return out


def _claim_line(text: str | None, claim_id: str) -> int:
    """The frontmatter line declaring this claim's id, or 1 when the text cannot be read."""
    if text is None:
        return 1
    for number, line in enumerate(text.splitlines(), start=1):
        if line.strip() in (f"- id: {claim_id}", f"id: {claim_id}"):
            return number
    return 1


def _stale_summaries(
    graph: DocGraph, changed: ChangedLines, read: Callable[[str], str | None]
) -> list[ReviewItem]:
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
        text = read(path)
        if text is None:
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
    graph: DocGraph, changed: ChangedLines, base_ref: str, read: Callable[[str], str | None]
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
        text = read(doc)
        if text is None:
            continue
        pattern = re.compile(
            "|".join(rf"(?<![\w/.-]){re.escape(name)}(?![\w-])" for name in sorted(names))
        )
        for line, _, sentence in _text_sentences(_body_of(text)):
            if pattern.search(sentence):
                out.append(
                    ReviewItem(
                        path=doc,
                        line=line,
                        sentence=sentence,
                        markers=["moved-file"],
                    )
                )
    return out


def _removed_sentences(
    repo_root: Path,
    config: IrminsulConfig,
    graph: DocGraph,
    changed: ChangedLines,
    base_ref: str,
    guidance: set[str],
    read: Callable[[str], str | None],
) -> list[ReviewItem]:
    """Sentences the change deleted, which no surviving line can carry.

    Every other item here is built from a line that still exists, so deleting a sentence
    removed it from the queue as well as from the doc — the one edit that makes a doc say
    less was the one edit nothing asked about. Whether the deletion was right is a
    judgment: the code it described may be gone too. So it is queued, not reported as a
    finding. A doc deleted whole is not in `changed`, so its sentences are not queued.
    """
    out: list[ReviewItem] = []
    for path in sorted(changed):
        if not path.endswith(".md") or not _reviewed_path(path, graph, config, guidance):
            continue
        before = _prose_at_ref(repo_root, config, graph, base_ref, path, guidance)
        if before is None:
            continue
        after = read(path) or ""
        surviving = _prose_index(_reviewed_text(after, path, guidance, config))
        for line, _, sentence in _text_sentences(before):
            if _comparable(sentence) in surviving:
                continue
            out.append(
                ReviewItem(path=path, line=line, sentence=sentence, markers=["removed-sentence"])
            )
    return out


def _prose_at_ref(
    repo_root: Path,
    config: IrminsulConfig,
    graph: DocGraph,
    base_ref: str,
    path: str,
    guidance: set[str],
) -> str | None:
    """A file's prose as the queue reads it at `base_ref`, or None when it had none there."""
    from irminsul.git.changes import GitChangesError, file_at_ref

    try:
        text = file_at_ref(graph.git, repo_root, base_ref, path)
    except GitChangesError:
        return None
    if text is None:
        return None
    return _reviewed_text(text, path, guidance, config)


def _prose_index(text: str) -> str:
    """The sentences of `text`, each reduced by `_comparable`, one to a line.

    `_comparable(sentence) in index` asks whether the prose of a sentence is in `text`, which
    is how both a deleted sentence and an edited one are told from one that only moved.
    """
    return "\n".join(_comparable(sentence) for _, _, sentence in _text_sentences(text))


def _comparable(text: str) -> str:
    """`text` reduced to what a claim asserts, for telling a deletion from a rewording.

    A markdown link is reduced to a placeholder, so renaming a document — which rewrites
    both the label and the target of every link to it — does not read as deleting every
    sentence that links it. What the queue asks is whether the claim is gone, and the
    claim is the prose around the link rather than the file it points at. An HTML comment
    after a sentence, such as an anchor's pin, is dropped for the same reason; one quoted
    in a code span is prose and stays.

    Reduce one sentence at a time on both sides: a `[` that never closes pairs with the
    next link's brackets however much text lies between, so a whole file does not reduce
    to the sentences it holds.
    """
    uncommented = _CODE_OR_COMMENT_RE.sub(lambda m: m.group(0) if m.group(1) else "", text)
    return " ".join(_LINK_RE.sub("[]", uncommented).split())


def _body_of(text: str) -> str:
    """`text` with its frontmatter blanked, keeping line numbers."""
    lines = text.splitlines()
    if not lines or not is_frontmatter_delimiter(lines[0]):
        return text
    for index, line in enumerate(lines[1:], start=1):
        if is_frontmatter_delimiter(line):
            return "\n".join([""] * (index + 1) + lines[index + 1 :])
    return text


def marker_meanings(items: list[ReviewItem]) -> dict[str, str]:
    """What each marker the items carry means, in the order `MARKER_MEANINGS` lists them.

    A marker with a payload, such as `evidence:<path>`, is explained by its name. A marker
    with no entry raises `KeyError`, so a new marker cannot be shown without its meaning.
    """
    shown = {marker.split(":", 1)[0] for item in items for marker in item.markers}
    meanings = {name: MARKER_MEANINGS[name] for name in shown}
    return {name: meanings[name] for name in MARKER_MEANINGS if name in meanings}


def review_to_json(items: list[ReviewItem], *, show_all: bool = False) -> str:
    shown = items if show_all else [item for item in items if item.code_changed_after_doc]
    return json.dumps(
        {
            "version": REVIEW_VERSION,
            "total": len(items),
            "shown": len(shown),
            "items": [asdict(item) for item in shown],
            "markers": marker_meanings(shown),
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
    committed_only: bool = False,
) -> str:
    graph = build_graph(repo_root, config, committed_only=committed_only)
    items = build_review(repo_root, config, graph, changed, base_ref, committed_only=committed_only)
    if changed is not None:
        show_all = True
    if doc is not None:
        wanted = resolve_doc_target(graph, doc)
        if wanted is None:
            raise UnknownDocError(f"--doc: no doc with id or path {doc}")
        items = [item for item in items if item.path == wanted]
    return review_to_json(items, show_all=show_all)


def list_review(
    repo_root: Path,
    config: IrminsulConfig,
    *,
    fmt: str,
    doc: str | None,
    show_all: bool = False,
    changed: ChangedLines | None = None,
    base_ref: str = "HEAD",
    committed_only: bool = False,
) -> None:
    report = review_json(
        repo_root,
        config,
        doc,
        show_all=show_all,
        changed=changed,
        base_ref=base_ref,
        committed_only=committed_only,
    )
    if fmt == "json":
        typer.echo(report)
        return
    data = json.loads(report)
    items = data["items"]
    if changed is not None:
        typer.echo(f"{data['shown']} items this change asks to re-read")
    elif not show_all:
        typer.echo(
            f"{data['shown']} of {data['total']} sentences naming code name code changed since "
            "their doc was last committed; pass --all for all of them"
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
            typer.echo(f"    `{name}` -> unbound; {UNBOUND_ADVICE}")
    if not items:
        typer.echo("(none)")
        return
    typer.echo()
    typer.echo("markers:")
    width = max(len(name) for name in data["markers"])
    for name, meaning in data["markers"].items():
        typer.echo(f"  {name:<{width}}  {meaning}")
