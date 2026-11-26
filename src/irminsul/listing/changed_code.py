"""The functions and classes a change touched, as the sentences that name them are asked.

A change runs from a base commit to the working tree, or to `HEAD` when only commits are
judged. A code span is paired with the function or class it names on both sides, because
each side knows what the other cannot: where the change ends, the lines the definition has
now, and at the base, the lines it had and what the span named before the change removed it
or gave its name to a second definition. Both pairings are `CodeResolver`'s, so what a
sentence names here is what the review queue says it names without a change. Nothing else a
span can name is paired with a change: a command, an option, an environment variable, any
other surface identity and a path are each named by too many sentences, for too many
reasons, for an edit to ask about them all.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING

from irminsul.checks.globs import SourceWalkResult, is_configured_source_path
from irminsul.code_references import CodeResolver, Reference
from irminsul.git.changes import (
    GitChangesError,
    file_at_ref,
    renamed_paths,
    tracked_paths_at_ref,
    working_tree_changed_paths,
)
from irminsul.inventory.base import PythonModule
from irminsul.source_tree import SourceTree

if TYPE_CHECKING:
    from irminsul.docgraph import DocGraph
    from irminsul.git.reader import GitReader
    from irminsul.listing.review import ChangedLines


@dataclass(frozen=True)
class ChangedCode:
    """A function or class a sentence names that the change touched, and where.

    `identity` is its bare name. `path` and `line` are the change's: the first changed line
    in its range, or the line that defined it at the base when the change removed or renamed
    it, which `removed` says. One in a file every line of which is new has no line, and
    neither has one in a file that no longer parses, where its lines cannot be read.
    """

    span: str
    identity: str
    path: str
    line: int | None
    removed: bool = False


class SourceAtCommit(SourceTree):
    """The configured source as one commit holds it, read through the working tree's snapshot.

    Its files are the walked files that commit tracks, plus the source files it tracks that
    are no longer on disk, so the walk's policy decides both sides alike. A file the working
    tree holds unchanged is read, and parsed, once for both; one that `differs` names, or
    that is gone from disk, is read from the commit. Files in a source root outside the
    repository are not part of its commits and are read as they stand.
    """

    def __init__(
        self,
        live: SourceTree,
        git: GitReader,
        ref: str,
        tracked: frozenset[str],
        differs: frozenset[str],
    ) -> None:
        super().__init__(live.repo_root, live.config)
        self._live = live
        self._git = git
        self._ref = ref
        root = live.repo_root.resolve()
        kept = [
            (path, display)
            for path, display in live.files
            if path != root / display or display in tracked
        ]
        walked = {display for _, display in live.files}
        gone = sorted(
            display
            for display in tracked - walked
            if not (root / display).is_file()
            and is_configured_source_path(live.repo_root, live.config, display)
        )
        self._files = [*kept, *((root / display, display) for display in gone)]
        self._at_commit = {
            os.fspath(path): display
            for path, display in self._files
            if path == root / display and (display in differs or not path.is_file())
        }

    @cached_property
    def walk(self) -> SourceWalkResult:
        return SourceWalkResult(files=self._files, missing_roots=[], issues=[])

    def text(self, path: Path) -> str | None:
        key = os.fspath(path)
        display = self._at_commit.get(key)
        if display is None:
            return self._live.text(path)
        if key not in self._texts:
            try:
                self._texts[key] = file_at_ref(self._git, self.repo_root, self._ref, display)
            except GitChangesError:
                self._texts[key] = None
        return self._texts[key]

    def module(self, path: Path) -> PythonModule | None:
        if os.fspath(path) not in self._at_commit:
            return self._live.module(path)
        return super().module(path)


class ChangePairing:
    """Which function or class a span names the change touched.

    A definition is the one a span names where the change ends, or the one it named at the
    base, which is how it is found once the change removed it or a second definition took
    its name. Its lines are its decorators, its `def` or `class` line and its body, and it is
    touched when the lines it has where the change ends are not the lines it had at the
    base. So an added or altered line counts where the change puts it and a deleted one
    where it lay, which a diff's line numbers do not say: git files a deletion under the
    line before it, and that may be the last line of the definition above. One the span
    named at the base was removed or renamed when its file, which a rename git reports
    carries with it, no longer defines it, unless that file no longer parses: then what it
    defines cannot be read, and the definition is reported as changed with no line.
    """

    def __init__(
        self,
        graph: DocGraph,
        resolver: CodeResolver,
        changed: ChangedLines,
        base_ref: str,
        *,
        committed_only: bool = False,
    ) -> None:
        assert graph.repo_root is not None
        self._repo_root = graph.repo_root
        self._root = graph.repo_root.resolve()
        self._git = graph.git
        self._live = graph.source
        self._changed = changed
        self._base_ref = base_ref
        self._head = "HEAD" if committed_only else None
        self._at_head: frozenset[str] | None = None
        self._dirty: frozenset[str] = frozenset()
        self.after = resolver
        after_tree = self._live
        if committed_only:
            self._dirty = self._uncommitted()
            self._at_head = self._tracked("HEAD")
            if self._dirty and self._at_head is not None:
                after_tree = SourceAtCommit(
                    self._live, self._git, "HEAD", self._at_head, self._dirty
                )
                self.after = CodeResolver(after_tree)
        self._memo: dict[str, list[ChangedCode]] = {}

    def _uncommitted(self) -> frozenset[str]:
        try:
            return frozenset(working_tree_changed_paths(self._git, self._repo_root))
        except GitChangesError:
            return frozenset()

    def _tracked(self, ref: str) -> frozenset[str] | None:
        try:
            paths = tracked_paths_at_ref(self._git, self._repo_root, ref)
        except GitChangesError:
            return None
        return None if paths is None else frozenset(paths)

    def _on_after_side(self, display: str) -> bool:
        if self._head is not None and self._at_head is not None:
            return display in self._at_head
        return (self._root / display).is_file()

    @cached_property
    def _before(self) -> CodeResolver | None:
        """The pairing at the base, or None when the change cannot have removed a function
        or class: the base cannot be read, or the change edited no source file the base
        holds and every source file the base holds is still there."""
        tracked = self._tracked(self._base_ref)
        if tracked is None:
            return None
        differs = frozenset(self._changed) | self._dirty
        tree = SourceAtCommit(self._live, self._git, self._base_ref, tracked, differs)
        if not any(
            display in self._changed or not self._on_after_side(display)
            for display in tracked.intersection(display for _, display in tree.files)
        ):
            return None
        return CodeResolver(tree)

    @cached_property
    def _renamed(self) -> dict[str, str]:
        try:
            return renamed_paths(self._git, self._repo_root, self._base_ref, self._head)
        except GitChangesError:
            return {}

    def touched(self, span: str) -> list[ChangedCode]:
        """The function or class `span` names that the change edited, renamed or deleted."""
        if span not in self._memo:
            self._memo[span] = self._touched(span)
        return self._memo[span]

    def _touched(self, span: str) -> list[ChangedCode]:
        out: list[ChangedCode] = []
        judged: set[tuple[str, str]] = set()
        before = self._before
        if before is not None:
            for ref in _definitions(before, span):
                name, was_in = before.named_as(ref), ref.defined_at
                now_in = self._renamed.get(was_in, was_in)
                if self.after.definitions(name, now_in):
                    judged.add((name, now_in))
                    out.extend(self._edited(span, ref.identity, name, now_in, was_in))
                elif self.after.unparsed(now_in):
                    out.append(ChangedCode(span, ref.identity, now_in, None))
                else:
                    out.append(ChangedCode(span, ref.identity, was_in, ref.line, removed=True))
        for ref in _definitions(self.after, span):
            name, now_in = self.after.named_as(ref), ref.defined_at
            if (name, now_in) not in judged:
                was_in = next((old for old, new in self._renamed.items() if new == now_in), now_in)
                out.extend(self._edited(span, ref.identity, name, now_in, was_in))
        return out

    def _edited(
        self, span: str, identity: str, name: str, display: str, was_in: str
    ) -> list[ChangedCode]:
        """The definition `display` holds as `name` where the change ends, when its lines are
        not the ones `was_in` held under that name at the base, with the first line that
        differs."""
        if display not in self._changed or not self.after.in_repository(display):
            return []
        if self._changed[display] is None:
            return [ChangedCode(span, identity, display, None)]
        had = self._before.definitions(name, was_in) if self._before is not None else []
        for index, (first, lines) in enumerate(self.after.definitions(name, display)):
            old = had[index][1] if index < len(had) else []
            if lines != old:
                same = 0
                while same < min(len(lines), len(old)) and lines[same] == old[same]:
                    same += 1
                return [ChangedCode(span, identity, display, first + min(same, len(lines) - 1))]
        return []


def _definitions(resolver: CodeResolver, span: str) -> list[Reference]:
    """The function or class `span` names, as `resolver` pairs it: none when the span names
    a surface identity or a path instead."""
    return [ref for ref in resolver.resolve(span) if ref.kind == "symbol"]
