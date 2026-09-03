---
id: 0023-scaffold-agent-harness-wiring-statically
title: "ADR-0023: Scaffold agent harness wiring statically"
audience: adr
tier: 2
status: draft
describes: []
summary: Write harness wiring at adoption as unpoliced static constants, and repair the agent-facing surfaces that state something untrue.
---

# ADR-0023: Scaffold agent harness wiring statically

## Status

Proposed. Resolves
[`0043-wire-agent-harnesses-at-setup-and-repair-agent-facing-claims`](../80-evolution/rfcs/0043-wire-agent-harnesses-at-setup-and-repair-agent-facing-claims.md).

## Context

Irminsul's agent read surface is complete — orientation, context, references,
listings, derived surfaces, change queries, and a read-only MCP server, each with
versioned JSON. None of it is connected to a harness. The MCP server is unreachable
until a human finds and runs a registration command documented only in a component
page, so a fresh clone can use none of it.

Separately, four agent-facing surfaces state something untrue. The root agent entry
point was copied rather than referenced and the copy rotted, naming the wrong harness
and teaching the opposite of current behaviour for unknown check names. Orientation
reports entry documents only from under the docs root, so it cannot name the root entry
point adoption creates. The context report's hints field ignores its inputs and returns
a constant while its component page advertises next-command hints. The fix command
reports planned fixes after a live run, though no-op fixes are skipped during
application.

Root-level files sit outside the docs root, so the doc-graph checks cannot reach them;
only the retired-reference audit reads the readme and the agent files. The tool is
structurally blind exactly where its own entry point decayed.

## Decision

Write three harness files at adoption: a project-scoped MCP registration, a
trigger-only skill, and a pointer file for Claude Code that imports the root entry
point, so the harness that reads that file reaches the router the skill assumes. Hold
all three as module constants in the init package rather than as scaffold templates,
because two of them have to be merged into an existing file under `--force` — a
registration may hold servers the adopter needs, a pointer file the adopter's own
guidance — and the template writer only knows skip-or-replace; the skill sits beside
them so the three share one writer and one skipped-file note. None carries a
project-specific value, so none needs substitution.

Keep the skill a trigger. It carries its activation condition and two pointers: run
orientation first, then follow the recorded work order. It carries no command table and
no restatement of that work order, because both already have a single home and a live
retrieval path.

Leave the files unpoliced. None is derived from anything, so a drift check would
compare a constant against itself, and its cost would fall on adopters who legitimately
delete any of them. Accept the optional server dependency's absence as a failure the
CLI diagnoses itself rather than moving it into the base dependency set; a harness may
surface that failure only as a closed connection, so the server's component page and
the adoption next steps name the install the harness's PATH needs and the command that
reproduces the diagnosis.

Skip the files when present, unless forced. Reuse the existing skip-if-exists policy
and the pre-existing-file note, and print the manual registration command as the fallback
unless the existing registration already names the server. Under `--force`, replace the
skill but merge the other two: set the `irminsul` entry in the registration, keeping
every other server, and prepend the import to a pointer file that lacks it, keeping its
content. Never rewrite a registration that cannot be parsed, forced or not: leave it
alone and name it in the note, since overwriting it would delete whatever the adopter
keeps there.

Collapse the duplicated root entry point to one canonical document and one reference,
rather than re-synchronizing the pair. Add no check for the result: after the collapse
there is one file and nothing to compare.

Repair the three remaining surfaces in place. Orientation gains a separate root-scoped
name list holding only the canonical entry point. Context hints reuse the existing
finding-to-fix mapping instead of a parallel one, and the hints field keeps its place in
the versioned output. Fix reports written files on a live run and planned fixes only
under a planned run, and gains versioned JSON.

Request the annotation output format from the Action by default, overridable, with the
exit code unchanged for every format.

## Alternatives Considered

- **Generate the harness files as a regen target with a drift check.** Rejected for the
  registration because it is derived from nothing; a second regen target plus a second
  opt-in hard check is disproportionate to a seven-line constant adopters may delete.
- **Ship harness files for every known harness.** Rejected because the other harnesses in
  scope read the root entry point natively, and one keeps its server registration in a
  user-global file that adoption has no business writing.
- **Add slash-command wrappers for the command vocabulary.** Rejected as a third
  ungoverned copy of a vocabulary already served live and already policed against
  command drift.
- **Ship the registration as a hidden scaffold template.** Dot-prefixed templates do
  ship in the built wheel, so this was viable; rejected because the template writer
  cannot merge into an existing registration, which `--force` has to do.
- **Move the optional server dependency into the base set.** Rejected because the failure
  is visible with a one-line remedy already printed, and the cost would fall on every
  installation.
- **Re-synchronize the two root files and keep both.** Rejected because that is the state
  that produced the rot.
- **Delete the context hints field instead of repairing it.** Rejected because it belongs
  to a published output contract.

## Consequences

- A freshly adopted repository reaches the MCP server without a manual step.
- Adoption now writes outside the docs tree and the CI directory, widening its
  responsibility.
- The registration content exists both as an init constant and as an illustrative block
  in the server's component page, and this repository tracks its own copies of all
  three harness files. A repository-local test binds all of them to the constants, so drift
  fails this suite without adding an adopter-facing check.
- A change to the server's invocation will not mechanically flag already-adopted
  repositories, and the skill is stale without signal if harness conventions change.
- The root entry point remains outside every check's reach, so its accuracy stays a
  review responsibility — but there is only one file to review.
- Continuous integration reports findings as annotations on the failing line by default.
