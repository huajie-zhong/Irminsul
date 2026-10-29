---
id: claim-evidence-names-a-part
title: "Claim evidence names a part"
status: stable
describes: []
rfc_state: accepted
affects:
  - anchors
  - checks
  - frontmatter
  - context
  - new-list-regen
  - languages
  - cli
  - init
  - adoption-record
resolved_by: docs/decisions/code-is-named-in-code-spans-and-bound-by-anchors.md
summary: A claim's evidence may name part of a file, found by a finder its extension selects, so its pin re-asks the claim only when that part changes; anchors resolve through the same finders, and evidence drift is then judged in every layer.
required_updates: []
weight: large
---

# Claim evidence names a part

## Summary

A claim, a doc's sentence about code, is re-asked when the code it rests on changes, not
whenever its file does, and claims in component docs get asked at all. Its evidence, the
files it rests on, may name one part of a file, which a finder for the file's type locates
without guessing, so its pin, the hash taken at the last read, covers only that part. Two
decisions, both answered.

## Problem

Measured on 2026-10-27, before the history reset: the claim `parent-child-check-available`
rests on one bullet of the checks doc, unchanged since 2026-09-21. Because a pin covers a
whole file, that doc's 65 commits in one week forced 31 rewrites of the pin, each for an
unchanged bullet. A pin on the bullet's section would have moved 5 times.

Evidence drift, the finding that asks for a re-read, also skips every layer but foundation
and architecture, for no recorded reason, so two claims of the adoption-record component
doc went unasked when their code changed on 2026-10-22.

## How it works

**A part** follows a `#`, as in `src/irminsul/cli.py#fix`, and its pin hashes only that
part; a bare path keeps today's whole-file pin.

**One finder per file type.** Python names a definition, hashed as every Python pin is;
Markdown, a heading; TOML, YAML and JSON, a key path. An absent or ambiguous name is a
certain finding, never a guess.

**Markers**, a pair of `irminsul:part` comments, mark a part in any text file and win over a
same-named symbol.

**Other languages** gain finders through their language profile; tree-sitter, as a required
dependency, is the recorded route.

**Anchors**, links from prose to code, use the same finders, replacing today's guess for
non-Python symbols.

**Review** keeps a part's claim only when that part changed; re-pointing evidence that a
rename broke needs no decision record, only a re-read.

**Drift in every layer** drops the layer test, as the last step (decision 2).

Not chosen: re-pinning more, Python and Markdown only, line ranges, tree-sitter now.

## Cost and risk

Five pull requests, one a migration that re-reads each narrowed claim. The main risk is
review missing a narrowed claim, so each test first fails on a planted instance. A part that
omits code its claim rests on under-asks it silently, so bare paths stay the default.
Adopters' non-Python symbol anchors break until marked.

## Decisions

Answered by the owner on 2026-10-28:

1. **A marked region of a Python file is hashed through its syntax tree**, like every other
   Python pin ([Python pin record](../decisions/code-is-named-in-code-spans-and-bound-by-anchors.md)):
   the dedented region is parsed and hashed, so a comment edit does not re-ask the claim, and a
   region that does not parse on its own does not resolve. One rule for Python pins.
2. **Drift in every layer lands last**, after part pins exist, since part pins are what keep
   it quiet.

## Design detail

### Grammar and pins

```yaml
evidence:
  - src/irminsul/cli.py#_failing_classes
pinned:
  src/irminsul/cli.py#_failing_classes: sha256:90ac15d2e7f3
```

- An entry splits at its first `#`, one part per entry. Whatever reads only the path, such
  as `evidence-path-missing`, the state classifiers and ownership, strips the part.
- A pin is keyed by the entry as written. An unpinned part falls back to commit times, so
  narrowing gains nothing until the re-pin. A bare path keeps the whole-file pin and stays
  the default.
- YAML reads `- src/x.py #Sym` as the bare path and a comment, which fails safe: the claim
  is asked more.

### Part finders

| Files | A part names | Hashed |
|-------|--------------|--------|
| `.py` | a top-level definition, or a dotted `Class.member`, as anchors resolve today | `_canonical` of the definition's syntax tree, as every Python pin is hashed today, so a comment edit does not move it |
| `.md` | a heading, by the slug link anchors use | the heading line and the lines to the next heading of the same or higher level, whitespace collapsed |
| `.toml`, `.yaml`, `.yml`, `.json` | a dotted key path | the value as canonical JSON: sorted keys, no whitespace |
| any text file | a marker name | the lines between the two markers, whitespace collapsed; in a `.py` file, the dedented lines parsed and hashed through `_canonical`, and a region that does not parse does not resolve (decision 1) |

- **Markers** `irminsul:part <name>` and `irminsul:end <name>` sit on any line, in the
  file's comment syntax. A marker wins over a same-named symbol, heading or key, because it
  is the author saying where the part is.
- **Nothing is guessed.** A name marked twice or never closed, a slug two headings share,
  and a key in a multi-document YAML file do not resolve. A key passes through mappings
  only, so a list is hashed whole; a segment holding a dot is double-quoted. A part that
  does not resolve is a certain finding naming the closest names the finder knows, so a
  renamed function is caught the way a renamed file is today.
- **Text in, hash out**, so a finder also hashes a revision read from git.
- **The hook.** A [language profile](../components/languages.md) may declare a finder for
  its extensions. The Python profile declares `.py`, so the hook is used from the start.
  Until a language has a finder, its files get parts only through markers.
- **A marked region of a `.py` file** (decision 1). The accepted record says every Python
  pin hashes the canonical syntax tree; the marker row as drafted would hash a marked
  region of a `.py` file as whitespace-collapsed text, so a comment edit would move it.
  - Under (a), the lines between the markers are dedented, parsed, and hashed by
    `_canonical` in `src/irminsul/anchors.py`, as a definition is, for an anchor and a
    claim pin alike. A region that does not parse on its own, such as half a statement,
    does not resolve, in line with "nothing is guessed": the author learns at once, as a
    certain finding, and marks whole statements. It reuses the canonical hash.
  - Under (b), the region is hashed as whitespace-collapsed text, and the resolving record
    also qualifies the Python-pin record, a third beside the two below.
- **tree-sitter** is the recorded route once several languages need finders, as a required
  dependency. An optional extra would let a file resolve on one machine and fail on
  another, which `checks-are-deterministic` in [enforcement](../foundation/enforcement.md)
  rules out. Until then, markers serve.

### Anchors

- `_resolve_text` in `src/irminsul/anchors.py` guesses a non-Python symbol's block from a
  whole-token match and a definition-looking line; a wrong block under-asks the anchor
  silently, so the guess is deleted, and a symbol no marker or finder resolves is a certain
  finding.
- In this repository's docs, extra docs and fixture repos, every anchor that names a symbol
  targets a `.py` file, so nothing here breaks. The only non-Python anchors are two
  file-level ones on `docs-pr.yml.j2` templates in `docs/components/init.md`, which keep
  their whole-text hash.
- Only `tests/test_binding.py` exercises the guess, with TypeScript and Go files built
  inline.

### Review, the seal and the repair rule

- **Review follows parts.** Review matches an entry to a file by its path, so before an
  edit `irminsul context` lists the claim and names the part. After a change, review keeps
  a part's claim only when that part hashes differently at the base than in the working
  tree.
- **The seal.** A governing claim, a `governs-evidence` claim, is a contract the owner
  decided, and the seal reports any change to its evidence unless a decision record names
  the claim. A renamed symbol or file leaves an entry that no longer resolves, and the
  certain finding forces an edit the seal would refuse. So when every entry a change
  removed no longer resolves, re-pointing is a repair: the seal stays quiet, and review
  lists the claim for a reader to confirm the new target. Narrowing an entry whose target
  still exists still needs a record.
- **Review drops narrowed claims**, the largest risk here. `_governing_claims` and
  `claim_reviews_for_paths` in `src/irminsul/context.py` match evidence by exact string,
  so a narrowed contract would never be re-asked; a wrong hash comparison would hide a
  changed part. Each test is shown failing on a planted instance first.
- **A hole in the removal seal.** `_evidence_exists` in `diff_integrity.py` asks whether
  the spelling names a file. A part spelling names none, so a removed claim citing a part
  reads as "evidence gone" and `claim-removed` is skipped.
- **A rename is a dead end.** `_rewritten_governing_claims` reports any edit to a
  governing claim's `evidence`, which a renamed symbol forces through the certain
  `evidence-part-missing`, as a renamed file does through `evidence-path-missing`. Both
  are therefore repairs: once the base's entry no longer resolves at head, nothing is left
  to govern, and re-pointing is the only way out.
- **A repair is read.** It changes what the claim points at, so `list review --changed`
  lists the claim for a reader to confirm the new target, at the cost of one item.

### Drift in every layer

`_is_protected_claim_node` in `src/irminsul/checks/claim_provenance.py` goes, so
`evidence-drift` judges the claims of every stable doc. The "protected claims" in
`docs/architecture/layers.md` and the layer sentence in the Scope of
`docs/components/checks.md` are reworded; that sentence is already wrong, since
`rfc-follow-through` reports `stale-claim` in every doc. It lands last, after the migration
narrows the claims (decision 2).

### Measured figures

Measured on 2026-10-27, before the history was reset on 2026-10-28; the commits they count
are archived outside this repository.

- **The whole-file pin.** `parent-child-check-available` in
  `docs/architecture/component-hierarchy.md` cites `src/irminsul/checks/parent_child.py`
  and `docs/components/checks.md`. In `checks.md` it rests on the bullet "The graph and its
  edges", which lists `parent-child` and has not changed since 2026-09-21. From 2026-10-20
  to 2026-10-27, `checks.md` had 65 commits, and the claim's pin on it was rewritten 31
  times (11 on 10-21, 18 on 10-22, 2 on 10-27): each a re-read of an unchanged bullet, or a
  doc-wide re-pin that acknowledged it without one. A part helps only once the list has its
  own section: today it sits under the H1, so `checks.md#checks` is the whole body. With an
  H2 around it, the section changed in 5 of those commits, the check removals of 10-21, and
  about 26 of the 31 re-asks go away.
- **Code evidence**, from 2026-10-20 to 2026-10-27:

  | Evidence file | Commits | Parts the claims rest on | Commits that changed the part |
  |---------------|---------|--------------------------|-------------------------------|
  | `src/irminsul/checks/pipeline.py` | 13 | `run_checks`; `apply_classes`, `effective_class`, `failing_findings` | 3; 1 |
  | `src/irminsul/cli.py` | 41 | `check`; `fix`; `_failing_classes` | 10; 2; 2 |

  So 13 re-asks become 1 to 3, and 41 become 2 to 10. The
  [record that introduced pins](../decisions/a-change-is-judged-from-its-merge-base-to-the-working-tree.md)
  names the remedy, narrowing evidence to the code a claim rests on, but no grammar allows
  it.
- **The unasked component claims.** `evidence-drift` judges only the foundation and
  architecture layers (`_is_protected_claim_node`), an exception no decision record
  explains, present since the first commit on 2026-09-21. On 2026-10-22, two commits
  changed `verified_debt` in `src/irminsul/adoption.py`, and one also changed the
  `_recorded_debt` readers then in `checks/uniqueness.py` and `checks/owned_tests.py`, since
  merged into `recorded_debt` in `adoption.py`. Two `governs-evidence` claims in
  `docs/components/adoption-record.md` rest on exactly those, `adoption-is-not-a-mode` and
  `cross-repo-debt-is-pinned`; nobody was asked to re-read them.
- **The layer experiment.** On main on 2026-10-27, forcing the layer test true turned no
  drift into 7 drifted pins: six in `adoption-record.md` and `context-is-stateless`. Three
  of the six cited `diff_integrity.py` functions unchanged since the pin, which is noise;
  with part pins they go quiet and the two claims above still drift, rightly. The
  `record-validity-is-asked-on-every-path` pins matched no committed revision, so its
  outcome was unknown. On 2026-10-28 the format migration of
  [a Python pin hashes the syntax tree](../decisions/code-is-named-in-code-spans-and-bound-by-anchors.md)
  re-pinned every pin, and the same experiment reports no drift until cited code changes
  again.

### Migration

The reader chooses each part and re-reads each claim before re-pinning it.

- `docs/components/checks.md` gains `## The checks by what they govern` above the grouped
  list and a second H2 below it, so the list forms a section of its own.
- **Narrowed `governs-evidence` claims**, all ten named in one [ADR](../GLOSSARY.md#adr)'s
  `## Decision`, because narrowing one while its file exists is `governing-claim-changed`:
  - overview: `checks-consume-the-graph` cites `docgraph.py#build_graph`,
    `pipeline.py#run_checks` and the new `checks/base.py#Check`, the protocol whose
    signature it states; `action-adds-no-logic` cites `cli.py#check`.
  - enforcement: `checks-are-deterministic` cites `pyproject.toml#project.dependencies` and
    `pipeline.py#run_checks`; `hints-advise` cites `apply_classes`, `effective_class` and
    `failing_findings` in `pipeline.py` and `cli.py#_failing_classes`;
    `fix-remediation-available` cites `cli.py#fix`.
  - adoption-record: `adoption-is-not-a-mode` and `cross-repo-debt-is-pinned` cite
    `verified_debt` and `recorded_debt` in `adoption.py` and the code in
    `checks/uniqueness.py`, `checks/owned_tests.py` and `checks/adoption_record.py` that
    calls them; `adoption-record-only-shrinks`,
    `adoption-exception-does-not-return` and `adopting-obligations-are-complete` cite the
    adoption functions in `diff_integrity.py`.
- **Narrowed `follows-evidence` claims**, needing no record: `parent-child-check-available`
  cites the new section, `certain-findings-block` the three `pipeline.py` functions above.
- **Kept bare:** `context-is-stateless` and `record-validity-is-asked-on-every-path`,
  each about a whole module or every entry point, so any commit to the file is a fair
  question; `action.yml`, `src/irminsul/fix.py`, `ci.yml` and `irminsul.toml`; and every
  claim not named.

### What this supersedes

This [RFC](../GLOSSARY.md#rfc) supersedes two requirements of
[Acknowledge a reviewed co-change or evidence drift](acknowledge-a-reviewed-co-change-or-evidence-drift.md).
That implemented RFC is not edited. Relations are forward-only, and `supersedes:` names a
whole doc while the predecessor's trailer requirements still hold, so this RFC names what
it replaces: `acknowledge-a-reviewed-co-change-or-evidence-drift#pin-suppresses-drift` by
`part-pin-suppresses-drift`, and `#re-pin-writes-claim-pins` by `re-pin-writes-part-pins`.
Finalization promotes the replacements into `docs/components/checks.md` and
`docs/components/anchors.md`, and the same change removes the bullets they replace.

### Records this qualifies

Two accepted records each have one bullet this changes:
[anchors resolve in any language](../decisions/code-is-named-in-code-spans-and-bound-by-anchors.md)
and [a pin covers a whole file](../decisions/a-change-is-judged-from-its-merge-base-to-the-working-tree.md).
Their other bullets hold, so, as [A gate file is sealed, not scored](a-gate-file-is-sealed-not-scored.md)
did, the resolving record qualifies each bullet and each Status line gains a sentence.
Decision 1 (b) would add the Python-pin record as a third.

### Cost and risk in detail

- **The five pull requests**, as under Tasks: the finders and anchors on them; the claim
  grammar, pins, the two new codes and re-pin; review by path and the two `diff-integrity`
  rules; the migration and its decision record; drift in every layer.
- A part that omits code the claim rests on under-asks it silently. The bare path stays
  the default, and narrowing a governing claim needs a decision record.
- The repair rule lets a change delete what a governing claim names and re-point it
  without a record; the deletion shows in the diff, and review lists the claim.
- Markers are plain text, so a marker quoted in a doc or a string counts as one.
- An adopter's non-Python symbol anchors break until they get markers or a finder.
- `context-is-stateless` stays whole-file, so drift asks it on each commit to
  `src/irminsul/context.py`, 17 from 2026-10-20 to 2026-10-27.
- tree-sitter, when it comes, adds install weight, a cost
  [principles](../foundation/principles.md) weighs heavily at adoption.

### Alternatives not chosen

- **Keep whole-file pins and re-pin more.** Rejected: 31 re-reads of an unchanged bullet in
  seven days teach re-pinning without reading.
- **Parts for `.py` and `.md` only.** The first design, rejected by the owner:
  `pyproject.toml#project.dependencies` is exactly the part `checks-are-deterministic`
  rests on, and markers give every other language a route without a guess.
- **Line ranges, such as `path#L10-L40`.** Rejected: they move with every edit above them.
- **tree-sitter now, or as an optional extra.** Rejected: no second language needs it yet,
  and an extra makes a verdict depend on the install.
- **A decision record for every rename.** Rejected: the certain finding forces an edit the
  seal then refuses.
- **Drift in every layer first.** The first draft rejected it because on 2026-10-27 it
  arrived with three noise findings; decision 2 weighs it again on today's tree.

### Settled questions

The first draft's three open questions are settled: a renamed file is a repair, as a
renamed symbol is; review lists a repaired claim; and `context-is-stateless` keeps a
whole-file pin.

## Requirements

### Requirement: Evidence names a part of a file
ID: evidence-names-a-part
Provenance: code

A claim's evidence entry `path#part` SHALL resolve to the lines between `irminsul:part`
and `irminsul:end` markers of that name when the file has them, and otherwise through the
finder its extension selects. An entry whose file has neither SHALL be reported as
`claim-provenance/evidence-part-unsupported`, a certain finding; a bare path SHALL keep
the whole-file pin.

#### Scenario: Markdown section
- **WHEN** a claim cites `docs/components/checks.md#the-checks-by-what-they-govern` and a commit edits a paragraph under another heading
- **THEN** the part's hash is unchanged

#### Scenario: Config key
- **WHEN** a claim cites `pyproject.toml#project.dependencies` and a commit changes only `[tool.ruff]`
- **THEN** the part's hash is unchanged, and adding a dependency changes it

#### Scenario: Marker wins
- **WHEN** a Python file defines a function `seal` and also wraps other lines in `# irminsul:part seal` and `# irminsul:end seal`
- **THEN** an entry `path#seal` resolves to the marked lines

#### Scenario: No finder
- **WHEN** a claim cites `src/session.ts#fetchUserSession` and that file has no marker of that name
- **THEN** `irminsul check` reports `claim-provenance/evidence-part-unsupported` and exits 1

### Requirement: A matching part pin suppresses evidence drift
ID: part-pin-suppresses-drift
Provenance: code

When an evidence entry's current hash equals its pin, keyed by the entry as written,
`evidence-drift` SHALL NOT report that entry; otherwise the entry SHALL be judged by the
commit-time comparison of its file.

#### Scenario: Another part of the file changed
- **WHEN** a claim cites `src/irminsul/cli.py#fix`, pinned at its current hash, and a commit after the doc changes only `check` in `cli.py`
- **THEN** no `evidence-drift` is reported for that claim

#### Scenario: Doc updated beside the evidence
- **WHEN** the part's hash differs from its pin, and the doc was committed after the file
- **THEN** no `evidence-drift` is reported for that claim

### Requirement: A part that does not resolve is certain
ID: missing-part-is-certain
Provenance: code

When an entry's file exists and its part does not resolve, `claim-provenance` SHALL report
`claim-provenance/evidence-part-missing`, a certain finding naming the closest names the
finder knows in that file, and `evidence-drift` SHALL NOT also report the entry.

#### Scenario: Renamed function
- **WHEN** a claim cites `src/irminsul/checks/pipeline.py#effective_class` and the function is renamed `finding_class`
- **THEN** `irminsul check` reports `evidence-part-missing` suggesting `finding_class` and exits 1

#### Scenario: Shared heading slug
- **WHEN** two headings in the cited Markdown file share the cited slug
- **THEN** `evidence-part-missing` is reported and says the slug is ambiguous

### Requirement: Re-pin writes a pin per part
ID: re-pin-writes-part-pins
Provenance: code

`irminsul anchors --re-pin` SHALL write one pin per evidence entry, keep it while the part
does not resolve, and drop a pin on a spelling the claim no longer cites. `--evidence`
SHALL accept a part spelling, and a bare path SHALL select every entry of that file.

#### Scenario: Bare path selects every part
- **WHEN** `hints-advise` cites three parts of `pipeline.py` and one of `cli.py`, and `irminsul anchors --re-pin --doc enforcement --claim hints-advise --evidence src/irminsul/checks/pipeline.py` runs
- **THEN** all three `pipeline.py` pins are written and the `cli.py` pin is left as it was

#### Scenario: Renamed part
- **WHEN** the claim's entry changed from `#effective_class` to `#finding_class` and the re-pin runs
- **THEN** a pin under the new spelling is written and the pin under the old spelling is removed

### Requirement: Anchors resolve through the part finders
ID: anchors-resolve-through-part-finders
Provenance: code

An anchor's symbol SHALL resolve through the same markers and finders as an evidence part,
never by searching the text for the name, and otherwise SHALL be reported as
`claim-anchor/part-unsupported`, a certain finding. `irminsul anchors --suggest` SHALL
offer a `path#name` marker only where it resolves.

#### Scenario: TypeScript symbol without markers
- **WHEN** a doc anchors `src/session.ts#fetchUserSession` and the file has no marker of that name
- **THEN** `irminsul check` reports `claim-anchor/part-unsupported` and exits 1

#### Scenario: File anchor on a template
- **WHEN** `docs/components/init.md` anchors `src/irminsul/init/workflows/same-repo/docs-pr.yml.j2` without a symbol
- **THEN** the anchor resolves to the same hash as before this change

#### Scenario: Suggestion for a file without a finder
- **WHEN** an unbound name is defined only in a TypeScript file that has no markers
- **THEN** `irminsul anchors --suggest` offers the file anchor and no `path#name` marker

### Requirement: Review matches claim evidence by its path
ID: review-matches-evidence-by-path
Provenance: code

`irminsul context` and `irminsul list review` SHALL match an evidence entry to a file by
its path. In after-change mode, an entry that names a part SHALL keep its claim only when
the part hashes differently at the base than in the working tree, or resolves on one side
only.

#### Scenario: Another part changed
- **WHEN** a change edits `check` in `src/irminsul/cli.py` and a `governs-evidence` claim cites only `src/irminsul/cli.py#fix`
- **THEN** `irminsul list review --changed` does not list the claim

#### Scenario: The cited part changed
- **WHEN** the change edits `fix`
- **THEN** `irminsul list review --changed` lists the claim, naming `src/irminsul/cli.py#fix`

#### Scenario: Before an edit
- **WHEN** `irminsul context src/irminsul/cli.py` runs
- **THEN** the claim citing `src/irminsul/cli.py#fix` is listed, and its question names the part

### Requirement: A removed claim's part evidence is read at head
ID: removed-claim-reads-part-evidence
Provenance: code

Under `--diff <base>`, `diff-integrity` SHALL count a removed claim's `path#part` entry as
existing when its file exists at head and its part resolves there.

#### Scenario: Claim removed, code kept
- **WHEN** a change removes a `review-on-divergence` claim citing `src/irminsul/cli.py#fix`, and `fix` still exists
- **THEN** `irminsul check --diff <base>` reports `diff-integrity/claim-removed`, and would not had the change also deleted `fix`

### Requirement: Re-pointing evidence that no longer resolves is a repair
ID: repointing-unresolved-evidence-is-a-repair
Provenance: code

When only a `governs-evidence` claim's `evidence` changed and every entry the base listed
but the head does not fails to resolve at head, by a missing part or a missing file,
`diff-integrity` SHALL NOT report `governing-claim-changed`, and `list review --changed`
SHALL list the claim. Any other change to its evidence SHALL still be reported.

#### Scenario: Renamed symbol
- **WHEN** a change renames `effective_class` to `finding_class` and edits the `hints-advise` entry to match
- **THEN** no `governing-claim-changed` finding is reported, and `irminsul list review --changed` lists `hints-advise`

#### Scenario: Renamed file
- **WHEN** a change renames `src/irminsul/fix.py` and edits the `fix-remediation-available` entry to the new path
- **THEN** no `governing-claim-changed` finding is reported

#### Scenario: The old target still exists
- **WHEN** a change re-points `#effective_class` to `#failing_findings` while `effective_class` exists, or narrows `src/irminsul/cli.py` to `src/irminsul/cli.py#check`
- **THEN** `governing-claim-changed` is reported unless a decision record added in the change names the claim

### Requirement: Evidence drift is judged in every layer
ID: drift-judged-in-every-layer
Provenance: code

`evidence-drift` SHALL judge the claims of every stable doc, whatever its layer.

#### Scenario: Component claim
- **WHEN** a stable component doc's claim cites `src/irminsul/adoption.py#verified_debt`, pinned, and a commit after the doc changes `verified_debt`
- **THEN** `evidence-drift` is reported for that claim

## Tasks

### PR 1: finders, and anchors on them

- `T1` Add the finder table and the language-profile hook, with the Python profile declaring the `.py` finder; each finder hashes text, so a base revision can be compared. (req: anchors-resolve-through-part-finders)
- `T2` Resolve anchors through the table, delete the keyword guess in `_resolve_text`, add `claim-anchor/part-unsupported`, and move the TypeScript and Go cases in `tests/test_binding.py` to markers. (req: anchors-resolve-through-part-finders)
- `T3` Offer `path#name` from `anchors --suggest` only where a finder resolves it; update `docs/components/anchors.md` and add the qualifying Status sentence to the anchors record. (req: anchors-resolve-through-part-finders)

### PR 2: claim grammar, pins, the two codes, re-pin

- `T4` Split evidence at its first `#`, resolve the part, read the path alone for existence, state and ownership, and add `evidence-part-unsupported`. (req: evidence-names-a-part)
- `T5` Add `evidence-part-missing` with its did-you-mean, and skip an unresolved part in the drift scan. (req: missing-part-is-certain)
- `T6` Key pins by the full spelling and skip a matching part pin in `evidence-drift`; add the qualifying Status sentence to the record that introduced pins. (req: part-pin-suppresses-drift)
- `T7` Accept a part in `--evidence`, select every part for a bare path, and update `docs/components/frontmatter.md` and the CLI help. (req: re-pin-writes-part-pins)

### PR 3: review by path, and the two diff-integrity rules

- `T8` Match evidence on its path in `context` and `list review`, and in after-change mode keep a part entry's claim only when its hash changed; show each test failing on a planted instance first. (req: review-matches-evidence-by-path)
- `T9` Resolve part evidence at head in `_evidence_exists`. (req: removed-claim-reads-part-evidence)
- `T10` Treat an evidence edit as a repair when every removed entry no longer resolves at head, and list the repaired claim in `list review --changed`. (req: repointing-unresolved-evidence-is-a-repair)

### PR 4: migration and its decision record

- `T11` Add the two H2s around the grouped list in `docs/components/checks.md`, and narrow `parent-child-check-available` to the new section. (component: checks)
- `T12` Narrow the overview and enforcement claims listed under Migration, re-reading each one before re-pinning it. (req: evidence-names-a-part)
- `T13` Narrow the five adoption-record claims, re-reading each one before re-pinning it. (component: adoption-record)
- `T14` Add one decision record whose `## Decision` names each of the ten narrowed `governs-evidence` claims. (req: repointing-unresolved-evidence-is-a-repair)

### PR 5: drift in every layer

- `T15` Remove the layer test from `evidence-drift`, reword `docs/architecture/layers.md` and the Scope sentence in `docs/components/checks.md`, and close the `component-claim-drift-unreported` backlog entry. (req: drift-judged-in-every-layer)
- `T16` At finalization, remove the promoted bullets of the two superseded requirements from `docs/components/checks.md` and `docs/components/anchors.md`. (req: part-pin-suppresses-drift)

## Resolution

Accepted by the owner on 2026-10-28, with the answers recorded under Decisions, and resolved by
[Code is named in code spans and bound by anchors](../decisions/code-is-named-in-code-spans-and-bound-by-anchors.md).
