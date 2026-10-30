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
    pinned:
      pyproject.toml: sha256:4ab5d4b249e6
      src/irminsul/checks/pipeline.py: sha256:3a133bab63c0
  - id: certain-findings-block
    state: enabled
    kind: ci_gate
    relation: follows-evidence
    claim: This repository runs its enabled Irminsul checks in CI and fails on any certain finding except a draft doc's own unfinished-doc codes.
    evidence:
      - .github/workflows/ci.yml
      - irminsul.toml
      - src/irminsul/checks/pipeline.py
    pinned:
      .github/workflows/ci.yml: sha256:18ef8c6bad1a
      irminsul.toml: sha256:4e83be9b6bc4
      src/irminsul/checks/pipeline.py: sha256:3a133bab63c0
  - id: hints-advise
    state: implemented
    kind: advisory_checks
    relation: governs-evidence
    claim: A hint or time finding is never an error — a run fails on one only when the invocation opts in to failing on it, an info-severity hint never fails a run, and a time finding is left out of a run given a diff range.
    evidence:
      - src/irminsul/checks/pipeline.py
      - src/irminsul/cli.py
    pinned:
      src/irminsul/checks/pipeline.py: sha256:3a133bab63c0
      src/irminsul/cli.py: sha256:e4d4e00586b4
  - id: fix-remediation-available
    state: implemented
    kind: auto_fix
    relation: governs-evidence
    claim: The fix command applies only remediations a check supplies for the findings that check reports, and an edit that rewrites load-bearing content waits for --confirm.
    evidence:
      - src/irminsul/cli.py
      - src/irminsul/fix.py
    pinned:
      src/irminsul/cli.py: sha256:e4d4e00586b4
      src/irminsul/fix.py: sha256:cc4c24a9385c
  - id: source-deletion-reckoning-available
    state: enabled
    kind: ci_gate
    relation: follows-evidence
    claim: Deleting a claimed source file without changing its owning doc is reported by co-change when a diff is supplied, which this repository's CI does on pull requests.
    evidence:
      - .github/workflows/ci.yml
      - src/irminsul/checks/co_change.py
    pinned:
      .github/workflows/ci.yml: sha256:18ef8c6bad1a
      src/irminsul/checks/co_change.py: sha256:411718444fe4
---

# Mechanical Enforcement

The point of the whole system is that you do not have to remember every rule. The tooling turns structural documentation rules into checks, and this repository's CI blocks violations by running `irminsul check`. <!-- claim:certain-findings-block --> It is the mechanical side of [The Harness Principle](principles.md#strategic-assumptions).

## Three Classes of Finding

Every check is deterministic, and every finding it reports has one of three [finding classes](../GLOSSARY.md#finding-class): <!-- claim:checks-are-deterministic -->

- **Certain** findings prove the tree breaks a rule, such as a link to a file that does not exist, and fail CI. <!-- claim:certain-findings-block -->
- **Hint** findings need judgment, such as a doc older than the code it claims, and fail a run only when the invocation opts in with `--fail-on`. <!-- claim:hints-advise -->
- **Time** findings come from elapsed time or the outside world, and a run given a diff range leaves them out, so a pull request is never blamed for one. <!-- claim:hints-advise -->

Every finding is computed; what separates the classes is whether the computation proves a rule broken. A certain finding does, so it blocks. A hint shows only that something may be wrong, and the judgment belongs to the agent or reviewer reading it, because build correctness never depends on model judgment ([Principles](principles.md#goals)). [Finding classes decide what blocks](../decisions/finding-classes-decide-what-blocks.md) records the classes, and `irminsul explain <code>` prints the class of any code. <!-- claim:checks-are-deterministic -->

## Where the Gate Holds

Pre-commit hooks ([`.pre-commit-config.yaml`](../../.pre-commit-config.yaml)) run only in a clone where someone installed them, and a commit can skip them, so they catch a violation early but cannot stop one: the gate every pull request meets is CI. <!-- claim:certain-findings-block -->

The `dogfood` job of the [CI workflow](../../.github/workflows/ci.yml) runs `irminsul check --diff` against the base branch on a pull request or in a merge queue, and `irminsul check` on a push to `main`, both with `--fail-on hint`, so a certain finding or a hint fails it. <!-- claim:certain-findings-block --> Its checkout uses `fetch-depth: 0` because every history-reading check finds nothing at depth 1 and reports nothing, which reads exactly like a clean tree. [CI runs each gate once, and the Action takes typed inputs](../decisions/ci-runs-each-gate-once-and-the-action-takes-typed-inputs.md) records why the jobs and legs are these.

### What the workflow cannot enforce

Requiring these runs before a merge is a repository setting on GitHub, not a line of YAML, and nothing in Irminsul can read or verify it: a green pipeline on an unprotected branch proves only that the pipeline ran. A person enables it once, under **Settings → Branches → branch protection for `main`**, by requiring a pull request and these status checks: `lint`, `test (ubuntu-latest, 3.12)`, `test (ubuntu-latest, 3.13)`, `test (windows-latest, 3.12)`, `test (macos-latest, 3.12)`, `dogfood`, `action` and `package`.

`dogfood` is the one that carries the gate-integrity seal; without it required, a pull request can weaken the gate and merge. A `test` leg's name comes from the job's `name:` line, built from its `os` and `python-version`, so changing that line or a leg renames the check and silently un-requires it.

## Supersession Enforcement

The most insidious failure mode is silent replacement: someone writes `composer-v2.md` covering the same ground as `composer.md` but forgets to mark the old doc deprecated, so both look authoritative and slowly contradict each other. <!-- irminsul:ignore code-references reason="example skeleton" --> Deterministic checks reduce this risk by enforcing source-ownership uniqueness and supersession consistency. <!-- claim:certain-findings-block -->

`irminsul fix` applies only the remediations a check supplies for its own findings. For a superseded doc that is still live, neither deprecated nor removed, it sets `status: deprecated`, and holds that edit until `--confirm` because it rewrites load-bearing metadata. <!-- claim:fix-remediation-available --> Certain findings prevent mechanically invalid states, while check-supplied fixes repair supported failure modes without inventing intent. <!-- claim:certain-findings-block --> <!-- claim:fix-remediation-available -->

Deleted source is reckoned with by `co-change`: given `--diff <base>`, a claimed source file deleted in that range warns on its owning doc unless the doc changed in the same diff, and this repository's CI passes `--diff --fail-on hint` on pull requests, so the warning blocks the merge. <!-- claim:source-deletion-reckoning-available -->

## Gates a Change Cannot Lower

A finding can be cleared by weakening what raised it: deleting the claim it cites, turning its check off, dropping the CI step that runs it, or recording it in the baseline. Given a diff range, the diff-integrity pass ([checks](../components/checks.md)) compares the change with its merge base, which the change cannot rewrite, and reports those moves under [RFCs have four states, and git history seals decided records](../decisions/rfcs-have-four-states-and-git-history-seals-decided-records.md), [A baseline holds certain findings and grows only by decision](../decisions/a-baseline-holds-certain-findings-and-grows-only-by-decision.md), [A change may not lower its own gates](../decisions/a-change-may-not-lower-its-own-gates.md) and [Authority follows the kind of claim](../decisions/authority-follows-the-kind-of-claim.md).

## Documentation Health

Irminsul commits no health report: [`irminsul orient`](../components/orient.md) counts source ownership and `irminsul check` the findings when someone asks, because a committed report would copy facts the tree already holds ([Derive facts and leave meaning to the reader](../decisions/derive-facts-and-leave-meaning-to-the-reader.md)).
