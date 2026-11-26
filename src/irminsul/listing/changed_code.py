"""The code a change touched, as the sentences that name it are asked.

A change runs from a base commit to the working tree, or to `HEAD` when only commits are
judged. A code span is paired with the code it names on both sides: on the after side, where
the change's line numbers are counted, to see whether a changed line falls in what the span
names, and at the base, to find what the span named there and names no longer. Both pairings
are `CodeResolver`'s, so what a sentence names here is what the review queue says it names
without a change.
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
    """Code a sentence names that the change touched, and where.

    `path` and `line` are the change's: the first changed line in what the span names, or
    the line that defined it at the base when the change removed or renamed it, which
    `removed` says. A file, and code in a file every line of which is new, has no line.
    """

    span: str
    kind: str
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
    """Which of the code a span names the change touched.

    Code the after side still has is touched when a changed line falls in the lines
    `CodeResolver.declared_lines` gives it. Code the span named at the base, in a file the
    change edited, renamed or deleted, was removed or renamed by the change when the span no
    longer names it and that file no longer has it; a file git says was only renamed keeps
    what it defines. A span that pairs with other code now, or with none because a second
    definition took its name, did not lose code that is still where it was.
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
                self.after = CodeResolver(after_tree, tracked=self._at_head)
        self._after_source = frozenset(display for _, display in after_tree.files)
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
        """The pairing at the base, or None when the change cannot have removed anything a
        span names: the base cannot be read, or the change edited no source file the base
        holds and every file the base holds is still there."""
        tracked = self._tracked(self._base_ref)
        if tracked is None:
            return None
        if not any(
            (path in self._changed and path in self._after_source) or not self._on_after_side(path)
            for path in tracked
        ):
            return None
        differs = frozenset(self._changed) | self._dirty
        tree = SourceAtCommit(self._live, self._git, self._base_ref, tracked, differs)
        return CodeResolver(tree, tracked=tracked)

    @cached_property
    def _renamed(self) -> dict[str, str]:
        try:
            return renamed_paths(self._git, self._repo_root, self._base_ref, self._head)
        except GitChangesError:
            return {}

    def touched(self, span: str) -> list[ChangedCode]:
        """The code `span` names that the change edited, renamed or deleted."""
        if span not in self._memo:
            self._memo[span] = self._touched(span)
        return self._memo[span]

    def _touched(self, span: str) -> list[ChangedCode]:
        now = self.after.resolve(span)
        out: list[ChangedCode] = []
        for ref in now:
            edited, line = self._edited_at(ref)
            if edited:
                out.append(ChangedCode(span, ref.kind, ref.identity, ref.defined_at, line))
        before = self._before
        if before is not None:
            held = {(ref.kind, self.after.named_as(ref), ref.defined_at) for ref in now}
            for ref in before.resolve(span):
                was_in = ref.defined_at
                if was_in not in self._changed and self._on_after_side(was_in):
                    continue
                name, now_in = before.named_as(ref), self._renamed.get(was_in, was_in)
                if (ref.kind, name, now_in) in held:
                    continue
                if ref.kind != "path" and self.after.has(ref.kind, name, now_in):
                    continue
                out.append(
                    ChangedCode(span, ref.kind, ref.identity, was_in, ref.line, removed=True)
                )
        return list(dict.fromkeys(out))

    def _edited_at(self, ref: Reference) -> tuple[bool, int | None]:
        """Whether a changed line falls in what `ref` names, and the first one that does."""
        display = ref.defined_at
        if display not in self._changed or not self.after.in_repository(display):
            return False, None
        lines = self._changed[display]
        if lines is None:
            return True, None
        first, last = self.after.declared_lines(ref)
        if first is None or last is None:
            return True, min(lines, default=None)
        inside = [line for line in lines if first <= line <= last]
        return bool(inside), min(inside, default=None)
