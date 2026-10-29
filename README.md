# Irminsul

> Repository knowledge that stays accountable to the code.

However your team creates documentation and specifications, Irminsul mechanically verifies their structure, the code they claim, their provenance and lifecycle, and whether those relationships still hold in the repository. It is a Python CLI + composite GitHub Action that enforces those invariants locally and in CI without prescribing an authoring workflow.

## Why

Docs that rot are worse than no docs — they are noise that reads as signal. Agents are the primary operators and direct consumers of repository knowledge; humans interact with that knowledge primarily through agents and remain the authority for intent and approval. Irminsul gives both a machine-verified contract: agents query the graph and perform the work, while deterministic checks make structural drift visible to the humans who authorize it. There is no server, no hosted state, and no LLM in the check path.

## Quickstart

For an existing codebase:

```bash
pipx install irminsul
cd my-codebase
irminsul init
irminsul adoption init
```

The fourth line is what makes an existing codebase adoptable. It records the files that
have no owning document today, so they do not fail CI while you work through them. Every
check runs from that moment — the record excepts those named files from the one finding
that says a file has no owner, and nothing else. Each exception retires the moment you
document its file, editing a recorded file means documenting it in the same change, and
the record can only shrink. See [the adoption record](docs/components/adoption-record.md)
for the whole contract, and `irminsul list undocumented --all` for what is left.

Skip it on a repository whose code is already documented; skip it on a new project. The
symptom of skipping it when you needed it is a green run today and a red one the day you
write your first component doc, because documenting one file brings the rest of its
directory into scope.

For a new project with no code yet:

```bash
pipx install irminsul
irminsul init --fresh --language python --path my-new-project
```

That scaffolds a six-layer `/docs` skeleton, an `irminsul.toml` config, GitHub Actions workflows, and the agent wiring: `docs/AGENTS.md` (the generated navigation manifest), a root `AGENTS.md` holding the agent loop, which Cursor and Codex read natively (an `AGENTS.md` you already have gains it as a marked section), a `CLAUDE.md` that imports it for Claude Code, a `.mcp.json` registering the read-only MCP server, and a harness skill that points an agent at that loop and `irminsul orient`.

For private docs with separate public code, run `irminsul init --topology siblings --code-repo owner/repo --language python` inside a docs repo that sits beside the code repo. The code repo does not have to exist yet; omit `--language` when a local checkout is available for detection.

## For AI agents

The loop: orient, locate the owning docs, edit code and docs in the same commit, verify before committing. Each command supports `--format json`.

| Command | What it does |
|---------|--------------|
| `irminsul orient` | First call in a session: one-shot repo orientation — what this repo is, the layer map, how much of the source a doc owns, where to start |
| `irminsul context <path...>` / `--after-edit` | Before an edit: owners, tests, active RFCs, bounded authored excerpts, and next actions, with no checks run. After it: the same for the changed files, plus findings and what the change introduced |
| `irminsul context --topic <q>` | The docs that cover a topic, before you know which file to open |
| `irminsul refs <doc-id>` | The docs that depend on or link to a doc |
| `irminsul surface {cli,cli-options,http,exports,env-vars,mcp}` | Derive a code surface from source on demand — never written to disk, so it cannot drift |
| `irminsul list {undocumented,lifecycle,review,baseline}` | Source files no doc claims, unfinished RFC work, doc sentences to re-check against changed code, and the findings a baseline hides |
| `irminsul check --format json` | Machine-readable findings, each with its class, plus the exit code CI enforces; `--only <check>` runs one check, such as `orphans` |
| `irminsul fix` | Apply deterministic remediations for mechanical findings |

For MCP-speaking harnesses, `irminsul mcp` exposes the same commands as MCP tools (install with `pip install 'irminsul[mcp]'`).

## For humans

Read the curated layers — GitHub and your IDE render the markdown. The tree has six [layers](docs/architecture/layers.md): `foundation`, `architecture`, `components`, `decisions`, `rfcs`, and `guides`, each a folder you can rename under `[layers]` in `irminsul.toml`.

`irminsul new {adr,component,rfc}` scaffolds a correctly-frontmattered atom into the right layer.

## What it checks

Every check is deterministic and makes no LLM call. Each finding has a class: a **certain** finding proves the tree breaks a rule and fails CI; a **hint** points at something to investigate and fails only under `--fail-on hint` when it is a warning; a **time** finding comes from elapsed time and stays off pull requests. Checks enabled by default include:

- **Frontmatter validity** — required fields present, enums valid, IDs match filenames
- **Glob resolution** — every `describes` glob resolves to ≥1 source file
- **Coverage uniqueness** — every source file is claimed by exactly one most-specific doc
- **Internal link integrity** — no broken `[link](other.md)` references
- **Schema-leak detection** — no class/type definitions in component docs
- **Test coverage** — every component doc that claims source declares at least one valid test path
- **Code references** — a code span naming a command, option, function, or environment variable the code no longer has
- **Prose file references** — local `.md` filenames in stable prose must be real Markdown links
- **RFC lifecycle** — every RFC declares its state, and `resolved_by`/`implements` resolve; under `--diff`, `diff-integrity` reports an implemented RFC that changed
- **Retired references** — current docs do not present a command or concept an ADR retired as live
- **Agents manifest** (opt-in) — the generated section of `docs/AGENTS.md` matches the actual tree
- **mtime-drift** — a doc's last commit lags behind the sources it describes
- **orphans** — docs that nothing links to or claims
- **stale-reaper** — deprecated docs that have aged past the staleness threshold
- **supersession** — a doc another one `supersedes` is deprecated
- **parent-child** — INDEX.md invariants: no broad globs over children, length cap
- **glossary-discipline** — no doc uses a synonym the glossary forbids, and a term's first use links its entry
- **external-links** — http(s) link reachability, cached (opt-in)

…plus further deterministic audits (boundary, phantom-layer, claim provenance, inventory drift, and more), listed in `checks.enabled` in `irminsul.toml`.

## CI integration

```yaml
on: pull_request
jobs:
  docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: huajie-zhong/irminsul@v0.4.1
        with:
          diff: origin/${{ github.base_ref }}
```

`irminsul init` writes this file for you.

## License

AGPL-3.0-or-later. See [`LICENSE`](LICENSE).
