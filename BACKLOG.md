# Backlog

What we intend to fix next. Every entry below was re-checked against this tree on
2026-10-28 before being written down, because the longer list this replaces had entries
that the v0.3.0 work closed without the list noticing.

This file sits outside `docs_root` on purpose: a backlog names things that do not exist
yet, which the docs tree is checked against. A longer historical list, including the
doc-versus-code mismatches, is kept outside this repository.

**Name an issue by its slug, never by a bare number.** Verify an entry against the code
before working it.

## Enforcement and correctness

### `ignore-audit-blind-to-unran-passes`

`run_checks` (`src/irminsul/checks/pipeline.py:355`) takes a whole run through one
`finish`, so whether a comment was used is known across every pass, and `run_check`, the
one-check view, deliberately audits nothing. The audit still asks only about the
registered checks in `ran`: `apply_ignore_comments`
(`src/irminsul/checks/ignore_comments.py:169`) reports a comment unused only when every
name it holds is in `ran`. A comment naming a pass (`co-change`, `diff-integrity`,
`new-dependency`, `history-depth`) is never reported unused, and adding one of those names
to a comment that suppresses nothing exempts the whole comment: `links, co-change` stays
silent where `links` alone is reported (re-run on 2026-10-28). A pass's findings carry no
line, which a comment's `covers` requires, so a comment naming a pass can never suppress
anything either.

Not a one-liner. Adding those names to `ran` makes an ordinary `irminsul check` report
valid diff-only comments as certain `ignore-comment/unused`, because no diff pass ran. A
fix has to settle `ran` as the passes that actually ran, and what suppressing a finding
that carries no line even means, or reject a comment that names a pass. Seen again by the
PR 12d lane on 2026-10-28.

### `claim-move-and-reword-across-docs`

Within one document a surviving claim id is matched on its own
(`src/irminsul/checks/diff_integrity.py:810`) and a reworded claim reports
`claim-reworded`. Across documents `kept_claims` (`:802`, built from `_declared_now` at
`:738`) still keys on `(id, text)` and the test at `:831` asks for that pair, so a claim
moved to another document *and* reworded in the same change reads as removed — certain
`governing-claim-removed` for a claim that exists one file over.

### `connected-doc-hides-unconnected-sections`

A doc is re-asked about code only through its connections to it: the files it owns through
`describes`, its claims, its anchors, and the code its sentences name. One connection makes
the whole doc look tied to code while its other sections rot unseen. Example: `store.md`
owns `src/store.py` and anchors one paragraph to `Store.open`; a change to `Store.close`
is satisfied for `co-change` by an edit to any line of `store.md`, and the section that
explains closing is never queued, because it names no code. A sentence that explains code
it neither names nor anchors is likewise never re-asked when that code changes. Finer
rules, per section and per changed definition, were considered and deferred by
`docs/decisions/derive-facts-and-leave-meaning-to-the-reader.md`; until then the root
`AGENTS.md` asks the writer to name, anchor, or claim the code a sentence explains.

### `defined-means-two-things`

The review queue and `anchors --suggest` ask `CodeResolver.resolve` whether a code span
names a definition, and its symbol index (`_symbol_index`,
`src/irminsul/code_references.py:96`) holds only functions and classes, at the top level
and one class deep. Anchors resolve a name through `_find_symbol`
(`src/irminsul/anchors.py:117`), which also accepts an assignment. With `MAX_SIZE = 5` in
`src/m.py`, `<!-- anchor: src/m.py#MAX_SIZE -->` resolves, while a span `MAX_SIZE` resolves
to nothing, is listed as `unbound` by `list review --changed`, and is never paired with its
definition; `anchors --suggest` then offers that very anchor (re-run on 2026-10-28). One
rule for "this module defines that name" would let the two agree; which rule is right is a
decision, not a refactor.

### `narrowed-surface-is-not-a-filter`

`inventory-drift` extracts a doc's surface from the files its `source` or `describes` globs
match (`SourceTree.surface(kind, globs)`, `src/irminsul/source_tree.py:68`), not by
filtering the whole surface, and the two differ. A Typer command whose group is registered
in a module outside the globs loses its prefix — `serve` instead of `app serve` — and which
file a repeated identity is reported from depends on which files were read. Whether an
`inventory:` entry should name identities as the whole program sees them is undecided, so
both are cached, each under its own key.

### `suggest-splits-lines-unlike-python`

`binding.suggest` parses `"\n".join(lines)` (`src/irminsul/binding.py:173`), where the lines
come from `str.splitlines` (`:151`), which also splits on `\x0c`, `\x1c` and ` `.
Python ends no line at those characters, so a module holding a form feed parses with
shifted line numbers and `anchors --suggest` points a candidate at the wrong line (line 13
for a definition on line 12, re-run on 2026-10-28), while one holding `\x1c` in a string no
longer parses and offers nothing. Reading the module through the source tree's
`PythonModule` (`src/irminsul/inventory/base.py:62`), as every other reader now does, would
make suggestions agree with them.

### `suggest-matches-the-last-name-part`

`binding.suggest` (`src/irminsul/binding.py:155`) looks a dotted name up by its last part
(`:163`) and keeps the first three candidates by path (`_SUGGESTION_LIMIT`, `:191`). For
`graph.change` it offers `FinalizePlan.change`, `ChangeReport.change` and
`TransitionPlan.change` and misses `DocGraph.change` (`src/irminsul/docgraph.py:178`), so
the marker an agent pastes binds the wrong definition. Rank a candidate whose enclosing
class matches the qualifier first, or say that the name is ambiguous. Found by the PR 12f
lane and reproduced on 2026-10-28.

### `component-claim-drift-unreported`

`claim-provenance/evidence-drift` judges only claims in the foundation and architecture
layers (`_is_protected_claim_node`, `src/irminsul/checks/claim_provenance.py:37`). A claim
in a component doc whose evidence changes is never re-asked, yet `anchors --re-pin --doc`
still writes its pins, so they lag unseen and a doc-wide re-pin acknowledges code nobody
re-read. On 2026-10-28 `irminsul anchors --re-pin --all` on a clean copy of this tree moves
three such pins in `docs/components/adoption-record.md` (two on
`checks/diff_integrity.py`, one on `checks/pipeline.py`) while
`irminsul check --fail-on hint,time` exits 0; the re-pin, which writes, is the only way to
see them.

A stale pin is also unreported in any layer when the doc was committed after the evidence:
a pin that no longer matches falls back to the commit-time comparison
(`_scan_evidence_drift`, `:256`), so a doc touched in the same commit, or on the other
side of a merge, hides it. The PR 12 lanes met this each time they edited a component's
code (four stale pins after 12d, a `context.py` pin after 12f). Either judge every stable
doc's claims, or stop pinning evidence that nothing reads. A draft RFC,
`claim-evidence-names-a-part` (branch `rfc/claim-evidence-parts`, not on main), proposes
judging every layer. Until then, a read-only way to list the pins that no longer match would
let an agent see them without `--re-pin --all` rewriting them.

### `rfc-supersedes-unchecked`

`supersession` skips RFCs entirely (`src/irminsul/checks/supersession.py:43`), and no other
check reads an RFC's `supersedes:`, so it can name a doc id that does not exist. Requiring
the old doc to be `deprecated` may rightly wait for the RFC's state, but an unknown id is
wrong in any state. Found by the PR 9 design survey on 2026-10-22.

### `base-config-keys-dropped-unseen`

The seal reads the base branch's `irminsul.toml` through `parse_snapshot`
(`src/irminsul/config.py:568`), which drops every key the current schema no longer has. A
change that removes or renames a setting therefore shows the seal a base without it, and
the weakening is never compared. The one rename so far was mapped by hand
(`_with_surface_rules`, `:582`). Report a base key this schema lacks, so the next rename or
removal is judged rather than vanishing. Found by the PR 9h lane on 2026-10-27.

### `unbound-name-marks-values`

`irminsul list review --changed` marks an edited sentence `unbound-name` when a code span
names nothing the resolver binds (`unbound_names`, `src/irminsul/binding.py:128`, called at
`src/irminsul/listing/review.py:323`). A span holding a value or a builtin, such as
`not_run`, `ValueError` or `IRMINSUL_BASE_REF`, is marked though no symbol could ever bind
it. The marker legend now says to reword a name that is not this repository's code or to
leave it when no anchor can reach it, and `anchors --suggest` says "no source file defines
it", so a writer has an answer, but the answer is to leave or reword a correct sentence,
and the marker still lengthens every queue. Bind builtins and known environment variables,
or leave a span that is a literal value unmarked. Found by the PR 10b lane on 2026-10-28
and re-run the same day.

### `unmatched-generated-marker-is-redundant`

Since the marked-region reader (`src/irminsul/marked_region.py`), a manifest whose markers
do not make one region is read whole by `retired-references` and reported, with its marker
counts, by `agents-manifest/missing-generated-markers`. The certain finding
`retired-references/unmatched-generated-marker` still fires for a start marker with no end,
but it no longer protects anything: no prose is hidden. It is a second report of a fact
`agents-manifest` already states, though `agents-manifest` is opt-in, so deleting the code
leaves a project that has not enabled it without the report. Decide whether that report
belongs in `agents-manifest` always or in neither. Found by the marked-region PR on
2026-10-28.

### `home-paths-are-checked-as-repo-paths`

`code-references/unknown-path` reports `~/.ledger.json` in every doc that gives a
home-directory default: the rule's "written like a path"
(`code-is-named-in-code-spans-and-bound-by-anchors`, Decision: "no whitespace, `*` or `://`,
and a `/` before a last segment with an extension") admits it, and a path under `~` never names
a repository file. Three docs of the dogfood adoption needed an ignore comment or a rewrite
(2026-10-29). Add "and does not start with `~`" to that sentence; a Decision edit, so it lands
once a decision can be edited in place.

### `frontmatter-writer-reorders-keys`

`frontmatter_edit` re-emits keys in canonical order, so the first tool write to a doc authored
in another order moves keys it did not change: `change finalize` moved `summary:` below
`describes:` in `docs/components/new-list-regen.md`, and `change transition` did the same in a
dogfood RFC (2026-10-29). Keep the author's order, or bring every doc into the canonical order
once so later writes change only what they mean to.

### `evidence-drift-misses-component-claims`

`evidence-drift` skips every claim outside the foundation and architecture layers
(`src/irminsul/checks/claim_provenance.py:113-114`), so a component claim whose evidence file
changed is never re-asked by a plain `check`. On the trailer-step branch, 11 evidence pins in
three component docs no longer matched their files, in `docs/components/adoption-record.md`,
`docs/components/baseline.md` and `docs/components/change.md`. No gate reported them; a
comparison of each pin with its file's current hash did. The branch has since re-pinned them
after re-reading each claim, except two: both pins of `transition-applies-human-decisions` in
`docs/components/change.md`, which still do not match `src/irminsul/change/transition.py` and
`src/irminsul/change/finalize.py`. Found 2026-10-30.

## Agent workflow

Found by an agent working in this repository, as the root `AGENTS.md` asks.

### `finalize-has-no-end-commit`

`irminsul change finalize --base-ref <ref>` and `change verify` measure an RFC's work as
everything changed since `<ref>`, up to the working tree. Once other pull requests land
after the implementation, their components read as the RFC's undeclared scope
(`touched_undeclared`, `src/irminsul/change/report.py:366`) and finalize refuses. Seen on 2026-10-21 finalizing `a-gate-file-is-sealed-not-scored` after
three later pull requests: the only way through was a branch cut at the implementation's own
landing commit, finalized there and cherry-picked forward. Let verify and finalize name
where the implementation ends as well as where it starts, for the scope and evidence
reports only.

### `doc-evidence-pins-the-whole-file`

A claim's evidence pin covers a whole file. A claim in state `available` must cite a
user-facing doc, and when that doc is long every edit anywhere in it re-asks the claim:
`component-hierarchy`'s `parent-child-check-available` cites `docs/components/checks.md`
and was re-asked six times on 2026-10-21 and 2026-10-22, and re-pinned four more times on
2026-10-27, for edits to unrelated paragraphs. Code evidence does the same: a one-line
`--help` edit in `src/irminsul/cli.py` re-asked three foundation and architecture claims in
the PR 12a and 12b lanes on 2026-10-28. Re-asking that often trains a reader to re-pin
without reading. Let evidence name a section or a definition and pin only that part; the
accepted RFC `claim-evidence-names-a-part`, resolved into
`code-is-named-in-code-spans-and-bound-by-anchors`, does it and is not yet implemented. The
second reset hit it again on 2026-10-29: retargeting one link in `checks.md` re-asked that
claim, and a help-string edit in the `refs` fix re-asked three claims citing `cli.py`. The
dogfood fix lanes the same night re-pinned the three `cli.py` claims once per lane and again at
each rebase, about eight re-reads of three unchanged claims.

### `after-edit-buries-its-findings`

`irminsul context --after-edit` prints the whole owner packet, excerpts and active RFC
requirements included, before the findings the change introduced, so an agent greps for the
findings section (the `refs` fix lane, 2026-10-29). Print the findings first, or give the
packet a flag that leaves it out.

### `fix-buries-its-own-output`

On a clean tree `irminsul fix` lists every held fix, one line each, and ends with "held 44
fix(es); re-run with --confirm to apply" (58 on 2026-10-22), every one a glossary link for
an info finding (`_echo_fix_result`, `src/irminsul/cli.py:1129`; the summary at `:1318`), so
the line that matters in a real run is buried. Summarize held fixes by check and code, and
keep info-level fixes out of the default summary unless `--only` names their check.

`--confirm` then applies every held fix at once. An agent confirming the one fix its change
needed also wrote 60 glossary links into 40 files, stable decision records among them, and
had to restore `docs` and redo its edits (PR 10c lane, 2026-10-28). Let `--confirm` leave
info-level fixes alone unless `--only` names their check, or apply only the fixes in the
files the change touched.

### `review-binds-common-words`

`irminsul list review --changed` binds a code span that holds an ordinary word to the one
definition that shares it: `main` binds to `cli.main` (`src/irminsul/cli.py:169`), and
`path` and `status` to frontmatter fields (`CodeResolver.resolve`,
`src/irminsul/code_references.py:171`). Plain prose binds too, wherever a word is a
distinctive identity (`_DISTINCTIVE_RE`, `:27`; `resolve_prose`, `:87`): a flag mentioned
in another program's command binds to ours, so `pipx install --force irminsul` in a sentence
bound to `init`'s own `--force` (`src/irminsul/cli.py:295`; PR 12b lane, 2026-10-28). A
change to CI and its docs queued 87 items, most of them for such words (PR 11 lane,
2026-10-28). A queue that long is skimmed, not read. Bind prose only to names that are
unambiguous in the repository, and not to a flag that follows another program's name;
leave plain words to code spans that name them.

A name with two definitions binds to one without saying so: in a component doc about the
store, `add` bound to the CLI command `add`, not `Ledger.add`, so the queue sent a reader to the
wrong function for four sentences, and a dotted span resolves by its last segment
(`UnmatchedPath.recorded_debt` bound to `adoption.recorded_debt`) with no `unbound-name` raised
(dogfood, 2026-10-29). Show every candidate a name could bind to, or bind none.

### `first-review-after-init-queues-the-scaffold`

The first `list review --changed` after `irminsul init` in a brownfield repository queues 113
sentences, most of them the managed `AGENTS.md` block and the scaffolded guides, which equal
their templates; the one wrong sentence in the existing docs sat at the bottom (dogfood
adoption, 2026-10-29). The `derive-facts` Decision queues "each sentence the change added", so
the queue keeps them; the plain output could fold text equal to an `init` template into one line
per file, with JSON unchanged.

### `review-items-carry-no-excerpt`

A review item names the code it binds by `path:line` only, so every item is a file to open: the
dogfood adoption agent opened `cli.py` to judge the usage guide's "groups by week" (2026-10-29).
A few lines of the bound definition, under a flag or in JSON, would let a reader judge most items
in place.

### `stdlib-names-read-as-unbound`

A language's builtins are bound to the language since 2026-10-29, but a standard-library or
third-party name in a code span, such as `date.fromisoformat` or `monkeypatch.setenv`, is still
`unbound-name` with "bind it with an anchor", though nothing in the repository can define it
(dogfood feature lane). Treat a dotted name whose head is importable from the standard library or
a declared dependency as bound outside the repository.

### `queue-is-unranked`

A feature that adds docs queues every sentence of them: 85 items for the dogfood budget feature,
about 70 of them the agent's own new sentences, with the claims whose evidence changed under a
doc nobody edited mixed in (2026-10-29). Group the plain output by marker, the items the change
did not write first.

### `init-writes-no-gitattributes`

This repository's `.gitattributes` sets `* text=auto eol=lf`, but `init` scaffolds none
(`src/irminsul/init/` has no `.gitattributes` template), so an adopter on Windows with
`core.autocrlf=true` gets CRLF checkouts while `init`, `fix` and an agent's scripts write LF,
and meets both in one tree. Decide whether `init` should scaffold one. Found by the v0.4.0
reset on 2026-10-28.

### `acknowledgement-needs-its-own-commit`

A `co-change` acknowledgement is a trailer on a commit made after the last change to the
files the warning lists or, for work not yet committed, on the commit that carries it (the
warning's suggestion says which, `src/irminsul/checks/co_change.py:229`). An agent that
re-reads the doc after committing the code must still make an empty commit only to carry
the trailer, and a later commit touching those files silently voids an earlier trailer.
Seen three times on 2026-10-22. Let the acknowledgement name the source revision it re-read
against, so it survives being written before or after the code and is voided only by a
change to that code.

### `renamed-doc-has-no-review-base`

`irminsul list review --changed` compares a doc's sentences with the same path at the
base (`_prose_at_ref`, `src/irminsul/listing/review.py:493`). A doc the change renamed has
no base under its new path, so every sentence on a changed line is queued as `edited`: after
a `git mv`, an unchanged sentence sharing a line with a reworded one is queued too
(re-run on 2026-10-28). Read the base through the rename, as `renamed_paths`
(`src/irminsul/git/changes.py:362`) already finds it.

### `removed-sentences-queue-one-by-one`

`irminsul list review --base-ref` queues one `removed-sentence` item per deleted sentence
(`_removed_sentences`, `src/irminsul/listing/review.py:458`). A deliberate cut queues every
sentence of it: four items for a four-sentence paragraph, about 25 for one paragraph and
213 for the trim of `checks.md` in the PR 12 lanes. A sentence reworded rather than cut
shows twice, as `edited` and as `removed-sentence`. The reader has no way to say where a
cut sentence now lives, so the same cut is re-read at every run. Group removed sentences by
paragraph, pair a reworded sentence with its replacement, and let a reader name the home
once. Found by the PR 12a, 12c and 12d lanes on 2026-10-28.

### `deleted-doc-queues-nothing`

A doc the change deleted whole queues nothing in `list review --base-ref`: its path is not
in `changed`, which `_removed_sentences` (`src/irminsul/listing/review.py:458`) walks, and
its docstring records that as the rule (0 items for a `git rm` of a doc, 2026-10-28). So
deleting a whole doc, which removes more prose than any cut, raises no "where does this
live now" prompt. Queue a deleted doc's sentences like any other removal, grouped by doc.
Found by the PR 12c lane on 2026-10-28.

### `context-names-no-owner-for-directories-and-guidance-files`

`irminsul context src/irminsul/change` answers "no owning doc found" and exits 1
(`src/irminsul/context.py:613`), although `docs/components/change.md` describes
`src/irminsul/change/**`; a directory is what an agent has before editing several files.
`irminsul context AGENTS.md` gives the same answer for a file `paths.extra_docs` names,
without saying that it is one. Resolve a directory to the docs whose `describes` globs
match files under it, and say "extra doc" for a guidance file. Found by the PR 12e lane and
the PR 12 design survey, reproduced on 2026-10-28.

### `no-command-lists-declarations`

No command lists a doc's anchors, its claim markers, or which doc is the only code-span
home of an inventory identity. `anchors --format json` carries findings only, and
`context --include claims <doc>` lists one doc's frontmatter claims, without pins and
without body markers. Trimming docs in PR 12 needed a script to count anchors and markers
before and after each cut, and nothing warns before a cut that a doc holds the last
code-span mention of an inventory item: only the full `irminsul check`'s
`inventory-drift/unexplained-live-item` shows it, after the fact. Add one read-only view of
anchors, claim markers and inventory homes per doc. Found by the PR 12 design survey and
lane 12f on 2026-10-28.

### `surface-gives-names-only`

`irminsul surface config-keys` and `surface frontmatter-fields` print an identity, its file
and its line, and nothing else: no dotted name (`name`, `path` and `ref` come out bare), no
type, no default, no description. A key table in a doc therefore cannot be derived and is
kept by hand. Carry the dotted name, default and description in the surface items
(`SurfaceItem`, `src/irminsul/inventory/base.py:26`). Found by the PR 12 design survey on
2026-10-28.

### `docstrings-and-changelog-links-unchecked`

PR 12 moved the reasons the docs dropped onto docstrings, and no check reads a docstring: a
docstring that goes stale is found only by reading, and the survey found about a dozen that
had. Two other hand-kept statements are unchecked too: the links in `CHANGELOG.md`, which
`paths.extra_docs` does not name, and the status-check names that
`docs/foundation/enforcement.md:89` lists as required, which nothing compares with the job
names in `.github/workflows/ci.yml`. For the check names, derive the line from the
workflow or compare it with it. Found by the PR 12 design survey on 2026-10-28.

The changelog is not guidance: naming it in `paths.extra_docs` raised 39 findings on
2026-10-29, every one a removed name a changelog records on purpose. The draft RFC
`a-history-file-is-checked-for-its-links` (branch `rfc/history-files`) checks its links
alone.

### `manifest-table-is-the-working-tree`

`irminsul fix --only agents-manifest` renders the `docs/AGENTS.md` table from the whole
working tree (`render_generated_section`, `src/irminsul/regen/agents_md.py:44`), so a change
split into several commits that each pass `irminsul check` needs the table edited by hand
for every intermediate commit: the generated table lists docs the commit does not yet
contain. Found by the PR 12c lane on 2026-10-28. Decide whether an intermediate commit must
pass `agents-manifest`; if so, let `fix` render from the index, and if not, say so in the
loop.

### `suggest-prints-an-unpinned-anchor`

`irminsul anchors --suggest` prints `<!-- anchor: path#symbol -->` without a hash and does
not say that `anchors --re-pin --doc <doc> --anchor <path#symbol>` pins it. The only prompt
is the next run's `claim-anchor/unpinned`, an info hint that never fails a run, even under
`--fail-on hint,time` (re-run on 2026-10-28), so an anchor can stay unpinned for good and
cannot notice the code changing. Print the re-pin command with each marker, and let
`--re-pin` take the suggestion directly. Found by the PR 12c lane on 2026-10-28.

### `new-has-no-summary`

`irminsul new component` (and `adr`, `rfc`) writes `status: draft` and a commented-out
`# summary:` line, so the doc it creates raises `frontmatter/missing-summary` until the
writer edits the frontmatter by hand (re-run on 2026-10-28). Take `--summary` on `new`, so
a scaffold can be born with the one field the manifest needs. Found by the PR 10b lane on
2026-10-28.

### `new-slug-drops-dots`

`irminsul new adr "The loop lives in AGENTS.md once"` writes
`the-loop-lives-in-agentsmd-once.md`: `_slugify` (`src/irminsul/new/command.py:32`) deletes
every character outside `[a-z0-9\s_-]`, so a `.` joins its neighbours. A dot between
letters should separate words (`agents-md`). Found by the PR 12b lane on 2026-10-28, which
renamed the record by hand.

### `missing-config-uses-defaults`

With no `irminsul.toml` in the directory or above it, `load` returns the default config
(`src/irminsul/config.py:630`), so `irminsul new adr` run in the wrong directory writes a
doc there and reports success (re-run on 2026-10-28). Only a `--path` below an existing
config is refused. A command that writes should refuse when no config is found; a read-only
command could say it used defaults. Found by the PR 10b lane on 2026-10-28.

### `shared-module-asks-every-importer`

A new module that many components import, such as `errors.py` in PR 10b, makes
`new-dependency` ask each importing doc for its own `depends_on`: 13 one-line edits, each
answering the same question (one finding per doc, `src/irminsul/checks/new_dependency.py:132`).
The edges are real, but the warning repeats one fact per importer. Report a new shared
module once, naming its importers, with one fix that writes every `depends_on`. Found by the
PR 10b lane on 2026-10-28.

## Release pipeline

v0.3.0 was tagged and published on 2026-09-25: PyPI carries the wheel and sdist with
provenance attestations, and `ghcr.io/huajie-zhong/irminsul` carries `0.3.0` and `latest`
(both re-checked on 2026-10-28). The tag and the PyPI trusted publisher are in place.

- The workflow creates no GitHub Release object for a tag; the v0.3.0 release was made
  outside it.

## Review debt

Cross-repository adoption (the `siblings` layout, declared sources, and the adoption
record's `{path, source}` bindings) shipped in v0.3.0 without a clean external review
round. Eleven findings were raised against it across two rounds and all eleven were valid,
four of them in code written the same day. Treat that surface as unsettled.
