---
id: 0016-agent-lifecycle-protocol
title: Agent lifecycle protocol
audience: explanation
tier: 2
status: stable
describes: []
rfc_state: accepted
resolved_by: docs/50-decisions/0007-implement-rfc-0016-agent-lifecycle-protocol.md
followups: []
---

# RFC 0016: Agent lifecycle protocol

## Summary

Define the required work order for agents using Irminsul: what to read before
editing, when to create or resolve RFCs, when to update ADRs and component docs,
and which checks to run before returning work.

## Motivation

Irminsul has commands that help agents find context and checks that detect many
forms of rot, but it does not yet tell agents what to do after what. In
particular, an agent can accept or complete an RFC without turning it into an
ADR, can add a component without updating component docs, or can change project
direction without revisiting foundation docs.

The protocol should be explicit enough that a new agent can follow it without
needing project-specific memory.

## Detailed Design

Add a lifecycle protocol document to scaffolded projects. The exact surface is
coordinated with [`0013-agents-manifest`](0013-agents-manifest.md): this RFC
defines the required process content, while RFC 0013 defines the manifest
surface that exposes agent navigation.

The protocol requires this work order:

0. Read `docs/AGENTS.md` (RFC-0013) before any other step. The manifest names
   the layers and tiers, the Three Laws, and this protocol. If the manifest is
   missing or its generated section is stale, run `irminsul regen agents-md`
   and proceed.
1. Before editing, run `irminsul context <target>`, `irminsul context --topic
   <query>`, or `irminsul context --changed` to locate ownership, dependencies,
   tests, and relevant findings.
2. If the user's request changes project direction, update the foundation docs
   or create an RFC before changing implementation.
3. If the work proposes a significant behavior, architecture, lifecycle, CLI, or
   check change, create or update an RFC.
4. When an RFC is accepted, create or update an ADR and link the RFC to that
   decision record.
5. When code is added or moved, create or update component docs with `describes`
   coverage and tests metadata. Before renaming or moving a code symbol, doc,
   or directory, run `irminsul refs <symbol-or-path>` (RFC-0014) to enumerate
   strong and weak inbound references, and update each before completing the
   move.
6. When workflows, commands, or reference surfaces change, update the
   corresponding workflow, component, or generated reference docs.
7. When a doc replaces another doc, use `supersedes` on the new doc and run
   `irminsul fix` to update the old doc's metadata.
8. Before final response, run `irminsul check --profile hard`; for larger work,
   also run `irminsul check --profile configured` and `irminsul list
   undocumented`.
9. Report any remaining warnings, skipped checks, or follow-up decisions in the
   final response.

The protocol lives at `docs/90-meta/agent-protocol.md` once RFC-0013 lands;
`docs/AGENTS.md` summarizes it and deep-links here. This keeps the manifest
scannable and the protocol authoritative.

## Relationship to Existing RFCs

This RFC depends on the task context command from
[`0011-agent-context-command`](0011-agent-context-command.md), the agent
manifest proposed in [`0013-agents-manifest`](0013-agents-manifest.md), and the
reference lookup proposed in [`0014-backlinks-and-refs`](0014-backlinks-and-refs.md).

## Drawbacks

The protocol adds process weight. That cost is acceptable because it applies
where agents are already changing project state, and it turns implicit reviewer
expectations into explicit instructions.

The first version cannot guarantee that every agent follows the protocol. Later
RFCs can add checks that detect incomplete lifecycle transitions.

## Alternatives

- Put all lifecycle guidance only in `CLAUDE.md`. Rejected because Irminsul
  should be agent-neutral.
- Rely on `irminsul context` output alone. Rejected because context answers
  "what is relevant now," not "what work order should I follow."
- Make every protocol violation a hard check immediately. Rejected because the
  lifecycle needs advisory rollout before hard enforcement.

## Unresolved Questions

- Should the final-response reporting requirement be represented in generated
  agent instructions outside the docs tree?

## Resolution

Accepted 2026-05-15 by
[`ADR-0007`](../../50-decisions/0007-implement-rfc-0016-agent-lifecycle-protocol.md).
The canonical protocol document lives at
[`docs/90-meta/agent-protocol.md`](../../90-meta/agent-protocol.md) and is
shipped as an init-scaffold template so every new project gets it on day one.
No new check ships with this resolution; enforcement of incomplete lifecycle
transitions is deferred to later RFCs (notably
[`0017-rfc-resolution-check`](0017-rfc-resolution-check.md)).
