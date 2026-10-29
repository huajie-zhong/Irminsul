---
id: adoption-record
title: "Adoption record"
status: stable
summary: The files that had no owning doc on the day of adoption, excepted from the ownership finding; it only shrinks.
depends_on:
  - checks
  - config
  - docgraph
  - file-writing
  - user-errors
describes:
  - "src/irminsul/adoption.py"
  - "src/irminsul/source_map.py"
owns_tests:
  - "tests/test_adoption.py"
  - "tests/test_adoption_siblings.py"
  - "tests/test_adoption_validation_contract.py"
  - "tests/test_source_map.py"
claims:
  - id: adoption-is-not-a-mode
    state: implemented
    kind: invariant
    relation: governs-evidence
    claim: An adoption record excepts the files it names from the ownership finding and changes nothing else; no check is disabled while it exists, and none is enabled when it empties.
    evidence:
      - src/irminsul/adoption.py
      - src/irminsul/checks/uniqueness.py
      - src/irminsul/checks/owned_tests.py
    pinned:
      src/irminsul/adoption.py: sha256:172d868df4d6
      src/irminsul/checks/uniqueness.py: sha256:a650805acc40
      src/irminsul/checks/owned_tests.py: sha256:343c7c090f6d
  - id: adoption-record-only-shrinks
    state: implemented
    kind: invariant
    relation: governs-evidence
    claim: Only the change that creates an adoption record may write entries into it, and only for paths the base of the diff already held; afterwards it loses entries and never gains one.
    evidence:
      - src/irminsul/adoption.py
      - src/irminsul/checks/diff_integrity.py
    pinned:
      src/irminsul/adoption.py: sha256:172d868df4d6
      src/irminsul/checks/diff_integrity.py: sha256:8a5edf622f76
  - id: adoption-exception-does-not-return
    state: implemented
    kind: invariant
    relation: governs-evidence
    claim: A recorded file that had an owning doc at the base of the diff is governed normally at the head, whether or not anyone took its path out of the record; whether it had one is judged by the configuration at the base, so widening a root at the head cannot retract an owner the base had.
    evidence:
      - src/irminsul/checks/diff_integrity.py
    pinned:
      src/irminsul/checks/diff_integrity.py: sha256:8a5edf622f76
  - id: cross-repo-debt-is-pinned
    state: implemented
    kind: invariant
    relation: governs-evidence
    claim: Every entry from a root in another git repository is checked against the revision the record pins for that root, on every run; a pin that is missing or unreadable, a root that is not checked out, and a file that was not there each fail the run on a certain finding naming them, rather than being accepted in silence.
    evidence:
      - src/irminsul/adoption.py
      - src/irminsul/checks/uniqueness.py
      - src/irminsul/checks/adoption_record.py
    pinned:
      src/irminsul/adoption.py: sha256:172d868df4d6
      src/irminsul/checks/uniqueness.py: sha256:a650805acc40
      src/irminsul/checks/adoption_record.py: sha256:210962a2c53c
  - id: adopting-obligations-are-complete
    state: implemented
    kind: invariant
    relation: governs-evidence
    claim: The change that creates an adoption record must satisfy every obligation enumerated under "What the adopting change must prove", and that list is the complete set; a rule added to the adopting path without being added there is a rule the next reader will not find.
    evidence:
      - src/irminsul/checks/diff_integrity.py
    pinned:
      src/irminsul/checks/diff_integrity.py: sha256:8a5edf622f76
  - id: record-validity-is-asked-on-every-path
    state: implemented
    kind: invariant
    relation: governs-evidence
    claim: Every execution path that returns findings runs the pass that validates the adoption record, so a check may delegate reporting an unreadable or unverifiable record only because the calling path guarantees the reporter runs.
    evidence:
      - src/irminsul/checks/pipeline.py
      - src/irminsul/context.py
      - src/irminsul/mcp_server.py
    pinned:
      src/irminsul/checks/pipeline.py: sha256:48c24ad125b0
      src/irminsul/context.py: sha256:dd662a46a12a
      src/irminsul/mcp_server.py: sha256:d5097f13b089
---

# Adoption record

Turning ownership on over an existing repository would report every undocumented file at
once, so both ownership rules guess from the shape of the tree whether a file was already
there (the module docstring of `src/irminsul/adoption.py` describes the guess).
`irminsul adoption init` records the answer instead: every managed file with no owning
document today, by exact path, in the file `paths.adoption` names. Only those files are
excepted from the finding that says a file has no owner.

## It is a list of exceptions, not a mode

The record excepts the files it names from the ownership finding and changes nothing else:
no check is switched off while it exists, and none is switched on when it empties.
<!-- claim:adoption-is-not-a-mode --> A recorded file that two documents both claim is still
a duplicate claim, and a file that gains an owner is governed normally from that moment.

## Why the baseline could not do this

A [baseline](baseline.md) records findings, and on the day of adoption the findings this
record has to except do not exist: no document claims anything, so no directory is
covered, so the omission finding fires on nothing. They appear when the first component
document makes their directory covered, and by then they are new findings, which a baseline
is forbidden to absorb. So the record is built from the configured walk, not from findings.

## The lifecycle of one exception

Only the change that creates the record may write entries into it, and only for paths the
merge base already held; afterwards it loses entries and never gains one.
<!-- claim:adoption-record-only-shrinks --> An entry retires when its file gains an owner, is
deleted or is moved, and `diff-integrity` fails a change that grows the record
(`adoption-record-grew`) or edits a recorded file without giving it an owner
(`adoption-debt-touched`).

A rename is a new file, so the new path needs an owner in the change that moved it, and the
adopting change is no exception: the debt did exist under the old name, but adoption
tolerates debt nobody has gone back to, and moving a file is going back to it. Carrying an
exception across a move would let a repository rename its way out of ever documenting
anything. The remedy is to adopt, then move.

## Retirement is read from the base, not from the record

Nobody has to run `irminsul adoption update`, so a live record usually goes on naming files
that have since been documented, and asking only whether it names a path would hand the
exception back the moment such a file lost its owner. So a recorded file that had an owning
doc at the merge base is governed normally at the head whatever the record still says.
<!-- claim:adoption-exception-does-not-return --> Adding an owner and removing it again inside
one pull request is not that case: the base never documented the file.

"Had an owning doc at the merge base" is read with the **configuration at the merge base**,
because ownership is a declaration plus the rule that accepts it. Read through the head's
configuration, a change could delete an owner and, in the same commit, widen
`paths.source_roots`, which decides whether a test-root file answers to the test policy; the
retired exception would come back with nothing reporting it, since widening a root is not a
weakening. So a base whose `irminsul.toml` does not load, while the record holds entries, is
`diff-integrity/adoption-base-unreadable` rather than a quiet fallback to the head's rules.

This is a property of the pull-request gate, and only of it. A plain `irminsul check` has
no base to compare against, so it reads the record as written — which is why the
comparison run, `check --diff origin/<base>`, is the one CI enforces.

### What the adopting change must prove

The adopting change's base holds no record, so there is no ratchet to widen, but each entry
still claims its file was already unowned on the day of adoption, and git can check that.
This list is the authoritative and complete set of rules checked on that change; a rule
added to the adopting path belongs in it in the same change.
<!-- claim:adopting-obligations-are-complete -->

1. **Each entry was in this repository at the merge base**, at the path the record names,
   not at a path the change moved it from (`adoption-debt-not-historical`).
2. **Each entry from another repository was in that repository at the pinned revision**, and
   the pin is the full object id of a commit that repository holds
   (`adoption-record/debt-not-at-source-revision`, `adoption-record/source-unverifiable`).
3. **No entry is a file this change edited, moved or deleted** (`adoption-debt-touched`).
4. **No entry had an owning document at the merge base that this change removes**
   (`adoption-exception-revived`); every other rule passes such a change honestly.
5. **No entry has an owning document at the head** (`adoption-debt-already-owned`): it buys
   nothing today and becomes live the day that owner goes.
6. **Each pinned source's revision is on the history that source declares**
   (`adoption-pin-not-on-ref`), because pushing a branch needs no review. Asked of the
   adopting change only: afterwards the pin cannot move.
7. **Each entry matches a path the configured walk produces** (`adoption-debt-not-managed`),
   asked only when every configured root is present.

Afterwards the record may not gain an entry, its pins may not move, and it may not be
deleted while it holds entries. Two things are re-asked on every run, because they are about
the record as it stands: each entry existed in its source at the pinned revision, and the
source an entry states is the one the configured roots resolve it to.

### The boundary, and what it does not advance with

For an entry from another repository the boundary is a commit, recorded once: the **merge
base of the source checkout and the ref that source declares** — not the checkout's `HEAD`,
which on a side branch is a commit the declared history never had, and not the ref's tip,
which the checkout may not have reached. That settles the cutoff in both directions. A file
merged to the declared history before adoption **is** eligible: that is the approved
snapshot being adopted, and merging is the act the source repository reviews. A file merged
after is not, because the pin is a fixed point, and the source repository going on with its
life is exactly what the record may not absorb.

## When the code is a different repository

In the [`siblings` layout](../guides/private-docs.md) the source roots reach into a
repository whose files this repository's history never contained, so the record states the
boundary instead of deriving it: each such entry names its declared `[[paths.sources]]`
entry, and the record pins one revision per source, in the shape `parse_record` describes.

Every entry from a root in another git repository is checked, on every run, against the
revision the record pins for that root, and a pin that is missing or unreadable, a root that
is not checked out, and a file that was not there each fail the run on a certain finding
naming them rather than being accepted in silence. <!-- claim:cross-repo-debt-is-pinned -->
A pin needs no merge base, so a plain `check` asks as the pull-request gate does. An entry
nobody can verify goes on excepting its file, since calling it new would assert the opposite
of what could not be checked: what is refused is the silence, not the exception. So the
source repository has to be *present* when the gate runs, which in CI means checking it out
beside this one with its full history; the [`siblings` workflows](init.md) do that.

`uniqueness` and `test-ownership` say nothing about a record they cannot trust, and may stay
silent only because every path that reaches a verdict — `irminsul check`, `context
--after-edit`, the MCP `check` tool and the `change` gates — runs the checks through
`run_checks`, which runs the `adoption-record` pass whatever `checks.enabled` names
([checks](checks.md)). <!-- claim:record-validity-is-asked-on-every-path -->

## Where an entry is verified, decided once

An entry is bound to whichever root the managed walk resolves its display to, so `SourceMap`
(`src/irminsul/source_map.py`) resolves every display to a `(repository, revision)` pair once
per snapshot, and every rule that judges an entry reads it. The pull-request gate builds a
map for each side, and an entry in both records must have the same pair in both, which
catches a pin moved under an unchanged name and a root replaced under an unchanged pin.

## What the boundary does not prove

None of this establishes that the adoption boundary was *reviewed*. Git proves a path
existed at a revision, not that anybody agreed to the record that named it; that comes from
a protected branch and a required gate — repository settings, not this tool.

The pinned revision is likewise a string somebody wrote, and narrower than proof: it is
checkable, so a later change cannot add an entry and call it history; immutable, so the
boundary cannot be walked forward; and *stated*, so the reviewer of the adoption pull
request sees the exact revision being adopted rather than an implicit "now". It cannot show
that the revision deserved to be the boundary: adoption at a source `HEAD` that just gained a
file records that file as debt, and only the review of the adopting commit can tell that
apart from a `HEAD` that had sat there for a year.

## Scope & Limitations

The record does not decide which rule governs a file — that is the test-path question,
and recording a path never moves a file between the source and test policies. It holds
exact paths only, never a glob or a directory, because a pattern would adopt files
written next year. Its readers ask it different things: the two ownership rules which files
to except, `adoption-record` whether it can be trusted to except anything, and
`diff-integrity` how it differs from its content at the merge base. No *other* check
consults it, and a run that excepted files says so in its output rather than letting an exit
code of zero read as proof that every file is documented.

Nothing here judges whether a documented file is documented well. An owner retires an
exception the moment it exists; whether its prose is worth reading is the same question
it is everywhere else in this tree.
