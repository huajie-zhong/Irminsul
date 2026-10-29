---
id: a-change-may-not-lower-its-own-gates
title: A change may not lower its own gates
status: stable
describes: []
summary: Under --diff every config setting and every gate file is compared with the merge base, a weakening is certain or a hint by what it does, and only a decision record the change adds, naming what it weakens, clears it.
governs:
  - src/irminsul/checks/diff_integrity.py#run_diff_integrity
  - src/irminsul/checks/diff_integrity.py#_SEALS
  - src/irminsul/checks/diff_integrity.py#_Seal
  - src/irminsul/checks/diff_integrity.py#_Change
  - src/irminsul/checks/diff_integrity.py#_config_weakening
  - src/irminsul/checks/diff_integrity.py#_changes
  - src/irminsul/checks/diff_integrity.py#_weakenings
  - src/irminsul/checks/diff_integrity.py#_by_identity
  - src/irminsul/checks/diff_integrity.py#_parsed
  - src/irminsul/checks/diff_integrity.py#_adopting
  - src/irminsul/checks/diff_integrity.py#_accepted_decision_text
  - src/irminsul/checks/diff_integrity.py#_changed_gate_files
  - src/irminsul/checks/diff_integrity.py#_is_gate_path
retires:
  - id: gate-strength-scoring
    kind: concept
    matches:
      - gate-weakened
      - filter-unreadable
      - filter-not-compared
    guidance: A changed gate file is reported as `diff-integrity/gate-file-changed`; a stable decision record added in the same change clears it by naming the file's path in a code span.
---

# A change may not lower its own gates

## Status

Accepted, 2026-10-28. Resolves [A gate file is sealed, not scored](../rfcs/a-gate-file-is-sealed-not-scored.md).

## Context

A change is judged by the config and workflows at its head. An agent stuck on a failing check
can remove it from `checks.enabled`, set its `enabled` key to `false`, widen
`mtime_drift_days` from 30 to 3650, or rewrite the CI step as
`irminsul check --diff origin/main || echo docs drift`, and the run that should stop it
passes. A person may ask for exactly that, so a weakening cannot simply be blocked, but it must
be visible to the reviewer. Code owners do not help: an agent with its user's credentials can
approve its own pull request. Scoring workflow steps does not either: the ways to discard an
exit status cannot be listed.

## Decision

- **Under `--diff`, `diff-integrity` compares every field of `irminsul.toml` with the merge
  base.** The judged rules are one map, `_SEALS` in `checks/diff_integrity.py`, keyed by
  dotted name and giving the change that makes a check ask less, such as raised, narrowed or
  removed by identity. A test holds the map to the schema: every key names a field, and every
  field it does not call inert is reported when it changes.
- **Turning a gate off is certain.** `diff-integrity/check-disabled`: a check removed from
  `checks.enabled`, or `paths.docs_root` moved. `diff-integrity/layer-rule-disabled`: a
  layer's `require_tests` or `require_scope_section` turned off, or its folder moved.
  `diff-integrity/setting-weakened`: a check's own `enabled` turned off, a threshold widened,
  the glossary repointed, or a declared source removed or given another path or ref.
- **Narrowing what checks read is a hint**, because it is routine and its effect depends on the
  files. `diff-integrity/source-excluded`: an added include or exclude, a removed source root,
  test root or language, emptied test patterns, or gitignore honoured.
  `diff-integrity/extra-doc-removed`: a file dropped from `paths.extra_docs`.
  `diff-integrity/rules-narrowed`: a `surface.rules` entry gone by its `(kind, globs)`, or a
  framework pack dropped.
- **The seal follows a rule's identity:** under `--diff`, `surface.rules` is compared by
  `(kind, globs)`, and a base with the old table has its rules read from it, so the move reports
  nothing.
- **Any other change is a hint,** `diff-integrity/unreviewed-setting-change`, so a setting
  added to the schema later is never a free bypass. Only `project_name` is inert; moving
  `paths.baseline` or `paths.adoption` is such a hint, because it can move a gate.
- **A gate file is sealed whole.** A file under `.github/workflows/`, or an `action.yml` or
  `action.yaml` anywhere, whose text mentions irminsul at the merge base or the head is a gate
  file. Adding, deleting, renaming or editing one is `diff-integrity/gate-file-changed`,
  certain. The text is searched, not parsed, and nothing scores a step.
- **The excuse is a decision record the change adds.** A stable decision record added in the
  same change whose `## Decision` names, in a code span, what was weakened clears that
  subject's findings and no other, hints included: a setting by its dotted name, such as
  `layers.components.require_tests`; a removed check by its name, such as `links`; a gate file
  by its path, a deleted one by the path it had. The baseline and claims take the same excuse.
  Editing an existing record does not count, since a name such as `links` is an ordinary word
  an old record may contain.
- **The base decides what is sealed.** The decisions and RFC folders and the baseline path come
  from the merge base's config. A base with neither an `irminsul.toml` nor a baseline is
  adopting and has nothing to weaken. A base config that does not load is
  `diff-integrity/base-config-unreadable`, a hint: the config is not compared, and the sealed
  folders come from the head's config.
- **A commit trailer replaces the record excuse** (accepted, not yet implemented). A weakened
  setting, a removed check or a changed gate file is answered by an `Irminsul-Reviewed` trailer
  naming its subject, a setting by its dotted name with `irminsul.toml` as the path, and an
  added decision record answers nothing; a finding a trailer accepts prints at info with its
  reason. This replaces "The excuse is a decision record the change adds" above.
- **Four more settings have a direction** (accepted, not yet implemented):
  `checks.schema_leak.protected_paths` weakens when set or narrowed,
  `checks.external_links.ttl_hours` and `checks.external_links.timeout_seconds` when raised,
  and `checks.external_links.cache_path` on any change, each `setting-weakened` that way and
  nothing the other. A narrowing that drops files still on disk is
  `diff-integrity/files-dropped`, certain.
- **A base config that does not load is compared through the newest earlier one that loads**
  (accepted, not yet implemented), read back through the commits that changed `irminsul.toml`;
  only when none loads is `base-config-unreadable` reported, at info, and
  `adoption-base-unreadable` merges into it.

## Alternatives Considered

- **Code owners on the config.** Rejected: the approval can come from the agent itself.
- **Always block a weakening.** Rejected: a person dropping a check needs a path that does not
  bypass the gate.
- **Compare the config as text.** Rejected: a reformat would report and an equivalent rewrite
  would not be recognised.
- **Annotate every field with a direction.** Rejected: it forces a direction onto fields nobody
  has classified.
- **Accept bare setting names beside the dotted ones.** Rejected: two names for one setting, and
  a bare `require_tests` cannot say which layer.
- **Let the rename report `rules-narrowed`, answered by a record.** Rejected: nothing was
  removed, and the record would also excuse a rule dropped beside the rename.
- **Score workflow steps, adding each new spelling.** Rejected: the spellings cannot be listed.
- **A hint that a gating workflow changed.** Rejected: a hint does not stop the change that
  removes the gate.
- **Seal every workflow.** Rejected: a lint-only edit would need a record about a gate it does
  not hold.

## Consequences

- **The record proves a reason was written, not that anyone agreed.** The same author can
  weaken a setting and add the record in one commit; what the seal removes is silence. A second
  pair of eyes is branch protection on the forge, which no check here can read
  ([enforcement](../foundation/enforcement.md)).
- A harmless edit to a gate file, such as an `actions/checkout` bump, needs a one-line record.
- **Known limit:** the excuse is per setting, not per entry, so a record naming
  `paths.sources.ref` clears a ref change on every declared source.
- A gate run through a script or a reusable workflow elsewhere is sealed only if the calling
  workflow mentions irminsul. A plain `irminsul check` compares nothing.

## Changes

- 2026-10-29: Accepted [Each finding code has one answer](../rfcs/every-warning-hint-has-an-answer.md):
  a trailer replaces the record excuse, four settings gain a direction, and a base config
  that does not load is compared through an earlier one.
