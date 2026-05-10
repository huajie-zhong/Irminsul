---
id: 0007-fresh-start-init
title: Fresh-start init
audience: explanation
tier: 2
status: draft
describes: []
---

# RFC 0007: Fresh-start init

## Summary

Make empty-directory adoption an intentional, documented `irminsul init` path.
Irminsul should support users who are creating a new project and want the source
root, docs skeleton, config, and CI wiring to start together, not only users who
are adopting Irminsul midway through an existing codebase.

The proposal keeps the existing adoption paths, but adds a first-class
fresh-start branch to interactive init and a non-interactive flag for automation.
Fresh-start is orthogonal to topology: it can create either a same-repo project
or a private-docs/public-code project that has no code checked out yet. Midway
adoption keeps the same topology choices: existing same-repo code uses
`irminsul init`, and existing separate/public code with private docs uses
`irminsul init-docs-only`.

## Motivation

The foundation goal says adoption should work in three commands:
`pipx install irminsul && cd repo && irminsul init`. Today, `init` behaves as if
the target usually already contains code signals. In non-interactive mode an
empty directory exits with code 2 and tells the user to consider docs-only mode.
In interactive mode, an empty directory can continue only by answering "no" to a
question about docs-only setup. That makes fresh project creation possible, but
accidental and unclear.

Fresh-start support matters because Irminsul's strongest value appears when docs
and code grow together from PR 1. Treating a new project as a valid init target
also aligns with these foundation principles:

- **Mechanical Necessity:** the first commit can already contain the docs gate,
  avoiding a later migration.
- **Code as Ultimate Truth:** a scaffolded source root gives checks a real place
  to inspect once code exists without pretending a mature codebase exists.
- **Adoption in three commands:** the empty-repo case should be a supported
  happy path, not an error path.

## Detailed Design

### User-facing Modes

`irminsul init` should distinguish setup intent and topology when no code signals
are detected:

1. **Fresh-start, same repo:** create `docs/` and an empty `src/` in one repo.
2. **Fresh-start, private docs/public code:** create the private docs repo now
   and configure a future or external code repo as a gitignored subfolder.
3. **Adopt existing separate code:** docs live here and existing code is checked
   out into a gitignored subfolder.
4. **Abort:** the user ran the command in the wrong directory.

When code signals are detected, the existing behavior remains the default:
same-repo adoption of an existing codebase. When code already exists in a
separate public repo and docs should be private, the existing
`init-docs-only --code-repo <spec-or-path>` path remains the midway-adoption
entry point.

### CLI Surface

Add an explicit non-interactive flag:

```bash
irminsul init --fresh --path my-new-project
```

Default behavior:

- Create the target directory if it does not exist.
- Scaffold the normal docs tree, `irminsul.toml`, GitHub Actions workflows, and
  pre-commit wiring.
- Create an empty source root if none exists.
- Do not create language-specific starter code in non-interactive mode.
- Exit 0 if the generated project passes `irminsul check --profile=hard`.

For private-docs/public-code fresh-start, add an explicit topology flag:

```bash
irminsul init --fresh --topology docs-only --code-repo owner/future-public-repo
```

In that topology, `--code-repo` may name a repo that does not exist yet. The
scaffold should configure the future code checkout path and `.gitignore` entry,
but it should not require source files to exist at init time.

The current `irminsul init --no-interactive` behavior should remain conservative:
if no code signals exist and `--fresh` is not present, exit with a clear message
that names both valid non-interactive options:

```text
No code detected in the target directory.
Use `irminsul init --fresh` to start a new project, or
`irminsul init-docs-only --code-repo <spec-or-path>` for a docs-only repo.
```

There is no `irminsul new project` command in this proposal. Fresh project
creation remains part of `init` because the CLI already uses `new` for new doc
atoms, not new repositories.

### Interactive Flow

When interactive `irminsul init` sees no code signals, it should ask about setup
intent directly instead of routing the user through a docs-only yes/no question.

Proposed prompt:

```text
No code detected here. What are you setting up?
  [1] Fresh-start, same repo
  [2] Fresh-start, private docs / public code
  [3] Docs-only repo for existing separate code
  [4] Cancel
```

If the user chooses fresh start, ask only questions needed to produce a valid
scaffold:

- Project name
- Render target

If the user chooses private-docs/public-code fresh-start, also ask for the future
or current code repo spec and the local code subfolder name. The repo may be
created after the docs repo.

The current docs-only prompt for `--code-repo` remains under the existing
separate-code adoption path.

### Fresh-start Scaffold

The minimal fresh-start scaffold should avoid pretending there is real product
architecture before the user has written it. The generated project should create
only enough structure to make source-root assumptions true and let checks operate
without missing-directory noise.

Recommended starter:

```text
src/
```

Recommended `irminsul.toml` values:

```toml
[paths]
docs_root = "docs"
source_roots = ["src"]

[languages]
enabled = []
```

The fresh-start scaffold should not create tests or component docs. Placeholder
foundation and architecture docs can remain `describes: []` because they capture
intent and system shape, not a specific source file.

### Topologies

Fresh-start same-repo topology puts docs and source in the same repository, with
`docs/` and `src/` as sibling directories under the target root:

```text
my-new-project/
├── docs/
├── src/
└── irminsul.toml
```

Fresh-start private-docs/public-code topology creates the docs repo first and
points at a future or existing code repo that will be checked out into a
gitignored subfolder:

```text
my-private-docs/
├── docs/
├── irminsul.toml               # source_roots = ["my-public-code/src"]
├── .gitignore                  # /my-public-code/
└── my-public-code/             # absent at init time, checked out later
```

This topology supports public code with private docs. It is the fresh-start
variant of the current `init-docs-only` flow: the docs repo can exist before the
code repo has source files. Midway adoption of the same topology remains
`init-docs-only --code-repo <spec-or-path>` against an existing code repo.

### Check Invariants

The fresh-start output must satisfy these conditions:

- `irminsul check --profile=hard --path <target>` exits 0.
- No generated doc claims source paths that do not exist.
- No generated component doc claims code without a matching generated test.
- Non-interactive fresh-start does not assume a programming language.
- Private-docs/public-code fresh-start may configure missing source roots without
  failing hard checks while the code repo is not checked out yet.
- No hard check depends on LLM judgment.
- Re-running `irminsul init --fresh` without `--force` preserves user edits.

### Implementation Sketch

1. Add `fresh: bool = False` to the `init` CLI command.
2. Change the no-code branch in `src/irminsul/cli.py` to route interactive users
   through a three-way setup-intent prompt.
3. Add a topology option for fresh-start, defaulting to same-repo.
4. Add a fresh mode to init answer gathering so non-interactive same-repo
   fresh-start uses `source_roots = ["src"]` and `languages.enabled = []`.
5. Reuse the docs-only context fields for private-docs/public-code fresh-start,
   but allow the configured code subfolder and source root to be absent at init
   time.
6. Add source-root directory creation to the init writer for same-repo
   fresh-start mode.
7. Add tests for:
   - `init --fresh --no-interactive` on an empty directory.
   - interactive no-code selection of fresh start.
   - `init --fresh --topology docs-only --code-repo owner/future-repo` on an
     empty directory.
   - `init --no-interactive` on an empty directory still errors without
     `--fresh`.
   - `init --fresh` in a non-empty no-code directory such as one with only
     `README.md` and `.gitignore`.
   - no overwrite without `--force`.
   - generated fresh-start project passes hard checks.

### Documentation Updates

Update:

- `README.md` quickstart to mention both existing-code and fresh-start examples.
- `docs/20-components/init.md` to define the three setup intents.
- `docs/10-architecture/tooling.md` to clarify that "adopting on a new
  codebase" includes an empty-repo path.

## Drawbacks

- Adds one more branch to the init flow, which increases test matrix size.
- Starter source files can be perceived as framework scaffolding. Irminsul should
  stay a documentation system, so the starter is intentionally an empty source
  root.
- Users who expect a language starter must still run their language-specific
  project generator.
- Interactive prompting becomes more complex. The wording must make docs-only
  and fresh-start setup visibly different.

## Compatibility and Breaking Risk

This should not break existing users if implemented as an opt-in path:

- Existing codebases with code signals still run through current single-repo
  init.
- Existing private-docs/public-code midway adoption still runs through
  `init-docs-only`.
- Existing `init --no-interactive` on empty directories can remain an error
  unless `--fresh` is provided.
- `init --fresh` may run in a non-empty directory with no code signals, including
  a repo containing only `README.md` and `.gitignore`.
- Existing no-overwrite behavior remains unchanged.

The only intentional behavior change is interactive: an empty directory should
ask for setup intent instead of asking only whether it is docs-only. That is a
product-flow change, not a file-format break.

Potential new risks:

- Fresh-start scaffolds may produce a false sense that the generated
  architecture docs are complete. Template wording should keep the current
  "replace this with your own" tone.
- A generated source root makes coverage checks meaningful earlier once code is
  added, but source coverage remains advisory unless another RFC promotes it.
- Allowing missing source roots for fresh private-docs/public-code setup may
  require the globs/source-root checks to distinguish "configured future code
  checkout" from "misconfigured existing code checkout."
- `languages.enabled = []` may require config-schema support if the current
  schema assumes at least one language. If the schema forbids an empty list, the
  implementation must either relax that constraint or add a first-class
  language-neutral mode.

## Alternatives

- **Do nothing:** keep empty directories as a mostly accidental interactive path.
  This preserves simplicity but conflicts with the adoption-friction goal.
- **Create `irminsul new project`:** cleanly separates project generation from
  docs adoption, but it conflicts with the current command style: `new` creates
  doc atoms inside an adopted repo, while `init` adopts or initializes repos.
- **Make empty non-interactive init fresh by default:** convenient but too risky.
  Automation may currently rely on the empty-directory error to catch wrong
  paths.
- **Docs-only-first prompt only:** the current shape is adequate for separate
  docs repos, but it frames fresh project creation as the negative case.
