---
id: adoption-and-repository-layouts
title: Adoption and repository layouts
status: stable
describes: []
summary: "irminsul init adopts existing code or starts fresh in one of two layouts, same-repo or siblings, and irminsul seed captures initial intent into the foundation layer."
---

# Adoption and repository layouts

## Status

Accepted, 2026-09-12.

## Context

Adoption has to work for an existing codebase, for a project that has no code yet, and
for open-source projects that keep their docs private. Each extra layout multiplied the
paths through `init`, CI, and every diff-aware command.

## Decision

- **One command.** `irminsul init` detects languages and source roots in existing code;
  `--fresh` creates docs, config, CI, and an empty source root without starter code.
  Languages come from detection or repeated `--language`. The scaffold is born passing
  its own configured checks.
- **Two layouts.** `same-repo` puts `docs/` inside the code repository and is the
  default. `siblings` puts a docs repository beside a separate code repository under one
  parent, with `source_roots` reaching through `../` and two-checkout CI; it is chosen
  with `--topology siblings --code-repo <spec>`. No nested layout is supported, and
  `--fresh` does not combine with `siblings`.
- **`--delta` refuses what it cannot answer,** including any configured tree in another
  repository, rather than reporting every finding there as new.
- **Seed captures intent.** `irminsul seed` records the principle, idea, and belief plus
  first user, non-goals, and risks into the foundation docs and an anchoring ADR and RFC;
  it never invents missing input, and `foundation-readiness` warns while scaffold
  placeholders remain.

## Alternatives Considered

- **A separate `new project` command.** Rejected: `new` creates doc atoms in an
  initialized repository.
- **Nested private-docs layouts** — a private docs repository nested inside the code
  repository, or the code cloned into the docs repository. Rejected: each needs special
  cases in ignore handling, CI, and `--delta`, while `siblings` covers the same need.
- **Seed prompts in non-interactive init.** Rejected: non-interactive runs must stay
  scriptable; only the interactive paths that scaffold a new project offer seed.

## Consequences

- Every supported repository is one of two shapes, so diff-aware features can reason
  about them.
