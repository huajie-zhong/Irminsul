---
id: init-adopts-in-two-layouts-and-seed-fills-two-docs
title: "Init adopts in two layouts, and seed fills two docs"
status: stable
describes: []
summary: "`irminsul init` adopts existing code or starts fresh in one of two layouts, same-repo or siblings, and `irminsul seed` fills only the principles doc and the architecture overview with the project's starting intent."
governs:
  - src/irminsul/init/**
  - "!src/irminsul/init/workflows/**"
  - "!src/irminsul/init/scaffolds/AGENTS.md.j2"
  - "!src/irminsul/init/command.py#_ACTION_REPOSITORY"
  - "!src/irminsul/init/command.py#action_ref"
  - "!src/irminsul/init/command.py#_ROOT_ROUTER_PATH"
  - "!src/irminsul/init/command.py#_MCP_CONFIG_PATH"
  - "!src/irminsul/init/command.py#_SKILL_PATH"
  - "!src/irminsul/init/command.py#_CLAUDE_POINTER_PATH"
  - "!src/irminsul/init/command.py#_MCP_MANUAL_COMMAND"
  - "!src/irminsul/init/command.py#_SKILL_BODY"
  - "!src/irminsul/init/command.py#_ROUTER_IMPORT"
  - "!src/irminsul/init/command.py#_CLAUDE_POINTER_BODY"
  - "!src/irminsul/init/command.py#agents_block_span"
  - "!src/irminsul/init/command.py#_read_root_router"
  - "!src/irminsul/init/command.py#_merge_root_router"
  - "!src/irminsul/init/command.py#generate_agents_manifest"
  - "!src/irminsul/init/command.py#HarnessWiring"
  - "!src/irminsul/init/command.py#_load_mcp_config"
  - "!src/irminsul/init/command.py#_registers_irminsul"
  - "!src/irminsul/init/command.py#_link_pointer"
  - "!src/irminsul/init/command.py#write_harness_files"
  - "!src/irminsul/init/command.py#_scaffold_with_agent_wiring"
  - "!src/irminsul/init/command.py#_harness_next_step"
  - "!src/irminsul/init/command.py#check_mcp_launcher"
  - "!src/irminsul/init/command.py#print_mcp_warning"
  - src/irminsul/seed/**
  - src/irminsul/cli.py#init
  - src/irminsul/cli.py#_init_siblings
  - src/irminsul/cli.py#_offer_seed_after_scaffold
  - src/irminsul/cli.py#seed
retires:
  - id: seed-json-flag
    kind: concept
    matches:
      - seed --json
    guidance: Pass the answers as flags with `irminsul seed --no-interactive`.
---

# Init adopts in two layouts, and seed fills two docs

## Status

Accepted, 2026-10-28.

## Context

Adoption has to work for an existing codebase, for a project with no code yet, and for
open-source projects that keep their docs private. Each extra layout multiplies the paths
through `init`, CI and every diff-aware command. A project's starting intent written into
several records has several homes that later edits pull apart.

## Decision

- **One command adopts.** `irminsul init` detects languages and source roots in existing code.
  `--fresh` creates docs, config, CI and an empty source root without starter code, refusing
  where code exists unless `--allow-existing-code` is given. Languages come from detection or a
  repeated `--language`. The scaffold passes its own configured checks. `--force` overwrites
  scaffold files, first copying one git cannot restore to `<name>.irminsul-backup`.
- **Two layouts.** `same-repo` puts `docs/` inside the code repository and is the default, for
  the reasons [private docs](../guides/private-docs.md) gives. `siblings` puts a docs repository
  beside a code repository under one parent, with `source_roots` reaching through `../` and
  workflows that check out both, chosen with `--topology siblings --code-repo <spec>`. No nested
  layout is supported, and `--fresh` does not combine with `siblings`.
- **Seed fills the principles doc and the architecture overview, and nothing else.**
  `irminsul seed` renders each from the scaffold `init` writes, replacing only the text its
  `<!-- irminsul:placeholder -->` markers cover with the principle, idea, belief, first user,
  non-goals and risks, and never invents missing input. It refuses a doc edited away from its
  scaffold unless `--reseed` or `--merge` says what to do. A decision or proposal about the
  direction is the author's, with `irminsul new adr` or `irminsul new rfc`.
- **Input is the prompts, or the flags with `--no-interactive`.** Only the interactive paths
  that scaffold a new project offer seed.

## Alternatives Considered

- **A `new project` command.** Rejected: `new` creates doc atoms in an initialized repository.
- **Nested private-docs layouts.** Rejected: each needs special cases in ignore handling, CI and
  `--delta`, and `siblings` covers the need.
- **Seed prompts in non-interactive init.** Rejected: it must stay scriptable.
- **Seed also writing a decision record and an initial-direction RFC.** Rejected: each restated
  the principles doc, and nothing compared later work against the RFC.
- **A `--json` input for seed.** Rejected: the flags already script it.

## Consequences

- Every supported repository is one of two shapes, so diff-aware features can reason about them.
- Changing a scaffold's prompts changes what `init` and `seed` write alike.
