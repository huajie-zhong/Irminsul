---
id: docs-are-atoms-in-six-layers-and-code-has-one-owner
title: "Docs are atoms in six layers, and code has one owner"
status: stable
describes: []
summary: Docs are frontmatter-validated atoms in six configurable layers, each stating its own one-liner, folders own their docs, retired fields are errors, and every source file in documented territory has exactly one owning doc.
governs:
  - src/irminsul/frontmatter.py
  - "!src/irminsul/frontmatter.py#Claim"
  - "!src/irminsul/frontmatter.py#ClaimRelationEnum"
  - "!src/irminsul/frontmatter.py#ClaimStateEnum"
  - "!src/irminsul/frontmatter.py#RfcStateEnum"
  - "!src/irminsul/frontmatter.py#RetirementEntry"
  - src/irminsul/checks/frontmatter.py
  - src/irminsul/checks/uniqueness.py
  - src/irminsul/checks/orphans.py
  - src/irminsul/checks/supersession.py
  - src/irminsul/checks/parent_child.py
  - src/irminsul/checks/glossary.py
  - src/irminsul/checks/coverage.py
  - src/irminsul/checks/boundary.py
  - src/irminsul/adoption.py
  - src/irminsul/source_map.py
  - src/irminsul/ownership_moves.py
  - src/irminsul/checks/adoption_record.py
  - src/irminsul/checks/diff_integrity.py#_owner_changes
  - src/irminsul/checks/diff_integrity.py#_adoption_seal
  - src/irminsul/new/command.py#current_owners
  - src/irminsul/new/command.py#split_links
  - src/irminsul/listing/review.py#_moved_file_sentences
  - layers
  - paths.docs_root
  - paths.adoption
retires:
  - id: numbered-layer-folders
    kind: concept
    matches:
      - 00-foundation
      - 10-architecture
      - 20-components
      - 30-workflows
      - 50-decisions
      - 60-operations
      - 70-knowledge
      - 80-evolution
      - 90-meta
    guidance: Use the six configured layers — foundation, architecture, components, decisions, rfcs, and guides — named under `[layers]` in irminsul.toml.
  - id: tier-frontmatter-field
    kind: concept
    matches:
      - "tier: 2"
      - "tier: 3"
      - "tier: 4"
      - tier-3
    guidance: Remove `tier`; set `require_tests` and `require_scope_section` on the layer instead.
  - id: unlisted-sibling
    kind: concept
    matches:
      - unlisted-sibling
    guidance: An INDEX need not link every doc beside it; `docs/AGENTS.md` lists every doc with its `summary:`.
  - id: superseded-by-field
    kind: concept
    matches:
      - superseded_by
      - missing-superseded-by
      - unknown-superseded-by
      - missing-supersedes
    guidance: Declare `supersedes` on the newer doc and deprecate the older one; the inverse is derived.
  - id: requires-env
    kind: concept
    matches:
      - requires_env
      - requires-env
    guidance: Declare an `inventory:` entry of kind `env-vars`, which `inventory-drift` checks against the code.
  - id: inventory-fingerprints
    kind: concept
    matches:
      - unfingerprintable
      - fingerprint-unresolved
      - fingerprint-drift
    guidance: Bind the symbol with an anchor, which pins its normalized shape; `irminsul anchors --suggest` names the file.
---

# Docs are atoms in six layers, and code has one owner

## Status

Accepted, 2026-10-28.

## Context

Irminsul enforces a documentation system, and this repository is governed by the one it ships.
A checker has to decide structural questions, such as who owns a source file, whether a link
resolves, or whether a record is complete, without reading prose for meaning. Each structural
fact needs one home: a one-liner kept both in a folder index and in the doc drifts, and so does
a field that restates another. And if an unclaimed source file were only a hint, the cheapest
way to add undocumented code would be to add it, or to narrow a `describes` glob.

## Decision

- **One tree, six layers.** Docs live under `paths.docs_root` in the `foundation`,
  `architecture`, `components`, `decisions`, `rfcs` and `guides` layers, each a folder a project
  may rename under `[layers]`. Doc ids are global bare slugs.
- **[Doc atoms](../GLOSSARY.md#doc-atom) carry validated frontmatter.** Every doc but the
  top-level navigation files carries `id`, `title`, `status` and a one-sentence `summary:`, plus
  optional ownership, relationship, claim, inventory and lifecycle fields; any other key, a
  project's own or a leftover such as `audience`, is allowed and read by nothing. A missing `summary:` is `frontmatter/missing-summary`, certain and excused on a draft,
  and the doc still loads; an implemented RFC, being sealed, is passed over. A near miss of a
  canonical field is `frontmatter/misspelled-field`. A key Irminsul no longer reads is
  `frontmatter/retired-field`, naming its replacement: `tests` (`recommended_tests`),
  `superseded_by` (delete it), `requires_env` (an `env-vars` inventory entry) and an inventory
  entry's `fingerprints` (an anchor). Both are certain.
- **Folders own their docs.** A folder's index doc owns every doc beside it, so there is no
  `children:` list, an INDEX need not list its folder, and `orphans` counts a doc beside an
  INDEX as owned. The generated agent manifest is the complete list. A parent INDEX keeping a
  wildcard `describes` beside child docs is `parent-child/wildcard-with-children`, a hint.
- **Replacement is declared once:** the newer doc lists the older in `supersedes`, the older is
  `status: deprecated`, and `supersession` reports either half wrong.
- **Layers carry the rules.** A layer's `require_tests` and `require_scope_section` decide
  whether its docs list tests and state their scope and limitations; components do both by
  default. A decision record is a doc in the decisions layer other than its INDEX; no `audience`
  field labels a doc, and writing for one reader is a rule of the contributing guide and the
  principles.
- **The glossary is opt-in per term:** a heading may declare `match`, `forbidden_synonyms` and
  `case_sensitive`, and `glossary-discipline` reports a forbidden synonym as certain and an
  unused term or unlinked first use as hints.
- **Every source file has one owner.** Two docs claiming a file at the same specificity is
  `uniqueness/duplicate-claim`; otherwise the most specific claim wins. A source file in
  documented territory that no doc claims is `uniqueness/undocumented-file`, certain. Territory
  is a directory that holds claimed code, or one added inside such a directory, so an
  undocumented sibling tree can be adopted later while a new subdirectory of documented code
  inherits the obligation. The finding names `irminsul context <path>` for the nearest owner.
  Under an adoption record, every managed file it does not name is reportable, apart from the
  skip list and files governed as tests.
- **Splitting a doc keeps one description of the code.** `irminsul new component` refuses a
  `--describes` matching a file another doc owns unless each owner is named with
  `--split-from <doc-id>`; the new doc opens with a `Split from` link, and the command prints
  which files to remove from the owner. Under a diff, a file moved to another owner is
  `diff-integrity/owner-changed`, a hint, and `list review --changed` queues the old owner's
  sentences about it. A narrower claim on files a broader claim elsewhere matches, with neither
  doc linking the other, is `uniqueness/unlinked-overlap`, a hint.
- **One claim per source file** (accepted, not yet implemented). A source file that two or more
  docs' `describes:` match is `uniqueness/duplicate-claim`, certain whatever the specificity,
  naming every doc and pattern, and is answered by narrowing the broader claim; a `describes:`
  entry that starts with `!` removes files from its own doc's claim, as a negated gitignore
  pattern. Every reader that asks who owns a file gets every claimant, the specificity ranking
  goes, and `uniqueness/unlinked-overlap` and `parent-child/wildcard-with-children` are retired.
  This replaces "otherwise the most specific claim wins" above.
- **One record governs each item** (accepted, not yet implemented). A file, a part of a file or
  a setting that two stable decision records' `governs:` cover is
  `uniqueness/duplicate-governance`, certain, through the same matcher and `!` exclusions as one
  claim per source file.
- **Three findings gain an answer** (accepted, not yet implemented). `owner-changed` is reported
  only while the old owner's prose still names the moved file, read by the review queue's
  sentence reader, and a trailer answers it; a trailer naming the adoption record answers
  `adoption-record-removed`; and `glossary-discipline/unlinked-term` reads the body its fixer
  links, so every use it reports can be linked.

## Alternatives Considered

- **Free-form docs with conventions in a style guide.** Rejected: conventions a checker cannot
  see rot first.
- **A `children:` list or a generated INDEX list.** Rejected: the folder already states
  ownership, and the manifest already lists it.
- **A per-doc tier or an `audience` label.** Rejected: the tier follows the folder, and a label
  nothing reads cannot be kept honest.
- **More layers, or numbered folders.** Rejected: no check treats workflows, operations or meta
  differently, and global ids leave numbers nothing to namespace.
- **Inferred glossary matches and plurals.** Rejected: explicit strings stay deterministic.
- **A schema-required `summary`.** Rejected: a doc failing validation drops out of the graph.
- **Ignore retired keys, or reject every unknown key.** Rejected: a dead key reads as working,
  and projects add keys of their own.
- **An unclaimed file as a hint.** Rejected: the workflows `init` writes fail on certain findings
  only, and day-one debt has the adoption record and the baseline.
- **Every directory under a root as territory, or a claim per public symbol.** Rejected: one
  claimed file would claim the root, and per-symbol is a far larger obligation than this floor.
- **A moved owner as certain, or comparing two docs' prose.** Rejected: moving files between
  docs is a normal refactor, and sameness of meaning is a reader's call.

## Consequences

- Most doc rot surfaces as a finding, for a small frontmatter cost on every doc; a new doc is
  one edit.
- `tests` and `fingerprints` have no tombstone, because both are ordinary words;
  `frontmatter/retired-field` is their only guard.
- Adding a directory of code means saying, in the same change, which doc describes it, and
  `list undocumented` selects the finding by its code.
- An overlap made by editing frontmatter by hand, not through `new`, is caught only by the two
  hints.

## Changes

- 2026-10-29: Accepted [A source file has one claim](../rfcs/a-source-file-has-one-claim.md).
- 2026-10-29: Accepted [Decision records govern what they decide](../rfcs/decision-records-govern-what-they-decide.md):
  one record governs each item.
- 2026-10-29: Accepted [Each finding code has one answer](../rfcs/every-warning-hint-has-an-answer.md):
  `owner-changed`, a removed adoption record and an unlinked glossary term gain an answer.
