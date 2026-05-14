---
id: 0015-pib-seed-and-foundation-readiness
title: PIB seed and foundation readiness
audience: explanation
tier: 2
status: draft
describes: []
rfc_state: draft
---

# RFC 0015: PIB seed and foundation readiness

## Summary

Add a first-class seed flow for projects that begin with only a principle,
idea, or belief. The command captures the user's initial direction, writes it
into the foundation layer, and makes placeholder foundation docs visible before
agents start implementation work.

## Motivation

Fresh-start init already lets a project begin before code exists, but the first
real user intent is still just prose the user or agent must remember to place in
the right file. That leaves the strongest Irminsul workflow under-specified:
the user states the principle, idea, and belief clearly; agents expand that into
docs and code; checks keep later drift visible.

If the foundation remains a scaffold placeholder, agents can still move into
architecture and code. That is the wrong default. A project that starts with a
belief should make that belief the root artifact before implementation begins.

## Detailed Design

Add a command:

```text
irminsul seed
```

The command is interactive by default and collects:

- principle: what must remain true even if features change
- idea: what should be built first
- belief: why this direction is worth pursuing
- first user: the first audience the app should serve
- non-goals: what the app should not become
- direction risks: what would make the product drift away from the belief

The command writes or updates:

- `docs/00-foundation/principles.md`
- `docs/10-architecture/overview.md`
- a first ADR under `docs/50-decisions/`

For non-interactive use, the command should accept equivalent flags or a JSON
input file. The non-interactive form is useful when an agent receives a concise
PIB statement from a user and needs to materialize it without inventing missing
intent.

Add a deterministic soft check named `foundation-readiness`. It warns when a
fresh scaffold still contains known placeholder phrases in foundation or
architecture docs. The check is advisory because a short foundation can be
valid, but a literal scaffold placeholder is not useful project intent.

`irminsul init --fresh` should continue to work without `seed`. The seed command
is the next action after fresh init, not a replacement for init.

## Relationship to Existing RFCs

This RFC builds on fresh-start setup from
[`0007-fresh-start-init`](0007-fresh-start-init.md). It complements the agent
navigation manifest in [`0013-agents-manifest`](0013-agents-manifest.md) by
ensuring the manifest has real foundation content to point at.

## Drawbacks

The command introduces a second bootstrapping step after init. That is
intentional: `init` creates structure, while `seed` captures project intent.
Combining them would make `init --fresh` too interactive for automation.

The seed output can only structure the user's belief; it cannot decide whether
the belief is good. That remains a user judgment.

## Alternatives

- Keep seed text as manual edits to `principles.md`. Rejected because agents
  need a clear post-init step, not another convention.
- Add more prompts directly to `irminsul init --fresh`. Rejected because init
  must remain safe and scriptable.
- Use an LLM to infer the seed from a chat transcript. Rejected for the first
  version because the root intent should come from explicit user input.

## Unresolved Questions

- Should the non-interactive input be JSON only, or should individual flags be
  supported for short seeds?
- Should the generated ADR be a generic "start from PIB" decision, or should it
  be titled from the user's idea?
