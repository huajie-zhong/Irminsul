# Changelog

## Unreleased

Gaps that fresh agents hit while adopting Irminsul in a small brownfield project and then
making a feature, a refactor and an RFC-driven change in it.

**Adopting and scaffolding.**
- `irminsul init` enables `agents-manifest` in the `irminsul.toml` it writes, in all three
  layouts. It scaffolds `docs/AGENTS.md`, whose table `irminsul fix` rewrites only through that
  check, so `fix` used to answer "no automatic fixes available" while the table missed every doc
  added later. The check stays out of the defaults, so a config that lists no `checks.enabled`
  and has no manifest does not start failing.
- `irminsul init --name <name>` names the project instead of the directory, in `irminsul.toml`
  and every doc that carries it, and answers the prompt for it. An empty `--name` exits 2 before
  anything is written.
- `irminsul seed` writes the idea and the first user into the architecture overview after the
  labels `**Built first:**` and `**First user:**`, with nothing after the answer, so an answer
  keeps its capital and a trailing period is not doubled.
- `irminsul new component` writes a guiding comment under the title: what a component doc says,
  and the three ways to tie a sentence to code, a code span (`Class.method` binds a method), an
  anchor marker that `irminsul anchors --suggest` prints, or a claim. `--from-surface` names every
  file with no surface in one note that says what a surface is.
- `frontmatter/missing-frontmatter` carries a suggestion: add a block on line 1 with the `id` the
  filename implies, a `title`, a `status` and a `summary`, and, for a file outside every layer
  folder, move it into its layer after `irminsul refs` shows what links to it.

**Findings and messages.**
- `check --diff` with a base that does not resolve, such as `origin/main` in a repository with no
  remote, still exits 2 and now says to pass a ref that exists there, such as the base commit or
  `HEAD~1`, or to fetch the base (`fetch-depth: 0` in CI).
- A name the enabled languages define themselves, such as Python's `IndexError` or `len()`, is no
  longer reported as unbound by `list review` and `anchors --suggest`, and `code-references`
  reads the same list for a bare `name()` call.
- `code-references` no longer reads the generated table of `docs/AGENTS.md`, which repeats the
  summaries of decision records and RFCs that are exempt in their own docs. It judges a code span
  in a doc's `summary:` at that doc, by that doc's rules.
- `duplicate-block/repeated-block` reads the WHEN and THEN items under a `#### Scenario:` heading
  as one block, so scenarios that share an outcome are no longer reported as a repeat to delete; a
  whole scenario copied still is.
- A string where a list of mappings belongs, such as a bare path under `required_updates:`, fails
  with the keys an entry takes (`path`, optional `reason`, optional `kind` of `create`, `update` or
  `review`), and `change transition <rfc> accepted` prints the same keys beside the empty list it
  writes.
- The `unreconciled-scope` blocker of `change verify` and `change finalize` says the change touches
  components the RFC's `affects` does not declare, to be added if the RFC covers them or moved out
  of the change. It no longer names a removed code or offers a "reviewed exception" nothing reads.
- `change finalize`'s `ambiguous-owner` blocker, when no component in `affects` claims a
  requirement's bindings, names the components that do and lists the declared ones to choose from.
- The `irminsul new rfc` template asks for the Problem's worked example in plain words, with exact
  commands, file names and ids under `## Design detail`, so following it no longer draws
  `rfc-structure/dense-paragraph`.
- A closed stdout ends the output: `irminsul anchors --help | head -1` exits 1 without a traceback
  on Windows and on POSIX, and never 0, so a gate cut short cannot pass. An error that names a file
  is still raised.
- Every finding code declares its answer, the one way a correct doc turns it green: `fix`, `line`
  (a reasoned ignore comment on its line), `pin` (a re-pin after re-reading) or `trailer` (an
  `Irminsul-Reviewed` commit trailer). `irminsul explain <code>` prints it, with the comment to
  write for a `line` code, `irminsul explain <check>` labels each code `(class, answer)`, and every
  JSON finding carries `answer` and `subject`, the item a sign-off names.
- The suggestion of a finding answered on its line ends with the ignore comment that waives it,
  naming its code, such as
  `<!-- irminsul:ignore code-references/unknown-path reason="..." -->`.
- An ignore comment standing alone above a fenced block covers every line of the block, and an
  `ignore-start`/`ignore-end` pair covers the fenced lines between them. A comment above a fence
  used to cover the first line after the fence instead, so one that relied on that is now
  reported as unused. A comment inside a fence is still part of the example and is not read.
- `code-references` asks a doc's `summary:` only its certain codes: an unknown function,
  variable or path there is no longer reported, because no ignore comment reaches a
  frontmatter line to answer it.
- `history-depth/no-history` suggests committing the tree, or running `--only` with checks that
  read no history, instead of disabling the checks that do.

**Queries.**
- `context <path>` for a file the adoption record excepts says, before the edit, that a change
  editing it must give it an owning doc in the same change, or `check --diff` fails with
  `diff-integrity/adoption-debt-touched` (`recorded_debt` on the unmatched entry in JSON).
- `context <path>` for a file that does not exist yet answers the other paths, marks it "(does not
  exist)", and names the doc whose `describes:` glob would own it, instead of exiting 2 for the
  whole call. A path outside the repository and every source root is still refused.
- `context --after-edit` with no `--base-ref` judges the working tree against `HEAD` as before and
  now says so: `co-change`, `diff-integrity` and `new-dependency` did not run, and `--base-ref
  <base>` runs them for the branch, or `--base-ref HEAD` for the uncommitted work (JSON `note`).
- `context --after-edit` leaves the baseline, the adoption record, the manifest and the guidance
  files out of its unmatched list, since none of them has an owner by design, unless a claim cites
  one as evidence.
- `list review --changed` prints what it compared with, `HEAD` or the merge base of `--base-ref`,
  and without a base, when the branch holds commits the default branch lacks, says that
  `--base-ref` covers them (JSON `base` and `note`).
- `list review` no longer splits the marker of a numbered list item, such as `1.`, into a sentence
  of its own, and without `--changed` it lists every code-naming sentence of a doc no commit holds
  yet, instead of reporting that none changed since the doc was last committed.
- `irminsul refs` accepts any Markdown file in the repository as a target, so a brownfield page
  with no frontmatter can be asked what links to it before it is moved.

## v0.4.1

The 0.4 release on Irminsul's restarted history, and the one to install. 0.4.0 was published
from a history that `main` no longer holds, so it is withdrawn: its tag and release page are
removed, and its PyPI files stay, so an install that pins 0.4.0 still works. 0.4.1 holds
everything in 0.4.0 and the changes below.
From 0.4.0, the one edit an upgrade can need is a link written for a heading's old slug, which
`links/unknown-anchor` now reports. The known limitations listed under 0.4.0 still hold.

### What changed

- `check --diff` no longer compares a change with the accepted RFCs' `affects`:
  `change-binding/touched-but-undeclared` and `change-binding/declared-but-untouched` are
  removed, because a pull request is for one RFC and the union of all of them is not that RFC.
  `change verify <rfc>` and `change finalize <rfc>` compare it with the RFC they are given, as
  before. `change-binding` keeps `missing-affects` and `unknown-component`, and no longer counts
  as a check that reads commit history.
- `code-references/option-not-on-command` reads a Typer command's options the way the
  `cli-options` surface does, so an option declared through a module-level alias or by a
  default value is found on its command, and a docstring that mentions an option no longer
  counts as declaring it.
- `rfc-follow-through/missing-required-update-path` no longer reports a `required_updates`
  entry of `kind: create` before its RFC is implemented, since the doc is what the
  implementation writes. Finalizing the RFC still requires it to exist.
- `supersession/status-not-deprecated` accepts `status: removed` on a superseded doc as well
  as `deprecated`, so the step `stale-reaper` recommends for an aged deprecated doc no longer
  fails the check; `irminsul fix` leaves a removed doc as it is.
- `phantom-layer/hollow-layer` and `layer-under-construction` count a doc in any folder
  beneath the INDEX's folder as content, so a layer whose docs all live in subfolders is no
  longer reported as hollow.
- `links/unknown-anchor` anchors a heading as GitHub does: `## Scope & Limitations` is
  `#scope--limitations` (no hyphen collapses), a repeated heading is `-1`, `-2`, and a
  percent-encoded fragment is decoded. A link written for the old slug, such as
  `#scope-limitations`, is now reported; it never worked on GitHub.
- An RFC is written in two parts: an owner's part first (Summary, Problem, How it works, Cost
  and risk, Decisions) and an agent's part from `## Design detail` on (Requirements and Tasks
  as before). Every RFC declares `weight: small` (a sign-off: Summary and Decisions only) or
  `weight: large`. `irminsul new rfc` writes the large shape and `irminsul new rfc --small` the
  small one ([RFCs have four states, and git history seals decided records](docs/decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md)).
- New check `rfc-structure`, for draft and accepted RFCs: a missing weight, a missing or empty
  owner's section, and an owner's section after `## Design detail` are errors, and an owner's
  paragraph with four or more code spans is a hint. An existing config lists its checks, so it
  runs only once added to `checks.enabled`; `irminsul init` enables it.
- `irminsul refs` lists everything that names a doc: an RFC whose `resolved_by` names a
  decision record is listed under that record, at the key's line, and no longer the record
  under the RFC, and `context`'s `depended_on_by` follows. Links in guidance files, such as the
  root `AGENTS.md` and `docs/AGENTS.md`, count as weak hits with a `doc_id` of `null`, and a
  guidance file can itself be the target.
- A frontmatter value that starts with `!`, which YAML reads as a tag, gets a parse error that
  says to quote it.

## v0.4.0

A breaking upgrade from 0.3.0. It removes the commands, flags, checks and finding codes that
answered a question another one already answers, merges what remained into one command per
question, and makes the everyday runs faster. A removed spelling stops with exit 2, and six
of them name their replacement. A repository that adopted 0.3.0 needs a few targeted
edits, listed under *Upgrading from 0.3.0*, and one decision record in its upgrade change.

### What changed

**Commands** ([One command per question, and one rule per flag](docs/decisions/one-command-per-question-and-one-rule-per-flag.md)).
- The baseline and the adoption record have commands of their own: `irminsul baseline init`
  and `baseline update`, `irminsul adoption init` and `adoption update`.
- `context <path...>` and `context --topic <query>` run no checks. `context --after-edit` does,
  and with a base (`--base-ref`, `IRMINSUL_BASE_REF` or `GITHUB_BASE_REF`) it judges the change
  `check --diff` judges, so `co-change` and `diff-integrity` speak before you commit.
- `check --only <check>` runs any registered check and takes a comma list, as `fix --only`
  does. `--committed-only` leaves uncommitted work out of a change. `anchors --re-pin --doc`
  takes `--claim`, `--evidence` or `--anchor` to re-pin only what you re-read.

**Checks and findings.**
- New certain codes: `frontmatter/missing-summary`, since every doc carries a one-sentence
  `summary:` that the agent manifest lists
  ([Docs are atoms in six layers, and code has one owner](docs/decisions/docs-are-atoms-in-six-layers-and-code-has-one-owner.md));
  `frontmatter/retired-field`; and `diff-integrity/gate-file-changed`. New hint:
  `code-references/unknown-path`, a code span written like a file path that names no file.
- Under `--diff`, every config setting and every workflow or `action.yml` that mentions
  irminsul is compared with the merge base, and gate strength is no longer scored: an edit is
  answered by a stable decision record the change adds, naming it in its `## Decision`
  ([A change may not lower its own gates](docs/decisions/a-change-may-not-lower-its-own-gates.md)).
- `check --diff <base>` judges from the merge base to the working tree, uncommitted work
  included, and `--diff HEAD` means that work alone
  ([A change is judged from its merge base to the working tree](docs/decisions/a-change-is-judged-from-its-merge-base-to-the-working-tree.md)).
- The checks that judged what prose means from word lists are gone: `liar`, `reality`,
  `section-reference`, `terminology-overload`, the `claim-provenance` hints that asked prose
  for a claim, and `glossary-discipline/redefined-term`; `list review` selects by facts too
  ([Derive facts and leave meaning to the reader](docs/decisions/derive-facts-and-leave-meaning-to-the-reader.md)).
- A code span is a literal mention, so `prose-file-reference` judges plain text only
  ([Code is named in code spans and bound by anchors](docs/decisions/code-is-named-in-code-spans-and-bound-by-anchors.md)).
  Links resolve as GitHub resolves them, `<a href>` included. Frontmatter is read as YAML 1.2.
  A baseline records certain findings only
  ([A baseline holds certain findings and grows only by decision](docs/decisions/a-baseline-holds-certain-findings-and-grows-only-by-decision.md)),
  and the `change` commands judge an RFC by one gate
  ([RFCs have four states, and git history seals decided records](docs/decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md)).
- A Python anchor or claim pin hashes the syntax tree, not `ast.unparse`, whose output changes
  between Python patch releases, so a pin written on one interpreter matches on every other
  ([Code is named in code spans and bound by anchors](docs/decisions/code-is-named-in-code-spans-and-bound-by-anchors.md)).
- Surface rules are `[[surface.rules]]`, and a language profile's `suffixes` is the one list
  of its files: TypeScript's include the JavaScript suffixes, and Ruby is no longer read for
  environment variables
  ([Surface rules and language profiles are data](docs/decisions/surface-rules-and-language-profiles-are-data.md)).

**The agent guidance `init` writes** ([Agents get stateless read-only queries and one written loop](docs/decisions/agents-get-stateless-read-only-queries-and-one-written-loop.md)).
The loop and the posture live once, in the root `AGENTS.md` between
`<!-- irminsul:agents-start -->` and `<!-- irminsul:agents-end -->`; an `AGENTS.md` you
already have gains that section at its end, and `init --force` replaces only the section.
`.claude/skills/irminsul/SKILL.md` is a pointer of under 200 words, where 0.3.0 wrote a
1,200-word copy. `init` detects Go and Rust, and `seed` writes only the principles doc and the
overview ([Init adopts in two layouts, and seed fills two docs](docs/decisions/init-adopts-in-two-layouts-and-seed-fills-two-docs.md)).
The MCP server refuses every call once irminsul's own code changes on disk under it.

**The Action** ([CI runs each gate once, and the Action takes typed inputs](docs/decisions/ci-runs-each-gate-once-and-the-action-takes-typed-inputs.md)).
New inputs `path`, passed as `--path`, and `source-diff`, passed as `--source-diff`, are empty
by default; `profile` and `strict` are gone. The `docs-pr.yml` that `init` writes has no
`paths:` filter, and the `siblings` workflows call the Action with `path` naming the docs
checkout instead of installing the CLI.

**Speed.** On this repository's own v0.3.0 tree with the same checks, `irminsul check` takes
2.8 s where 0.3.0 takes 6.7 s (9.2 s with its default set), on one Windows machine.
`context <path>` answers in about a second, where 0.3.0 ran every check unless given
`--before-edit`, and `change finalize` runs the checks once instead of twice.

### Upgrading from 0.3.0

Move the CLI and the workflow pin in the same change: 0.4.0 refuses a config that names the
removed checks, and 0.3.0 refuses one with `[[surface.rules]]`. Python 3.12 or newer, as
before. Do not repair with `irminsul init --force`, which replaces every scaffold file.

**1. The config does not load (exit 2) until it is edited.**
- Delete `"liar"`, `"reality"`, `"requires-env"`, `"terminology-overload"` and
  `"section-reference"` from `checks.enabled`; every config 0.3.0's `init` wrote names all
  five. Delete any `forbid_speculation` layer key, `[checks.terminology_overload]` table and
  `prose_named` key.
- Rename each `[[checks.inventory_drift.generic]]` to `[[surface.rules]]` and write
  `glob = "x"` as `globs = ["x"]`, as the error says; `--diff` does not report the rename.
  Ruby's environment variables need a `[[surface.rules]]` rule of kind `env-vars`.

**2. Removed commands and options exit 2.** The first four rows print what replaced them, such
as `` `--strict` is now `--fail-on hint,time` ``; the rest get the CLI framework's
`No such option` or `No such command`.

| 0.3.0 | 0.4.0 |
|---|---|
| `check --init-baseline`, `--update-baseline` | `irminsul baseline init`, `baseline update` |
| `check --init-adoption`, `--update-adoption` | `irminsul adoption init`, `adoption update` |
| `check --strict` | `check --fail-on hint,time` |
| `context --before-edit <path>` | `context <path...>` |
| `context --changed` | `context --after-edit` |
| `--profile` on `check`, `fix` and `context` | `checks.enabled`, or `--only <check>` |
| `fix --check <check>` | `fix --only <check>` |
| `list review --base <ref>` | `list review --base-ref <ref>` |
| `check --base-ref`, `--head-ref` | `check --diff <base>` |
| `--dry-run` on `change transition`, `finalize` | the same command without `--confirm` |
| `seed --json` | the answer flags with `--no-interactive` |
| `refs --symbol <name>` | a text search of the tree |
| `status` | `orient` for coverage, `check` for findings |
| `regen agents-md` | `irminsul fix` |
| `list orphans`, `list stale` | `check --only orphans`, `check --only stale-reaper` |
| `change graph`, `change impact` | the RFC's `supersedes` and `depends_on`; `context --after-edit` |
| `check --pin-adoption-sources` | nothing: no release wrote an unpinned record |
| `irm` | `irminsul` |

**3. Exit codes.** `refs`, `explain` and `context` exit 2 rather than 1 for an argument that
names nothing (a missing doc, an unknown code, a missing path), and so does a git failure
under `context --after-edit`. `baseline init` and `adoption init` exit 1 when the file already
exists, where `check --init-baseline` exited 2. Exit 1 still means a command ran and refused
what it found, as `change finalize` now does on a tree with uncommitted work.

**4. JSON and MCP.** A finding's `category` key is gone: read `code`. `context` drops
`validation.checks_passed` (read `validation.repository.state`) and `workflow`, and its `mode`
is `path`, `topic` or `after-edit`; `change status` and `verify` rename `test_evidence` to
`changed_tests`. Over MCP, `context_changed` is `context_after_edit(base_ref)`,
`context_for_path` takes a list, `check` takes `only` for `profile`, and `change_impact`,
`binding_readiness` and the `list_docs` kinds `orphans` and `stale` are gone.

**5. The docs.** These are the findings 0.4.0 adds to a 0.3.0 tree.
- `frontmatter/missing-summary`: give every doc a one-sentence `summary:`, each INDEX and the
  `adopt-irminsul` record included; only an accepted record's `## Decision` is sealed. An
  implemented RFC is passed over.
- `frontmatter/retired-field`: rename `tests:` to `recommended_tests:`; delete `superseded_by:`;
  replace `requires_env:` with an `inventory:` entry of kind `env-vars`; delete an inventory
  entry's `fingerprints` and anchor the symbol. A duplicate key, or a block that does not open
  on line 1, is now `frontmatter/parse-error`.
- Delete each ignore comment naming a removed check or code (`ignore-comment/unknown-check`).
  `irminsul:ignore prose-file-reference` is now `ignore-comment/certain-finding`: delete it, or
  name `code-references` where its span is an example path. The same comment answers the
  `code-references/unknown-path` hints on the scaffold's examples, `components/foo.md` in
  `docs/CONTRIBUTING.md` and `@AGENTS.md` in `AGENTS.md`, as 0.4.0's scaffold does.
- A link that climbs out of its repository is now `links/broken-link`: link a file in another
  repository by its full URL, or name it in a code span.
- `foundation-readiness` reads a marker 0.3.0 scaffolds lack, so it no longer reports an
  unedited 0.3.0 principles doc or overview. Re-read them.
- `baseline update` drops entries for removed checks. To hold the new findings instead, delete
  the baseline, run `irminsul baseline init`, and name the file in the record of step 8.
- Every anchor and claim pin 0.3.0 wrote reads as `claim-anchor/pinned-drift` once, though no
  code changed, because 0.4.0 hashes a Python pin over its syntax tree. In a commit of its own,
  before any other edit, run `irminsul anchors --re-pin --all` twice: a claim that cites a doc
  changes when the first pass re-pins that doc's anchors. This is a format migration, the one
  time a whole-tree re-pin is right.

**6. The agent guidance.** Nothing makes you replace the 0.3.0 `AGENTS.md`, skill and
`docs/guides/agent-protocol.md`, but they send an agent to `context --before-edit`,
`context --changed`, `regen agents-md` and `refs --symbol`. Delete
`.claude/skills/irminsul/SKILL.md`, and `AGENTS.md` and `agent-protocol.md` if you never
edited them, and run `irminsul init`: it writes only missing files, and appends its marked
section to an `AGENTS.md` you kept, linking an `#acting-on-a-finding` heading that a kept 0.3.0
`agent-protocol.md` lacks. In what you kept, `docs/AGENTS.md` and `docs/README.md`, replace
those commands as the table says.

**7. CI.** A workflow pinned `huajie-zhong/irminsul@v0.3.0` keeps running 0.3.0, since the
Action installs the CLI from its own ref. When you move it to `@v0.4.0`, replace `strict: true`
with `fail-on: hint,time` and delete `profile:`: GitHub only warns about an input an action
lacks, so the run would quietly ask less. Delete the `paths:` filter in `docs-pr.yml`, which
leaves out test roots, so a required check stays Pending on a pull request touching only
tests. A 0.3.0 `siblings` workflow runs `pip install "irminsul==0.3.0"`: change the version in
`docs-pr.yml`, `docs-nightly.yml` and the code repository's `code-pr.yml`.

**8. One decision record.** 0.4.0 judges the upgrade change, and reports
`diff-integrity/check-disabled` for each check dropped and `diff-integrity/gate-file-changed`
for each workflow edited. Add a record with `irminsul new adr "<title>"` to that change, set
`status: stable` and a `summary:`, and in its `## Decision` name the five checks, each
workflow file by its path, and the baseline file if step 5 re-created it, each in a code span.

### Known limitations

These are the gaps a reviewer still has to cover. Each is a place where a green run proves
less than it looks.

- **Claim evidence in component docs is never re-asked.** `claim-provenance/evidence-drift`
  judges the foundation and architecture layers only, yet `anchors --re-pin --doc` still moves
  a component claim's pins, acknowledging code nobody re-read. In any layer, a pin that no
  longer matches falls back to commit times, so a doc committed after its evidence hides it.
- **One connection makes a whole doc look current.** `co-change` is satisfied by an edit
  anywhere in the owning doc, and a sentence that names, anchors or claims no code is never
  re-asked when that code changes.
- **The gate seal is textual.** It covers `.github/workflows/` files and `action.yml` files
  that mention irminsul. A script a workflow runs, a reusable workflow from another
  repository and branch protection are outside it, and a record naming a file excuses any edit.
- **A removed setting is not compared.** The base config is read through the current schema,
  which drops keys it lacks, so a change that removes or renames a setting is never judged.
- An ignore comment cannot answer a finding without a line: every `co-change`,
  `diff-integrity` and `history-depth` finding, and `claim-provenance/evidence-drift`. A
  comment naming one of those passes is never reported unused, nor are its other names.
- `claim-anchor/unpinned` is an info hint that never fails a run, so an anchor pasted from
  `anchors --suggest` can stay unpinned and never notice its code changing.
- An RFC's `supersedes:` is not checked, a code span naming a module-level constant is not
  paired with its definition by `list review`, and `list review --base-ref` queues nothing for
  a doc deleted whole.
- **An adoption boundary is checkable, not approved.** Git proves that a path existed at the
  pinned revision: a file merged the day before adoption is debt exactly like one there for a
  year, and a record pushed straight to an unprotected default branch skips the only base case
  the inductive validation has. Review the adopting commit.
- **A source-repository gate reports until it is required**, and nothing seals it, since it
  lives in a repository the docs gate cannot read. `--source-diff` reaches only touch-to-own
  over recorded debt, so a source change whose owning doc was not updated goes unreported.
- The adoption record names exact paths, so a moved file is documented at its new path.
  Cross-repository adoption shipped without a clean external review; treat it as unsettled.

### Decision records

Each change above links the record that is its reason; all fifteen are in `docs/decisions/`.
Two hold rules the others build on: [Finding classes decide what blocks](docs/decisions/finding-classes-decide-what-blocks.md)
and [Authority follows the kind of claim](docs/decisions/authority-follows-the-kind-of-claim.md).

## v0.3.0

The first release from this repository, and a breaking upgrade from 0.2.0 on PyPI.

### What Irminsul does

Irminsul is a Python CLI (`irminsul` / `irm`) plus a composite GitHub Action that checks a
repository's `docs/` tree against its code in CI. Every check is deterministic: the tool
makes no model calls, and a run is reproducible from the repository alone.

- **Structure.** Validated frontmatter, `describes` ownership of every source file,
  resolving links and globs, tests declared for component docs, and an RFC lifecycle bound
  to repository evidence.
- **Derived surfaces.** `irminsul surface` rebuilds a code surface on demand — `cli`,
  `cli-options`, `env-vars`, `exports`, `http`, `mcp`, or a kind the project configures —
  from framework packs for Typer, Click, argparse, FastAPI, Flask, MCP tools, cobra, clap,
  commander, and Express. A doc links or derives rather than hand-copying, and `liar`
  reports prose that hand-lists a derivable surface.
- **Curated knowledge stays honest.** `inventory:` watches a named subset of a surface,
  anchored claims pin prose to a symbol's current shape, and `irminsul list review` queues
  the sentences whose code changed after the doc.
- **Agents.** `irminsul orient`, `context`, `refs`, `check` and `explain` are available
  over the CLI and a read-only MCP server, and `irminsul fix` applies the remediations a
  check supplies for its own findings.
- **An existing backlog does not have to be paid off first.** `check --init-adoption`
  records every managed file that has no owning document today, by exact path, so ownership
  can be switched on over a repository that has never had it. Those files are excepted from
  the one finding that says a file has no owner — nothing else. Every check runs on them
  from the first day, and each exception retires the moment its file gains an owner, is
  deleted, or is moved. The record only shrinks: the pull-request gate refuses a change that
  grows it, that edits recorded debt without documenting it, or that hands back an exception
  the merge base had already retired.
- **Documentation and code may live in separate repositories.** In the `siblings` layout a
  declared source names the code repository and the branch whose history an adoption
  boundary has to sit on. Each recorded entry states which repository it came from, and each
  is checked against the pinned revision on every run — a boundary that cannot be read fails
  the run rather than passing quietly.

### Adopting it

```
pipx install irminsul && cd your-repo && irminsul init
```

`init` scaffolds `docs/`, `irminsul.toml`, CI workflows, and the agent-harness wiring, in
either the `same-repo` or `siblings` layout.

**Two starting states, two commands, and they are not interchangeable.**
`check --init-baseline` records the *findings* an existing tree already has.
`check --init-adoption` records the *files nobody has documented yet*. A baseline cannot do
the second job: on the day you adopt, no document claims anything, so no directory is
covered and the ownership findings do not exist yet — by the time they appear they are new
findings, which a baseline is forbidden to absorb. Run the adoption record if `check`
reports unowned source files you are not ready to document. Both only ever shrink.

For a docs repository beside a separate code repository,
`irminsul init --topology siblings --code-repo <spec>` scaffolds the workspace and writes a
second workflow for the code repository to copy in. To *adopt* from that repository, declare
it:

```toml
[[paths.sources]]
name = "engine"
path = "../code"
ref = "origin/main"
```

`ref` is the history the boundary must be part of; a bare branch name is refused, because in
a checkout that is the local branch. Both checkouts need `fetch-depth: 0` so the pinned
revision is present.

Irminsul reports. Whether a finding blocks a merge is branch protection on your repository,
which this tool can neither set nor see — `init` prints the check names to require, in each
repository.

Every finding carries a class that decides whether it blocks — **certain** (the tree
provably breaks a rule), **hint** (needs judgment), or **time** (elapsed time or the
outside world). `irminsul explain <code>` prints the class, what the code means, and how
to fix it.

Python 3.12 or newer.

### Known limitations

These are the gaps a reviewer still has to cover. Each is a place where a green run proves
less than it looks.

- **The gate seal reads two spellings of the gate.** `diff-integrity/gate-weakened` scores
  an `irminsul check` run step and the published Action (`owner/irminsul@ref`). It does not
  see a gate called as a local action (`uses: ./…`), from a fork, or from the Docker image;
  a narrower `--profile`; a narrower `paths:`, `paths-ignore:` or `branches:` filter; or a
  step made non-blocking with `continue-on-error`, `if: false`, or `|| true`. A workflow
  changed in one of those ways needs a reviewer's eye.
- Gate strength is totalled per triggering event, so a flag moved between two workflows
  that run on the same event balances.
- An ignore comment cannot suppress a finding that carries no line, which is every
  `co-change`, `diff-integrity` and `history-depth` finding and
  `claim-provenance/evidence-drift`. A comment naming one of those three passes is never
  reported as unused.
- The MCP `check` tool, `irminsul context` and `irminsul status` run the registered checks
  *and* the passes no run may omit — `history-depth` and the adoption-record validation —
  but not the unused-ignore-comment audit, which needs the set of checks that ran to know
  whether a comment went unused. So they can report fewer errors than `irminsul check` does,
  by that one audit. `irminsul orient` reports only what elapsed time caused, which is what
  it is for.
- Several prose checks read a fenced block by toggling on any line that opens with three
  backticks or tildes, so a four-backtick example quoting a fenced block can be misread: an
  anchor written as an example is reported as `claim-anchor/missing-file`.
- A Python anchor binds a function or a class, not a module-level constant.
- `claim-provenance/evidence-drift` and the hints that ask prose for a claim run only in
  the foundation and architecture layers.
- **An adoption boundary is checkable, not approved.** Every comparison rests on a revision:
  git proves whether a path existed there, and nothing more. For a file in this repository
  that revision is the merge base; for one in a declared source it is the pin, which
  `--init-adoption` takes from the merge base of the source checkout and the declared `ref`,
  so a commit on a branch anybody can push cannot become the boundary. What no comparison
  here can establish is that the adopting *moment* deserved to be it: a file merged to that
  history the day before adoption is recorded as debt exactly like one that had been there
  for a year. That is the deliberate cutoff — the approved snapshot as of adoption — and
  telling the two apart is the review of the adopting commit. Naming a ref is also not a
  claim that the branch is protected.
- **A record written past the gate is history as far as this tool can tell.** Validation is
  inductive: the change that creates a record is checked, and every later change against the
  one before it. A record pushed straight to an unprotected default branch skips the only
  base case that chain has.
- **A source-repository gate reports until it is required.** The workflow `init` writes for
  the code repository runs the check on that repository's pull requests, and nothing here can
  make it block a merge — that is branch protection over there. Nor is it sealed the way
  `diff-integrity` seals the workflows in the docs repository: it lives in the other
  repository, which this gate cannot read. Between two docs pull requests, a source-side
  change that removes an owner is caught only by that repository's own required check.
- `--source-diff` reaches touch-to-own over recorded ownership debt and nothing else. A
  source change whose owning doc was not updated is still not reported; co-change across a
  repository boundary would change what an existing check means in one layout only.
- The adoption record names exact paths, so moving a recorded file means documenting it at
  the new path — the exception does not follow the move. That is deliberate, since an
  exception that followed moves would let a repository rename its way out of documenting
  anything, but it does mean a large mechanical move lands as ownership work. Deleting a
  recorded file in a *source* repository is exempt, because the record lives in the docs
  repository and that pull request cannot change it.

### Upgrading from 0.2.0

**A scaffold written by an earlier version needs one targeted edit.** `irminsul init` and
`irminsul seed` used to write one sentence into `docs/architecture/overview.md` that now
fails while that doc is a draft, as `prose-file-reference/unlinked-reference`:

> Container-level (C4 L2) detail belongs in `containers.md`.

Edit that one sentence. Either drop the file name, as the templates now do ("belongs in a
containers doc of its own"), or create `docs/architecture/containers.md` and link it as
`[containers](containers.md)`.

Do not repair it with `irminsul init --force`: that replaces the whole file, and every
other scaffold file, with the template.
