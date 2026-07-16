# Irminsul

> A documentation system for complex codebases. Designed to resist rot, scale with complexity, and survive philosophy shifts.

Irminsul is a Python CLI + composite GitHub Action that enforces structural invariants on your `/docs` tree in CI. The rules are simple: every fact has one home, every doc has one purpose, every cross-reference is bidirectional and machine-verifiable. The tool's job is to make sure those rules stay true while the codebase evolves.

## Why

Docs that rot are worse than no docs — they are noise that reads as signal. Irminsul turns the docs tree into a machine-verified contract between humans and AI coding agents: humans read the curated layers and write the judgment calls; agents query the graph, do the heavy lifting, and are held to the same checks. There is no server, no hosted state, and no LLM in the hard-check path — every structural claim the docs make about the code is verified deterministically, on every PR.

## Quickstart

For an existing codebase:

```bash
pipx install irminsul
cd my-codebase
irminsul init
```

For a new project with no code yet:

```bash
pipx install irminsul
irminsul init --fresh --path my-new-project
```

That scaffolds a 9-layer `/docs` skeleton, an `irminsul.toml` config, GitHub Actions workflows, and the agent wiring: `docs/AGENTS.md` (the generated navigation manifest) plus a root `AGENTS.md` pointer that Claude Code, Cursor, and Codex pick up natively. Three commands, ten seconds, fully wired.

For private docs with separate public code, use `irminsul init-docs-only --code-repo owner/repo` when the code repo already exists, or `irminsul init --fresh --topology docs-only --code-repo owner/future-repo` when both repos are starting from zero.

## For AI agents

The loop: orient, locate the owning docs, edit code and docs in the same commit, verify before committing. Each command supports `--format json`.

| Command | What it does |
|---------|--------------|
| `irminsul orient` | First call in a session: one-shot repo orientation — what this repo is, the layer map, where to start |
| `irminsul context --before-edit <path...>` / `--after-edit` | Package owners, tests, active RFCs, requirements, findings, and deterministic next actions around an edit |
| `irminsul context --changed` (or `--topic <q>`, `<path>`) | Focused ownership, dependency, and finding queries for the current edit set, a topic, or a path |
| `irminsul refs <doc-id>` / `irminsul refs --symbol <name>` | Backlinks for a doc, or the docs that own/reference a symbol |
| `irminsul surface {cli,http,exports,env-vars}` | Derive a code surface from source on demand — never written to disk, so it cannot drift |
| `irminsul list {orphans,stale,undocumented}` | Docs nothing references, deprecated docs past threshold, source files no doc claims |
| `irminsul check --profile=hard --format json` | Machine-readable findings plus the exit code CI enforces |
| `irminsul fix` | Apply deterministic remediations for mechanical findings |

For MCP-speaking harnesses, `irminsul mcp` exposes the same commands as MCP tools (install with `pip install 'irminsul[mcp]'`).

## For humans

Read the curated layers — GitHub and your IDE render the markdown. The tree is fixed at nine layers:

| Layer | Purpose |
|-------|---------|
| `00-foundation` | Principles, constraints, stakeholders — rarely changes |
| `10-architecture` | System context, containers, boundaries, deployment |
| `20-components` | The per-component "what" |
| `30-workflows` | The cross-component "how" |
| `50-decisions` | ADRs — the "why", append-only |
| `60-operations` | Runbooks, playbooks, SLOs |
| `70-knowledge` | Tutorials, how-tos, explanations |
| `80-evolution` | Roadmap, RFCs, risks, tech debt |
| `90-meta` | Docs about the doc system itself |

`irminsul new {adr,component,rfc}` scaffolds a correctly-frontmattered atom into the right layer.

## What it checks

Hard, blocking checks (deterministic, no LLM):

- **Frontmatter validity** — required fields present, enums valid, IDs match filenames
- **Glob resolution** — every `describes` glob resolves to ≥1 source file
- **Coverage uniqueness** — every source file is claimed by exactly one most-specific doc
- **Internal link integrity** — no broken `[link](other.md)` references
- **Schema-leak detection** — no class/type definitions in component docs
- **Test coverage** — every living (tier-3) doc declares at least one valid test path
- **Liar detection** — no hand-enumerated derivable surfaces in prose; use `irminsul surface`
- **Prose file references** — file paths mentioned in stable docs must exist
- **Agents manifest** — the generated section of `docs/AGENTS.md` matches the actual tree

Soft deterministic checks (warnings by default, errors with `--strict`):

- **mtime-drift** — a doc's last commit lags behind the sources it describes
- **orphans** — docs that nothing links to or claims
- **stale-reaper** — deprecated docs that have aged past the staleness threshold
- **supersession** — `supersedes`/`superseded_by` reciprocity between decisions
- **parent-child** — INDEX.md invariants: no broad globs over children, length cap
- **glossary-discipline** — glossary terms are not redefined outside `GLOSSARY.md`
- **external-links** — http(s) link reachability, cached (opt-in)

…plus further deterministic audits (reality, boundary, phantom-layer, claim provenance, inventory drift, and more) selectable in `irminsul.toml`.

## CI integration

```yaml
on: pull_request
jobs:
  docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: huajie-zhong/irminsul@v0.1.0
        with:
          profile: hard
```

`irminsul init` writes this file for you.

## License

AGPL-3.0-or-later. See [`LICENSE`](LICENSE).
