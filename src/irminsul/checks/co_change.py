"""Co-change enforcement — docs ship in the same change as the code they claim.

A pass, not a registered graph check: it needs the changed-file set of the range on the
graph, from the merge base to the working tree, which only `--diff <base>` or
`context --after-edit` with a base supplies. It reads the diff itself, where
`mtime-drift` compares commit times. Ownership is resolved through the exact `describes`
glob logic the uniqueness check uses (`resolve_claims` / `most_specific_claims`), so "who
owns this file?" has one answer everywhere. Findings are hints, so `--fail-on hint` makes
them fail the run like any other hint.

A reader who re-reads the doc and finds it still right acknowledges the warning with a
commit trailer in the change, `Irminsul-Reviewed: co-change <doc> reason="..."`. The
warning is then reported as info quoting the reason, for exactly as long as the change
it belongs to: the trailer leaves nothing in the tree. An ignore comment cannot do this:
the finding has no line, and adding the comment would itself be the doc edit the check
asks for.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Final

from irminsul.checks.base import Answer, Finding, FindingClass, Severity
from irminsul.checks.change_range import after_text
from irminsul.checks.uniqueness import most_specific_claims, resolve_claims
from irminsul.docgraph import ChangeRange, DocGraph, DocNode, resolve_doc_target

if TYPE_CHECKING:
    from irminsul.git.reader import GitReader

CHECK_NAME: Final = "co-change"
CODE_UNREFLECTED_CHANGE: Final = "co-change/unreflected-change"
CODE_ACKNOWLEDGED: Final = "co-change/acknowledged"
CODE_INVALID_ACKNOWLEDGEMENT: Final = "co-change/invalid-acknowledgement"
CODE_UNUSED_ACKNOWLEDGEMENT: Final = "co-change/unused-acknowledgement"
TRAILER_KEY: Final = "Irminsul-Reviewed"
_TRAILER_FORM: Final = f'{TRAILER_KEY}: co-change <doc-id|path> reason="..."'

_TRAILER_RE = re.compile(
    r"(?P<check>\S+)(?:\s+(?!reason=)(?P<target>[^\s\"]+))?"
    r"(?:\s+reason=\"(?P<reason>[^\"]*)\")?\s*"
)


class CoChangePass:
    """Docs must ship in the same change as the code they claim.

    It judges the change rather than the tree, so it reports only when the CLI's `--diff`
    flag puts a range on the graph.
    """

    name: ClassVar[str] = CHECK_NAME
    default_severity: ClassVar[Severity] = Severity.warning
    explanations: ClassVar[dict[str, str]] = {
        CODE_UNREFLECTED_CHANGE: (
            "A source file this doc claims via `describes` changed in the diff, but "
            "the doc itself did not. Update the doc in the same change, or run "
            "`irminsul context <changed-file>` to see what it claims. If you re-read the "
            "doc and it is still right, acknowledge it instead with the commit trailer "
            f"`{_TRAILER_FORM}` on a commit made after the last change to those files, or "
            "on the commit that carries them. A trailer covers the changes made up to its "
            "own commit, so a later change to them needs a later trailer, and a change not "
            "yet committed is later than every commit."
        ),
        CODE_ACKNOWLEDGED: (
            f"A `{TRAILER_KEY}` commit trailer in the diff range says the doc was re-read "
            "and is still right after its claimed sources changed. Reported so a reviewer "
            "sees what was waved through and why; it never fails a run."
        ),
        CODE_INVALID_ACKNOWLEDGEMENT: (
            f"A `{TRAILER_KEY}` commit trailer acknowledges nothing: it names a check other "
            "than co-change, no doc, or a doc that does not exist, or gives no reason, so "
            "the warning it meant to answer still stands. It is info rather than a warning "
            "because a trailer cannot be removed without rewriting history; add a valid "
            f"one, `{_TRAILER_FORM}`, to a later commit."
        ),
        CODE_UNUSED_ACKNOWLEDGEMENT: (
            f"A `{TRAILER_KEY}` commit trailer names a doc co-change does not warn on in "
            "this range, so it acknowledges nothing. Nothing is left to do when the doc "
            "changed in the range too; if the trailer names the wrong doc, add one naming "
            "the right doc to a later commit."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_UNREFLECTED_CHANGE: FindingClass.hint,
        CODE_ACKNOWLEDGED: FindingClass.hint,
        CODE_INVALID_ACKNOWLEDGEMENT: FindingClass.hint,
        CODE_UNUSED_ACKNOWLEDGEMENT: FindingClass.hint,
    }
    answers: ClassVar[dict[str, Answer]] = {
        CODE_UNREFLECTED_CHANGE: Answer.trailer(
            "if you re-read the doc and it is still right, add the `Irminsul-Reviewed` trailer "
            "its suggestion prints, on a commit made after the last change to the files it lists"
        ),
        CODE_ACKNOWLEDGED: Answer.fix(
            "nothing to do: it shows a reviewer what a trailer acknowledged, and ends when the "
            "change merges"
        ),
        CODE_INVALID_ACKNOWLEDGEMENT: Answer.fix("add a valid trailer to a later commit"),
        CODE_UNUSED_ACKNOWLEDGEMENT: Answer.fix(
            "nothing to do if the doc changed in the range; otherwise add a trailer naming the "
            "right doc to a later commit"
        ),
    }

    def run(self, graph: DocGraph, selected: Collection[str]) -> list[Finding]:
        change, repo_root = graph.change, graph.repo_root
        if change is None or repo_root is None:
            return []
        return run_co_change(
            graph,
            change.changed,
            whitespace_only_docs(graph.git, repo_root, change),
            reviewed_trailers(graph.git, repo_root, change),
            change.uncommitted,
        )


@dataclass(frozen=True)
class Trailer:
    """One `Irminsul-Reviewed` trailer read from a commit in the diff range."""

    commit: str
    value: str
    changed_after: frozenset[str]
    """What the range changes in commits after this one, which its writer cannot have
    re-read the doc against."""


def whitespace_only_docs(git: GitReader, repo_root: Path, change: ChangeRange) -> frozenset[str]:
    """The changed docs whose content differs from the merge base only in whitespace."""
    from irminsul.git.changes import GitChangesError, file_at_ref

    def words(text: str) -> str:
        return " ".join(text.split())

    out: set[str] = set()
    for path in change.changed:
        if not path.endswith(".md"):
            continue
        try:
            before = file_at_ref(git, repo_root, change.merge_base, path)
        except GitChangesError:
            continue
        after = after_text(git, repo_root, change.head, path)
        if before is not None and after is not None and words(before) == words(after):
            out.add(path)
    return frozenset(out)


def reviewed_trailers(git: GitReader, repo_root: Path, change: ChangeRange) -> list[Trailer]:
    """The `Irminsul-Reviewed` trailers in the range, each with what later changes touched.

    Work not yet committed is later than every commit. When git cannot say what changed
    after a commit, everything in the range counts as later, so a trailer whose reach is
    unknown acknowledges nothing.
    """
    from irminsul.git.changes import GitChangesError, commit_trailers, files_changed_after

    try:
        read = commit_trailers(git, repo_root, change.base, change.commit, TRAILER_KEY)
        changed_after: dict[str, frozenset[str]] = {}
        for commit, _ in read:
            if commit not in changed_after:
                after = files_changed_after(git, repo_root, commit, change.commit, change.base)
                changed_after[commit] = (
                    change.changed if after is None else after | change.uncommitted
                )
    except GitChangesError:
        return []
    return [Trailer(commit, value, changed_after[commit]) for commit, value in read]


def run_co_change(
    graph: DocGraph,
    changed: frozenset[str],
    cosmetic: frozenset[str] = frozenset(),
    trailers: Sequence[Trailer] = (),
    uncommitted: frozenset[str] = frozenset(),
) -> list[Finding]:
    """Warn for each owning doc whose claimed sources changed without it.

    `changed` is the repo-relative POSIX path set from `git diff --name-only`, and
    `uncommitted` the part of it no commit holds yet, which a warning marks so the reader
    knows the trailer belongs in the commit that will carry those files.
    A changed source file is "unreflected" when none of its most-specific
    owning docs appear in the changed set; findings are grouped per owning
    doc, listing every unreflected file it claims.

    `cosmetic` names docs whose change was whitespace only. They do not count as
    having shipped with the code: one blank line in the owning doc would otherwise
    satisfy this check, making the cheapest way to pass it an edit that says nothing.

    A valid trailer naming a warned doc turns its warning into info, unless a later
    change, committed or not, touched one of the files the warning lists.
    """
    if graph.config is None or graph.repo_root is None:
        return []

    # Resolve claims against the changed set directly rather than walking the
    # whole source tree: faster on large repos, and a deleted claimed file
    # (absent from any walk) still triggers enforcement on its owning doc.
    claims_by_file = resolve_claims(graph, sorted(changed))

    unreflected_by_doc: dict[str, tuple[DocNode, list[str]]] = {}
    for source_file in sorted(changed):
        claims = claims_by_file.get(source_file)
        if not claims:
            continue  # unclaimed file — nothing owns it, nothing to enforce
        owners = {node.path.as_posix(): node for node, _, _ in most_specific_claims(claims)}
        if any(doc_path in changed and doc_path not in cosmetic for doc_path in owners):
            continue  # an owning doc shipped in the same change
        for doc_path, node in owners.items():
            _, files = unreflected_by_doc.setdefault(doc_path, (node, []))
            files.append(source_file)

    unreflected = {doc_path: files for doc_path, (_, files) in unreflected_by_doc.items()}
    reviewed, outdated, notes = _read_trailers(graph, trailers, unreflected, uncommitted)

    out: list[Finding] = []
    for doc_path in sorted(unreflected_by_doc):
        node, files = unreflected_by_doc[doc_path]
        shown = ", ".join(_shown(path, uncommitted) for path in files)
        message = (
            f"source file(s) claimed by this doc changed in the diff but the doc did not: {shown}"
        )
        if doc_path in reviewed:
            out.append(
                Finding(
                    check=CHECK_NAME,
                    code=CODE_ACKNOWLEDGED,
                    severity=Severity.info,
                    path=node.path,
                    doc_id=node.id,
                    message=f"{message}; acknowledged as reviewed in {'; '.join(reviewed[doc_path])}",
                )
            )
            continue
        pending = [path for path in files if path in uncommitted]
        placement = (
            f"in the message of the commit that carries {', '.join(pending)}"
            if pending
            else "on a commit made after the last change to those files"
        )
        suggestion = (
            "update the doc in the same change, or run "
            "`irminsul context <changed-file>` to see what it claims; if you "
            "re-read it and it is still right, add the commit trailer "
            f'`{TRAILER_KEY}: co-change {doc_path} reason="..."` {placement}'
        )
        if doc_path in outdated:
            suggestion += f" ({outdated[doc_path]}: that trailer does not count)"
        out.append(
            Finding(
                check=CHECK_NAME,
                code=CODE_UNREFLECTED_CHANGE,
                severity=Severity.warning,
                path=node.path,
                doc_id=node.id,
                message=message,
                suggestion=suggestion,
            )
        )
    return out + notes


def _shown(path: str, uncommitted: frozenset[str]) -> str:
    return f"{path} (uncommitted)" if path in uncommitted else path


def _read_trailers(
    graph: DocGraph,
    trailers: Sequence[Trailer],
    unreflected: dict[str, list[str]],
    uncommitted: frozenset[str],
) -> tuple[dict[str, list[str]], dict[str, str], list[Finding]]:
    """(the quoted reasons for each acknowledged doc, what outdated each trailer that a
    later change overtook, an info finding for each trailer that acknowledges nothing).

    A trailer is valid when it names co-change, a doc by id or path, and a non-empty
    reason, so an acknowledgement is as reviewable as an ignore comment.
    """
    reviewed: dict[str, list[str]] = {}
    outdated: dict[str, str] = {}
    notes: list[Finding] = []
    for trailer in trailers:
        match = _TRAILER_RE.fullmatch(trailer.value)
        target = match["target"] if match else None
        doc_path = resolve_doc_target(graph, target) if target else None
        reason = (match["reason"] or "").strip() if match else ""
        problem: str | None = None
        if match is None:
            problem = "is not written as a check, a doc and a reason"
        elif match["check"] not in (CHECK_NAME, CODE_UNREFLECTED_CHANGE):
            problem = f"names {match['check']}, and a trailer acknowledges only co-change"
        elif target is None:
            problem = "names no doc"
        elif doc_path is None:
            problem = f"names no doc with id or path {target}"
        elif not reason:
            problem = "gives no reason"
        if problem is not None:
            notes.append(
                _note(
                    CODE_INVALID_ACKNOWLEDGEMENT,
                    trailer,
                    problem,
                    doc_path,
                    f"add a valid trailer, `{_TRAILER_FORM}`, to a later commit",
                )
            )
            continue
        assert doc_path is not None
        if doc_path not in unreflected:
            notes.append(
                _note(
                    CODE_UNUSED_ACKNOWLEDGEMENT,
                    trailer,
                    "names a doc co-change does not warn on in this range",
                    doc_path,
                    "nothing to do if the doc changed in the range; if the trailer names "
                    "the wrong doc, add one naming the right doc to a later commit",
                )
            )
            continue
        later = [path for path in unreflected[doc_path] if path in trailer.changed_after]
        if later:
            shown = ", ".join(_shown(path, uncommitted) for path in later)
            outdated[doc_path] = f"{trailer.commit}, which predates the change to {shown}"
            continue
        reviewed.setdefault(doc_path, []).append(f'{trailer.commit}: "{reason}"')
    return reviewed, outdated, notes


def _note(
    code: str, trailer: Trailer, problem: str, doc_path: str | None, suggestion: str
) -> Finding:
    return Finding(
        check=CHECK_NAME,
        code=code,
        severity=Severity.info,
        path=Path(doc_path) if doc_path is not None else None,
        message=f"the {TRAILER_KEY} trailer in {trailer.commit} {problem}: {trailer.value}",
        suggestion=suggestion,
    )
