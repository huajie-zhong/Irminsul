---
id: 0041-pre-lifecycle-rfc-migration
title: "Migrate pre-lifecycle RFCs without inferring intent"
audience: explanation
tier: 2
status: stable
describes: []
rfc_state: accepted
affects:
- change
- checks
- frontmatter
- new-list-regen
resolved_by: docs/50-decisions/0020-migrate-pre-lifecycle-rfcs-explicitly.md
required_updates: []
---

# RFC 0041: Migrate pre-lifecycle RFCs without inferring intent

## Summary

Add `irminsul change migrate` to inventory RFCs created before structured
lifecycle metadata and apply one explicit, human-authorized classification at a
time. Agents receive evidence and exact plans; the command never recommends or
infers a lifecycle state from document status, Git history, links, or code.

## Motivation

`rfc_state` remains optional so repositories can parse historical proposals, but
every normal `change` command rejects an RFC without it. Lifecycle checks and the
maintenance queue currently skip those files, leaving real historical work
outside the system that is supposed to account for it.

Document `status: stable` cannot solve this. A stable proposal can still be a
draft, and implementation-looking code or links do not prove acceptance. The
migration must expose evidence to agents while reserving state, scope, decision,
and implementation attestation for human authority.

## Requirements

### Requirement: Inventory pre-lifecycle RFCs
ID: inventory-pre-lifecycle-rfcs
Provenance: code

The command MUST list RFC atoms under the configured RFC directory whose
frontmatter has no `rfc_state`, sorted by id and excluding the index.

#### Scenario: Repository inventory
- **WHEN** `change migrate` is called without an RFC argument
- **THEN** plain or versioned JSON output lists every candidate and evidence without a recommended state

#### Scenario: Detailed candidate
- **WHEN** one candidate is named without `--state`
- **THEN** the command returns its detailed evidence packet and performs no write

#### Scenario: Modern RFC
- **WHEN** a named RFC already has `rfc_state`
- **THEN** the command rejects it as not being a migration candidate

### Requirement: Require explicit classification inputs
ID: require-explicit-classification
Provenance: code

The command MUST require `--state draft|accepted|implemented|rejected` before it
can plan a mutation and MUST NOT derive that value from candidate evidence.

#### Scenario: Draft classification
- **WHEN** a human selects `draft`
- **THEN** the plan adds migration provenance and `rfc_state: draft` while preserving the existing document status

#### Scenario: Accepted classification
- **WHEN** a human selects `accepted`
- **THEN** an existing stable ADR with a backlink, explicit affected scope, explicit required-update disposition, and the normal requirement grammar are required

#### Scenario: Rejected classification
- **WHEN** a human selects `rejected`
- **THEN** an explicit rejection reason is required and becomes the rejection-rationale section

#### Scenario: Implemented classification
- **WHEN** a human selects `implemented`
- **THEN** accepted-state inputs plus `--attest-implemented` are required and the RFC records that historical implementation was human-attested rather than normally finalized

### Requirement: Preserve migration provenance
ID: preserve-migration-provenance
Provenance: code

Every migrated RFC MUST carry typed `lifecycle_migration` metadata with
`source: pre-lifecycle` and a basis distinguishing human classification from
historical implementation attestation.

#### Scenario: Later status inspection
- **WHEN** an agent reads a migrated RFC
- **THEN** it can distinguish ordinary lifecycle finalization from legacy classification without consulting Git history

### Requirement: Plan before writing
ID: plan-before-writing
Provenance: code

Migration MUST be read-only by default, MUST require `--confirm` for mutation,
and MUST apply one RFC atomically through one composite transformation.

#### Scenario: Default invocation
- **WHEN** a valid target state and inputs are supplied without `--confirm`
- **THEN** the exact planned changes are printed and the file remains byte-for-byte unchanged

#### Scenario: Confirmed invocation
- **WHEN** the same valid plan is supplied with `--confirm`
- **THEN** all metadata and terminal prose are written atomically to one RFC

#### Scenario: Transformation fails
- **WHEN** any transformation raises before replacement
- **THEN** the original RFC remains unchanged and the command exits with an error

### Requirement: Seal attested implementation last
ID: seal-attested-implementation-last
Provenance: code

An implemented migration MUST set all classification metadata and terminal prose
before calculating the normal `frozen_hash` seal.

#### Scenario: Historical implementation is attested
- **WHEN** a valid implemented migration is confirmed
- **THEN** its seal verifies against the complete migrated record and later edits fail lifecycle integrity

#### Scenario: Attestation is absent
- **WHEN** `implemented` is selected without `--attest-implemented`
- **THEN** migration is blocked and ordinary `change finalize` remains the only non-migration implementation path

### Requirement: Expose migration debt
ID: expose-migration-debt
Provenance: code

Lifecycle integrity and `list lifecycle --queue` MUST report each pre-lifecycle
RFC with a direct `change migrate <id>` next action.

#### Scenario: Legacy candidate remains
- **WHEN** an RFC has no lifecycle state
- **THEN** hard-profile output warns without blocking and the lifecycle queue classifies the work as migration

## Detailed Design

`find_rfc_artifact()` resolves id, numeric prefix, or repository-relative path
without requiring state. Existing lifecycle commands call the stricter
`find_rfc_node()` wrapper; migration alone accepts missing state.

`change/migrate.py` builds versioned inventory records and a `MigrationPlan`.
Candidate evidence includes existing status, lifecycle-shaped fields, decision
docs linking the RFC, implementation backlinks, and headings. The JSON carries
`recommended_state: null` deliberately.

Scope uses repeated `--affects <component>` or `--affects-none`. Required update
disposition uses repeated `--required-update <path>` or
`--no-required-updates`. Existing explicit frontmatter values satisfy those
inputs. Mutually exclusive or state-inapplicable flags are usage errors.

Accepted and implemented migration require `--resolved-by` (or an existing
value) that resolves to a stable ADR whose Markdown links back to the RFC.
Accepted migration runs the normal requirement grammar gate. Implemented
migration is the narrow historical exception: explicit
`--attest-implemented` persists `basis: human-implementation-attestation`, then
the composite transform seals the record last. It does not fabricate anchors,
claim promotions, or evidence that did not exist in the pre-lifecycle process.

## Tasks

- `T1` Add typed lifecycle migration provenance to frontmatter. (component: frontmatter)
- `T2` Split state-neutral RFC artifact resolution from normal change resolution. (component: change)
- `T3` Build inventory, evidence, planning, and atomic transforms. (req: plan-before-writing)
- `T4` Add the CLI and versioned JSON/plain output. (component: change)
- `T5` Report legacy RFCs in lifecycle integrity and the maintenance queue. (req: expose-migration-debt)
- `T6` Add fixture, focused, CLI, seal, and failure-atomicity coverage. (component: checks)
- `T7` Document the migration and provenance contract without classifying Irminsul's legacy RFCs automatically. (component: new-list-regen)

## Drawbacks

- Migration is intentionally one RFC at a time; repositories with many legacy
  proposals need repeated human decisions.
- Historical implemented attestation is weaker than normal finalization and is
  labeled permanently rather than disguised as verified evidence.
- Accepted migration requires modern requirement grammar, so an old still-live
  proposal may need a real contract edit before acceptance.

## Alternatives

- Infer state from `status`, links, or code. Rejected because each produces
  false implementation claims in real repositories.
- Bulk-write every missing state as draft. Rejected because even a reversible
  default would overwrite historical truth without approval.
- Require manual YAML edits only. Rejected because agents need inventory,
  validation, atomicity, and stable machine output for a safe migration loop.
- Route historical implementation through ordinary finalization. Rejected
  because pre-lifecycle RFCs lack the anchors and requirement contracts that
  ordinary finalization is designed to prove.

## Unresolved Questions

- A future batch orchestrator may sequence already-approved per-RFC plans, but
  it must not add a state inference policy.

## Resolution

Accepted by
[`ADR-0020`](../../50-decisions/0020-migrate-pre-lifecycle-rfcs-explicitly.md).
Migration is an evidence-and-confirmation workflow, not a state inference policy:
agents may inventory, explain, and prepare a plan, while a human supplies the
lifecycle classification and any historical implementation attestation.
