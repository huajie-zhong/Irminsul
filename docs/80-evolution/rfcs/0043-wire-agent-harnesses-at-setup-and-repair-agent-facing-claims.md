---
id: 0043-wire-agent-harnesses-at-setup-and-repair-agent-facing-claims
title: "Wire agent harnesses at setup and repair agent-facing claims"
audience: explanation
tier: 2
status: draft
describes: []
rfc_state: draft
affects:
- init
- orient
- context
- cli
- mcp-server
- new-list-regen
- check-pipeline
resolved_by: docs/50-decisions/0022-scaffold-agent-harness-wiring-statically.md
required_updates:
- path: docs/20-components/init.md
  reason: Init now writes harness wiring, so the scope limitation denying local tooling configuration is false.
  kind: update
- path: docs/20-components/orient.md
  reason: Entry docs are no longer limited to the docs root.
  kind: update
- path: docs/20-components/context.md
  reason: The next-command hints claim becomes true and needs its derivation described.
  kind: update
- path: docs/20-components/mcp-server.md
  reason: Registration is scaffolded, so the manual wiring instruction becomes the fallback.
  kind: update
- path: docs/30-workflows/check-pipeline.md
  reason: The GitHub annotation format is now the Action default and is undocumented.
  kind: update
---

# RFC 0043: Wire agent harnesses at setup and repair agent-facing claims

## Summary

Close the last mile between Irminsul's agent surfaces and the harnesses that drive
agents. `init` gains two static harness files — a project MCP registration and a
trigger-only skill — so a freshly adopted repository is wired on arrival instead of
after an undocumented manual step. Alongside that, repair four agent-facing surfaces
that currently state something untrue: the duplicated root entry point, the orientation
report's entry-doc scope, the context report's hints field, and the fix command's
account of what it changed. Wire the existing GitHub annotation format into the Action.

## Motivation

Irminsul already exposes a complete read surface for agents: a read-only MCP server,
orientation, context, references, listings, derived surfaces, and change queries, each
with versioned JSON. The capability is not the gap.

The gap is that nothing connects that capability to a harness. The MCP server is
unreachable until a human discovers and runs a registration command that lives only in
a component document, so for most adopters the tool's richest agent interface does not
exist. Adoption is measured by what a fresh clone can do, and a fresh clone can do none
of it.

The second problem is worse than a missing feature, because a false statement to an
agent is more expensive than silence. Four surfaces currently mislead:

- The repository's root agent entry point was copied rather than referenced, and the
  copy rotted. It names the wrong harness, and it teaches the opposite of current
  behaviour for unknown check names. Root-level files sit outside the docs root, so no
  check can see them — the one place the tool is structurally blind is where its own
  entry point decayed.
- Orientation reports entry documents only from under the docs root, so it cannot name
  the root entry point that adoption creates. The command designated as the first call
  cannot point at the file designated as the first read.
- The context report's hints field ignores its inputs and returns a constant, while its
  component document advertises next-command hints.
- The fix command reports planned fixes after a live run, but no-op fixes are skipped
  during application, so the report overstates what changed.

Each is a claim the repository makes about itself that the repository does not honour.
Repairing them is the same discipline the tool sells.

## Requirements

### Requirement: Wire the MCP server at adoption
ID: wire-mcp-at-setup
Provenance: code

Adoption MUST write a project-scoped MCP registration and a harness skill into the
target repository. Both MUST be portable across operating systems, and neither MUST
overwrite an existing file at the same path unless forced.

#### Scenario: Fresh adoption
- **WHEN** a repository is initialized
- **THEN** an MCP registration naming the `irminsul` server and a skill file are written, and both appear in the created-file report

#### Scenario: Pre-existing registration
- **WHEN** the target already has an MCP registration
- **THEN** it is left byte-identical, a note names the skipped file, and the manual registration command is printed

#### Scenario: Portability
- **WHEN** the registration is written on any supported platform
- **THEN** it invokes the bare console script against the current directory, containing no absolute, virtual-environment, or platform-specific path

### Requirement: One canonical root entry point
ID: single-root-entry-point
Provenance: adr

The repository MUST carry exactly one root document that describes the project to an
agent. Any other root harness file MUST reference it rather than restate it.

#### Scenario: Harness-neutral content
- **WHEN** an agent reads the root entry point
- **THEN** it finds the navigation route, the edit loop, and the verification gate without harness-proprietary framing

#### Scenario: No second copy
- **WHEN** a second root harness file is present
- **THEN** it contains a reference to the canonical entry point and no duplicated project description

### Requirement: Orientation names the root entry point
ID: orient-reports-root-router
Provenance: code

The orientation report MUST include a root-level entry document when one exists on
disk, ordered ahead of docs-root entries, without changing the report's version or the
type of its entry-doc field.

#### Scenario: Root entry present
- **WHEN** a root entry document exists
- **THEN** it is reported first, as a repo-relative path, in both plain and JSON output

#### Scenario: Root entry absent
- **WHEN** no root entry document exists
- **THEN** the reported entry documents are exactly the docs-root entries, unchanged

### Requirement: Context hints follow from findings
ID: context-hints-are-actionable
Provenance: code

Hints MUST be derived from the findings relevant to the query, using the same
finding-to-fix mapping the findings surfaces already use, and MUST retain the
verification gate as the terminal hint.

#### Scenario: Fixable finding
- **WHEN** a relevant finding is remediable
- **THEN** its fix invocation appears in the hints, deduplicated

#### Scenario: No fixable finding
- **WHEN** no relevant finding is remediable
- **THEN** the hints contain the verification gate alone, preserving the existing output contract

### Requirement: Fix reports what it did
ID: fix-reports-what-it-did
Provenance: code

A live fix run MUST report the files it wrote; a planned run MUST report the fixes it
would attempt. The command MUST offer versioned JSON so an agent can consume the result
without parsing prose.

#### Scenario: No-op fix
- **WHEN** a harvested fix leaves its file unchanged
- **THEN** a live run does not list that file as changed

#### Scenario: Machine-readable result
- **WHEN** an agent requests JSON
- **THEN** written paths, planned fixes, held fixes, and errors are returned under a version field

### Requirement: Annotate findings in continuous integration
ID: ci-annotations-by-default
Provenance: code

The Action MUST request the annotation output format by default and MUST allow it to be
overridden, without altering the exit code for any format.

#### Scenario: Default run
- **WHEN** the Action runs without format input
- **THEN** the check is invoked with the annotation format and the exit code is unchanged

#### Scenario: Strict and format together
- **WHEN** strict mode and a format are both selected
- **THEN** both reach the check invocation

## Detailed Design

**Harness files are static constants, not templates.** The MCP registration carries no
project-specific value, so it needs no substitution. It is a module constant in the init
package rather than a scaffold template, because the built wheel currently contains no
dot-prefixed files and inclusion of a hidden template under the configured package root
is unverified — a silently excluded template fails at release time, not at test time.
The skill file is a constant for the same reason.

**The skill is a trigger, not a copy.** It carries the activation condition and two
pointers: run orientation first, then follow the recorded work order. It deliberately
carries no command table and no restatement of the work order, because both already have
one home and a live retrieval path. A skill that restated them would be a third copy in
a format no check can read.

**Both harness files are unpoliced by design.** Neither is derived from anything, so a
drift check would compare a constant against itself. The cost of that check would fall
on adopters who legitimately delete either file — a repository using a different harness,
or one that vendors the tool without the optional server dependency. The accepted
consequence is that a change to the server's invocation will not mechanically flag
already-adopted repositories.

**Root entry-point de-duplication is a deletion, not a re-synchronization.** The copy
rotted precisely because nothing compared the two files, and nothing can: they sit
outside the docs root. Collapsing the second file to a reference removes the compared
pair rather than adding machinery to compare it. This is what adoption already instructs
adopters to do.

**Orientation gains a separate root-scoped name list.** The docs-root list stays as it
is. Only the canonical entry point is probed at the root; other repository-conventional
names would duplicate their docs-root counterparts as noise, and harness-proprietary
names do not belong in a harness-neutral report.

**Hints reuse the existing finding-to-fix mapping** rather than introducing a parallel
one. That mapping already resolves the registry, harvests per finding, and appends the
confirmation flag when a harvested fix would otherwise be held. The hints field keeps its
place in the versioned output, because removing it would break a published contract to
delete a field that is about to become useful.

**The Action accumulates arguments** instead of branching per flag combination. The
current nested form cannot express a third flag without another branch.

## Tasks

- `T1` Collapse the duplicated root entry point to one canonical document and one reference. (req: single-root-entry-point)
- `T2` Report root-level entry documents from orientation. (component: orient)
- `T3` Derive context hints from relevant findings via the shared fix mapping. (component: context)
- `T4` Add the harness constants and the non-clobbering writer, and call it from the single adoption funnel. (component: init)
- `T5` Request the annotation format from the Action by default and document it. (component: check-pipeline)
- `T6` Report written files on live fix runs and add versioned JSON output. (component: cli)
- `T7` Record the scaffolded registration as the primary wiring path and the manual command as the fallback. (component: mcp-server)

`T5` and `T7` are documentation-only by construction: the annotation format already
existed in the CLI and only the Action invocation and its prose were missing, and the
server's tool set is unchanged — only which wiring path is primary. Neither owns a source
change, so both surface as unbound review clues rather than as evidence.

## Drawbacks

- The registration content exists both as an init constant and as an illustrative block
  in the server's component document. At this size there is no generator-free way to
  keep one copy, so the duplication is accepted and recorded rather than hidden.
- Writing harness files means adoption now touches paths outside the docs tree and the
  CI directory, widening what adoption is responsible for.
- Leaving both harness files unpoliced accepts silent staleness if the server's
  invocation changes.
- A skill is a harness-specific format; if its conventions change, the file is stale
  with no mechanical signal.

## Alternatives

- Generate the harness files as a regen target governed by a drift check. Rejected for
  the registration because it is derived from nothing, and because a second regen target
  and a second opt-in check are disproportionate to a seven-line constant that adopters
  may legitimately delete.
- Ship harness files for every known harness. Rejected because the two other harnesses
  in scope read the root entry point natively, and one keeps its server registration in
  a user-global file that adoption has no business writing.
- Add slash-command wrappers for the command vocabulary. Rejected as a third
  ungoverned copy of a vocabulary that is already served live and already policed
  against command drift.
- Move the optional server dependency into the base dependency set so the registration
  always resolves. Rejected because the failure is visible and self-diagnosing, and the
  cost would fall on every installation.
- Re-synchronize the two root files and keep both. Rejected because that is the state
  that produced the rot.
- Delete the context hints field instead of repairing it. Rejected because it is part of
  a published output contract.

## Unresolved Questions

- Should the harness skill be surfaced by orientation, or does naming it there invite the
  restatement the design excludes?
- Should the remaining write commands gain versioned JSON, and what envelope describes
  "what changed" uniformly across them?
- If a future change alters the server's invocation, what mechanism warns
  already-adopted repositories, given the deliberate absence of a drift check?
