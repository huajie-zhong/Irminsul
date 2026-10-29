---
id: an-rfc-has-an-owners-part-and-an-agents-part
title: "An RFC has an owner's part and an agent's part"
status: stable
describes: []
rfc_state: implemented
affects:
  - checks
  - new-list-regen
  - init
resolved_by: docs/decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md
summary: Every RFC opens with a short part the owner reads to decide, and keeps the names, ids and migration lists an agent needs in a part after it.
required_updates: []
weight: large
---

# An RFC has an owner's part and an agent's part

## Summary

An owner sees what an RFC proposes and what it needs from them in the time its stakes deserve:
5 to 30 seconds for a sign-off, about two minutes for a large change. Every RFC declares a
**weight**, opens with a short **owner's part** in plain words, and moves every list of names,
ids and migration steps into an **agent's part** below it; `irminsul new rfc` writes both parts
and a check keeps their shape. Four decisions, all answered.

## Problem

The draft `claim-evidence-names-a-part` was approved only after its owner asked for a
summary. Its design section puts the one fact the owner needs, that a pin covers a whole file
so an edit anywhere in it re-asks the claim, beside a paragraph naming ten claims, eight files
and twelve functions; whether it works for other languages is answered only mid-table. The
template cannot help: it runs Summary, Motivation, Detailed Design, Requirements, Tasks,
Drawbacks, Alternatives and Unresolved Questions, so nothing separates the two readers and
the owner's questions come last.

## How it works

**The owner's part comes first**, in five sections: **Summary** (the gain, then how, then how
many decisions need you, so a reader with no questions can stop there); **Problem** (one
worked example with names and numbers); **How it works** (the mechanism at a level you can
question: what is general, where it can grow, such as to other languages, and what it leaves
out); **Cost and risk**; and **Decisions** (options, the deciding factors and a
recommendation, later the answers). It is written for a person, in plain words with terms
defined where they appear, and reads in about two minutes.

**The weight sets how much the owner reads.** A *small* RFC is a sign-off, such as changing
an exit code to match a rule: its owner's part is a Summary that says what changes and what you
sign off on, and Decisions, read in 5 to 30 seconds. A *large* RFC changes a decision or the
foundation, breaks adopters, adds or removes a check or a command, or migrates data or history,
and gets all five sections. The author proposes the weight; the owner can change it.

**The agent's part starts at `## Design detail`**: every list of names, files, ids and
migration steps, then Requirements and Tasks as today. Those two are all the code reads, so
nothing new is parsed.

**A check keeps the shape.** It reports a missing weight, an owner's section its weight
requires that is missing or empty, a misplaced owner's section, and, as
a hint, a paragraph in the owner's part with four or more code spans: a countable sign of a
list that belongs below, not a judgement of the prose.

## Cost and risk

One template, one small check that shares the decision-record check's section reader, and
edits to two guides. The density hint will sometimes fire on a paragraph that needs its names,
and an ignore comment with a reason answers it. No check can tell whether a decision was
buried in the agent's part; review still has to.

## Decisions

Answered by the owner on 2026-10-28:

1. **The two drafts already approved** are rewritten in this layout while still drafts, their
   Requirements and Tasks unchanged, and accepted after. Implementing them from the new layout
   is its first real test.
2. **The two implemented RFCs** are rewritten in this layout at a second history reset, once
   this layout and its check exist. The cost was weighed: the published `v0.4.0` tag leaves
   `main`'s history, and every clone re-clones.
3. **The density hint** is included, at four code spans in one paragraph.
4. **Two weights for now**, small and large, each with its own shape, and no check that guesses
   a weight from counts; the owner judges it on sight. A third weight can come later if one
   earns its own shape.

## Design detail

- **Not chosen**: a command that prints the owner's part, since reading the top of the file
  does the same; a file for each part, which would drift apart; a word limit, since a long
  problem can be the right length and density is what hurts scanning. "About two minutes" is
  a guideline the style guide states, not something a check counts.
- **Out of scope**: decision records mix the same two readers; a later change can apply the
  layout to them. Implemented RFCs are not judged by the check (decision 2 rewrites this
  repository's two at the reset).
- **Weight**: a frontmatter field `weight: small | large` on RFC docs, added to
  `DocFrontmatter` (and so to the `frontmatter-fields` surface) and read only by
  `rfc-structure`. `irminsul new rfc` writes `weight: large` and the five sections;
  `irminsul new rfc --small` writes `weight: small` with Summary and Decisions only. Required
  owner's sections: small, Summary and Decisions; large, all five. Both shapes have
  `## Design detail`, `## Requirements` and `## Tasks`.
- **Template** (`src/irminsul/new/templates/rfc.md.j2`): `## Summary`, `## Problem`,
  `## How it works`, `## Cost and risk`, `## Decisions`, then `## Design detail`,
  `## Requirements`, `## Tasks`, each owner's section with one guiding HTML comment. The
  example requirement and task comments stay. `## Motivation`, `## Detailed Design`,
  `## Drawbacks`, `## Alternatives` and `## Unresolved Questions` go.
- **Shared section reader**: the per-slug H2 collection in `checks/adr_structure.py`
  (`by_slug` and `_section_findings`) moves to one helper both checks call with their own
  required list, so the rule "a record has these H2 sections, once each, non-empty" has one
  implementation.
- **`rfc-structure`**, a new registered check, enabled in this repository and in the
  `irminsul.toml` that `init` writes (an existing config lists its checks, so adopters opt in):
  - `rfc-structure/missing-weight` (certain, drafts-exempt): a draft or accepted RFC with no
    `weight`, or one other than `small` or `large`.
  - `rfc-structure/missing-section` (certain, drafts-exempt): an owner's section its weight
    requires, absent or empty apart from HTML comments and placeholder lines, in a draft or
    accepted RFC.
  - `rfc-structure/section-out-of-order` (certain): an owner's section heading below
    `## Design detail`, or `## Design detail` absent while `## Requirements` is present.
  - `rfc-structure/dense-paragraph` (hint, warning): a paragraph of the owner's part, its
    list items each a paragraph, holding four or more code spans, counted with the code-span
    reader `code-references` uses.
  - Skips an RFC whose `rfc_state` is `implemented` or `rejected`.
- **`rfc-follow-through/retained-questions`** reads `## Unresolved Questions`, which the new
  template no longer writes. It stays for the implemented RFCs that carry the heading;
  `## Decisions` is covered by `rfc-structure/missing-section` instead.
- **`change transition`** writes `## Resolution` as today; it lands after `## Tasks`, which is
  where the agent's part ends and the record of the decision begins.
- **Docs**: `docs/guides/style-guide.md` gains the owner's-part rules; `docs/guides/agent-protocol.md`
  step 2 and its scaffold `init/scaffolds/docs/guides/agent-protocol.md.j2` name the layout;
  `docs/components/new-list-regen.md` and `docs/components/checks.md` name the new check.
- **Migration of drafts** (decision 1): `claim-evidence-names-a-part` and
  `every-warning-hint-has-an-answer` are rewritten into the layout while still drafts, their
  Requirements and Tasks unchanged, and only then accepted.
- **Migration of implemented RFCs** (decision 2): `acknowledge-a-reviewed-co-change-or-evidence-drift`
  and `a-gate-file-is-sealed-not-scored` are rewritten into the layout in the tree of a second
  history reset, after `rfc-structure` exists, so the check judges them before the reset
  commit is made. Their Requirements, Tasks, `## Resolution` and frontmatter stay byte for
  byte; only the prose around them moves into the owner's sections and `## Design detail`.
  With no base, no seal applies to that commit.

## Requirements

### Requirement: New RFCs are written in two parts
ID: new-rfcs-are-written-in-two-parts
Provenance: code

`irminsul new rfc` SHALL write the owner's sections Summary, Problem, How it works, Cost and
risk and Decisions, in that order, above `## Design detail`, followed by `## Requirements`
and `## Tasks`.

#### Scenario: A new RFC
- **WHEN** `irminsul new rfc "Export rows"` runs
- **THEN** its frontmatter says `weight: large`, and its H2 headings are, in order, Summary,
  Problem, How it works, Cost and risk, Decisions, Design detail, Requirements and Tasks

#### Scenario: A new small RFC
- **WHEN** `irminsul new rfc --small "Exit 1 on an existing baseline"` runs
- **THEN** its frontmatter says `weight: small`, and its H2 headings are, in order, Summary,
  Decisions, Design detail, Requirements and Tasks

### Requirement: An RFC declares its weight
ID: an-rfc-declares-its-weight
Provenance: code

`rfc-structure` SHALL report `rfc-structure/missing-weight` for an RFC whose `rfc_state` is
`draft` or `accepted` and whose frontmatter has no `weight`, or one other than `small` or
`large`.

#### Scenario: No weight
- **WHEN** a draft RFC's frontmatter has no `weight`
- **THEN** the run reports `rfc-structure/missing-weight` for it

### Requirement: An owner's section is required
ID: an-owners-section-is-required
Provenance: code

`rfc-structure` SHALL report `rfc-structure/missing-section` for each owner's section the
RFC's weight requires (Summary and Decisions for `small`; Summary, Problem, How it works, Cost
and risk and Decisions for `large`) that is absent, or empty apart from HTML comments and
placeholder lines, in an RFC whose `rfc_state` is `draft` or `accepted`.

#### Scenario: A small RFC without a Problem
- **WHEN** a draft RFC with `weight: small` has Summary and Decisions and no `## Problem`
- **THEN** `rfc-structure` reports no `rfc-structure/missing-section` for it

#### Scenario: Decisions left empty
- **WHEN** an accepted RFC's `## Decisions` holds only the template's comment
- **THEN** the run reports `rfc-structure/missing-section` naming Decisions

#### Scenario: An implemented RFC in the old layout
- **WHEN** an RFC whose `rfc_state` is `implemented` has no `## Problem`
- **THEN** `rfc-structure` reports nothing for it

### Requirement: The owner's part comes first
ID: the-owners-part-comes-first
Provenance: code

`rfc-structure` SHALL report `rfc-structure/section-out-of-order` for an owner's section
heading below `## Design detail`, and for an RFC that has `## Requirements` but no
`## Design detail`.

#### Scenario: Cost and risk moved down
- **WHEN** a draft RFC's `## Cost and risk` follows `## Design detail`
- **THEN** the run reports `rfc-structure/section-out-of-order` naming Cost and risk

### Requirement: A dense owner's paragraph is a hint
ID: a-dense-owners-paragraph-is-a-hint
Provenance: code

`rfc-structure` SHALL report `rfc-structure/dense-paragraph`, a hint, for a paragraph of the
owner's part that holds four or more code spans, and SHALL NOT report one in the agent's
part.

#### Scenario: A list of claims in How it works
- **WHEN** a paragraph under `## How it works` names five claim ids in code spans
- **THEN** the run reports `rfc-structure/dense-paragraph` on that paragraph's line

#### Scenario: The same list in Design detail
- **WHEN** that paragraph is moved under `## Design detail`
- **THEN** the run reports no `rfc-structure/dense-paragraph`

## Tasks

- `T1` Move the per-slug section reader out of `checks/adr_structure.py` into one helper both
  checks call, with `adr-structure` behaving as before. (component: checks)
- `T2` Rewrite the RFC template in the two-part layout, with `--small` writing the small shape,
  and add `weight` to the frontmatter schema. (req: new-rfcs-are-written-in-two-parts,
  req: an-rfc-declares-its-weight)
- `T3` Add `rfc-structure` with its missing-section and out-of-order codes, a fixture and
  tests, and enable it here and in the scaffold config. (req: an-owners-section-is-required,
  req: the-owners-part-comes-first)
- `T4` Add the dense-paragraph hint and its tests. (req: a-dense-owners-paragraph-is-a-hint)
- `T5` State the owner's-part rules in the style guide, the layout in the agent protocol and
  its scaffold, and the check in the components that describe it. (component: new-list-regen)
- `T6` Rewrite `claim-evidence-names-a-part` and `every-warning-hint-has-an-answer` in the
  layout, Requirements and Tasks unchanged, before they are accepted. (component: checks)
- `T7` At the second history reset, rewrite the two implemented RFCs in the layout, with their
  Requirements, Tasks, Resolution and frontmatter unchanged. (component: checks)

## Resolution

Accepted by the owner on 2026-10-28, with the answers recorded under Decisions, and resolved by
[RFCs have four states, and git history seals decided records](../decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md).
