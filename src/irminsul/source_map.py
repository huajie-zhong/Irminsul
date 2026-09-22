"""Which repository and revision each managed file answers to — resolved once per snapshot.

Resolution, and deliberately not policy. This module answers *where* a display path comes
from; whether that makes it legitimate adoption debt is decided by the `adoption-record`
check and by `diff-integrity`'s seal. A successfully resolved `(repository, revision)` pair
is not a valid adoption binding, and keeping the two apart is what stops "I could find it"
from being mistaken for "it checks out".

The line that keeps them apart is mechanical: **resolution reads the filesystem, the
configuration and the record; validation reads git history.** Nothing here runs git. Finding
the repository that owns a tree is a walk up the directory chain; asking that repository
what it held at a revision is a subprocess, and it belongs on the other side of the line.

Why one map per snapshot rather than a helper called wherever it is needed: an entry is not
bound to a root, it is bound to whichever root the walk resolves its display to, and that
mapping depends on the configuration *and* the record. Recomputing it in each rule meant
each rule could disagree, and three review rounds each found a different rule holding the
minority opinion. A snapshot has exactly one answer here, and every consumer reads it.

Two snapshots are still two maps. `diff-integrity` builds one for the merge base, from the
base's configuration and the base's record, and one for the head — because "resolve once"
means once per snapshot, not one answer for a comparison that has two sides.
"""

from __future__ import annotations

import hashlib
import posixpath
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from irminsul.adoption import AdoptionRecord, SourceBoundary
    from irminsul.config import SourceSpec

#: The display is produced by a root inside this repository. Its boundary is the diff's own
#: merge base, which `diff-integrity` reads; there is no pin and none is wanted.
OWN: Final = "own"
#: The display is produced by a root in another git repository, named by `root`.
EXTERNAL: Final = "external"
#: The managed walk does not produce this display at all — the file is gone, or no
#: configured root reaches it any more. A record may still name it; that is staleness, and
#: this module reports the state rather than deciding what it means.
ABSENT: Final = "absent"
#: More than one configured root spells a file this way, so which repository answers for it
#: is not decided. Guessing is how an exception gets verified against the wrong boundary.
AMBIGUOUS: Final = "ambiguous"


@dataclass(frozen=True)
class Binding:
    """Where one display is verified, in one snapshot."""

    display: str
    state: str
    root: str | None = None
    source: str | None = None
    """The declared `[[paths.sources]]` name that owns `root`, or None when the root
    sits in no declared source — which adoption refuses to record from, and which every other
    check reads exactly as before."""
    git_root: Path | None = None
    revision: str | None = None
    exists: bool = True

    @property
    def identity(self) -> tuple[str, str | None, str | None]:
        """What must not change between two snapshots while an entry survives in both.

        The repository *and* the revision, together. Either alone is a discriminator that
        is not the property: comparing recorded pin strings misses a boundary that moved
        under a name, and comparing roots misses an entry re-pointed at another repository
        by a configuration edit that never touched a pin.

        The repository is the declared *source name* rather than the root: two roots in one
        repository are one boundary, and a root moved from one declared source to another is a
        change of boundary even when neither spelling moved. An undeclared root falls back to
        its own spelling, so two of those are still told apart.

        `git_root` is left out on purpose. It is where this checkout happens to have put
        the repository, which is a fact about the machine and not about the binding; a
        sibling cloned to a different directory is the same boundary.
        """
        owner = self.source if self.source is not None else self.root
        return (self.state, owner, self.revision)


@dataclass(frozen=True)
class SourceMap:
    """One snapshot's resolution of every managed display to the repository behind it."""

    repo_root: Path
    walk: tuple[tuple[Path, str], ...]
    boundaries: tuple[SourceBoundary, ...]
    configured_roots: tuple[str, ...]
    missing_roots: tuple[str, ...]
    pins: dict[str, str] = field(default_factory=dict, repr=False)
    ambiguous: frozenset[str] = frozenset()
    record_unreadable: bool = False
    """The record could not be parsed, so `pins` is empty because nothing was recorded — not
    because nothing was pinned. Carried rather than swallowed: a consumer that treats an
    unpinned external root as merely unpinned would recommend pinning it, and the repair for
    a corrupt file is not to write more into it. The `adoption-record` pass reports the
    condition itself."""
    declared: dict[str, str] = field(default_factory=dict, repr=False)
    """Declared source name -> its path. Empty in a single-repository project, and in a
    siblings one that records no cross-repository debt."""
    refs: dict[str, str] = field(default_factory=dict, repr=False)
    """Declared source name -> the ref a pin has to be contained in."""
    _source_of_root: dict[str, str] = field(default_factory=dict, repr=False)
    _external: dict[str, SourceBoundary] = field(default_factory=dict, repr=False)
    _own: frozenset[str] = frozenset()

    def source_of_root(self, root: str) -> str | None:
        """The declared source a configured root sits in, or None when none covers it.

        At most one can, because the configuration refuses two declared paths that overlap, so
        this is a lookup rather than a precedence rule."""
        return self._source_of_root.get(root)

    @property
    def undeclared_external_roots(self) -> tuple[str, ...]:
        """Cross-repository roots no declared source covers.

        Reading them is unchanged. Recording adoption debt from one is refused: there would be
        no name for the record to bind an entry to and no ref to check a pin against, so the
        entry would rest on the walk resolving the same way forever."""
        return tuple(
            sorted(
                boundary.root
                for boundary in self.boundaries
                if boundary.root not in self._source_of_root
            )
        )

    outside_the_walk: tuple[str, ...] = ()
    """Configured roots inside this git repository but outside the tree walked from.
    Neither local nor cross-repository, and verifiable by neither half; see
    `adoption.roots_outside_the_walk`."""

    @property
    def split_sources(self) -> tuple[str, ...]:
        """Declared sources whose configured roots sit in more than one repository.

        A declared `path` is meant to be a repository's own root, and nothing in the
        configuration can check that — it is a fact about the filesystem. Declaring a common
        ancestor such as `..` instead matches every root beneath it, and then one pin stands
        for two histories: the second repository's entries get read against the first
        repository's commit, and a path that exists in both reads as history it never had.

        Reported rather than resolved. Picking one of the two repositories is exactly the
        guess that makes an exception verifiable against the wrong history.
        """
        seen: dict[str, set[Path]] = {}
        for boundary in self.boundaries:
            source = self._source_of_root.get(boundary.root)
            if source is None or boundary.git_root is None:
                continue
            seen.setdefault(source, set()).add(boundary.git_root)
        return tuple(sorted(name for name, roots in seen.items() if len(roots) > 1))

    def boundary_for_source(self, source: str) -> SourceBoundary | None:
        """Any boundary belonging to one declared source. Two roots in one repository
        share its git root, so either answers what is asked of the repository."""
        for boundary in self.boundaries:
            if self._source_of_root.get(boundary.root) == source:
                return boundary
        return None

    @property
    def displays(self) -> frozenset[str]:
        """Every display the managed walk produced, ambiguous ones included."""
        return frozenset(display for _, display in self.walk)

    def binding(self, display: str) -> Binding:
        """Where `display` is verified in this snapshot. Never guesses, never falls back."""
        if display in self.ambiguous:
            return Binding(display, AMBIGUOUS)
        boundary = self._external.get(display)
        if boundary is not None:
            return Binding(
                display,
                EXTERNAL,
                root=boundary.root,
                git_root=boundary.git_root,
                source=self._source_of_root.get(boundary.root),
                revision=self.pins.get(self._source_of_root.get(boundary.root, "")),
                exists=boundary.exists,
            )
        if display in self._own:
            return Binding(display, OWN)
        return Binding(display, ABSENT)

    def external_entries(self, entries: frozenset[str]) -> dict[str, list[str]]:
        """Which of `entries` each external root produced, keyed by root.

        Every external root appears, including ones with no entries and ones whose tree is
        not checked out: a root that resolved nothing is the state a missing checkout and a
        fully documented root have in common, and the difference between them is a question
        for validation, which cannot ask it about a root it was never told about.
        """
        grouped: dict[str, list[str]] = {boundary.root: [] for boundary in self.boundaries}
        for display, boundary in self._external.items():
            if display in entries and boundary.root in grouped:
                grouped[boundary.root].append(display)
        return grouped

    def boundary_for_root(self, root: str) -> SourceBoundary | None:
        for boundary in self.boundaries:
            if boundary.root == root:
                return boundary
        return None


def build_source_map(repo_root: Path, config: object, record: AdoptionRecord) -> SourceMap:
    """Resolve one snapshot: this configuration, this record, the tree as it stands.

    `record` is passed in rather than read, because the base snapshot's record is a git blob
    and not a file on disk. The tree is shared — there is one working directory, and a
    sibling repository is checked out once — so a base binding is the base's configuration
    and record read against the checkout that exists, and nothing pretends otherwise.
    """
    from irminsul.adoption import (
        _configured_roots,
        boundary_for_displays,
        cross_repo_source_boundaries,
        managed_walk,
        missing_configured_roots,
        roots_outside_the_walk,
    )

    walked = managed_walk(repo_root, config)
    boundaries = tuple(cross_repo_source_boundaries(repo_root, config))
    external, ambiguous = boundary_for_displays(repo_root, config, walked)
    displays = {display for _, display in walked}
    return SourceMap(
        repo_root=repo_root,
        walk=tuple(walked),
        boundaries=boundaries,
        configured_roots=tuple(_configured_roots(config)),
        missing_roots=tuple(missing_configured_roots(repo_root, config)),
        outside_the_walk=tuple(roots_outside_the_walk(repo_root, config)),
        pins={source.source: source.revision for source in record.sources},
        ambiguous=frozenset(ambiguous),
        declared={spec.name: spec.path for spec in _declared(config)},
        refs={spec.name: spec.ref for spec in _declared(config)},
        _source_of_root=_roots_by_source(boundaries, _declared(config)),
        _external=dict(external),
        _own=frozenset(displays - set(external) - ambiguous),
    )


def _declared(config: object) -> list[SourceSpec]:
    paths = getattr(config, "sources", None) or getattr(config, "paths", None)
    return list(getattr(paths, "sources", None) or [])


def _roots_by_source(
    boundaries: tuple[SourceBoundary, ...], declared: list[SourceSpec]
) -> dict[str, str]:
    """Which declared source each cross-repository root sits in.

    Compared on normalized spellings rather than resolved filesystem paths, so the answer is a
    fact about the configuration and reads the same on every machine. The configuration already
    refuses two declared paths that overlap, so no root matches two and there is no order to
    resolve.
    """
    out: dict[str, str] = {}
    for boundary in boundaries:
        root = posixpath.normpath(boundary.root)
        for spec in declared:
            path = posixpath.normpath(spec.path)
            if root == path or root.startswith(f"{path}/"):
                out[boundary.root] = spec.name
                break
    return out


def record_stamp(repo_root: Path, config: object) -> tuple[object, ...]:
    """A cheap signature of the one input a `SourceMap` re-reads after its graph exists.

    Three inputs, three different lifetimes, and only one of them needs watching:

    - **The configuration** is the graph's own `IrminsulConfig` object, loaded once and never
      mutated. A map built from it cannot go stale against it, and stamping `irminsul.toml`
      would suggest otherwise — a rewritten file is not the configuration this graph has.
    - **The tree** is what the graph itself walked. A map hung on a graph is exactly as stale
      as the graph, which is the existing contract for every check; giving the map a stricter
      one would be a promise the thing it hangs off does not keep.
    - **The record** is neither. The graph never reads it, so it can be rewritten under a
      caller that goes on holding the same graph — a test, a long-lived server, a `fix` pass
      — and the pins would be the ones from before the write. So its contents are digested
      and the map is rebuilt when the digest moves.

    Absent stamps as None rather than raising: no record is the ordinary state, and it has to
    be distinguishable from a record that appears later.

    A digest of the bytes, not their size and modification time. Size and mtime are the
    cheaper signal and they miss the edit that matters most: a pin is forty hexadecimal
    characters, so moving a boundary rewrites the file to exactly the same length, and the
    system clock's resolution is coarse enough that two writes in quick succession share an
    mtime to the nanosecond. Measured on Windows, rewriting a record with a different pin left
    `(st_size, st_mtime_ns)` identical — the stale answer would have been served, and the
    thing it was stale about is the boundary. Reading a small JSON file on the handful of
    accesses a run makes is nothing beside the git subprocesses on either side of it.
    """
    from irminsul.adoption import record_path

    try:
        data = record_path(repo_root, config).read_bytes()
    except OSError:
        return (None,)
    return (hashlib.sha256(data).hexdigest(),)


__all__ = [
    "ABSENT",
    "AMBIGUOUS",
    "EXTERNAL",
    "OWN",
    "Binding",
    "SourceMap",
    "build_source_map",
    "record_stamp",
]
