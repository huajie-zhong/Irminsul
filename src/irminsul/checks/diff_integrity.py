"""Diff integrity — a change must not quietly lower the gates it is judged by.

Not a registered graph check: like `co-change`, it needs the diff range only the CLI's
`--diff <base>` (or `--base-ref`/`--head-ref`) supplies, so the CLI calls
`run_diff_integrity` directly. It compares files with their content at the merge base,
which a pull request cannot rewrite, and reports:

- the baseline gained entries, so new findings were recorded instead of fixed;
- an RFC that was implemented at the base changed, or no longer exists;
- a decision record that was accepted at the base no longer exists;
- an accepted decision record's `## Decision` section was rewritten in place;
- a source file's owning doc changed, so the old owner's prose about it may stay behind;
- the config turned a check or a layer rule off, unless a decision record the same diff
  adds names it in a code span, or the source walk or guidance files were narrowed;
- an anchor, a `claims:` entry, or an `inventory:` entry was deleted while the code it
  named is still there, so a doc stopped asking about code that still exists. The same
  removal is not reported when that code went away in the same change — except for a
  claim that governed its evidence at the base, which only a decision record ends;
- a claim was reworded rather than removed — a hint, since nothing separates correcting
  a sentence from emptying it of meaning — unless it is `follows-evidence`, where the
  evidence wins and correcting the report is routine;
- a `governs-evidence` claim had its wording, evidence, state, kind or relation changed,
  each of which stops it governing what it governed at the base;
- an `inventory:` entry kept its kind and source but asks less than it did — it dropped
  `explained_in`, dropped `complete`, or gained an `omit`. The removal seal keys on
  `(kind, source)` alone, so a contract could otherwise be hollowed out in place.

A record missing at its old path is not reported when git reports it as renamed, or
when a record at another path holds the same text apart from its `id`. A renamed record
is still read at its old path, so the governance it dropped along the way is caught, and
compared without its `id:` line, which has to change with the filename.
"""

from __future__ import annotations

import json
import posixpath
import re
import tomllib
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import ClassVar, Final

from pathspec import GitIgnoreSpec
from pydantic import BaseModel
from ruamel.yaml import YAML

from irminsul import source_map
from irminsul.checks.base import Finding, FindingClass, Severity
from irminsul.config import (
    CONFIG_FILENAME,
    IrminsulConfig,
    LayerName,
    docs_root_prefix,
    in_layer,
    layer_prefix,
)
from irminsul.docgraph import DocGraph, guidance_files
from irminsul.frontmatter_edit import split_frontmatter
from irminsul.git.changes import (
    GitChangesError,
    exists_at_ref,
    file_at_ref,
    files_at_ref,
    merge_base,
    renamed_paths,
    tracked_paths_at_ref,
    working_tree_changed_paths,
)
from irminsul.source_map import Binding, SourceMap

CHECK_NAME: Final = "diff-integrity"
CODE_BASELINE_GREW: Final = "diff-integrity/baseline-grew"
CODE_ADOPTION_RECORD_GREW: Final = "diff-integrity/adoption-record-grew"
CODE_ADOPTION_DEBT_TOUCHED: Final = "diff-integrity/adoption-debt-touched"
CODE_ADOPTION_EXCEPTION_REVIVED: Final = "diff-integrity/adoption-exception-revived"
CODE_ADOPTION_DEBT_NOT_HISTORICAL: Final = "diff-integrity/adoption-debt-not-historical"
CODE_ADOPTION_RECORD_REMOVED: Final = "diff-integrity/adoption-record-removed"
CODE_ADOPTION_SOURCE_REBOUND: Final = "diff-integrity/adoption-source-rebound"
CODE_ADOPTION_BASE_UNREADABLE: Final = "diff-integrity/adoption-base-unreadable"
CODE_ADOPTION_DEBT_ALREADY_OWNED: Final = "diff-integrity/adoption-debt-already-owned"
CODE_ADOPTION_DEBT_NOT_MANAGED: Final = "diff-integrity/adoption-debt-not-managed"
CODE_ADOPTION_PIN_NOT_ON_REF: Final = "diff-integrity/adoption-pin-not-on-ref"
CODE_IMPLEMENTED_RFC_CHANGED: Final = "diff-integrity/implemented-rfc-changed"
CODE_IMPLEMENTED_RFC_REMOVED: Final = "diff-integrity/implemented-rfc-removed"
CODE_ACCEPTED_DECISION_REMOVED: Final = "diff-integrity/accepted-decision-removed"
CODE_DECISION_REWRITTEN: Final = "diff-integrity/decision-rewritten"
CODE_OWNER_CHANGED: Final = "diff-integrity/owner-changed"
CODE_CHECK_DISABLED: Final = "diff-integrity/check-disabled"
CODE_LAYER_RULE_DISABLED: Final = "diff-integrity/layer-rule-disabled"
CODE_SOURCE_EXCLUDED: Final = "diff-integrity/source-excluded"
CODE_EXTRA_DOC_REMOVED: Final = "diff-integrity/extra-doc-removed"
CODE_BASE_CONFIG_UNREADABLE: Final = "diff-integrity/base-config-unreadable"
CODE_GATE_WEAKENED: Final = "diff-integrity/gate-weakened"
CODE_ANCHOR_REMOVED: Final = "diff-integrity/anchor-removed"
CODE_CLAIM_REMOVED: Final = "diff-integrity/claim-removed"
CODE_GOVERNING_CLAIM_CHANGED: Final = "diff-integrity/governing-claim-changed"
CODE_GOVERNING_CLAIM_REMOVED: Final = "diff-integrity/governing-claim-removed"
CODE_CLAIM_REWORDED: Final = "diff-integrity/claim-reworded"
CODE_INVENTORY_REMOVED: Final = "diff-integrity/inventory-removed"
CODE_INVENTORY_WEAKENED: Final = "diff-integrity/inventory-weakened"
CODE_SETTING_WEAKENED: Final = "diff-integrity/setting-weakened"
CODE_UNREVIEWED_SETTING_CHANGE: Final = "diff-integrity/unreviewed-setting-change"
CODE_RULES_NARROWED: Final = "diff-integrity/rules-narrowed"
CODE_FILTER_UNREADABLE: Final = "diff-integrity/filter-unreadable"
CODE_FILTER_NOT_COMPARED: Final = "diff-integrity/filter-not-compared"
#: Settings whose weaker direction is unambiguous: switching the check off, or raising
#: the threshold it fires above. Keyed by the name a decision record must say in a code
#: span to accept the change.
#: Settings the comparisons above already judge, by dotted name under `checks`.
_JUDGED_SETTINGS: Final = frozenset(
    {
        "enabled",
        "external_links.enabled",
        "stale_reaper.deprecated_threshold_days",
        "rfc_follow_through.accepted_threshold_days",
        "parent_child.length_warning_lines",
        "glossary_discipline.glossary_path",
        "terminology_overload.rules",
        "inventory_drift.generic",
    }
)
_THRESHOLD_SETTINGS: Final[tuple[tuple[str, Callable[[IrminsulConfig], int]], ...]] = (
    ("mtime_drift_days", lambda c: c.overrides.mtime_drift_days),
    (
        "deprecated_threshold_days",
        lambda c: c.checks.stale_reaper.deprecated_threshold_days,
    ),
    (
        "accepted_threshold_days",
        lambda c: c.checks.rfc_follow_through.accepted_threshold_days,
    ),
    ("length_warning_lines", lambda c: c.checks.parent_child.length_warning_lines),
)
_LAYER_RULES: Final = ("require_tests", "require_scope_section", "forbid_speculation")

_DECISION_RE = re.compile(r"(?ms)^##\s+Decision\s*$(.*?)(?=^##\s|\Z)")
_ID_LINE_RE = re.compile(r"(?m)^id:[^\n]*\n")


class DiffIntegrityCheck:
    """Gives the diff-integrity pass a `name` and `explanations` for `irminsul explain`."""

    name: ClassVar[str] = CHECK_NAME
    default_severity: ClassVar[Severity] = Severity.error
    explanations: ClassVar[dict[str, str]] = {
        CODE_BASELINE_GREW: (
            "The baseline file records findings it did not record at the base of the diff, "
            "so new findings were recorded rather than fixed. Fix them and restore the "
            "baseline, or shrink it."
        ),
        CODE_ADOPTION_RECORD_GREW: (
            "The adoption record excepts a file it did not except at the base of the diff. "
            "That record is the finite list of files already unowned on the day this "
            "repository adopted Irminsul; a pull request that adds to it is excusing debt "
            "it just created. Give the file an owning doc instead. Only the change that "
            "creates the record may write entries into it."
        ),
        CODE_ADOPTION_SOURCE_REBOUND: (
            "The change moves the source revision an adoption record's entries are history "
            "at. That revision is the boundary: everything the source repository gained "
            "since would become pre-existing debt, which is the record growing without a "
            "line being added to it. Restore the recorded revision."
        ),
        CODE_ADOPTION_DEBT_ALREADY_OWNED: (
            "A first adoption record names a file that already has an owning doc. The exception "
            "buys nothing today and becomes live the day somebody removes that owner, which is "
            "a dormant exception rather than recorded history. Take the path out of the record; "
            "a documented file is not debt. Later changes are not judged this way, because a "
            "record that still names a file somebody has since documented is the ordinary "
            "state — nothing obliges anyone to run `--update-adoption`."
        ),
        CODE_ADOPTION_PIN_NOT_ON_REF: (
            "A first adoption record pins a source at a commit that the history the source "
            "declares does not contain. Anything committed off that history is not something "
            "the source repository's mainline ever had, so recording its files as pre-existing "
            "debt would except files nobody reviewed into that history — pushing a branch "
            "needs no review, and pinning it would be the whole of the attack. Pin a commit on "
            "the declared ref; `check --init-adoption` picks the merge base of the source "
            "checkout and that ref, which is such a commit by construction.\n\n"
            "Naming a ref is not a claim that it is protected. This checks that the pin is "
            "contained in that ref's history; whether the branch is protected, and who "
            "reviewed what reached it, are repository settings and reviews outside this tool."
        ),
        CODE_ADOPTION_DEBT_NOT_MANAGED: (
            "A first adoption record names a path that no configured root produces, so it "
            "excepts nothing and nothing checks it — until a root is widened and it starts "
            "excepting a file nobody adopted. Remove the entry, or fix the path. This is not "
            "reported when a configured root is missing from the checkout: then which files "
            "exist is unknown, and `adoption-record/source-unverifiable` says so instead."
        ),
        CODE_ADOPTION_BASE_UNREADABLE: (
            "The adoption record holds entries and the `irminsul.toml` at the merge base does "
            "not load, so what counted as an owner there cannot be read. Ownership is a "
            "declaration plus the rule that accepts it, and half that rule is configuration — "
            "so judging the base by this change's configuration would decide whether an "
            "exception retired using rules the base never had. Repair the configuration at the "
            "base, or rebase onto a commit whose configuration loads."
        ),
        CODE_ADOPTION_RECORD_REMOVED: (
            "The change deletes an adoption record that still holds entries. That hands back "
            "the coarse covered-directory guess the record replaced, and lets the next change "
            "adopt from scratch. Retire the entries with `--update-adoption` until the record "
            "is empty, or add a decision record naming the record's path and why."
        ),
        CODE_ADOPTION_DEBT_NOT_HISTORICAL: (
            "The first adoption record names a file that was not in the tree at the base of "
            "the diff, so this change both wrote the file and excused it as pre-existing "
            "debt. Document it, or land it separately from the adoption."
        ),
        CODE_ADOPTION_EXCEPTION_REVIVED: (
            "A file the adoption record names had an owning doc at the base of the diff, so "
            "its exception had already retired; this change takes that owner away and the "
            "record would hand the exception back. Keep an owner, or document the file "
            "somewhere else in this change."
        ),
        CODE_ADOPTION_DEBT_TOUCHED: (
            "This change edits a file the adoption record excepts. The exception covers "
            "pre-existing code nobody has gone back to; editing it means somebody has, so "
            "the same change gives it an owning doc and the exception retires. Add it to a "
            "doc's `describes:` (or `owns_tests:` for a test), or write one with "
            "`irminsul new component`."
        ),
        CODE_IMPLEMENTED_RFC_CHANGED: (
            "An RFC that was implemented at the base of the diff changed. Restore the record "
            "and propose the change in a new RFC."
        ),
        CODE_IMPLEMENTED_RFC_REMOVED: (
            "An RFC that was implemented at the base of the diff no longer exists, and no "
            "record elsewhere holds its text. Restore it; retire it by writing an RFC that "
            "supersedes it."
        ),
        CODE_ACCEPTED_DECISION_REMOVED: (
            "A decision record that was accepted at the base of the diff no longer exists, "
            "and no record elsewhere holds its text. Restore it; a changed decision belongs "
            "in a new ADR that supersedes it."
        ),
        CODE_DECISION_REWRITTEN: (
            "An accepted decision record's `## Decision` section was rewritten in place. "
            "Record a changed decision in a new ADR that supersedes this one."
        ),
        CODE_OWNER_CHANGED: (
            "Source files moved from one doc's `describes` to another's. Remove what the old "
            "owner still says about them, or link the two docs; `irminsul list review "
            "--changed` lists the old owner's sentences that name the files."
        ),
        CODE_CHECK_DISABLED: (
            "The change removed a check from `checks.enabled`, so the gate that judges this "
            "change got weaker. Restore it, or add a decision record in the same change that "
            "names the check in a code span and says why."
        ),
        CODE_LAYER_RULE_DISABLED: (
            "The change turned off a layer rule, such as `require_tests`, so the gate that "
            "judges this change got weaker. Restore it, or add a decision record in the same "
            "change that names the rule in a code span and says why."
        ),
        CODE_SOURCE_EXCLUDED: (
            "The change made the source walk read fewer files: an added source exclude or "
            "include, a removed source root or language, or gitignore honoured. Confirm the "
            "files no longer read hold no documented code."
        ),
        CODE_EXTRA_DOC_REMOVED: (
            "The change removed a file from `paths.extra_docs`, so the checks that read "
            "guidance files no longer read it. Confirm it holds no guidance to keep true."
        ),
        CODE_GATE_WEAKENED: (
            "A workflow dropped an `irminsul check` invocation or a step running the "
            "composite Action, or one of the flags or Action inputs that makes it a gate. "
            "The checks that seal records and compare a change with its "
            "base run only when CI asks for them, so a change that edits its own workflow "
            "can otherwise switch off the thing judging it. Restore the invocation, or add "
            "a decision record in the same change that names the flag in a code span."
        ),
        CODE_ANCHOR_REMOVED: (
            "An `<!-- anchor: ... -->` marker was deleted while the code it pinned is "
            "still there. An anchor is how a doc asks to be told when that code changes, "
            "so removing it silences the question instead of answering it. Restore the "
            "marker; delete it only when the code it names is gone too."
        ),
        CODE_CLAIM_REMOVED: (
            "A `claims:` entry was deleted while every file it cited still exists. The "
            "claim is what makes the prose around it checkable. Restore it, or, if the "
            "behaviour really went away, remove the evidence files in the same change."
        ),
        CODE_GOVERNING_CLAIM_REMOVED: (
            "A claim that governed its evidence at the base of the diff was deleted, "
            "renamed, or deleted along with its doc. A contract does not end because the "
            "code it governed was deleted in the same change: that is exactly the change "
            "it would forbid. Restore the claim, or add a decision record in the same change "
            "naming it in a code span."
        ),
        CODE_CLAIM_REWORDED: (
            "A claim's sentence changed while its id stayed the same, so it is a "
            "rewording rather than a removal. Nothing can tell a correction from a "
            "claim quietly emptied of meaning, so re-read it against the evidence it "
            "cites. A `follows-evidence` claim is exempt: the evidence wins there, and "
            "correcting the report is routine."
        ),
        CODE_GOVERNING_CLAIM_CHANGED: (
            "A claim that governs its evidence was rewritten, or stopped governing it. "
            "Such a claim is a contract: the implementation answers to it, so changing "
            "its words — or its `relation` — is a change of intent, not doc maintenance, "
            "and it must not ride along with the change it would otherwise forbid. Add a "
            "decision record in the same change naming the claim in a code span, or "
            "restore the wording."
        ),
        CODE_INVENTORY_WEAKENED: (
            "An `inventory:` entry kept its kind and source but asks less of the code "
            "than it did at the base of the diff: it stopped requiring the prose to "
            "explain each item, stopped demanding completeness, or added an `omit`. "
            "Each of those silences a live identity without removing the entry, which "
            "the removal seal watches. Restore the contract, or add a decision record in "
            "the same change that names the doc in a code span and says why."
        ),
        CODE_SETTING_WEAKENED: (
            "A setting that decides how much a check asks was weakened: the check was "
            "switched off through its own `enabled` key, a threshold it fires above was "
            "widened, or the glossary it reads was repointed. None of these touch "
            "`checks.enabled`, so the check stays listed while asking less. Restore the "
            "setting, or add a stable decision record in the same change naming it in a "
            "code span and saying why."
        ),
        CODE_RULES_NARROWED: (
            "A configured rule stopped watching something: a terminology term, an "
            "inventory `(kind, glob)` pair, or a framework pack. Compared by what the rule "
            "watched rather than by list length, since an edited rule and a deleted one "
            "shorten the list alike. Confirm nothing documented depended on it."
        ),
        CODE_UNREVIEWED_SETTING_CHANGE: (
            "A per-check settings table changed and no rule here judges whether that "
            "weakens the gate. Nothing is asserted to be wrong — it is a prompt to "
            "confirm, and to seal the setting if the answer needs to be mechanical."
        ),
        CODE_INVENTORY_REMOVED: (
            "An `inventory:` entry was deleted while its source still exists, so a "
            "watched surface stopped being watched. Restore it; narrow it with `omit` "
            "if some items should not be listed."
        ),
        CODE_BASE_CONFIG_UNREADABLE: (
            "The config at the base of the diff does not load with this version, so config "
            "weakening is not compared and sealed folders come from the change's own config. "
            "Review the config changes by hand."
        ),
        CODE_FILTER_UNREADABLE: (
            "This change left a gating workflow with a `paths:` or `paths-ignore:` entry "
            "that is not a pattern, so what the workflow admits could not be compared with "
            "the base and the narrowing pass did not run for that event. A filter that "
            "stops being comparable costs the seal an axis. GitHub's filter syntax is not a "
            "shell glob: `?` and `+` quantify the character before them and need one to "
            "quantify, and `[...]` must close and must not run its range backwards."
        ),
        CODE_FILTER_NOT_COMPARED: (
            "A gating workflow's path filter holds an entry that is not a pattern, and it "
            "was already unreadable at the base of the diff. What the gate admits is "
            "therefore unknown on at least one side, so the narrowing pass did not run for "
            "that event. Nothing is asserted to be wrong with this change — review the "
            "filter by hand, and fixing the entry restores the comparison."
        ),
    }
    classes: ClassVar[dict[str, FindingClass]] = {
        CODE_BASELINE_GREW: FindingClass.certain,
        CODE_ADOPTION_RECORD_GREW: FindingClass.certain,
        CODE_ADOPTION_SOURCE_REBOUND: FindingClass.certain,
        CODE_ADOPTION_BASE_UNREADABLE: FindingClass.certain,
        CODE_ADOPTION_DEBT_ALREADY_OWNED: FindingClass.certain,
        CODE_ADOPTION_DEBT_NOT_MANAGED: FindingClass.certain,
        CODE_ADOPTION_PIN_NOT_ON_REF: FindingClass.certain,
        CODE_ADOPTION_RECORD_REMOVED: FindingClass.certain,
        CODE_ADOPTION_DEBT_NOT_HISTORICAL: FindingClass.certain,
        CODE_ADOPTION_EXCEPTION_REVIVED: FindingClass.certain,
        CODE_ADOPTION_DEBT_TOUCHED: FindingClass.certain,
        CODE_IMPLEMENTED_RFC_CHANGED: FindingClass.certain,
        CODE_IMPLEMENTED_RFC_REMOVED: FindingClass.certain,
        CODE_ACCEPTED_DECISION_REMOVED: FindingClass.certain,
        CODE_DECISION_REWRITTEN: FindingClass.hint,
        CODE_OWNER_CHANGED: FindingClass.hint,
        CODE_CHECK_DISABLED: FindingClass.certain,
        CODE_LAYER_RULE_DISABLED: FindingClass.certain,
        CODE_SOURCE_EXCLUDED: FindingClass.hint,
        CODE_EXTRA_DOC_REMOVED: FindingClass.hint,
        CODE_BASE_CONFIG_UNREADABLE: FindingClass.hint,
        CODE_GATE_WEAKENED: FindingClass.certain,
        CODE_ANCHOR_REMOVED: FindingClass.certain,
        CODE_CLAIM_REMOVED: FindingClass.certain,
        CODE_GOVERNING_CLAIM_CHANGED: FindingClass.certain,
        CODE_GOVERNING_CLAIM_REMOVED: FindingClass.certain,
        CODE_CLAIM_REWORDED: FindingClass.hint,
        CODE_INVENTORY_REMOVED: FindingClass.certain,
        CODE_INVENTORY_WEAKENED: FindingClass.certain,
        CODE_SETTING_WEAKENED: FindingClass.certain,
        CODE_UNREVIEWED_SETTING_CHANGE: FindingClass.hint,
        CODE_RULES_NARROWED: FindingClass.hint,
        CODE_FILTER_UNREADABLE: FindingClass.certain,
        CODE_FILTER_NOT_COMPARED: FindingClass.hint,
    }

    def run(self, graph: DocGraph) -> list[Finding]:
        raise NotImplementedError(
            "diff-integrity needs the diff range; call run_diff_integrity(graph, ...)"
        )


def run_diff_integrity(
    graph: DocGraph,
    changed: frozenset[str],
    base_ref: str,
    head_ref: str,
    source_changed: frozenset[str] = frozenset(),
) -> list[Finding]:
    """Findings for the gates a diff from `base_ref` to `head_ref` weakened.

    Which folders hold sealed records, and where the baseline lives, are read from the
    config at the merge base, so a change cannot move them out of its own way.

    `source_changed` is what a sibling source repository changed, in display spellings, and
    it reaches exactly one rule: touch-to-own over recorded debt. Everything else here
    judges this repository's own diff, and widening those would answer a question nobody
    asked — `co-change` across a repository boundary is its own open design, not a side
    effect of this parameter.
    """
    if graph.config is None or graph.repo_root is None:
        return []
    config = graph.config
    repo_root = graph.repo_root
    try:
        base = merge_base(repo_root, base_ref, head_ref) or base_ref
    except GitChangesError:
        return []
    if head_ref == "HEAD":
        # Contents are read from the working tree, so its uncommitted changes count too.
        with suppress(GitChangesError):
            changed = changed | frozenset(working_tree_changed_paths(repo_root))

    # Memoized for this run only, never across runs: `--delta` runs the whole pass
    # twice against different trees, and "HEAD" means the working tree, which an
    # editor changes between invocations. Each doc is read about three times here —
    # the main loop, the sealed-layer sweep, and the rename check — so the misses
    # are what the subprocesses cost.
    seen: dict[tuple[str, str], str | None] = {}

    def _read(ref: str, path: str) -> str | None:
        key = (ref, path)
        if key not in seen:
            try:
                seen[key] = file_at_ref(repo_root, ref, path)
            except GitChangesError:
                seen[key] = None
        return seen[key]

    def before(path: str) -> str | None:
        return _read(base, path)

    def after(path: str) -> str | None:
        if head_ref == "HEAD":
            try:
                return (repo_root / path).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                return None
        return _read(head_ref, path)

    def listed(ref: str, directory: str) -> list[str]:
        if ref == "HEAD":
            root = repo_root / directory
            return [p.relative_to(repo_root).as_posix() for p in root.rglob("*.md")]
        try:
            return files_at_ref(repo_root, ref, directory)
        except GitChangesError:
            return []

    def workflows_at(ref: str) -> list[str]:
        if ref == "HEAD":
            root = repo_root / _WORKFLOW_DIR
            found = [p.relative_to(repo_root).as_posix() for p in root.glob("*") if p.is_file()]
        else:
            try:
                found = files_at_ref(repo_root, ref, _WORKFLOW_DIR)
            except GitChangesError:
                found = []
        return sorted(path for path in found if _is_workflow(path))

    from irminsul.checks.globs import walk_configured_source_files

    def judged_files() -> list[str]:
        """What the gate reads, which is what a change to it should run the gate for."""
        files = {node.path.as_posix() for node in graph.nodes.values()}
        files.update(display for display, _ in guidance_files(repo_root, config))
        files.update(d for _, d in walk_configured_source_files(repo_root, config).files)
        files.update(
            {
                CONFIG_FILENAME,
                _repo_path(config.paths.baseline),
                _repo_path(config.paths.adoption),
            }
        )
        files.update(workflows_at(head_ref))
        return sorted(path for path in files if (repo_root / path).is_file())

    out: list[Finding] = []
    declared = _declared_now(graph)
    base_text = before(CONFIG_FILENAME)
    base_config = _parsed(base_text)
    if base_text is not None and base_config is None:
        out.append(
            _finding(
                CODE_BASE_CONFIG_UNREADABLE,
                Severity.warning,
                CONFIG_FILENAME,
                f"the {CONFIG_FILENAME} at {base_ref} does not load, so config changes and "
                "sealed folders are judged by this change's own config",
                "review the config changes by hand",
            )
        )
    sealing = base_config or config

    # A run with no config reads the baseline at the default path, so with no config at
    # the base that is the file the ratchet is measured against. The path this change's
    # own config names could be one that never existed.
    ratchet = sealing if base_text is not None else IrminsulConfig()
    base_baseline = _repo_path(ratchet.paths.baseline)
    head_baseline = _repo_path(config.paths.baseline)
    if base_baseline in changed or head_baseline in changed or base_baseline != head_baseline:
        added = _entries(after(head_baseline)) - _entries(before(base_baseline))
        if added and not _adopting(repo_root, base, base_baseline):
            out.append(
                _finding(
                    CODE_BASELINE_GREW,
                    Severity.error,
                    head_baseline,
                    f"baseline gained {len(added)} entr{'y' if len(added) == 1 else 'ies'} "
                    f"since {base_ref}",
                    "fix the new findings instead of recording them",
                )
            )

    base_adoption = _repo_path(ratchet.paths.adoption)
    head_adoption = _repo_path(config.paths.adoption)
    walked = walk_configured_source_files(repo_root, config).files
    walked_displays = [display for _, display in walked]
    # The record covers tests too, and `test_roots` are not source roots, so the ordinary
    # walk does not reach a declared test tree at all. The record is built from both walks
    # (`adoption.py`); the seal has to ask about the same set or a recorded test would keep
    # an exception the record no longer justifies.
    managed = list(walked)
    if config.paths.test_roots:
        from irminsul.checks.owned_tests import TestOwnershipCheck

        already = {display for _, display in walked}
        managed += [
            (source, display)
            for source, display in walk_configured_source_files(
                repo_root, TestOwnershipCheck._scoped(config)
            ).files
            if display not in already
        ]
    # Which of those this repository's own history can answer for. In the siblings layout a
    # display is relative to a source root in another repository, and asking this tree
    # whether it held that path at some ref is a question with no answer.
    in_this_repo = frozenset(
        display for source, display in managed if _relative_to(Path(source), repo_root) == display
    )
    added_records = " ".join(
        reasoning
        for path in sorted(changed)
        if path.endswith(".md")
        and not path.endswith("/INDEX.md")
        and in_layer(config, path, "decisions")
        and before(path) is None
        and (text := after(path)) is not None
        and (reasoning := _accepted_decision_text(text))
    )

    renames = renamed_paths(repo_root, base, head_ref)
    # `diff_name_only` passes `--find-renames`, so a renamed doc appears under its new
    # path only. Reading the base side at the new path finds nothing, which used to skip
    # the doc entirely — making a rename the cheapest way to drop everything it declared.
    renamed_from = {new_path: old_path for old_path, new_path in renames.items()}
    # Answering the seal's questions costs a `git show` per document at the base, and a
    # repository that never adopted has no record for any of them to be about. So the
    # texts are read first and the rest is skipped when neither side holds a record.
    base_record, head_record = before(base_adoption), after(head_adoption)
    if base_record is not None or head_record is not None:
        # Both docs roots, because a change may move the tree and the base's docs sit
        # under whichever one the base's own config named.
        base_docs = sorted(
            {
                path
                for folder in {docs_root_prefix(sealing), docs_root_prefix(config)}
                for path in listed(base, folder)
                if path.endswith(".md")
            }
        )
        out.extend(
            _adoption_seal(
                repo_root,
                changed | source_changed,
                base_record,
                head_record,
                head_adoption,
                base_ref,
                adopting=exists_at_ref(repo_root, base, base_adoption) is False,
                owned=_owned_now(graph),
                owned_at_base=_owned_at_ref(graph, walked_displays, base_docs, before, sealing),
                # A recorded path the tree no longer holds excepts nothing, and its owner
                # at the base went away with the file rather than with this change's docs.
                present=frozenset(display for _, display in managed),
                at_base=tracked_paths_at_ref(repo_root, base),
                in_this_repo=in_this_repo,
                configured_roots=frozenset((*config.paths.source_roots, *config.paths.test_roots)),
                renamed_from=renamed_from,
                excused=f"`{head_adoption}`" in added_records,
                # Two snapshots, two resolutions. The base's bindings come from the base's
                # config and the base's record, so a change cannot alter what the base *meant*
                # by editing either. The checkout is the one input they share, because there is
                # one working tree and a sibling repository is cloned into it once.
                base_map=_source_map_at(repo_root, sealing, base_record),
                head_map=graph.source_map,
                # Whether `sealing` really is the base's configuration or the fallback to this
                # change's own. A base that never had one is the adopting story and is decided
                # by `adopting`; a base that had one that will not load is the case where the
                # seal would otherwise judge the base by rules the base never had.
                base_rules_known=base_text is None or base_config is not None,
                # Anchoring is an adopting-time obligation, so it is computed only for the
                # change that writes the record. Afterwards the pin cannot move and entries
                # cannot be added, so the fact established here is preserved by the seal
                # rather than re-proved — which also means no later run needs the ref fetched.
                unanchored=(
                    _unanchored_pins(graph.source_map, head_record)
                    if exists_at_ref(repo_root, base, base_adoption) is False
                    else ()
                ),
                # Which of the changed paths the other repository deleted. Separated from the
                # merged set because the remedy for touching recorded debt is a change to the
                # record, and only this repository's own pull requests can make one.
                source_deleted=_source_paths_gone(graph.source_map, source_changed),
                base_bindings=_adoption_bindings(base_record),
            )
        )

    source_displays = walked_displays

    for path in sorted(changed):
        if not path.endswith(".md"):
            continue
        was_renamed = path in renamed_from
        old = before(renamed_from.get(path, path))
        new = after(path)
        if old is None:
            continue
        # A renamed doc must change its `id:` to match the new filename, so a pure
        # rename is compared without that line — the same tolerance the sealed-record
        # sweep already applies.
        same = _without_id if was_renamed else _normalized
        if new is not None and same(old) == same(new):
            continue
        # A deleted doc is the cheapest way to drop every anchor, claim and inventory
        # entry it held, so it is judged as a removal of all of them rather than
        # skipped. `declared` is tree-wide, so a doc that was split or moved rather
        # than deleted still finds its governance alive somewhere and reports nothing.
        surviving = new if new is not None else ""
        out.extend(
            _removed_governance(
                repo_root,
                config,
                path,
                old,
                surviving,
                declared,
                added_records,
                base_ref,
                source_displays,
            )
        )
        out.extend(_rewritten_governing_claims(path, old, surviving, added_records, base_ref))
        if new is None or was_renamed:
            # A renamed sealed record is the `sealed_layers` sweep's business: it finds
            # the record at its new path through the same rename map and says where it
            # moved from. Reporting here too would say the same thing twice.
            continue
        meta = _frontmatter(old)
        if in_layer(sealing, path, "rfcs") and _implemented(meta):
            out.append(
                _finding(
                    CODE_IMPLEMENTED_RFC_CHANGED,
                    Severity.error,
                    path,
                    f"RFC was implemented at {base_ref} and has changed since",
                    "restore the record and propose the change in a new RFC",
                )
            )
        elif (
            in_layer(sealing, path, "decisions")
            and meta.get("status") == "stable"
            and _decision(old) is not None
            and _decision(old) != _decision(new)
        ):
            out.append(
                _finding(
                    CODE_DECISION_REWRITTEN,
                    Severity.warning,
                    path,
                    f"accepted decision section rewritten since {base_ref}",
                    "record the changed decision in a new ADR that supersedes this one",
                )
            )

    sealed_layers: tuple[tuple[LayerName, str, Callable[[dict[str, object]], bool], str], ...] = (
        ("rfcs", CODE_IMPLEMENTED_RFC_REMOVED, _implemented, "implemented RFC"),
        ("decisions", CODE_ACCEPTED_DECISION_REMOVED, _accepted, "accepted decision record"),
    )
    for layer, code, sealed, noun in sealed_layers:
        directory = layer_prefix(sealing, layer)
        head_paths = {
            path
            for folder in sorted({directory, layer_prefix(config, layer)})
            for path in listed(head_ref, folder)
            if not path.endswith("/INDEX.md")
        }
        head_texts: set[str] | None = None
        for path in sorted(listed(base, directory)):
            if not path.endswith(".md") or path.endswith("/INDEX.md") or path in head_paths:
                continue
            old = before(path)
            if old is None or not sealed(_frontmatter(old)):
                continue
            moved = renames.get(path)
            if moved is not None and moved in head_paths:
                out.extend(_renamed_record(layer, path, moved, old, after(moved), base_ref))
                continue
            if head_texts is None:
                head_texts = {
                    _without_id(text)
                    for text in (after(candidate) for candidate in sorted(head_paths))
                    if text is not None
                }
            if _without_id(old) in head_texts:
                continue
            out.append(
                _finding(
                    code,
                    Severity.error,
                    path,
                    f"{noun} at {base_ref} no longer exists",
                    "restore the record; retire it by superseding it with a new one",
                )
            )
    out.extend(_owner_changes(graph, changed, base, base_ref, _read))
    head_text = after(CONFIG_FILENAME)
    head_config = _parsed(head_text) if head_text is not None else IrminsulConfig()
    if CONFIG_FILENAME in changed and base_config is not None and head_config is not None:
        out.extend(_config_weakening(base_config, head_config, added_records, base_ref))
    out.extend(
        _weakened_workflows(
            changed,
            (workflows_at(base), before),
            (workflows_at(head_ref), after),
            added_records,
            base_ref,
            judged_files,
        )
    )
    return out


def _declared_now(graph: DocGraph) -> tuple[set[tuple[str, str | None]], set[object], set[object]]:
    """Every anchor, claim, and inventory entry the head tree declares, in any doc.

    Gathered tree-wide rather than per-doc so splitting a doc, which moves declarations
    from one file to another, is not read as deleting them — but each is identified by
    its *content*, not by its name. `Claim.id` is unique only within one document, so
    matching on the bare id let an unrelated doc reusing a name mask a real removal.
    """
    from irminsul.anchors import parse_anchors

    anchors: set[tuple[str, str | None]] = set()
    claims: set[object] = set()
    kinds: set[object] = set()
    for node in graph.nodes.values():
        anchors.update((a.path, a.symbol) for a in parse_anchors(node.body))
        for claim in getattr(node.frontmatter, "claims", None) or []:
            claims.add((getattr(claim, "id", None), getattr(claim, "claim", None)))
        for entry in getattr(node.frontmatter, "inventory", None) or []:
            kinds.add((getattr(entry, "kind", None), getattr(entry, "source", None)))
    return anchors, claims, kinds


def _removed_governance(
    repo_root: Path,
    config: IrminsulConfig,
    path: str,
    old: str,
    new: str,
    declared: tuple[set[tuple[str, str | None]], set[object], set[object]],
    excused: str,
    base_ref: str,
    source_displays: list[str],
) -> list[Finding]:
    """What a doc stopped asking about code that is still there.

    A doc governs code by declaring things about it: an anchor pins a symbol, a `claims:`
    entry cites evidence, an `inventory:` entry watches a surface. Every check verifies
    that such a declaration is true, and none noticed it being deleted — so the cheapest
    way to clear a finding was to delete the declaration that raised it. Removing one is
    only reported when what it named is still present: when the code went away too, the
    doc is right to stop describing it.
    """
    from irminsul.anchors import parse_anchors, resolve

    out: list[Finding] = []
    live_anchors, live_claims, live_kinds = declared
    surviving = live_anchors | {(a.path, a.symbol) for a in parse_anchors(_body(new))}
    for anchor in parse_anchors(_body(old)):
        if (anchor.path, anchor.symbol) in surviving:
            continue
        if resolve(repo_root, anchor).status != "ok":
            continue
        named = f"{anchor.path}#{anchor.symbol}" if anchor.symbol else anchor.path
        out.append(
            _finding(
                CODE_ANCHOR_REMOVED,
                Severity.error,
                path,
                f"anchor on '{named}' was removed while that code is still there",
                "restore the anchor; remove one only when the code it names is gone",
            )
        )

    old_meta, new_meta = _frontmatter(old), _frontmatter(new)
    kept_claims = live_claims | {
        (claim.get("id"), claim.get("claim")) for claim in _entries_of(new_meta, "claims")
    }
    # Content identity is what makes a doc *split* readable as a move rather than a
    # deletion, but within one doc a surviving id means the sentence was reworded, not
    # removed. A rewording is still reported — as a hint, since no rule separates a
    # correction from a claim quietly emptied of meaning, and reading "The widget runs
    # on demand" as a deletion left ordinary maintenance with no green route.
    surviving_by_id = {claim.get("id"): claim for claim in _entries_of(new_meta, "claims")}
    for claim in _entries_of(old_meta, "claims"):
        claim_id = claim.get("id")
        evidence = [str(item) for item in _listed(claim.get("evidence"))]
        if (kept := surviving_by_id.get(claim_id)) is not None:
            if (
                kept.get("claim") != claim.get("claim")
                and claim.get("relation") != _FOLLOWS
                and f"`{claim_id}`" not in excused
            ):
                out.append(
                    _finding(
                        CODE_CLAIM_REWORDED,
                        Severity.warning,
                        path,
                        f"claim '{claim_id}' was reworded since {base_ref}",
                        "re-read the new wording against the evidence the claim cites, "
                        "and the prose it governs",
                    )
                )
            continue
        if (claim_id, claim.get("claim")) in kept_claims or not evidence:
            continue
        if f"`{claim_id}`" in excused:
            continue
        if claim.get("relation") == _GOVERNS:
            # Read from the base, so downgrading the relation earlier in the same change
            # does not release it, and never excused by deleting the evidence: removing
            # the code a contract governs is the change the contract exists to stop.
            out.append(
                _finding(
                    CODE_GOVERNING_CLAIM_REMOVED,
                    Severity.error,
                    path,
                    f"governing claim '{claim_id}' was removed since {base_ref}",
                    f"restore it, or add a decision record naming `{claim_id}`",
                )
            )
            continue
        if claim.get("relation") == _FOLLOWS:
            # A report answers to its evidence, and a report cheap enough to derive
            # should not have been persisted: dropping one is hygiene, not loss.
            continue
        if not all(_evidence_exists(repo_root, config, item) for item in evidence):
            continue
        out.append(
            _finding(
                CODE_CLAIM_REMOVED,
                Severity.error,
                path,
                f"claim '{claim_id}' was removed while all of its evidence still exists",
                "restore the claim, or remove the evidence it cited in the same change",
            )
        )

    kept_kinds = live_kinds | {
        (entry.get("kind"), entry.get("source")) for entry in _entries_of(new_meta, "inventory")
    }
    surviving_entries = {
        (entry.get("kind"), entry.get("source")): entry
        for entry in _entries_of(new_meta, "inventory")
    }
    for entry in _entries_of(old_meta, "inventory"):
        kind, source = entry.get("kind"), entry.get("source")
        still_here = surviving_entries.get((kind, source))
        if still_here is not None:
            weakening = _inventory_weakening(entry, still_here)
            if weakening is not None and f"`{path}`" not in excused:
                out.append(
                    _finding(
                        CODE_INVENTORY_WEAKENED,
                        Severity.error,
                        path,
                        f"inventory entry '{kind}' {weakening} since {base_ref}",
                        "restore the contract, or add a decision record naming this doc",
                    )
                )
            continue
        if (kind, source) in kept_kinds or not isinstance(source, str):
            continue
        if not _glob_matches_anything(source_displays, source):
            continue
        out.append(
            _finding(
                CODE_INVENTORY_REMOVED,
                Severity.error,
                path,
                f"inventory entry '{kind}' was removed while '{source}' still exists",
                "restore the entry; narrow it with `omit` rather than deleting it",
            )
        )
    return out


def _inventory_weakening(before: dict[str, object], after: dict[str, object]) -> str | None:
    """How a surviving `inventory:` entry asks less of the code than it used to.

    The removal seal keys on `(kind, source)`, so every field that makes the entry a
    contract — `explained_in`, `complete`, `omit` — could be dropped while the entry
    itself stayed, silencing live identities without tripping anything.
    """
    was, now = before.get("explained_in"), after.get("explained_in")
    if was and not now:
        return "stopped requiring its items to be explained in prose"
    if was == "self" and now == "any":
        return "stopped requiring its own prose to explain its items"
    if before.get("complete") and not after.get("complete"):
        return "stopped requiring the list to be complete"
    added = {str(item) for item in _listed(after.get("omit"))} - {
        str(item) for item in _listed(before.get("omit"))
    }
    if added:
        return f"added {len(added)} entr{'y' if len(added) == 1 else 'ies'} to `omit`"
    return None


def _evidence_exists(repo_root: Path, config: IrminsulConfig, display: str) -> bool:
    """Whether a `claims[].evidence` spelling still names a file.

    Through `resolve_display_path`, not `repo_root / display`: for a file the walk
    returns from a root outside the repository — the code repo of the `siblings`
    layout — the spelling is source-root-relative, so joining it to the docs repo
    finds nothing and every removal there went unreported.
    """
    from irminsul.checks.globs import resolve_display_path

    resolved = resolve_display_path(repo_root, config.paths.source_roots, display)
    return resolved is not None and resolved.exists()


def _glob_matches_anything(displays: list[str], pattern: str) -> bool:
    """Whether an `inventory.source` glob from the base ref still matches a walked file.

    Matched against the walk's display paths the way `inventory-drift` matches them, not
    joined to the repository root: outside the docs repo — the code repo of the
    `siblings` layout — a display is source-root-relative, so a join finds nothing and
    the removal goes unreported.

    The pattern is raw YAML read through `git show`, so it never passed the schema, and
    the schema would admit an empty or absolute one anyway. `GitIgnoreSpec` takes any
    string without raising, where `Path.glob` raises on "", on an absolute path, and
    (with `IndexError`) on ".".
    """
    spec = pattern.replace("\\", "/").strip()
    if not spec:
        return False
    try:
        matcher = GitIgnoreSpec.from_lines([spec])
    except Exception:
        return False
    return any(matcher.match_file(display) for display in displays)


_WORKFLOW_DIR: Final = ".github/workflows/"

#: A step's `name:` is prose about the step, not the command it runs, so renaming one
#: to mention the tool must not read as gaining or losing an invocation.
_YAML_NAME_LINE_RE: Final = re.compile(r"(?m)^\s*(?:-\s*)?name:.*$")

#: A `#` at line start or after whitespace opens a YAML comment. A commented-out step
#: still contains every token, so counting raw text let an agent switch the gate off by
#: prefixing one character.
_YAML_COMMENT_RE: Final = re.compile(r"(?m)(?:^|(?<=\s))#.*$")

_FAIL_ON_RE: Final = re.compile(r"--fail-on[= ]\s*([a-z,]+)")
_PROFILE_RE: Final = re.compile(r"--profile[= ]\s*([a-z-]+)")
# The composite Action this project publishes, pinned to any ref: `owner/irminsul@v1`.
_ACTION_USES_RE: Final = re.compile(r"^[\w.-]+/irminsul@\S+$", re.IGNORECASE)
_FINDING_CLASSES: Final = frozenset({"certain", "hint", "time"})
_GATE_FLAGS: Final = frozenset({"--strict", "--fail-on", "--diff", "--profile"})
_LOCAL_ACTION_FILES: Final = ("action.yml", "action.yaml")
#: The tails that discard a command's exit status.
_NEUTRALISED_TAIL_RE: Final = re.compile(r"\|\|\s*(?:true|:)\s*(?:#.*)?$")


def _line_continuations(text: str) -> str:
    r"""Join shell line continuations so one command is one line.

    Strength is scored per line, and a `run: |` block that wraps its flags across
    continuation lines put `--strict` and `--diff` on lines that do not contain
    `irminsul check` — so wrapping a long invocation for readability, changing nothing
    else, read as dropping every flag and failed CI with two certain findings.
    """
    return re.sub(r"\\\n\s*", " ", text)


def _live_workflow_text(text: str) -> str:
    """The part of a workflow that actually runs: no step names, no comments."""
    return _line_continuations(_YAML_COMMENT_RE.sub("", _YAML_NAME_LINE_RE.sub("", text)))


#: Invocations, the finding classes that fail, how strictly the diff range is gated,
#: and how many checks run.
_Strength = tuple[int, int, int, int]
_NO_STRENGTH: Final[_Strength] = (0, 0, 0, 0)


def _breadth(profile: object) -> int:
    """`all-available` runs every implemented check; any other profile, or none, runs the
    enabled ones. Narrowing `checks.enabled` is reported on its own, so without this a
    narrower profile is the route to the same result that nothing watches."""
    return 2 if str(profile or "").strip() == "all-available" else 1


def _local_action_flags(uses: str, read: Callable[[str], str | None]) -> frozenset[str] | None:
    """The gate flags a local action passes on, or None when the step is not a gate.

    `uses: ./` and `uses: ./.github/actions/<name>` name an action in the repository, so
    its definition can be read at the same ref as the workflow. It is a gate when it
    runs `irminsul check`. An input counts only while the definition still names the
    flag it becomes: the workflow can stay as it was while the action it calls stops
    turning `diff` into `--diff`.
    """
    if not uses.startswith("./"):
        return None
    folder = posixpath.normpath(uses)
    for name in _LOCAL_ACTION_FILES:
        text = read(name if folder == "." else f"{folder}/{name}")
        if text is None:
            continue
        live = _live_workflow_text(text)
        if "irminsul check" not in live:
            return None
        return frozenset(flag for flag in _GATE_FLAGS if flag in live)
    return None


def _parsed_workflow(text: str) -> object | None:
    """The workflow as YAML, or `None` when it does not parse.

    Shared so that one document is loaded once per scoring pass. `None` covers both an
    unparseable file and one that parses to nothing; every caller treats the two the same.
    """
    try:
        loaded: object = YAML(typ="safe").load(text)
    except Exception:
        return None
    return loaded


def _action_gate_strength(
    text: str,
    read: Callable[[str], str | None] | None = None,
    data: object | None = None,
) -> _Strength:
    """The same four totals for steps that run the composite Action.

    A workflow `irminsul init` scaffolds gates through `uses: <owner>/irminsul@<ref>` and
    `with:` inputs, which never contain the words `irminsul check`, so reading only command
    lines scored every adopter's gate as absent. The inputs mean what the Action turns them
    into: `strict: true` is `--strict`, `fail-on` is `--fail-on`, any `diff` is `--diff`,
    and `profile` is `--profile`.
    The workflow is read as YAML rather than as lines, so a commented-out step is gone and
    an input belongs to the step it sits under. The published Action is taken to pass
    every input on, since its definition is not in the repository to read; a local one is
    read through `read`, and is not scored without it.
    """
    if data is None:
        data = _parsed_workflow(text)
    if data is None:
        return _NO_STRENGTH
    jobs = data.get("jobs") if isinstance(data, dict) else None
    invocations = strictness = diff_rank = breadth = 0
    for job in jobs.values() if isinstance(jobs, dict) else ():
        steps = job.get("steps") if isinstance(job, dict) else None
        for step in steps if isinstance(steps, list) else ():
            uses = step.get("uses") if isinstance(step, dict) else None
            if not isinstance(uses, str):
                continue
            if _switched_off(job) or _switched_off(step):
                # The scaffolded workflows gate through `uses:`, so leaving this out gave
                # adopters none of the protection a `run:` gate gets.
                continue
            passed: frozenset[str] | None = _GATE_FLAGS
            if not _ACTION_USES_RE.match(uses.strip()):
                passed = _local_action_flags(uses.strip(), read) if read else None
            if passed is None:
                continue
            inputs = step.get("with")
            inputs = inputs if isinstance(inputs, dict) else {}
            invocations += 1
            fail_on = {c.strip() for c in str(inputs.get("fail-on") or "").split(",")}
            if str(inputs.get("strict", "")).strip().lower() == "true" and "--strict" in passed:
                strictness += 3
            elif "--fail-on" in passed:
                strictness += len({"certain"} | (fail_on & _FINDING_CLASSES))
            else:
                strictness += 1
            if str(inputs.get("diff") or "").strip() and "--diff" in passed:
                diff_rank += 2
            breadth += _breadth(inputs.get("profile")) if "--profile" in passed else 1
    return invocations, strictness, diff_rank, breadth


def _gate_strength(text: str, read: Callable[[str], str | None] | None = None) -> _Strength:
    """How hard the `irminsul check` invocations in a workflow gate, as four totals.

    Counting flag *tokens* treated interchangeable spellings as equal, which they are
    not: `--strict` fails on certain, hint and time, while `--fail-on time` lets hints
    pass, and `--diff` exits 2 on a range it cannot resolve where `--base-ref` only
    warns and skips the diff-aware passes. Both swaps are weakenings that a token count
    reads as a migration, so strength is measured rather than presence.
    """
    # One parse for both halves: reading run steps as YAML, which is what lets a step
    # switched off with `continue-on-error` or `if: false` stop counting, otherwise
    # loaded the same document a second time for every workflow on every side.
    data = _parsed_workflow(text)
    commands = _live_run_commands(text, data)
    if commands is None:
        commands = [_live_workflow_text(text)]
    invocations = strictness = diff_rank = breadth = 0
    for command in commands:
        # Two things the raw script still needs. A `run: |` block may wrap its flags over
        # continuation lines, which puts `--strict` on a line with no `irminsul check` on
        # it. And `#` inside a block scalar is a shell comment that YAML hands over
        # untouched, so a gate commented out there would otherwise score at full strength
        # — the one-character bypass the comment rule exists to stop.
        for line in _line_continuations(_YAML_COMMENT_RE.sub("", command)).splitlines():
            if "irminsul check" not in line:
                continue
            invocations += 1
            if "--strict" in line:
                strictness += 3
            elif match := _FAIL_ON_RE.search(line):
                strictness += len({"certain", *(c for c in match.group(1).split(",") if c)})
            else:
                strictness += 1
            if "--diff" in line:
                diff_rank += 2
            elif "--base-ref" in line or "--head-ref" in line:
                diff_rank += 1
            profile = _PROFILE_RE.search(line)
            breadth += _breadth(profile.group(1) if profile else None)
    action = _action_gate_strength(text, read, data)
    return (
        invocations + action[0],
        strictness + action[1],
        diff_rank + action[2],
        breadth + action[3],
    )


def _switched_off(node: object) -> bool:
    """Whether this job or step is turned off in a way anyone can read off the file.

    Two ways a gate stops gating while every flag stays where it was:
    `continue-on-error: true`, which runs the step and ignores its exit code, and an `if:`
    that cannot be true. Only a *statically* false condition counts. `if: github.event_name
    == 'pull_request'` is an ordinary conditional gate and evaluating it would need the
    event, so anything that is not literally false is treated as running — the alternative
    is reporting every matrix workflow in the world as a weakening.
    """
    if not isinstance(node, dict):
        return False
    if str(node.get("continue-on-error", "")).strip().lower() == "true":
        return True
    condition = node.get("if")
    if condition is None:
        return False
    text = str(condition).strip()
    if text.startswith("${{") and text.endswith("}}"):
        text = text[3:-2].strip()
    return text.lower() in {"false", "!true", "0"}


def _neutralised(command: str) -> bool:
    """Whether the shell throws the gate's exit code away.

    `irminsul check || true` runs the whole check and then reports success, which reads as
    a full-strength gate to anything counting flags. Deliberately shallow: the three
    spellings below, on the command itself or over the block it sits in. A general reading
    of shell control flow is not something a regex can do, and guessing would report
    working scripts.
    """
    joined = _line_continuations(command)
    if any(
        "irminsul check" in line and _NEUTRALISED_TAIL_RE.search(line)
        for line in joined.splitlines()
    ):
        return True
    # `set +e` alone neutralises nothing: the step still exits with the last command's
    # status, so a script that turns errexit off and then runs the gate last still fails.
    # A trailing `exit 0` alone neutralises nothing either: GitHub runs `bash -eo
    # pipefail`, so a failing gate aborts before reaching it. Only the pair does — which
    # is why it is a conjunction and not two separate guesses.
    lines = [line.strip() for line in joined.splitlines() if line.strip()]
    return "set +e" in lines and bool(lines) and lines[-1] == "exit 0"


def _live_run_commands(text: str, data: object | None = None) -> list[str] | None:
    """Every `run:` script a workflow actually runs, or `None` when it cannot be read.

    `None` means the file did not parse as YAML, or parsed into a shape with no run steps
    while still naming the command — the caller then falls back to scanning the raw text,
    which is what this did before it could see steps at all. Scoring the raw text is the
    conservative direction: it counts a gate that may be switched off, never misses one.
    """
    if data is None:
        data = _parsed_workflow(text)
    if data is None:
        return None
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, dict):
        return None
    commands: list[str] = []
    saw_step = False
    for job in jobs.values():
        steps = job.get("steps") if isinstance(job, dict) else None
        for step in steps if isinstance(steps, list) else ():
            if not isinstance(step, dict):
                continue
            script = step.get("run")
            if not isinstance(script, str):
                continue
            saw_step = True
            if _switched_off(job) or _switched_off(step) or _neutralised(script):
                continue
            commands.append(script)
    if not saw_step and "irminsul check" in text:
        return None
    return commands


def _adoption_paths(text: str | None) -> set[str]:
    """The excepted paths in an adoption record, or none when it will not parse."""
    if text is None:
        return set()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return set()
    unowned = payload.get("unowned") if isinstance(payload, dict) else None
    if not isinstance(unowned, list):
        return set()
    # Both spellings: a plain path for a file in this repository, an object stating its source
    # for one from elsewhere. Read tolerantly, like everything else in this pair of readers —
    # the base is a record this change did not write, and one that will not parse has to yield
    # nothing to compare rather than take the pass down.
    out: set[str] = set()
    for item in unowned:
        if isinstance(item, str):
            out.add(item)
        elif isinstance(item, dict) and isinstance(item.get("path"), str):
            out.add(str(item["path"]))
    return out


def _adoption_bindings(text: str | None) -> dict[str, str]:
    """Each entry's stated source in an adoption record, for the entries that state one."""
    if text is None:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    unowned = payload.get("unowned") if isinstance(payload, dict) else None
    if not isinstance(unowned, list):
        return {}
    out: dict[str, str] = {}
    for item in unowned:
        if isinstance(item, dict):
            display, source = item.get("path"), item.get("source")
            if isinstance(display, str) and isinstance(source, str) and display and source:
                out[display] = source
    return out


def _adoption_pins(text: str | None) -> dict[str, str]:
    """Each declared source's pinned revision in an adoption record, by source name.

    Read off the raw JSON for the same reason `_adoption_paths` is: this is a comparison
    between two texts, one of which is a blob at the merge base, and a record that will not
    parse yields nothing to compare rather than taking the pass down.
    """
    if text is None:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    raw = payload.get("sources") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        return {}
    out: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        name, revision = item.get("name"), item.get("revision")
        if isinstance(name, str) and isinstance(revision, str):
            out[name] = revision
    return out


def _source_map_at(repo_root: Path, config: IrminsulConfig, text: str | None) -> SourceMap:
    """Resolution for one snapshot, from a record that is a blob rather than a file.

    Parsed with the two tolerant readers above rather than `load_record`, for the reason they
    exist: the base is a record this change did not write, and one that will not parse has to
    yield nothing to compare instead of taking the pass down. A record whose `unowned` is
    unreadable is reported by the `adoption-record` pass against the head, where it can be
    repaired.
    """
    from irminsul.adoption import AdoptionRecord, AdoptionSource
    from irminsul.source_map import build_source_map

    record = AdoptionRecord(
        unowned=frozenset(_adoption_paths(text)),
        sources=tuple(AdoptionSource(name, rev) for name, rev in _adoption_pins(text).items()),
        bindings=_adoption_bindings(text),
    )
    return build_source_map(repo_root, config, record)


def _binding_label(binding: Binding) -> str:
    if binding.state != source_map.EXTERNAL:
        return "this repository"
    if binding.revision is None:
        return f"`{binding.root}` with no pinned revision"
    return f"`{binding.root}` at {binding.revision[:12]}"


def _rebound_bindings(
    base_map: SourceMap,
    head_map: SourceMap,
    base_paths: set[str],
    head_paths: set[str],
    head_path: str,
    base_ref: str,
) -> list[Finding]:
    """Entries that survive this change but are verified somewhere else than they were.

    The invariant the three rules above each approach from one side: an entry that is in both
    records must resolve to the same `(repository, revision)` pair in both snapshots. Stating
    it directly catches what a pin comparison cannot see, because an entry is not bound to a
    root — it is bound to whichever root the walk resolves its display to. Replace
    `../code/src` with `../newcode/src` and every existing entry is verified against another
    repository with no pin having changed.

    Two states are passed over rather than reported. `absent` means the walk no longer
    produces the display at all, which is a stale entry and not a moved boundary; a record
    naming a file nobody has any more excepts nothing. `ambiguous` has its own certain finding
    from the `adoption-record` pass, and reporting the same collision twice under two names
    sends a reader looking for two problems.
    """
    skip = {source_map.ABSENT, source_map.AMBIGUOUS}
    moved: dict[tuple[str, str], list[str]] = {}
    for display in sorted(base_paths & head_paths):
        was, now = base_map.binding(display), head_map.binding(display)
        if was.state in skip or now.state in skip or was.identity == now.identity:
            continue
        moved.setdefault((_binding_label(was), _binding_label(now)), []).append(display)

    out: list[Finding] = []
    for (was_label, now_label), displays in sorted(moved.items()):
        listed = ", ".join(f"`{item}`" for item in displays[:3])
        more = f" and {len(displays) - 3} more" if len(displays) > 3 else ""
        out.append(
            _finding(
                CODE_ADOPTION_SOURCE_REBOUND,
                Severity.error,
                head_path,
                f"at {base_ref}, {len(displays)} recorded "
                f"entr{'y' if len(displays) == 1 else 'ies'} ({listed}{more}) answered to "
                f"{was_label}; this change would have {'it' if len(displays) == 1 else 'them'} "
                f"verified against {now_label}",
                "restore the configuration and pins the entries were adopted under, or retire "
                "the entries first; an exception cannot follow its boundary somewhere else",
            )
        )
    return out


def _dropped_boundaries(
    base_map: SourceMap, base_paths: set[str], configured_roots: frozenset[str]
) -> list[str]:
    """Base roots this change stops configuring while the record still binds entries to them.

    Without this the quietest way to stop a boundary being checked is to delete the root from
    the config: the pin may stay, so the pin rules say nothing, and the entries drop out of
    the walk, so they read as `absent` rather than as moved.
    """
    out: list[str] = []
    for boundary in base_map.boundaries:
        if boundary.root in configured_roots:
            continue
        if any(base_map.binding(display).root == boundary.root for display in base_paths):
            out.append(boundary.root)
    return sorted(out)


def _source_paths_gone(smap: SourceMap, source_changed: frozenset[str]) -> frozenset[str]:
    """Which of the other repository's changed displays are no longer on disk.

    Asked of the filesystem rather than of the managed walk, because absence from the walk is
    not deletion. `honor_gitignore` is on by default, so a source pull request that adds a
    recorded file to `.gitignore` drops it out of the walk while leaving it in place — and
    reading that as a deletion exempted the change from touch-to-own, let it edit recorded
    debt unchallenged, and handed the exception back the day the ignore rule came off. The
    file being gone is the property; the walk not returning it is a discriminator that is not
    the property.

    A root that is not checked out cannot be looked in, so its files read as gone. The run
    already fails on `adoption-record/source-unverifiable` for that root, so nothing passes on
    the strength of it.
    """
    return frozenset(
        display
        for display in source_changed
        if not any(
            boundary.exists and (boundary.tree / display).exists() for boundary in smap.boundaries
        )
    )


def _unanchored_pins(smap: SourceMap, head_text: str | None) -> tuple[tuple[str, str, str], ...]:
    """Pinned sources whose revision is not contained in the ref they declare.

    Asked of the repository on disk, once, for the change that creates the record. A commit
    on a pushed side branch resolves and reads perfectly well — which is exactly why the
    revision alone was never evidence that the declared history ever had those files.

    Each unresolvable piece is reported as its own reason rather than skipped. A missing ref
    and a pin off the history are both "this pin is not anchored", and treating either as
    "nothing to check" would make the quietest state the safest one.
    """
    from irminsul.git.changes import is_ancestor, resolve_ref

    out: list[tuple[str, str, str]] = []
    for source, revision in sorted(_adoption_pins(head_text).items()):
        ref = smap.refs.get(source)
        if ref is None:
            out.append((source, "any declared ref", "no `[[paths.sources]]` entry declares it"))
            continue
        boundary = smap.boundary_for_source(source)
        if boundary is None or boundary.git_root is None:
            out.append((source, ref, "its repository is not checked out here to ask"))
            continue
        tip = resolve_ref(boundary.git_root, ref)
        if tip is None:
            out.append((source, ref, "that ref is not in this checkout of the repository"))
            continue
        if not is_ancestor(boundary.git_root, revision, tip):
            out.append((source, ref, f"{revision[:12]} is not an ancestor of {tip[:12]}"))
    return tuple(out)


def _adoption_seal(
    repo_root: Path,
    changed: frozenset[str],
    base_text: str | None,
    head_text: str | None,
    head_path: str,
    base_ref: str,
    *,
    adopting: bool,
    owned: frozenset[str],
    owned_at_base: frozenset[str],
    present: frozenset[str],
    at_base: set[str] | None,
    in_this_repo: frozenset[str],
    configured_roots: frozenset[str],
    renamed_from: dict[str, str],
    excused: bool,
    base_map: SourceMap,
    head_map: SourceMap,
    base_rules_known: bool,
    unanchored: tuple[tuple[str, str, str], ...],
    source_deleted: frozenset[str],
    base_bindings: dict[str, str],
) -> list[Finding]:
    """What this change did to the adoption record, and to the files it excepts.

    Two things have to hold for the record to mean anything. It may not grow — an entry
    added by a pull request is a file this change left unowned and then excused, which is
    the debt the record exists to bound rather than to absorb. And an excepted file this
    change *edits* stops being untouched history: somebody is in there, so the exception
    has done its job and the same change documents the file. That is touch-to-own, and it
    reads the diff's own changed set, which is `base...HEAD` from the merge base, so it
    sees work already committed on the branch rather than only what is uncommitted.

    The change that creates the record is the adoption itself and is allowed, the way a
    first baseline is: the base holds no record, so there is no ratchet to widen. What it
    is not allowed to do is decide for itself what counts as history.

    **The obligations that change has to meet are enumerated in one place, and it is not
    here:** `docs/components/adoption-record.md`, under "What the adopting change must
    prove". Six rules, listed rather than discovered, because this path was patched three
    times — each fix a correct answer to the previous review's finding and each leaving a
    different rule missing. A rule added here belongs in that list in the same change; the
    claim `adopting-obligations-are-complete` is what says so.

    The third rule is what the other two cannot see. An entry is retired by the file
    gaining an owner, and `--update-adoption` is what takes the path back out — but
    nothing makes anyone run it, so a stale record goes on naming a file that is already
    documented. Take that owner away and current-record-contents alone would hand the
    exception back, which is an exception returning. So a recorded file that had an owner
    *at the base of the diff* is judged as retired whatever the record still says, and the
    comparison boundary supplies the state the record failed to record.
    """
    base_paths, head_paths = _adoption_paths(base_text), _adoption_paths(head_text)
    out: list[Finding] = []
    if base_paths and not base_rules_known:
        # Reported rather than worked around, and the rest of the seal still runs: the
        # findings it can reach are still worth having, and suppressing them because one
        # input is degraded would trade a loud limitation for a quiet one.
        out.append(
            _finding(
                CODE_ADOPTION_BASE_UNREADABLE,
                Severity.error,
                head_path,
                f"the record holds {len(base_paths)} entr"
                f"{'y' if len(base_paths) == 1 else 'ies'} and the {CONFIG_FILENAME} at "
                f"{base_ref} does not load, so what counted as an owner there cannot be read "
                "and whether an exception retired cannot be decided",
                f"repair the {CONFIG_FILENAME} at {base_ref}, or rebase onto a commit whose "
                "configuration loads; the base's ownership rules are not this change's to "
                "supply",
            )
        )
    if base_text is not None and head_text is None and base_paths and not excused:
        out.append(
            _finding(
                CODE_ADOPTION_RECORD_REMOVED,
                Severity.error,
                head_path,
                f"the adoption record still named {len(base_paths)} file(s) at {base_ref} and "
                "this change deletes it",
                "retire the entries with `check --update-adoption` until the record is empty, "
                f"or add a decision record naming `{head_path}` and why it goes",
            )
        )
        return out

    # Computed before the record-growth rules, and reported before their early returns,
    # because it applies to the adopting change as much as to any other. The change that
    # creates the record was trusted here twice over: it could delete an owning document and
    # register the file it had owned as history in the same commit, and the file did exist at
    # the base, so the historical-presence rule below passes it honestly.
    revived = sorted((head_paths & owned_at_base & present) - set(owned))
    for path in revived:
        out.append(
            _finding(
                CODE_ADOPTION_EXCEPTION_REVIVED,
                Severity.error,
                path,
                f"`{path}` had an owning doc at {base_ref}, so its adoption exception had "
                "retired; this change leaves it unowned and the record still names it",
                "keep an owner for it, or give it one elsewhere in this change; the record "
                "cannot hand back an exception the file already grew out of",
            )
        )

    if added := head_paths - base_paths:
        if adopting:
            # Only paths this repository's own history can answer for, and only ones the
            # walk still returns: an entry naming nothing managed excepts nothing, and a
            # sibling code repo's files are in no revision of this tree.
            for path in sorted(added):
                if at_base is None or path not in in_this_repo or path in at_base:
                    continue
                # A rename is diagnosed and not excused. Following it back used to make a
                # moved file count as history under its new name, which is the exception
                # travelling: adoption tolerates debt nobody has gone back to, and moving a
                # file is going back to it. So the origin only words the message.
                origin = renamed_from.get(path)
                became = (
                    f", which is `{origin}` moved — a move is a touch, and the exception does "
                    "not follow the file to its new path"
                    if origin is not None and origin in at_base
                    else f", which was not in the tree at {base_ref}, so this change wrote the "
                    "file and excused it in one go"
                )
                out.append(
                    _finding(
                        CODE_ADOPTION_DEBT_NOT_HISTORICAL,
                        Severity.error,
                        path,
                        f"the first adoption record names `{path}`{became}",
                        "document the file instead, or adopt in a change that does not also "
                        "move it; the record names what was already unowned, at the path it "
                        "was unowned at",
                    )
                )
            for path in sorted(added & set(owned)):
                out.append(
                    _finding(
                        CODE_ADOPTION_DEBT_ALREADY_OWNED,
                        Severity.error,
                        path,
                        f"the first adoption record names `{path}`, which already has an owning "
                        "doc, so the exception buys nothing now and becomes live the day that "
                        "owner goes",
                        "take the path out of the record; a documented file is not debt",
                    )
                )
            # A path no configured root produces excepts nothing today and starts excepting a
            # file nobody adopted the day a root is widened. Only asked when the walk is
            # complete: a root missing from the checkout makes every path under it look absent,
            # and `adoption-record/source-unverifiable` is the honest finding for that.
            if not head_map.missing_roots:
                for path in sorted(added - present):
                    out.append(
                        _finding(
                            CODE_ADOPTION_DEBT_NOT_MANAGED,
                            Severity.error,
                            head_path,
                            f"the first adoption record names `{path}`, which no configured "
                            "root produces, so it excepts nothing and nothing checks it",
                            "remove the entry, or correct the path; `check --init-adoption` "
                            "writes only paths the walk returns",
                        )
                    )
            for source, ref, reason in unanchored:
                out.append(
                    _finding(
                        CODE_ADOPTION_PIN_NOT_ON_REF,
                        Severity.error,
                        head_path,
                        f"the first adoption record pins source `{source}` at a commit "
                        f"{ref} does not contain ({reason})",
                        f"pin a commit on {ref}; `check --init-adoption` uses the merge base "
                        "of the source checkout and that ref, which is one by construction",
                    )
                )
            # Touch-to-own applies to the adopting change too. Returning here let the one
            # change that both creates the record and edits a file it records call that file
            # untouched history — while the identical edit one commit later is caught. The
            # record describes code nobody has gone back to; this change went back to it.
            out.extend(
                _touched_findings(sorted((added & changed) - set(owned) - set(revived)), present)
            )
            return out
        listed = ", ".join(f"`{item}`" for item in sorted(added)[:3])
        more = f" and {len(added) - 3} more" if len(added) > 3 else ""
        out.append(
            _finding(
                CODE_ADOPTION_RECORD_GREW,
                Severity.error,
                head_path,
                f"the adoption record gained {len(added)} entr"
                f"{'y' if len(added) == 1 else 'ies'} since {base_ref}: {listed}{more}",
                "document the file instead of recording it as pre-existing debt; the "
                "record names what was already unowned on the day of adoption",
            )
        )
        return out

    base_pins, head_pins = _adoption_pins(base_text), _adoption_pins(head_text)
    # One loop over the pins the base recorded, because "moved" and "gone" are the same
    # question — is this root still pinned where it was — and were two loops only because the
    # answers word differently. A root the base never pinned is not compared here: gaining a
    # pin is the adopting case above, or the orphan case below.
    for root in sorted(base_pins):
        now = head_pins.get(root)
        if now == base_pins[root]:
            continue
        if now is None and root not in set(base_bindings.values()):
            # A pin no entry was bound to grants nothing, so dropping it weakens nothing.
            # Reporting it anyway made an unused pin permanent: `--update-adoption` preserves
            # every pin, so a source that never contributed an exception stayed coupled to the
            # record forever with no way to remove it.
            continue
        out.append(
            _finding(
                CODE_ADOPTION_SOURCE_REBOUND,
                Severity.error,
                head_path,
                f"the adoption boundary for source root `{root}` moved from "
                f"{base_pins[root][:12]} to {now[:12]} since {base_ref}"
                if now is not None
                else f"the adoption boundary for source root `{root}`, pinned at "
                f"{base_pins[root][:12]} at {base_ref}, is gone from the record",
                f"restore {base_pins[root][:12]}; everything that root gained since "
                "would otherwise become pre-existing debt"
                if now is not None
                else "restore the pin; without it nothing establishes that that root's "
                "entries pre-date this repository's adoption",
            )
        )
    # A pin that is *added* while the record already holds entries, beside a pin whose root
    # this change stopped configuring, is the same boundary move wearing a different shape.
    # Moving `../code/src` to `../newcode/src` keeps the old pin — dropping one is reported,
    # so the repair command preserves it — adds a new one, and the existing entries then
    # resolve to the new root and are verified against a different repository's revision.
    # Comparing only the roots the two records share, and the ones that went away, saw none
    # of that.
    orphaned = sorted(set(base_pins) - configured_roots)
    for root in sorted(set(head_pins) - set(base_pins)):
        if not base_paths or not orphaned:
            continue
        out.append(
            _finding(
                CODE_ADOPTION_SOURCE_REBOUND,
                Severity.error,
                head_path,
                f"the record gains a boundary for source root `{root}` while it still holds "
                f"{len(base_paths)} entr{'y' if len(base_paths) == 1 else 'ies'} and no longer "
                f"configures {', '.join(repr(item) for item in orphaned)} — those entries would "
                "be judged against a different repository",
                "retire the entries under the root being replaced before configuring the new "
                "one; an exception cannot follow the boundary to somewhere else",
            )
        )
    out.extend(_rebound_bindings(base_map, head_map, base_paths, head_paths, head_path, base_ref))
    for root in _dropped_boundaries(base_map, base_paths, configured_roots):
        out.append(
            _finding(
                CODE_ADOPTION_SOURCE_REBOUND,
                Severity.error,
                head_path,
                f"source root `{root}` is no longer configured, and the record still holds "
                f"entries adopted from it at {base_ref}, so nothing checks them any more",
                f"retire those entries before dropping `{root}`, or keep the root configured; "
                "an exception whose boundary is gone from the config is unverifiable, not met",
            )
        )

    # A recorded file the *source* repository deleted is excluded, and only that case. The
    # remedy for touching recorded debt is to retire the entry in the same change, and a pull
    # request in the other repository cannot: the record lives here, at this repository's
    # default branch. Requiring it would make such a deletion unmergeable once that workflow
    # is required, which is a gate nobody can satisfy rather than a gate. The entry goes stale
    # instead, which is the state this design already tolerates everywhere — and re-creating
    # the path is a source-side change to a file that exists, so touch-to-own still catches
    # that. Deleting it here, where the record is, still asks for the record.
    touched = sorted(
        (base_paths & head_paths & changed) - set(owned) - set(revived) - source_deleted
    )
    out.extend(_touched_findings(touched, present))
    return out


def _touched_findings(touched: list[str], present: frozenset[str]) -> list[Finding]:
    """Touch-to-own over recorded debt, for one set of paths this change worked on."""
    return [
        _finding(
            CODE_ADOPTION_DEBT_TOUCHED,
            Severity.error,
            path,
            f"`{path}` is recorded as pre-existing ownership debt and this change "
            + (
                # Deletion is one of the three ways an entry retires, so telling the author
                # to document the file asks for a doc about nothing. The remedy there is the
                # record, not a document — and "edits it" was wrong about the fact as well.
                "removes it, so the entry excepts nothing any more"
                if path not in present
                else "edits it, so it is no longer untouched history"
            ),
            "retire the entry: run `irminsul check --update-adoption` and commit the "
            "record in this change"
            if path not in present
            else "give it an owning doc in this change — add it to a doc's `describes:`, "
            "or write one with `irminsul new component` — and the exception retires",
        )
        for path in touched
    ]


def _owned_now(graph: DocGraph) -> frozenset[str]:
    """Every managed file this change gives an owner, under either ownership rule."""
    from irminsul.checks.globs import walk_configured_source_files
    from irminsul.checks.uniqueness import resolve_claims
    from irminsul.declared_tests import classify_test_reference

    if graph.repo_root is None or graph.config is None:
        return frozenset()
    from irminsul.declared_tests import governed_as_test, test_root_displays

    walked = list(walk_configured_source_files(graph.repo_root, graph.config).files)
    owned = set(resolve_claims(graph, walked))
    # A declaration is ownership only where the ownership rule would accept it. Counting
    # every exact entry meant `owns_tests: [src/b.py]` on an ordinary recorded source file
    # bought its way out of touch-to-own — and `test-ownership`, the only check that rejects
    # such a declaration as `not-a-test`, is one a repository may leave out of
    # `checks.enabled`, so with `uniqueness` alone the edit passed and the record went on
    # excepting the file.
    in_test_root = test_root_displays(graph.repo_root, graph.config)
    managed = {display for _, display in graph.source_map.walk}
    for node in graph.nodes.values():
        for entry in node.frontmatter.owns_tests:
            reference = classify_test_reference(entry, graph.repo_root)
            if not reference.is_exact:
                continue
            if not governed_as_test(
                reference.raw, graph.config, in_test_root=reference.raw in in_test_root
            ):
                continue
            if reference.raw not in managed and not (graph.repo_root / reference.raw).is_file():
                continue
            owned.add(reference.raw)
    return frozenset(owned)


def _relative_to(source: Path, repo_root: Path) -> str | None:
    """`source` as a POSIX path under `repo_root`, or None when it sits outside it."""
    try:
        return source.relative_to(repo_root).as_posix()
    except ValueError:
        return None


def _owned_at_ref(
    graph: DocGraph,
    displays: list[str],
    docs: list[str],
    read: Callable[[str], str | None],
    config: IrminsulConfig,
) -> frozenset[str]:
    """Every managed file some doc claimed at one ref, under either ownership rule.

    The head-side twin is `_owned_now`, which reads the built graph. Here there is no
    graph for the other ref, so the frontmatter is read off the blobs and run through the
    same specificity resolution — `owners` keys claimants by whatever name it is handed,
    and this hands it doc paths, because only the claimed set is wanted back.

    `config` is the configuration **of that ref**, and the distinction is the point.
    Ownership is a declaration plus the rule that accepts it, and the rule lives in
    `irminsul.toml`: whether a file in a declared test root answers to the test policy
    depends on `paths.source_roots`, so widening that list changes what an `owns_tests:`
    entry *meant* at the base. Read through the head's config instead, one change could
    delete an owner and widen a root, and the exception that owner had retired came back
    with nothing reporting it.

    The tree is the exception and cannot be one per snapshot: there is a single working
    tree, so a declared root's membership is walked in the checkout that exists.
    """
    from irminsul.declared_tests import (
        classify_test_reference,
        governed_as_test,
        test_root_displays,
    )
    from irminsul.ownership_moves import owners

    if graph.repo_root is None or graph.config is None:
        return frozenset()
    describes: dict[str, list[str]] = {}
    exact_tests: set[str] = set()
    in_test_root = test_root_displays(graph.repo_root, config)
    for path in docs:
        text = read(path)
        if text is None:
            continue
        meta = _frontmatter(text)
        claims = meta.get("describes")
        if isinstance(claims, list):
            describes[path] = [str(item) for item in claims]
        declared = meta.get("owns_tests")
        if isinstance(declared, list):
            for entry in declared:
                reference = classify_test_reference(str(entry), graph.repo_root)
                # Validated exactly as `_owned_now` validates it. Counting a declaration the
                # ownership rule would reject made the two sides disagree about the same
                # file, and the disagreement surfaced as a revived exception that was not one.
                if reference.is_exact and governed_as_test(
                    reference.raw, config, in_test_root=reference.raw in in_test_root
                ):
                    exact_tests.add(reference.raw)
    return frozenset(set(owners(describes, displays)) | exact_tests)


def _adopting(repo_root: Path, base: str, default_baseline: str) -> bool:
    """Whether the base is a repository that has not adopted Irminsul yet: no config, and
    no baseline where a run without a config would read one.

    Such a base holds no ratchet, so the baseline the adopting change records is a first
    one rather than a bigger one. A missing config alone is not the test. Deleting the
    config leaves the default baseline in force, so one change could drop the config and
    the next bring it back beside a bigger baseline. Each absence is asked of git rather
    than read off a failed read, which a base that cannot be read produces too.
    """
    return (
        exists_at_ref(repo_root, base, CONFIG_FILENAME) is False
        and exists_at_ref(repo_root, base, default_baseline) is False
    )


def _is_workflow(path: str) -> bool:
    """GitHub runs a YAML file directly in the workflows folder, and nothing nested in it."""
    name = path.removeprefix(_WORKFLOW_DIR)
    return path.startswith(_WORKFLOW_DIR) and "/" not in name and name.endswith((".yml", ".yaml"))


#: An event's `paths` or `paths-ignore` patterns, or None when every path triggers it.
_PathFilter = tuple[str, list[str]] | None


def _event_filters(text: str) -> dict[str, _PathFilter]:
    """The events in a workflow's `on:`, each with its path filter when it has one."""
    try:
        data = YAML(typ="safe").load(text)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    # YAML 1.1 reads a bare `on` key as the boolean true.
    declared = data.get("on", data.get(True))
    if isinstance(declared, str):
        return {declared: None}
    if isinstance(declared, list):
        return {str(event): None for event in declared}
    out: dict[str, _PathFilter] = {}
    for event, settings in declared.items() if isinstance(declared, dict) else ():
        out[str(event)] = None
        for key in ("paths", "paths-ignore"):
            patterns = settings.get(key) if isinstance(settings, dict) else None
            if isinstance(patterns, list):
                out[str(event)] = (key, [str(pattern) for pattern in patterns])
    return out


def _workflow_events(text: str) -> frozenset[str]:
    """The events in a workflow's `on:`, or none when it declares none that can be read."""
    return frozenset(_event_filters(text))


def _filter_regex(pattern: str) -> re.Pattern[str] | None:
    """A GitHub path filter as a regex: `*` stops at a slash, `**` does not, and `?` and
    `+` quantify the character before them, which is not what a shell glob means.

    `None` when the result does not compile. Those three constructs are handed to the
    regex engine rather than escaped, so a filter can be well-formed YAML, and something a
    person can reasonably type, and still not be a pattern: `+build/**` and `?src/**`
    quantify nothing, `src/[z-a].py` inverts a range, `src/[]` never closes its class.
    The caller decides what an unreadable filter means; it may not decide by tracebacking,
    which is what an uncaught `re.error` here did to the whole run.
    """
    out, index = "", 0
    while index < len(pattern):
        char = pattern[index]
        if pattern.startswith("**/", index):
            out, index = out + "(?:.*/)?", index + 3
        elif pattern.startswith("**", index):
            out, index = out + ".*", index + 2
        elif char == "*":
            out, index = out + "[^/]*", index + 1
        elif char in "?+":
            out, index = out + char, index + 1
        elif char == "[" and "]" in pattern[index:]:
            close = pattern.index("]", index)
            out, index = out + pattern[index : close + 1], close + 1
        else:
            out, index = out + re.escape(char), index + 1
    try:
        return re.compile(out)
    except re.error:
        return None


def _unreadable(rule: _PathFilter) -> list[str]:
    """The patterns in this filter that are not patterns, in the order they were written.

    A rule holding one of these admits an unknown set of paths, so a caller comparing what
    two filters admit has no answer to give and must say so rather than guess.

    A leading `!` is stripped from both kinds, where `_triggers` strips it only for
    `paths:` — inside `paths-ignore:` it reads `!` as an ordinary character, which is the
    open `paths-ignore-negation-not-honoured` gap. The disagreement is deliberate and it
    runs one way: calling a pattern unreadable can only skip a comparison, never assert a
    weakening from a pattern read the wrong way.
    """
    if rule is None:
        return []
    return [p for p in rule[1] if _filter_regex(p.removeprefix("!")) is None]


def _triggers(rule: _PathFilter, path: str) -> bool:
    """Whether a change to `path` alone runs a workflow that carries this filter.

    A pattern that does not compile matches nothing here. That keeps this total for every
    caller, and it is not the answer to what the filter admits — `_unreadable` is what
    tells a caller the question has no answer.
    """
    if rule is None:
        return True
    kind, patterns = rule
    if kind == "paths-ignore":
        return not any(
            regex.fullmatch(path)
            for pattern in patterns
            if (regex := _filter_regex(pattern)) is not None
        )
    hit = False
    for pattern in patterns:
        # A later pattern overrides an earlier one, which is how `!` takes paths back out.
        regex = _filter_regex(pattern.removeprefix("!"))
        if regex is not None and regex.fullmatch(path):
            hit = not pattern.startswith("!")
    return hit


#: The bucket for a workflow whose events cannot be read, which includes one whose YAML
#: stopped parsing: GitHub runs it on nothing, so its gates stop counting for any event.
_NO_EVENT: Final = ""

_Workflows = tuple[list[str], Callable[[str], str | None]]


def _gate_filters(workflows: _Workflows) -> dict[str, list[tuple[str, _PathFilter]]]:
    """For each event, the path filter of every workflow that gates on it, with the
    workflow that carries it, so a filter nothing can read names the file to edit."""
    paths, read = workflows
    filters: dict[str, list[tuple[str, _PathFilter]]] = {}
    for path in paths:
        text = read(path) or ""
        if _gate_strength(text, read)[0]:
            for event, rule in _event_filters(text).items():
                filters.setdefault(event, []).append((path, rule))
    return filters


def _strength_by_event(workflows: _Workflows) -> dict[str, _Strength]:
    paths, read = workflows
    totals: dict[str, _Strength] = {}
    for path in paths:
        text = read(path) or ""
        strength = _gate_strength(text, read)
        for event in _workflow_events(text) or {_NO_EVENT}:
            held = totals.get(event, _NO_STRENGTH)
            totals[event] = (
                held[0] + strength[0],
                held[1] + strength[1],
                held[2] + strength[2],
                held[3] + strength[3],
            )
    return totals


def _weakened_workflows(
    changed: frozenset[str],
    base: _Workflows,
    head: _Workflows,
    excused: str,
    base_ref: str,
    judged: Callable[[], list[str]],
) -> list[Finding]:
    """Events whose workflows stopped running `irminsul check`, or stopped gating it.

    `diff-integrity` and `co-change` run only under a diff range CI supplies, so the
    seal is armed by a flag living in a file the pull request can edit.

    Every workflow at the base is compared with every workflow at the head, not only the
    paths the diff lists: git reports a renamed file under its new name alone, so reading
    changed paths scored a renamed workflow's base as empty and any weakening made in the
    same change as no loss.

    Totals are kept per triggering event rather than per file or for the repository as a
    whole. Per file, moving a step to another workflow reads as deleting the gate. As one
    total, a gate added to a nightly run pays for one removed from pull requests, though
    no pull request is judged by it.

    A path filter is compared by what it admits rather than by its patterns, because a
    removed pattern proves nothing: a wider one may have replaced it. `judged` lists the
    files the gate reads. One that ran a gated workflow for an event at the base and
    runs none now is a change the gate has stopped seeing, and the finding names it. A
    file the gate never reads, or one that no longer exists, is not evidence of that.
    """
    # A local action's definition is part of the gate, so a change to one is compared too.
    touched = sorted(
        path
        for path in changed
        if path.startswith(_WORKFLOW_DIR) or posixpath.basename(path) in _LOCAL_ACTION_FILES
    )
    if not touched:
        return []

    was, now = _strength_by_event(base), _strength_by_event(head)
    axes = (
        (0, "irminsul check", "run `irminsul check` fewer times"),
        (1, "--strict", "fail on fewer finding classes (`--strict` / `--fail-on`)"),
        (2, "--diff", "gate the diff range less strictly (`--diff` / `--base-ref`)"),
        (3, "--profile", "run fewer checks (`--profile`)"),
    )
    where = ", ".join(touched)
    out: list[Finding] = []

    def report(message: str, token: str) -> None:
        out.append(
            _finding(
                CODE_GATE_WEAKENED,
                Severity.error,
                touched[0],
                f"{message} (changed: {where})",
                f"restore it, or add a decision record that names `{token}` and says why",
            )
        )

    for index, token, described in axes:
        if f"`{token}`" in excused:
            continue
        lost = sorted(
            event
            for event, strength in was.items()
            if strength[index] > now.get(event, _NO_STRENGTH)[index]
        )
        if not lost:
            continue
        events = ", ".join(f"`{event}`" for event in lost if event != _NO_EVENT)
        subject = f"workflows triggered by {events}" if events else "workflows"
        report(f"{subject} {described} than at {base_ref}", token)

    if "`paths`" in excused:
        return out
    filtered_was, filtered_now = _gate_filters(base), _gate_filters(head)
    for event in sorted(filtered_was):
        carried_was, carried_now = filtered_was[event], filtered_now.get(event, [])
        rules_was = [rule for _, rule in carried_was]
        rules_now = [rule for _, rule in carried_now]
        # With no gate left on the event the loss is reported above, and with no filter
        # on either side there is nothing to narrow.
        if not rules_now or all(rule is None for rule in (*rules_was, *rules_now)):
            continue
        if unreadable := _unreadable_report(event, carried_was, carried_now, base_ref):
            out.extend(unreadable)
            continue
        unseen = [
            path
            for path in judged()
            if any(_triggers(rule, path) for rule in rules_was)
            and not any(_triggers(rule, path) for rule in rules_now)
        ]
        if unseen:
            more = f" and {len(unseen) - 1} more" if len(unseen) > 1 else ""
            report(
                f"a change to `{unseen[0]}`{more} alone no longer runs a `{event}` workflow "
                f"that gates, as it did at {base_ref}",
                "paths",
            )
    return out


def _unreadable_report(
    event: str,
    carried_was: list[tuple[str, _PathFilter]],
    carried_now: list[tuple[str, _PathFilter]],
    base_ref: str,
) -> list[Finding]:
    """What to say about an event whose filters hold a pattern nothing can read.

    Comparing what two filters admit needs both sides read. One unreadable pattern on
    either side and the question has no answer, so this reports the pattern and the caller
    skips the comparison — the alternative is a certain `gate-weakened` resting on a
    pattern we failed to parse, or the traceback that used to end the run here.

    A pattern already unreadable at the base is inherited, and warns. One this change
    introduced errors: a filter that stops being readable stops being comparable, which is
    the seal losing an axis, and that is this change's doing.
    """
    inherited = {pattern for _, rule in carried_was for pattern in _unreadable(rule)}
    out: list[Finding] = []
    for path, rule in carried_now:
        for pattern in _unreadable(rule):
            if pattern in inherited:
                out.append(_not_compared(event, path, pattern, base_ref, at_base=False))
                continue
            out.append(
                _finding(
                    CODE_FILTER_UNREADABLE,
                    Severity.error,
                    path,
                    f"the `{event}` path filter entry `{pattern}` is not a pattern, so what "
                    f"this workflow admits was not compared with {base_ref}",
                    "fix the entry: `?` and `+` quantify the character before them and need "
                    "one, and `[...]` must close and must not invert its range",
                )
            )
    if out:
        return out
    # Nothing unreadable at the head, so the head side is comparable and the base is not.
    return [
        _not_compared(event, path, pattern, base_ref, at_base=True)
        for path, rule in carried_was
        for pattern in _unreadable(rule)
    ]


def _not_compared(event: str, path: str, pattern: str, base_ref: str, *, at_base: bool) -> Finding:
    """An entry that was already not a pattern before this change touched the filter."""
    where = f"at {base_ref} " if at_base else ""
    return _finding(
        CODE_FILTER_NOT_COMPARED,
        Severity.warning,
        path,
        f"the `{event}` path filter entry `{pattern}` {where}is not a pattern and was not "
        f"this change's doing, so what the gate admits was not compared with {base_ref}",
        "review the filter change by hand, and fix the entry to get the comparison back",
    )


def _accepted_decision_text(text: str) -> str:
    """The `## Decision` section of an accepted record, or "" when it is neither.

    The excuse for turning a gate off is meant to be a decision someone can review, so
    the name has to appear in a stable record's actual decision. Matching anywhere in any
    added file let a nine-line draft whose whole body was the check's name unlock it.
    """
    if _frontmatter(text).get("status") != "stable":
        return ""
    return _decision(text) or ""


_GOVERNS: Final = "governs-evidence"
_FOLLOWS: Final = "follows-evidence"


def _rewritten_governing_claims(
    path: str, old: str, new: str, excused: str, base_ref: str
) -> list[Finding]:
    """Governing claims whose wording or authority changed since the base.

    Protection is judged from the claim *at the base*: reading `relation` from the
    version under review would let a change downgrade its own protection and then edit
    freely — the same reason sealed folders and the baseline path are read from the
    merge base rather than from the change being judged.
    """
    after_by_id = {claim.get("id"): claim for claim in _entries_of(_frontmatter(new), "claims")}
    out: list[Finding] = []
    for before in _entries_of(_frontmatter(old), "claims"):
        if before.get("relation") != _GOVERNS:
            continue
        claim_id = before.get("id")
        after = after_by_id.get(claim_id)
        if after is None:
            continue  # removal is `claim-removed`'s business, not this one
        if f"`{claim_id}`" in excused:
            continue
        changed_field = next(
            (
                field
                for field in ("claim", "evidence", "state", "kind")
                if after.get(field) != before.get(field)
            ),
            None,
        )
        if changed_field is not None:
            # Not the wording alone: repointing `evidence` at a file that trivially
            # satisfies the sentence, or dropping `state` back to `planned`, leaves the
            # contract's words intact while it stops governing anything real.
            out.append(
                _finding(
                    CODE_GOVERNING_CLAIM_CHANGED,
                    Severity.error,
                    path,
                    f"governing claim '{claim_id}' had its {changed_field} changed "
                    f"since {base_ref}",
                    f"restore it, or add a decision record naming `{claim_id}`",
                )
            )
        elif after.get("relation") != _GOVERNS:
            out.append(
                _finding(
                    CODE_GOVERNING_CLAIM_CHANGED,
                    Severity.error,
                    path,
                    f"claim '{claim_id}' stopped governing its evidence since {base_ref}",
                    f"restore `relation: {_GOVERNS}`, or add a decision record naming `{claim_id}`",
                )
            )
    return out


def _body(text: str) -> str:
    try:
        _, body = split_frontmatter(text)
    except ValueError:
        return text
    return body


def _entries_of(meta: dict[str, object], key: str) -> list[dict[str, object]]:
    return [item for item in _listed(meta.get(key)) if isinstance(item, dict)]


def _listed(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _renamed_record(
    layer: LayerName, old_path: str, new_path: str, old: str, new: str | None, base_ref: str
) -> list[Finding]:
    """What a sealed record's move to `new_path` weakened, if anything.

    The move itself is allowed — a record is named by the slug of its title, so retitling
    one renames its file — but the content that arrives at the new path is still held to
    the seal.
    """
    if new is None or _without_id(old) == _without_id(new):
        return []
    if layer == "rfcs":
        return [
            _finding(
                CODE_IMPLEMENTED_RFC_CHANGED,
                Severity.error,
                new_path,
                f"RFC was implemented at {base_ref} as {old_path} and has changed since",
                "restore the record's text and propose the change in a new RFC",
            )
        ]
    if (decision := _decision(old)) is not None and decision != _decision(new):
        return [
            _finding(
                CODE_DECISION_REWRITTEN,
                Severity.warning,
                new_path,
                f"accepted decision section rewritten since {base_ref}, where it was {old_path}",
                "record the changed decision in a new ADR that supersedes this one",
            )
        ]
    return []


def _repo_path(raw: str) -> str:
    return posixpath.normpath(raw.replace("\\", "/"))


def _parsed(text: str | None) -> IrminsulConfig | None:
    if text is None:
        return None
    try:
        return IrminsulConfig.model_validate(tomllib.loads(text))
    except (tomllib.TOMLDecodeError, ValueError):
        return None


def _config_weakening(
    old: IrminsulConfig, new: IrminsulConfig, added_records: str, base_ref: str
) -> list[Finding]:
    def named(setting: str) -> bool:
        return f"`{setting}`" in added_records

    out: list[Finding] = []
    for name in sorted(set(old.checks.enabled) - set(new.checks.enabled)):
        if not named(name):
            out.append(
                _finding(
                    CODE_CHECK_DISABLED,
                    Severity.error,
                    CONFIG_FILENAME,
                    f"check '{name}' was removed from checks.enabled since {base_ref}",
                    f"restore '{name}', or add a decision record that names `{name}` and why",
                )
            )
    if _repo_path(old.paths.docs_root) != _repo_path(new.paths.docs_root) and not named(
        "docs_root"
    ):
        out.append(
            _finding(
                CODE_CHECK_DISABLED,
                Severity.error,
                CONFIG_FILENAME,
                f"paths.docs_root moved from '{old.paths.docs_root}' to "
                f"'{new.paths.docs_root}' since {base_ref}, so a different tree is judged",
                "restore docs_root, or add a decision record that names `docs_root` and why",
            )
        )
    # Declared sources, which nothing compared before: a source removed, its path pointed at
    # another repository, or its ref changed are each a change to what an adoption boundary
    # means, and the last two are what the adoption docs promise the gate reports. Anchoring
    # is checked when the record is written and not again, so an unreported ref change would
    # silently redefine the history the next adoption is measured against.
    old_sources = {source.name: source for source in old.paths.sources}
    new_sources = {source.name: source for source in new.paths.sources}
    for source_name in sorted(old_sources):
        before_source = old_sources[source_name]
        after_source = new_sources.get(source_name)
        if after_source is None:
            if not named(f"sources.{source_name}"):
                out.append(
                    _finding(
                        CODE_SETTING_WEAKENED,
                        Severity.error,
                        CONFIG_FILENAME,
                        f"declared source '{source_name}' is gone from paths.sources since "
                        f"{base_ref}, so any adoption entry bound to it has no repository, no "
                        "ref, and nothing to verify it",
                        f"restore it, or add a decision record naming `sources.{source_name}` "
                        "and why; retire its entries first if the repository really is gone",
                    )
                )
            continue
        for field, was, now in (
            ("path", before_source.path, after_source.path),
            ("ref", before_source.ref, after_source.ref),
        ):
            if was != now and not named(f"sources.{source_name}.{field}"):
                out.append(
                    _finding(
                        CODE_SETTING_WEAKENED,
                        Severity.error,
                        CONFIG_FILENAME,
                        f"source '{source_name}' changed its {field} from {was!r} to {now!r} "
                        f"since {base_ref}, which changes which history its adoption "
                        "boundary is measured against",
                        f"restore it, or add a decision record naming "
                        f"`sources.{source_name}.{field}` and why",
                    )
                )
    for layer in type(old.layers).model_fields:
        old_layer, new_layer = getattr(old.layers, layer), getattr(new.layers, layer)
        if old_layer.path != new_layer.path and not named(f"layers.{layer}"):
            out.append(
                _finding(
                    CODE_LAYER_RULE_DISABLED,
                    Severity.error,
                    CONFIG_FILENAME,
                    f"layer '{layer}' moved from '{old_layer.path}' to '{new_layer.path}' "
                    f"since {base_ref}, so its rules now judge a different folder",
                    f"restore the folder, or add a decision record naming `layers.{layer}`",
                )
            )
        for rule in _LAYER_RULES:
            if getattr(old_layer, rule) and not getattr(new_layer, rule) and not named(rule):
                out.append(
                    _finding(
                        CODE_LAYER_RULE_DISABLED,
                        Severity.error,
                        CONFIG_FILENAME,
                        f"layer rule layers.{layer}.{rule} was turned off since {base_ref}",
                        f"restore {rule}, or add a decision record that names `{rule}` and why",
                    )
                )
    old_paths, new_paths = old.paths, new.paths
    narrowed = [
        *(
            f"source exclude '{p}' was added"
            for p in new_paths.source_excludes
            if p not in old_paths.source_excludes
        ),
        *(
            f"source include '{p}' was added"
            for p in new_paths.source_includes
            if p not in old_paths.source_includes
        ),
        *(
            f"source root '{r}' was removed"
            for r in old_paths.source_roots
            if r not in new_paths.source_roots
        ),
        *(
            f"language '{name}' was removed"
            for name in old.languages.enabled
            if name not in new.languages.enabled
        ),
    ]
    if not old_paths.honor_gitignore and new_paths.honor_gitignore:
        narrowed.append("paths.honor_gitignore was turned on")
    # The test-ownership policy lives entirely in these two, so leaving them out let the
    # invariant be switched off by the same kind of edit this pass exists to seal.
    for root in [r for r in old_paths.test_roots if r not in new_paths.test_roots]:
        narrowed.append(f"test root '{root}' was removed, so its tests need no owner")
    if old_paths.test_patterns and not new_paths.test_patterns:
        narrowed.append("paths.test_patterns was emptied, so no file is recognised as a test")
    for change in narrowed:
        out.append(
            _finding(
                CODE_SOURCE_EXCLUDED,
                Severity.warning,
                CONFIG_FILENAME,
                f"{change} since {base_ref}",
                "confirm the files no longer read hold no documented code",
            )
        )
    for doc in [d for d in old_paths.extra_docs if d not in new_paths.extra_docs]:
        out.append(
            _finding(
                CODE_EXTRA_DOC_REMOVED,
                Severity.warning,
                CONFIG_FILENAME,
                f"'{doc}' was removed from paths.extra_docs since {base_ref}",
                "confirm it holds no guidance that must stay true",
            )
        )
    out.extend(_settings_weakening(old, new, named, base_ref))
    return out


def _settings_weakening(
    old: IrminsulConfig,
    new: IrminsulConfig,
    named: Callable[[str], bool],
    base_ref: str,
) -> list[Finding]:
    """Weakenings that do not go through `checks.enabled`.

    Removing a name from `checks.enabled` was sealed; switching the same check off
    through its own `enabled` key, or widening the threshold it fires above, was not —
    and both leave the check listed, so the sealed surface read as untouched. These
    compare the effective setting rather than the text, and are accepted the same way:
    a new stable decision record naming the setting in a code span.
    """
    out: list[Finding] = []
    if (
        old.checks.external_links.enabled
        and not new.checks.external_links.enabled
        and not named("external_links")
    ):
        out.append(
            _finding(
                CODE_SETTING_WEAKENED,
                Severity.error,
                CONFIG_FILENAME,
                f"checks.external_links.enabled was turned off since {base_ref}",
                "restore it, or add a decision record naming `external_links` and why",
            )
        )
    for setting, read in _THRESHOLD_SETTINGS:
        before, after = read(old), read(new)
        if after > before and not named(setting):
            out.append(
                _finding(
                    CODE_SETTING_WEAKENED,
                    Severity.error,
                    CONFIG_FILENAME,
                    f"{setting} was widened from {before} to {after} since {base_ref}, so "
                    "the check fires on less",
                    f"restore it, or add a decision record naming `{setting}` and why",
                )
            )
    if old.checks.glossary_discipline.glossary_path != (
        new.checks.glossary_discipline.glossary_path
    ) and not named("glossary_path"):
        out.append(
            _finding(
                CODE_SETTING_WEAKENED,
                Severity.error,
                CONFIG_FILENAME,
                f"glossary_path was repointed since {base_ref}; the terms governed are "
                "whatever the new file holds",
                "restore it, or add a decision record naming `glossary_path` and why",
            )
        )
    out.extend(_rules_narrowed(old, new, base_ref))
    out.extend(_unreviewed_settings(old, new, base_ref))
    return out


def _rules_narrowed(old: IrminsulConfig, new: IrminsulConfig, base_ref: str) -> list[Finding]:
    """Configured rules that stopped watching something, compared by identity.

    A rule list is a set of watches, so what matters is which watch disappeared, not that
    the list is shorter — an edited rule and a deleted one look the same by length.
    """
    gone: list[str] = []
    old_terms = {rule.term for rule in old.checks.terminology_overload.rules}
    new_terms = {rule.term for rule in new.checks.terminology_overload.rules}
    gone.extend(
        f"terminology rule for '{term}' was removed" for term in sorted(old_terms - new_terms)
    )
    old_generic = {(rule.kind, rule.glob) for rule in old.checks.inventory_drift.generic}
    new_generic = {(rule.kind, rule.glob) for rule in new.checks.inventory_drift.generic}
    gone.extend(
        f"inventory rule '{kind}' over '{glob}' was removed"
        for kind, glob in sorted(old_generic - new_generic)
    )
    old_packs, new_packs = old.frameworks.enabled, new.frameworks.enabled
    if old_packs is None and new_packs is not None:
        gone.append("frameworks.enabled narrowed from every pack to a named set")
    elif old_packs is not None and new_packs is not None:
        gone.extend(f"framework pack '{p}' was removed" for p in old_packs if p not in new_packs)
    return [
        _finding(
            CODE_RULES_NARROWED,
            Severity.warning,
            CONFIG_FILENAME,
            f"{change} since {base_ref}",
            "confirm nothing documented depended on it",
        )
        for change in gone
    ]


def _unreviewed_settings(old: IrminsulConfig, new: IrminsulConfig, base_ref: str) -> list[Finding]:
    """A check setting that changed with no rule above to judge it.

    Without this, the next setting added to the schema is a free bypass until somebody
    remembers to seal it: the comparison above is a hand-written list and nothing
    mechanical notices what is missing from it. Compared field by field rather than table
    by table, because naming a whole table judged left its siblings unwatched —
    `external_links.enabled` is sealed while `timeout_seconds` dropped to 0.01, which times
    every link out and passes, was neither judged nor mentioned.

    Reported as a hint: "changed" is not "weakened", and only a reader can say which.
    """
    out: list[Finding] = []
    for table in type(old.checks).model_fields:
        before, after = getattr(old.checks, table), getattr(new.checks, table)
        for name, changed in _setting_changes(table, before, after):
            if name in _JUDGED_SETTINGS or not changed:
                continue
            out.append(
                _finding(
                    CODE_UNREVIEWED_SETTING_CHANGE,
                    Severity.warning,
                    CONFIG_FILENAME,
                    f"checks.{name} changed since {base_ref}, and nothing here judges "
                    "whether that weakens the gate",
                    "confirm it does not, or seal the setting in _settings_weakening",
                )
            )
    return out


def _setting_changes(table: str, before: object, after: object) -> list[tuple[str, bool]]:
    """`(dotted name, changed)` for a settings table, one entry per leaf field.

    A table that is not a model — a future scalar directly on `checks` — yields itself;
    calling `model_dump()` on one would have taken the whole pass down with an
    AttributeError the first time somebody added a bool.
    """
    if not isinstance(before, BaseModel) or not isinstance(after, BaseModel):
        return [(table, before != after)]
    return [
        (f"{table}.{field}", getattr(before, field) != getattr(after, field))
        for field in type(before).model_fields
    ]


def _owner_changes(
    graph: DocGraph,
    changed: frozenset[str],
    base: str,
    base_ref: str,
    read: Callable[[str, str], str | None] | None = None,
) -> list[Finding]:
    from irminsul.ownership_moves import owner_moves

    grouped: dict[tuple[tuple[str, ...], tuple[str, ...]], list[str]] = {}
    for move in owner_moves(graph, changed, base, read):
        grouped.setdefault((move.before, move.after), []).append(move.file)
    out: list[Finding] = []
    for (before, after), files in sorted(grouped.items()):
        shown = ", ".join(files[:3]) + (f", and {len(files) - 3} more" if len(files) > 3 else "")
        out.append(
            _finding(
                CODE_OWNER_CHANGED,
                Severity.warning,
                after[0],
                f"{shown} moved from {', '.join(before)} to {', '.join(after)} since {base_ref}",
                "remove what the old owner still says about these files, or link the two docs",
            )
        )
    return out


def _implemented(meta: dict[str, object]) -> bool:
    return meta.get("rfc_state") == "implemented"


def _accepted(meta: dict[str, object]) -> bool:
    return meta.get("status") == "stable"


def _normalized(text: str) -> str:
    return text.replace("\r\n", "\n")


def _without_id(text: str) -> str:
    return _ID_LINE_RE.sub("", _normalized(text), count=1)


def _entries(text: str | None) -> set[tuple[str, str, str]]:
    if text is None:
        return set()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return set()
    findings = payload.get("findings") if isinstance(payload, dict) else None
    if not isinstance(findings, list):
        return set()
    return {
        (str(entry.get("check")), str(entry.get("path")), str(entry.get("message")))
        for entry in findings
        if isinstance(entry, dict)
    }


def _frontmatter(text: str) -> dict[str, object]:
    try:
        raw, _ = split_frontmatter(text)
        data = YAML(typ="safe").load(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _decision(text: str) -> str | None:
    match = _DECISION_RE.search(_normalized(text))
    return " ".join(match.group(1).split()) if match else None


def _finding(code: str, severity: Severity, path: str, message: str, suggestion: str) -> Finding:
    category = code.split("/", 1)[1]
    return Finding(
        check=CHECK_NAME,
        code=code,
        category=category,
        severity=severity,
        message=message,
        path=Path(path),
        suggestion=suggestion,
        data={"problem": category},
    )
