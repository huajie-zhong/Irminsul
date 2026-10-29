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

That makes the record *stricter* than the guess it replaces, not weaker. Under the guess, a
whole undocumented sibling tree is invisible; under the record, only the enumerated files are
excepted, and only from the one finding that says they have no owner. Nothing else is
suppressed, no other check is affected, and no glob or directory is ever excepted — a
pattern would silently adopt files written next year.

An entry retires when its file gains an owner, is deleted, or is renamed: the record
names paths, so a moved file is a file the record does not name. Entries never come
back. `irminsul adoption update` removes retired ones and refuses to add any, and
`diff-integrity` fails a change that grows the record or that edits a recorded file
without documenting it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final

from irminsul.atomic import write_atomic
from irminsul.errors import UserError

if TYPE_CHECKING:
    from irminsul.config import IrminsulConfig
    from irminsul.docgraph import DocGraph
    from irminsul.git.reader import GitReader
    from irminsul.source_map import SourceMap
    from irminsul.source_tree import SourceTree

#: A full git object id, the only spelling a pin may take. Both hash lengths, so a
#: repository using sha256 object format is not locked out.
_OBJECT_ID: Final = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")

ADOPTION_VERSION: Final = 1


class AdoptionError(UserError):
    """The adoption record is unreadable, or the operation asked for is not allowed."""


@dataclass(frozen=True)
class AdoptionSource:
    """The revision of one declared source repository that a record's entries are history at.

    `source` is the `name` of a `[[paths.sources]]` entry, not a path. A name survives
    somebody moving the checkout and does not survive somebody pointing the name at another
    repository, which is the property wanted: keyed by root, editing `source_roots` would
    re-point existing entries at a different history with no pin changing.

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
    unowned: frozenset[str] = frozenset()
    adopted_at: str | None = None
    sources: tuple[AdoptionSource, ...] = ()
    bindings: Mapping[str, str] = field(default_factory=dict)
    """Display path -> declared source name, for the entries that came from another
    repository. Absent for a file in this repository, which is why a single-repository
    record is a plain list of strings."""

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
    """What `irminsul adoption update` did, or why it refused.

    `added` is never applied. A record that could grow under an ordinary update is a
    record that excuses the debt a change just created, which is the whole thing the
    seal exists to stop.
    """

    added: list[str] = field(default_factory=list)
    removed: int = 0
    kept: int = 0


def record_path(repo_root: Path, config: object) -> Path:
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
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        # `UnicodeDecodeError` is a ValueError, not an OSError. Uncaught, a record saved as UTF-16
        # ends the run in a traceback before any finding prints, including the one whose
        # explanation says how to repair the file.
        raise AdoptionError(f"could not read the adoption record {path.name}: {e}") from e
    return parse_record(text, path.name)


def parse_record(
    text: str, name: str = ".irminsul-adoption.json", *, tolerant: bool = False
) -> AdoptionRecord:
    """A record from its text. `name` only words the errors.

    The shape is `{"version": 1, "unowned": [...], "adopted_at": <sha>, "sources": [...]}`, and
    only `version` and `unowned` are required. An `unowned` entry is a path string for a file in
    this repository, or `{"path", "source"}` for one from a declared `[[paths.sources]]` entry;
    `sources` holds one `{"name", "revision"}` pin per declared source an entry is bound to.

    Strict, the default, is the record a repository stands on: anything malformed is an
    `AdoptionError`, because dropping it would leave a record that reads as pinned or as
    complete and is neither. Tolerant is for a blob this change did not write, such as the
    record at the merge base: it keeps what is well formed and skips the rest, so a record
    that will not parse yields nothing to compare against rather than taking the pass down.
    The head's own record is reported by the `adoption-record` pass, where it can be
    repaired.

    A tolerant read does not check the version, takes the last of two pins for one source,
    and does not hold a pin to being a commit id.
    """
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        if tolerant:
            return AdoptionRecord()
        raise AdoptionError(f"could not read the adoption record {name}: {e}") from e
    body: dict[str, object] = payload if isinstance(payload, dict) else {}
    if not tolerant:
        if body.get("version") != ADOPTION_VERSION:
            raise AdoptionError(
                f"adoption record {name} has unsupported format; expected version "
                f"{ADOPTION_VERSION}"
            )
        if not isinstance(body.get("unowned"), list):
            raise AdoptionError(
                f"adoption record {name} is missing its `unowned` list of exact paths"
            )
    raw = body.get("unowned")
    unowned, bindings = _read_entries(name, raw if isinstance(raw, list) else [], tolerant)
    adopted_at = body.get("adopted_at")
    return AdoptionRecord(
        unowned=unowned,
        adopted_at=adopted_at if isinstance(adopted_at, str) else None,
        sources=_read_sources(name, body.get("sources"), tolerant),
        bindings=bindings,
    )


def _read_entries(
    name: str, raw: list[object], tolerant: bool
) -> tuple[frozenset[str], dict[str, str]]:
    """The recorded paths, and which declared source each one that has one came from.

    Two spellings. A **string** is a file in this repository, which is every entry a
    single-repository project writes. An **object** is a file from another repository and
    states the source it came from, because a binding re-derived from `paths.source_roots`
    could be re-pointed at a different history by a configuration edit.

    Anything else is an error rather than a skip, and a missing or empty `source` is an error
    rather than a fall back to "this repository". Guessing which repository answers for a
    file is how an exception gets verified against the wrong one. A tolerant read skips an
    entry it cannot read, keeps a path whose source is missing as a path in this repository,
    and lets the last of two sources for one path win.
    """
    unowned: set[str] = set()
    bindings: dict[str, str] = {}
    for item in raw:
        if isinstance(item, str):
            if not item:
                if tolerant:
                    continue
                raise AdoptionError(f"adoption record {name} has an empty path in `unowned`")
            unowned.add(item)
            continue
        if not isinstance(item, dict):
            if tolerant:
                continue
            raise AdoptionError(
                f"adoption record {name} has an `unowned` entry that is neither a path "
                "nor a {path, source} object"
            )
        display, source = item.get("path"), item.get("source")
        if not isinstance(display, str) or not display:
            if tolerant:
                continue
            raise AdoptionError(
                f"adoption record {name} has an `unowned` object without a string `path`"
            )
        unowned.add(display)
        if not isinstance(source, str) or not source:
            if tolerant:
                continue
            raise AdoptionError(
                f"adoption record {name} names `{display}` without a `source`. An entry "
                "from another repository states which declared source it came from; a file in "
                "this repository is written as a plain path"
            )
        if not tolerant and display in bindings and bindings[display] != source:
            raise AdoptionError(
                f"adoption record {name} binds `{display}` to both {bindings[display]!r} "
                f"and {source!r}; one entry has one source"
            )
        bindings[display] = source
    return frozenset(unowned), bindings


def _read_sources(name: str, raw: object, tolerant: bool) -> tuple[AdoptionSource, ...]:
    """The pinned source revisions, or `()` when the record names none.

    Absent is the same-repository case and the ordinary one, so it is not an error here.
    A record that *needs* a pin and has none is decided where the exception is granted,
    not while reading the file: this function cannot know which roots are cross-repo.

    A malformed entry is an error rather than a skip. Dropping it would leave a record
    that looks pinned, reads as pinned, and excepts files against a revision nobody
    recorded. A tolerant read is the one that skips it.
    """
    if raw is None:
        return ()
    if not isinstance(raw, list):
        if tolerant:
            return ()
        raise AdoptionError(
            f"adoption record {name} has a `sources` that is not a list of "
            "{name, revision} entries"
        )
    pairs: list[tuple[str, str]] = []
    for item in raw:
        source = item.get("name") if isinstance(item, dict) else None
        revision = item.get("revision") if isinstance(item, dict) else None
        if (
            not isinstance(source, str)
            or not isinstance(revision, str)
            or not source
            or not revision
        ):
            if tolerant:
                continue
            raise AdoptionError(
                f"adoption record {name} has a `sources` entry without a string "
                "`name` and `revision`. A pin names a declared source from "
                "`[[paths.sources]]` and the commit this repository adopted at"
            )
        if not tolerant and not _OBJECT_ID.fullmatch(revision):
            # A symbolic name is not a boundary. `HEAD` and a branch name both resolve, so
            # they verify — against whatever the sibling repository happens to be now — and
            # because the recorded string never changes, nothing can see the boundary moving
            # forward. A record pinned at `HEAD` would accept a file committed yesterday
            # as pre-existing debt.
            raise AdoptionError(
                f"adoption record {name} pins '{source}' at {revision!r}, which is not a "
                "commit id. A boundary has to be a fixed point, and a name is not one; "
                "record the full hexadecimal id of the commit adopted at."
            )
        pairs.append((source, revision))
    if not tolerant and len({source for source, _ in pairs}) != len(pairs):
        raise AdoptionError(
            f"adoption record {name} pins the same source twice in `sources`; one "
            "source has one adoption revision"
        )
    return tuple(AdoptionSource(source, revision) for source, revision in dict(pairs).items())


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
            f"adoption record {path.name} already exists; run irminsul adoption update to retire "
            "entries that are now owned, since a record only shrinks",
            code=1,
        )
    _write(path, sorted(set(unowned)), adopted_at, sources, bindings)
    return len(set(unowned))


def shrink_adoption(path: Path, still_unowned: set[str]) -> ShrinkResult:
    """Retire the entries that are now owned, deleted or moved; refuse to add any."""
    if not path.is_file():
        raise AdoptionError(
            f"no adoption record at {path.name}; create one with irminsul adoption init"
        )
    record = load_record(path)
    added = sorted(still_unowned - record.unowned)
    if added:
        return ShrinkResult(added=added)
    kept = record.unowned & still_unowned
    # The pins carry over untouched. `irminsul adoption update` retires entries; the revision an
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
    """Whether the tree is on disk. An absent tree stays in the boundary list: dropped, a
    missing sibling checkout would be the *quietest* state there is — nothing resolves to it,
    so nothing is pinned, checked or reported, and the gate goes green on a tree it cannot
    see. Absence is an answer here, not a reason to stop asking."""

    def git_path(self, display: str) -> str:
        """A display path as the owning repository spells it."""
        return f"{self.prefix}/{display}" if self.prefix else display


def _configured_roots(config: object) -> list[str]:
    """Every root the managed walk reads, source and test alike, in order and deduplicated.

    `paths.test_roots` is not a source root and the ordinary walk does not reach it, but
    the record covers tests too — so a declared test tree in another repository can put
    entries in the record. Left out of the boundary list, those entries would resolve to no
    boundary, so nothing would pin or check them, and a new cross-repo test hand-added to the
    record would be accepted in silence.
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
    `irminsul adoption update` that is the difference between retiring the entries whose work is
    done and emptying the record, which nothing but git can undo.
    """
    return [rel for rel in _configured_roots(config) if not (repo_root / rel).is_dir()]


def managed_walk(tree: SourceTree) -> list[tuple[Path, str]]:
    """Every managed file as `(absolute path, display)`, test roots included.

    One walk for both ownership rules and for the boundary resolution, because the record
    is one list: a display that only the test walk returns still has to resolve to the
    repository it came from.

    A test-root pair whose display the source walk already produced is *kept*, not dropped.
    Two roots that spell one file the same way is an ambiguity, and `boundary_for_displays`
    is what reports it; deduplicating here would silence it, and the surviving entry would
    except a file under both ownership policies while being verified against one repository.
    `globs` never compares the separately walked test root, so nothing else would say so.
    """
    walked = list(tree.files)
    seen_pairs = set(walked)
    walked += [pair for pair in tree.test_walk.files if pair not in seen_pairs]
    return walked


def cross_repo_source_boundaries(repo_root: Path, config: object) -> list[SourceBoundary]:
    """Every configured root — source or test — owned by a git repository other than this one.

    This is the same question `delta.cross_repo_trees` asks and the same primitive
    (`git_root_for`) answers it, but the answers differ in what they carry: delta needs
    only the names of the roots it must refuse, and adoption needs the repository and the
    offset, because it has to read history out of them.

    A root with no `.git` above it is returned with `git_root` set to None rather than
    dropped. Dropped, a code repository whose `.git` is removed or was never cloned would take
    the whole root out of the boundary list, and its entries would go on excepting files with
    nothing to check them against. "Outside this repository" is the test, and whether a
    repository can be found there is the answer, not the filter.

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
    # repository has been initialized. Without it, `irminsul adoption init` in an uncommitted
    # project would decide `src` belongs to another repository and refuse.
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


def pin_source_revisions(git: GitReader, smap: SourceMap) -> list[AdoptionSource]:
    """The revision each cross-repo source root is at right now, for a first record.

    Refuses rather than guessing. A root whose repository has no commit yet cannot supply
    an adoption boundary, and writing a record that claims one anyway is how a file added
    tomorrow becomes yesterday's debt.
    """
    from irminsul.git.changes import head_revision, merge_base, resolve_ref

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
    for boundary in smap.boundaries:
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
        revision = head_revision(git, boundary.git_root)
        if revision is None:
            raise AdoptionError(
                f"source root '{boundary.root}' belongs to the git repository at "
                f"{boundary.git_root}, which has no commit to adopt at. The record would "
                "claim its files are pre-existing debt with nothing able to confirm it; "
                "commit the source repository first."
            )
        ref = smap.refs[source]
        resolved = resolve_ref(git, boundary.git_root, ref)
        if resolved is None:
            raise AdoptionError(
                f"source {source!r} declares ref {ref!r}, which the repository at "
                f"{boundary.git_root} does not have. The boundary has to be a point on that "
                "history, so there is nothing to record; fetch the ref (in CI, a checkout "
                "that includes it), or declare the one this checkout has."
            )
        boundary_revision = merge_base(git, boundary.git_root, revision, resolved)
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
    git: GitReader,
    smap: SourceMap,
    unowned: Sequence[str],
    sources: Sequence[AdoptionSource],
) -> list[str]:
    """Entries the revision about to be pinned does not contain.

    The walk reads the source working tree and the pin names its committed `HEAD`, so an
    untracked file is recorded as debt and then disproved by the very next run. Writing a
    record that is already wrong is worse than refusing: `irminsul adoption init` will not
    overwrite, so the repair is to delete the record by hand.
    """
    from irminsul.git.changes import has_revision, tracked_paths_at_ref

    pinned = {source.source: source.revision for source in sources}
    out: list[str] = []
    at_revision: dict[str, set[str] | None] = {}
    for display in sorted(set(unowned)):
        binding = smap.binding(display)
        # Two questions with two answers. *Which revision* is the source's, because a
        # repository has one history however many roots reach into it. *How the file is
        # spelled inside it* is the root's, because `../code/src` and `../code/tests` sit at
        # different offsets — reading the spelling off the source's first root would ask the
        # repository for `src/test_a.py`, which does not exist.
        boundary = smap.boundary_for_root(binding.root) if binding.root else None
        if boundary is None or boundary.git_root is None or binding.source is None:
            continue
        revision = pinned.get(binding.source)
        if revision is None or not has_revision(git, boundary.git_root, revision):
            continue
        if binding.source not in at_revision:
            at_revision[binding.source] = tracked_paths_at_ref(git, boundary.git_root, revision)
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
    """What to do about it. Several conditions share the `unverifiable` kind and they do not
    share an answer — telling somebody to re-pin a boundary when two roots spell one file
    the same way sends them to the wrong file entirely."""


def verified_debt(
    git: GitReader,
    repo_root: Path,
    record: AdoptionRecord,
    source_map: SourceMap,
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
    and is `graph.source_map`, so one run resolves once. Pins are read from `record` rather
    than from the map, because the record is the thing being validated: a map built from
    some other record would answer about that one.

    The first element is always `record.unowned`; a caller that needs only the excepted
    paths reads that, and asks nothing of git.
    """
    from irminsul.git.changes import has_revision, tracked_paths_at_ref

    if not record.unowned:
        return record.unowned, []
    ambiguous = source_map.ambiguous
    # Grouped by declared source rather than by root, because the pin belongs to the
    # repository: two roots in one repository share one boundary, and keyed by root, two pins
    # for one history could drift apart. A root no source declares keys by its own spelling, so
    # it is still answered for rather than silently dropped.
    grouped: dict[str, tuple[SourceBoundary, list[str]]] = {}
    for root, displays in source_map.external_entries(record.unowned).items():
        boundary = source_map.boundary_for_root(root)
        if boundary is None:
            continue
        key = source_map.source_of_root(root) or root
        held = grouped.get(key)
        grouped[key] = (
            boundary if held is None else held[0],
            sorted(displays if held is None else [*held[1], *displays]),
        )
    # A source the record pinned but the config no longer declares still has to be answered
    # for: dropping the declaration is how an exception would stop being checked while the
    # entries it covers stay in the record.
    for pinned_source in record.sources:
        path = source_map.declared.get(pinned_source.source, pinned_source.source)
        grouped.setdefault(
            pinned_source.source, (SourceBoundary(path, repo_root / path, None, ""), [])
        )

    # The record's exceptions stand exactly as written. A file this proves was not there is
    # named by its own finding, which fails the run; dropping it from the debt as well would
    # report the same file twice, once as new and once as merely unowned.
    debt = record.unowned
    problems: list[DebtProblem] = []
    for stray in source_map.outside_the_walk:
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
    for name in source_map.split_sources:
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
    problems.extend(_binding_problems(record, source_map))
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
                        "restore the pin from the record's own history: `irminsul adoption init` "
                        "pins every cross-repository source it records entries from"
                    ),
                )
            )
            continue
        if not has_revision(git, boundary.git_root, revision):
            problems.append(_missing_pin_problem(git, root, revision, boundary))
            continue
        at_revision = tracked_paths_at_ref(git, boundary.git_root, revision)
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
            own = source_map.boundary_for_root(source_map.binding(display).root or "") or boundary
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


def _missing_pin_problem(
    git: GitReader, source: str, revision: str, boundary: SourceBoundary
) -> DebtProblem:
    """Why the pinned revision is not readable here, as specifically as can be known.

    Three causes share this condition, and they need different answers.
    A shallow clone is the overwhelmingly common one — `actions/checkout` clones to depth 1 —
    and is repaired by fetching. A full clone that still lacks the commit is either a
    repository that never had it or one whose history was rewritten, and **this cannot tell
    which from here**: saying the history is gone would be asserting something only the
    source repository can answer. So it says what it knows, names the command, and stops.
    """
    from irminsul.git.mtime import history_state

    assert boundary.git_root is not None
    _, shallow = history_state(git, boundary.git_root)
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
    against each other is the point of writing the binding down — a source field trusted
    without comparison would be no better than re-deriving the binding on every run.

    Each is a refusal, never a repair. Picking one of two disagreeing answers is how an
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
                        remedy="state the source the entry came from on the entry",
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
    repo_root: Path,
    config: IrminsulConfig,
    refs: Mapping[str | None, str],
    *,
    committed_only: bool = False,
) -> tuple[frozenset[str], list[str]]:
    """Display paths a source repository changed since `base_ref`, and the roots it failed on.

    The docs repository's own diff cannot see this. `source_roots` reach into another
    repository with its own history, so a pull request there produces no docs-repo diff at
    all, and touch-to-own — the rule that says editing recorded debt means documenting it —
    would have nothing to read.

    `refs` maps a declared source name to the base ref to read in that repository, with `None`
    as the key for "every source". Two repositories can spell their default branch
    differently, so one ref for all would leave one of them unable to resolve it and the run
    exiting 2; a named ref diffs the repository under review and leaves the others alone,
    which is what a pull request in one repository is about.

    A source named here whose repository cannot answer is returned in the second element
    rather than silently contributing nothing: a rule that quietly reads an empty change set
    is a rule that passes everything. A source *not* named is not asked, and contributes
    nothing for the same reason a docs-only run contributes nothing for it — no range was
    given for it.

    Each repository is read as the docs repository is: from the merge base to its working
    tree, or to its `HEAD` under `committed_only`.
    """
    from irminsul.git.changes import changed_since
    from irminsul.git.reader import GitReader
    from irminsul.source_map import build_source_map
    from irminsul.source_tree import SourceTree

    git = GitReader()
    changed: set[str] = set()
    failed: list[str] = []
    resolution = build_source_map(SourceTree(repo_root, config), AdoptionRecord())
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
        since = changed_since(git, boundary.git_root, base_ref, committed_only=committed_only)
        if since is None:
            failed.append(boundary.root)
            continue
        prefix = f"{boundary.prefix}/" if boundary.prefix else ""
        for path in since.changed:
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
    from irminsul.checks.uniqueness import omitted_from_source_ownership
    from irminsul.declared_tests import classify_test_reference, governed_as_test

    if graph.config is None or graph.repo_root is None:
        return []
    config, root = graph.config, graph.repo_root

    walked = list(graph.source.files)
    displays = {display for _, display in walked}
    # Which displays a declared test root produced, read off the walk rather than matched
    # against the root's spelling — the two differ in the siblings layout, where a display is
    # relative to the root that produced it.
    in_test_root = graph.source.test_displays
    displays |= in_test_root

    claimed = set(graph.claims)
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


def _unowned_in_a_whole_tree(graph: DocGraph, repo_root: Path, config: IrminsulConfig) -> list[str]:
    """`unowned_managed_files`, refusing a walk that cannot see every configured root."""
    if absent := missing_configured_roots(repo_root, config):
        # The walk cannot see these, so "has no owner" has no answer for anything under
        # them. `irminsul adoption update` would read that silence as work completed and
        # retire every entry it covers; `irminsul adoption init` would record a tree it
        # cannot see.
        listed = ", ".join(repr(root) for root in absent)
        raise AdoptionError(
            f"configured root(s) {listed} are not on disk, so which managed files have "
            "no owner cannot be determined. Refusing rather than reading an absent tree "
            "as a documented one — that would empty the record. Check the source "
            "repository out where `paths.source_roots` says it is."
        )
    return unowned_managed_files(graph)


@dataclass(frozen=True)
class Adopted:
    """What `record_adoption` wrote: the entry count and the sources it pinned."""

    count: int
    sources: tuple[AdoptionSource, ...] = ()


def record_adoption(graph: DocGraph, repo_root: Path, config: IrminsulConfig) -> Adopted:
    """Write a first adoption record from the configured walk.

    It reads no findings. The record's whole purpose is to name the files whose ownership
    findings do not exist yet — on the day of adoption the covered-directory rule is silent,
    so a record built from findings would be empty and would except nothing.
    """
    path = record_path(repo_root, config)
    unowned = _unowned_in_a_whole_tree(graph, repo_root, config)
    head = _head_sha(graph.git, repo_root)
    # A source root in another repository has a history of its own, and this
    # repository's merge base says nothing about it. The revision that root is at
    # now is the boundary its entries are history at, and it goes in the record so
    # every later run can ask that repository the same question.
    # Only the sources some entry is bound to. A pin grants nothing on its own, and
    # `irminsul adoption update` preserves every pin it finds, so a pin for a source whose
    # files are all documented would couple an unrelated repository to this record until
    # somebody removed it by hand.
    smap = graph.source_map
    contributing = {
        binding.source
        for display in unowned
        if (binding := smap.binding(display)).source is not None
    }
    sources = [
        source for source in pin_source_revisions(graph.git, smap) if source.source in contributing
    ]
    if stranded := unpinnable_entries(graph.git, smap, unowned, sources):
        listed = ", ".join(repr(item) for item in stranded[:5])
        more = f" and {len(stranded) - 5} more" if len(stranded) > 5 else ""
        raise AdoptionError(
            f"{len(stranded)} managed file(s) are not in the revision being "
            f"pinned: {listed}{more}. The walk reads the source working tree and "
            "the boundary is its committed HEAD, so these are uncommitted — "
            "recording them would write a record the next run disproves. Commit "
            "the source repository first."
        )
    # Each entry from another repository states the source it came from, so no later
    # configuration edit can re-derive a different one for it.
    bindings = {
        display: binding.source
        for display in unowned
        if (binding := smap.binding(display)).source is not None
    }
    return Adopted(init_adoption(path, unowned, head, sources, bindings), tuple(sources))


def retire_adoption(graph: DocGraph, repo_root: Path, config: IrminsulConfig) -> ShrinkResult:
    """Retire the record's entries whose file is now owned, deleted or moved."""
    path = record_path(repo_root, config)
    return shrink_adoption(path, set(_unowned_in_a_whole_tree(graph, repo_root, config)))


def _head_sha(git: GitReader, repo_root: Path) -> str | None:
    # A repository with no commit yet still adopts; the record simply records no origin.
    return (git.text(repo_root, "rev-parse", "HEAD") or "").strip() or None


def recorded_debt(graph: DocGraph) -> frozenset[str] | None:
    """The record's excepted paths, or `None` when the tree has no readable record.

    `None` and an empty record mean different things and must not collapse: no record at
    all keeps the progressive covered-directory rule, while a record that has shrunk to
    nothing means every managed file is owned and the closed rule applies with no
    exceptions left to spend.

    An unreadable record reads as none here, and a cross-repository entry no boundary could
    confirm still excepts its file: calling it new would assert the opposite of what could
    not be shown. Both are reported once by the `adoption-record` pass, which runs outside
    `checks.enabled` because the record grants exceptions to `uniqueness` and
    `test-ownership` and a repository may enable either alone. What fails the run is the
    finding it raises, so the consumers of this set say nothing about the file it came from.
    """
    record = graph.adoption_record
    return None if record is None else record.unowned


@dataclass(frozen=True)
class Assessment:
    """How much pre-existing ownership debt a run left unreported, for the record it read.

    Zero errors means nothing provable is broken, and while a record holds entries it does
    not mean every file has documentation. Saying so is the same duty the baseline line
    discharges: what a run hides, it names — and the number is what it says it is, which is
    files without an owner, not lines in a file nobody has tidied.

    `live` counts entries whose file still has no owner. Retiring one needs
    `irminsul adoption update`, which nobody is obliged to run, so a live record is usually stale
    and the entry count and the file count drift apart; `entries` keeps the raw count.
    """

    path: str
    record: AdoptionRecord | None = None
    error: str | None = None
    absent_roots: tuple[str, ...] = ()
    """Configured roots not on disk. The managed walk cannot see them, so every count here
    would be read off a smaller tree, and `remaining: 0` would say full coverage to every
    parser while the amount is unknown."""
    live: frozenset[str] = frozenset()

    @property
    def assessable(self) -> bool:
        return not self.absent_roots

    def as_json(self) -> dict[str, object]:
        """The `adoption` object of `check --format json`."""
        if self.record is None:
            return {"path": self.path, "readable": False, "error": self.error}
        recorded = self.record.unowned
        sources = [
            {"source": source.source, "revision": source.revision} for source in self.record.sources
        ]
        if not self.assessable:
            return {
                "path": self.path,
                "readable": True,
                "assessable": False,
                "absent_roots": list(self.absent_roots),
                "entries": len(recorded),
                "recorded": sorted(recorded),
                "adopted_at": self.record.adopted_at,
                "sources": sources,
            }
        return {
            "path": self.path,
            "readable": True,
            "assessable": True,
            "remaining": len(self.live),
            "entries": len(recorded),
            "unowned": sorted(self.live),
            "recorded": sorted(recorded),
            "adopted_at": self.record.adopted_at,
            "sources": sources,
        }

    def note(self) -> tuple[str, str] | None:
        """The line a human-readable run prints, and its colour; `None` when it has nothing
        to add."""
        if self.record is None:
            return None
        if not self.assessable:
            # Saying "0 remaining" here would recommend `irminsul adoption update` over a walk
            # that cannot see these roots, which empties the record.
            return (
                f"adoption: {self.path} names files under "
                + ", ".join(repr(root) for root in self.absent_roots)
                + ", which are not on disk, so how much debt is left is unknown. Do not run "
                "`irminsul adoption update` until they are checked out.",
                "yellow",
            )
        remaining = len(self.live)
        stale = len(self.record.unowned) - remaining
        if not remaining:
            if stale:
                return (
                    f"adoption: every file {self.path} names now has an owner. "
                    "Run `irminsul adoption update` to retire the entries.",
                    "cyan",
                )
            return None
        tail = (
            f" {stale} further entr{'y names a file' if stale == 1 else 'ies name files'} that is "
            "now owned or gone; `irminsul adoption update` retires them."
            if stale
            else ""
        )
        return (
            f"adoption: {remaining} file(s) still have no owning doc and are excepted by "
            f"{self.path}; `irminsul list undocumented --all` lists them.{tail}",
            "cyan",
        )


def assess(graph: DocGraph) -> Assessment | None:
    """What the record a run read leaves unreported, or `None` when the tree has none."""
    if graph.config is None or graph.repo_root is None:
        return None
    path = graph.config.paths.adoption
    if graph.adoption_error is not None:
        return Assessment(path, error=graph.adoption_error)
    record = graph.adoption_record
    if record is None:
        return None
    if absent := missing_configured_roots(graph.repo_root, graph.config):
        return Assessment(path, record, absent_roots=tuple(absent))
    return Assessment(path, record, live=record.unowned & frozenset(unowned_managed_files(graph)))


def _write(
    path: Path,
    unowned: list[str],
    adopted_at: str | None,
    sources: Sequence[AdoptionSource] = (),
    bindings: Mapping[str, str] | None = None,
) -> None:
    """Replace the record in one step.

    Written beside the target and moved over it, because a half-written record and a
    missing one are both states `irminsul adoption init` refuses to rebuild — it will not
    overwrite — so a failed write would leave recovery to git.
    """
    bound = bindings or {}
    # A plain string for a file in this repository, an object for one from elsewhere.
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
    write_atomic(path, json.dumps(payload, indent=2) + "\n", newline="\n")


__all__ = [
    "ADOPTION_VERSION",
    "Adopted",
    "AdoptionError",
    "AdoptionRecord",
    "AdoptionSource",
    "Assessment",
    "DebtProblem",
    "ShrinkResult",
    "SourceBoundary",
    "assess",
    "boundary_for_displays",
    "cross_repo_source_boundaries",
    "init_adoption",
    "load_record",
    "managed_walk",
    "missing_configured_roots",
    "parse_record",
    "pin_source_revisions",
    "record_adoption",
    "record_path",
    "recorded_debt",
    "retire_adoption",
    "shrink_adoption",
    "source_changed_displays",
    "unowned_managed_files",
    "unpinnable_entries",
    "verified_debt",
]
