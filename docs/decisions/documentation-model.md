---
id: documentation-model
title: Documentation model
status: stable
describes: []
summary: Six configurable layers of single-purpose doc atoms with validated frontmatter, folder-owned navigation, per-layer rules, structured ADRs, and an opt-in glossary.
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
    guidance: Remove `tier`; set `require_tests`, `require_scope_section`, and `forbid_speculation` on the layer instead.
---

# Documentation model

## Status

Accepted, 2026-09-12.

## Context

Irminsul enforces a documentation system, and this repository is governed by the same
system it ships. The system has to be shaped so that a checker can decide structural
questions — who owns a source file, whether a link resolves, whether a record is
complete — without reading prose for meaning.

## Decision

- **One tree, six layers.** Docs live under `docs_root` in the `foundation`,
  `architecture`, `components`, `decisions`, `rfcs`, and `guides` layers, each a folder
  named in `[layers]`, so a project can rename one. Doc ids are global bare slugs. This
  repository runs its own checks in CI, and a certain finding blocks merge.
- **Doc atoms.** Every doc except the top-level navigation files carries validated
  frontmatter: `id`, `title`, and `status`, plus optional ownership,
  relationship, claim, inventory, and lifecycle fields. Projects may add their own keys.
- **Folders own their docs.** A folder's index doc owns every sibling in its folder; there is no
  `children:` registry, and a parent INDEX never describes source with wildcards.
- **Layers carry the rules.** Each layer's config decides whether its docs must list
  tests, state their scope and limitations, and avoid speculative language; components
  do by default. Derivable facts are derived on demand, and non-derivable reference sits
  with its owner.
- **ADRs have a fixed shape.** Status, Context, Decision, Alternatives Considered, and
  Consequences; `adr-structure` reports a missing or empty section. The body Status is a
  human summary, never lifecycle evidence.
- **The glossary is opt-in per term.** A glossary heading may declare `match` strings,
  `forbidden_synonyms`, and `case_sensitive`; `glossary-discipline` warns on forbidden
  synonyms, unused declared terms, and redefinitions, and suggests linking a term's
  first use.

## Alternatives Considered

- **Free-form docs with conventions in a style guide.** Rejected: conventions a checker
  cannot see are the ones that rot first.
- **An explicit `children:` list on each INDEX.** Rejected: folder membership already
  states ownership, and the list drifted from the folder.
- **A committed layer of generated reference.** Rejected: committed derivations go stale;
  see [Derive, don't materialize](derive-dont-materialize.md).
- **A per-doc maintenance tier in frontmatter.** Rejected: the tier follows the folder in
  practice, so declaring it on every doc adds a field that can only disagree with the
  layer.
- **Separate layers for workflows, operations, knowledge, and meta.** Rejected: no check
  treats them differently, cross-component flows are architecture, and how-tos of every
  kind read the same way.
- **Numbered layer folders.** Rejected: ids are global, so the numbers namespace nothing,
  and they only fix a sort order.
- **Infer glossary matches, plurals, and aliases.** Rejected: explicit match strings keep
  the rule deterministic and reviewable.

## Consequences

- Structural questions have mechanical answers, so most doc rot surfaces as a finding
  rather than as a reader's surprise.
- Authors pay a small frontmatter cost on every doc.
