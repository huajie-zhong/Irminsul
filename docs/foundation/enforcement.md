---
id: enforcement
title: Mechanical Enforcement
status: stable
summary: How documentation rules become deterministic checks, which findings block and which advise, and why CI rather than local tooling is where they hold.
describes: []
claims:
  - id: checks-are-deterministic
    state: implemented
    kind: invariant
    relation: governs-evidence
    claim: Every check reaches its verdict by deterministic computation over the graph, the filesystem, and git, so a rule needing semantic judgment reports a hint and leaves the judgment to the agent or human reading it.
    evidence:
      - pyproject.toml
      - src/irminsul/checks/pipeline.py
  - id: certain-findings-block
    state: enabled
    kind: ci_gate
    relation: follows-evidence
    claim: This repository runs its enabled Irminsul checks in CI and fails on any certain finding except a draft doc's own unfinished-doc codes.
    evidence:
      - .github/workflows/ci.yml
      - irminsul.toml
      - src/irminsul/checks/pipeline.py
  - id: hints-advise
    state: implemented
    kind: advisory_checks
    relation: governs-evidence
    claim: A hint or time finding is never an error — a run fails on one only when the invocation opts in to failing on it, an info-severity hint never fails a run, and a time finding is left out of a run given a diff range.
    evidence:
      - src/irminsul/checks/pipeline.py
      - src/irminsul/cli.py
  - id: fix-remediation-available
    state: implemented
    kind: auto_fix
    relation: governs-evidence
    claim: The fix command applies only remediations a check supplies for the findings that check reports, and an edit that rewrites load-bearing content waits for --confirm.
    evidence:
      - src/irminsul/cli.py
      - src/irminsul/fix.py
  - id: source-deletion-reckoning-available
    state: enabled
    kind: ci_gate
    relation: follows-evidence
    claim: Deleting a claimed source file without changing its owning doc is reported by co-change when a diff is supplied, which this repository's CI does on pull requests.
    evidence:
      - .github/workflows/ci.yml
      - src/irminsul/checks/co_change.py
---

# Mechanical Enforcement

The point of the whole system is that you do not have to remember every rule. The tooling turns structural documentation rules into checks, and this repository's CI blocks violations by running `irminsul check`. <!-- claim:certain-findings-block --> <!-- irminsul:ignore liar reason="names commands in passing across the doc, not a surface list" -->

This technical layer provides the mechanical realization of [**The Harness Principle**](principles.md#strategic-assumptions).

## Three Classes of Finding

Every check is deterministic, and every finding it reports has one of three [finding classes](../GLOSSARY.md#finding-class): <!-- claim:checks-are-deterministic -->

- **Certain, blocking.** The tree provably breaks a rule, such as a link to a file that does not exist. CI fails. <!-- claim:certain-findings-block -->
- **Hint, advisory.** Something may be wrong and deciding needs judgment, such as a doc older than the code it claims. The finding is reported for an agent or reviewer to investigate, and a run fails on it only when the invocation opts in with `--strict` or `--fail-on`. <!-- claim:hints-advise -->
- **Time, advisory.** The finding comes from elapsed time or the outside world, such as a deprecated doc past its threshold. It is left out of a run given a diff range, so a pull request is never blamed for it. <!-- claim:hints-advise -->

Every finding is computed; what separates the classes is whether the computation proves a rule broken. A certain finding does, so it blocks. A hint shows only that something may be wrong, and the judgment belongs to the agent or reviewer reading it, because build correctness never depends on model judgment ([Principles](principles.md#goals), [Deterministic enforcement](../decisions/deterministic-enforcement.md)). [Finding classes decide what blocks](../decisions/finding-classes-decide-what-blocks.md) records the three classes, and `irminsul explain <code>` prints the class of any code. <!-- claim:checks-are-deterministic -->

The full list of checks is the registry in `src/irminsul/checks/__init__.py`; `irminsul orient` reports which ones a project enables.

## The Change Triplet

Every PR should touch the right combination of three things: **code**, **tests**, and **docs**. The tooling makes a missing doc update visible — `co-change` reports a claimed source file that changed without its owning doc — but final judgment about whether a specific change needs prose still belongs to reviewers.

## Pre-commit Hooks (run locally before push)

The hooks are whatever [`.pre-commit-config.yaml`](../../.pre-commit-config.yaml) declares. They run only in a clone where someone installed them, and a commit can skip them, so they catch a violation early but cannot be relied on to stop one: the gate every pull request meets is the CI run below. <!-- claim:certain-findings-block -->

## CI Pipeline (run on every PR)

This repository's [CI workflow](../../.github/workflows/ci.yml) runs `irminsul check` over the enabled checks, and on a pull request runs it again with `--diff` against the base branch. An Irminsul step fails the workflow when any finding it reports is certain. <!-- claim:certain-findings-block -->

The `--diff` run is what turns on the passes that judge a change rather than the tree as it stands: `co-change` and the gate-integrity pass described below. The base it compares against comes from the event that delivered the change — `github.base_ref` on a pull request, `github.event.merge_group.base_ref` in a merge queue — and never from `HEAD`, which on a branch already holds the commits being judged and would compare the change with itself. The CLI takes the merge base of that ref and `HEAD`, so a base branch that has moved on does not report its own commits as this change's. The checkout uses `fetch-depth: 0` because every history-reading check finds nothing at depth 1 and reports nothing, which reads exactly like a clean tree.

### What the workflow cannot enforce <!-- irminsul:ignore claim-provenance/risky-prose-unclaimed reason="the subject is a GitHub setting outside this repository, so no evidence file exists for a claim to rest on; the paragraph exists to say exactly that" -->

Requiring these runs before a merge is a repository setting on GitHub, not a line of YAML, and nothing in Irminsul can read or verify it — a green pipeline on an unprotected branch proves only that the pipeline ran. Enabling it is a person's job, once, in **Settings → Branches → branch protection for `main`**: require a pull request, and require these status checks, whose names are what the jobs render as:

| Required check | Job |
|---|---|
| `lint` | `ruff check` and `ruff format --check` |
| `type` | `mypy` |
| `test (ubuntu-latest, 3.12)` … `test (windows-latest, 3.13)` | the six matrix cells |
| `dogfood` | `irminsul check`, plus `irminsul check --diff` on a pull request or merge queue |
| `action` | the composite Action against this repository |

`dogfood` is the one that carries the gate-integrity seal; without it required, a pull request can weaken the gate and merge. A matrix cell's name is the job id followed by its matrix values in declaration order, so renaming a job or reordering the matrix renames the check and silently un-requires it.

## Supersession Enforcement (the "Did Anyone Mark This Deprecated?" Problem)

The most insidious failure mode is silent replacement: someone writes `composer-v2.md` covering the same ground as `composer.md`, but forgets to mark the old doc deprecated. Now both exist, both look authoritative, and they slowly contradict each other. <!-- irminsul:ignore prose-file-reference reason="example skeleton" -->

Deterministic checks reduce this risk by enforcing source-ownership uniqueness and supersession consistency. <!-- claim:certain-findings-block -->

`irminsul fix` applies only the remediations a check supplies for its own findings. When a supersession finding has one unambiguous remediation, it updates the old doc's frontmatter: it adds a missing `superseded_by` directly, and holds setting `status: deprecated` until `--confirm`, because that rewrites load-bearing metadata. <!-- claim:fix-remediation-available -->

Deleted source is reckoned with by `co-change`. Given `--diff <base>`, a claimed source file deleted in that range warns on its owning doc unless the doc changed in the same diff, and `--strict` makes that warning fail the run. This repository's CI passes `--diff` on pull requests, so the reckoning is enabled here. <!-- claim:source-deletion-reckoning-available -->

The combination is the point. Certain findings prevent mechanically invalid documentation states, while check-supplied fixes repair supported failure modes without inventing intent. <!-- claim:certain-findings-block --> <!-- claim:fix-remediation-available -->

## Gates a Change Cannot Lower

A finding can be cleared by weakening what raised it: deleting the claim it cites, turning its check off, dropping the CI step that runs it, or recording it in the baseline. Given a diff range, the diff-integrity pass compares a change with its merge base, which the change cannot rewrite, and reports those moves; [the checks component](../components/checks.md) explains how it compares workflows. The rules it applies are recorded in [Git history seals implemented records](../decisions/git-history-seals-implemented-records.md), [Baseline holds certain findings and only shrinks](../decisions/baseline-holds-certain-findings-and-only-shrinks.md), [Weakening the config needs a decision record](../decisions/weakening-the-config-needs-a-decision-record.md), and [Removing a claim about surviving code is a finding](../decisions/removing-a-claim-about-surviving-code-is-a-finding.md); a claim that governs its evidence is protected from rewording the same way ([Authority follows the kind of claim](../decisions/authority-follows-the-kind-of-claim.md)). <!-- irminsul:ignore claim-provenance/risky-prose-unclaimed reason="the linked decision records are this paragraph's provenance; a claim would restate them" -->

## Documentation Health

Irminsul commits no health report. Health is derived when someone asks — [`irminsul status`](../components/status.md) is the one-glance digest — because a generated report would be a copy of facts the tree already holds, and [Derive, don't materialize](../decisions/derive-dont-materialize.md) keeps the agent manifest as the only generated artifact.
