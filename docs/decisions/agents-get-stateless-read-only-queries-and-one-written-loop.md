---
id: agents-get-stateless-read-only-queries-and-one-written-loop
title: Agents get stateless read-only queries and one written loop
status: stable
describes: []
summary: Agents query the repository through read-only commands and an MCP server that keep no session, follow one edit loop written in a marked section of the root AGENTS.md, and get harness wiring scaffolded at adoption.
governs:
  - src/irminsul/context.py
  - src/irminsul/mcp_server.py
  - src/irminsul/orient.py
  - src/irminsul/regen/**
  - src/irminsul/checks/agents_manifest.py
  - src/irminsul/checks/external_links.py
  - src/irminsul/init/scaffolds/AGENTS.md.j2
  - src/irminsul/init/command.py#_ROOT_ROUTER_PATH
  - src/irminsul/init/command.py#_MCP_CONFIG_PATH
  - src/irminsul/init/command.py#_SKILL_PATH
  - src/irminsul/init/command.py#_CLAUDE_POINTER_PATH
  - src/irminsul/init/command.py#_MCP_MANUAL_COMMAND
  - src/irminsul/init/command.py#_SKILL_BODY
  - src/irminsul/init/command.py#_ROUTER_IMPORT
  - src/irminsul/init/command.py#_CLAUDE_POINTER_BODY
  - src/irminsul/init/command.py#agents_block_span
  - src/irminsul/init/command.py#_read_root_router
  - src/irminsul/init/command.py#_merge_root_router
  - src/irminsul/init/command.py#generate_agents_manifest
  - src/irminsul/init/command.py#HarnessWiring
  - src/irminsul/init/command.py#_load_mcp_config
  - src/irminsul/init/command.py#_registers_irminsul
  - src/irminsul/init/command.py#_link_pointer
  - src/irminsul/init/command.py#write_harness_files
  - src/irminsul/init/command.py#_scaffold_with_agent_wiring
  - src/irminsul/init/command.py#_harness_next_step
  - src/irminsul/init/command.py#check_mcp_launcher
  - src/irminsul/init/command.py#print_mcp_warning
  - AGENTS.md
  - CLAUDE.md
  - .mcp.json
  - checks.external_links.cache_path
  - checks.external_links.ttl_hours
retires:
  - id: context-change-alias
    kind: concept
    matches:
      - context --change
    guidance: Run `irminsul change status <id>` for an RFC's evidence report.
---

# Agents get stateless read-only queries and one written loop

## Status

Accepted, 2026-10-28.

## Context

Coding agents do most of the editing in repositories that adopt Irminsul. They need to find what
owns a file, what depends on it and what to update without reading the whole tree, through the
harness they already run, and every harness needs the same instructions. Instructions kept in
several places drift, and an adopter whose root `AGENTS.md` predated `init` would get none. A
session kept between calls goes stale, yet requesting every external link on every call is slow,
rate-limited and makes a run depend on the network.

## Decision

- **Read commands with JSON.** `orient`, `context`, `refs`, `surface`, `check`, `list`,
  `anchors`, `fix`, `change status` and `change verify` take `--format json`. `orient` is the
  first call and teaches the loop's vocabulary, which the `cli` inventory in
  `docs/components/orient.md` keeps honest against the CLI.
- **`orient` teaches the edit loop,** so its `cli` inventory in `docs/components/orient.md`
  omits the four maintenance commands.
- **`context` costs what its moment needs.** `context <path...>` and `context --topic` return
  owners, tests, dependencies, active RFCs, claims and bounded excerpts and run no checks;
  `context --after-edit` alone runs them, maps changed paths to owners, and says what the
  change introduced.
- **Context keeps no session.** A call stores nothing for a later call: no task or agent
  session, no selection of paths or owners, no ownership result, packet or other
  repository-derived result; every call derives them from the repository as it stands. A lower
  layer may reuse such a result only within the invocation
  that derived it: git history is read once per graph, and the MCP server builds a new graph for
  each call. The governing claim `context-is-stateless` states this.
- **An external-link check may cache what it observed,** in a cache declared as
  `checks.external_links.cache_path` under the graph's state root, each entry living
  `checks.external_links.ttl_hours` from its recorded observation if reachable and one hour if
  not. An entry with no readable time, no time zone or a future time counts as expired, and a
  cache written in another format version is ignored. A cached
  result is an observation: its finding gives the observation time, a run that read the cache
  reports `external-links/cached-results` with the count and the oldest observation, and caching
  never changes a finding's code, class or severity.
- **A read-only MCP server** exposes the same queries and the read side of the change
  lifecycle; writes stay confirmed CLI actions until MCP has an authorization model. It refuses
  every call once irminsul's own files changed on disk since it started.
- **MCP follows the CLI:** `context_for_path` takes several paths and runs no checks,
  `context_after_edit` takes an optional `base_ref`, `check` takes `only`, and `refs` resolves
  docs only.
- **The loop has one home, a marked section of the root `AGENTS.md`.** The template
  `init/scaffolds/AGENTS.md.j2` holds the loop, "Follow the foundation layer", "What a finding
  tells you" with the moves that clear a finding without repairing anything, and the harness
  note, between `<!-- irminsul:agents-start -->` and `<!-- irminsul:agents-end -->`. `init`
  writes the file when there is none, appends the section to one without the markers, leaves one
  with them alone, replaces only the section under `--force`, and refuses unpaired markers. This
  repository's root `AGENTS.md` carries the same section, which a test compares. The
  [agent protocol](../guides/agent-protocol.md) keeps acting on a finding and changing direction.
- **The [manifest](../AGENTS.md) is generated, with two curated sections:** a table of every doc
  that `irminsul fix` rewrites from the graph, a `Foundations` that in a scaffold holds the Three
  Laws, and a one-line `Protocol` naming where the loop lives; `agents-manifest` requires both
  headings.
- **Harness wiring is scaffolded, not policed.** `init` writes `.mcp.json`, a pointer skill
  naming the root `AGENTS.md`, `orient`, `explain` and `list review`, and a `CLAUDE.md` that
  imports `AGENTS.md`, from constants. It skips an existing file; under `--force` it merges the
  registration and the pointer and replaces the skill. No check watches them, and this
  repository keeps no skill, because its `CLAUDE.md` imports the root `AGENTS.md`.
- **`context <path>` names the governing record and the sign-offs** (accepted, not yet
  implemented). For each input path it lists every stable decision record with an item in that
  file, and the `Irminsul-Reviewed` trailers of the commits that changed it, the newest five with
  a count of the rest, read from git history on every call, so nothing is stored.
- **The cached-link count joins the run's summary** (accepted, not yet implemented), with its
  oldest observation, and `external-links/cached-results` goes.

## Alternatives Considered

- **A persistent session or index.** Rejected: re-deriving cannot go stale, and nothing would
  invalidate a cached ownership result.
- **MCP write tools now.** Rejected until writes have an authorization model.
- **A drift check on the harness files.** Rejected: none is derived, so it would compare a
  constant with itself and burden adopters who delete a file.
- **No external-link cache.** Rejected: every run would request every link, for freshness a
  lower `ttl_hours` already buys.
- **Leave check caches outside the statelessness rule unsaid, or report each cached link.**
  Rejected: any check could reintroduce stale state, and one notice per run carries the count.
- **Leave an adopter's own `AGENTS.md` untouched.** Rejected: those adopters' agents would never
  see the loop.
- **A skill copy in this repository, rendered or packaged.** Rejected: still a copy plus a
  guard, and an editable install does not map a packaged file.

## Consequences

- An agent works the loop from `orient`, `context <path...>` and `context --after-edit`; a
  packet carries no findings, so an agent that wants them before editing runs `check`.
- A section or harness file already written does not follow a later release until
  `init --force` refreshes it, and nothing reports that it is behind.
- No test can show that a future code path keeps no session; that stays a review question for
  any change to context or the layers it calls.

## Changes

- 2026-10-29: Accepted [Decision records govern what they decide](../rfcs/decision-records-govern-what-they-decide.md):
  `context` names a path's governing record and its sign-offs.
- 2026-10-29: Accepted [Each finding code has one answer](../rfcs/every-warning-hint-has-an-answer.md):
  the cached-link count moves into the run's summary.
- 2026-10-29: Accepted [A change re-asks the sentences that name its code](../rfcs/a-change-re-asks-the-sentences-that-name-its-code.md):
  `context <path>` lists the sentences that name the path's code.
- 2026-10-29: Accepted [A topic search reads doc bodies](../rfcs/a-topic-search-reads-doc-bodies.md):
  `context --topic` matches body prose, ranked below the other fields.
