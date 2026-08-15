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

Record the repository layout in `irminsul.toml`, verify it against the tree
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
base run finds nothing under it. Every finding over that tree survives as new:

| layout | absent from the base checkout | result |
| --- | --- | --- |
| `same-repo` | nothing | correct |
| `siblings` | the code repo `source_roots` reach through `../` | source-dependent findings all read as new |

[`ADR-0022`](../../50-decisions/0022-reduce-supported-repository-topologies.md)
reduced the supported layouts to those two, which narrows this RFC's problem
considerably. The nested layouts it retired included the severe case — a docs
root owned by another repository, where `build_graph` walked a docs root that
did not exist and `compute_delta` compared against an empty fingerprint set.
That case can no longer arise: in both surviving layouts `docs_root` belongs to
the repository Irminsul was invoked from. What remains is bounded to source
roots.

See [private docs](../../30-workflows/private-docs.md) for the sibling layout
and [baseline](../../20-components/baseline.md) for the delta mechanism.
`verify_single_repo_topology` currently refuses `siblings` with exit 2, which is
honest but leaves every private-docs user without the feature.

## Detailed Design

### Declare the layout

Add `paths.topology` to the `Paths` model with values `same-repo` and
`siblings`, matching the `Topology` enum the init scaffolder already uses. The
field is optional with a default, so existing configs keep loading unchanged —
`extra="forbid"` rejects unknown keys, not known keys that are absent.

Sharing the vocabulary with `init` is the point. When the config value, the
`--topology` flag and the scaffolded workflows all say `siblings`, there is one
name for the layout and nothing to reconcile.

### Populate it, but do not trust it

`init` already knows the answer: `--topology` is a user-facing flag and
`InitAnswers` carries `code_repo_spec` and `code_dir`; the scaffold template
simply never writes the field. Emitting it is recovering information the tool
already collected.

That is not sufficient on its own. Repositories initialized before this field
exists have nothing recorded, and a repository can be moved between layouts by
hand.

So detection is the fallback, not the exception: when `paths.topology` is
absent, derive it by comparing the nearest enclosing `.git` of each source root
against the target repo's own, which is what `cross_repo_trees` already does and
what `git_root_for` already provides. A declared layout that disagrees with the
detected one is a soft finding, not a silent override — a hand-maintained
assertion with nothing verifying it is the drift this project exists to catch.

### Split the graph's anchor

`build_graph(repo_root, config)` takes one root, and that root anchors both the
doc walk and, through `walk_configured_source_files`, the source walk. The
sibling layout needs those to differ. Introduce a second anchor — a
`source_root_base` threaded to the single resolution site in `_walk_source_files`
— and let the layout select how the two are set:

| topology | doc walk anchored at | source walk anchored at |
| --- | --- | --- |
| `same-repo` | scratch checkout | scratch checkout |
| `siblings` | scratch checkout | live working tree |

Because `docs_root` always belongs to the invoked repository, `pristine_checkout`
keeps operating on that repository in both layouts — one fewer moving part than
when three layouts were in scope.

### Hold source constant, and say so

The sibling layout has two independent histories, and `--delta-base` names a
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
assumes it will be subtly wrong in the sibling layout only — a class of bug that
CI on a same-repo fixture will not catch.

Delta already costs about 2.5x a plain run. Holding source constant does not
reduce that.

## Alternatives

**Keep refusing.** Honest, already shipped, zero risk. It leaves every
private-docs user without the feature, and `siblings` is now one of only two
supported layouts rather than one of four.

**Detect only, no config field.** Always accurate, no migration, no rot. It
gives up the declarative contract the rest of `[paths]` follows, and leaves no
place for a user to state intent when detection is ambiguous. With two values
instead of four this alternative is stronger than it was, since detection has
only one distinction to get right.

**Add `--delta-source-base <rev>`.** Correct rather than approximate: name a
base in the second history explicitly. It requires the user to know both
histories, adds surface to a flag that is already dense, and does not generalize
beyond two repositories.

**Auto-select the source repo's `HEAD`.** Appears to remove the limitation.
It does not: with uncommitted source edits, `HEAD`-versus-worktree in the source
repo is a different comparison than the one the user asked for, so `--delta`
would quietly mean something different in the sibling layout than in
`same-repo`.

## Unresolved Questions

Should a declared-versus-detected mismatch be a soft finding or a hard error?
Soft matches how the project treats other drift, but a wrong layout produces
wrong delta output rather than merely stale prose.

What the sibling-delta comparison should actually be is open, and this RFC does
not settle it. "Hold source constant" above is the shape this proposal assumes,
not a decided answer; a separate design is in progress and may replace it. The
seam is `verify_single_repo_topology` in `delta.py` — the single place the
refusal is decided — and nothing else in the codebase depends on the refusal
staying.
