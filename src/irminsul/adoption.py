"""The managed files that had no owner on the day a repository adopted Irminsul.

Both ownership rules ship with a progressive half, and for the same reason: switching a
check on must not turn an existing tree red before anyone has agreed to anything.
`uniqueness` reports an unowned source file only inside a *doc-covered directory*, and
`test-ownership` reports an unowned test only beside one already owned or inside a
declared `paths.test_roots`. Both are guesses at the same question — *is this file new,
or was it already here?* — answered from the shape of the tree because nothing recorded
the answer.

This module records the answer. An adoption record is the exhaustive list of managed
files that had no owner when the record was written, by exact repository-relative path.
It is not a mode and it enables nothing: every check runs from the first day either way.
What it changes is that the covered-directory guess stops being needed, because a file
that is not on the list and not owned is, provably, new.

That makes the record *stricter* than the guess it replaces, not weaker. Before it, a
whole undocumented sibling tree was invisible; after it, only the enumerated files are
excepted, and only from the one finding that says they have no owner. Nothing else is
suppressed, no other check is affected, and no glob or directory is ever excepted — a
pattern would silently adopt files written next year.

An entry retires when its file gains an owner, is deleted, or is renamed: the record
names paths, so a moved file is a file the record does not name. Entries never come
back. `check --update-adoption` removes retired ones and refuses to add any, and
`diff-integrity` fails a change that grows the record or that edits a recorded file
without documenting it.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from irminsul.docgraph import DocGraph
    from irminsul.source_map import SourceMap

#: A full git object id, the only spelling a pin may take. Both hash lengths, so a
#: repository using sha256 object format is not locked out.
_OBJECT_ID: Final = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")

ADOPTION_VERSION: Final = 1


class AdoptionError(Exception):
    """The adoption record is unreadable, or the operation asked for is not allowed."""


@dataclass(frozen=True)
class AdoptionSource:
    """The revision of one declared source repository that a record's entries are history at.

    `source` is the `name` of a `[[paths.sources]]` entry, not a path. A name survives
    somebody moving the checkout and does not survive somebody pointing the name at another
    repository, which is the property wanted: keyed by root, editing `source_roots`
    re-pointed existing entries at a different history with no pin having changed.

    Nothing else is recorded, and a remote URL deliberately is not. A commit id is only
    resolvable in a repository that actually holds that history, so the revision
    identifies the repository by being verifiable in it; a URL beside it would be a
    hand-written assertion with nothing checking it, which is the drift this project
    exists to catch.
    """

    source: str
    revision: str


@dataclass(frozen=True)
class AdoptionRecord:
    """One adoption record, as read from disk."""

    unowned: frozenset[str] = frozenset()
    adopted_at: str | None = None
    sources: tuple[AdoptionSource, ...] = ()
    bindings: Mapping[str, str] = field(default_factory=dict)
    """Display path -> declared source name, for the entries that came from another
    repository. Absent for a file in this repository, which is why a single-repository
    record is a plain list of strings and reads exactly as it always has."""

    def __bool__(self) -> bool:
        return bool(self.unowned)

    def revision_for(self, source: str | None) -> str | None:
        """The pinned revision for one declared source, or None when unpinned."""
        if source is None:
            return None
        for item in self.sources:
            if item.source == source:
                return item.revision
        return None


@dataclass(frozen=True)
class ShrinkResult:
    """What `--update-adoption` did, or why it refused.

    `added` is never applied. A record that could grow under an ordinary update is a
    record that excuses the debt a change just created, which is the whole thing the
    seal exists to stop.
    """

    added: list[str] = field(default_factory=list)
    removed: int = 0
    kept: int = 0


def record_path(repo_root: Path, config: object) -> Path:
    """Where this repository keeps its adoption record."""
    paths = getattr(config, "paths", None)
    name = getattr(paths, "adoption", ".irminsul-adoption.json")
    return repo_root / name


def load_record(path: Path) -> AdoptionRecord:
    """Read the record, or an empty one when the repository has none.

    A repository without a record is the ordinary case, not an error: it has either
    always been documented or never adopted, and both keep the progressive rules.
    """
    if not path.is_file():
        return AdoptionRecord()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        # `UnicodeDecodeError` is a ValueError, not an OSError, so a record an editor saved
        # as UTF-16 used to end the run in a traceback before a single finding printed —
        # including the one whose explanation says how to repair the file.
        raise AdoptionError(f"could not read the adoption record {path.name}: {e}") from e
    if not isinstance(payload, dict) or payload.get("version") != ADOPTION_VERSION:
        raise AdoptionError(
            f"adoption record {path.name} has unsupported format; expected version "
            f"{ADOPTION_VERSION}"
        )
    raw = payload.get("unowned")
    if not isinstance(raw, list):
        raise AdoptionError(
            f"adoption record {path.name} is missing its `unowned` list of exact paths"
        )
    unowned, bindings = _read_entries(path, raw)
    adopted_at = payload.get("adopted_at")
    return AdoptionRecord(
        unowned=unowned,
        adopted_at=str(adopted_at) if isinstance(adopted_at, str) else None,
        sources=_read_sources(path, payload.get("sources")),
        bindings=bindings,
    )


def _read_entries(path: Path, raw: list[object]) -> tuple[frozenset[str], dict[str, str]]:
    """The recorded paths, and which declared source each one that has one came from.

    Two spellings, and the difference is the whole of the format change. A **string** is a
    file in this repository, which is every entry a single-repository project writes — so
    such a record is byte-for-byte what it always was. An **object** is a file from another
    repository and states the source it came from, because an entry that left its binding to
    be re-derived from `paths.source_roots` was an entry a configuration edit could
    re-point at a different history.

    Anything else is an error rather than a skip, and a missing or empty `source` is an error
    rather than a fall back to "this repository". Guessing which repository answers for a
    file is how an exception gets verified against the wrong one.
    """
    unowned: set[str] = set()
    bindings: dict[str, str] = {}
    for item in raw:
        if isinstance(item, str):
            if not item:
                raise AdoptionError(f"adoption record {path.name} has an empty path in `unowned`")
            unowned.add(item)
            continue
        if not isinstance(item, dict):
            raise AdoptionError(
                f"adoption record {path.name} has an `unowned` entry that is neither a path "
                "nor a {path, source} object"
            )
        display, source = item.get("path"), item.get("source")
        if not isinstance(display, str) or not display:
            raise AdoptionError(
                f"adoption record {path.name} has an `unowned` object without a string `path`"
            )
        if not isinstance(source, str) or not source:
            raise AdoptionError(
                f"adoption record {path.name} names `{display}` without a `source`. An entry "
                "from another repository states which declared source it came from; a file in "
                "this repository is written as a plain path"
            )
        if display in bindings and bindings[display] != source:
            raise AdoptionError(
                f"adoption record {path.name} binds `{display}` to both {bindings[display]!r} "
                f"and {source!r}; one entry has one source"
            )
        unowned.add(display)
        bindings[display] = source
    return frozenset(unowned), bindings


def _read_sources(path: Path, raw: object) -> tuple[AdoptionSource, ...]:
    """The pinned source revisions, or `()` when the record names none.

    Absent is the same-repository case and the ordinary one, so it is not an error here.
    A record that *needs* a pin and has none is decided where the exception is granted,
    not while reading the file: this function cannot know which roots are cross-repo.

    A malformed entry is an error rather than a skip. Dropping it would leave a record
    that looks pinned, reads as pinned, and excepts files against a revision nobody
    recorded.
    """
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise AdoptionError(
            f"adoption record {path.name} has a `sources` that is not a list of "
            "{name, revision} entries"
        )
    out: list[AdoptionSource] = []
    for item in raw:
        name = item.get("name") if isinstance(item, dict) else None
        revision = item.get("revision") if isinstance(item, dict) else None
        if not isinstance(name, str) or not isinstance(revision, str) or not name or not revision:
            raise AdoptionError(
                f"adoption record {path.name} has a `sources` entry without a string "
                "`name` and `revision`. A pin names a declared source from "
                "`[[paths.sources]]`; a record that pins a path instead predates that and "
                "is migrated once with `check --pin-adoption-sources`"
            )
        if not _OBJECT_ID.fullmatch(revision):
            # A symbolic name is not a boundary. `HEAD` and a branch name both resolve, so
            # they verify — against whatever the sibling repository happens to be now — and
            # because the recorded string never changes, nothing can see the boundary moving
            # forward. A record pinned at `HEAD` accepted a file committed yesterday as
            # pre-existing debt.
            raise AdoptionError(
                f"adoption record {path.name} pins '{name}' at {revision!r}, which is not a "
                "commit id. A boundary has to be a fixed point, and a name is not one; "
                "record the full hexadecimal id of the commit adopted at."
            )
        out.append(AdoptionSource(source=name, revision=revision))
    seen = [source.source for source in out]
    if len(set(seen)) != len(seen):
        raise AdoptionError(
            f"adoption record {path.name} pins the same source twice in `sources`; one "
            "source has one adoption revision"
        )
    return tuple(out)


def load_debt(path: Path) -> frozenset[str]:
    """Just the excepted paths, which is all a check needs."""
    return load_record(path).unowned


def init_adoption(
    path: Path,
    unowned: list[str],
    adopted_at: str | None = None,
    sources: Sequence[AdoptionSource] = (),
    bindings: Mapping[str, str] | None = None,
) -> int:
    """Write the record from the tree as it stands. Returns the entry count.

    Refuses to overwrite: a second run after the first documents have landed would
    re-record whatever debt exists *then*, which is how a record grows back.
    """
    if path.exists():
        raise AdoptionError(
            f"adoption record {path.name} already exists; run --update-adoption to retire "
            "entries that are now owned, since a record only shrinks"
        )
    _write(path, sorted(set(unowned)), adopted_at, sources, bindings)
    return len(set(unowned))


def _refuse_unanchored(smap: SourceMap, source: str, revision: str) -> None:
    """Refuse to carry a pin that is not on the history its source declares.

    Migration copies a revision across rather than choosing one, which is what makes it safe
    — and would make it the way round the anchoring obligation if it copied without asking.
    A record written before refs existed was never checked against one, so a legacy pin on a
    side branch is exactly the state this has to catch: converting it would leave a boundary
    the adopting change's own rule would have rejected, and the rule does not run again
    afterwards because the pin cannot move.
    """
    from irminsul.git.changes import is_ancestor, resolve_ref

    ref = smap.refs.get(source)
    boundary = smap.boundary_for_source(source)
    if ref is None or boundary is None or boundary.git_root is None:
        raise AdoptionError(
            f"cannot migrate the pin for source {source!r}: its repository is not checked out "
            "here, or it declares no ref, so whether the recorded boundary is on that "
            "history cannot be established. Check the repository out and declare its ref."
        )
    tip = resolve_ref(boundary.git_root, ref)
    if tip is None:
        raise AdoptionError(
            f"cannot migrate the pin for source {source!r}: {ref!r} is not in this checkout "
            f"of {boundary.git_root}, so the boundary cannot be placed on that history. Fetch "
            "the ref and run this again."
        )
    if not is_ancestor(boundary.git_root, revision, tip):
        raise AdoptionError(
            f"the recorded boundary for source {source!r}, {revision[:12]}, is not on {ref!r}. "
            "A record written before refs existed was never checked against one, and carrying "
            "this pin forward would keep a boundary off the declared history that a first "
            "record would be refused for. Re-adopt against a commit on that ref: delete the "
            "record and run `check --init-adoption`, reviewing the entries it writes."
        )


def migrate_record(repo_root: Path, config: object, path: Path) -> list[str]:
    """Rewrite a record written before entries and pins named their source.

    The old shape keyed pins by configured root and left every entry a bare path, so which
    repository answered for an entry was re-derived from `paths.source_roots` on every run.
    The conversion is mechanical and takes nothing from anywhere else: each pinned root
    becomes the source that *currently* declares it, with its revision copied across
    unchanged, and each entry the walk resolves to a repository states that repository.

    Nothing is guessed. A pinned root no declared source covers, two roots of one pinned
    repository disagreeing about the revision, or an entry whose display resolves nowhere —
    each ends the migration with a message naming it, because a record is the evidence for
    every exception it holds and a converted one has to mean exactly what the old one meant.

    Returns the lines describing what changed, for the caller to print. Raises
    `AdoptionError` with the reason when it will not convert.
    """
    import json as _json

    from irminsul.source_map import build_source_map

    try:
        payload = _json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, _json.JSONDecodeError) as e:
        raise AdoptionError(f"could not read the adoption record {path.name}: {e}") from e
    if not isinstance(payload, dict):
        raise AdoptionError(f"adoption record {path.name} is not an object")
    raw_sources = payload.get("sources")
    raw_unowned = payload.get("unowned")
    if not isinstance(raw_sources, list) or not isinstance(raw_unowned, list):
        raise AdoptionError(
            f"adoption record {path.name} has no `sources` and `unowned` to migrate"
        )

    smap = build_source_map(repo_root, config, AdoptionRecord())
    revisions: dict[str, str] = {}
    notes: list[str] = []
    for item in raw_sources:
        if not isinstance(item, dict) or not isinstance(item.get("revision"), str):
            raise AdoptionError(f"adoption record {path.name} has a `sources` entry to hand")
        revision = str(item["revision"])
        if isinstance(item.get("name"), str):
            # Anchored like any other pin this migration keeps. A partially migrated record
            # holds both spellings, and seeding from the named one unchecked meant the later
            # root entry found the revision already held and skipped the check too — so a
            # side-branch commit could be rewritten into the valid schema, after which the
            # gate never asks again because it is not a first record and the string did not
            # change.
            named = str(item["name"])
            if named not in revisions:
                _refuse_unanchored(smap, named, revision)
            revisions.setdefault(named, revision)
            continue
        root = item.get("root")
        if not isinstance(root, str):
            raise AdoptionError(
                f"adoption record {path.name} has a `sources` entry with neither a `name` "
                "nor a `root`, so there is nothing to convert it from"
            )
        source = smap.source_of_root(root)
        if source is None:
            raise AdoptionError(
                f"adoption record {path.name} pins '{root}', which no `[[paths.sources]]` "
                "entry covers. Declare the repository that root belongs to and run this "
                "again; picking a source for it would be inventing the boundary the pin is"
            )
        held = revisions.get(source)
        if held is not None and held != revision:
            raise AdoptionError(
                f"adoption record {path.name} pins two roots of source {source!r} at "
                f"different revisions ({held[:12]} and {revision[:12]}). One repository has "
                "one boundary, and choosing between them would move it for half the entries"
            )
        if held is None:
            _refuse_unanchored(smap, source, revision)
            revisions[source] = revision
            notes.append(f"  '{root}' at {revision[:12]} is now source '{source}'")

    bindings: dict[str, str] = {}
    unowned: set[str] = set()
    for item in raw_unowned:
        if isinstance(item, dict) and isinstance(item.get("path"), str):
            unowned.add(str(item["path"]))
            if isinstance(item.get("source"), str):
                bindings[str(item["path"])] = str(item["source"])
            continue
        if not isinstance(item, str):
            raise AdoptionError(f"adoption record {path.name} has an `unowned` entry to hand")
        unowned.add(item)
        binding = smap.binding(item)
        if binding.source is not None:
            bindings[item] = binding.source
            notes.append(f"  '{item}' now states it comes from '{binding.source}'")
    _write(
        path,
        sorted(unowned),
        payload.get("adopted_at") if isinstance(payload.get("adopted_at"), str) else None,
        [AdoptionSource(source=name, revision=rev) for name, rev in sorted(revisions.items())],
        bindings,
    )
    return notes


def rewrite_sources(path: Path, record: AdoptionRecord, sources: Sequence[AdoptionSource]) -> None:
    """Replace the record's pins, keeping everything else, without ever removing the file.

    `init_adoption` refuses to overwrite — that refusal is what stops a second adoption —
    so the pin command used to unlink the record and call it, which opens a window where a
    failed write leaves no record at all and nothing that will rebuild one.
    """
    if not path.is_file():
        raise AdoptionError(f"no adoption record at {path.name}; create one with --init-adoption")
    _write(path, sorted(record.unowned), record.adopted_at, sources, record.bindings)


def shrink_adoption(path: Path, still_unowned: set[str]) -> ShrinkResult:
    """Retire the entries that are now owned, deleted or moved; refuse to add any."""
    if not path.is_file():
        raise AdoptionError(f"no adoption record at {path.name}; create one with --init-adoption")
    record = load_record(path)
    added = sorted(still_unowned - record.unowned)
    if added:
        return ShrinkResult(added=added)
    kept = record.unowned & still_unowned
    # The pins carry over untouched. `--update-adoption` retires entries; the revision an
    # entry was history at is not a thing that retires, and rewriting it here would let
    # routine housekeeping move the adoption boundary forward.
    _write(
        path,
        sorted(kept),
        record.adopted_at,
        record.sources,
        {display: record.bindings[display] for display in kept if display in record.bindings},
    )
    return ShrinkResult(removed=len(record.unowned) - len(kept), kept=len(kept))


@dataclass(frozen=True)
class SourceBoundary:
    """One configured source root that answers to a git repository of its own.

    `prefix` is where the root sits inside that repository, so a record entry's display
    path — which is relative to the root — becomes a path the repository's own history can
    be asked about. With `source_roots = ["../code/src"]` the repository is `../code`, the
    prefix is `src`, and the entry `a.py` is `src/a.py` at the pinned revision.
    """

    root: str
    tree: Path
    git_root: Path | None
    prefix: str
    exists: bool = True
    """Whether the tree is on disk. An absent one used to be dropped from the boundary
    list, which made a missing sibling checkout the *quietest* state there is: nothing
    resolved to it, so nothing was pinned, checked or reported, and the gate went green on
    a tree it could not see. Absence is an answer here, not a reason to stop asking."""

    def git_path(self, display: str) -> str:
        """A display path as the owning repository spells it."""
        return f"{self.prefix}/{display}" if self.prefix else display


def _configured_roots(config: object) -> list[str]:
    """Every root the managed walk reads, source and test alike, in order and deduplicated.

    `paths.test_roots` is not a source root and the ordinary walk does not reach it, but
    the record covers tests too — so a declared test tree in another repository can put
    entries in the record. Leaving it out of the boundary list was a way to fail open:
    those entries resolved to no boundary, so nothing pinned them and nothing checked them,
    and a brand-new cross-repo test hand-added to the record was accepted in silence.
    """
    paths = getattr(config, "paths", None)
    seen: dict[str, None] = {}
    for rel in (
        *(getattr(paths, "source_roots", []) or []),
        *(getattr(paths, "test_roots", []) or []),
    ):
        seen.setdefault(rel, None)
    return list(seen)


def roots_outside_the_walk(repo_root: Path, config: object) -> list[str]:
    """Configured roots inside this git repository but outside the tree walked from.

    A monorepo where Irminsul runs from a subdirectory can point a root at a sibling
    directory of that subdirectory: same repository, outside `repo_root`. It is not
    cross-repository, so no boundary is made for it and its files are treated as locally
    verifiable — but nothing can actually place them. The walk spells them relative to the
    root (`a.py`), the seal only counts a display as this repository's when it is
    `repo_root`-relative, and git reports the change under its worktree path
    (`code/src/a.py`). So a first record could name a file the same change added with neither
    the historical-presence check nor touch-to-own matching it.

    Reported rather than repaired. Mapping the display into the worktree is a real design
    with its own questions — two roots could spell one worktree path, and the diff's own
    changed set is `repo_root`-relative — and inventing half of it here is how an exception
    ends up resting on a coincidence. Run Irminsul from the worktree root, or bring the root
    under it.
    """
    from irminsul.git.mtime import git_root_for

    own = git_root_for(repo_root)
    if own is None:
        return []
    enclosing, here = own.resolve(), repo_root.resolve()
    if enclosing == here:
        return []
    out: list[str] = []
    for rel in _configured_roots(config):
        tree = (repo_root / rel).resolve()
        if tree.is_relative_to(enclosing) and not tree.is_relative_to(here):
            out.append(rel)
    return out


def missing_configured_roots(repo_root: Path, config: object) -> list[str]:
    """Configured roots that are not on disk, so the walk cannot see the files under them.

    An absent root makes the managed walk quietly smaller, and anything that reads "no
    unowned files left" off that walk reads it as "everything is documented". For
    `--update-adoption` that is the difference between retiring the entries whose work is
    done and emptying the record, which nothing but git can undo.
    """
    return [rel for rel in _configured_roots(config) if not (repo_root / rel).is_dir()]


def managed_walk(repo_root: Path, config: object) -> list[tuple[Path, str]]:
    """Every managed file as `(absolute path, display)`, test roots included.

    One walk for both ownership rules and for the boundary resolution, because the record
    is one list: a display that only the test walk returns still has to resolve to the
    repository it came from.

    A test-root pair whose display the source walk already produced is *kept*, not dropped.
    Two roots that spell one file the same way is an ambiguity, and `boundary_for_displays`
    is what reports it; deduplicating here silenced it, and the surviving single entry then
    excepted a file under both ownership policies while being verified against one
    repository. `globs` never compares the separately walked test root, so nothing else
    would have said so either.
    """
    from irminsul.checks.globs import walk_configured_source_files

    walked = list(walk_configured_source_files(repo_root, config).files)  # type: ignore[arg-type]
    if getattr(getattr(config, "paths", None), "test_roots", None):
        from irminsul.checks.owned_tests import TestOwnershipCheck

        seen_pairs = set(walked)
        walked += [
            pair
            for pair in walk_configured_source_files(
                repo_root,
                TestOwnershipCheck._scoped(config),  # type: ignore[arg-type]
            ).files
            if pair not in seen_pairs
        ]
    return walked


def cross_repo_source_boundaries(repo_root: Path, config: object) -> list[SourceBoundary]:
    """Every configured root — source or test — owned by a git repository other than this one.

    This is the same question `delta.cross_repo_trees` asks and the same primitive
    (`git_root_for`) answers it, but the answers differ in what they carry: delta needs
    only the names of the roots it must refuse, and adoption needs the repository and the
    offset, because it has to read history out of them.

    A root with no `.git` above it is returned with `git_root` set to None rather than
    dropped. Dropping it was a way to fail open: the code repository's `.git` removed, or
    never cloned, took the whole root out of the boundary list, and its entries went on
    excepting files with nothing left to check them against. "Outside this repository" is
    the test, and whether a repository can be found there is the answer, not the filter.

    A root missing from disk entirely *is* skipped. The source walk reports it already, and
    a root with no files contributes no entries for a boundary to be about.
    """
    from irminsul.git.mtime import git_root_for

    own = git_root_for(repo_root)
    own_resolved = own.resolve() if own is not None else None
    # What "inside this repository" means when this repository is in no git at all — a
    # scaffold nobody has committed yet, which is an ordinary state here and only a hint
    # (`history-depth/no-history`). Falling back to the invocation directory keeps its own
    # source roots same-repo: they do not become another repository's files because no
    # repository has been initialized. Without it a plain `--init-adoption` in an
    # uncommitted project refused, having decided `src` was somebody else's.
    contains = own_resolved if own_resolved is not None else repo_root.resolve()
    out: list[SourceBoundary] = []
    for rel in _configured_roots(config):
        tree = (repo_root / rel).resolve()
        if tree.is_relative_to(contains):
            # Inside this repository. A missing one is the source walk's business — it
            # reports `globs/missing-source-root` — and the diff's merge base governs its
            # files either way, so there is no boundary to establish.
            continue
        if not tree.is_dir():
            # Outside this repository and not checked out. `resolve()` answers the "outside"
            # question by path arithmetic alone, so this is still known to be a cross-repo
            # root; what is unknown is everything else about it. `git_root_for` is not asked,
            # because walking up from a path that does not exist can land in an unrelated
            # repository and answer confidently with the wrong history.
            out.append(SourceBoundary(root=rel, tree=tree, git_root=None, prefix="", exists=False))
            continue
        owner = git_root_for(tree)
        owner_resolved = owner.resolve() if owner is not None else None
        if owner_resolved is not None and owner_resolved == own_resolved:
            continue
        prefix = ""
        if owner_resolved is not None:
            try:
                relative = tree.relative_to(owner_resolved).as_posix()
            except ValueError:  # pragma: no cover - resolve() makes this unreachable
                owner_resolved = None
            else:
                prefix = "" if relative == "." else relative
        out.append(SourceBoundary(root=rel, tree=tree, git_root=owner_resolved, prefix=prefix))
    return out


def pin_source_revisions(repo_root: Path, config: object) -> list[AdoptionSource]:
    """The revision each cross-repo source root is at right now, for a first record.

    Refuses rather than guessing. A root whose repository has no commit yet cannot supply
    an adoption boundary, and writing a record that claims one anyway is how a file added
    tomorrow becomes yesterday's debt.
    """
    from irminsul.git.changes import head_revision, merge_base, resolve_ref
    from irminsul.source_map import build_source_map

    smap = build_source_map(repo_root, config, AdoptionRecord())
    if stray := smap.outside_the_walk:
        raise AdoptionError(
            "these configured roots are inside this git repository but outside the tree "
            f"Irminsul walks from: {', '.join(repr(root) for root in stray)}. Their files "
            "cannot be placed in this repository's history by path — the walk spells them "
            "relative to the root and git reports them under the worktree — so neither the "
            "historical-presence check nor touch-to-own would match them, and a record naming "
            "them would rest on nothing. Run Irminsul from the worktree root, or bring the "
            "root under the tree it walks."
        )
    if split := smap.split_sources:
        raise AdoptionError(
            "these declared sources cover roots in more than one git repository: "
            f"{', '.join(repr(name) for name in split)}. A source is one repository, because "
            "one pin is one history: covering two means the second repository's files would be "
            "checked against the first one's commit, and a path that exists in both would read "
            "as history it never had. Declare each repository separately, with `path` naming "
            "its own root."
        )
    if undeclared := smap.undeclared_external_roots:
        raise AdoptionError(
            "these roots are in another repository and no `[[paths.sources]]` entry declares "
            f"them: {', '.join(repr(root) for root in undeclared)}. Adopting from a repository "
            "needs a name for the record to bind each entry to, and a `ref` to check the "
            "boundary against; declare the repository and run this again."
        )
    out: list[AdoptionSource] = []
    for boundary in cross_repo_source_boundaries(repo_root, config):
        source = smap.source_of_root(boundary.root)
        if source is None:  # pragma: no cover - refused above
            continue
        if any(item.source == source for item in out):
            continue
        if not boundary.exists:
            raise AdoptionError(
                f"source root '{boundary.root}' is in another repository and is not checked "
                f"out at {boundary.tree}. There is nothing to read a boundary from; check it "
                "out where `paths.source_roots` says it is."
            )
        if boundary.git_root is None:
            raise AdoptionError(
                f"source root '{boundary.root}' is outside this repository and no git "
                f"repository was found at or above {boundary.tree}. Its files cannot be "
                "shown to pre-date anything, so there is no boundary to record; clone the "
                "source repository, or configure a root that is versioned."
            )
        revision = head_revision(boundary.git_root)
        if revision is None:
            raise AdoptionError(
                f"source root '{boundary.root}' belongs to the git repository at "
                f"{boundary.git_root}, which has no commit to adopt at. The record would "
                "claim its files are pre-existing debt with nothing able to confirm it; "
                "commit the source repository first."
            )
        ref = smap.refs[source]
        resolved = resolve_ref(boundary.git_root, ref)
        if resolved is None:
            raise AdoptionError(
                f"source {source!r} declares ref {ref!r}, which the repository at "
                f"{boundary.git_root} does not have. The boundary has to be a point on that "
                "history, so there is nothing to record; fetch the ref (in CI, a checkout "
                "that includes it), or declare the one this checkout has."
            )
        boundary_revision = merge_base(boundary.git_root, revision, resolved)
        if boundary_revision is None:
            raise AdoptionError(
                f"source {source!r} is checked out at a commit with no common history with "
                f"{ref!r}, so no point on that ref is an ancestor of this checkout. Nothing "
                "here is a boundary on the declared history; check the source repository out "
                "on that ref."
            )
        # The merge base, not `HEAD`. A checkout sitting on a side branch would otherwise
        # pin a commit that the declared history never contained, and every file added on
        # that branch would be recorded as debt the declared history had — which is the
        # laundering the ref exists to stop. The merge base is the most recent point on the
        # declared history this checkout descends from, so a side branch pins its branch
        # point and its own new files are simply new.
        out.append(AdoptionSource(source=source, revision=boundary_revision))
    return out


def unpinnable_entries(
    repo_root: Path,
    config: object,
    unowned: Sequence[str],
    sources: Sequence[AdoptionSource],
) -> list[str]:
    """Entries the revision about to be pinned does not contain.

    The walk reads the source working tree and the pin names its committed `HEAD`, so an
    untracked file is recorded as debt and then disproved by the very next run. Writing a
    record that is already wrong is worse than refusing: `--init-adoption` will not
    overwrite, so the repair is to delete the record by hand.
    """
    from irminsul.git.changes import has_revision, tracked_paths_at_ref
    from irminsul.source_map import build_source_map

    pinned = {source.source: source.revision for source in sources}
    smap = build_source_map(repo_root, config, AdoptionRecord())
    out: list[str] = []
    at_revision: dict[str, set[str] | None] = {}
    for display in sorted(set(unowned)):
        binding = smap.binding(display)
        # Two questions with two answers. *Which revision* is the source's, because a
        # repository has one history however many roots reach into it. *How the file is
        # spelled inside it* is the root's, because `../code/src` and `../code/tests` sit at
        # different offsets — reading the spelling off the source's first root asked the
        # repository for `src/test_a.py` and was told, correctly, that no such file existed.
        boundary = smap.boundary_for_root(binding.root) if binding.root else None
        if boundary is None or boundary.git_root is None or binding.source is None:
            continue
        revision = pinned.get(binding.source)
        if revision is None or not has_revision(boundary.git_root, revision):
            continue
        if binding.source not in at_revision:
            at_revision[binding.source] = tracked_paths_at_ref(boundary.git_root, revision)
        known = at_revision[binding.source]
        if known is not None and boundary.git_path(display) not in known:
            out.append(display)
    return out


def boundary_for_displays(
    repo_root: Path,
    config: object,
    walked: Sequence[tuple[Path, str]],
) -> tuple[dict[str, SourceBoundary], set[str]]:
    """Which cross-repo root each walked display came from, and the ambiguous ones.

    A display is relative to the root that produced it, so two roots can spell one file
    the same way — `globs` reports that collision on its own. Here an ambiguous display is
    returned separately rather than resolved, because guessing which repository's history
    to ask is how an exception gets verified against the wrong boundary.
    """
    boundaries = cross_repo_source_boundaries(repo_root, config)
    found: dict[str, SourceBoundary] = {}
    ambiguous: set[str] = set()
    for source, display in walked:
        for boundary in boundaries:
            candidate = boundary.tree / display
            if candidate != source:
                continue
            if found.get(display, boundary).root != boundary.root:
                ambiguous.add(display)
            found[display] = boundary
    return {k: v for k, v in found.items() if k not in ambiguous}, ambiguous


@dataclass(frozen=True)
class DebtProblem:
    """Why one root's or one entry's claim to be pre-existing debt does not stand.

    `kind` is the difference between *cannot tell* and *know it is false*, and the two get
    different treatment. `unverifiable` names a root whose boundary could not be
    established: the entries under it keep excepting, because calling them new would be
    asserting the opposite of what nobody could check, and the run fails on this finding
    instead. `not_historical` names one entry the pinned revision proves was not there.
    """

    kind: str
    root: str
    detail: str
    display: str | None = None
    remedy: str = ""
    """What to do about it. Four conditions share the `unverifiable` kind and they do not
    share an answer — telling somebody to re-pin a boundary when two roots spell one file
    the same way sends them to the wrong file entirely."""


def verified_debt(
    repo_root: Path,
    config: object,
    record: AdoptionRecord,
    source_map: SourceMap | None = None,
) -> tuple[frozenset[str], list[DebtProblem]]:
    """The record's entries that may still except a file, and why any may not.

    Entries inside this repository are not touched here: their boundary is the diff's own
    merge base, which `diff-integrity` reads. Entries from a source root in another
    repository have no such boundary — this repository's history says nothing about that
    one — so each is checked against the revision the record pinned for its root.

    Asked on every run rather than only on a diff, because the pin is in the record and
    needs no base to read. That is what lets a plain `check`, a nightly run and a
    source-repository gate all reach the same verdict.

    This is the validation half and it reads git history. `source_map` is the resolution
    half — which root produced each display, and whether two roots spell one the same way —
    and callers with a graph pass `graph.source_map` so one run resolves once. Pins are read
    from `record` rather than from the map, because the record is the thing being validated:
    a map built from some other record would answer about that one.
    """
    from irminsul.git.changes import has_revision, tracked_paths_at_ref
    from irminsul.source_map import build_source_map

    if not record.unowned:
        return record.unowned, []
    resolution = (
        source_map if source_map is not None else build_source_map(repo_root, config, record)
    )
    ambiguous = resolution.ambiguous
    # Grouped by declared source rather than by root, because the pin belongs to the
    # repository: two roots in one repository share one boundary, and keying by root let two
    # pins for one history drift apart. A root no source declares keys by its own spelling, so
    # it is still answered for rather than silently dropped.
    grouped: dict[str, tuple[SourceBoundary, list[str]]] = {}
    for root, displays in resolution.external_entries(record.unowned).items():
        boundary = resolution.boundary_for_root(root)
        if boundary is None:
            continue
        key = resolution.source_of_root(root) or root
        held = grouped.get(key)
        grouped[key] = (
            boundary if held is None else held[0],
            sorted(displays if held is None else [*held[1], *displays]),
        )
    # A source the record pinned but the config no longer declares still has to be answered
    # for: dropping the declaration is how an exception would stop being checked while the
    # entries it covers stay in the record.
    for pinned_source in record.sources:
        path = resolution.declared.get(pinned_source.source, pinned_source.source)
        grouped.setdefault(
            pinned_source.source, (SourceBoundary(path, repo_root / path, None, ""), [])
        )

    # The record's exceptions stand exactly as written. A file this proves was not there is
    # named by its own finding, which fails the run; dropping it from the debt as well would
    # report the same file twice, once as new and once as merely unowned.
    debt = record.unowned
    problems: list[DebtProblem] = []
    for stray in resolution.outside_the_walk:
        problems.append(
            DebtProblem(
                kind="unverifiable",
                root=stray,
                detail=(
                    f"'{stray}' is inside this git repository but outside the tree Irminsul "
                    "walks from, so its files cannot be placed in this repository's history by "
                    "path and no entry from it can be shown to pre-date anything"
                ),
                remedy=(
                    "run Irminsul from the worktree root, or bring the root under the tree it "
                    "walks; a root in between is verified by neither half"
                ),
            )
        )
    for name in resolution.split_sources:
        problems.append(
            DebtProblem(
                kind="unverifiable",
                root=name,
                detail=(
                    f"declared source '{name}' covers roots in more than one git repository, so "
                    "which history its pin belongs to is not decided and entries from one "
                    "repository would be checked against another's commit"
                ),
                remedy=(
                    "declare each repository separately in `paths.sources`, with `path` naming "
                    "its own root; one pin is one history"
                ),
            )
        )
    problems.extend(_binding_problems(record, resolution))
    for display in sorted(ambiguous & record.unowned):
        problems.append(
            DebtProblem(
                kind="unverifiable",
                root="",
                display=display,
                detail=(
                    f"more than one configured source root spells a file '{display}', so "
                    "which repository's history would answer for it is not decided"
                ),
                remedy=(
                    "narrow or widen one of the roots in `paths.source_roots` so each file "
                    "has one spelling; `globs` reports the same collision"
                ),
            )
        )
    for root in sorted(grouped):
        boundary, displays = grouped[root]
        revision = record.revision_for(root)
        # `root` is this group's key — the declared source name where there is one — and
        # `boundary.root` is a configured directory inside it. Tree-level problems name the
        # directory, because that is what is missing from disk; boundary-level ones name the
        # source, because that is what the record pinned.
        named = boundary.root
        if not boundary.exists:
            problems.append(
                DebtProblem(
                    kind="unverifiable",
                    root=root,
                    detail=(
                        f"'{named}' is a configured root in another repository and is not "
                        f"checked out at {boundary.tree}, so which of this record's entries "
                        "come from it — and whether they are history — cannot be read"
                    ),
                    remedy=(
                        "check the source repository out beside this one; in CI that is the "
                        "second `actions/checkout`, and its `path:` has to match "
                        "`paths.source_roots`"
                    ),
                )
            )
            continue
        if not displays:
            # The tree is here and the record names nothing from it. An ordinary siblings
            # repository with no cross-repo debt looks exactly like this, and so does one
            # whose entries for this root have all been documented. Asking anything of the
            # pin would fail a run over a boundary with nothing resting on it — which a
            # shallow clone or a squash-rewritten commit is enough to trigger.
            continue
        if boundary.git_root is None:
            problems.append(
                DebtProblem(
                    kind="unverifiable",
                    root=root,
                    detail=(
                        f"'{named}' is outside this repository and no git repository was found "
                        f"at or above {boundary.tree}, so which files it held when this "
                        "repository adopted cannot be read"
                    ),
                    remedy=(
                        "check the source repository out beside this one — the siblings "
                        "workflows do that with a second `actions/checkout`"
                    ),
                )
            )
            continue
        if revision is None:
            problems.append(
                DebtProblem(
                    kind="unverifiable",
                    root=root,
                    detail=(
                        f"{len(displays)} entr{'y' if len(displays) == 1 else 'ies'} come from "
                        f"'{root}', which is a separate git repository, and the record pins no "
                        "revision for it, so nothing establishes that those files already "
                        "existed when this repository adopted"
                    ),
                    remedy=(
                        "record the boundary once with `irminsul check "
                        "--pin-adoption-sources`, after checking the revision it reports is "
                        "the one this repository adopted at"
                    ),
                )
            )
            continue
        if not has_revision(boundary.git_root, revision):
            problems.append(_missing_pin_problem(root, revision, boundary))
            continue
        at_revision = tracked_paths_at_ref(boundary.git_root, revision)
        if at_revision is None:
            problems.append(
                DebtProblem(
                    kind="unverifiable",
                    root=root,
                    detail=(
                        f"the repository at {boundary.git_root} could not be read at "
                        f"{revision[:12]}, so which files existed then is unknown"
                    ),
                    remedy="check that repository is readable and its history is complete",
                )
            )
            continue
        for display in sorted(displays):
            # The display's own root supplies its spelling inside the repository; the group
            # supplies the revision. One source with two roots has one boundary and two
            # offsets.
            own = resolution.boundary_for_root(resolution.binding(display).root or "") or boundary
            if own.git_path(display) not in at_revision:
                problems.append(
                    DebtProblem(
                        kind="not_historical",
                        root=root,
                        display=display,
                        detail=(
                            f"'{display}' is recorded as debt that '{root}' already had, but it "
                            f"was not in that repository at {revision[:12]}, the revision this "
                            "record adopted"
                        ),
                    )
                )
    return debt, problems


def _missing_pin_problem(source: str, revision: str, boundary: SourceBoundary) -> DebtProblem:
    """Why the pinned revision is not readable here, as specifically as can be known.

    One condition used to carry three causes and one remedy, and they need different answers.
    A shallow clone is the overwhelmingly common one — `actions/checkout` clones to depth 1 —
    and is repaired by fetching. A full clone that still lacks the commit is either a
    repository that never had it or one whose history was rewritten, and **this cannot tell
    which from here**: saying the history is gone would be asserting something only the
    source repository can answer. So it says what it knows, names the command, and stops.
    """
    from irminsul.git.mtime import history_state

    assert boundary.git_root is not None
    _, shallow = history_state(boundary.git_root)
    if shallow:
        return DebtProblem(
            kind="unverifiable",
            root=source,
            detail=(
                f"the record pins source '{source}' at {revision[:12]}, and the clone at "
                f"{boundary.git_root} is shallow and does not reach it, so which files it held "
                "then cannot be read"
            ),
            remedy=(
                "fetch that repository's full history: `fetch-depth: 0` on its "
                "`actions/checkout` in CI, or `git fetch --unshallow` locally"
            ),
        )
    return DebtProblem(
        kind="unverifiable",
        root=source,
        detail=(
            f"the record pins source '{source}' at {revision[:12]}, and the complete clone at "
            f"{boundary.git_root} does not contain that commit. It is not in this checkout; "
            "whether that repository still has it elsewhere is a question only it can answer"
        ),
        remedy=(
            f"fetch it (`git -C {boundary.git_root} fetch origin {revision}`) if the "
            "repository still has it. If its history was rewritten past that commit, the "
            "boundary cannot be re-established from here: document those files, or re-adopt "
            "deliberately against a commit on the declared ref"
        ),
    )


def _binding_problems(record: AdoptionRecord, resolution: SourceMap) -> list[DebtProblem]:
    """Where the record's stated bindings and the configured sources disagree.

    Two independent statements about one entry: the record says which source it came from,
    and the configuration says which source the walk resolves its display to. Checking them
    against each other is the point of writing the binding down — a record that merely
    *had* a source field, trusted without comparison, would be the old
    re-derive-it-every-run behaviour with extra words.

    All three are refusals, never repairs. Picking one of two disagreeing answers is how an
    exception gets verified against the wrong repository, which is the whole failure this
    format exists to make impossible.
    """
    out: list[DebtProblem] = []
    for display in sorted(record.unowned):
        stated = record.bindings.get(display)
        binding = resolution.binding(display)
        resolved = binding.source
        if stated is None:
            if binding.state == "external":
                out.append(
                    DebtProblem(
                        kind="unverifiable",
                        root=resolved or binding.root or "",
                        display=display,
                        detail=(
                            f"'{display}' is written as a plain path, which means a file in "
                            f"this repository, but the walk resolves it to source "
                            f"{resolved!r} in another one"
                        ),
                        remedy=(
                            "state the source on the entry, or run "
                            "`irminsul check --pin-adoption-sources` to migrate a record "
                            "written before entries stated theirs"
                        ),
                    )
                )
            continue
        if stated not in resolution.declared:
            out.append(
                DebtProblem(
                    kind="unverifiable",
                    root=stated,
                    display=display,
                    detail=(
                        f"'{display}' is bound to source {stated!r}, which no "
                        "`[[paths.sources]]` entry declares, so there is no repository to "
                        "ask and no ref to check its boundary against"
                    ),
                    remedy=(
                        f"declare {stated!r} in `paths.sources`, or retire the entry; a "
                        "binding to a source that does not exist is not a boundary"
                    ),
                )
            )
            continue
        if binding.state == "absent":
            # The file is gone from the walk. That is staleness, which retires by the
            # ordinary update, and not a disagreement about where it came from.
            continue
        if resolved != stated:
            out.append(
                DebtProblem(
                    kind="unverifiable",
                    root=stated,
                    display=display,
                    detail=(
                        f"'{display}' is bound to source {stated!r}, and the configured roots "
                        f"resolve it to {resolved!r}; the record and the configuration "
                        "disagree about which repository answers for it"
                    ),
                    remedy=(
                        "restore the roots the entry was adopted under, or retire the entry "
                        "and document the file; an exception cannot change repository"
                    ),
                )
            )
    return out


def source_changed_displays(
    repo_root: Path, config: object, refs: Mapping[str | None, str]
) -> tuple[frozenset[str], list[str]]:
    """Display paths a source repository changed since `base_ref`, and the roots it failed on.

    The docs repository's own diff cannot see this. `source_roots` reach into another
    repository with its own history, so a pull request there produces no docs-repo diff at
    all, and touch-to-own — the rule that says editing recorded debt means documenting it —
    had nothing to read.

    `refs` maps a declared source name to the base ref to read in that repository, with `None`
    as the key for "every source". One ref for all was the only spelling, and it made the
    source-side gate unusable the moment two repositories spelled their default branch
    differently: a pull request in one supplied `origin/main`, the other could not resolve it,
    and the whole run exited 2. A named ref diffs the repository under review and leaves the
    others alone, which is what a pull request in one repository is about.

    A source named here whose repository cannot answer is returned in the second element
    rather than silently contributing nothing: a rule that quietly reads an empty change set
    is a rule that passes everything. A source *not* named is not asked, and contributes
    nothing for the same reason a docs-only run contributes nothing for it — no range was
    given for it.
    """
    from irminsul.git.mtime import diff_name_only
    from irminsul.source_map import build_source_map

    changed: set[str] = set()
    failed: list[str] = []
    resolution = build_source_map(repo_root, config, AdoptionRecord())
    for boundary in cross_repo_source_boundaries(repo_root, config):
        source = resolution.source_of_root(boundary.root)
        base_ref = refs.get(source) if source is not None else None
        if base_ref is None:
            base_ref = refs.get(None)
        if base_ref is None:
            continue
        if boundary.git_root is None:
            failed.append(boundary.root)
            continue
        paths = diff_name_only(boundary.git_root, base_ref, "HEAD")
        if paths is None:
            failed.append(boundary.root)
            continue
        prefix = f"{boundary.prefix}/" if boundary.prefix else ""
        for path in paths:
            if prefix and not path.startswith(prefix):
                continue
            changed.add(path[len(prefix) :])
    return frozenset(changed), failed


def unowned_managed_files(graph: DocGraph) -> list[str]:
    """Every managed file with no owner, under the *closed* reading of both rules.

    "Managed" is what the configured walk returns, plus a declared test root, so the
    inventory covers directories no document has reached yet — a record built from the
    findings the checks currently emit would record nothing at all on the day of
    adoption, because the covered-directory guess is silent until the first document
    lands. That is exactly the case this exists for.

    Which rule governs a file is `governed_as_test`'s answer, not this function's: a test
    answers to `owns_tests:` and ordinary source to `describes:`, and recording a path
    here never moves a file between them.
    """
    from irminsul.checks.globs import walk_configured_source_files
    from irminsul.checks.uniqueness import omitted_from_source_ownership, resolve_claims
    from irminsul.declared_tests import (
        classify_test_reference,
        governed_as_test,
        test_root_displays,
    )

    if graph.config is None or graph.repo_root is None:
        return []
    config, root = graph.config, graph.repo_root

    walked = list(walk_configured_source_files(root, config).files)
    displays = {display for _, display in walked}
    # Which displays a declared test root produced, read off the walk rather than matched
    # against the root's spelling — the two differ in the siblings layout, where a display is
    # relative to the root that produced it.
    in_test_root = test_root_displays(root, config)
    displays |= in_test_root

    claimed = set(resolve_claims(graph, walked))
    owned_tests: set[str] = set()
    for node in graph.nodes.values():
        for entry in node.frontmatter.owns_tests:
            reference = classify_test_reference(entry, root)
            if reference.is_exact:
                owned_tests.add(reference.raw)

    out: list[str] = []
    for display in sorted(displays):
        if governed_as_test(display, config, in_test_root=display in in_test_root):
            if display not in owned_tests:
                out.append(display)
            continue
        if display in claimed or omitted_from_source_ownership(display, config):
            continue
        out.append(display)
    return out


def _write(
    path: Path,
    unowned: list[str],
    adopted_at: str | None,
    sources: Sequence[AdoptionSource] = (),
    bindings: Mapping[str, str] | None = None,
) -> None:
    """Replace the record in one step.

    Written beside the target and moved over it, because a half-written record and a
    missing one are both states `--init-adoption` refuses to rebuild — it will not
    overwrite — so a failed write would leave recovery to git.
    """
    bound = bindings or {}
    # A plain string for a file in this repository, an object for one from elsewhere. The
    # single-repository record is therefore unchanged, byte for byte, by the format that let
    # a cross-repository entry state its own binding.
    entries: list[object] = [
        {"path": display, "source": bound[display]} if display in bound else display
        for display in unowned
    ]
    payload: dict[str, object] = {"version": ADOPTION_VERSION, "unowned": entries}
    if adopted_at:
        payload["adopted_at"] = adopted_at
    if sources:
        payload["sources"] = [
            {"name": source.source, "revision": source.revision}
            for source in sorted(sources, key=lambda item: item.source)
        ]
    # `paths.adoption` is configurable, and a nested one such as `.irminsul/adoption.json`
    # has a directory that need not exist yet. The baseline writer creates its parent; this
    # one raised FileNotFoundError and left the documented setting unusable.
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = path.with_name(path.name + ".tmp")
    scratch.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(scratch, path)


__all__ = [
    "ADOPTION_VERSION",
    "AdoptionError",
    "AdoptionRecord",
    "AdoptionSource",
    "DebtProblem",
    "ShrinkResult",
    "SourceBoundary",
    "boundary_for_displays",
    "cross_repo_source_boundaries",
    "init_adoption",
    "load_debt",
    "load_record",
    "managed_walk",
    "missing_configured_roots",
    "pin_source_revisions",
    "record_path",
    "rewrite_sources",
    "shrink_adoption",
    "source_changed_displays",
    "unowned_managed_files",
    "unpinnable_entries",
    "verified_debt",
]
