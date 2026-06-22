# Agent Navigation Manifest

This manifest is the curated entry point into `docs/` for agents. The
documentation-tree table below is generated; the Foundations and Protocol
sections are curated. Run `irminsul regen agents-md` after adding or
moving docs.

New and updated docs should set a one-line `summary:` in their frontmatter
so they describe themselves in the table below; the Summary column appears
automatically once any doc declares one.

## About this manifest

- **Don't hand-edit between the markers.** Anything between
  `agents-manifest:generated-start` and `agents-manifest:generated-end` is
  rewritten by `irminsul regen agents-md`. Edits to the intro, this section,
  Foundations, and Protocol are curated and survive regens.
- **How to read the table.** Rows are grouped by docs-tree layer. Docs that
  live directly under `docs/` (a project-wide INDEX, this manifest itself)
  appear under `(root)`. Exempt navigation files — `README.md`, `GLOSSARY.md`,
  `CONTRIBUTING.md`, and `AGENTS.md` itself — are intentionally not listed;
  they aren't doc atoms.
- **The Foundations and Protocol sections are yours.** They scaffold with
  Irminsul's default doc-system framing, but downstream projects are meant to
  edit them to their own taste; `irminsul regen agents-md` preserves the
  edits.

## Documentation Tree

<!-- agents-manifest:generated-start -->

### 00-foundation

| ID | Doc | Audience | Tier | Summary |
|----|-----|----------|------|---------|
| `00-foundation` | [Foundation](00-foundation/INDEX.md) | reference | 2 |  |
| `anti-patterns` | [Anti-Patterns](00-foundation/anti-patterns.md) | explanation | 2 |  |
| `enforcement` | [Mechanical Enforcement](00-foundation/enforcement.md) | explanation | 2 |  |
| `laws` | [The Three Laws of Maintenance](00-foundation/laws.md) | explanation | 2 |  |
| `principles` | [Principles](00-foundation/principles.md) | explanation | 2 |  |

### 10-architecture

| ID | Doc | Audience | Tier | Summary |
|----|-----|----------|------|---------|
| `10-architecture` | [Architecture](10-architecture/INDEX.md) | reference | 2 |  |
| `component-hierarchy` | [Component Hierarchy and Doctrine](10-architecture/component-hierarchy.md) | explanation | 2 |  |
| `layers` | [The Layered Directory Structure](10-architecture/layers.md) | explanation | 2 |  |
| `levels-and-views` | [Architecture Levels and Views](10-architecture/levels-and-views.md) | explanation | 2 |  |
| `overview` | [Architecture overview](10-architecture/overview.md) | explanation | 2 |  |
| `tiers` | [The Tier System](10-architecture/tiers.md) | explanation | 2 |  |
| `tooling` | [Tooling Stack and Deployment](10-architecture/tooling.md) | explanation | 2 |  |

### 20-components

| ID | Doc | Audience | Tier | Summary |
|----|-----|----------|------|---------|
| `20-components` | [Components](20-components/INDEX.md) | reference | 3 |  |
| `anchors` | [Anchored prose claims](20-components/anchors.md) | explanation | 3 |  |
| `baseline` | [Baseline ratchet](20-components/baseline.md) | explanation | 3 | Brownfield adoption mechanism — a baseline file grandfathers existing findings so CI fails only on new ones, and only ever shrinks. |
| `checks` | [Checks](20-components/checks.md) | explanation | 3 |  |
| `cli` | [CLI](20-components/cli.md) | explanation | 3 |  |
| `config` | [Config](20-components/config.md) | reference | 3 |  |
| `context` | [Agent context command](20-components/context.md) | explanation | 3 |  |
| `doc-atom` | [The Doc Atom Specification](20-components/doc-atom.md) | reference | 2 |  |
| `docgraph` | [DocGraph](20-components/docgraph.md) | explanation | 3 |  |
| `frontmatter` | [Frontmatter](20-components/frontmatter.md) | explanation | 3 |  |
| `init` | [Init scaffolder](20-components/init.md) | explanation | 3 |  |
| `languages` | [Language profiles](20-components/languages.md) | reference | 3 |  |
| `llm` | [LLM Client](20-components/llm.md) | explanation | 3 |  |
| `mcp-server` | [MCP server](20-components/mcp-server.md) | explanation | 3 | Read-only MCP stdio server that lets AI agents query the doc graph natively instead of shelling out to the CLI. |
| `new-list-regen` | [New / List / Regen / Fix commands](20-components/new-list-regen.md) | explanation | 3 |  |
| `orient` | [Agent orientation command](20-components/orient.md) | explanation | 3 | The recommended first call for agents — repo structure, doc totals, entry docs, and the command vocabulary as one stable report. |
| `refs` | [Refs backlink and symbol query](20-components/refs.md) | explanation | 3 |  |
| `seed` | [Seed command](20-components/seed.md) | explanation | 3 |  |
| `status` | [Status command](20-components/status.md) | explanation | 3 | One-glance digest of docs inventory, source-file coverage, and findings. |
| `surface` | [Surface extraction & on-demand derivation](20-components/surface.md) | explanation | 3 |  |

### 30-workflows

| ID | Doc | Audience | Tier | Summary |
|----|-----|----------|------|---------|
| `30-workflows` | [Workflows](30-workflows/INDEX.md) | explanation | 3 |  |
| `check-pipeline` | [Check Pipeline](30-workflows/check-pipeline.md) | explanation | 3 |  |

### 50-decisions

| ID | Doc | Audience | Tier | Summary |
|----|-----|----------|------|---------|
| `0001-adopt-irminsul` | [ADR-0001: Adopt the Irminsul doc system on Irminsul itself](50-decisions/0001-adopt-irminsul.md) | adr | 2 |  |
| `0002-support-fresh-start-init` | [Support fresh-start init](50-decisions/0002-support-fresh-start-init.md) | adr | 2 |  |
| `0003-generated-code-reference-surfaces` | [ADR-0003: Generate code-derived reference surfaces](50-decisions/0003-generated-code-reference-surfaces.md) | adr | 2 | Adopt generated reference docs for code-derived surfaces; verify them in CI. |
| `0004-agents-manifest` | [ADR-0004: Add the agent navigation manifest](50-decisions/0004-agents-manifest.md) | adr | 2 | Add an agent navigation manifest plus an opt-in hard check and a regen target. |
| `0005-backlinks-and-refs` | [ADR-0005: Add the refs backlink and symbol-reference query](50-decisions/0005-backlinks-and-refs.md) | adr | 2 | Add `irminsul refs` as a CLI surface over the strong and weak inbound indexes plus claim and describes provenance. |
| `0006-implement-rfc-0015-pib-seed-and-foundation-readiness` | [ADR-0006: Implement RFC-0015 PIB seed and foundation readiness](50-decisions/0006-implement-rfc-0015-pib-seed-and-foundation-readiness.md) | adr | 2 | Add `irminsul seed` and the `foundation-readiness` check, with an opt-in seed prompt on interactive fresh-start init. |
| `0007-implement-rfc-0016-agent-lifecycle-protocol` | [ADR-0007: Implement RFC-0016 agent lifecycle protocol](50-decisions/0007-implement-rfc-0016-agent-lifecycle-protocol.md) | adr | 2 | Add the canonical agent lifecycle protocol document and ship it via the init scaffold. |
| `0008-implement-rfc-0017-rfc-resolution-check` | [ADR-0008: Implement RFC-0017 RFC resolution check](50-decisions/0008-implement-rfc-0017-rfc-resolution-check.md) | adr | 2 | Add the `rfc-resolution` soft deterministic check and a `--now` override so the RFC lifecycle is machine-enforced end to end. |
| `0009-implement-rfc-0018-decision-followups-and-maintenance-queue` | [ADR-0009: Implement RFC-0018 decision updates and maintenance queue](50-decisions/0009-implement-rfc-0018-decision-followups-and-maintenance-queue.md) | adr | 2 | Add `required_updates` and `implements` frontmatter fields, a `decision-updates` soft check, and `irminsul list lifecycle [--queue]` to surface unfinished decision work. |
| `0010-implement-rfc-0019-glossary-discipline` | [ADR-0010: Implement RFC-0019 glossary discipline](50-decisions/0010-implement-rfc-0019-glossary-discipline.md) | adr | 2 | Rename the glossary check to `glossary-discipline` and enforce explicit glossary metadata for term usage, forbidden synonyms, and glossary links. |
| `0011-derive-dont-materialize` | [ADR-0011: Derive, don't materialize](50-decisions/0011-derive-dont-materialize.md) | adr | 2 | Retire committed code-derived reference surfaces; derive on demand and govern the non-derivable. |
| `0012-anchored-prose-claims` | [ADR-0012: Anchored prose claims](50-decisions/0012-anchored-prose-claims.md) | adr | 2 | Pin intent paragraphs to code symbols with a content hash; flag drift deterministically. |
| `0013-retire-render-subsystem` | [ADR-0013: Retire the render and reference-stub subsystem](50-decisions/0013-retire-render-subsystem.md) | adr | 2 | Remove the MkDocs renderer and the regen python/typescript stubs; keep check + derive + agent manifest. |
| `0014-retire-tier-1-and-reference-layer` | [ADR-0014: Retire Tier 1 and the reference layer](50-decisions/0014-retire-tier-1-and-reference-layer.md) | adr | 2 | Remove the Tier 1 ("Generated") tier and the 40-reference layer; non-derivable reference lives in its owning layer, derivable surfaces stay on-demand. |
| `0015-govern-mcp-tool-surface` | [ADR-0015: Govern the MCP tool surface as a watched surface](50-decisions/0015-govern-mcp-tool-surface.md) | adr | 2 | Govern the MCP tool set with a dedicated `mcp` extractor and a watched `inventory:` block in mcp-server.md (internal consistency), rather than a generic-regex rule or a two-surface CLI-parity check. |
| `50-decisions` | [Architecture decisions](50-decisions/INDEX.md) | reference | 2 |  |

### 60-operations

| ID | Doc | Audience | Tier | Summary |
|----|-----|----------|------|---------|
| `60-operations` | [Operations](60-operations/INDEX.md) | reference | 3 |  |
| `release` | [Release Process](60-operations/release.md) | reference | 3 |  |

### 70-knowledge

| ID | Doc | Audience | Tier | Summary |
|----|-----|----------|------|---------|
| `70-knowledge` | [Knowledge](70-knowledge/INDEX.md) | reference | 3 |  |
| `bootstrap` | [Bootstrapping Checklist](70-knowledge/bootstrap.md) | tutorial | 3 |  |

### 80-evolution

| ID | Doc | Audience | Tier | Summary |
|----|-----|----------|------|---------|
| `0001-topology-b-and-format-json` | [RFC-0001: Topology B (sibling code repos) and structured check output](80-evolution/rfcs/0001-topology-b-and-format-json.md) | explanation | 2 |  |
| `0002-fix-and-regen-typescript` | [RFC-0002: irminsul fix (auto-remediation) and TypeScript reference regen](80-evolution/rfcs/0002-fix-and-regen-typescript.md) | explanation | 2 |  |
| `0003-vscode-extension` | [RFC-0003: VS Code extension (Phase 3)](80-evolution/rfcs/0003-vscode-extension.md) | explanation | 2 |  |
| `0004-remove-children-field` | [RFC-0004: Remove children: field — INDEX auto-owns all folder siblings](80-evolution/rfcs/0004-remove-children-field.md) | explanation | 2 |  |
| `0005-systemic-doc-enforcement` | [Systemic Doc Enforcement (Reality, Coverage, Boundary, Liar)](80-evolution/rfcs/0005-systemic-doc-enforcement.md) | reference | 4 |  |
| `0006-structural-accountability-and-external-state` | [Structural Accountability & External State Verification](80-evolution/rfcs/0006-structural-accountability-and-external-state.md) | reference | 4 |  |
| `0007-fresh-start-init` | [Fresh-start init](80-evolution/rfcs/0007-fresh-start-init.md) | explanation | 2 |  |
| `0008-check-profiles-and-warning-policy` | [Check profiles and warning policy](80-evolution/rfcs/0008-check-profiles-and-warning-policy.md) | explanation | 2 |  |
| `0009-deterministic-doc-reality-audits` | [Deterministic doc reality audits](80-evolution/rfcs/0009-deterministic-doc-reality-audits.md) | explanation | 2 |  |
| `0010-structured-claim-provenance` | [Structured claim provenance](80-evolution/rfcs/0010-structured-claim-provenance.md) | explanation | 2 |  |
| `0011-agent-context-command` | [RFC-0011: Agent context command](80-evolution/rfcs/0011-agent-context-command.md) | explanation | 2 |  |
| `0012-generated-code-reference-surfaces` | [Generated code reference surfaces](80-evolution/rfcs/0012-generated-code-reference-surfaces.md) | explanation | 2 |  |
| `0013-agents-manifest` | [RFC-0013: AGENTS.md agent navigation manifest](80-evolution/rfcs/0013-agents-manifest.md) | explanation | 2 |  |
| `0014-backlinks-and-refs` | [RFC-0014: Backlinks and symbol-reference query](80-evolution/rfcs/0014-backlinks-and-refs.md) | explanation | 2 |  |
| `0015-pib-seed-and-foundation-readiness` | [PIB seed and foundation readiness](80-evolution/rfcs/0015-pib-seed-and-foundation-readiness.md) | explanation | 2 |  |
| `0016-agent-lifecycle-protocol` | [Agent lifecycle protocol](80-evolution/rfcs/0016-agent-lifecycle-protocol.md) | explanation | 2 |  |
| `0017-rfc-resolution-check` | [RFC resolution check](80-evolution/rfcs/0017-rfc-resolution-check.md) | explanation | 2 |  |
| `0018-decision-followups-and-maintenance-queue` | [Decision required updates and maintenance queue](80-evolution/rfcs/0018-decision-followups-and-maintenance-queue.md) | explanation | 2 |  |
| `0019-glossary-discipline` | [Glossary discipline and terminology resolution](80-evolution/rfcs/0019-glossary-discipline.md) | explanation | 2 |  |
| `0020-inventory-drift` | [Derive, don't materialize — surfaces, curated inventory, and the boundary lint](80-evolution/rfcs/0020-inventory-drift.md) | explanation | 2 |  |
| `0021-code-doc-cochange` | [Code-doc co-change drift signal](80-evolution/rfcs/0021-code-doc-cochange.md) | explanation | 2 |  |
| `0022-universal-fix-coverage` | [Universal auto-fix coverage](80-evolution/rfcs/0022-universal-fix-coverage.md) | explanation | 2 |  |
| `0023-adr-template-structure` | [ADR template and structured decision record](80-evolution/rfcs/0023-adr-template-structure.md) | explanation | 2 |  |
| `0024-anchored-prose-claims` | [Anchored prose claims (pinned provenance)](80-evolution/rfcs/0024-anchored-prose-claims.md) | explanation | 2 |  |
| `0025-retire-render-subsystem` | [Retire the render and reference-stub subsystem](80-evolution/rfcs/0025-retire-render-subsystem.md) | explanation | 2 |  |
| `0026-retire-tier-1-and-reference-layer` | [Retire Tier 1 and the dedicated reference layer](80-evolution/rfcs/0026-retire-tier-1-and-reference-layer.md) | explanation | 2 |  |
| `0027-watched-surfaces` | [Watched surfaces: pin a derivable surface and flag any change for review](80-evolution/rfcs/0027-watched-surfaces.md) | explanation | 2 |  |
| `0028-mcp-tool-surface-governance` | [Govern the MCP tool surface as a watched surface](80-evolution/rfcs/0028-mcp-tool-surface-governance.md) | explanation | 2 |  |
| `0029-bound-change-loop` | [Bound changes: turn the RFC into a code-bound proposal-to-verification loop](80-evolution/rfcs/0029-bound-change-loop.md) | explanation | 2 |  |
| `0030-rfc-requirements-and-scenarios` | [Requirements and scenarios in the RFC, with provenance](80-evolution/rfcs/0030-rfc-requirements-and-scenarios.md) | explanation | 2 |  |
| `0031-change-tasks-and-apply` | [Change tasks and the apply loop](80-evolution/rfcs/0031-change-tasks-and-apply.md) | explanation | 2 |  |
| `0032-accept-time-anchoring` | [Accept-time anchoring: archive that anchors, not just tidies](80-evolution/rfcs/0032-accept-time-anchoring.md) | explanation | 2 |  |
| `0033-derived-layered-impact` | [Derived layered impact: the change ripple as a query, not metadata](80-evolution/rfcs/0033-derived-layered-impact.md) | explanation | 2 |  |
| `0034-base-truth-gate-and-mcp-loop` | [Base-truth gate and the MCP loop surface](80-evolution/rfcs/0034-base-truth-gate-and-mcp-loop.md) | explanation | 2 |  |
| `80-evolution` | [Evolution](80-evolution/INDEX.md) | reference | 4 |  |
| `patterns` | [Evolution Patterns](80-evolution/patterns.md) | explanation | 2 |  |
| `rfcs` | [RFCs](80-evolution/rfcs/INDEX.md) | reference | 2 |  |

### 90-meta

| ID | Doc | Audience | Tier | Summary |
|----|-----|----------|------|---------|
| `90-meta` | [Meta](90-meta/INDEX.md) | meta | 2 |  |
| `agent-protocol` | [Agent lifecycle protocol](90-meta/agent-protocol.md) | explanation | 3 | The required work order any agent must follow when editing this repository. |
| `style-guide` | [Style Guide](90-meta/style-guide.md) | reference | 3 |  |

<!-- agents-manifest:generated-end -->

## Foundations

Read this before editing any doc. Full detail lives in `docs/00-foundation/`
and `docs/10-architecture/`.

### The Three Laws of Maintenance

> **Law 1.** Each fact has exactly one home.
>
> **Law 2.** Each document has exactly one purpose and one audience moment.
>
> **Law 3.** Every cross-reference is bidirectional and machine-verifiable.

### The Layered Structure

Numeric prefixes give stable sort order and namespace doc IDs as bare slugs.

- `00-foundation` — principles, constraints, stakeholders; rarely changes.
- `10-architecture` — system context, containers, boundaries, deployment.
- `20-components` — the per-component "what".
- `30-workflows` — cross-component "how".
- `50-decisions` — ADRs; the "why", append-only.
- `60-operations` — runbooks, playbooks, SLOs.
- `70-knowledge` — tutorials, how-tos, explanations.
- `80-evolution` — roadmap, RFCs, risks, debt.
- `90-meta` — docs about the doc system.

### The Tier System

Each doc's tier dictates its enforcement policy.

| Tier | Name | Edited by | Examples |
|------|------|-----------|----------|
| T2 | Stable | Humans, rarely | Principles, architecture overview, ADRs |
| T3 | Living | Humans, often | Component docs, workflows, runbooks |
| T4 | Ephemeral | Anyone | Sprint plans, RFCs in flight |

## Protocol

Before editing docs, follow the agent lifecycle protocol: read this
manifest, run `irminsul context` to locate ownership, tests, dependencies,
and findings, create or update RFCs and ADRs for direction or behavior
changes, keep component docs and generated references current, and run
`irminsul check --profile hard` before returning work.

The full lifecycle work order lives at
[`90-meta/agent-protocol`](90-meta/agent-protocol.md); its rationale and
alternatives live in
[`0016-agent-lifecycle-protocol`](80-evolution/rfcs/0016-agent-lifecycle-protocol.md).
