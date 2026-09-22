"""One reading of the test paths a doc declares, shared by everything that reads them.

Three fields name test paths, and they mean different things:

- `owns_tests:` is **maintenance ownership** — this document is responsible for the test
  implementation it names. Exactly one document may own a test file. Entries must be
  exact paths: a glob or a directory would claim files nobody chose, and ownership has to
  be a decision somebody made.
- `recommended_tests:` is a **recommendation** — what an agent editing this component
  should run. Several documents may recommend the same shared integration test without
  any of them owning it. Directories and globs are fine here, because recommending is not
  claiming.
- `tests:` is the older spelling of `recommended_tests:`, still read.

Before this module the three consumers disagreed about the same list: `coverage` treated
an entry as a literal path and `Path.exists()`'d it, `change/footprint` matched it as a
gitignore pattern, and `context` compared it by exact string. One `tests: [tests/]` entry
therefore passed the first, claimed every file under it in the second, and matched
nothing in the third.

Nothing here executes a test or reads a result. A declared test is a pointer, and that a
file changed is not evidence that anything was verified.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pathspec import GitIgnoreSpec

from irminsul.config import IrminsulConfig
from irminsul.languages import LANGUAGE_REGISTRY

TestReferenceKind = Literal["file", "directory", "pattern"]


@dataclass(frozen=True)
class TestReference:
    """One declared entry, and what shape it turned out to be."""

    raw: str
    kind: TestReferenceKind

    @property
    def is_exact(self) -> bool:
        return self.kind == "file"


def classify_test_reference(entry: str, repo_root: Path | None = None) -> TestReference:
    """What shape a declared entry is.

    A trailing slash, or a path that is a directory on disk, is a directory. Anything
    carrying a wildcard is a pattern. Everything else names one file — whether or not it
    exists, which is a separate question `coverage` asks.
    """
    cleaned = entry.strip()
    if cleaned.endswith("/"):
        return TestReference(raw=cleaned, kind="directory")
    if any(char in cleaned for char in "*?["):
        return TestReference(raw=cleaned, kind="pattern")
    if repo_root is not None and (repo_root / cleaned).is_dir():
        return TestReference(raw=cleaned, kind="directory")
    return TestReference(raw=cleaned, kind="file")


def test_reference_spec(entries: list[str]) -> GitIgnoreSpec:
    """A matcher covering every entry, with directories expanded to their contents.

    `tests/` has to match `tests/test_cli.py`, and a bare `tests` written without the
    slash means the same thing to whoever wrote it.

    An entry that does not compile — `tests/[z-a].py` is an inverted character range —
    matches nothing rather than raising. A person can type that, and every caller is
    asking "which files does this name", where the answer for a malformed pattern is
    "none". `coverage` then reports the entry as matching no file, which is the finding
    that says so; an uncaught `re.error` ended the whole run in a traceback instead.
    """
    lines: list[str] = []
    for entry in entries:
        reference = classify_test_reference(entry)
        candidates = [reference.raw]
        if reference.kind == "directory":
            candidates.append(f"{reference.raw.rstrip('/')}/**")
        for line in candidates:
            try:
                GitIgnoreSpec.from_lines([line])
            except (re.error, ValueError):
                continue
            lines.append(line)
    return GitIgnoreSpec.from_lines(lines)


def matching_paths(entries: list[str], candidates: list[str]) -> list[str]:
    """Which of `candidates` the declared entries name, in sorted order."""
    if not entries:
        return []
    spec = test_reference_spec(entries)
    return sorted(path for path in candidates if spec.match_file(path))


def configured_test_patterns(config: IrminsulConfig) -> tuple[str, ...]:
    """The patterns that decide whether a path is a test implementation file.

    `paths.test_patterns` replaces the language defaults outright when set, so a project
    whose layout no convention describes can say so once rather than per document.
    """
    configured = tuple(config.paths.test_patterns)
    if configured:
        return configured
    out: list[str] = []
    for name in config.languages.enabled:
        profile = LANGUAGE_REGISTRY.get(name)
        if profile is not None:
            out.extend(profile.test_patterns)
    return tuple(dict.fromkeys(out))


def is_test_path(path: str, config: IrminsulConfig) -> bool:
    """Whether `path` is a test implementation file by *name*, under the project's
    conventions.

    The weaker of the two signals, and never a reason on its own to waive ownership —
    `governed_as_test` is what the rules ask. A document cannot make a file a test by
    naming it either, so an ordinary source file listed under `owns_tests:` is reported
    rather than quietly excused from `describes:` ownership.
    """
    patterns = configured_test_patterns(config)
    return bool(patterns) and GitIgnoreSpec.from_lines(patterns).match_file(path)


def _under(path: str, roots: list[str]) -> bool:
    for root in roots:
        cleaned = root.strip("/")
        if not cleaned or cleaned == ".":
            return True
        if path == cleaned or path.startswith(f"{cleaned}/"):
            return True
    return False


def test_root_displays(repo_root: Path, config: IrminsulConfig) -> frozenset[str]:
    """The display paths a declared `paths.test_roots` walk produces.

    `_under` answers "is this path inside a declared test root" by comparing strings, and
    that only works while displays and roots are spelled the same way. They are not in the
    siblings layout: a file in another repository carries a display relative to the root
    that produced it, so `../code/tests/helpers.py` arrives as `helpers.py` and no string
    comparison with `../code/tests` can recognize it. The walk knows, because it is what
    produced the display, so the answer is taken from there instead of reconstructed.
    """
    from irminsul.checks.globs import walk_configured_source_files

    if not config.paths.test_roots:
        return frozenset()
    scoped = config.model_copy(
        update={"paths": config.paths.model_copy(update={"source_roots": config.paths.test_roots})}
    )
    return frozenset(
        display for _, display in walk_configured_source_files(repo_root, scoped).files
    )


def governed_as_test(
    path: str, config: IrminsulConfig, *, in_test_root: bool | None = None
) -> bool:
    """Whether the test-ownership policy governs this file, rather than `describes:`.

    Every managed file answers to exactly one policy, decided in this order:

    1. **Named as a test** — `parser_test.go` beside `parser.go` is a test wherever it
       lives, which is the only thing that can see Go's colocated layout.
    2. **Inside a declared test root and outside every source root** — location settles
       what a filename cannot, so a helper or a package marker under `tests/` still has an
       owner. The source-root exclusion is what keeps an overlapping pair of roots (a Go
       repository may set both to `.`) from putting ordinary source under the test policy.
    3. **Otherwise the source policy**, and the file needs a `describes:` owner.

    The order matters: a filename is decisive only where a declared root has not already
    spoken, and a declared root never captures a tree the source walk also owns.

    `in_test_root` is rule 2's answer supplied by a caller that walked the roots itself.
    Left out, membership is read from the path, which is right whenever displays and roots
    share a spelling — every same-repository layout. It is wrong in the siblings layout,
    where a display is relative to the root that produced it: `helpers.py` from
    `../code/tests` matched no root, so a non-test-shaped file in a *declared* test root
    answered to neither policy and nothing asked anybody to claim it. Callers that have the
    walk pass `test_root_displays`.
    """
    if is_test_path(path, config):
        return True
    inside = _under(path, config.paths.test_roots) if in_test_root is None else in_test_root
    if not inside:
        return False
    return not _under(path, config.paths.source_roots)


__all__ = [
    "TestReference",
    "TestReferenceKind",
    "classify_test_reference",
    "configured_test_patterns",
    "governed_as_test",
    "is_test_path",
    "matching_paths",
    "test_reference_spec",
    "test_root_displays",
]
