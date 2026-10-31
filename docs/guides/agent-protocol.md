---
id: agent-protocol
title: Agent lifecycle protocol
status: stable
describes: []
summary: How an agent acts on a finding and changes the project's direction; the edit loop every change follows is in the root AGENTS.md.
inventory:
  - kind: cli
    source: src/irminsul/cli.py
    items:
      - explain
      - anchors
      - refs
      - fix
      - new adr
      - new rfc
      - list lifecycle
      - change status
      - change verify
      - change transition
      - change finalize
---

# Agent lifecycle protocol

The root [`AGENTS.md`](../../AGENTS.md) carries the edit loop every change follows and
what a finding does and does not tell you. This guide carries the two procedures that
loop points to: acting on a finding, and changing the project's direction.

## Acting on a finding

Every finding has a class — **certain** (an error; the tree breaks a rule), **hint** (a
warning or info; it needs judgment), **time** (elapsed time caused it, so report rather
than fix it in passing). Its code also declares one of four answers, the one way a
correct doc turns it green, and `irminsul explain <code>` prints both:

- **fix** — the doc or the config is wrong whenever the finding fires; change it.
- **line** — `<!-- irminsul:ignore <code> reason="..." -->` on the finding's line, or
  alone on the line above it; one above a fenced block covers the whole block. The reason
  is required and says why the doc is right.
- **pin** — re-read the prose or the claim against its code, then run the
  `irminsul anchors --re-pin` command the finding prints, which moves only that pin.
- **trailer** — do what the finding's answer asks (`irminsul explain <code>` names it), then
  add the `Irminsul-Reviewed` commit trailer the suggestion prints, on the commit that carries
  the last change to the files it is about or a later one; an earlier commit's trailer does
  not count. The reason says why the finding is acceptable. `irminsul check` and
  `irminsul context --after-edit` list the trailers their open findings can take, under one
  heading just before the summary; a finding a trailer already accepted is not listed.

Then, in order:

1. **Read the code the finding names.** Do not infer what it does from the doc you are
   about to edit.
2. **The claim is false and the code is right** — rewrite the sentence to say what the
   code does.
3. **The claim is false and the code is wrong** — fix the code, and say so.
4. **The claim is true and the check cannot see why** — take the answer its code
   declares, and no other: an ignore comment on a code that declares `fix` or `pin` hides
   the next real mismatch too.
5. **What it described is genuinely gone** — remove the claim *and* the code in the same
   change. That is the one case where removal costs nothing.

## Changing direction

A step that opens with a condition applies only when that condition holds.

1. **Update the foundation before the implementation** when the request changes the
   project's direction, or create an RFC first.
2. **Create or update an RFC** for a significant behavior, architecture, lifecycle, CLI,
   or check change. `irminsul new rfc "<title>"` writes it in two parts, or `--small`
   for a sign-off: the owner's part first (Summary, Problem, How it works, Cost and
   risk, Decisions), then the agent's part from `## Design detail` on, with
   `## Requirements` and `## Tasks`. Put every list of names, files and ids in the
   agent's part, and write the owner's part by the
   [style guide](style-guide.md#the-owners-part-of-an-rfc); `rfc-structure` keeps the shape.
3. **Resolve an accepted RFC with an ADR** that links it, written with
   `irminsul new adr "<title>"`; its template carries the convention, and
   [the decisions index](../decisions/INDEX.md) the rules a template cannot state. Keep
   it short enough to review: what changes, why, and what protection is gained or lost.
   Accepting is the user's decision: run `irminsul change transition <id> accepted
   --confirm` only after they approve. Writing the record is not the approval, and
   nothing here can establish that a person agreed.
4. **Work an accepted RFC through the bound-change loop.** Find it with
   `irminsul list lifecycle --queue`, orient with `irminsul change status <id>`,
   implement, then resolve the blockers and review clues `irminsul change verify <id>`
   reports; both judge the change `check --diff` judges, so on a branch give them
   `--base-ref`. Once the user has authorized completion, commit or stash your work,
   because `irminsul change finalize <id> --confirm` refuses a tree with uncommitted
   work, and run it with the reviewed `--anchor` bindings. Finalizing is the only path to
   `rfc_state: implemented`.
5. **Supersede deliberately:** set `supersedes` on the new doc and run `irminsul fix` to
   update the old doc's metadata.

Before moving or renaming a doc, run `irminsul refs <doc>` and update every hit. It reads
`depends_on` and Markdown links, so a doc named only in prose returns nothing; before
renaming a code name or a directory, search the tree for it.

## Scope & Limitations

- This guide does not enumerate doc-system rules ([`CONTRIBUTING.md`](../CONTRIBUTING.md)
  does) or coding conventions, nor which checks run or block: that is the registry in
  `src/irminsul/checks/__init__.py`, each code's class, and `irminsul.toml`.
- Neither procedure is one check; `rfc-lifecycle`, `rfc-follow-through` and
  `change-binding` enforce individual transitions.

## Rationale and alternatives

The rationale, the rejected alternatives and where each piece of the agent guidance lives
are in [Agents get stateless read-only queries and one written loop](../decisions/agents-get-stateless-read-only-queries-and-one-written-loop.md).
