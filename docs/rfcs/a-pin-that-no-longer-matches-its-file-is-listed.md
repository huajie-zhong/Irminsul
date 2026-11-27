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
file, a rule the accepted RFC on naming a part of evidence keeps. On 2026-11-26 nine such
pins sat in component docs, and two reviewers each wrote a script to find them. This adds a read-only listing of every pin that no longer matches, so an
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
  reading `--re-pin` makes. A target that does not resolve is left to the findings that
  report it.
- **A row.** In the JSON, `{"version": 1, "stale": [...]}`, each row has `doc`, `line`, `kind`
  (`anchor` or `claim-evidence`), `target` (`path#symbol` for an anchor, the evidence path for a
  claim), `claim` (the claim id, or null), `pinned`, `current`, `reported_by` and `re_pin`.
  `line` is the anchor marker's line, or for a claim the line of its `<!-- claim:<id> -->`
  marker in the body, or 1 when no paragraph declares it. `re_pin` is the whole command that
  re-pins only that pin: `irminsul anchors --re-pin --doc <doc> --anchor <path#symbol>`, or
  `--claim <id> --evidence <path>`. Plain output prints one row per line and a count.
- **`reported_by`.** The listing runs the two checks that ask about pins, `claim-anchor` and
  `claim-provenance`, over the same graph and names the code of a finding about that doc and
  that anchor target or claim id: `claim-anchor/pinned-drift` for a stale anchor, and
  `claim-provenance/evidence-drift` for a claim's evidence when that check reports it, which
  depends on the doc's layer and on commit times. Otherwise it is null.
- **Flags.** `--stale` takes `--doc` and `--format`. With `--re-pin` or `--suggest` it exits 2:
  one action per run.
- **Measured** with a script doing the same reading of claim evidence pins: 38 on main, of
  which 12 were stale before the re-pins of 2026-11-26 (three in architecture and foundation
  docs, reported once a squash merge made them newer than their docs) and 9 after them, all in
  component docs and none reported. Re-reading and re-pinning on 2026-11-27 leaves none, so
  the listing starts empty on this repository.
- **Out of scope.** The MCP `anchors` tool returns `claim-anchor` findings and does not gain the
  listing; `affects` names no MCP change.
- **Not chosen.** Changing `evidence-drift` to report a stale pin whatever the commit times:
  the accepted `claim-evidence-names-a-part` keeps the fallback (its requirement
  `part-pin-suppresses-drift`, scenario "Doc updated beside the evidence"), and its last step
  judges every layer but still skips a stale pin behind a later doc commit, so that change
  would overturn an accepted decision; this listing is how such a pin is seen meanwhile. A
  dry run of `--re-pin`, which prints what would move: it covers one doc or `--all`, and puts
  a reading behind a flag of the command that writes. Naming the commit a stale pin last
  matched: useful for knowing what to re-read, and left to the backlog.

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
