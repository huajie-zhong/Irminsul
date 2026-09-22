# Changelog

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
