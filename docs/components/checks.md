---
id: checks
title: Checks
status: stable
depends_on:
  - config
  - docgraph
  - frontmatter
  - init
  - languages
  - new-list-regen
describes:
  - src/irminsul/checks/**
owns_tests:
  - tests/test_checks_adr_structure.py
  - tests/test_checks_anchors.py
  - tests/test_checks_boundary.py
  - tests/test_checks_change_binding.py
  - tests/test_checks_claim_anchor.py
  - tests/test_checks_code_references.py
  - tests/test_checks_coverage.py
  - tests/test_checks_dependency.py
  - tests/test_checks_doc_reality.py
  - tests/test_checks_doc_refs.py
  - tests/test_checks_doc_structure.py
  - tests/test_checks_env.py
  - tests/test_checks_external_links.py
  - tests/test_checks_foundation_readiness.py
  - tests/test_checks_frontmatter.py
  - tests/test_checks_globs.py
  - tests/test_checks_glossary.py
  - tests/test_checks_history_depth.py
  - tests/test_checks_liar.py
  - tests/test_checks_links.py
  - tests/test_checks_mtime_drift.py
  - tests/test_checks_new_dependency.py
  - tests/test_checks_orphans.py
  - tests/test_checks_parent_child.py
  - tests/test_checks_phantom_layer.py
  - tests/test_checks_pipeline_classes.py
  - tests/test_checks_reality.py
  - tests/test_checks_requirement_grammar.py
  - tests/test_checks_retired_references.py
  - tests/test_checks_rfc_follow_through.py
  - tests/test_checks_rfc_lifecycle.py
  - tests/test_checks_rfc_required_updates.py
  - tests/test_checks_schema_leak.py
  - tests/test_checks_stale_reaper.py
  - tests/test_checks_supersession.py
  - tests/test_checks_uniqueness.py
  - tests/test_diff_base_semantics.py
  - tests/test_diff_integrity.py
  - tests/test_diff_integrity_bypasses.py
  - tests/test_draft_status.py
  - tests/test_finding_codes.py
  - tests/test_finding_enforcement_class.py
  - tests/test_ignore_comments.py
  - tests/test_owned_tests.py
  - tests/test_walk_source_files.py
inventory:
  - kind: checks
    source: src/irminsul/checks/*.py
    explained_in: any
---

# Checks

Checks consume a [DocGraph](docgraph.md) and return `Finding` records with severity, message, and a path/line where applicable. The exact registry surface is defined by the registry in `src/irminsul/checks/__init__.py`.

**What a finding code means, and how to fix it, is `irminsul explain <code>`.** Every code carries its explanation beside the code that raises it, so this doc does not restate them — a second copy would be a cache of a derivable fact, and would go stale exactly where being wrong costs most. What follows is what that output cannot say: why the set is shaped this way, and where a check deliberately stops short.

The checks, grouped by what they govern:

- **The graph and its edges** — `frontmatter`, `doc-refs`, `links`, `orphans`, `supersession`, `phantom-layer`, `parent-child`, `uniqueness`, `globs`, `coverage`, `test-ownership`
- **Layer discipline** — `boundary`, `reality`, `schema-leak`, `foundation-readiness`, `terminology-overload`, `glossary-discipline`, `duplicate-block`, `section-reference`, `prose-file-reference`
- **Prose against code** — `claim-provenance`, `claim-anchor`, `code-references`, `inventory-drift`, `liar`, `requires-env`, `import-deps`
- **Records and lifecycle** — `rfc-lifecycle`, `rfc-follow-through`, `requirement-grammar`, `change-binding`, `adr-structure`, `retired-references`, `agents-manifest`
- **Elapsed time and the outside world** — `mtime-drift`, `stale-reaper`, `external-links`

`test-ownership` answers "who maintains this test", which `uniqueness` deliberately does
not: a test file is exempt from `undocumented-file` because it needs a maintainer rather
than a description. A doc names the test implementations it maintains in `owns_tests:`,
exactly one doc may name each, and the entries are exact paths — a glob would adopt
whatever is added later, and ownership is a decision somebody makes.

Which policy a managed file answers to is decided in one place and in one order: a
test-shaped name first, then a location inside a declared `paths.test_roots` that no source
root also claims, and otherwise `describes:`. That order is what lets Go's colocated
`parser_test.go` be a test wherever it sits, lets a helper under a declared `tests/` have
an owner without a test-shaped name, and keeps a repository pointing both roots at `.` from
putting ordinary source under the test policy. The declaration never decides:
`owns_tests: [src/important.py]` is reported rather than becoming a way for source to stop
needing a `describes:` owner, and `uniqueness` waives `describes:` exactly where this
policy takes over, so the two checks partition the managed files instead of both skipping
some.

Inside a declared test root the rule is closed — every test needs an owner, because
declaring the root is the act of agreeing to that — and outside one it spreads from where
it started, so switching the check on does not turn an existing tree red. A file whose name
waived `describes:` while no test policy took it is reported as `ungoverned-test-file`, a
hint: that gap used to be silent, and it is how an ordinary module named `test_refs.py`
escaped both checks.

Two of them report in one direction only, on purpose. `requires-env` reports a declared variable that neither the described source nor a `depends_on` dependency reads, never an undeclared read; `import-deps` reports a `depends_on` entry no import backs, never a missing declaration. Both fields are curated intent rather than an inventory — the complete list is derivable and would not need declaring — so only a declaration the code contradicts is wrong.

Whether a finding blocks follows its class, which each check declares for every code it explains ([Finding classes decide what blocks](../decisions/finding-classes-decide-what-blocks.md)). A **certain** finding proves the tree breaks a rule and is an error, such as an orphaned doc, an unknown id in `supersedes`, or a missing anchored file; a certain finding on a draft doc stays a warning only when its code is one the check declares in `drafts_exempt` — a missing `## Scope & Limitations` section or an unfinished requirements contract — because a half-written doc may be half-written but may not point at something that does not exist ([drafts excuse an unfinished doc](../decisions/drafts-excuse-an-unfinished-doc-not-a-wrong-one.md)). The same record is why a check that reads only stable docs does so for its hints alone and reports its certain codes on a draft too: skipping drafts outright would excuse every code the check has, and one word of frontmatter would clear them. A deprecated or removed doc describes what is gone, and is not read. A **hint** needs judgment and is a warning or info, such as `mtime-drift` or speculative wording. A **time** finding, such as a deprecated doc past its threshold, comes from elapsed time and is left out of a run given `--diff`. A test runs every check over the fixture corpus and fails if a check emits a severity its class does not allow.

Four of those class choices are worth the reasoning behind them. `doc-refs` is certain because a dangling `depends_on` edge silently weakens orphan detection and every other consumer of strong dependencies. `phantom-layer` splits on the INDEX's own status — an error when it is `stable`, an info hint when it is `draft` — because a draft INDEX marks a layer deliberately under construction, the state every freshly scaffolded layer starts in, rather than abandoned navigation. `foundation-readiness` reads a literal scaffold placeholder as a signal the project never ran [`irminsul seed`](seed.md) to capture real intent. And `requirement-grammar`'s findings only warn while an RFC is a draft but block `change transition ... accepted`, because acceptance freezes the contract to implement.

`liar` reports a doc that hand-lists a derivable code surface in prose, as a hint: once a doc names enough identities of one surface kind, it must either declare a curated `inventory:` subset or link to `irminsul surface <kind>`. Kinds whose identities docs name in context, such as options, check names, and config keys, are not counted across the doc; a single list or table naming five or more distinctive ones still counts as an enumeration.

`external-links` answers a link from its cache until the entry expires, so a result it did not request in this run is what the link returned when it was observed, not what it returns now ([context keeps no session; external checks may cache observations](../decisions/context-keeps-no-session-external-checks-may-cache-observations.md)). An `external-links/unreachable` finding built from a cached result gives its observation time in the message and in `data`, and a run that answered any link from the cache adds one `external-links/cached-results` info finding with how many and the oldest observation. An entry without a readable, time-zoned observation time, or dated in the future, counts as expired. <!-- irminsul:ignore reality/speculative-language reason="'future' dates a cache timestamp later than now; it predicts nothing" -->

`rfc-follow-through` asks a required-update doc for its `implements` back-link only once the driving RFC reaches `implemented`, because `rfc-lifecycle` rejects `implements:` on any RFC that has not ([Change lifecycle](../decisions/change-lifecycle.md)); asking earlier would tell an author, and `irminsul fix`, to write what the gate rejects. Between acceptance and finalization the pending work is already visible as `irminsul list lifecycle --queue`.

`adr-structure` keeps architecture decision records reviewable by reporting missing or duplicate canonical sections and an empty or placeholder-only `## Decision`, all certain findings. It is a shape check, not a lifecycle engine: RFC state remains in structured lifecycle metadata, and the check does not interpret an ADR's human-readable `## Status` prose.

The generic `supersession` check maintains reciprocal `supersedes` / `superseded_by`
metadata for ordinary documents. RFC records are excluded from that repair path:
their replacement graph is forward-only from the successor's `supersedes`, and
reverse successors are derived by [`change graph`](change.md). This prevents a new
proposal from demanding a metadata write to an implemented predecessor, which does not change.

`prose-file-reference` also audits its own exception markers as specified by
[Deterministic enforcement](../decisions/deterministic-enforcement.md). A line marker
is active only when its line still contains an unlinked local `.md` reference
after the marker comment is removed. A matched block is active only when an
enclosed, non-fenced line would independently trigger the check. Clean markers
produce one certain finding with `category: stale-suppression` and structured
line-or-block scope. The baseline never records it, so a baseline update cannot hide
an obsolete exception. Unmatched block markers are certain findings too, and marker
removal stays manual.

Every check, and the `co-change` and `diff-integrity` passes, honours the same comment form, in docs and in the guidance files `paths.extra_docs` names, for its own
name or one of its finding codes: a comment such as `<!-- irminsul:ignore reality reason="quoted" -->` covers its
line, or the next non-blank line when it stands alone, and an `ignore-start` and
`ignore-end` pair covers the lines between. The comment suppresses only hint and time
findings; a certain finding cannot be silenced from a doc. A comment inside a fenced code block is an example of the syntax and suppresses nothing; fences are read the CommonMark way, so a four-backtick example may quote a three-backtick block.
Every command that runs the configured checks drops the covered findings, and the check
command also reports misuse as certain `ignore-comment` findings: a name whose findings are all certain, an unknown name, an
unbalanced block, a comment for a check that ran but suppressed nothing, and a comment
with no `reason="..."` or a blank one. The reason is the whole reviewable record of why a
finding was judged wrong here, so it is required: a reasonless blanket block naming eight
checks used to take a doc's findings to nothing and explain none of it.

`globs` also warns when one display path names two files. The display
encoding is not injective — two configured roots outside the repo that both
hold `a.py`, or a sibling file whose display is also the name of a docs-repo
file no root covers, produce the same spelling — so no `describes` pattern or
`claims[].evidence` entry can name one of them, and nothing downstream can
disambiguate. Widening a configured root from `../code/src` to `../code` is
enough to hit it: the code repo's readme and agent manifest then collide
with the docs repo's own. A spelling the walk emits resolves to the walked
source file, so the docs-repo file is the one that becomes unnameable until
the root is narrowed.

`retired-references` builds its tombstone registry only from stable ADRs. A stale
reference is certain, so the gate fails without `--strict`, which is what makes a
retirement decision enforceable rather than advisory. An unmatched `agents-manifest:generated-start` marker in the agent
manifest is an error too — only a balanced pair blanks anything, because an
unclosed marker would otherwise switch the check off for the rest of the file.
The markers are read only in the manifest that `regen agents-md` writes, and
never inside a fenced example there, so quoting them in other guidance neither
opens a region nor hides anything. The tombstone-hygiene findings it
also emits — an inactive owner, a duplicate declaration, a retired CLI identity
that is live again — are certain findings too: each proves the registry is wrong.

It scans every stable and draft atom, frontmatter included, plus the current README, docs
README, glossary, contributor guidance, and the agent manifests, which are
high-traffic guidance that no doc atom covers. Out of range:
an ADR is never audited against the tombstones it declares itself, since a
decision has to be able to name what it retired; RFCs are frozen historical
record under [Change lifecycle](../decisions/change-lifecycle.md); and so are the generated navigation rows that echo their
titles. Deprecated and removed atoms, link destinations, URLs, and HTML comments are also
not treated as current claims. Phrases match whole tokens, never substrings, and
case is part of the phrase: a `cli-command` match is always case-sensitive, and a
`concept` match folds case only when the declaration is written entirely in lower
case. So a declaration like `sidecar mode` still catches a capitalised heading,
while a proper name such as `Topology A` cannot swallow the ordinary English
"whatever topology a project picks" — a tombstone that wants both readings lists
both spellings in `matches`. Fenced examples stay
visible because obsolete commands there are operationally dangerous — which
means a migration note showing the retired invocation has no in-fence remedy,
since a Markdown link cannot live inside a fence. Two answers exist and both
are deliberate: wrap the example in an HTML comment, which is not read as a
current claim, or keep it in the changelog, which is a migration record rather
than guidance and so lies outside the audit. A `draft` doc is not such a place: a
retired command is as wrong there as in a stable doc. Findings
aggregate repeated aliases per retirement and doc, and carry the declaring ADR,
guidance, first line, and occurrence count. An exact phrase linked to its owning
ADR is an explicit historical citation. CLI tombstones are first checked against
the derived live CLI surface: a reintroduced identity is reported on the ADR and
disables that tombstone for the run.

Four enforcements live outside the registries. The first is `co-change`. It needs a changed-file set from git, so it runs only when the [CLI](cli.md) is given `--diff <base>` (or the equivalent two-flag spelling `--base-ref`/`--head-ref`; the two forms are mutually exclusive). It is the only diff-precise signal; `mtime-drift` compares commit times, not a diff. Each source file changed in `<base>...HEAD` is resolved to its most-specific owning docs through the same `describes` glob logic as `uniqueness`; when none of a file's owning docs changed in the same diff, each owning doc gets one warning listing its changed-but-unreflected files. The warning is a hint, so `--strict` counts it toward failure like any other. A doc whose change is whitespace only does not count as having shipped: one blank line in the owning doc satisfied the check, which made the cheapest way to pass it an edit that says nothing.

The second is `diff-integrity`, which runs under the same diff range and compares each relevant file with its content at the merge base, so a change cannot pass by rewriting what should stop it. Git history is the seal: a pull request cannot rewrite what the merge base holds ([Git history seals implemented records](../decisions/git-history-seals-implemented-records.md)). `irminsul explain <code>` says what each of its findings means; what follows is why the pass is shaped this way.

**Protection is read from the base, never from the change under review.** Which folders hold sealed records, where the baseline lives, and whether a claim governs its evidence all come from the merge base — otherwise a change could lower its own protection in one commit and edit freely in the next. When the base config does not load, a hint says so and the change's own config is used; a repository with neither a config nor a baseline at the base is adopting Irminsul and has nothing to weaken, so the baseline its adopting change records is a first one rather than growth. A missing config alone does not make an adopter: a run without one still reads the baseline at its default path, so dropping the config in one change and bringing it back beside a bigger baseline in the next does not reset the ratchet.

**Deleting a declaration is how a doc stops asking about code that still exists.** An anchor, a `claims:` entry and an `inventory:` entry are each a doc asking to be told about specific code, so deleting one silences the question rather than answering it — and deleting it was the cheapest way to clear the finding it raised ([removing a claim about surviving code](../decisions/removing-a-claim-about-surviving-code-is-a-finding.md)). Three things are deliberately *not* removals: the code going away in the same change, which is the release valve and needs no ignore comment; another doc in the tree now carrying the declaration, so splitting a doc is free; and a rename, since a record is named by the slug of its title ([Records are named by slug](../decisions/records-are-named-by-slug.md)) and retitling one renames its file. A renamed record is still read at its old path, so the governance it dropped along the way is caught. Removing a `follows-evidence` claim is not reported at all: a report answers to its evidence, and one cheap enough to derive should not have been written down. A claim that governed its evidence at the base gets no release valve: deleting it, renaming it, or deleting its doc is `governing-claim-removed` even when its code goes too, and only a decision record naming it ends it ([a governing claim ends by decision](../decisions/a-governing-claim-ends-by-decision-not-by-deleting-its-evidence.md)).

**The [adoption record](adoption-record.md) is compared for three separate things, because its own contents answer none of them.** Whether an entry is still a live exception is read from ownership at the base, not from the record, since nobody is obliged to run `--update-adoption` and a stale record would otherwise hand an exception back to a file that had already grown out of it. Whether the *first* record's entries are the history they claim to be is read from the tree at the base, since the change that creates a record is trusted to write entries and would otherwise be trusted to invent them; a path the change only moved is followed back to where it came from. And deleting a record that still holds entries is a weakening like any other, because it restores the coarse covered-directory guess the record replaced. A fourth thing is compared only in a siblings layout: the revision the record pins for each source root in another repository, which may not move, because moving it forward turns everything that repository gained in between into pre-existing debt without a line being added to the record (`diff-integrity/adoption-source-rebound`).

**The historical question for a cross-repo entry is not a diff at all.** A source display in a siblings layout is relative to a root in another repository, and no revision of this tree ever held that path, so the merge base has nothing to say and the record names the source revision instead. That pin needs no base to read, so `uniqueness` asks it on every run — a plain `check`, a nightly, or a source-repository gate all reach the same verdict — and it is the check that grants the exception, which is the right place to refuse one. An entry the pinned revision did not hold is `adoption-record/debt-not-at-source-revision`, naming the file. An entry nobody can answer for is `adoption-record/source-unverifiable`, naming the record: the entries go on excepting their files, because calling them new would assert the opposite of what could not be checked, and the finding fails the run instead. Both are certain. `--source-diff` then supplies the sibling repository's own change range, and it reaches touch-to-own over recorded debt and nothing else — widening the rest would answer a question nobody asked, and co-change across a repository boundary is its own open design.

**Deleted prose is never a finding here.** No rule separates a deleted claim from a rewritten one, so `list review --changed` queues it with a `removed-sentence` marker instead of failing the run. The same reasoning makes a reworded claim a hint rather than an error.

The config seal reaches past `checks.enabled`: a per-check `enabled` turned off, a threshold widened so a check fires on less, or a repointed glossary are certain (`diff-integrity/setting-weakened`), a removed configured rule is a hint compared by what it watched, and a settings table nothing here judges is a hint saying so ([switching a check off is more than a list edit](../decisions/switching-a-check-off-is-more-than-a-list-edit.md)).

**The escape hatch is a decision record, not an ignore comment.** Turning a check off, moving the tree it judges, or editing a governing claim passes when a stable decision record the same change adds names the subject in a code span — so a person asking for the change leaves something reviewable behind.

**The workflows are compared too, because the diff-aware passes run only when CI asks for them**, which arms the seal with a flag living in a file the pull request may edit. A step that runs the composite Action counts as an invocation too, scored from its `with:` inputs as the flags the Action turns them into — `strict`, `fail-on`, and `diff` — so the workflows [`init`](init.md) scaffolds are sealed like a hand-written invocation of the CLI. A step that calls an action kept in the repository, `uses: ./` or a folder under it, counts the same way when that action's definition runs the check. There an input counts only while the definition still names the flag it becomes, so an action that stops passing `--diff` on is a weakening though no workflow changed. A fork or a Docker image has no definition in the repository to read, and is not scored. Strength is measured rather than tokens counted: `--strict` fails on three finding classes where `--fail-on time` fails on two, and `--diff` exits on a range `--base-ref` only warns about, so treating interchangeable spellings as equal accepted real weakenings. A fourth total counts how many checks an invocation runs: `--profile all-available` runs every implemented check and any other profile the enabled ones. Taking a check out of `checks.enabled` is reported on its own, so a narrower profile would otherwise be the one route to the same result that nothing watched. Every workflow at the base is compared with every workflow at the head rather than only the paths the diff lists, because git reports a renamed file under its new name alone, which would score the renamed workflow's base as empty and hide a weakening made in the same change. Totals are kept per triggering event. Within one event, moving a step between files is not a weakening; across events it is, so a gate added to a scheduled run does not pay for one taken off pull requests, which no scheduled run judges. A workflow stops counting for an event when its `on:` drops the event, when it leaves the folder GitHub reads, or when its YAML stops parsing, and a commented-out step counts as gone. So does a step whose result cannot fail the run — `continue-on-error: true` on the step or its job, an `if:` that is statically false, or a command ending `|| true` (or a block that sets `+e` or ends `exit 0`) — because a gate removed and a gate neutered leave CI equally unable to stop anything, while the flags stay where they were. Only a provably false condition counts: evaluating `github.event_name == 'pull_request'` would need the event, so anything else is read as running. An event's `paths:` and `paths-ignore:` filters are compared by what they admit rather than by their patterns, since a removed pattern proves nothing when a wider one may have replaced it. A file the gate reads, which is a doc, a claimed source file, a guidance file, the config, the baseline, or a workflow, that ran a gated workflow at the base and runs none now is a change the gate has stopped seeing, and the finding names it. A file the gate never reads is not evidence, so filtering an unfiltered gate down to what it reads is not a weakening, and neither is dropping the pattern of a source root that was deleted. A `branches:` filter is not compared. Diff findings are never recorded in a baseline, because a baseline could otherwise hide its own growth. Run locally, uncommitted changes count as part of the diff.

The fourth is `new-dependency`, which runs under the same diff range and reports an import edge the change *added* between two documented components when the importing doc's `depends_on` does not carry it. It is a hint and never a prohibition: nothing in the tree declares a forbidden edge, because a prohibition has to be written before the case that would justify crossing it exists, and once written it is a contract, so the cheapest way past it stops being revision and becomes evasion — an import moved inside a function, an indirection module — each worse than the honest dependency and none of them visible in review. The resolution is to declare the edge and say why, which is a reviewable one-line change to `depends_on`. Three deliberate narrowings keep it quiet: only edges new in the diff are reported, so an undeclared edge already in the tree needs no migration; only edges between two owned modules, since an unowned file has no doc to declare anything; and imports are read from the whole AST, so moving one inside a function does not evade it. Its reach is `import-deps`' reach — a dotted module path resolved under `source_roots` — so `from package import module` records the package, not the module, and an edge spelled that way is missed by both.

The third is `history-depth`, which judges the checkout rather than the tree, so no `checks.enabled` list can leave it out. `mtime-drift`, `stale-reaper`, `claim-provenance`, `rfc-follow-through` and `change-binding` answer their question from commit history; given a checkout without one they find nothing and report nothing, which reads exactly like a clean tree. A shallow clone — what `actions/checkout` produces by default — is an error naming the enabled checks that went blind (`history-depth/shallow-clone`), answered by `fetch-depth: 0`, which every workflow [`init`](init.md) scaffolds already sets. No git repository at all is a hint (`history-depth/no-history`), because a scaffold that is not committed yet is the ordinary case. Neither fires when no enabled check reads history, and that self-scoping is what lets the guard travel: the [change](change.md) lifecycle gates block on the same findings, and `change-binding` is on the list above, so a shallow clone used to turn it into a no-op and let a gate report success on the absence of evidence. A workflow that was not asking a historical question gains nothing to fail on. A third code, `history-depth/diff-unavailable`, is a hint reporting that `--base-ref`/`--head-ref` could not resolve their range, so the diff-aware passes did not run: those two flags degrade rather than exit, and the report, the JSON, and the CI annotations show that degradation rather than leaving it on stderr alone.

`adoption-record` is outside the list for the same reason, and it is worth saying why rather than only that. The [adoption record](adoption-record.md) grants exceptions to `uniqueness` *and* `test-ownership`, and `checks.enabled` is a list a repository writes — so reporting from whichever of the two happened to be listed meant a project running only `test-ownership` honoured a record nothing had validated: malformed JSON fell back to the progressive rule, and a cross-repository boundary nobody could read was accepted in silence. Validity is therefore asked once, here, and reported once: `adoption-record/unreadable` when the file does not load, `adoption-record/source-unverifiable` when nothing establishes that a cross-repo entry pre-dates adoption, and `adoption-record/debt-not-at-source-revision` when the pinned revision proves a recorded file was not there. All three are certain. The pass reports nothing when neither ownership rule is selected, because a record that excepts a finding nobody asked for is unused rather than wrong; the ownership checks consume the verified set and say nothing about the file it came from.

Checks are registered in `REGISTRY` keyed by name. The CLI selects checks with `--profile`: `enabled`, the default, runs the checks named in `checks.enabled`, and `all-available` runs every implemented check regardless of config. Every command that runs checks passes their findings through `checks/pipeline.py`, which applies classes and ignore comments, and each finding in JSON output carries its `class`.

## What a run consists of, and who decides

Two of the passes above are outside `REGISTRY`, which keeps `checks.enabled` from omitting them and settles nothing about the caller. `MANDATORY_PASSES` in `checks/pipeline.py` is that list, and `mandatory_findings` runs it; `irminsul check`, the [change](change.md) lifecycle gates, `irminsul context`, and the [MCP server](mcp-server.md) all go through it, so a run means the same thing wherever it is asked for.

The contract it keeps, stated once because it is the one a reader has to carry to any check: **a check may delegate error reporting only where the calling execution path guarantees that the responsible validation runs.** `uniqueness` and `test-ownership` swallow an unreadable adoption record deliberately — the pass above reports it, and reporting it twice would name the same file as both unowned and unverifiable. That delegation is sound exactly as far as the guarantee reaches. It did not reach `context` or the MCP server, both of which enumerated the registry themselves, and both answered a corrupt record with a clean repository: the ownership rule fell back to its progressive half, the file it would have blocked on sat in an uncovered directory, and nothing said a word. A test replaces every entry in `MANDATORY_PASSES` with a sentinel and asserts each entry point fired all of them, so a pass added later is covered by being added and an entry point that goes back to assembling its own run fails at once.

In JSON output (`--format json`) every finding carries two machine-actionable fields for agents. `data` is a structured decomposition of the finding — always with a kebab-case `problem` key and string values — or `null` where the check does not decompose that finding kind. `fixable` is `true` exactly when `irminsul fix` would plan a remediation for *that* finding, in which case the finding also carries a ready-to-run `fix_command`.

Both halves of that claim are load-bearing, and each constrains an implementation detail. Because `irminsul fix --check` only selects checks active under *its own* profile, the emitted `fix_command` repeats the profile the finding was reported under (`irminsul fix --profile all-available --check supersession`) — otherwise a finding surfaced by `--profile all-available` would advertise a command that silently no-ops under `fix`'s default `enabled` profile. And because some remediations are `requires_confirm` (they rewrite load-bearing metadata or prose), the command appends `--confirm` when any of the fixes it would plan is held back without it. Fixability is also per *finding*, not per doc: a check's `fixes()` discriminates on the finding's category, so an unfixable finding (a dangling `resolved_by`, a missing reverse `supersedes` pointer) stays `fixable: false` even when the same doc carries a fixable finding of another category.

## RFC checks

RFC rules are split by whether they block ([Change lifecycle](../decisions/change-lifecycle.md)).
Every `rfc-lifecycle` finding is certain: a record the lifecycle cannot
trust — no state, a dangling `resolved_by` or `implements`, or implementation evidence
ahead of finalization. It has no fixes, because `change finalize` is the only writer of
`rfc_state: implemented`.
`rfc-follow-through` reports outstanding work after a decision, several kinds of which
`irminsul fix` can complete; most of it is certain, and a draft RFC's past decision date
and an accepted RFC nothing followed up are time findings.

## Source inventory and glob resolution

The shared source walker applies built-in noise exclusions, repository-local `.gitignore`, and configured include/exclude patterns before any check or report sees a file. Directory symlinks are not traversed. A file symlink is inventoried under its lexical path only when its resolved target remains within the resolved configured source root; an escaping target is an error, while a broken target is a warning. Explicit external or symlinked source roots remain supported because the configured root itself defines the containment boundary.


## Scope & Limitations

Checks do not apply fixes — findings are advisory output only; call `irminsul fix` to remediate. They do not evaluate prose quality or writing style. They do not modify source files or docs, and neither the source walk nor the doc walk follows a directory symlink.

Three limits are deliberate, because each is a wide net on a hint and narrowing one would report things that are not wrong — which is what teaches an author to reach for an ignore comment. `code-references` treats a name as defined when it appears as a whole identifier anywhere in a source file, so a name surviving only in a comment or a string still resolves; it validates an invocation only when the code span names the project's own program, so an invocation of some other program, written without that program name, is prose. `claim-provenance` asks for a structured claim only in the `foundation` and `architecture` layers, so enforcement prose written in a component doc is not required to carry one; a claim written in any layer must still cite evidence that exists and fits its state, and a `claim:<id>` marker naming no declared claim is an error in any layer, because each is a broken reference rather than a missing claim. Valid evidence shows a claim points at something real, not that the claim is true. And a doc's freshness is its commit time, so a commit that touches a doc for any reason — a formatting sweep, a mass rename — resets `mtime-drift` and `stale-reaper` for it. Anchors are the precise instrument; the commit clock is the coarse net behind them.
