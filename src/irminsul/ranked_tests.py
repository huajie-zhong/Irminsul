"""The tests `irminsul context` names for a source file, and the reason each one is named.

A doc can own dozens of tests, and a flat list buries the one that exercises the file in
hand. The owner's declared tests stay the starting point, and every test file in the
declared test roots that imports the file is added to them, whichever doc owns it. They are
ordered by evidence, strongest first:

1. tests that import the file, read by the same reader the import checks use;
2. tests by how many commits changed both the test and the file;
3. the rest, alphabetically, with no reason.

Nothing here runs a test or says one passes: a reason says why a path is listed, not that
it covers the change.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from irminsul.checks.dependency_check import imported_paths
from irminsul.checks.globs import resolve_display_path
from irminsul.declared_tests import classify_test_reference, governed_as_test
from irminsul.docgraph import DocGraph, DocNode
from irminsul.git.mtime import git_root_for

_COMMIT_ID_RE = re.compile(r"[0-9a-f]{40,64}")
#: Commits changing more files than this are left out of the co-change count: an initial
#: import or a repository-wide rename changes every test and the file alike, so it says
#: nothing about which tests belong with the file.
_MAX_CO_CHANGED_FILES = 30
#: How far back the count looks: the latest commits that changed the file, so a file
#: with a long history costs a bounded `git log`.
_RECENT_COMMITS = 200


@dataclass(frozen=True)
class Ranking:
    """Every test path, best first, and the reasons for the ones that have any."""

    tests: list[str]
    reasons: dict[str, list[str]]


class Ranker:
    """Ranks tests for one graph. Holds what it derived for that call only."""

    def __init__(self, graph: DocGraph) -> None:
        self._graph = graph
        self._test_owner: dict[str, DocNode] | None = None
        self._test_files: dict[str, Path] | None = None
        self._imports: dict[str, frozenset[str]] = {}

    def rank(self, owner: DocNode, inputs: Sequence[str]) -> Ranking:
        """The owner's tests plus the tests importing any of `inputs`, ordered.

        Only an input that is source ranks anything: a doc has no importers, and a test
        file is imported by every test that shares it, which says nothing about which ones
        matter. With no source input the owner's list stands in the order it was authored.
        """
        declared = owner.frontmatter.effective_recommended_tests
        subjects = self._source_inputs(inputs)
        if not subjects:
            return Ranking(tests=list(declared), reasons={})

        importers = self._importers(subjects)
        candidates = list(
            dict.fromkeys(
                [
                    *declared,
                    *(test for subject in subjects for test in importers[subject]),
                ]
            )
        )
        co_changes = self._co_changes(subjects, candidates)

        reasons: dict[str, list[str]] = {}
        order: list[tuple[int, int, str]] = []
        for test in candidates:
            why = [f"imports {subject}" for subject in subjects if test in importers[subject]]
            imports = bool(why)
            changed_together = 0
            for subject in subjects:
                count = co_changes[subject].get(test, 0)
                if count:
                    changed_together += count
                    noun = "commit" if count == 1 else "commits"
                    named = "it" if len(subjects) == 1 else subject
                    why.append(f"changed with {named} in {count} {noun}")
            maintainer = self._maintainer(test)
            if maintainer is not None and maintainer.id != owner.id:
                why.append(f"owned by {maintainer.path.as_posix()}")
            if why:
                reasons[test] = why
            order.append((0 if imports else 1, -changed_together, test))
        return Ranking(tests=[test for _, _, test in sorted(order)], reasons=reasons)

    def _source_inputs(self, inputs: Sequence[str]) -> list[str]:
        config = self._graph.config
        assert config is not None
        return [
            path
            for path in inputs
            if Path(PurePosixPath(path)) not in self._graph.by_path
            and not governed_as_test(path, config)
        ]

    def _importers(self, subjects: Sequence[str]) -> dict[str, list[str]]:
        """Each subject's importing tests, by the display path the test walk gives them."""
        graph = self._graph
        config = graph.config
        assert config is not None and graph.repo_root is not None
        found: dict[str, list[str]] = {subject: [] for subject in subjects}
        python = [subject for subject in subjects if subject.endswith(".py")]
        if not python:
            return found
        targets = {_key(self._absolute(subject)): subject for subject in python}
        names = "|".join(sorted({re.escape(_module_name(subject)) for subject in python}))
        # A file importing a module spells its name as a whole identifier, so this cheap
        # test leaves the parse to the few files that could.
        mentions = re.compile(rf"\b(?:{names})\b")
        for abs_path, display in graph.source.test_walk.files:
            if PurePosixPath(display).suffix != ".py":
                continue
            if not governed_as_test(display, config, in_test_root=True):
                continue
            text = graph.source.text(abs_path)
            if text is None or mentions.search(text) is None:
                continue
            module = graph.source.module(abs_path)
            if module is None:
                continue
            if (imported := self._imports.get(display)) is None:
                imported = self._imports[display] = frozenset(
                    _key(path)
                    for path in imported_paths(
                        module, abs_path, config.paths.source_roots, graph.repo_root
                    )
                )
            for key, subject in targets.items():
                if key in imported:
                    found[subject].append(display)
        return found

    def _co_changes(
        self, subjects: Sequence[str], candidates: Sequence[str]
    ) -> dict[str, dict[str, int]]:
        """For each subject, the commits that changed it together with each candidate.

        A commit over `_MAX_CO_CHANGED_FILES` files is not counted, for the reason given at
        that constant. Nothing follows a rename, and a merge commit lists no files, so
        neither is counted either.
        """
        out: dict[str, dict[str, int]] = {subject: {} for subject in subjects}
        tests = {
            test: path
            for test in candidates
            if classify_test_reference(test).is_exact
            and (path := self._test_path(test)) is not None
        }
        for root, subject_paths in self._subjects_by_root(subjects).items():
            test_paths = {
                relative: test
                for test, path in tests.items()
                if (relative := _relative(path, root)) is not None
            }
            if not test_paths:
                continue
            for files in self._commits_touching(root, list(subject_paths)):
                if len(files) > _MAX_CO_CHANGED_FILES:
                    continue
                together = [test for relative, test in test_paths.items() if relative in files]
                for relative, subject in subject_paths.items():
                    if relative in files:
                        for test in together:
                            out[subject][test] = out[subject].get(test, 0) + 1
        return out

    def _subjects_by_root(self, subjects: Sequence[str]) -> dict[Path, dict[str, str]]:
        """Each subject under the repository that holds it, by its path in that repository."""
        by_root: dict[Path, dict[str, str]] = {}
        for subject in subjects:
            path = self._absolute(subject)
            root = git_root_for(path)
            if root is not None and (relative := _relative(path, root)) is not None:
                by_root.setdefault(root, {})[relative] = subject
        return by_root

    def _commits_touching(self, root: Path, paths: list[str]) -> list[set[str]]:
        """The files of the latest commits that changed any of `paths` in the repository
        at `root`, from one bounded `git log`. `--full-diff` makes it list every file of
        each commit that touched `paths`, not only the pathspec's, which is what shows
        the other files a commit changed and how many there were."""
        raw = self._graph.git.text(
            root,
            "--literal-pathspecs",
            "log",
            "-n",
            str(_RECENT_COMMITS),
            "--name-only",
            "-z",
            "--format=%H",
            "--full-diff",
            "--",
            *paths,
        )
        return _commit_files(raw) if raw else []

    def _absolute(self, display: str) -> Path:
        graph = self._graph
        assert graph.repo_root is not None and graph.config is not None
        found = resolve_display_path(graph.repo_root, graph.config.paths.source_roots, display)
        return found if found is not None else graph.repo_root / display

    def _test_path(self, display: str) -> Path | None:
        graph = self._graph
        assert graph.repo_root is not None and graph.config is not None
        if self._test_files is None:
            self._test_files = {d: p for p, d in graph.source.test_walk.files}
        if display in self._test_files:
            return self._test_files[display]
        paths = graph.config.paths
        return resolve_display_path(
            graph.repo_root, [*paths.source_roots, *paths.test_roots], display
        )

    def _maintainer(self, test: str) -> DocNode | None:
        if self._test_owner is None:
            self._test_owner = {}
            for node in sorted(self._graph.nodes.values(), key=lambda n: n.path.as_posix()):
                for entry in node.frontmatter.owns_tests:
                    self._test_owner.setdefault(entry, node)
        return self._test_owner.get(test)


def _module_name(display: str) -> str:
    path = PurePosixPath(display)
    if path.stem == "__init__" and path.parent.name:
        return path.parent.name
    return path.stem


def _key(path: Path) -> str:
    return os.path.normcase(os.path.normpath(os.fspath(path)))


def _relative(path: Path, root: Path) -> str | None:
    try:
        relative = Path(os.path.normpath(path)).relative_to(Path(os.path.normpath(root)))
    except ValueError:
        return None
    return relative.as_posix()


def _commit_files(raw: str) -> list[set[str]]:
    """The files each commit of a `log --name-only -z --format=%H` listing changed.

    The first file of a commit follows its id after a newline, and every token is
    NUL-terminated, so a token that is a bare commit id opens the next commit.
    """
    commits: list[set[str]] = []
    for token in raw.split("\0"):
        if not token:
            continue
        if token[0] != "\n" and _COMMIT_ID_RE.fullmatch(token):
            commits.append(set())
        elif commits:
            commits[-1].add(token.removeprefix("\n"))
    return commits
