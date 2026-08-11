---
id: 0044-cross-repo-delta
title: "Cross-repo topologies for check --delta"
audience: explanation
tier: 2
status: draft
describes: []
rfc_state: draft
affects:
- baseline
- checks
- cli
- docgraph
---

# RFC 0044: Cross-repo topologies for check --delta

## Summary

Record the repository topology in `irminsul.toml`, verify it against the tree
rather than trusting it, and split `build_graph`'s single `repo_root` into a
docs anchor and a source anchor so `check --delta` can compare across a
repository boundary instead of refusing to.

## Motivation

`check --delta` reports only findings the working tree introduced relative to a
base rev, by running the configured checks twice — once live, once against the
base rev checked out into a scratch `git worktree`. On this repo that turns 249
findings into 1, which is the difference between output an agent acts on and
output an agent skips.

`git worktree add` checks out tracked files only. A configured tree owned by a
different git repository is therefore absent from the base checkout, and the
base run finds nothing under it. Every finding over that tree survives as new.
Both cross-repo layouts this project supports hit it, for the same reason but
with different blast radii:

| layout | absent from the base checkout | result |
| --- | --- | --- |
| single repo | nothing | correct |
| code repo nested in the docs repo | the gitignored code subfolder | source-dependent findings all read as new |
| docs repo nested in the code repo | the whole of `docs/` | every finding reads as new |

The second row is the severe one: `build_graph` walks a docs root that does not
exist, produces an empty graph, and `compute_delta` compares against an empty
fingerprint set. See [private docs](../../30-workflows/private-docs.md) for the
two layouts and [baseline](../../20-components/baseline.md) for the delta
mechanism.

`verify_single_repo_topology` currently refuses both layouts with exit 2, which
is honest but leaves every cross-repo user without the feature.

## Detailed Design

### Declare the topology

Add `paths.topology` to the `Paths` model with values `same-repo`,
`nested-code`, and `nested-docs`. The field is optional with a default, so
existing configs keep loading unchanged — `extra="forbid"` rejects unknown keys,
not known keys that are absent.

The values are named for the layout rather than lettered. "Topology B" already
denotes two different things in this repository: the nested-docs layout in
[private docs](../../30-workflows/private-docs.md), and a sibling-path layout in
[RFC 0001](0001-topology-b-and-format-json.md) and the `init-docs-only`
docstring. This RFC does not settle which meaning wins, but it declines to
encode either into a config value.

### Populate it, but do not trust it

`init` already knows the answer. `FreshTopology` is a user-facing `--topology`
flag, and `InitAnswers` carries `code_repo_spec` and `code_subfolder`; the
scaffold template simply never writes them. Emitting the field is recovering
information the tool already collected.

That is not sufficient on its own. `init` scaffolds only `same-repo` and
`nested-code` — the nested-docs layout is built by hand, and it is exactly the
layout that fails worst. Repositories initialized before this field exists also
have nothing recorded.

So detection is the fallback, not the exception: when `paths.topology` is
absent, derive it by comparing the nearest enclosing `.git` of `docs_root` and
each source root against the target repo's own, which is what
`cross_repo_trees` already does and what `git_root_for` already provides. A
declared topology that disagrees with the detected one is a soft finding, not a
silent override — a hand-maintained assertion with nothing verifying it is the
drift this project exists to catch.

### Split the graph's anchor

`build_graph(repo_root, config)` takes one root, and that root anchors both the
doc walk and, through `walk_configured_source_files`, the source walk. Every
cross-repo mode needs those to differ. Introduce a second anchor — a
`source_root_base` threaded to the single resolution site in `_walk_source_files`
— and let the topology select how the two are set:

| topology | doc walk anchored at | source walk anchored at |
| --- | --- | --- |
| `same-repo` | scratch checkout | scratch checkout |
| `nested-code` | scratch checkout | live working tree |
| `nested-docs` | scratch checkout of the nested docs repo | live working tree |

`nested-docs` also changes which repository `pristine_checkout` operates on: the
base rev names a point in the docs history, so the checkout must target the repo
that owns `docs_root`, not the repo at `repo_root`.

### Hold source constant, and say so

A cross-repo layout has two independent histories, and `--delta-base` names a
point in one of them. Holding the source tree constant across both passes is
therefore the defined comparison, and it has a cost worth stating plainly:
a source edit that makes a doc claim stale produces the same finding in both
passes, so it is suppressed as pre-existing. Doc-side deltas stay correct.

This matches the boundary the project already draws. Diff-based views inspect
only the repository where Irminsul was invoked, and
[private docs](../../30-workflows/private-docs.md) already directs users to
mtime drift as the cross-repository signal.

## Drawbacks

A new config field is a new thing that can rot, which is why the cross-check is
part of this proposal rather than a follow-up.

Splitting the graph anchor touches a parameter that roughly fifteen call sites
reach through `walk_configured_source_files`. The call sites do not change, but
the invariant "one root anchors everything" stops holding, and future code that
assumes it will be subtly wrong in cross-repo mode only — a class of bug that
CI on a single-repo fixture will not catch.

Delta already costs about 2.5x a plain run. Holding source constant does not
reduce that.

## Alternatives

**Keep refusing.** Honest, already shipped, zero risk. It leaves every
cross-repo user without the feature, and the nested-docs layout is a documented,
tested configuration rather than an exotic one.

**Detect only, no config field.** Always accurate, no migration, no rot. It
gives up the declarative contract the rest of `[paths]` follows, and leaves no
place for a user to state intent when detection is ambiguous.

**Add `--delta-source-base <rev>`.** Correct rather than approximate: name a
base in the second history explicitly. It requires the user to know both
histories, adds surface to a flag that is already dense, and does not generalize
beyond two repositories.

**Auto-select the source repo's `HEAD`.** Appears to remove the limitation.
It does not: with uncommitted source edits, `HEAD`-versus-worktree in the source
repo is a different comparison than the one the user asked for, so `--delta`
would quietly mean something different in cross-repo mode than in same-repo
mode.

## Unresolved Questions

Should a declared-versus-detected mismatch be a soft finding or a hard error?
Soft matches how the project treats other drift, but a wrong topology produces
wrong delta output rather than merely stale prose.

Which meaning of "Topology B" survives — the nested-docs layout that ships and
is tested, or the sibling-path layout that RFC 0001 proposed and
`init-docs-only` still refers to? This RFC routes around the collision; it does
not resolve it.

Does the sibling-path layout, if it is ever implemented, need a fourth topology
value, or does it fold into `nested-code` with a relative source root?
