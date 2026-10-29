---
id: init
title: Init scaffolder
status: stable
summary: Scaffolding command and templates.
depends_on:
  - languages
  - checks
  - docgraph
  - file-writing
  - user-errors
describes:
  - src/irminsul/init/**
owns_tests:
  - tests/test_init.py
  - tests/test_init_detector.py
  - tests/test_init_placeholders.py
  - tests/test_init_siblings.py
implements:
  - a-gate-file-is-sealed-not-scored
---

# Init scaffolder

`irminsul init` scaffolds a `/docs` skeleton, an `irminsul.toml`, two GitHub workflows (PR-time `docs-pr.yml` and nightly `docs-nightly.yml`) and the agent-harness wiring into a target codebase. Three paths run through it: `irminsul init` adopts existing code, detecting languages and source roots in place; `--fresh` starts a project with no code, takes `--language` for the profiles detection cannot see yet, and refuses a directory with code signals unless `--allow-existing-code` says that is intended; and `--topology siblings --code-repo <spec>` scaffolds a docs repo beside a separate code repo ([Init adopts in two layouts, and seed fills two docs](../decisions/init-adopts-in-two-layouts-and-seed-fills-two-docs.md), [private docs](../guides/private-docs.md)). The templates are Jinja files under `src/irminsul/init/scaffolds/` and `src/irminsul/init/workflows/<topology>/`, rendered in the one [environment](file-writing.md) every template in the tool uses. <!-- irminsul:ignore code-references reason="a workflow irminsul init writes into the target repository, not one of this repository" -->

The PR workflow has no `paths:` filter, in either layout. GitHub leaves a required check Pending when a filter skipped its workflow, and a filter would have to list every file the gate reads — docs, config, source and test roots, guidance files, the baseline, the [adoption record](adoption-record.md) — so one omission makes a pull request touching only that file unmergeable. Adding a filter back edits a gate file, which [`diff-integrity`](checks.md) reports until a decision record names it.

The `siblings` layout gets a third file, `.github/for-code-repo/code-pr.yml`, a workflow for the *other* repository: the gate runs in the docs repo, and a pull request in the code repo makes no diff there and fires nothing there. It is written outside `.github/workflows/` so this repo's CI does not run it on docs pull requests against a code checkout nothing is reviewing, and the printed next steps say to copy it across because init runs in the docs repo and cannot commit to the code one. <!-- irminsul:ignore code-references reason="a workflow irminsul init writes into the target repository, not one of this repository" -->

The workflows run the Action at `v<version>`, the version doing the scaffolding, and the Action installs the CLI from that same ref, so CI runs the tool the adopter installed rather than a version hardcoded in a template, which is right for one release and wrong after it. A development build has no release tag, so it writes `@main` instead of a tag the repository does not have.

Agent-harness wiring is written after the templates, from module constants rather than templates: `.mcp.json` registers the read-only [MCP server](mcp-server.md), the skill is a trigger that points at the root [`AGENTS.md`](../../AGENTS.md) and the commands that print their own advice, and `CLAUDE.md` imports the root `AGENTS.md`, which Claude Code does not read on its own. They are constants because `--force` merges them: the `irminsul` entry is set in an existing `mcpServers` map and every other server survives, and a [`CLAUDE.md`](../../CLAUDE.md) that lacks the import gains it at the top, which the skip-or-replace template writer cannot express. None of the three is governed by a check, because none is derived from anything ([Agents get stateless read-only queries and one written loop](../decisions/agents-get-stateless-read-only-queries-and-one-written-loop.md)).

The root `AGENTS.md` is the one template init merges: its section sits between `<!-- irminsul:agents-start -->` and `<!-- irminsul:agents-end -->`, the only part of the file init owns, so init can add it to a file it did not write and `--force` can refresh it alone. A marker inside a code fence is not one, so a file that quotes the pair as an example has no section yet. The section is the one home of the agent loop and posture; this repository's root `AGENTS.md` carries it too, and a test compares the two.

The scaffold is born compliant with its own configured checks. Every layer ships a navigation INDEX so sibling docs are never orphans; the components INDEX carries a Scope & Limitations section because that layer sets `require_scope_section`; the INDEX of each not-yet-filled layer is `status: draft`, which `phantom-layer` treats as under construction rather than navigation rot. A fresh same-repo scaffold reports zero errors, and two `foundation-readiness/scaffold-placeholder` warnings on the draft principles and overview until `irminsul seed` fills them. Each prompt there carries `<!-- irminsul:placeholder -->`, so a prompt is found by its marker and never by its wording.

## Scope & Limitations

Init scaffolds doc, config and CI structure and agent-harness wiring only: it does not scaffold application code or generate implementation stubs, and it does not provision remote services such as GitHub repositories or CI runners. Harness wiring is limited to a project MCP registration, a harness skill and a Claude Code pointer, and nothing outside the target repository: a harness that keeps its server registration in a user-global file is deliberately not wired, because adoption has no business writing outside the repo. In the `siblings` layout the wiring lands in the docs repo, where init runs; a session opened in the code repo has neither file, so the printed next steps give the registration command to run there, pointed back at the docs repo.

Because the harness files are static constants with no drift check, a later change to the server's invocation will not mechanically flag already-adopted repositories.

## Implemented requirements

- **a-gate-file-is-sealed-not-scored#scaffold-without-path-filter** — `irminsul init` SHALL write a `docs-pr.yml` whose `pull_request` trigger has no `paths:` or `paths-ignore:` filter, in both repository layouts. (provenance: code; [RFC](../rfcs/a-gate-file-is-sealed-not-scored.md)) <!-- irminsul:ignore code-references reason="a workflow irminsul init writes into the target repository, not one of this repository" -->
  <!-- anchor: src/irminsul/init/workflows/same-repo/docs-pr.yml.j2 @sha256:6baaba29b86d -->
  <!-- anchor: src/irminsul/init/workflows/siblings/docs-pr.yml.j2 @sha256:c4499deccb6f -->
