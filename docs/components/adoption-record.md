---
id: adoption-record
title: "Adoption record"
status: stable
summary: The finite list of managed files that had no owning doc when an existing repository adopted Irminsul; it excepts those files from the ownership finding, only shrinks, switches nothing on or off, cannot except a file the base of the diff already documented, and pins the revision of any source repository whose files it names.
depends_on:
  - checks
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
  - id: adoption-record-only-shrinks
    state: implemented
    kind: invariant
    relation: governs-evidence
    claim: Only the change that creates an adoption record may write entries into it, and only for paths the base of the diff already held; afterwards it loses entries and never gains one.
    evidence:
      - src/irminsul/adoption.py
      - src/irminsul/checks/diff_integrity.py
  - id: adoption-exception-does-not-return
    state: implemented
    kind: invariant
    relation: governs-evidence
    claim: A recorded file that had an owning doc at the base of the diff is governed normally at the head, whether or not anyone took its path out of the record; whether it had one is judged by the configuration at the base, so widening a root at the head cannot retract an owner the base had.
    evidence:
      - src/irminsul/checks/diff_integrity.py
  - id: cross-repo-debt-is-pinned
    state: implemented
    kind: invariant
    relation: governs-evidence
    claim: Every entry from a root in another git repository is checked against the revision the record pins for that root, on every run; a pin that is missing or unreadable, a root that is not checked out, and a file that was not there each fail the run on a certain finding naming them, rather than being accepted in silence.
    evidence:
      - src/irminsul/adoption.py
      - src/irminsul/checks/uniqueness.py
  - id: adopting-obligations-are-complete
    state: implemented
    kind: invariant
    relation: governs-evidence
    claim: The change that creates an adoption record must satisfy every obligation enumerated under "What the adopting change must prove", and that list is the complete set; a rule added to the adopting path without being added there is a rule the next reader will not find.
    evidence:
      - src/irminsul/checks/diff_integrity.py
  - id: record-validity-is-asked-on-every-path
    state: implemented
    kind: invariant
    relation: governs-evidence
    claim: Every execution path that returns findings runs the pass that validates the adoption record, so a check may delegate reporting an unreadable or unverifiable record only because the calling path guarantees the reporter runs.
    evidence:
      - src/irminsul/checks/pipeline.py
      - src/irminsul/context.py
      - src/irminsul/mcp_server.py
---

# Adoption record

An existing repository has code nobody has documented yet. Turning ownership on over it
would report every file at once, so both ownership rules carry a progressive half:
[uniqueness](checks.md) reports an unowned source file only inside a directory that
already holds claimed code, and test ownership reports an unowned test only beside one
already owned. Both are guesses at the same question — was this file already here? —
answered from the shape of the tree, because nothing had recorded the answer.

This component records the answer. `irminsul check --init-adoption` writes every managed
file that has no owning document today into the record named by `paths.adoption`, by
exact repository-relative path. Those files, and only those, are excepted from the
finding that says a file has no owner.

## It is a list of exceptions, not a mode

Nothing is switched off while a record exists, and nothing is switched on when it
empties. Every check runs from the first day, the excepted files included: a recorded
file that two documents both claim is still a duplicate claim, and a recorded test named
under a document's `owns_tests:` is still judged by the test rule. The record suppresses
one finding per named path, and that is its whole effect.

A file that gains an owner is governed normally from that moment, in the same run. There
is no second activation step and no proportion of the tree to reach first. When the last
entry retires every managed file has an owner and the record can be deleted; nothing
about the run changes when it goes.

## Why the baseline could not do this

A [baseline](baseline.md) records findings, and on the day of adoption the findings this
record has to except do not exist: no document claims anything, so no directory is
covered, so the omission finding fires on nothing. A baseline written then records
nothing about the undocumented tree. Those findings appear later, when the first
component document makes their directory covered, and by then they are new findings,
which a baseline is forbidden to absorb. So the record is built from the configured walk
rather than from findings, and it is its own file.

## The record makes the rule stricter, not weaker

Before it, an undocumented sibling tree was invisible: a new top-level package escaped
the rule by sitting where no document had reached. With a record in hand that escape is
gone — every managed file the record does not name needs an owner, wherever it sits. A
repository that never adopted keeps the progressive rule exactly as it was.

## The lifecycle of one exception

An entry retires when its file gains an owner, is deleted, or is moved, and it never
comes back:

- `check --update-adoption` removes retired entries and refuses to add any, naming the
  files it would have had to add.
- `diff-integrity/adoption-record-grew` fails a pull request whose record excepts a path
  the base did not. Only the change that creates the record may write entries into it.
- `diff-integrity/adoption-debt-touched` fails a pull request that edits a recorded file
  without giving it an owner. The exception covers code nobody has gone back to; editing
  it means somebody has.

A rename is a new file. The record names paths, so a moved file is one the record does
not name, and the new path needs an owner in the change that moved it. Carrying an
exception across a move was rejected: it would let a repository rename its way out of
ever documenting anything.

## Retirement is read from the base, not from the record

`--update-adoption` is housekeeping, and nothing makes anybody run it. So the ordinary
state of a live record is *stale*: it goes on naming files that have since been
documented. Asking only whether the record names a path would then hand the exception
back the moment an owner was removed again, and the file would go quiet after having been
governed normally for months — an exception returning, which is the one thing the record
may not do.

What settles it is the same boundary the rest of `diff-integrity` reads: a recorded file
that had an owning doc **at the merge base** has already retired its entry, so leaving it
unowned at the head is `diff-integrity/adoption-exception-revived`, whatever the record
still says. Adding an owner and taking it away again inside one pull request is not that
case: the base never documented the file, the exception was live the whole time, and the
change is about something else.

"Had an owning doc at the merge base" is read with the **configuration at the merge base**,
not the one the change proposes. Ownership is a declaration plus the rule that accepts it,
and the rule lives in `irminsul.toml`: whether a file inside a declared test root answers to
the test policy depends on `paths.source_roots`, so widening that list changes what an
`owns_tests:` entry meant at the base. Read through the head's configuration instead, a
change could delete an owner and widen a root in one commit, and the exception the deleted
owner had retired came back with nothing reporting it — widening a root is not a weakening
and no rule reports it. The tree is the one shared input and cannot be one per side: there
is a single working directory, so a declared root's membership is walked in the checkout
that exists.

This is a property of the pull-request gate, and only of it. A plain `irminsul check` has
no base to compare against, so it reads the record as written — which is why the
comparison run, `check --diff origin/<base>`, is the one CI enforces.

## What the first record may call history

The change that creates a record writes entries into it, because the base holds no record
and there is no ratchet to widen. That allowance is about the *file*, not about the claim
each entry makes: "already unowned on the day of adoption" is a statement about the tree
at the adoption boundary, and git can check it. A recorded path that was not in the tree
at the merge base is a file the same change wrote, and calling it pre-existing debt is
ordinary growth wearing the first record's allowance —
`diff-integrity/adoption-debt-not-historical`.

A path the change *moved* is reported too, and that is deliberate. The debt did exist at
the boundary under the old name, which is not the question: adoption tolerates debt nobody
has gone back to, and moving a file is going back to it. Following the rename would let a
repository rename its way out of ever documenting anything, which is already why no change
*after* the first carries an exception across a move. The remedy is to adopt, then move.

### What the adopting change must prove

This is the authoritative list. Every rule below is checked on the change that creates the
record, and the list is complete — three review rounds patched this path one rule at a time,
each fix correct and each leaving a different rule missing, so what it needs is an
enumeration rather than another patch.

1. **Each entry was in this repository at the merge base**, at the path the record names —
   not at a path the change moved it from (`adoption-debt-not-historical`).
2. **Each entry from another repository was in that repository at the pinned revision**, and
   the pin is the full object id of a commit that repository holds
   (`adoption-record/debt-not-at-source-revision`, `adoption-record/source-unverifiable`).
3. **No entry is a file this change edited, moved or deleted** (`adoption-debt-touched`).
   Editing it means somebody went back to it; deleting it means the entry excepts nothing,
   and the remedy there is the record rather than a document about a file that is gone.
4. **No entry had an owning document at the merge base that this change removes**
   (`adoption-exception-revived`). Every other rule passes such a change honestly — the file
   really did exist at the base — so this is the only one that can see it.
5. **No entry has an owning document at the head** (`adoption-debt-already-owned`). It buys
   nothing today and becomes live the day that owner goes. Adopting-time only: a record that
   still names a file somebody has *since* documented is the ordinary state, because nothing
   obliges anyone to run `--update-adoption`.
6. **Each pinned source's revision is on the history that source declares**
   (`adoption-pin-not-on-ref`). Pushing a branch needs no review, so a commit id alone was
   never evidence the declared history ever had those files; `--init-adoption` pins the
   merge base of the source checkout and the declared ref, which is such a commit by
   construction, and a hand-written record is judged on the same obligation. Checked on the
   adopting change only: afterwards the pin cannot move and entries cannot be added, so the
   fact is preserved by the seal rather than re-proved — and no later run needs the ref.
7. **Each entry matches a path the configured walk produces**
   (`adoption-debt-not-managed`) — asked only when every configured root is present, because
   an absent root makes every path under it look like a path that does not exist, and the
   honest finding for that is `adoption-record/source-unverifiable`.

After the adopting change the rules are different and shorter: the record may not gain an
entry, its pins may not move, and it may not be deleted while it holds entries. Two things
*are* re-asked on every run, because they are about the record as it stands rather than
about the change that wrote it: each entry still existed in its source at the pinned
revision, and the source the entry states is the source the configured roots resolve it to.

A declared source is **one repository**. `path` names that repository's own root, and a
declaration covering roots in two of them — a common ancestor such as `..` — is refused,
because one pin is one history: the second repository's entries would be checked against the
first one's commit, and a path that exists in both would read as history it never had. The
configuration cannot see this, since it is a fact about the filesystem, so it is reported
where the filesystem is known rather than guessed at either end.

A configured root that is inside *this* git repository but outside the tree Irminsul walks
from — a monorepo where it runs from a subdirectory and the root points at a sibling of that
subdirectory — is refused rather than adopted from. It is neither local nor
cross-repository, and it is verifiable by neither half: the walk spells its files relative to
the root while git reports them under the worktree, so neither the historical-presence check
nor touch-to-own would match them. Run Irminsul from the worktree root, or bring the root
under the tree it walks.

A pin is recorded only for a source some entry is actually bound to. A pin grants nothing by
itself and every pin is preserved for ever, so recording one for a repository whose files are
all documented coupled it to the record permanently — and it could not be removed either,
because dropping a pin is a weakening the seal reports. A pin no entry binds to may now go.

### The boundary, and what it does not advance with

For an entry from another repository the boundary is a commit, recorded once. It is the
**merge base of the source checkout and the ref that source declares** — not the checkout's
`HEAD`, which on a side branch is a commit the declared history never had, and not the ref's
tip, which the checkout may not have reached.

That settles the cutoff in both directions. A file already merged to the declared history
before adoption **is** eligible: that is the approved snapshot an existing repository is
adopting, and merging is the act the source repository reviews. A file merged after is not,
because the pin is a fixed point — the source repository going on with its life is exactly
what the record may not absorb, and an entry added later is a record growing.

The ref is resolved to exactly one candidate: the value itself when it starts with `refs/`,
otherwise `refs/remotes/<value>`. A bare branch name is refused in configuration, because in
a checkout that means the local branch — movable by anyone, invisible when it moves — and a
missing ref fails closed rather than falling back to `HEAD`.

Deleting a record that still holds entries is `diff-integrity/adoption-record-removed`.
It would hand back the coarse covered-directory guess the record replaced, and leave the
next change free to adopt from scratch and re-run the allowance. Retiring every entry
until the record is empty is the way out; un-adopting on purpose takes the excuse the
config seal takes, a decision record naming the record's path.

## When the code is a different repository

In the [`siblings` layout](../guides/private-docs.md) the source roots reach into a repository
of their own, and everything above stops applying to them: this repository's merge base is
a point in a history that never contained those files. Asking it whether `core.py` existed
at the adoption boundary is not a hard question, it is the wrong repository.

So the boundary is recorded instead of derived. `check --init-adoption` reads the revision
each cross-repo source root's repository is at and writes it into the record beside the
entries:

```json
{
  "version": 1,
  "unowned": [
    { "path": "core.py", "source": "engine" },
    { "path": "util.py", "source": "engine" }
  ],
  "adopted_at": "<this repository's HEAD>",
  "sources": [{ "name": "engine", "revision": "<a commit on engine's declared ref>" }]
}
```

`name` is a declared `[[paths.sources]]` entry, not a path, and every entry from that
repository says so. A name survives somebody moving the checkout and does not survive
somebody pointing the name at a different repository, which is the property wanted: keyed by
root, an edit to `source_roots` re-pointed existing entries at another history with no pin
having changed. A file in *this* repository is still a plain string, so a single-repository
record is exactly what it always was.

Nothing else is stored, and a remote URL deliberately is not: a commit id resolves only in a
repository that holds that history, so the revision identifies the repository by being
verifiable in it, where a URL beside it would be one more hand-written assertion with
nothing checking it.

A declared `paths.test_roots` entry is pinned on the same terms. It is not a source root
and the ordinary walk does not reach it, but the record covers tests too, so a test tree in
the other repository puts entries in the record — and a root outside the boundary list is a
root whose entries nothing checks. One managed walk answers for both ownership rules and
for this resolution, so there is one list of roots rather than two that can disagree.

Every run then asks that repository the question this one cannot answer — did the file
exist at that revision? A pin needs no merge base to read, so the question is asked on a
plain `check`, on the nightly run, and on the source repository's own gate alike, and the
answers are:

- **It was there.** The entry excepts its file, as recorded debt always has. Deleting the
  file later does not un-verify it; it was there at the boundary, which is the whole
  question.
- **It was not.** `adoption-record/debt-not-at-source-revision` names the file. The
  record called it history and the source repository disagrees, so it is new and needs an
  owner.
- **Nobody can say.** No pin for the source, a revision that repository does not hold, a
  root outside this repository with no `.git` above it, one spelling that two roots both
  claim, or a **binding the configuration contradicts** — each is
  `adoption-record/source-unverifiable`. The entries go on excepting their files, because
  calling them new would assert the opposite of what could not be checked, and this finding
  fails the run instead. What is refused is the silence, not the exception.

"Nobody can say" is three different situations and they get three different messages,
because they have three different repairs. A **root that is not checked out** names the root
and the second `actions/checkout`. A **pinned revision the clone does not reach** names the
clone as shallow and gives both `fetch-depth: 0` and `git fetch --unshallow`, which is the
common case by a wide margin. A **complete clone that still lacks the commit** gets the
honest version: it is not in this checkout, whether that repository still has it elsewhere is
a question only that repository can answer, and the message gives the fetch to try rather
than concluding the history is gone. The third state — a pin that exists but is not on the
declared ref — can only arise while a record is being written, and is
`diff-integrity/adoption-pin-not-on-ref` with the revision and the ref's tip both named.

The binding cases are worth naming, because they are the ones the record's own format
exists to make answerable. An entry states the source it came from, and the configured roots
resolve its display to a source; the two are checked against each other every run, and
disagreement is a refusal rather than a choice. So: an entry naming a source no
`[[paths.sources]]` declares, an entry naming one source while the roots resolve another,
and an entry written as a plain path — which means a file in *this* repository — whose
display comes from elsewhere. Writing the binding down and then trusting it without
comparison would be the old re-derive-it-every-run behaviour with extra words.

A pin is a pin. `--update-adoption` carries it through untouched — the revision an entry
was history at is not a thing that retires — and a pull request that moves or drops one is
`diff-integrity/adoption-source-rebound`. Moving it forward is the growth move with no line
added to the record: everything the source repository gained in between would become
pre-existing debt. `check --pin-adoption-sources` exists for a record written before pins
did, and it only ever adds one, never moves one.

It is also the one migration path. A record written before entries and pins named their
source will not load at all — the message says so and says which command — and this one
converts it: each pinned root becomes the source that currently declares that root, with
its revision copied across unchanged, and each entry the walk resolves to another repository
states that repository. Nothing moves. Where the conversion cannot be mechanical it stops
and says why rather than guessing: a pinned root no declared source covers, two roots of one
repository pinned at different revisions — one repository has one boundary — or an entry
whose display resolves nowhere.

**Migration also has to meet the anchoring obligation**, and refuses when the legacy pin does
not. A record written before refs existed was never checked against one, so its boundary can
sit on a branch nobody reviewed; anchoring is checked when a record is *written* and not
again, because afterwards the pin cannot move. Carrying such a pin forward would therefore
leave a boundary permanently off the declared history that a first record would have been
refused for — copying a revision across is only safe while it is still asked the same
question. The remedy is to re-adopt deliberately, reviewing the entries that produces.

Two limits are worth stating in the same breath. A root with no commit yet cannot be
adopted at all — `--init-adoption` refuses rather than writing a record that claims a
boundary nothing can confirm. And the source repository has to be *present* when the gate
runs, which in CI means checking it out beside this one; the
[`siblings` workflows](init.md) do that.

## Where an entry is verified, decided once

An entry is not bound to a root. It is bound to whichever root the managed walk resolves its
display to, and that mapping depends on the configuration *and* on the record — so
`paths.source_roots` can re-point an existing entry at a different repository without
touching a pin. Every rule that judges an entry needs that mapping, and while each rule
worked it out for itself each one could disagree; three review rounds each found a different
rule holding the minority opinion.

`SourceMap` (`src/irminsul/source_map.py`) is the one answer. It resolves every managed
display to a `(repository, revision)` pair for one snapshot, and the checks, the ownership
rules and the seal all read it rather than re-deriving it. Two things keep it honest:

- **It resolves and does not judge.** Resolution reads the filesystem, the configuration and
  the record; validation reads git history. Nothing in the map runs git, and a display that
  resolves is not thereby legitimate debt — `adoption-record` and `diff-integrity` decide
  that, and a resolved pair that is unpinned, unreachable or ambiguous is reported as the
  state it is rather than replaced with a guess.
- **One map per snapshot, not one per comparison.** The pull-request gate has two sides and
  builds two maps: the merge base's, from the base's configuration and the base's record, and
  the head's. "Resolve once" means once for each side. An entry that survives in both records
  must have the same pair on both, and that single comparison is what catches a pin moved
  under an unchanged name and a root replaced under an unchanged pin — two failures a rule
  each would have to be written for separately.

The map is built on demand from the [DocGraph](docgraph.md) and lives as long as it does: a
graph is already a snapshot of the tree, so the map is no staler than the thing it hangs off.
The record is the exception, because the graph never reads it: a digest of its contents is
stamped, and the map is rebuilt when the digest moves, so a record written between two reads
is not answered from the first one. Size and modification time would be cheaper and would
miss the edit that matters most — a pin is forty hexadecimal characters, so moving a boundary
rewrites the file to the same length, and two writes in quick succession share an mtime to
the nanosecond on a coarse system clock.

One thing the map cannot supply is the base's rules. Ownership is a declaration plus the
configuration that accepts it, and when the `irminsul.toml` at the merge base does not load,
`diff-integrity` falls back to the change's own — reasonable degradation for most of the
seal, and not for this, where it would decide whether an exception retired using rules the
base never had. While the record holds entries, that fallback is
`diff-integrity/adoption-base-unreadable` and it fails the run. Such a base fails its own run
with exit 2, so a repository whose check is required cannot reach this state; that is a
repository setting rather than something this tool enforces, which is why the tool says what
it cannot decide instead of relying on it.

## What the boundary does not prove

What none of this establishes is that the adoption boundary was *reviewed*. Git proves a
path existed at a revision; it cannot prove anybody agreed to the record that named it.
That guarantee comes from the branch the merge base sits on being protected and the gate
being required — repository settings, not this tool.

The pinned source revision is the same kind of thing, and more obviously so, because it is
a string in a JSON file somebody wrote. What the pin buys is narrower than proof and still
worth having: it is checkable, so a later change cannot add an entry and call it history;
it is immutable, so the boundary cannot be walked forward to absorb what landed since; and
it is *stated*, so a reviewer of the adoption pull request is looking at the exact revision
being adopted rather than at an implicit "now". What it cannot do is establish that that
revision deserved to be the boundary. Adoption at a source `HEAD` that just gained a file
records that file as debt, and no comparison inside this tool can tell that apart from
adoption at a `HEAD` that had been sitting there for a year — the difference is whether
somebody agreed, and agreement lives in the review of the adopting commit.

## Scope & Limitations

The record does not decide which rule governs a file — that is the test-path question,
and recording a path never moves a file between the source and test policies. It holds
exact paths only, never a glob or a directory, because a pattern would adopt files
written next year. Three passes read it, and they read it for different things: the two ownership rules ask it which files to except, `adoption-record` asks whether it can be trusted to except anything, and `diff-integrity` compares it with its content at the merge base for growth, deletion and a moved boundary. No *other* check consults it, and a run
that excepted files says so in its output rather than letting an exit code of zero read
as proof that every file is documented.

Nothing here judges whether a documented file is documented well. An owner retires an
exception the moment it exists; whether its prose is worth reading is the same question
it is everywhere else in this tree.
