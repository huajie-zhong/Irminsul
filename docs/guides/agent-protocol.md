---
id: agent-protocol
title: Agent lifecycle protocol
status: stable
describes: []
summary: The required work order any agent must follow when editing this repository.
inventory:
  - kind: cli
    source: src/irminsul/cli.py
    items:
      - orient
      - context
      - check
      - regen agents-md
      - list lifecycle
      - change status
      - change verify
      - change transition
      - change finalize
---

# Agent lifecycle protocol

This document defines the work order an agent must follow when editing this
repository. The agent navigation manifest at [`AGENTS.md`](../AGENTS.md) is the
entry point; it summarizes the doc system and deep-links here.

The protocol is universal — it applies to any project that uses Irminsul, not
just this one. Follow each step in order; do not skip ahead.

## What to assume

The work order says what to run. These say how to read what comes back, and they hold
for any harness: an agent reaches them through the root [`AGENTS.md`](../../AGENTS.md),
which Cursor and Codex read natively and which the Claude Code pointer imports.

- **A finding is right about its fact and silent about the meaning.** It reports
  something mechanical: this link resolves to nothing, this symbol is absent, no doc
  claims this file. Take that fact as true. What a check never knows is whether the prose
  is *correct*, so "the check is wrong" is almost never the answer — "the check is
  reporting something I did not intend" sometimes is.
- **A green run does not mean the docs are right.** It means nothing provable is broken.
  The semantic half is `irminsul list review`, a queue to read, not a gate that stops you.
- **A suggestion is a menu, not a ranking.** Several end "...or remove it". That branch is
  for when the thing really is gone. Taking it to clear a finding leaves documentation
  that passes and says nothing, which is worse than the finding.
- **The docs are part of the deliverable.** When the doc and the code disagree, work out
  which is wrong before editing either. Which one wins depends on what kind of claim it is
  ([authority follows the kind of claim](../decisions/authority-follows-the-kind-of-claim.md)):
  code is authoritative for what a tool can rebuild without judgment — surfaces,
  signatures, config keys — and not for intent, constraints, or rationale. If the code
  changed on purpose, correct the sentence. If the sentence describes what the code
  *should* do, that is a bug to report, not a doc to rewrite.

## The foundation layer binds choices

The `foundation/` layer records why the project exists, what it values, and what it will
not do. Those are constraints on the change, not only on the prose describing it. Follow
them unless one is wrong for the work at hand — and then say so to the user and let them
decide, rather than routing around it. Report a principle you had to break even when the
build is green; no check will raise it for you.

## Moves that make documentation worse

Each turns a finding green while making the tree less true. Most are reported now; none
is a repair.

- Delete a true sentence, a `claims:` entry, an `<!-- anchor: -->` marker, or an
  `inventory:` entry in order to clear a finding.
- Narrow a `describes:` glob so files stop being claimed.
- Change a doc's `status:` to `draft`.
- Add an `irminsul:ignore` comment as the first move, or one whose reason restates the
  finding instead of saying why the doc is right.
- Run `check --init-baseline`, or edit the baseline, to get a green run.
- Edit an implemented RFC, or delete an accepted decision record.
- Re-pin an anchor before re-reading the prose it marks.
- Remove a check from `checks.enabled`, or weaken the workflow that runs it.

## Acting on a finding

Every finding has a class — **certain** (an error; the tree breaks a rule), **hint** (a
warning or info; it needs judgment), **time** (elapsed time caused it, so report rather
than fix it in passing). `irminsul explain <code>` describes any code. Then, in order:

1. **Read the code the finding names.** Do not infer what it does from the doc you are
   about to edit.
2. **The claim is false and the code is right** — rewrite the sentence to say what the
   code does.
3. **The claim is false and the code is wrong** — fix the code, and say so.
4. **The claim is true and the check cannot see why** — keep the claim and add
   `<!-- irminsul:ignore <check-or-code> reason="..." -->` on that line. The reason is
   required and must say why the doc is right.
5. **What it described is genuinely gone** — remove the claim *and* the code in the same
   change. That is the one case where removal costs nothing.

## Work order

0. **Orient first.** Run `irminsul orient` (or `irminsul orient --format json`)
   to load the repo's structure, doc totals, entry docs, and command
   vocabulary, then read [`AGENTS.md`](../AGENTS.md) before any other step.
   The manifest names the layers, the Three Laws, and this protocol.
   If the manifest is missing or its generated section is stale, run
   `irminsul regen agents-md` and proceed.

1. **Locate context before editing.** Run
   `irminsul context --before-edit <target...>` to package ownership,
   dependencies, tests, active RFCs, and relevant findings for the work ahead.
   Use the path, topic, and changed modes directly when a focused power-tool
   query is more appropriate. The packet is a map, not the documentation: read
   the owning docs it names, and the decision records they link, before
   changing code.

2. **Update the foundation before the implementation.** If the request changes
   project direction, update the foundation docs or create an RFC before
   changing implementation.

3. **Create or update an RFC for significant change.** If the work proposes a
   significant behavior, architecture, lifecycle, CLI, or check change, create
   or update an RFC.

4. **Resolve accepted RFCs with an ADR.** When an RFC is accepted, create or
   update an ADR and link the RFC to that decision record. Write it with
   `irminsul new adr "<title>"`, whose template carries the section-by-section
   convention; the rules the template cannot state are in
   [the decisions index](../decisions/INDEX.md). Keep it short enough to review:
   what changes, why, and what protection is gained or lost. The decision itself
   is human-authorized: apply it with
   `irminsul change transition <id> accepted --confirm` only after the user has
   approved it. Writing the record is not the approval — it makes the change
   visible and reviewable, and nothing here can establish that a person agreed.

4a. **Work the bound-change loop for accepted RFCs.** Discover accepted work
   with `irminsul list lifecycle --queue`, orient with
   `irminsul change status <id>`, implement, then run
   `irminsul change verify <id>` and resolve its mechanical blockers and
   semantic-review clues. When the report is mechanically ready and the user
   has authorized completion, run `irminsul change finalize <id> --confirm`
   with the reviewed `--anchor` bindings — finalization is the only path to
   `rfc_state: implemented`.

5. **Keep component docs honest.** When code is added or moved, create or
   update component docs with up-to-date `describes` mappings and tests
   metadata. Before renaming or moving a code symbol, doc, or directory, run
   `irminsul refs <doc>` or `irminsul refs --symbol <name>` and update every hit
   before completing the move. Neither enumerates the whole blast radius:
   `refs --symbol` reads `describes` globs and `claims.evidence` frontmatter, so a
   symbol named only in prose, or only in code, returns nothing. Grep the tree too
   before trusting an empty result.

6. **Keep component docs and guides current.** When commands or reference
   surfaces change, update the owning component docs and any affected guides.

7. **Supersede deliberately.** When a doc replaces another doc, use
   `supersedes` on the new doc and run `irminsul fix` to update the old doc's
   metadata.

8. **Validate after editing.** Run `irminsul context --after-edit` — on a branch whose
   work is committed, with `--base-ref origin/main`, because HEAD already holds those
   commits and a comparison with it would be a comparison with itself. It reports the
   repository's state and what this change introduced as two separate verdicts; the
   second is the one you are answerable for, and the first is what you inherited.
   Resolve its errors and deterministic next actions, then run
   `irminsul check` as the local gate: fix every certain finding, and investigate
   each hint, then fix the doc or leave a reasoned `irminsul:ignore` comment. Before
   opening the pull request run `irminsul check --diff origin/<base>`, which is what CI
   enforces and adds the passes that judge the change rather than the tree. Run
   `irminsul list review --changed` and confirm each listed claim against the code
   it names; no check decides whether a sentence is true. A claim listed because your
   change touched its evidence is a question, not a violation: read the declaring
   document and the decisions it links, then answer the question it asks. A
   `governs-evidence` claim asks whether the code still obeys it, so if it no longer
   should, say so to the user rather than editing the sentence to fit the code. A
   `review-on-divergence` claim asks which of the two is now wrong; correct that one and
   say why in the change. Bind each `unbound` name it
   lists with an anchor, choosing the file from `irminsul anchors --suggest`. For larger work, also run
   `irminsul list undocumented`.

9. **Report remaining signal.** Report any remaining warnings, skipped checks,
   or follow-up decisions in the final response.

## Scope & Limitations

- This protocol covers the work order; it does not enumerate doc-system
  rules (those live in [`CONTRIBUTING.md`](../CONTRIBUTING.md)) or coding
  conventions (those live in the project's own style guide).
- Steps 8–9 require running `irminsul check`; the protocol does not itself
  define which checks run or which findings block — that is the province of
  the check registry in `src/irminsul/checks/__init__.py`, each code's class, and
  the project's `irminsul.toml`.
- The protocol as a whole is not one check; individual transitions are
  enforced by `rfc-lifecycle`, `rfc-follow-through`, and `change-binding`.

## Rationale and alternatives

The rationale, drawbacks, and rejected alternatives for this protocol live in
[Agent interface](../decisions/agent-interface.md).
