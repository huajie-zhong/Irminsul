---
id: decision-records-govern-what-they-decide
title: "Decision records govern what they decide"
status: stable
describes: []
rfc_state: accepted
affects:
  - checks
  - change
  - context
  - frontmatter
  - new-list-regen
  - init
resolved_by: docs/decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md
summary: A sign-off for one change becomes a commit trailer, and a decision record becomes a living topic that declares what it governs, is the only record for it, and is edited in place with a dated Changes line when its rule changes.
required_updates: []
weight: large
---

# Decision records govern what they decide

## Summary

Each decision has one record, found from the code it governs, and a change made on purpose
keeps its reason in its commit, not a new file. A **sign-off**, why one change did
something on purpose, becomes a line of the commit message. A **decision record** becomes a
living topic: it lists what it governs, no other record governs the same thing, and a changed
rule is edited in place with a dated line. Four decisions, all answered.

## Problem

Take the link cache's lifetime, `checks.external_links.ttl_hours`:

1. **PR #12** raises it from 168 hours to 720. The gate wants a reason and accepts only a new
   decision record naming the setting, so PR #12 adds one.
2. **After the merge** that record answers nothing, since base and change both say 720, but
   the file stays.
3. **PR #13** asks why the cache lives 30 days; no command leads from the setting to that
   record.

Records pile up: 24 on 20 October, 43 on 28 October. That day's history reset folded them
into 14, and four more followed: two each resolving one [RFC](../GLOSSARY.md#rfc), one only
correcting another record, which could not be rewritten, and one retiring two findings.

## How it works

**A sign-off is a commit trailer**, a `Key: value` line closing a commit message. PR #12's
commit gives the finding, the setting and a reason in an `Irminsul-Reviewed:` trailer, which
the every-hint RFC's acknowledgement step accepts; PR #12's run prints one info line with the
reason. After the merge nothing prints, and for PR #13 `irminsul context irminsul.toml` lists
the trailers on that file's commits.

**A record lists what it governs** in a new `governs:` field: files, a part of a file such as
one function, components, checks or settings. Two records governing one thing is an error, the
one-claim RFC's rule for docs, and `irminsul context <path>` names a path's record. A file no
record governs reports nothing.

**A changed rule is edited in place**: the Decision, one dated line under a new Changes
section, and the rest as needed. The gate flags the edit and a trailer answers it; a merged
Changes line is never edited. The baseline record, for example:

```markdown
---
id: a-baseline-holds-certain-findings-and-grows-only-by-decision
governs:
  - src/irminsul/baseline.py
  - src/irminsul/delta.py
  - src/irminsul/checks/diff_integrity.py#_baseline_ratchet
---
...
## Decision
...
- **Grows only with a reason.** A baseline holding entries its merge base did not is
  `diff-integrity/baseline-grew`, unless a commit trailer names its path or the change
  adopts Irminsul.
...
## Changes
- 2026-11-02: A trailer naming the baseline answers `baseline-grew`; an added record no
  longer does. [Each finding code has one answer](../rfcs/every-warning-hint-has-an-answer.md)
```

**A new decision goes into the record that governs what it changes**: accepting an RFC
writes there and adds the dated line. A new file appears only for something no record
governs, such as a new component, so records follow governed areas, not changes.

**At the second history reset** the 18 records gain their lists, and the four added after the
first reset fold into their topics, leaving 14.

Not chosen: a folder of sign-off records, still a file per change.

## Cost and risk

- **Accepted decisions can be rewritten**, each edit with a trailer (decision 4) and a dated
  line (decision 3). Removing or deprecating one is an error a trailer answers; deprecating
  passes unseen today.
- **"A record naming the setting answers it" becomes "a trailer naming it does".**
- **Trailer reasons live in git.** A squash reset drops them unless copied into a Changes line
  (the first left 34 commits' trailers in the archive), and a forge's squash merge can hide an
  early commit's.
- **Shared files are split by part**: eight records decide the module that compares a change
  with its base.
- One field, six new codes and two changed, a `context` section, a transition step; adopters
  add `governs:` to each record (decision 2).

## Decisions

Answered by the owner on 2026-10-29:

1. **A setting is governed by its dotted name**, checked against the config schema, since
   findings and trailers already name settings that way and most settings sit at a default no
   path reaches.
2. **A record must govern something.** A principle with no code of its own lives in the
   foundation's principles, so an empty list cannot route around the one-record rule.
3. **Every Decision edit adds a dated `## Changes` line**, the only form a check can verify,
   and the one that survives a history reset.
4. **An unanswered Decision edit is an error a trailer answers**, in every gate, since editing
   in place is now how a decision changes.

## Design detail

### Today, measured

- **The record excuse.** `run_diff_integrity` joins, as `added_records`, the `## Decision`
  text of every stable decision record the change adds (`_accepted_decision_text`), and nine
  places test for `` `name` `` in it: the baseline, the adoption record, claim rewording,
  claim removal, a weakened inventory entry, gate files, a changed governing claim, and the
  sealed and unsealed settings. A record that is edited rather than added counts for nothing.
- **`decision-rewritten`** is a hint, reported as a warning, for a record that was
  `status: stable` at the base and whose `## Decision` differs as `_decision_wording` reads it:
  inline links reduced to their text, backticks dropped, anchor pins left out. Context,
  Alternatives and Consequences are never compared. Its suggestion sends the reader to a new
  [ADR](../GLOSSARY.md#adr) that supersedes the record. The every-hint audit found that
  nothing clears it.
- **`accepted-decision-removed`** is certain. `_accepted` reads `status: stable`, and the sweep
  looks only for paths that are gone, so a record moved to `deprecated` or `draft` is not
  reported; the every-hint table gives exactly that as the way out, deprecating a record and
  deleting it in a later change.
- **`change transition`** requires a `resolved_by` naming a doc that exists
  (`dangling_resolved_by` in `change/gate.py`), any doc, not only a decision record. It writes
  the RFC's frontmatter and `## Resolution` and creates no record; the author writes one with
  `irminsul new adr`, and `rfc-follow-through/adr-missing-rfc-link` asks it to link back.
- **Trailers** are read by `commit_trailers` in `git/changes.py` with git's own trailer parser
  over `<base>..<head>`, so only the closing trailer block of each message counts.
- **Counts.** Records, without the INDEX: 24 on 2026-10-20, 33 on 2026-10-22, 38 on
  2026-10-27 and 43 at the archive tag `pre-v0.4.0` on 2026-10-28; 14 at the reset commit
  `c2a9685`; 18 on 2026-10-29, before the second reset. Commits carrying an `Irminsul-Reviewed`
  trailer: 34 in the archived history, 8 since the first reset, all `co-change` re-reads.

### Terms

- A **sign-off** here is a trailer: a change's author stating why it did something on purpose.
  A `small` RFC, which the RFC-layout record calls a sign-off too, is the owner approving a
  change before it is made; the two are different steps, and neither replaces the other.
- A **decision record** is a doc in the decisions layer other than its INDEX, as today. An
  **item** is what one `governs:` entry covers: a whole file, a part of a file, or a setting.

### The `governs:` grammar

A list of strings in a decision record's frontmatter, read only on decision records and added
to `DocFrontmatter`, so the `frontmatter-fields` surface names it. Each entry is one of:

| Entry | Example | Covers |
|---|---|---|
| a path or glob | `src/irminsul/change/**` | every file it matches, as a `describes:` pattern matches, over the files git lists and the untracked files it does not ignore |
| a path and a part | `src/irminsul/checks/diff_integrity.py#_SEALS` | that part, located by the finder its extension selects |
| a component | `component:anchors` | every file that component doc's `describes:` resolves to, so it follows that doc |
| a check | `check:co-change` | the module that defines that check or pass, where the repository holds it |
| a setting (decision 1) | `checks.external_links.ttl_hours` | that setting, or with a table's name every setting under it |
| an exclusion | `!src/irminsul/init/workflows/**`, `!src/irminsul/frontmatter.py#Claim` | removes files, or one part of a file, from the record's own items |

- **Parts** use the grammar and finders of [Claim evidence names a part](claim-evidence-names-a-part.md):
  one `#`, one part per entry. Until its finders land, a part resolves through the resolver
  anchors use today, `_find_symbol` in `src/irminsul/anchors.py`: a top-level definition or a
  dotted `Class.member` of a `.py` file. The mapping below names only such parts, so the reset
  does not wait for the finders. One resolver serves anchors, claim evidence and `governs:`.
- **Exclusions** follow the one-claim RFC (`a-source-file-has-one-claim`):
  a `!` entry is a negated gitignore pattern built into the same `GitIgnoreSpec` as the
  record's other paths, and a `!path#part` removes that part from a whole file the record
  governs, leaving the rest of the file. In the frontmatter such an entry is quoted,
  `- "!src/irminsul/init/workflows/**"`, since YAML reads a bare `!` as a tag.
- **A check entry** resolves only in a repository that holds the check's module, which in
  practice is Irminsul's own. An adopter decides about a check through its settings, such as
  `checks.external_links.enabled`, never through Irminsul's code.
- **A setting** (decision 1, recommended) is a dotted name the config schema declares, walked
  through `IrminsulConfig.model_fields` as `_changes` in `checks/diff_integrity.py` walks it, so
  a setting resolves whether or not `irminsul.toml` sets it. Under decision 1(b) the entry is
  `irminsul.toml#checks.external_links.ttl_hours`, which resolves only while the file sets the
  key, or the schema field `src/irminsul/config.py#ExternalLinksSettings.ttl_hours` in this
  repository. Under (a), a part of `irminsul.toml` is not accepted, so a setting has one
  spelling.
- **An entry that resolves to nothing** is `adr-structure/unresolved-governs`, certain: a path
  or glob matching no file, a part its file does not define, an unknown component id or check,
  a dotted name the schema lacks.
- **Governance is not total.** A file no record governs reports nothing; `context` says so.
  Many modules, such as `src/irminsul/refs.py` and `src/irminsul/checks/links.py`, have no
  governing record today and need none until someone decides something about them.

### What overlaps, and the check that says so

Every stable record's entries are resolved to items, exclusions applied, and two records
overlap when an item of one meets an item of the other:

- two whole files that are the same file;
- a whole file and a part of it that the first record did not exclude;
- two parts of one file, when one Python part equals the other or is its dotted prefix
  (`Checks` and `Checks.enabled`), or, for a finder that locates lines, when their lines meet;
- two settings, when equal or when one is the other's dotted prefix
  (`checks.external_links` and `checks.external_links.ttl_hours`).

A setting and a path never overlap, since they name different things: the meaning a setting
carries, and the code that implements it. Each overlap is `uniqueness/duplicate-governance`,
certain and not drafts-exempt, reported on the later record by path order and naming both
records, both entries and the item. Only stable records count, so a draft record is checked
for its entries' resolution and joins the overlap rule when it becomes stable. It lives in
`uniqueness` beside `duplicate-claim`, through the same claim matcher the one-claim RFC
builds, so "one doc per file" and "one record per item" are one implementation.

### Finding codes

Each code with its [finding class](../GLOSSARY.md#finding-class) and the answer it declares:

| Code | Class | Answer | Reports |
|---|---|---|---|
| `adr-structure/missing-governs` | certain, drafts-exempt | fix | a stable record with no `governs:` entry (decision 2a) |
| `adr-structure/unresolved-governs` | certain | fix | an entry that resolves to nothing |
| `adr-structure/malformed-changes` | certain | fix | a `## Changes` section that is not the last H2, holds anything but dated list items, or lists dates out of order |
| `uniqueness/duplicate-governance` | certain | fix | an item two stable records govern |
| `diff-integrity/changes-rewritten` | certain | fix | a `## Changes` item at the base that the change removes or alters |
| `diff-integrity/change-unrecorded` | certain | fix | a Decision whose wording changed with no new `## Changes` item (decision 3a) |
| `diff-integrity/decision-rewritten` | **certain** (decision 4a) | trailer | as today; subject the record's path; the suggestion names the in-place edit |
| `diff-integrity/accepted-decision-removed` | certain | **trailer** | as today, and a record stable at the base and not stable now; subject the record's path at the base |

Under decision 3(b) `change-unrecorded` does not exist; under 4(b) `decision-rewritten` stays
a hint declared `trailer`, as the every-hint RFC has it. An edit to Context, Alternatives or
Consequences alone is not flagged, as today: those are the reasoning around a decision, and
`list review --changed` queues each sentence the edit touched. Superseding a record deprecates
it, which `supersession` requires, so it is the same finding as a fold: the superseded record
stops being stable, and a trailer gives the reason.

### The acknowledgement step's sources

- **One source: the `Irminsul-Reviewed` trailers on the change's commits.** The step is the
  every-hint RFC's, which matches a trailer to a finding by code, path and subject and
  reports the accepted finding at info under its own code with the commit and the reason.
- **A decision record is not a source**, added or edited. The excuse the nine tests read today
  goes with them.
- **A `## Changes` line is not a source either.** It stays in the tree, so read as an excuse it
  would answer the same subject in every later change, which is the substring problem the
  record excuse avoided only by counting added records. Testing for lines new in the change
  would be a second source with its own matching. The trailer is the one thing a change
  carries that the tree does not keep.
- **What the run shows.** An accepted finding prints once, at info, in runs that judge the
  change, until it merges. After that the comparison finds nothing, and the reason is reached
  through `irminsul context` from git history.

### `context`

- **Governing records.** `irminsul context <path>` lists, for each input path, every stable
  record with an item in that file: a whole-file item, or each part with its name. JSON gains
  `governing_records`, a list of `{doc_id, path, entry, part}` per input; plain output prints
  `governing record: <id> (<path>)`, with `#<part>` for a part. A path no record governs prints
  `governing record: (none)`. The packet already uses `governed_by`, for the governing claims
  over a path no doc owns (`UnmatchedPath` in `src/irminsul/context.py`), so the records take
  their own key. For `irminsul.toml` under decision 1(a), each setting a trailer names is
  joined to the record that governs it.
- **Sign-offs.** For each input path, the `Irminsul-Reviewed` trailers of the commits that
  changed it, newest first: at most five, with the count of the rest. Each gives the commit,
  its date, the code, the subject and the reason, parsed with the acknowledgement step's
  grammar; a trailer that does not parse is shown as written. JSON gains `sign_offs`.
- **Derived on every call** from one `git log --format=... -- <path>` per input path, so
  [Agents get stateless read-only queries and one written loop](../decisions/agents-get-stateless-read-only-queries-and-one-written-loop.md)
  holds: nothing is stored between calls. `context` still runs no checks.
- **Limit.** A forge's squash merge that joins every commit message into one keeps the earlier
  trailers as text in the body, but git reads a trailer only in the closing block of a message,
  so `context` misses them. A merge commit, a rebase or a fast-forward keeps each commit, and
  its trailers, readable.
- The MCP tool `context_for_path` returns the same JSON. Topic mode is unchanged.

### `## Changes`

- **Where.** An optional H2, the last section of a decision record, after
  `## Consequences`. A record never changed has none.
- **Shape.** Only list items, each opening with an ISO date and a colon,
  `- 2026-11-02: ...`, oldest first, one item per change. An item may wrap in the source; it
  is one change, not one physical line. `adr-structure/malformed-changes` reports any other
  shape.
- **What an item says.** What changed in the Decision, in one sentence, and the RFC it came
  from as a link when there is one. The link is what `rfc-follow-through/adr-missing-rfc-link`
  asks of a resolving record, so the transition's item satisfies it.
- **Never edited once merged.** `diff-integrity/changes-rewritten` compares each item at the
  base with the head, whitespace collapsed and each inline link reduced to its text, through
  the reading `_decision_wording` already applies to a Decision. So rewrapping, retargeting a
  link to a renamed doc, or unlinking an RFC that was folded away is no edit; any changed word
  is. Inserting a new item between old ones fails the date order instead.
- **Required on a Decision edit** (decision 3a): `diff-integrity/change-unrecorded` when the
  Decision wording of a record stable at the base changed and its `## Changes` gained no item.
  The date is the author's; nothing compares it with a commit time.
- **At a reset** no base exists, so items may be pruned or merged there; a folded record's
  items join its target's in date order.

### `change transition` and `new adr`

- **`change transition <rfc> accepted`** refuses a `--resolved-by`, or a frontmatter
  `resolved_by`, that is not a decision record. With `--confirm`, as well as today's edits, it
  appends to that record's `## Changes` an item dated by `src/irminsul/clock.py`,
  `- <date>: Accepted [<RFC title>](<path>).`, creating the section when absent, and prints the
  trailer that will answer the rewritten Decision:
  `Irminsul-Reviewed: diff-integrity/decision-rewritten <record path> reason="..."`. It writes
  no Decision text: what the decision says is the author's, in the same change, and the item's
  sentence may be extended before the change merges. It creates no record.
- It notes, without blocking, when the named record governs no file that a component in the
  RFC's `affects` describes, and lists the records that do.
- **`irminsul new adr "<title>" --governs <entry>`**, repeatable, writes the entries into the
  new record's `governs:`. It refuses an entry that a stable record already covers, exiting 1
  and naming that record, so the author edits it instead, unless `--split-from <record-id>`
  names it: then it prints which entries to remove from that record, as
  `new component --split-from` does for a split doc.
- **The ADR template** gains `governs: []` and drops its sign-off guidance, the dotted name
  with both values, which a trailer now carries.

### The codes that move to trailers

The every-hint RFC makes this switch: its decision 1, revised on 2026-10-29, makes a trailer
the only acknowledgement, and its answers table moves 20 codes from a record to a trailer. Both
RFCs were accepted on 2026-10-29, so the record fallback it kept is gone. They are listed here
so the two RFCs can be checked against each other:

- **Gates and settings:** `check-disabled`, `layer-rule-disabled`, `setting-weakened`,
  `source-excluded`, `extra-doc-removed`, `rules-narrowed`, `unreviewed-setting-change`, the
  new `files-dropped`, and `gate-file-changed`.
- **Files that only shrink:** `baseline-grew` and `adoption-record-removed`.
- **Governance removed or weakened:** `claim-reworded`, `claim-removed`,
  `governing-claim-removed`, `governing-claim-changed`, the new `claim-downgraded`,
  `anchor-removed`, `inventory-removed` and `inventory-weakened`.
- **A sealed record folded away:** `implemented-rfc-removed`.

All are `diff-integrity/` codes. This RFC adds two more answers of its own,
`decision-rewritten` (made certain) and `accepted-decision-removed`, both above. So the
answers are four: fix, line, pin and trailer.

### Interactions with other RFCs

- **`every-warning-hint-has-an-answer`** (accepted 2026-10-29). It defines the acknowledgement
  step, the trailer grammar and the answer each code declares; this RFC builds on them and
  defines none of them again. Its requirement `acknowledgement-step` reads trailers only, and
  it depends on this RFC for that. The dependency runs the other way in code: the owner chose on
  2026-10-29 that its step (its T1, T2 and T7, and T18's trailer for `decision-rewritten`) lands
  before this RFC, since without it a record whose `governs:` must resolve cannot also serve as
  the excuse the nine record tests read, and no Decision edit has an answer. Three of its table
  rows change here:
  - `decision-rewritten`, "a wording correction; a changed decision is superseded", becomes the
    in-place edit with a Changes item, and its class follows decision 4;
  - `accepted-decision-removed`, "fix: deprecate it, then delete it in a later change", becomes
    a trailer, since deprecating is how a record leaves unseen today and is reported as removal
    here;
  - the five-answer fallback it kept for the case that this RFC was rejected is gone, since
    both were accepted.
- **Its acceptance** was written at the second history reset, before either RFC is
  implemented, in the shape this RFC prescribes: each record that governs code it changes
  states the accepted rule, marked as not yet implemented, with a dated item, and no record was
  added. The `mtime-drift` tombstone joins the `retires:` of
  [Finding classes decide what blocks](../decisions/finding-classes-decide-what-blocks.md),
  the record that decides time findings, in the change that deletes the check: a tombstone for
  a check that still runs would report every live mention of it.
- **`a-source-file-has-one-claim`** (accepted 2026-10-29). This RFC applies its rule to records
  and reuses its matcher and its `!` exclusions. Its acceptance is an in-place edit of
  [Docs are atoms in six layers, and code has one owner](../decisions/docs-are-atoms-in-six-layers-and-code-has-one-owner.md),
  which governs `checks/uniqueness.py`: the record states the one-claim rule beside the sentence
  "otherwise the most specific claim wins", which is rewritten when the code changes, and its two
  tombstones join that record's `retires:` in the change that removes the codes.
- **`a-path-is-named-when-git-lists-it`** (accepted 2026-10-29). Its correction of the code-span
  record's "a file on disk" clause is an in-place edit of that record with a dated item, as its
  decision asks.
- **[Claim evidence names a part](claim-evidence-names-a-part.md)** (accepted). Parts in
  `governs:` resolve through its finders once they exist; until then only Python definitions
  resolve, which is all the mapping uses. Its resolving record was folded at the reset, and its
  `resolved_by` names the code-is-named record.
- **[An RFC has an owner's part and an agent's part](an-rfc-has-an-owners-part-and-an-agents-part.md)**
  (accepted). Its record was folded into the RFC-states record at the reset that rewrote the two
  implemented RFCs in the new layout, and its `resolved_by` names that record.

### The 18 records

Paths are under `src/irminsul/` unless they start with a dot or name a root file. `*` marks a
function pulled out of `run_diff_integrity` at the reset, behaviour unchanged, so a record can
name it: `_baseline_ratchet` (the baseline growth test), `_sealed_records` (the sweep for removed
implemented RFCs and accepted records) and `_sealed_rewrites` (the `implemented-rfc-changed` and
`decision-rewritten` tests inside the per-doc loop, which one record decides). Settings follow
decision 1(a). Each row names the entries that decide the area; the reset wrote each list in
full, and the records' own `governs:` are the complete lists.

| Record | Proposed `governs:` | At the reset |
|---|---|---|
| [a-baseline-holds-certain-findings-and-grows-only-by-decision](../decisions/a-baseline-holds-certain-findings-and-grows-only-by-decision.md) | `baseline.py`, `delta.py`, `checks/diff_integrity.py#_baseline_ratchet`*, `#_entries`, `checks/pipeline.py#without_baselined`, `#run_delta`, `#BaselineStatus`, `cli.py#baseline_init`, `#baseline_update`, `#list_baseline`, `paths.baseline` | stays; gains the init record's `--delta` bullet |
| [a-change-is-judged-from-its-merge-base-to-the-working-tree](../decisions/a-change-is-judged-from-its-merge-base-to-the-working-tree.md) | `checks/change_range.py`, `checks/co_change.py`, `git/changes.py`, `docgraph.py#ChangeRange`, `config.py#parse_snapshot`, `checks/diff_integrity.py#_owned_at_ref`, and the acknowledgement step's module once it exists | stays; its pin bullet splits, re-pinning to the code-is-named record and drift skipping to the authority record |
| [a-change-may-not-lower-its-own-gates](../decisions/a-change-may-not-lower-its-own-gates.md) | `checks/diff_integrity.py#run_diff_integrity`, `#_SEALS`, `#_Seal`, `#_config_weakening`, `#_changes`, `#_weakenings`, `#_parsed`, `#_adopting`, `#_changed_gate_files`, `#_is_gate_path` | stays; gains the surface record's `surface.rules` seal bullet; its `paths:` filter bullet moves to the CI record |
| [agents-get-stateless-read-only-queries-and-one-written-loop](../decisions/agents-get-stateless-read-only-queries-and-one-written-loop.md) | `context.py`, `mcp_server.py`, `orient.py`, `regen/**`, `checks/agents_manifest.py`, `checks/external_links.py`, `init/scaffolds/AGENTS.md.j2`, `init/command.py#write_harness_files`, `#agents_block_span`, `#_merge_root_router`, `#_MCP_CONFIG_PATH`, `checks.external_links.cache_path`, `checks.external_links.ttl_hours` | stays; gains the one-command record's MCP and `orient` bullets |
| an-rfc-is-written-for-its-owner-first-and-its-agent-second | `checks/rfc_structure.py`, `new/templates/rfc.md.j2` | **folded** into the RFC-states record |
| a-python-pin-hashes-the-syntax-tree-not-its-printed-form | `anchors.py#_canonical`, `#_hash` | **folded** into the code-is-named record, replacing the anchor sentence it corrects; its bullet on pin-blind Decision wording went to the RFC-states record |
| [authority-follows-the-kind-of-claim](../decisions/authority-follows-the-kind-of-claim.md) | `checks/claim_provenance.py`, `frontmatter.py#Claim`, `checks/diff_integrity.py#_removed_governance`, `#_rewritten_governing_claims`, `#_inventory_weakening`, `#_declared_now`, `listing/review.py#_governing_claims_over_changed_code`, `#_removed_sentences` | stays; gains the claim-evidence record's drift-in-every-layer bullet and the drift half of the merge-base record's pin bullet |
| [ci-runs-each-gate-once-and-the-action-takes-typed-inputs](../decisions/ci-runs-each-gate-once-and-the-action-takes-typed-inputs.md) | `.github/workflows/**`, `action.yml`, `Dockerfile`, `.pre-commit-config.yaml`, `init/workflows/**`, `init/command.py#action_ref` | stays; gains the gates record's `paths:` filter bullet |
| claim-evidence-may-name-a-part-of-a-file | the two rules it deletes, `anchors.py#_resolve_text` and `checks/claim_provenance.py#_is_protected_claim_node` | **folded**: finders and anchors into the code-is-named record, drift in every layer into the authority record |
| [code-is-named-in-code-spans-and-bound-by-anchors](../decisions/code-is-named-in-code-spans-and-bound-by-anchors.md) | `anchors.py`, `binding.py`, `code_references.py`, `checks/code_references.py`, `checks/code_spans.py`, `checks/prose_file_reference.py`, `checks/claim_anchor.py`, and the finders' module | stays; absorbs the Python-pin record and the claim-evidence record's finders |
| [derive-facts-and-leave-meaning-to-the-reader](../decisions/derive-facts-and-leave-meaning-to-the-reader.md) | `listing/review.py`, less the authority and ownership parts, `checks/inventory_drift.py`, `checks/foundation_readiness.py`, `git/blame.py` | stays |
| [docs-are-atoms-in-six-layers-and-code-has-one-owner](../decisions/docs-are-atoms-in-six-layers-and-code-has-one-owner.md) | `frontmatter.py` with `!frontmatter.py#Claim`, `checks/frontmatter.py`, `checks/uniqueness.py`, `checks/orphans.py`, `checks/supersession.py`, `checks/parent_child.py`, `checks/glossary.py`, `adoption.py`, `source_map.py`, `checks/adoption_record.py`, `checks/diff_integrity.py#_owner_changes`, `#_adoption_seal`, `new/command.py#current_owners`, `#split_links`, `listing/review.py#_moved_file_sentences`, `layers`, `paths.docs_root`, `paths.adoption` | stays; its ADR-shape bullet moves to the RFC-states record |
| [finding-classes-decide-what-blocks](../decisions/finding-classes-decide-what-blocks.md) | `checks/base.py`, `checks/pipeline.py#apply_classes`, `#effective_class`, `#class_of`, `#failing_findings`, `#_drafts_exempt`, `checks/ignore_comments.py`, `fix.py`, `source_tree.py`, `checks/dependency_check.py` with `!checks/dependency_check.py#IMPORT_LANGUAGE`, `checks/new_dependency.py`, `cli.py#_failing_classes`, `checks.enabled`, `paths.honor_gitignore`, `paths.source_includes`, `paths.source_excludes` | stays |
| [init-adopts-in-two-layouts-and-seed-fills-two-docs](../decisions/init-adopts-in-two-layouts-and-seed-fills-two-docs.md) | `init/**` with `!init/workflows/**`, `!init/scaffolds/AGENTS.md.j2` and `!` on each harness and CI part of `init/command.py`, `seed/**` | stays; its `--delta` bullet moves to the baseline record |
| [one-command-per-question-and-one-rule-per-flag](../decisions/one-command-per-question-and-one-rule-per-flag.md) | `cli.py#IrminsulGroup`, `#_MOVED`, `#_split_commas`, `#OutputFormat`, `#CheckFormat`, `errors.py`, `checks/pipeline.py#select_checks` | stays; its MCP and `orient` bullets move to the agents record, and its copy of the baseline record's consequence goes |
| rfc-scope-is-judged-by-the-change-commands | `checks/change_binding.py`, `change/gate.py`, which the RFC-states record governs | **folded** into the RFC-states record, with its one `retires:` entry |
| [rfcs-have-four-states-and-git-history-seals-decided-records](../decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md) | `change/**`, `checks/rfc_lifecycle.py`, `checks/rfc_follow_through.py`, `checks/requirement_grammar.py`, `checks/change_binding.py`, `checks/retired_references.py`, `checks/adr_structure.py`, `checks/sections.py`, `new/templates/adr.md.j2`, `new/command.py#_slugify`, `#resolve_destination`, `checks/diff_integrity.py#_sealed_records`*, `#_sealed_rewrites`*, `#_renamed_record`, `#_only_retargeted`, `#_retarget`, `#_decision_wording` | stays; absorbs the RFC-layout and RFC-scope records, the ADR-shape bullet and the pin-blind wording bullet, and its Decision states the living-topic rules |
| [surface-rules-and-language-profiles-are-data](../decisions/surface-rules-and-language-profiles-are-data.md) | `inventory/**`, `surface.py`, `languages/**`, `checks/dependency_check.py#IMPORT_LANGUAGE`, `surface.rules`, `frameworks`, `languages.enabled` | stays; its `surface.rules` seal bullet moves to the gates record |

18 records become 14. Of the four that fold, only the RFC-scope record declares `retires:`; its
one entry, `diff-wide-rfc-scope`, moves unchanged to the RFC-states record.

### Areas two records decided

Fourteen areas were decided by two or more records, read from their `## Decision` sections. The
overlap check would report each of them once the records list what they govern, and each
resolves by part or by moving a bullet to the record that governs the code:

| Area | Decided by | Resolves as |
|---|---|---|
| `checks/diff_integrity.py` | eight: gates, baseline, authority, RFC states, atoms, merge base, surface rules, Python pin | one record per function, after the three `*` functions are pulled out; the implementer checks what stays inline in `run_diff_integrity`, such as the adoption seal's two source maps, and pulls out any rule a second record decides |
| pins: `anchors.py`, `checks/claim_provenance.py` | merge base (a pin answers drift), authority (only a person re-pins), code-is-named, Python pin, claim evidence | code-is-named governs writing and hashing a pin, authority governs judging drift |
| `init/workflows/**` | gates (no `paths:` filter), CI (each calls the Action), init (`init/**`) | CI; init excludes it |
| harness wiring in `init/` | agents (the loop's section, `.mcp.json`, the pointer files), init | agents, by part; init excludes those parts |
| `delta.py` | baseline (`--delta` asks the same question), init (`--delta` refuses another repository's tree) | baseline |
| `checks/pipeline.py` | finding classes, baseline (what a run hides), one command (`--only`) | by part |
| `listing/review.py` | derive facts (the queue), authority (claims over changed code, removed sentences), atoms (an old owner's sentences) | derive facts, less the parts the other two govern |
| `mcp_server.py`, `orient.py` | agents, one command (MCP follows the CLI, `orient` teaches the loop) | agents |
| `checks/dependency_check.py` | finding classes (contradiction, not completeness), surface rules (`IMPORT_LANGUAGE`) | by part |
| record shape: `checks/adr_structure.py`, `checks/sections.py` | atoms (ADRs have a fixed shape), RFC states, RFC layout (the shared section reader) | RFC states |
| `frontmatter.py` | atoms (validated frontmatter), authority (a claim's `relation`) | atoms, less `Claim` |
| `new/command.py` | atoms (`--split-from`), RFC states (records named by slug) | by part |
| the baseline commands in `cli.py` | baseline, one command, whose Consequences repeat one sentence word for word | baseline; the copy goes |
| RFC scope: `checks/change_binding.py`, `change/gate.py` | RFC states (`change/**`), RFC scope (`check --diff` leaves it to the change commands) | RFC states, which absorbs the RFC-scope record |

The repeated sentence, "`baseline update` cannot be narrowed, so it removes the entries of a
check taken out of `checks.enabled`", was in both records' Consequences. `duplicate-block` does
not read decision records, so nothing reported it.

### The reset

The owner chose the order on 2026-10-29: the second history reset carries the records' new
shape, and the changes that implement this RFC land on `main` after it. In the tree of that
reset, before its commit:

1. Pull `_baseline_ratchet`, `_sealed_records` and `_sealed_rewrites` out of
   `run_diff_integrity`, a pure move with the full suite green, so the lists can name them.
2. Fold the Python-pin record into the code-is-named record: its Decision bullets replace the
   anchor sentence they correct, its Context, Alternatives and Consequences join, its pin-blind
   wording bullet goes to the RFC-states record, and the code-is-named record gains
   `- 2026-10-28: A Python pin hashes a canonical text of the syntax tree, not its ast.unparse.`
   Delete the file.
3. Fold the claim-evidence record: finder and anchor bullets into the code-is-named record, the
   drift-in-every-layer bullet into the authority record, each marked as not yet implemented and
   with a dated item linking the RFC; that RFC's `resolved_by` becomes the code-is-named record.
   Delete the file.
4. Fold the RFC-layout record into the RFC-states record with a dated item linking its RFC,
   retarget that RFC's `resolved_by`, and delete the file.
5. Fold the RFC-scope record into the RFC-states record, which governs `change/**` and
   `checks/change_binding.py`, with a dated item and its `retires:` entry, and delete the file.
6. Move each bullet the two tables name to the record that governs its code; a moved bullet is
   not a change of decision and takes no item.
7. Write each record's `governs:` in full. With the folding records gone in the same tree, no
   temporary exclusion is needed. An entry that starts with `!` is quoted, since YAML reads a
   bare `!` as a tag.
8. List the `Irminsul-Reviewed` trailers in the history being squashed and copy into the
   governing record's `## Changes` any that explains a choice still in force. The eight since
   the first reset are `co-change` re-reads, so none qualifies.
9. Accept this RFC and the three accepted with it, each into the records that govern what it
   changes, with a dated item, and no new record.
10. Retarget every link to a deleted record, found with `irminsul refs <record>` and a search of
    frontmatter, the CHANGELOG and the backlog, including the links in implemented RFCs, which
    no seal guards in a tree with no base.
11. Run `irminsul check --fail-on hint,time`. The reset commit has no base, so no `--diff` seal
    applies to it.

Until the implementation lands, nothing reads `governs:` or `## Changes`: the codes above do not
exist yet, `decision-rewritten` is still a hint, and a decision record a change adds is still
the excuse `diff-integrity` accepts. The change that enables `missing-governs` and
`duplicate-governance` finds every list resolving with no overlap, as a script found at the
reset, so it needs no temporary exclusion.

### Docs this changes

- `docs/decisions/INDEX.md`: "Decisions are not rewritten in place" and its periodic
  consolidation into themed records become the living-topic rule with `## Changes`, and "Write
  the smallest record that is reviewable", which describes a sign-off record, is rewritten for
  a topic record, since a sign-off is now a trailer. Its fourth rule, about the record excuse,
  is the every-hint RFC's to change. The RFC-states record's bullet "Settled records are
  consolidated" changes the same way: an implemented or rejected RFC folds into the record that
  governs what it changed. The second history reset rewrote the first rule and that bullet,
  since its records already take the new shape; the other two rules change with the code.
- `src/irminsul/init/scaffolds/docs/decisions/INDEX.md.j2`: its summary and its
  "Append-only — never edit a past decision; supersede it with a new one".
- `src/irminsul/init/scaffolds/docs/decisions/adopt-irminsul.md.j2` gains
  `governs: [irminsul.toml]`, which the CHANGELOG also tells an upgrader to add to their copy.
- `src/irminsul/new/templates/adr.md.j2`, as above.
- The managed section of the root `AGENTS.md` and `src/irminsul/init/scaffolds/AGENTS.md.j2`,
  which a test keeps equal: step 2 reads "the decision record that governs each path" in place
  of "the decision records they link".
- `docs/guides/agent-protocol.md` and its scaffold: "Resolve an accepted RFC with an ADR"
  becomes "in the record that governs what it changes", and "Supersede deliberately" says a
  decision record is edited, not superseded.
- `docs/components/change.md` (the transition's item; its claim
  `transition-applies-human-decisions` is reworded), `docs/components/context.md`,
  `docs/components/frontmatter.md`, `docs/components/checks.md` and
  `docs/components/new-list-regen.md`.
- The record excuse's sentences in `docs/components/config.md`, `docs/components/baseline.md`
  and the root `AGENTS.md` are the every-hint RFC's.

### Implementation answers

The owner answered on 2026-10-29 what an independent review of the implementation plan found
the spec leaves open:

- **A bare entry** is a setting when the config schema declares that dotted name, and a path
  otherwise; an entry holding `/`, `#` or a glob character is always a path.
- **`governs:` on a doc outside the decisions layer** is reported, not ignored, since a key that
  does nothing reads as if it works.
- **The sign-offs `context` lists** for a path are the trailers that name that path or its owning
  doc, not every trailer of every commit that touched it.
- **`new adr --split-from`** is repeatable, as `new component`'s is.
- **`new adr` refuses an entry that resolves to nothing**, so a new record never starts with a
  certain `unresolved-governs`.
- **Sign-offs do not follow renames**: a renamed file's earlier trailers are listed under its old
  path only. A limitation.

### Not chosen, and out of scope

- **A folder for sign-off records.** Still a file per change, and the same orphaned file once
  the change merges.
- **Sealing records and superseding them.** It produced the correction record, and a chain of
  superseded records spreads one area over several files.
- **A `## Changes` line as the acknowledgement.** See the acknowledgement step's sources.
- **Most-specific record wins.** The tie-break the one-claim RFC deletes for docs.
- **Governing every file.** A floor like `uniqueness/undocumented-file` would demand a record
  for code nobody has decided anything about.
- **Judging Context, Alternatives and Consequences.** They change with the reasoning; review
  reads them.
- Out of scope: RFCs, whose sealing and folding stay as they are; a record per adopter
  setting, which stays the trailer's job.

## Requirements

Written for the recommended answers. Under 2(b) `missing-governs` goes, under 3(b) the
requirement `a-decision-edit-adds-a-changes-item` goes, under 4(b) `decision-rewritten` stays a
hint, and under 1(b) the setting scenarios name the setting as a part of a file.

### Requirement: A decision record declares what it governs
ID: a-record-declares-what-it-governs
Provenance: code

`adr-structure` SHALL report `adr-structure/missing-governs` for a stable decision record with
no `governs:` entry, and `adr-structure/unresolved-governs` for each entry of a decision record
that resolves to no file, part, component, check or setting.

#### Scenario: No list
- **WHEN** a stable decision record has no `governs:` field
- **THEN** the run reports `adr-structure/missing-governs` for it

#### Scenario: A part that is not defined
- **WHEN** a record lists `src/irminsul/checks/diff_integrity.py#_SEAL` and that file defines no `_SEAL`
- **THEN** the run reports `adr-structure/unresolved-governs` naming that entry

#### Scenario: A setting left at its default
- **WHEN** a record lists `checks.external_links.ttl_hours` and `irminsul.toml` does not set it
- **THEN** the entry resolves, and nothing is reported for it

### Requirement: One record governs each item
ID: one-record-governs-each-item
Provenance: code

`uniqueness` SHALL report `uniqueness/duplicate-governance` for each file, part or setting
that items of two or more stable decision records cover, after each record's exclusions,
naming both records and both entries, and SHALL NOT report two parts of one file that do not
overlap.

#### Scenario: A part inside a governed file
- **WHEN** one record lists `src/irminsul/checks/diff_integrity.py` and another lists `src/irminsul/checks/diff_integrity.py#_baseline_ratchet`
- **THEN** the run reports `uniqueness/duplicate-governance` for `_baseline_ratchet`, naming both records

#### Scenario: Two parts of one file
- **WHEN** one record lists `src/irminsul/checks/diff_integrity.py#_SEALS` and another lists `src/irminsul/checks/diff_integrity.py#_baseline_ratchet`
- **THEN** the run reports no `uniqueness/duplicate-governance`

#### Scenario: A carved-out part
- **WHEN** the record that lists the whole file also lists `!src/irminsul/checks/diff_integrity.py#_baseline_ratchet`
- **THEN** no overlap is reported for that part

#### Scenario: A table and its setting
- **WHEN** one record lists `checks.external_links` and another lists `checks.external_links.ttl_hours`
- **THEN** the run reports `uniqueness/duplicate-governance` for `checks.external_links.ttl_hours`

### Requirement: Context names the governing record
ID: context-names-the-governing-record
Provenance: code

`irminsul context <path>` SHALL list, for each input path, every stable decision record with
an item in that file, with the entry and, for a part, its name, in plain and JSON output, and
SHALL say when no record governs the path.

#### Scenario: A file split by part
- **WHEN** `irminsul context src/irminsul/checks/diff_integrity.py` runs on a tree whose records govern that file's functions
- **THEN** the packet lists each of those records with the part it governs

#### Scenario: An ungoverned file
- **WHEN** no record governs `src/irminsul/refs.py` and `irminsul context src/irminsul/refs.py` runs
- **THEN** the packet says no record governs it, and the command exits 0

### Requirement: Context lists the sign-offs on a path
ID: context-lists-sign-offs
Provenance: code

`irminsul context <path>` SHALL list the `Irminsul-Reviewed` trailers of the commits that
changed each input path, newest first, at most five with the count of the rest, each with its
commit, date, code, subject and reason, read from git history on every call.

#### Scenario: A setting raised last week
- **WHEN** a commit that raised `checks.external_links.ttl_hours` carried a trailer naming `diff-integrity/setting-weakened`, `irminsul.toml` and that setting, and `irminsul context irminsul.toml` runs
- **THEN** the packet lists that trailer with its commit and reason, and names the record that governs the setting

#### Scenario: Seven sign-offs on one file
- **WHEN** seven commits that changed `docs/components/checks.md` each carried a trailer
- **THEN** the packet lists the newest five and says two more exist

### Requirement: A rewritten decision is signed off
ID: a-rewritten-decision-is-signed-off
Provenance: code

`diff-integrity/decision-rewritten` SHALL be certain, its subject the record's path, SHALL be
accepted by a trailer naming that code and path, and its suggestion SHALL name the in-place
edit, the dated Changes item and the trailer rather than a superseding record.

#### Scenario: An edit with no trailer
- **WHEN** a change rewrites a bullet of the Decision of `docs/decisions/finding-classes-decide-what-blocks.md`, adds a dated Changes item, and no commit carries a trailer for it
- **THEN** the run reports `diff-integrity/decision-rewritten` as an error

#### Scenario: The same edit, signed off
- **WHEN** a commit of that change carries `Irminsul-Reviewed: diff-integrity/decision-rewritten docs/decisions/finding-classes-decide-what-blocks.md reason="drafts stop failing the hint gate"`
- **THEN** the finding is reported at info under its own code, quoting that reason

### Requirement: Changes items are dated, ordered and kept
ID: changes-items-are-dated-and-kept
Provenance: code

`adr-structure` SHALL report `adr-structure/malformed-changes` for a decision record's
`## Changes` that is not its last H2, holds anything but list items each opening with a
`YYYY-MM-DD:` date, or lists its dates out of order; and `diff-integrity` SHALL report
`diff-integrity/changes-rewritten` for each item of a record's `## Changes` at the base that the
change removes or alters, compared with whitespace collapsed and each inline link reduced to
its text.

#### Scenario: An undated item
- **WHEN** a record's `## Changes` holds the item `- Raised the cache lifetime.`
- **THEN** the run reports `adr-structure/malformed-changes` on that line

#### Scenario: An old item reworded
- **WHEN** a change alters one word of an item that the record's `## Changes` held at the base
- **THEN** the run reports `diff-integrity/changes-rewritten` for it

#### Scenario: A folded RFC unlinked
- **WHEN** a change deletes an RFC and reduces an item's link to that RFC to the link's text
- **THEN** no `diff-integrity/changes-rewritten` is reported for that item

### Requirement: A Decision edit adds a Changes item
ID: a-decision-edit-adds-a-changes-item
Provenance: code

`diff-integrity` SHALL report `diff-integrity/change-unrecorded`, certain, for a decision
record stable at the base whose Decision wording changed while its `## Changes` gained no item.

#### Scenario: An edit with no item
- **WHEN** a change rewrites the Decision of a stable record and leaves its `## Changes` as it was
- **THEN** the run reports `diff-integrity/change-unrecorded` for that record

#### Scenario: An edit with its item
- **WHEN** the same change also appends `- 2026-11-02: ...` to that record's `## Changes`
- **THEN** no `diff-integrity/change-unrecorded` is reported

### Requirement: Removing or demoting a record is signed off
ID: removing-a-record-is-signed-off
Provenance: code

`diff-integrity/accepted-decision-removed` SHALL be reported for a decision record stable at the
base that the change deletes, unless another record holds its text, or leaves with any status
other than stable, and SHALL be accepted by a trailer naming that code and the record's path at
the base.

#### Scenario: A fold with its trailer
- **WHEN** a change folds a stable record into another and deletes it, and a commit carries `Irminsul-Reviewed: diff-integrity/accepted-decision-removed <that record's path> reason="..."`
- **THEN** the finding is reported at info under its own code

#### Scenario: A record set to deprecated
- **WHEN** a change sets a stable record's status to `deprecated` and no commit carries a trailer for it
- **THEN** the run reports `diff-integrity/accepted-decision-removed` as an error

### Requirement: Acceptance writes into the governing record
ID: acceptance-writes-into-the-governing-record
Provenance: code

`change transition <rfc> accepted` SHALL refuse a `resolved_by` that names no decision record,
SHALL append to that record's `## Changes` an item dated today that links the RFC, creating the
section when it is absent, SHALL print the trailer that answers the record's rewritten
Decision, and SHALL create no record.

#### Scenario: Accepting into an existing record
- **WHEN** `irminsul change transition decision-records-govern-what-they-decide accepted --resolved-by docs/decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md --confirm` runs on 2026-11-02
- **THEN** that record's `## Changes` ends with an item opening `2026-11-02:` that links the RFC, and `rfc-follow-through/adr-missing-rfc-link` is not reported for it

#### Scenario: A component doc named as the record
- **WHEN** the same transition runs with `--resolved-by docs/components/checks.md`
- **THEN** it refuses, saying `resolved_by` must name a decision record, and writes nothing

### Requirement: A new record governs something new
ID: a-new-record-governs-something-new
Provenance: code

`irminsul new adr` SHALL write each `--governs` entry into the new record's `governs:`, and
SHALL refuse, exiting 1 and naming the record, an entry that a stable record already covers,
unless `--split-from` names that record.

#### Scenario: An area already governed
- **WHEN** `irminsul new adr "Cache unreachable links" --governs checks.external_links.ttl_hours` runs while the agents record governs that setting
- **THEN** it exits 1, names `agents-get-stateless-read-only-queries-and-one-written-loop`, and writes nothing

#### Scenario: A new component
- **WHEN** the same command names `--governs src/irminsul/export/**`, which no record covers
- **THEN** it writes the record with that entry in its `governs:`

## Tasks

- `T1` Add `governs:` to the frontmatter schema, resolve its entries through the anchor
  resolver, the component and check registries and the config schema walk, and report
  `missing-governs` and `unresolved-governs`. (req: a-record-declares-what-it-governs)
- `T2` Done at the second history reset: `_baseline_ratchet`, `_sealed_records` and
  `_sealed_rewrites` were pulled out of `run_diff_integrity`, behaviour unchanged and shown by
  the existing tests. (req: one-record-governs-each-item)
- `T3` Report `uniqueness/duplicate-governance` through the matcher the one-claim RFC builds
  for `describes:`, with `!` exclusions on files and parts, a fixture and its green case.
  (req: one-record-governs-each-item)
- `T4` List the governing records in the `context` packet, its JSON and the MCP tool.
  (req: context-names-the-governing-record)
- `T5` List each path's trailers in the `context` packet from one `git log` per path.
  (req: context-lists-sign-offs)
- `T6` Make `decision-rewritten` certain, declare it `trailer` with the record's path as its
  subject, and rewrite its suggestion. (req: a-rewritten-decision-is-signed-off)
- `T7` Add `malformed-changes` and `changes-rewritten`, reading items through the reading
  `_decision_wording` applies. (req: changes-items-are-dated-and-kept)
- `T8` Add `change-unrecorded`. (req: a-decision-edit-adds-a-changes-item)
- `T9` Report a record that stops being stable as `accepted-decision-removed`, and declare that
  code `trailer`. (req: removing-a-record-is-signed-off)
- `T10` Make `change transition` refuse a `resolved_by` outside the decisions layer, append the
  dated item and print the trailer. (req: acceptance-writes-into-the-governing-record)
- `T11` Add `--governs` and `--split-from` to `new adr`, and give the ADR template and the
  scaffolded adoption record their `governs:`. (req: a-new-record-governs-something-new)
- `T12` Update the decisions index's remaining rules, its scaffold, the agent loop's step 2
  with its template, the agent protocol with its scaffold, and the component docs listed above;
  the records' `governs:` were written at the second history reset.
  (req: a-record-declares-what-it-governs)
- `T13` Done at the second history reset: the four records folded, the bullets the two tables
  name moved, each list written in full, and links and `resolved_by` retargeted.
  (req: one-record-governs-each-item)

## Resolution

Accepted by the owner on 2026-10-29, with the answers recorded under Decisions, at the second
history reset, which carries the records' new shape before the code: every record's `governs:`
is written in full and four records are folded, as The reset describes. It is resolved by
[RFCs have four states, and git history seals decided records](../decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md), which states the living-topic rules as accepted and not yet implemented. [Docs are atoms in six layers, and code has one owner](../decisions/docs-are-atoms-in-six-layers-and-code-has-one-owner.md) holds
the rule that one record governs each item, and [Agents get stateless read-only queries and one written loop](../decisions/agents-get-stateless-read-only-queries-and-one-written-loop.md) the `context` packet's governing
records and sign-offs, each with a dated item under its Changes.
