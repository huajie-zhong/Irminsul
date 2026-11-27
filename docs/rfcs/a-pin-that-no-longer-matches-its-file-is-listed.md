---
id: a-pin-that-no-longer-matches-its-file-is-listed
title: "A pin that no longer matches its file is listed"
status: draft
summary: "`irminsul anchors --stale` lists every anchor and claim evidence pin, in any doc, whose file no longer has the pinned hash, with the command that re-pins only that one, and fails nothing."
describes: []
rfc_state: draft
affects:
  - anchors
  - cli
weight: small
---

# A pin that no longer matches its file is listed

## Summary

A pin records what a file looked like when someone last re-read the sentence that relies on
it. Today a claim's pin can stop matching its file and nobody is told: the check that asks
about it judges two layers of docs only, and skips a pin whose doc was committed after the
file. On 2026-11-26 nine such pins sat in component docs, and two reviewers each wrote a
script to find them. This adds a read-only listing of every pin that no longer matches, so an
agent can see them and re-read each one, without changing what any check reports. The owner
chose this over changing the check on 2026-11-27; three decisions remain.

## Decisions

1. **Where it lives.** (a) A flag, `irminsul anchors --stale`. Recommended: the command
   already reports and re-pins pins, and nothing it prints today changes. (b) In the plain
   output of `irminsul anchors`, beside the findings it reports: no new flag, but the JSON of
   that command changes shape.
2. **Its exit code.** (a) Always 0, as a reading list. Recommended: the gate stays what the
   checks decide. (b) Non-zero when any pin is stale: a script could fail on it, but it would
   be a second gate beside `check`.
3. **What it lists.** (a) Every stale pin, anchors and claim evidence alike, each saying
   whether a check already reports it. Recommended: one place answers "what is stale".
   (b) Only the claim evidence pins no check reports: shorter, but an agent then runs two
   commands.

## Design detail

- **Today.** `claim-anchor/pinned-drift` reports an anchor whose target changed, in any doc.
  `claim-provenance/evidence-drift` reports a claim's evidence only in the foundation and
  architecture layers (`_is_protected_claim_node` in
  `src/irminsul/checks/claim_provenance.py`), and reads a pin that no longer matches as no
  pin, falling back to commit times (`_scan_evidence_drift`), so it is silent while the doc's
  last commit is no older than the evidence's. `anchors --re-pin` is the only command that
  computes every pin, and it writes. The backlog entry `component-claim-drift-unreported`
  records both gaps and asks for a read-only listing.
- **The listing.** For each doc, or the one `--doc` names: each anchor whose target resolves
  and hashes differently from its pin, and each claim evidence pin whose file hashes
  differently, through `resolve` and `file_pin` in `src/irminsul/anchors.py`, the same
  reading `--re-pin` makes. A row holds the doc and line, the kind (`anchor` or
  `claim-evidence`), the target, the pinned and current hash, the finding code that reports
  it or none, and the command that re-pins only it: `--anchor <path#symbol>` for an anchor,
  `--claim <id> --evidence <path>` for a claim's evidence. A target that does not resolve is
  left to the findings that report it. Plain output prints one row per line and a count; the
  JSON is `{"version": 1, "stale": [...]}`.
- **Flags.** `--stale` takes `--doc` and `--format`. With `--re-pin` or `--suggest` it exits 2:
  one action per run.
- **Measured** on 2026-11-26 with a script doing the same reading: 38 claim evidence pins on
  main, 9 stale, all in component docs, none reported. After the re-pins of that day, 3 remain.
- **Not chosen.** Changing `evidence-drift` to report a stale pin in every layer whatever the
  commit times: it reports more, so it waits for `claim-evidence-names-a-part`, whose last
  step judges every layer. Naming the commit a stale pin last matched: useful for knowing
  what to re-read, and left to the backlog.

## Requirements

### Requirement: Every stale pin is listed and nothing fails
ID: stale-pins-are-listed
Provenance: code

`irminsul anchors --stale` SHALL list each anchor and each claim evidence pin, in every doc or
the one `--doc` names, whose target's current hash differs from its pin, each with the
command that re-pins only that pin, and SHALL exit 0.

#### Scenario: A component claim's evidence changed
- **WHEN** a component doc's claim pins `src/loans/policy.py` and that file has changed since, with the doc committed after it
- **THEN** `irminsul anchors --stale` lists that pin with `--claim <id> --evidence src/loans/policy.py` and exits 0

#### Scenario: Every pin matches
- **WHEN** every pin in the tree matches its file
- **THEN** `irminsul anchors --stale` lists nothing and exits 0

#### Scenario: Two actions in one run
- **WHEN** `irminsul anchors --stale --re-pin --doc <doc>` runs
- **THEN** it exits 2 and writes nothing

## Tasks

- `T1` List the stale anchors and claim evidence pins under `anchors --stale`, plain and JSON, with the narrow re-pin command for each. (req: stale-pins-are-listed)
- `T2` Say it in the anchors doc, the help of `anchors` and the changelog, and close the backlog's request for a read-only listing. (component: anchors)
