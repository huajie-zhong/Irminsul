---
id: finding-classes-decide-what-blocks
title: Finding classes decide what blocks
status: stable
describes: []
summary: Every finding code is certain, hint, or time; certain findings block, hints are investigated, time findings stay off pull requests, and one enabled list replaces hard and soft.
retires:
  - id: split-check-lists
    kind: concept
    matches:
      - soft_deterministic
      - checks.hard
      - HARD_REGISTRY
      - SOFT_REGISTRY
      - hard check
      - hard checks
      - soft check
      - soft checks
      - soft deterministic
    guidance: List the checks to run in `checks.enabled`; whether a finding blocks follows its class, certain, hint, or time.
  - id: hard-and-configured-profiles
    kind: concept
    matches:
      - --profile=hard
      - --profile hard
      - --profile=configured
      - --profile configured
      - "profile: hard"
      - "profile: configured"
      - hard profile
      - configured profile
    guidance: Run `irminsul check`, which runs the enabled checks; `--profile all-available` runs every check.
---

# Finding classes decide what blocks

## Status

Accepted, 2026-09-15.

## Context

[Deterministic enforcement](deterministic-enforcement.md) split checks into hard and soft, and let the
list a check sat in decide whether its findings could fail a run. That test was drawn around
the wrong thing. One check emits findings of different strength: `claim-anchor` reports a
symbol that does not exist, which is simply wrong, and code that changed since a claim was
pinned, which may be fine. Hard checks emitted warnings that never blocked, soft checks
emitted errors, and most rot findings were warnings that merged unread.

Deterministic checks also report two different things. Some findings prove the tree breaks a
rule. Others only point at something suspicious that a reader or an agent has to judge.
Blocking a merge on the second kind leaves an agent two ways to get green: game the signal,
such as touching a doc to reset its age, or suppress it.

## Decision

- **Every finding code has a class.** Each check declares the class of every code it
  explains, next to the explanation, and a test requires that every explained code has one.
  - **Certain.** The tree provably breaks a rule, and the fix is unambiguous: a link to a
    file that does not exist, a command no CLI declares, an ADR with no `## Decision`.
    Certain findings are errors and fail every run.
  - **Hint.** Something may be wrong, and deciding needs judgment: a doc older than the code
    it claims, speculative wording, a pinned anchor whose code changed. Hints are warnings
    or info, never errors; a warning fails a run only under `--strict`, and an info never does. An agent resolves a hint by
    investigating, then fixing the doc or leaving a reasoned ignore comment for a reviewer.
  - **Time.** The finding appears because time passed or the outside world changed, not
    because of a change to the repository: a deprecated doc past its threshold, a draft
    RFC's decision date in the past, an unreachable external link. Time findings are
    warnings and are left out of a run given a diff range, so a pull request is never
    blamed for the calendar.
- **Drafts are work in progress.** A certain finding on a doc whose `status` is `draft`
  keeps the severity its check chose, so an RFC can be committed while its requirements are
  still incomplete. Structural errors, such as unparseable frontmatter, stay errors.
- **One enabled list.** `checks.enabled` names the checks a repository runs, replacing
  `checks.hard` and `checks.soft_deterministic`. `--profile` takes `enabled`, the default,
  or `all-available`. A configuration that still uses the old keys fails to load with the
  new key named.
- **Ignore comments reach hints and time findings only.** A comment that names a certain
  code, or a check whose every code is certain, suppresses nothing and is itself reported.
  `prose-file-reference` keeps its own audited markers, because a bare filename in an
  example is the one certain finding whose rule has a legitimate, reviewable exception.
- **Output carries the class.** Every finding in JSON output includes its `class`, so a CI
  annotation or an agent can treat hints as questions and certain findings as failures.

The classification of every code is `irminsul explain <code>`, which prints the class beside the explanation. This record deliberately holds no table of them: the mapping lives in each check's `classes` declaration, and a copy here would be a cache inside a record that must not change. The copy that used to sit here had already drifted — it omitted a whole check and listed a promoted code under its old class.

## Alternatives Considered

- **Keep hard and soft beside the classes.** Rejected: two overlapping axes decide what runs
  and what blocks, and every doc would have to explain both.
- **Class per check instead of per code.** Rejected: one check emits both proven and
  suspected findings, which is the failure this record corrects.
- **Block new hints in pull requests with `--delta`.** Rejected: some hints have no honest
  fix when the doc is right, so blocking on them teaches an agent to game the signal.
- **Promote rot warnings to errors in the components layer.** Rejected: a layer does not make
  a suspicion into a proof.

## Consequences

- Findings that were warnings and are certain now fail runs, among them orphans, unlisted
  siblings, ADR structure, and supersession reciprocity. A repository upgrading into these
  errors adopts them through its baseline or fixes them.
- Hints no longer need `--strict` to be seen; they reach an agent through the review loop
  and a pull request's annotations, and a reviewer sees each reasoned suppression in the diff.
- Adding a code means choosing its class. A code whose certainty is unclear is a hint until
  a mechanical proof exists.
