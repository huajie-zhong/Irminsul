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

### `governed-code-does-not-re-ask-its-record`

A decision record's `governs:` names the code it decides, and nothing reads that list yet. The
accepted RFC `decision-records-govern-what-they-decide` makes `irminsul context <path>` name the
governing record before an edit; it does not re-ask the record's Decision when that code
changes. A Decision that names a function or class in a code span is queued by
`list review --changed` when the change touches it, marked `names-changed-code`. One that names
only a command, an option or a file, or states the rule in plain words, is reached by neither,
and the case `decision-governs-the-function` of `tests/test_seeded_rot.py` pins the last. On
2026-11-25 every one of the 14 records named code somewhere in its Decision, and 167 of the 339
Decision sentences named code the queue resolves (a review). Queue a record's Decision when a
change touches what the record governs.

### `defined-means-two-things`

The review queue and `anchors --suggest` ask `CodeResolver.resolve` whether a code span
names a definition, and its symbol index (`_symbol_index`,
`src/irminsul/code_references.py:96`) holds only functions and classes, at the top level
and one class deep. Anchors resolve a name through `_find_symbol`
(`src/irminsul/languages/python_reader.py`), which also accepts an assignment. With `MAX_SIZE = 5` in
`src/m.py`, `<!-- anchor: src/m.py#MAX_SIZE -->` resolves, while a span `MAX_SIZE` resolves
to nothing, is listed as `unbound` by `list review --written`, and is never paired with its
definition; `anchors --suggest` then offers that very anchor (re-run on 2026-10-28). One
rule for "this module defines that name" would let the two agree; which rule is right is a
decision, not a refactor.

### `changed-lines-read-an-added-line-as-a-file-name`

`changed_line_numbers` (`src/irminsul/git/changes.py`) takes any line of git's diff that starts
`+++ ` for the name of the next file, and a line the change added that starts `++ ` prints that
way. With `-- a/one` replaced by `++ b/two` on line 1 of `src/a.sql` and line 3 edited too, it
returns `{"src/a.sql": {1}, "two": {3}}`: the later hunk is filed under a path that does not
exist, so `list review --changed` reads no change on those lines (run on 2026-11-26). A file's
two names come between its `diff --git` line and its first hunk; read them only there.

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
longer parses and offers nothing. The tree-sitter readers count lines as Python does, by line feeds, so a TypeScript, Go or Rust file holding one of those characters has the same shift. Reading the module through the source tree's reading of
the file (`SourceReader.reading`, `src/irminsul/inventory/base.py`), as every other feature
now does, would make suggestions agree with them.

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
`irminsul check --fail-on hint,time` exits 0. Until 2026-11-27 the re-pin, which writes, was
the only way to see them; `irminsul anchors --stale` now lists them, and no check reports them
still.

A stale pin is also unreported in any layer when the doc was committed after the evidence:
a pin that no longer matches falls back to the commit-time comparison
(`_scan_evidence_drift`), so a doc touched in the same commit, or on the other
side of a merge, hides it. The PR 12 lanes met this each time they edited a component's
code (four stale pins after 12d, a `context.py` pin after 12f). On 2026-11-26 it reached main
in the foundation and architecture layers too: a merge took main's `cli.py` pins for three
claims, which no longer matched the merged file, and touched both docs, so the branch's gates
passed; squashed onto main, the commit touched `cli.py` and not the docs, and three
`evidence-drift` warnings appeared there. Either judge every stable
doc's claims, or stop pinning evidence that nothing reads. The accepted RFC
`claim-evidence-names-a-part` judges every layer, as its last step, and still skips a stale pin
behind a later doc commit. Since 2026-11-27 `irminsul anchors --stale` lists every pin that no
longer matches, each saying whether a check reports it, so an agent sees them without
`--re-pin --all` rewriting them; it fails nothing, so a gate still passes over each one.

Two branches that each re-pin the same claim's evidence conflict on the pin line when merged,
since each writes the hash of its own version of the file, and taking either side leaves a pin
that matches neither version once the code merges; the merge commit touches the doc, so the
fallback above keeps `evidence-drift` silent (a dogfood agent, 2026-11-26). The one right
resolution is a re-pin after re-reading the merged file, and no gate says the pin needs one:
`evidence-drift` skips a component claim, and the merge commit hides it in any layer.
`irminsul anchors --stale` lists the pin, with no check reporting it, only when someone runs it.

### `drift-findings-carry-no-subject`

`claim-anchor/pinned-drift` and `claim-provenance/evidence-drift` carry no target, claim or
evidence field: `data` and `subject` are null, and only the message names what drifted. So
`anchors --stale` reads its `reported_by` back from the message (`_PINNED_DRIFT_RE` and
`_EVIDENCE_DRIFT_RE` in `src/irminsul/anchors.py`), where a quoted name ends at the first `'`:
a pin whose path or claim id holds a `'` is listed as reported by nothing although a check
reports it, and a reworded message would do the same to every pin. Give both findings `data`
naming the anchor target, or the claim id and each evidence path, and read that instead. It
adds fields to what two checks report, so it is the owner's call.

### `re-pin-suggestions-are-not-shell-quoted`

The `--re-pin` command that `claim-provenance/evidence-drift` suggests, and the one
`claim-anchor` suggests, write the doc path and the evidence path bare
(`_drift_finding` in `src/irminsul/checks/claim_provenance.py`, `run` in
`src/irminsul/checks/claim_anchor.py`). For evidence spelled `src/my file.py` the suggestion
fails as printed with "unexpected extra argument (file.py)", and a doc path holding a space
does the same to both. `anchors --stale` prints its `re_pin` through `shlex.quote`; the two
suggestions should too.

### `same-tree-test-answers-two-questions`

`base_is_the_working_tree` (`src/irminsul/delta.py`) decides both whether `check --delta` would
compare a tree with itself and whether `context --after-edit` has a change to judge, from one
list of watched paths: the docs root, the source roots, the guidance files, `irminsul.toml` and
the workflows. The two questions have different answers. With only the adoption record changed
and not committed, `context --after-edit --base-ref HEAD` says the tree is identical to `HEAD`
and judges no change, though `diff-integrity` judges that record (run on 2026-11-25). A new test
file no doc owns fails `irminsul check` with `test-ownership/unowned-test` while `check --delta`
refuses the run as identical to `HEAD`, because `paths.test_roots` is not watched, and deleting
a file a claim cites as evidence outside those roots, such as `action.yml`, is refused the same
way (a review, 2026-11-25). Watching the baseline and the adoption record for both was tried
that day and withdrawn: `--delta` applies no baseline to either side, so a tree that differs
only in the baseline compares equal and the run exits 0 having measured nothing, which the
refusal exists to prevent. The adoption record is different: with one entry removed from it,
`irminsul check` reports `uniqueness/undocumented-file` while `check --delta` refuses the run as
identical (a review, 2026-11-25). Ask the two questions apart: for `--delta`, every path a
check reads, test roots, cited evidence and the adoption record included; for a change, the
baseline as well.

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

`irminsul list review --written` marks an edited sentence `unbound-name` when a code span
names nothing the resolver binds (`unbound_names`, `src/irminsul/binding.py:140`, called at
`src/irminsul/listing/review.py:347`). A span holding a value or a builtin, such as
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
`src/irminsul/change/finalize.py`. A claim with no pin on a cited doc still reports after a
re-pin commit of that doc, because the commit-time comparison remains: the re-pin commit is
later than the doc's edit, and only a commit of the claim's own doc clears it. Found 2026-10-30.

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
reports only. Seen again on 2026-11-26: `an-edit-with-no-base-is-judged-against-head` was
finalized at `62d5eab`, where its work landed, after `a-topic-search-reads-doc-bodies` had
landed on top of it. Implementing and finalizing an RFC in one pull request, the rule of the
root `AGENTS.md` since that day, avoids it for an RFC not yet built.

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

### `confirm-applies-every-held-fix`

`irminsul fix --confirm` applies every held fix at once. An agent confirming the one fix its
change needed also wrote 60 glossary links into 40 files, stable decision records among them,
and had to restore `docs` and redo its edits (PR 10c lane, 2026-10-28). On 2026-11-25 a clean
tree holds 33 such fixes, every one a glossary link for an info finding. Let `--confirm` leave
info-level fixes alone unless `--only` names their check, or apply only the fixes in the files
the change touched. The other half of this entry, the held fixes printed one line each, was
closed on 2026-10-31: `fix` prints one summary line and `--dry-run --confirm` lists them.

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

### `a-name-two-files-define-pairs-with-nothing`

`CodeResolver.resolve` (`src/irminsul/code_references.py`) pairs a span with a function or class
only when one definition in the source has that name, so a bare name that two definitions share
pairs with neither, in the queue with a change and without one. `parse` is a function of
`src/irminsul/checks/acknowledgement.py` and a method of `PythonModule` in
`src/irminsul/inventory/base.py`. The sentence of `docs/components/checks.md:125` that says what
`parse` reads was therefore not asked about for `parse` when the pull request `dde68e0..ffa39b4`
changed what `parse` takes for a reason; `list review --changed` queued it only because the same
sentence names `acknowledge`, which the pull request also touched (measured on 2026-11-26). A
span in a doc that owns one of the defining files could pair with that file's definition; which
definition a name means elsewhere is `review-binds-common-words`.

### `first-review-after-init-queues-the-scaffold`

The first review after `irminsul init` in a brownfield repository listed 113 sentences, most of
them the managed `AGENTS.md` block and the scaffolded guides, which equal their templates; the
one wrong sentence in the existing docs sat at the bottom (dogfood adoption, 2026-10-29). Those
were `list review --changed` then; since 2026-11-26 they are `edited` items of
`list review --written`, which the `derive-facts` Decision has list each sentence the change
added, so the list keeps them. The plain output could fold text equal to an `init` template into
one line per file, with JSON unchanged.

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

### `a-mention-pattern-hides-its-kinds-bare-identities`

`CodeResolver.resolve` (`src/irminsul/code_references.py`) matches a configured surface kind by
exactly its identity only when the kind has no mention pattern: a kind with one is matched by
its pattern alone (`if kind in self.mentions: continue`), though the method's docstring says
any other configured kind is found by exactly its identity. This repository's
`[[surface.rules]]` entry for `config-keys` gives a `mention_pattern` that reads the last
segments of a dotted key, so `paths.docs_root` resolves while a bare `mention_pattern` or
`require_tests`, which `irminsul surface config-keys` lists, resolves to nothing:
`list review --written` marks a sentence naming one `unbound-name`, and `anchors --suggest`
lists it with the field of that name as a candidate (both run on 2026-11-26, after a dogfood
agent reported the first). Matching the bare identity as well changes what `code-references`,
the review queue and `context`'s `named_by` resolve, which the Decision of
`surface-rules-and-language-profiles-are-data` decides ("A kind resolves to its mention
pattern"), so it is the owner's call; a mention pattern that matched every bare key would read
every lowercase word of a doc as one. `defined-means-two-things` is the same symptom for a
module-level assignment.

### `co-change-asks-a-doc-that-states-no-rule-for-the-change`

`co-change/unreflected-change` warns on a component doc whenever source it describes changes and
the doc does not (`run_co_change`, `src/irminsul/checks/co_change.py`), whatever the change
was. Adding one option to a command in `src/irminsul/cli.py` warns on `docs/components/cli.md`,
which states no rule per option and sends a reader to `--help` for what a command takes, so the
only honest answer is a trailer that says so (a dogfood agent, 2026-11-26). On main that day, 14
commits carry a `co-change` trailer for `docs/components/cli.md` and 9 for
`docs/components/mcp-server.md`, most of them saying that the doc states nothing about what the
change touched, often a help string; a reader who writes that a fourteenth time is learning to
sign without reading. Asking only a doc that names, anchors or
claims what changed would change what the check reports and what the Decision of
`a-change-is-judged-from-its-merge-base-to-the-working-tree` says it asks for; the owner
deferred tightening `co-change` on 2026-11-26 until another change is measured.
`connected-doc-hides-unconnected-sections` is the opposite gap: one edit anywhere in the doc
answers the warning.

### `queue-is-unranked`

A feature that adds docs queues every sentence of them: 85 items for the dogfood budget feature,
about 70 of them the agent's own new sentences, with the claims whose evidence changed under a
doc nobody edited mixed in (2026-10-29). Group the plain output by marker, the items the change
did not write first.

### `change-queue-asks-through-functions-and-classes-alone`

Since 2026-11-26 `list review --changed` queues each sentence whose code span names a Python
function or class the change touched, marked `names-changed-code` (`_sentences_naming_changed_code`,
`src/irminsul/listing/review.py`), and pairs nothing else with a change (`ChangePairing`,
`src/irminsul/listing/changed_code.py`). That is the owner's decision of that day in the RFC
`a-change-re-asks-the-sentences-that-name-its-code`, taken after a first build that paired every
kind of name took the queue of the pull request `dde68e0..ffa39b4` from 48 items to 214. Run
that day with the rule as it stands over the same four ranges, the queue went from 0 to 0 items
for commit `460c44c`, from 26 to 27 for commit `9759e15`, from 48 to 51 for the pull request and
from 108 to 109 for `ffa39b4..55ab870`; 0, 6, 4 and 12 of them carry the marker, 17 of those 22
on a sentence the change itself wrote. Five items are about a sentence the change did not
write. One was worth the re-read: the sentence of `docs/components/checks.md` that names
`trailer_for`, queued by the pull request, which had also put that trailer in the JSON the
sentence leaves out; the one beside it, naming `acknowledge`, was still true. The other three are one sentence,
`docs/components/mcp-server.md:46`, which says what `create_server` records when it runs and was
queued by three of the four changes, each time because the change reworded the description of
a tool: every MCP tool is a function nested in `create_server` (`src/irminsul/mcp_server.py`),
so an edit to any of them changes that function's own lines, which is how the Decision of
`derive-facts-and-leave-meaning-to-the-reader` judges touched. Counting a function as touched
only by its lines outside the functions nested in it would drop those three; it changes what a
function's own lines are in that Decision, so it is the owner's call.

What the rule leaves out on purpose: a sentence that names only a command, an option, an
environment variable or a file is not asked about when the behaviour behind the name changes,
unless its doc owns the code or anchors the test that asserts it. The RFC leaves open pairing a
sentence with the part of a file it names, once `claim-evidence-names-a-part` gives the finders.
`460c44c` still prints "0 items", because no sentence names the functions it changed in a code
span, which is `connected-doc-hides-unconnected-sections`.

The measurement of 2026-11-25 that the entries beside this one cite: run with that day's code
over the three pull requests merged on 2026-10-30 and 2026-10-31 (heads `89772e4`, `dde68e0`,
`ffa39b4`) and two single commits, the queue held 189 items: 99 sentences the change itself
wrote, 29 summaries of docs whose body changed, 20 claims whose evidence file changed in a part
they do not rest on, 19 removed sentences, 8 with a wrong reference, and 14 worth the re-read. A
few of the 19 were list items a deletion had only renumbered, which are no longer queued. Eight
sentences those pull requests made false and did not edit were in no queue; four of the eight
name no code, which is `connected-doc-hides-unconnected-sections`. The owner's direction on
2026-11-25 is that this queue asks only about what the change did not write and may have made
stale, and leaves the sentences the change wrote to its reviewer; the accepted RFC
`the-change-queue-asks-about-what-the-change-did-not-write` carries it out. These counts replace
the ones in `queue-is-unranked`, measured before the fixes of 2026-10-31.

### `stale-summary-asks-after-any-body-edit`

`_stale_summaries` (`src/irminsul/listing/review.py:386`) queues a doc's `summary:` whenever a
body line changed and the summary line did not. In the measurement above, 29 of 30 such items
were summaries the edit could not have affected: "CLI entry point." for
`docs/components/cli.md` was queued by each of three consecutive pull requests. The decision
record says "a rewritten body", and one changed line is not that. Print them as one group that
closes the plain output, or decide what "rewritten" means; the second is a decision.

### `path-packet-pairs-every-code-span`

Since 2026-11-26 `irminsul context <path>` names the docs that name code in the path
(`_named_by`, `src/irminsul/context.py`). To count their sentences, `docs_naming`
(`src/irminsul/listing/review.py`) builds a `CodeResolver`, which extracts every surface and
indexes every function and class of the source, and pairs every code span in the docs, whatever
the path. `irminsul context src/irminsul/cli.py --format json` went from 1.5 to 2.6 seconds that
day, the median of fifteen runs on one machine, and an MCP caller of `context_for_path` waits as
long; building the resolver is 0.9 of the added 1.1 seconds. The JSON went from 26 to 32 KB,
with 50 docs under `named_by`, where a first build that listed each sentence gave 112 KB.
`list review --changed` on the pull request `dde68e0..ffa39b4` went from 2.3 to 3.0 seconds on
the same machine, because it builds a second resolver for the merge base. Not measured: which
surfaces a packet could leave unextracted without changing what a span names. Counting every
name Irminsul resolves to the path, as the owner decided later that day, left the packet for
`cli.py` at 50 docs and took `mcp_server.py` from 1 doc to 27 and `frontmatter.py` from 1 to 27,
through the MCP tools and the frontmatter fields their sentences name.

### `http-route-resolves-from-no-code-span`

`CodeResolver.resolve` (`src/irminsul/code_references.py`) finds an identity of a kind with no
mention pattern only when the span is identifier-shaped, and an HTTP route's identity, such as
`GET /items` from the `fastapi` pack, has a space and a slash. So a sentence that names
`` `GET /items` `` resolves to nothing: `irminsul context` does not count it under `named_by`
for the file that declares the route. With a `[[surface.rules]]` entry for kind `http` that gives a `mention_pattern`, the
same sentence counts (both run on 2026-11-26 in a scratch FastAPI project). A built-in mention
pattern for `http` would make it count everywhere, and would also make `code-references` and
the review queue read routes; that changes what a code span names, so it is a decision.

### `environment-variable-counts-for-one-file`

`EnvVarsExtractor.extract` (`src/irminsul/inventory/env_vars.py:68`) keeps one item for each
variable, from the first file that reads it, so a variable two files read is reported from one
of them. `irminsul context <path>` counts a sentence that names the variable under `named_by`
for that file alone (`docs_naming`, `src/irminsul/listing/review.py`): with `LEDGER_DATE_FORMAT`
read in `dates.py` and in `fees.py` of the `names-changed-code` fixture, the packet for `fees.py`
does not count the usage guide's sentence about it (run on 2026-11-26). `irminsul surface
env-vars` names one file for the same reason. Keep every file that reads a variable, which
changes what the surface prints.

### `lifecycle-queue-shows-no-progress`

`irminsul list lifecycle --queue` prints one line per accepted RFC, each ending "accepted RFC
is not yet implemented": ten lines alike but for the RFC they name on 2026-11-25, for RFCs of 2
tasks and of 27, five of whose tasks had landed. Which tasks are done is readable only from pull request titles, and
the order the RFCs depend on each other in only from their prose. Tasks T23, T25 and T27 of
`every-warning-hint-has-an-answer` (a checkbox per task and "N of M tasks done" in
`change status`) answer the first; the queue should print the same count.

### `no-measure-of-recall`

Nothing measures whether a code change that makes a sentence false leads a reader to that
sentence. A pilot on 2026-11-25 seeded 14 such changes into a clone of this tree, the sentence
chosen before the change and the doc left untouched, and ran `check --diff HEAD`,
`list review --changed` and `context --after-edit`. Three were pointed at by sentence, all
through an anchor or a claim. Six were pointed at by doc only, through `co-change`, which a
one-word edit elsewhere in that doc cleared in the two cases tried. Five were not pointed at:
the root `README.md` and `AGENTS.md`, a guide, a decision record whose `governs:` names the
changed function, and a code span in a doc that does not own the file. Every new finding was a
hint, so the gate an adopter is scaffolded with exited 0 in the three cases tried. Fourteen
cases chosen by someone who knew the rules give counts per kind of connection, not a rate. Keep
it as a fixture under `tests/fixtures/repos/` with one case per kind of connection and its
outcome asserted, so recall cannot fall unseen and the code-span cases change when the re-ask
RFC lands; a sampled run on this tree, with each case stored as a sentence and a patch, gives
the number. The owner decided on 2026-11-25 that `init` should scaffold a gate that fails on
hints as well, once every hint has an answer. That reverses the Scope of
`every-warning-hint-has-an-answer`, which keeps the scaffolded default at certain findings
alone, so it needs its own RFC.

### `no-command-lists-the-changes-a-test-misses`

A paragraph anchored to a test is guarded only as far as that test fails when its sentence
becomes false. Seeing it fail once is a written step of the agent protocol
(`docs/guides/agent-protocol.md`, "Tying a sentence to a test") that nothing verifies, and one
failure shows one way of breaking the code. The command the RFC
`a-sentence-about-behaviour-is-anchored-to-the-test-that-asserts` left out (decision 2 of
2026-11-26) would change a function in several small ways, run the tests its paragraphs are
anchored to, and list the changes no test noticed. It runs code, so it is no check, and each
language runs tests its own way. Recorded on 2026-11-26, when that RFC was implemented.

### `init-declares-no-test-roots`

`irminsul init` writes no `paths.test_roots`, and `SourceTree.test_walk`
(`src/irminsul/source_tree.py`) walks nothing without it, so in a freshly initialized
repository `anchors --suggest --doc <doc>` says "no test names it" and "no test file was read"
for a function its test calls, and `context <source file>` prints `tests: -` (both run on
2026-11-26). The agent protocol's step on finding a test now says so and sends the reader to
search the test files. Declaring the roots is the adopter's fix, and it raises
`test-ownership/unowned-test`, an error, for every test file no doc lists in `owns_tests`
(`src/irminsul/checks/owned_tests.py`), so the first declaration turns a passing repository
red. Decide whether `init` detects a test tree and declares it, and how the files in it that
predate adoption are excepted, as the adoption record excepts source files. Found by a review
of the RFC `a-sentence-about-behaviour-is-anchored-to-the-test-that-asserts` on 2026-11-26.

### `context-lists-no-tests-for-an-unowned-source-file`

`irminsul context <source file>` for a file no doc owns answers "no owning doc found", exits 1
and lists no test, even when a file under the declared test roots imports it (run on
2026-11-26): `Ranker.rank` (`src/irminsul/ranked_tests.py`) ranks the tests for an owning doc
(`src/irminsul/context.py`, where it is called once per owner), and an unowned file has none.
The agent protocol sends a sentence that names no code to this packet for its test, and an
undocumented file is where such a sentence is most likely. List the importing tests of an
unowned source file in the packet as well, with the reason each is listed. Found by a review of
the RFC `a-sentence-about-behaviour-is-anchored-to-the-test-that-asserts` on 2026-11-26.

### `suggest-hides-how-many-tests-name-a-definition`

`anchors --suggest --doc <doc>` offers at most three tests for a definition, the first by path
and line (`naming_tests` in `src/irminsul/binding.py`), and neither its plain output nor its
JSON says how many more name it. In this repository 23 tests name `acknowledge` and 14 name
`Finding` (counted on 2026-11-26), so three by path order says little about which assert the
sentence, and a reader cannot tell three from three hundred. Print the count beside the three,
and keep it in each row's JSON. Found by a review of the RFC
`a-sentence-about-behaviour-is-anchored-to-the-test-that-asserts` on 2026-11-26.

### `suggest-json-hides-that-no-test-was-read`

With no `paths.test_roots` declared, `anchors --suggest --doc <doc>` prints "no test file was
read" in its plain output alone (`_suggest_anchors` in `src/irminsul/cli.py`); in the JSON each
row's `tests` is `[]`, the same as for a function no test names, so an agent reading the JSON
cannot tell the two apart. The plain output also prints "no
test names it" under each name when it read no test at all. Found by a review on 2026-11-26.

### `a-file-level-rebinding-still-names-the-definition`

`anchors --suggest --doc` counts a test as naming a function when its body uses a name the
file imported from the defining module and the test does not bind itself. A test file that
imports `late_fee` and then rebinds it at file level, by `def late_fee`, an assignment or a
later import of another `late_fee`, still has its tests offered for the function
(`src/irminsul/binding.py`). Found by a review on 2026-11-26; no test of this repository does
it.

Two imports from the defining module itself are read the wrong way round too.
`_TestReader.file_imports` reads a file's imports from the last line to the first, so after
`from pkg.m import a as x` and `from pkg.m import b as x` a test that calls `x()` is offered
for `a`, where Python has bound `x` to `b` (run on 2026-11-27, on two lines, on one line with
`;`, and across the branches of an `if`, a `try` and a `match`). The order was an accident of
a stack walk and was kept on purpose when the module moved onto the language reader, a change
that was to alter no output. Reading the imports from the first line to the last fixes it; a
strict `xfail` in `tests/test_binding.py` holds the gap until then.

### `python-reader-lists-a-trys-else-before-its-handlers`

Python's reader says its definitions and imports are in source order, and for a `try`
statement they are not: `_statement_bodies` (`src/irminsul/languages/python_reader.py`) yields
the body, the `else`, the `finally` and then the handlers, so with an import on lines 2, 5, 8
and 11 of a `try` with an `except` and an `else`, `imports()` returns lines 2, 8, 11, 5 (run on
2026-11-27). The walk came unchanged from the code in `src/irminsul/anchors.py` that the
reader replaced.
What depends on it today is small: the order in which `anchors --suggest` lists the
definitions no anchor reaches, and which three it keeps, when one name is defined in both a
handler and the `else` of one `try`. Yielding the handlers second makes the docstrings of
`PythonReading.definitions` and `imports` true as the interface states them, and
`docs/components/languages.md` then loses its sentence about it. A strict `xfail` in
`tests/test_languages_python_reader.py` holds the gap until then.

### `a-redefined-class-is-reachable-and-does-not-resolve`

Python's reader answers two questions about a member of a class its file defines twice,
and the answers disagree. With `class A: pass` and then a second `class A:` holding
`def f`, `definitions()` gives `A.f` as `reachable`, while `canonical("A.f")` is None,
because `_find_symbol` descends into the first `A` and `_Walk` into each
(`src/irminsul/languages/python_reader.py`, run on 2026-11-27). So `anchors --suggest`
offers the marker `#A.f`, and pasting it reports `claim-anchor/missing-symbol`. The two
functions disagreed the same way while they lived in `src/irminsul/anchors.py`. One walk
should answer both; Python itself keeps the last `A`.

### `context-parses-every-file-a-reader-reads`

`context <path>` builds a `CodeResolver` to name the docs that name the path's code
(`docs_naming`, `src/irminsul/listing/review.py`), and the resolver's symbol index reads the
definitions of every source file a reader reads (`_symbol_index`,
`src/irminsul/code_references.py`), as `check` does. Measured on 2026-11-27: Python's `ast`
costs about 0.7 s per MB of source and a tree-sitter reader about 0.4 s, so a TypeScript
project of 2,100 files and 19 MB adds about 7 s to every `context` call, the command step 2 of
the loop runs before each edit. An index built for the names a call asks about, reading only
the files whose text holds the name, would cost what the call uses; it changes how a bare name
is found to be unique, so it wants its own measurement of how many names one call asks.

### `two-readers-of-what-typescript-exports`

`TypeScriptExportsExtractor` (`src/irminsul/inventory/exports_ts.py`) finds exports with
regular expressions, and the TypeScript reader finds the same declarations in the syntax tree
(`src/irminsul/languages/queries/typescript.scm`). They disagree: for
`export const a = 1, b = () => 2;` and `export default async function* walk() {}` the
extractor gives `a` and `default`, missing `b` and the name `walk`, while the reader gives
`a`, `b` and `walk` (run on 2026-11-27). The `exports` surface could be derived from the
reader's definitions under an `export`, which the reader does not say today; the record
`surface-rules-and-language-profiles-are-data` keeps surfaces as rules, so merging them is the
owner's call.

Until then a span that names an export is taken for the one definition of that name in
TypeScript or JavaScript (`CodeResolver.resolve`, `src/irminsul/code_references.py`), and
nothing checks that the definition is what the export exports: with
`export { handler as config } from "./impl"` in one file and an unrelated `function config`
in another, the span `config` names the function (by reading, 2026-11-27). The reader reads a
re-export as an import that binds nothing, so the name it exports under is not known to it.

### `a-tree-sitter-pin-hashes-some-layout-and-misses-three-changes`

The canonical text of a TypeScript, Go or Rust definition
(`TreeSitterReading._written`, `src/irminsul/languages/tree_sitter_reader.py`) leaves out
comments, a trailing comma and the tokens a query file marks as layout. A review on
2026-11-27 found both kinds of error by running each case. A formatter's rewrite that
changes a token moves the pin with no change of meaning: prettier's `x => x` to
`(x) => x`, `{'a': 1}` to `{a: 1}`, `'it\'s'` to `"it's"`, `0xAB` to `0xab`, gofmt's
`for ;; {}` to `for {}` and `for ; c; {}` to `for c {}`, and for a pin
on a whole file gofmt's sorting of an import block. And three pairs that differ in meaning
hash alike: in TypeScript `(a?.b).c` and `a?.b.c`, because a parenthesized expression is
written as what it holds (`typescript.scm`) and the parentheses end the optional chain; in
Rust `(a,)` and `(a)`, and `m!(a,)` and `m!(a)`, because `_trailing` drops the comma that
makes a one-element tuple. A parenthesized expression kept where it is the object of a
member, a call or a subscript would close the first, at the cost of a pin that moves when a
formatter removes needless parentheses there; the tuple needs the grammar's node kinds, which
the engine does not know.

### `a-python-source-root-that-is-its-own-package`

Python's reader places an absolute import under each source root
(`PythonReading.files`, `src/irminsul/languages/python_reader.py`). With the source root
`app`, which the init detector picks when a project's package is `app/`, the import
`from app.models import User` in `app/views.py` is looked for at `app/app/models.py`, so the
file `app/models.py` it does load is not found (run on 2026-11-27) and a true `depends_on`
between two docs under `app/` is reported by `import-deps`. Python's reader says it places
every import, which this breaks. Trying the root's parent when the root holds an
`__init__.py` would place it; it changes which imports back a dependency, so it is a rule.

### `typescript-go-and-rust-list-no-builtins`

Only Python's profile lists `builtins` (`src/irminsul/languages/python.py`). Since the other
three have readers, `CodeResolver.defines_symbol` answers for a project of theirs, so a doc
that writes `panic()` or `make()` where no source file spells the name gets
`code-references/unknown-symbol`, a hint with an ignore comment for its answer. Go's
predeclared names are a closed list in its specification; Rust's prelude and JavaScript's
globals are longer and move.

### `a-rust-unit-test-is-not-offered`

`anchors --suggest --doc` reads the test files under `paths.test_roots` that import a
definition's file (`Ranker.importers`, `src/irminsul/ranked_tests.py`), and a Rust unit test
sits in the file it tests, in `mod tests`, under no test root. The reader reads it as a test
(`tests.caps`), an anchor can name it, and the suggestion does not offer it (2026-11-27).
Offering it means reading a source file as its own test file and the `use super::*` of its
`mod tests` as the file's import of itself.

### `a-revision-places-imports-with-the-working-tree`

A reader places a Go or Rust import through a `go.mod`, a `go.work` or a `Cargo.toml`, and a
TypeScript or Go one through a directory's listing, each read from disk
(`src/irminsul/languages/manifests.py`). The merge base's files are read from git
(`SourceAtCommit`, `src/irminsul/listing/changed_code.py`), so the `new-dependency` pass reads
a changed file's old imports against the manifests and directories of the working tree: an
import of a file the change renamed is not found on the old side and is reported as new
(2026-11-27, by reading; Python has the same blind spot through `owner_of`, which asks the
disk whether a candidate exists).

### `prose-beside-a-comment-marker-is-misread`

The review queue reads no sentence on the lines of a multi-line HTML comment
(`src/irminsul/checks/code_spans.py`), and two edges of that reading are wrong both ways: prose
after `-->` on the line that closes a comment is dropped with the comment, though
`anchors --suggest` still reads a code span in it; and a comment opened after prose on a line
is read with that line, its words in the sentence. A review probe found both on 2026-11-26;
this repository's own `list review --all` is the same before and after the fix that skips
comment lines, 699 items each.

### `decision-edit-is-confirmed-twice`

The accepted RFC `decision-records-govern-what-they-decide` answers an edit of a record's
Decision twice: a dated item under `## Changes`, which `diff-integrity/change-unrecorded` asks
for, and a trailer, which answers `diff-integrity/decision-rewritten`. Both say that the
decision was changed on purpose and why. The owner asked on 2026-11-25 whether they can merge.
One finding answered by adding the dated item would do it: the item is in the tree, so it
survives a squash merge or a history reset, which a trailer does not, and the trailer stays
the answer of every other seal. Amend the RFC before its tasks T6 to T8 are built; accepting
the amendment is the owner's.

### `after-edit-names-plain-check-when-it-could-not-compare`

When `context --after-edit` judged a range and could not compare it, as in the two-repository
layout, its next action is the literal `irminsul check` (`src/irminsul/context.py:1782`) with
"The repository has errors to resolve". A finding raised by a pass that judges a change is not
in that plain run: with a check removed and committed without a trailer, the run exits 1, sends
the reader to `irminsul check`, which prints 0 errors, while `check --diff <base>` exits 1 (a
review, 2026-11-25). `_change_check_command` in the same file already builds the right command
for the compared case.

### `after-edit-in-a-pre-commit-hook-reads-the-commits-index`

Run from a pre-commit hook, `context --after-edit` builds its scratch checkout
(`pristine_checkout`, `src/irminsul/delta.py:250`) with git's `GIT_INDEX_FILE` still set to the
index of the commit being made. Under `git commit -a` the commit came out empty, and under a
plain `git commit` the checkout failed, so inherited debt failed every commit (a review on
2026-11-25, run on main). Clear the hook's git environment before that git call.

### `change-status-says-ready-before-any-work`

`irminsul change status` prints "mechanically ready for: implemented" for an RFC accepted the
evening before, with "0 changed path(s)" and none of its five tasks built (run on 2026-11-26 for
`the-change-queue-asks-about-what-the-change-did-not-write`). With no base given it finds no
blocker because it measured nothing. Say that nothing was measured, as `context --after-edit`
says of a change it did not compare.

### `body-matches-are-listed-in-path-order`

Among the topic matches that needed body prose, `_pending_for_topic`
(`src/irminsul/context.py`) orders by path once the other keys tie, so a doc under
`docs/foundation` sorts after the architecture, component and decision docs. When eight such
matches sort ahead of it, the case `a-topic-search-reads-doc-bodies` was written for, a non-goal
named only in the foundation's prose, is among the ids left out: `context --topic "will not"`
leaves `principles` out (a review, 2026-11-26). Which order serves a reader is a decision.

### `a-doc-that-restates-a-linked-doc-is-not-asked-about`

A sentence that links to another doc and says in its own words what that doc says is not
queued when the linked doc changes: `docs/guides/bootstrap.md` says what the baseline keeps
from blocking, links `docs/components/baseline.md`, and would not be asked about if that rule
changed. `irminsul refs` lists such sentences on request: 9 prose links to `baseline`, 10 to
`checks` on 2026-11-25. Queuing every link would bring back the length the change queue is
losing, since most links only point, and a link that only points cannot be made false by its
target. Add a seeded-rot case for it first, so the gap has a number.

### `a-retargeted-pull-request-keeps-its-old-gate-run`

`.github/workflows/ci.yml` runs on the default `pull_request` events, which do not include a
change of base. A pull request retargeted from a stacked branch to `main` on 2026-11-25 kept
the `dogfood` run made against its old base: `check --diff` then judged every commit `main`
had gained as later than the branch's trailers, and reported two findings the same command
with `main` as base did not. Only a new commit starts a run against the new base. Running the
job when a pull request's base changes is an edit to a gate file, which a trailer answers.

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
change to that code. A merge shows it too: after one branch was merged into another on
2026-11-25, each branch's trailer for `docs/components/mcp-server.md` counted the other's commit
as later, so the warning both had answered came back until a trailer on the merge commit, or on
one after it, answered it again.

### `renamed-doc-has-no-review-base`

`irminsul list review --written` compares a doc's sentences with the same path at the
base (`_prose_at_ref`, `src/irminsul/listing/review.py`). A doc the change renamed has
no base under its new path, so every sentence on a changed line is queued as `edited`: after
a `git mv`, an unchanged sentence sharing a line with a reworded one is queued too
(re-run on 2026-10-28). Read the base through the rename, as `renamed_paths`
(`src/irminsul/git/changes.py:362`) already finds it.

### `removed-sentences-queue-one-by-one`

`irminsul list review --written --base-ref` queues one `removed-sentence` item per deleted
sentence (`_removed_sentences`, `src/irminsul/listing/review.py`). A deliberate cut queues every
sentence of it: four items for a four-sentence paragraph, about 25 for one paragraph and
213 for the trim of `checks.md` in the PR 12 lanes. The reader has no way to say where a
cut sentence now lives, so the same cut is re-read at every run. Group removed sentences by
paragraph, pair a reworded sentence with its replacement, and let a reader name the home
once. Found by the PR 12a, 12c and 12d lanes on 2026-10-28.

The pairing has since landed, by position: within a run the change rewrote, the first new
sentence pairs with the first old one the file no longer has, and
`docs/components/new-list-regen.md` accepts that a sentence inserted before a rewrite takes the
`was` of the sentence the rewrite replaced, because a similarity threshold would guess. A
dogfood agent met it on 2026-11-26, and a scratch repository shows it: with "A lock is taken
first." inserted before "The store writes rows in order." was reworded, `--written` gave the
inserted sentence that `was` and the reworded one none. Pairing by similarity is the rejected
alternative that doc records, so changing it is the owner's call.

### `deleted-doc-queues-nothing`

A doc the change deleted whole queues nothing in `list review --written --base-ref`: its path
is not in `changed`, which `_removed_sentences` (`src/irminsul/listing/review.py`) walks, and
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

## Two repositories

Found by a trial of the `siblings` layout on 2026-11-25: a code repository and a docs
repository side by side, each with its own history, and a single-repository control. Checks
that read the tree, and pins, which hash content, behaved as in one repository. The layout stays
supported; these are what is left before a change in the code repository is judged as one in
the docs repository is.

### `siblings-change-views-read-the-docs-repository-only`

Every view of a change reads the docs repository's range alone: `co-change` (`change.changed`,
`src/irminsul/checks/co_change.py:69`), `new-dependency`
(`src/irminsul/checks/new_dependency.py:117`), `list review --changed`, `change verify`, and the
trailers (`reviewed_trailers`, `src/irminsul/checks/acknowledgement.py:248`). `--source-diff`
(`src/irminsul/cli.py:731`) reaches only `diff-integrity/adoption-debt-touched`, as the Scope of
`docs/guides/private-docs.md` says. In the trial a commit in the code repository made three
sentences and two claims false: `list review --changed` printed "0 items", `check --diff` with
`--source-diff` reported no `co-change`, and `change verify` read the RFC that commit
implemented as not started. Only a pinned architecture claim and one anchor reported. The
single-repository control reported `co-change/unreflected-change` and
`new-dependency/undeclared-new-dependency` for the same edit. `list review --changed` and
`change verify` do not say that a declared source was left out. Say so in both first; then give
every view of a change the source range, with a trailer read from the repository whose commit
it is on.

### `mtime-drift-is-the-only-cross-repository-signal`

`docs/guides/private-docs.md:206` names mtime drift as the cross-repository signal. Task T16 of
`every-warning-hint-has-an-answer` deletes that check and T22 makes `co-change` read the source
range in its place. Land T22 first or both in one change: T16 alone leaves this layout with pins
and nothing else. T22 also reads the trailers of the source range, which nothing reads today:
in the code repository's pull request the doc cannot be edited, so a trailer is the one
answer there, and a doc that is wrong has none.

### `siblings-time-signals-clear-on-any-doc-commit`

Where no pin exists, drift is a comparison of the code repository's commit time with the doc's
last commit: the fallback of `claim-provenance/evidence-drift`, `mtime-drift`, and `list review`
without a change. In the trial a one-word edit to the doc cleared `evidence-drift` on a claim
that was still false, though `anchors --re-pin --all` would still have moved its pin, and took
`list review` from three marked sentences to none. It is the second paragraph of
`component-claim-drift-unreported`, and in this layout it is the only signal unpinned prose has.

### `siblings-gates-deadlock-on-a-rename`

Each generated workflow checks out the other repository's default branch. With an exact path in
`describes`, renaming that file fails the code pull request against the docs' default branch
(`globs/empty-describes-pattern`, `uniqueness/undocumented-file`) and fails the docs pull
request against the code's, while the two heads together pass, a pair no workflow builds. A
glob in `describes` avoids it. Let each workflow check out the other repository's branch of the
same name when one exists, and say so in the guide.

### `shallow-source-clone-reads-as-drift`

`history-depth` asks the docs repository alone (`history_state(git, repo_root)`,
`src/irminsul/checks/history_depth.py:76`). With the code repository cloned at depth 1 and the
docs repository whole, every source file read as changed at the tip: two false
`mtime-drift/drift-detected`, exit 1 under `--fail-on hint`, and no
`history-depth/shallow-clone`. The generated workflows set `fetch-depth: 0`, so only a
hand-written checkout meets it. Ask each declared source too.

### `siblings-paths-have-two-spellings`

An anchor resolves only as `../code/src/ledger/store.py#open_store`, the spelling from the docs
root; `ledger/store.py#open_store`, the spelling `describes` takes, is
`claim-anchor/missing-file`, and `change finalize` refuses it as an unresolvable binding.
`recommended_tests: [test_store.py]` is `coverage/tests-path-missing` while `owns_tests` accepts
the same path. One spelling for a file in a declared source, in every field that names one.

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
four of them in code written the same day. Treat that surface as unsettled. The entries under
"Two repositories" are what a trial of it found on 2026-11-25.
