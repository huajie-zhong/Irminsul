---
id: 0022-reduce-supported-repository-topologies
title: "ADR-0022: Reduce supported repository topologies to two"
audience: adr
tier: 2
status: stable
describes: []
summary: Support only the same-repo and siblings layouts; retire both nested private-docs topologies and the command that scaffolded one.
retires:
  - id: init-docs-only-command
    kind: cli-command
    surface_identity: init-docs-only
    matches:
      - irminsul init-docs-only
      - irm init-docs-only
      - init-docs-only
    guidance: Use `irminsul init --topology siblings --code-repo <spec-or-path>` to scaffold a docs repo beside a separate code repo.
  - id: docs-only-topology
    kind: concept
    matches:
      - --topology docs-only
      - docs-only topology
    guidance: The siblings layout replaces it; pass `--topology siblings` and keep the code repo outside the docs repo.
  - id: lettered-topologies
    kind: concept
    matches:
      - Topology A
      - Topology B
    guidance: Name the layout instead - `same-repo` or `siblings`.
---

# ADR-0022: Reduce supported repository topologies to two

## Status

Accepted, 2026-08-15. Supersedes the topology clauses of
[`ADR-0002`](0002-support-fresh-start-init.md); the rest of that decision —
fresh-start adoption as a first-class `irminsul init` path — stands unchanged.
The corresponding clauses of
[`RFC 0007`](../80-evolution/rfcs/0007-fresh-start-init.md) are historical
record and are not edited, per [`ADR-0016`](0016-freeze-implemented-rfc-records.md).

## Context

Irminsul claimed support for four repository layouts. Two were same-repo and
sibling variants; the other two were nested, and both existed for one purpose —
letting a private docs tree reach a public code checkout on the filesystem:

- the docs repo primary, with the code repo cloned into a gitignored subfolder
  (what `init-docs-only` scaffolded, previously called "Topology A");
- the code repo primary, with `docs/` as a nested private repo gitignored by the
  outer one (previously "Topology B").

Four layouts is four times the surface for one job. Every path-resolving change
had to be reasoned about in four configurations, `--delta` had to refuse three of
them, the scaffolder carried two answer gatherers plus a `.gitignore` mutation,
and the CI templates branched inside themselves. The names had drifted too:
"Topology B" meant the nested-docs layout in the workflow doc and the sibling
layout in [`RFC 0001`](../80-evolution/rfcs/0001-topology-b-and-format-json.md).

The nested layouts also buy their filesystem access by nesting one repository
inside another's working tree. That is the arrangement git tooling handles worst:
`git worktree add` cannot reproduce it, diff-based views silently see only the
outer repo, and a stray `git add -A` in the outer repo can capture the inner one.

The path-representation rework from RFC 0001 has already landed —
`walk_source_files` returns `(abs_path, display_posix)` pairs and git-time
lookups resolve through each file's own nearest `.git` — so checking already
works with the code repo outside the docs repo. What was missing was a
scaffolder and CI for that shape, not a mechanism.

## Decision

Support exactly two repository layouts, named for what they are:

- **`same-repo`** — `docs/` is a plain subfolder of the code repo. The default,
  what `irminsul init` scaffolds, and what this repository is.
- **`siblings`** — a parent workspace directory holds the code repo and the docs
  repo as two separate git repositories, and `paths.source_roots` reach out
  through `../`. This is the private-docs story.

Retire both nested layouts and the `irminsul init-docs-only` command. Scaffold
the siblings layout from `irminsul init --topology siblings --code-repo <spec>`:
a flag on the one command that already scaffolds repositories, rather than a
second command, because the layout only selects where `source_roots` point and
how CI reassembles the tree.

Reject `--fresh` together with `--topology siblings`. Whether the code repo
exists yet is read off the disk, so the flag would answer a question the layout
does not ask, and the old four-way matrix collapses to three real paths.

Generate sibling CI as two `actions/checkout` steps with explicit `path:`
arguments under a common parent, then run the installed CLI with
`working-directory:` set to the docs checkout. The composite Action cannot carry
a `working-directory`, so the sibling workflows install and call the CLI
directly.

Keep `--delta`'s refusal in the siblings layout. `git worktree add` checks out
tracked files only, so the sibling code repo is absent from the base checkout
and every finding over it would survive as new. The guard now covers one case
instead of three; teaching `--delta` to compare across the sibling boundary is
open work tracked in
[`RFC 0044`](../80-evolution/rfcs/0044-cross-repo-delta.md).

Stop using lettered topology names. `same-repo` and `siblings` describe the
layout and cannot collide the way "Topology B" did.

## Alternatives Considered

- **Keep all four.** Rejected: the two nested layouts served the same goal as
  `siblings` at the cost of a repository nested inside another's working tree,
  and their maintenance was paid on every path-resolving change.
- **Keep the nested-code layout and drop `siblings`.** Rejected: it is the one
  the tool could already scaffold, so it was the cheap answer, but it is also
  the one that requires a gitignore rule to stay correct and that no git command
  understands. `siblings` needs neither.
- **Keep `init-docs-only` as a second command.** Rejected: scaffolding a docs
  tree, an `irminsul.toml` and CI is one job. A second command forced every
  prompt, error message and help string to teach two entry points for it.
- **Record the layout in `irminsul.toml` as `paths.topology`.** Rejected here,
  not on the merits — it is RFC 0044's proposal and belongs to the `--delta`
  work, not to a decision about which layouts exist.
- **Solve sibling `--delta` in the same change.** Rejected: the refusal is
  correct and shipped, and coupling a topology reduction to a new comparison
  semantics would make both harder to review.

## Consequences

- One private-docs story to document, test, and support;
  [private docs](../30-workflows/private-docs.md) describes one layout instead
  of two.
- Repositories using either nested layout have no migration command. Moving to
  `siblings` is a filesystem move plus a `source_roots` edit, and the checks
  behave the same afterwards, but nothing automates it.
- Nothing detects a retired layout at runtime, and nothing will. Both nested
  shapes still check clean, because the two mechanisms that made them work were
  never nested-layout code: the enclosing-ignore filter earns its keep on
  gitignored generated code configured as a source root, and resolving a path
  through its own nearest `.git` earns its keep when the invocation root sits
  below the enclosing git root, as in a monorepo subfolder — the shape this
  repository's own fixtures use. Retiring a layout means deleting the code that
  existed to serve it, which is done; it does not mean adding code to police it.
  A detect-and-reject path would be new machinery built for a layout we no
  longer support, and it could not tell the retired shapes apart from the
  supported uses above without breaking them.
- `--delta` still refuses the siblings layout, so the private-docs story keeps
  paying for the missing feature — now visibly, as the single remaining case.
- Claims on files outside the docs repo are written source-root-relative, which
  reads less obviously than the nested layouts' repo-relative paths. This is
  existing behavior, now the only behavior, and the workflow doc must teach it.
- The retirement tombstones above make current guidance that still teaches
  `init-docs-only` or the lettered names fail the `retired-references` audit.
  For that to be true rather than aspirational, the audit is a **hard** check
  emitting **errors**, so it blocks without `--strict` — CI's dogfood step runs
  none. It reads every stable doc including ADRs, plus the repository readme,
  the two agent manifests, the Claude guide, the docs readme, the glossary and
  the contributing guide — frontmatter included. Two things are out of range by
  design: an ADR is never audited against the tombstones it declares itself,
  and RFC records are frozen by
  [`ADR-0016`](0016-freeze-implemented-rfc-records.md), so neither their text
  nor the generated manifest rows that echo their titles are read.
