"""Diff integrity — a change must not quietly lower the gates it is judged by.

A pass, not a registered graph check: like `co-change`, it needs the diff range, which
`--diff <base>` or `context --after-edit` with a base puts on the graph. It compares files
with their content at the merge base, which a pull request cannot rewrite, and always
reports what it finds. Each finding names a subject, and the acknowledgement step accepts
it when a trailer of the change names that subject, so the lists below say what the pass
reports, not what a trailer can answer.

- the baseline gained entries, so new findings were recorded instead of fixed;
- an RFC that was implemented at the base changed, or no longer exists. A change whose
  only difference is a reference pointed at a doc the same diff renamed is not a change;
- a decision record that was accepted at the base no longer exists;
- an accepted decision record's `## Decision` section was rewritten in place;
- a source file's owning doc changed, so the old owner's prose about it may stay behind;
- the config moved a setting the way that makes a check ask less — a check or a layer rule
  turned off, a threshold widened, the tree moved, the source walk or guidance files
  narrowed — or changed a setting nothing here judges;
- a workflow or action file that mentions irminsul was added, deleted, renamed or edited;
- an anchor, a `claims:` entry, or an `inventory:` entry was deleted while the code it
  named is still there, so a doc stopped asking about code that still exists. The same
  removal is not reported when that code went away in the same change — except for a
  claim that governed its evidence at the base, which only a trailer naming the claim ends;
- a claim was reworded rather than removed — a hint, since nothing separates correcting
  a sentence from emptying it of meaning — unless it is `follows-evidence`, where the
  evidence wins and correcting the report is routine, or `governs-evidence`, where
  `governing-claim-changed` reports the rewording instead;
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
from collections.abc import Callable, Collection, Iterator
from dataclasses import dataclass
from functools import cache
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, ClassVar, Final, Literal

from pathspec import GitIgnoreSpec
from pydantic import BaseModel
from ruamel.yaml import YAML

from irminsul import source_map
from irminsul.adoption import AdoptionRecord, parse_record
from irminsul.anchors import ANCHOR_RE
from irminsul.checks.base import Answer, Finding, FindingClass, Severity
from irminsul.checks.change_range import after_paths, after_text
from irminsul.config import (
    CONFIG_FILENAME,
    LAYER_NAMES,
    IrminsulConfig,
    LayerName,
    docs_root_prefix,
    in_layer,
    layer_prefix,
    parse_snapshot,
)
from irminsul.docgraph import ChangeRange, DocGraph
from irminsul.frontmatter_edit import split_frontmatter
from irminsul.git.changes import (
    GitChangesError,
    exists_at_ref,
    file_at_ref,
    files_at_ref,
    renamed_paths,
    tracked_paths_at_ref,
)
from irminsul.source_map import Binding, SourceMap, build_source_map
from irminsul.source_tree import SourceTree

if TYPE_CHECKING:
    from irminsul.git.reader import GitReader

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
_DECISION_REWRITTEN_SUGGESTION: Final = (
    "restore the record and keep the code it names, so the two still agree as accepted"
)
CODE_OWNER_CHANGED: Final = "diff-integrity/owner-changed"
CODE_CHECK_DISABLED: Final = "diff-integrity/check-disabled"
CODE_LAYER_RULE_DISABLED: Final = "diff-integrity/layer-rule-disabled"
CODE_SOURCE_EXCLUDED: Final = "diff-integrity/source-excluded"
CODE_EXTRA_DOC_REMOVED: Final = "diff-integrity/extra-doc-removed"
CODE_BASE_CONFIG_UNREADABLE: Final = "diff-integrity/base-config-unreadable"
CODE_GATE_FILE_CHANGED: Final = "diff-integrity/gate-file-changed"
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

_DECISION_RE = re.compile(r"(?ms)^##\s+Decision\s*$(.*?)(?=^##\s|\Z)")
_INLINE_LINK_RE = re.compile(r"(?<!!)\[([^\]\n]*)\]\([^)\n]*\)")
_ID_LINE_RE = re.compile(r"(?m)^id:[^\n]*\n")


class DiffIntegrityPass:
    """A change must not quietly lower the gates it is judged by."""

    name: ClassVar[str] = CHECK_NAME
    default_severity: ClassVar[Severity] = Severity.error
    explanations: ClassVar[dict[str, str]] = {
        CODE_BASELINE_GREW: (
            "The baseline file records findings it did not record at the base of the diff, "
            "so new findings were recorded rather than fixed. Fix them and restore the "
            "baseline, or shrink it. An upgrade whose new rules find problems in old docs "
            "may not be able to fix them all in one change."
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
            "state — nothing obliges anyone to run `irminsul adoption update`."
        ),
        CODE_ADOPTION_PIN_NOT_ON_REF: (
            "A first adoption record pins a source at a commit that the history the source "
            "declares does not contain. Anything committed off that history is not something "
            "the source repository's mainline ever had, so recording its files as pre-existing "
            "debt would except files nobody reviewed into that history — pushing a branch "
            "needs no review, and pinning it would be the whole of the attack. Pin a commit on "
            "the declared ref; `irminsul adoption init` picks the merge base of the source "
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
            "adopt from scratch. Retire the entries with `irminsul adoption update` until the record "
            "is empty."
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
            "and propose the change in a new RFC. A reference pointed at a doc the same "
            "change renamed is not a change; any other edit is."
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
            "An accepted decision record's `## Decision` section was rewritten in place. A "
            "changed decision needs a new record that supersedes this one, unless an accepted "
            "RFC already made the change. A correction that changes no decision, such as a "
            "typo, or a change that carries out an accepted RFC, needs no new record; a trailer "
            "naming this record says which of the two it is."
        ),
        CODE_OWNER_CHANGED: (
            "Source files moved from one doc's `describes` to another's. Remove what the old "
            "owner still says about them, or link the two docs; `irminsul list review "
            "--changed` lists the old owner's sentences that name the files."
        ),
        CODE_CHECK_DISABLED: (
            "The change removed a check from `checks.enabled`, or moved `paths.docs_root` so "
            "a different tree is judged, and the gate that judges this change got weaker. "
            "Restore it."
        ),
        CODE_LAYER_RULE_DISABLED: (
            "The change turned off a layer rule, or moved a layer's folder so its rules judge "
            "a different one, and the gate that judges this change got weaker. Restore it."
        ),
        CODE_SOURCE_EXCLUDED: (
            "The change made the source walk read fewer files: an added source exclude or "
            "include, a removed source root, test root or language, emptied test patterns, or "
            "gitignore honoured. Whether the files no longer read hold documented code is "
            "not something a check can tell."
        ),
        CODE_EXTRA_DOC_REMOVED: (
            "The change removed a file from `paths.extra_docs`, so the checks that read "
            "guidance files no longer read it. Whether it held guidance to keep true is not "
            "something a check can tell."
        ),
        CODE_GATE_FILE_CHANGED: (
            "The change added, deleted, renamed or edited a file under `.github/workflows/`, "
            "or an `action.yml` or `action.yaml`, whose text mentions irminsul at the base "
            "of the diff or now. The passes that compare a change with its base run only "
            "when CI asks for them, so a change that edits the file asking can switch off "
            "the thing judging it. What the edit means is not read: a comment counts the "
            "same as a dropped flag. The finding's subject is the file's path: the path it "
            "had when deleted, otherwise its path now. Not reported when the base holds "
            "neither irminsul.toml nor a baseline, since a change that adopts Irminsul has "
            "nothing to weaken."
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
            "it would forbid. Restore the claim."
        ),
        CODE_CLAIM_REWORDED: (
            "A claim's sentence changed while its id stayed the same, so it is a "
            "rewording rather than a removal. Nothing can tell a correction from a "
            "claim quietly emptied of meaning, so re-read it against the evidence it "
            "cites. A `follows-evidence` claim is exempt: the evidence wins there, and "
            "correcting the report is routine. A `governs-evidence` claim is exempt too, and "
            "`governing-claim-changed` reports its rewording instead."
        ),
        CODE_GOVERNING_CLAIM_CHANGED: (
            "A claim that governs its evidence was rewritten, or stopped governing it. "
            "Such a claim is a contract: the implementation answers to it, so changing "
            "its words — or its `relation` — is a change of intent, not doc maintenance, "
            "and it must not ride along with the change it would otherwise forbid. Restore "
            "the wording."
        ),
        CODE_INVENTORY_WEAKENED: (
            "An `inventory:` entry kept its kind and source but asks less of the code "
            "than it did at the base of the diff: it stopped requiring the prose to "
            "explain each item, stopped demanding completeness, or added an `omit`. "
            "Each of those silences a live identity without removing the entry, which "
            "the removal seal watches. Restore the contract."
        ),
        CODE_SETTING_WEAKENED: (
            "A setting that decides how much a check asks was weakened: the check was "
            "switched off through its own `enabled` key, a threshold it fires above was "
            "widened, the glossary it reads was repointed, or a declared source was removed "
            "or given another path or ref. None of these touch `checks.enabled`, so the "
            "check stays listed while asking less. Restore the setting."
        ),
        CODE_RULES_NARROWED: (
            "A configured rule stopped watching something: a `surface.rules` entry's "
            "`(kind, globs)` pair, or a framework pack. Compared by what the rule watched "
            "rather than by list length, since an edited rule and a deleted one shorten the "
            "list alike. Whether anything documented depended on it is not something a "
            "check can tell."
        ),
        CODE_UNREVIEWED_SETTING_CHANGE: (
            "A setting changed and no rule here judges whether that weakens the gate. Every "
            "field of the config schema is compared, so a setting added later is reported "
            "from the day it exists instead of being a free bypass until somebody seals it. "
            "Nothing is asserted to be wrong: it asks a reader to confirm."
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
        CODE_GATE_FILE_CHANGED: FindingClass.certain,
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
    }
    answers: ClassVar[dict[str, Answer]] = {
        CODE_DECISION_REWRITTEN: Answer.trailer(
            "a changed decision needs a superseding record, unless an accepted RFC already made "
            "it; if this only corrects the wording or carries out that RFC, add this trailer"
        ),
        CODE_OWNER_CHANGED: Answer.fix(
            "remove what the old owner still says about the moved files, or link the two docs"
        ),
        CODE_BASE_CONFIG_UNREADABLE: Answer.fix(
            "review the config changes by hand; it ends once the change that repairs the config "
            "merges"
        ),
        CODE_BASELINE_GREW: Answer.trailer(
            "if the new findings have to wait, add this trailer and say why"
        ),
        CODE_ADOPTION_RECORD_REMOVED: Answer.trailer(
            "if the record should go, add this trailer and say why"
        ),
        CODE_CLAIM_REWORDED: Answer.trailer(
            "if you re-read the new wording against its evidence and it is right, add this trailer"
        ),
        CODE_CLAIM_REMOVED: Answer.trailer("if the claim no longer applies, add this trailer"),
        CODE_GOVERNING_CLAIM_REMOVED: Answer.trailer(
            "if the contract is retired on purpose, add this trailer and say why"
        ),
        CODE_GOVERNING_CLAIM_CHANGED: Answer.trailer(
            "if the change of intent is deliberate, add this trailer and say why"
        ),
        CODE_INVENTORY_WEAKENED: Answer.trailer(
            "if the weaker contract is deliberate, add this trailer and say why"
        ),
        CODE_GATE_FILE_CHANGED: Answer.trailer(
            "if the edit does not weaken the gate, add this trailer"
        ),
        CODE_CHECK_DISABLED: Answer.trailer(
            "if the weaker gate is deliberate, add this trailer and say why"
        ),
        CODE_LAYER_RULE_DISABLED: Answer.trailer(
            "if the weaker rule is deliberate, add this trailer and say why"
        ),
        CODE_SETTING_WEAKENED: Answer.trailer(
            "if the weaker setting is deliberate, add this trailer and say why"
        ),
        CODE_SOURCE_EXCLUDED: Answer.trailer(
            "if the files no longer read hold no documented code, add this trailer"
        ),
        CODE_EXTRA_DOC_REMOVED: Answer.trailer(
            "if the file holds no guidance that must stay true, add this trailer"
        ),
        CODE_RULES_NARROWED: Answer.trailer(
            "if nothing documented depended on the rule, add this trailer"
        ),
        CODE_UNREVIEWED_SETTING_CHANGE: Answer.trailer(
            "if the change does not weaken the gate, add this trailer"
        ),
    }

    def run(self, graph: DocGraph, selected: Collection[str]) -> list[Finding]:
        change = graph.change
        if change is None:
            return []
        return run_diff_integrity(graph, change)


def run_diff_integrity(graph: DocGraph, change: ChangeRange) -> list[Finding]:
    """Findings for the gates the change weakened.

    The before side is the merge base, and the after side is the working tree, or `HEAD`
    when the range ends there. Which folders hold sealed records, and where the baseline
    lives, are read from the config at the merge base, so a change cannot move them out of
    its own way.

    `change.source_changed` is what a sibling source repository changed, in display
    spellings, and it reaches exactly one rule: touch-to-own over recorded debt. Everything
    else here judges this repository's own diff, and widening those would answer a question
    nobody asked — `co-change` across a repository boundary is its own open design, not a
    side effect of this field.
    """
    if graph.config is None or graph.repo_root is None:
        return []
    config = graph.config
    repo_root = graph.repo_root
    git = graph.git
    changed, source_changed = change.changed, change.source_changed
    base_ref, base = change.base, change.merge_base

    def _read(ref: str, path: str) -> str | None:
        try:
            return file_at_ref(git, repo_root, ref, path)
        except GitChangesError:
            return None

    def before(path: str) -> str | None:
        return _read(base, path)

    def after(path: str) -> str | None:
        return after_text(git, repo_root, change.head, path)

    def listed_before(directory: str) -> list[str]:
        try:
            return files_at_ref(git, repo_root, base, directory)
        except GitChangesError:
            return []

    def listed_after(directory: str) -> list[str]:
        return after_paths(git, repo_root, change.head, directory)

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
    out.extend(
        _baseline_ratchet(
            changed,
            base_baseline,
            head_baseline,
            git,
            repo_root,
            base,
            base_ref,
            before,
            after,
        )
    )

    base_adoption = _repo_path(ratchet.paths.adoption)
    head_adoption = _repo_path(config.paths.adoption)
    walked = graph.source.files
    walked_displays = [display for _, display in walked]
    # The record covers tests too, and `test_roots` are not source roots, so the ordinary
    # walk does not reach a declared test tree at all. The record is built from both walks
    # (`adoption.py`); the seal has to ask about the same set or a recorded test would keep
    # an exception the record no longer justifies.
    already = {display for _, display in walked}
    managed = [
        *walked,
        *(pair for pair in graph.source.test_walk.files if pair[1] not in already),
    ]
    # Which of those this repository's own history can answer for. In the siblings layout a
    # display is relative to a source root in another repository, and asking this tree
    # whether it held that path at some ref is a question with no answer.
    in_this_repo = frozenset(
        display for source, display in managed if _relative_to(Path(source), repo_root) == display
    )

    renames = renamed_paths(git, repo_root, base, change.head)
    # `changed_since` passes `--find-renames`, so a renamed doc appears under its new
    # path only, so the base side is read at the old one.
    renamed_from = {new_path: old_path for old_path, new_path in renames.items()}
    renamed_docs = {
        old_path: new_path
        for old_path, new_path in renames.items()
        if old_path.endswith(".md") and new_path.endswith(".md")
    }

    @cache
    def renamed_ids() -> dict[str, str]:
        return {
            _stem(old_path): _stem(new_path)
            for old_path, new_path in renamed_docs.items()
            if _stem(old_path) != _stem(new_path)
            and (text := before(old_path)) is not None
            and _frontmatter(text).get("id") == _stem(old_path)
        }

    def retargeted(old: str, new: str, path: str, same: Callable[[str], str]) -> bool:
        return _only_retargeted(old, new, path, renamed_docs, renamed_ids, same)

    # Answering the seal's questions costs a `git show` per document at the base, and a
    # repository that never adopted has no record for any of them to be about. So the
    # texts are read first and the rest is skipped when neither side holds a record.
    base_record, head_record = before(base_adoption), after(head_adoption)
    if base_record is not None or head_record is not None:
        base_parsed, head_parsed = (
            parse_record(text, tolerant=True) if text is not None else AdoptionRecord()
            for text in (base_record, head_record)
        )
        # Both docs roots, because a change may move the tree and the base's docs sit
        # under whichever one the base's own config named.
        base_docs = sorted(
            {
                path
                for folder in {docs_root_prefix(sealing), docs_root_prefix(config)}
                for path in listed_before(folder)
                if path.endswith(".md")
            }
        )
        base_tree = graph.source if sealing is config else SourceTree(repo_root, sealing)
        out.extend(
            _adoption_seal(
                repo_root,
                changed | source_changed,
                base_parsed,
                head_parsed,
                head_adoption,
                base_ref,
                base_path=base_adoption,
                removed=base_record is not None and head_record is None,
                adopting=exists_at_ref(git, repo_root, base, base_adoption) is False,
                owned=_owned_now(graph),
                owned_at_base=_owned_at_ref(
                    graph, walked_displays, base_docs, before, sealing, base_tree.test_displays
                ),
                # A recorded path the tree no longer holds excepts nothing, and its owner
                # at the base went away with the file rather than with this change's docs.
                present=frozenset(display for _, display in managed),
                at_base=tracked_paths_at_ref(git, repo_root, base),
                in_this_repo=in_this_repo,
                configured_roots=frozenset((*config.paths.source_roots, *config.paths.test_roots)),
                renamed_from=renamed_from,
                # Two snapshots, two resolutions. The base's bindings come from the base's
                # config and the base's record, so a change cannot alter what the base *meant*
                # by editing either. The checkout is the one input they share, because there is
                # one working tree and a sibling repository is cloned into it once.
                base_map=build_source_map(base_tree, base_parsed),
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
                    _unanchored_pins(git, graph.source_map, head_parsed)
                    if exists_at_ref(git, repo_root, base, base_adoption) is False
                    else ()
                ),
                # Which of the changed paths the other repository deleted. Separated from the
                # merged set because the remedy for touching recorded debt is a change to the
                # record, and only this repository's own pull requests can make one.
                source_deleted=_source_paths_gone(graph.source_map, source_changed),
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
        if (
            new is not None
            and not was_renamed
            and in_layer(sealing, path, "rfcs")
            and _implemented(_frontmatter(old))
            and retargeted(old, new, path, same)
        ):
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
                base_ref,
                source_displays,
            )
        )
        out.extend(_rewritten_governing_claims(path, old, surviving, base_ref))
        if new is None or was_renamed:
            # A renamed sealed record is the `sealed_layers` sweep's business: it finds
            # the record at its new path through the same rename map and says where it
            # moved from. Reporting here too would say the same thing twice.
            continue
        out.extend(_sealed_rewrites(sealing, path, old, new, base_ref))

    out.extend(
        _sealed_records(
            sealing,
            config,
            renames,
            before,
            after,
            listed_before,
            listed_after,
            retargeted,
            base_ref,
        )
    )
    out.extend(_owner_changes(graph, changed, base, base_ref, _read))
    head_text = after(CONFIG_FILENAME)
    head_config = _parsed(head_text) if head_text is not None else IrminsulConfig()
    if CONFIG_FILENAME in changed and base_config is not None and head_config is not None:
        out.extend(_config_weakening(base_config, head_config, base_ref))
    # A change that adopts Irminsul has no gate to weaken, as with its first baseline.
    if not _adopting(git, repo_root, base, base_baseline):
        out.extend(_changed_gate_files(changed, renames, renamed_from, before, after, base_ref))
    return out


def _baseline_ratchet(
    changed: frozenset[str],
    base_baseline: str,
    head_baseline: str,
    git: GitReader,
    repo_root: Path,
    base: str,
    base_ref: str,
    before: Callable[[str], str | None],
    after: Callable[[str], str | None],
) -> list[Finding]:
    """A baseline that gained entries since the base, unless the change adopts Irminsul."""
    out: list[Finding] = []
    if base_baseline in changed or head_baseline in changed or base_baseline != head_baseline:
        added = _entries(after(head_baseline)) - _entries(before(base_baseline))
        if added and not _adopting(git, repo_root, base, base_baseline):
            out.append(
                _finding(
                    CODE_BASELINE_GREW,
                    Severity.error,
                    head_baseline,
                    f"baseline gained {len(added)} entr{'y' if len(added) == 1 else 'ies'} "
                    f"since {base_ref}",
                    "fix the new findings instead of recording them",
                    subject=head_baseline,
                    about=(base_baseline, head_baseline),
                )
            )
    return out


def _sealed_records(
    sealing: IrminsulConfig,
    config: IrminsulConfig,
    renames: dict[str, str],
    before: Callable[[str], str | None],
    after: Callable[[str], str | None],
    listed_before: Callable[[str], list[str]],
    listed_after: Callable[[str], list[str]],
    retargeted: Callable[[str, str, str, Callable[[str], str]], bool],
    base_ref: str,
) -> list[Finding]:
    """Sealed records the base held that the head no longer has, or whose move weakened them."""
    out: list[Finding] = []
    sealed_layers: tuple[tuple[LayerName, str, Callable[[dict[str, object]], bool], str], ...] = (
        ("rfcs", CODE_IMPLEMENTED_RFC_REMOVED, _implemented, "implemented RFC"),
        ("decisions", CODE_ACCEPTED_DECISION_REMOVED, _accepted, "accepted decision record"),
    )
    for layer, code, sealed, noun in sealed_layers:
        directory = layer_prefix(sealing, layer)
        head_paths = {
            path
            for folder in sorted({directory, layer_prefix(config, layer)})
            for path in listed_after(folder)
            if path.endswith(".md") and not path.endswith("/INDEX.md")
        }
        head_texts: set[str] | None = None
        for path in sorted(listed_before(directory)):
            if not path.endswith(".md") or path.endswith("/INDEX.md") or path in head_paths:
                continue
            old = before(path)
            if old is None or not sealed(_frontmatter(old)):
                continue
            moved = renames.get(path)
            if moved is not None and moved in head_paths:
                out.extend(
                    _renamed_record(layer, path, moved, old, after(moved), base_ref, retargeted)
                )
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
    return out


def _sealed_rewrites(
    sealing: IrminsulConfig, path: str, old: str, new: str, base_ref: str
) -> list[Finding]:
    """A sealed record edited in place: an implemented RFC, or an accepted decision's wording."""
    out: list[Finding] = []
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
        and _decision_wording(old) != _decision_wording(new)
    ):
        out.append(
            _finding(
                CODE_DECISION_REWRITTEN,
                Severity.warning,
                path,
                f"accepted decision section rewritten since {base_ref}",
                _DECISION_REWRITTEN_SUGGESTION,
                subject=path,
            )
        )
    return out


def _declared_now(graph: DocGraph) -> tuple[set[tuple[str, str | None]], set[object], set[object]]:
    """Every anchor, claim, and inventory entry the head tree declares, in any doc.

    Gathered tree-wide rather than per-doc so splitting a doc, which moves declarations
    from one file to another, is not read as deleting them — but each is identified by
    its *content*, not by its name. `Claim.id` is unique only within one document, so
    matching on the bare id would let an unrelated doc reusing a name mask a real removal.
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
    base_ref: str,
    source_displays: list[str],
) -> list[Finding]:
    """What a doc stopped asking about code that is still there.

    A doc governs code by declaring things about it: an anchor pins a symbol, a `claims:`
    entry cites evidence, an `inventory:` entry watches a surface. Every check verifies
    that such a declaration is true, and none notices it being deleted — so the cheapest
    way to clear a finding would be to delete the declaration that raised it. Removing one is
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
    # on demand" as a deletion would leave ordinary maintenance with no green route.
    surviving_by_id = {claim.get("id"): claim for claim in _entries_of(new_meta, "claims")}
    for claim in _entries_of(old_meta, "claims"):
        claim_id = claim.get("id")
        evidence = [str(item) for item in _listed(claim.get("evidence"))]
        if (kept := surviving_by_id.get(claim_id)) is not None:
            if kept.get("claim") != claim.get("claim") and claim.get("relation") not in (
                _FOLLOWS,
                _GOVERNS,
            ):
                out.append(
                    _finding(
                        CODE_CLAIM_REWORDED,
                        Severity.warning,
                        path,
                        f"claim '{claim_id}' was reworded since {base_ref}",
                        "re-read the new wording against the evidence the claim cites, "
                        "and the prose it governs",
                        subject=str(claim_id),
                    )
                )
            continue
        if (claim_id, claim.get("claim")) in kept_claims or not evidence:
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
                    "restore it",
                    subject=str(claim_id),
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
                subject=str(claim_id),
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
            if weakening is not None:
                out.append(
                    _finding(
                        CODE_INVENTORY_WEAKENED,
                        Severity.error,
                        path,
                        f"inventory entry '{kind}' {weakening} since {base_ref}",
                        "restore the contract",
                        subject=path,
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
    """How a surviving `inventory:` entry asks less of the code than it did at the base.

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
    finds nothing and every removal there goes unreported.
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
_ACTION_FILES: Final = ("action.yml", "action.yaml")


def _is_gate_path(path: str) -> bool:
    return path.startswith(_WORKFLOW_DIR) or posixpath.basename(path) in _ACTION_FILES


def _changed_gate_files(
    changed: frozenset[str],
    renames: dict[str, str],
    renamed_from: dict[str, str],
    before: Callable[[str], str | None],
    after: Callable[[str], str | None],
    base_ref: str,
) -> list[Finding]:
    """Every workflow or action file mentioning irminsul that this change touched.

    The passes that judge a change run only when CI asks for them, so the files that ask
    are sealed whole. What an edit means is not read: git reports that a file changed
    exactly, and a reading of the change would have to guess at the semantics of GitHub
    and of the shell. The text is searched rather than parsed, so a file that stops parsing
    is still sealed, and a file that mentions irminsul on either side counts, so one that
    stops mentioning it is sealed too.
    """
    out: list[Finding] = []
    for path in sorted(changed):
        if renames.get(path) in changed:
            continue  # reported once, under the path it moved to
        old_path = renamed_from.get(path, path)
        if not (_is_gate_path(path) or _is_gate_path(old_path)):
            continue
        old, new = before(old_path), after(path)
        if not any(text is not None and "irminsul" in text.lower() for text in (old, new)):
            continue
        if (
            old_path == path
            and old is not None
            and new is not None
            and _normalized(old) == _normalized(new)
        ):
            continue
        named = old_path if new is None else path
        if old is None:
            how = "was added"
        elif new is None:
            how = "was deleted"
        elif old_path != path:
            how = f"was renamed from `{old_path}`"
        else:
            how = "was edited"
        out.append(
            _finding(
                CODE_GATE_FILE_CHANGED,
                Severity.error,
                named,
                f"`{named}` mentions irminsul and {how} since {base_ref}",
                "undo the change if it weakens the gate",
                subject=named,
                about=(old_path, path),
            )
        )
    return out


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

    The invariant the pin rules in `_adoption_seal` and `_dropped_boundaries` each approach
    from one side: an entry that is in both records must resolve to the same
    `(repository, revision)` pair in both snapshots. Stating it directly catches what a pin
    comparison cannot see, because an entry is not bound to a root — it is bound to whichever
    root the walk resolves its display to. Replace `../code/src` with `../newcode/src` and
    every existing entry is verified against another repository with no pin having changed.

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
    reading that as a deletion would exempt the change from touch-to-own, let it edit recorded
    debt unchallenged, and hand the exception back the day the ignore rule came off. The
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


def _unanchored_pins(
    git: GitReader, smap: SourceMap, head: AdoptionRecord
) -> tuple[tuple[str, str, str], ...]:
    """Pinned sources whose revision is not contained in the ref they declare.

    Asked of the repository on disk, once, for the change that creates the record. A commit
    on a pushed side branch resolves and reads perfectly well — which is exactly why the
    revision alone is not evidence that the declared history ever had those files.

    Each unresolvable piece is reported as its own reason rather than skipped. A missing ref
    and a pin off the history are both "this pin is not anchored", and treating either as
    "nothing to check" would make the quietest state the safest one.
    """
    from irminsul.git.changes import is_ancestor, resolve_ref

    out: list[tuple[str, str, str]] = []
    for source, revision in sorted((pin.source, pin.revision) for pin in head.sources):
        ref = smap.refs.get(source)
        if ref is None:
            out.append((source, "any declared ref", "no `[[paths.sources]]` entry declares it"))
            continue
        boundary = smap.boundary_for_source(source)
        if boundary is None or boundary.git_root is None:
            out.append((source, ref, "its repository is not checked out here to ask"))
            continue
        tip = resolve_ref(git, boundary.git_root, ref)
        if tip is None:
            out.append((source, ref, "that ref is not in this checkout of the repository"))
            continue
        if not is_ancestor(git, boundary.git_root, revision, tip):
            out.append((source, ref, f"{revision[:12]} is not an ancestor of {tip[:12]}"))
    return tuple(out)


def _adoption_seal(
    repo_root: Path,
    changed: frozenset[str],
    base: AdoptionRecord,
    head: AdoptionRecord,
    head_path: str,
    base_ref: str,
    *,
    base_path: str,
    removed: bool,
    adopting: bool,
    owned: frozenset[str],
    owned_at_base: frozenset[str],
    present: frozenset[str],
    at_base: set[str] | None,
    in_this_repo: frozenset[str],
    configured_roots: frozenset[str],
    renamed_from: dict[str, str],
    base_map: SourceMap,
    head_map: SourceMap,
    base_rules_known: bool,
    unanchored: tuple[tuple[str, str, str], ...],
    source_deleted: frozenset[str],
) -> list[Finding]:
    """What this change did to the adoption record, and to the files it excepts.

    Two things have to hold for the record to mean anything. It may not grow — an entry
    added by a pull request is a file this change left unowned and then excused, which is
    the debt the record exists to bound rather than to absorb. And an excepted file this
    change *edits* stops being untouched history: somebody is in there, so the exception
    has done its job and the same change documents the file. That is touch-to-own, and it
    reads the diff's own changed set, which runs from the merge base to the working tree, so
    it sees work already committed on the branch as well as what is uncommitted.

    The change that creates the record is the adoption itself and is allowed, the way a
    first baseline is: the base holds no record, so there is no ratchet to widen. What it
    is not allowed to do is decide for itself what counts as history.

    **The obligations that change has to meet are enumerated in one place, and it is not
    here:** `docs/components/adoption-record.md`, under "What the adopting change must
    prove". The rules are listed rather than discovered, because no one of them implies
    another: each closes a different way for the adopting change to call new debt history.
    A rule added here belongs in that list in the same change; the claim
    `adopting-obligations-are-complete` is what says so.

    The revival rule covers what growth and touch-to-own cannot see. An entry is retired by the file
    gaining an owner, and `irminsul adoption update` is what takes the path back out — but
    nothing makes anyone run it, so a stale record goes on naming a file that is already
    documented. Take that owner away and current-record-contents alone would hand the
    exception back, which is an exception returning. So a recorded file that had an owner
    *at the base of the diff* is judged as retired whatever the record still says, and the
    comparison boundary supplies the state the record failed to record.
    """
    base_paths, head_paths = set(base.unowned), set(head.unowned)
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
    if removed and base_paths:
        out.append(
            _finding(
                CODE_ADOPTION_RECORD_REMOVED,
                Severity.error,
                head_path,
                f"the adoption record still named {len(base_paths)} file(s) at {base_ref} and "
                "this change deletes it",
                "retire the entries with `irminsul adoption update` until the record is empty",
                subject=head_path,
                about=(base_path, head_path),
            )
        )
        return out

    # Computed before the record-growth rules, and reported before their early returns,
    # because it applies to the adopting change as much as to any other. The change that
    # creates the record would otherwise be trusted twice over: it could delete an owning
    # document and register the file it had owned as history in the same commit, and the file
    # did exist at the base, so the historical-presence rule below passes it honestly.
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
                # A rename is diagnosed and not excused. Following it back would make a
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
                            "remove the entry, or correct the path; `irminsul adoption init` "
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
                        f"pin a commit on {ref}; `irminsul adoption init` uses the merge base "
                        "of the source checkout and that ref, which is one by construction",
                    )
                )
            # Touch-to-own applies to the adopting change too. Returning here would let the one
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

    base_pins = {pin.source: pin.revision for pin in base.sources}
    head_pins = {pin.source: pin.revision for pin in head.sources}
    # One loop over the pins the base recorded, because "moved" and "gone" are the same
    # question — is this root still pinned where it was — and only the answers word
    # differently. A root the base never pinned is not compared here: gaining a
    # pin is the adopting case above, or the orphan case below.
    for root in sorted(base_pins):
        now = head_pins.get(root)
        if now == base_pins[root]:
            continue
        if now is None and root not in set(base.bindings.values()):
            # A pin no entry was bound to grants nothing, so dropping it weakens nothing.
            # Reporting it anyway would make an unused pin permanent: `irminsul adoption
            # update` preserves every pin, so a source that never contributed an exception
            # would stay coupled to the record forever with no way to remove it.
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
    # Comparing only the roots the two records share, and the ones that went away, would see
    # none of that.
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
                # Deletion is one of the ways an entry retires, so telling the author to
                # document the file would ask for a doc about nothing. The remedy there is the
                # record, not a document.
                "removes it, so the entry excepts nothing any more"
                if path not in present
                else "edits it, so it is no longer untouched history"
            ),
            "retire the entry: run `irminsul adoption update` and commit the record in this change"
            if path not in present
            else "give it an owning doc in this change — add it to a doc's `describes:`, "
            "or write one with `irminsul new component` — and the exception retires",
        )
        for path in touched
    ]


def _owned_now(graph: DocGraph) -> frozenset[str]:
    """Every managed file this change gives an owner, under either ownership rule."""
    from irminsul.declared_tests import classify_test_reference

    if graph.repo_root is None or graph.config is None:
        return frozenset()
    from irminsul.declared_tests import governed_as_test

    owned = set(graph.claims)
    # A declaration is ownership only where the ownership rule would accept it. Counting
    # every exact entry would let `owns_tests: [src/b.py]` on an ordinary recorded source file
    # buy its way out of touch-to-own — and `test-ownership`, the only check that rejects
    # such a declaration as `not-a-test`, is one a repository may leave out of
    # `checks.enabled`, so with `uniqueness` alone the edit would pass and the record would
    # go on excepting the file.
    in_test_root = graph.source.test_displays
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
    test_displays: frozenset[str],
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
    delete an owner and widen a root, and the exception that owner had retired would come
    back with nothing reporting it.

    The tree is the exception and cannot be one per snapshot: there is a single working
    tree, so a declared root's membership is walked in the checkout that exists, and
    `test_displays` is what that walk produced for the declared test roots.
    """
    from irminsul.declared_tests import classify_test_reference, governed_as_test
    from irminsul.ownership_moves import owners

    if graph.repo_root is None or graph.config is None:
        return frozenset()
    describes: dict[str, list[str]] = {}
    exact_tests: set[str] = set()
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
                # ownership rule rejects would make the two sides disagree about the
                # same file, and the disagreement would surface as a revived exception that
                # is not one.
                if reference.is_exact and governed_as_test(
                    reference.raw, config, in_test_root=reference.raw in test_displays
                ):
                    exact_tests.add(reference.raw)
    return frozenset(set(owners(describes, displays)) | exact_tests)


def _adopting(git: GitReader, repo_root: Path, base: str, default_baseline: str) -> bool:
    """Whether the base is a repository that has not adopted Irminsul yet: no config, and
    no baseline where a run without a config would read one.

    Such a base holds no ratchet, so the baseline the adopting change records is a first
    one rather than a bigger one. A missing config alone is not the test. Deleting the
    config leaves the default baseline in force, so one change could drop the config and
    the next bring it back beside a bigger baseline. Each absence is asked of git rather
    than read off a failed read, which a base that cannot be read produces too.
    """
    return (
        exists_at_ref(git, repo_root, base, CONFIG_FILENAME) is False
        and exists_at_ref(git, repo_root, base, default_baseline) is False
    )


_GOVERNS: Final = "governs-evidence"
_FOLLOWS: Final = "follows-evidence"


def _rewritten_governing_claims(path: str, old: str, new: str, base_ref: str) -> list[Finding]:
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
                    "restore it",
                    subject=str(claim_id),
                )
            )
        elif after.get("relation") != _GOVERNS:
            out.append(
                _finding(
                    CODE_GOVERNING_CLAIM_CHANGED,
                    Severity.error,
                    path,
                    f"claim '{claim_id}' stopped governing its evidence since {base_ref}",
                    f"restore `relation: {_GOVERNS}`",
                    subject=str(claim_id),
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
    layer: LayerName,
    old_path: str,
    new_path: str,
    old: str,
    new: str | None,
    base_ref: str,
    retargeted: Callable[[str, str, str, Callable[[str], str]], bool],
) -> list[Finding]:
    """What a sealed record's move to `new_path` weakened, if anything.

    The move itself is allowed — a record is named by the slug of its title, so retitling
    one renames its file — but the content that arrives at the new path is still held to
    the seal.
    """
    if new is None or _without_id(old) == _without_id(new):
        return []
    if layer == "rfcs":
        if retargeted(old, new, old_path, _without_id):
            return []
        return [
            _finding(
                CODE_IMPLEMENTED_RFC_CHANGED,
                Severity.error,
                new_path,
                f"RFC was implemented at {base_ref} as {old_path} and has changed since",
                "restore the record's text and propose the change in a new RFC",
            )
        ]
    if _decision(old) is not None and _decision_wording(old) != _decision_wording(new):
        return [
            _finding(
                CODE_DECISION_REWRITTEN,
                Severity.warning,
                new_path,
                f"accepted decision section rewritten since {base_ref}, where it was {old_path}",
                _DECISION_REWRITTEN_SUGGESTION,
                subject=new_path,
                about=(old_path, new_path),
            )
        ]
    return []


def _only_retargeted(
    old: str,
    new: str,
    path: str,
    renamed: dict[str, str],
    renamed_ids: Callable[[], dict[str, str]],
    same: Callable[[str], str],
) -> bool:
    """Whether `new` is `old` with each reference to a doc this change renamed pointed at
    the doc's new name, and differs in nothing else.

    An implemented RFC is sealed, so a change that renames a doc the RFC links would be
    stuck: the link breaks, and mending it edits a sealed record. The references are
    rewritten in `old` and the result compared with `new`, so a retargeted link passes
    and any other word changed, or a link pointed at a doc that was not renamed, does not.

    A reference is the doc's repo path, its path from the RFC's directory, or its id when
    the id is the filename stem, each as a whole token. The ids are tried second, because
    an id such as `checks` is also an ordinary word in prose: rewriting every occurrence
    then no longer matches an RFC that retargeted only its links. Once tried, an id counts
    as a reference wherever it stands, so a prose word equal to a renamed id passes too.
    """
    if not renamed:
        return False
    target = same(new)
    start = posixpath.dirname(path)
    spellings: dict[str, str] = {}
    for source, moved in renamed.items():
        spellings[source] = moved
        spellings[_relative_from(start, source)] = _relative_from(start, moved)
    if same(_retarget(old, spellings)) == target:
        return True
    ids = renamed_ids()
    return bool(ids) and same(_retarget(old, spellings | ids)) == target


def _retarget(text: str, spellings: dict[str, str]) -> str:
    alternatives = "|".join(
        re.escape(spelling) for spelling in sorted(spellings, key=len, reverse=True)
    )
    pattern = re.compile(rf"(?<![\w./-])(\./)?({alternatives})(?![\w/-])(?!\.\w)")
    return pattern.sub(lambda match: (match.group(1) or "") + spellings[match.group(2)], text)


def _relative_from(directory: str, target: str) -> str:
    start = PurePosixPath(directory).parts
    goal = PurePosixPath(target).parts
    shared = 0
    while shared < min(len(start), len(goal) - 1) and start[shared] == goal[shared]:
        shared += 1
    return "/".join([*[".."] * (len(start) - shared), *goal[shared:]])


def _stem(path: str) -> str:
    return posixpath.basename(path).removesuffix(".md")


def _repo_path(raw: str) -> str:
    return posixpath.normpath(raw.replace("\\", "/"))


def _parsed(text: str | None) -> IrminsulConfig | None:
    if text is None:
        return None
    try:
        return parse_snapshot(tomllib.loads(text))
    except (tomllib.TOMLDecodeError, ValueError):
        return None


_Weaker = Literal[
    "raised",
    "false",
    "true",
    "narrowed",
    "added",
    "emptied",
    "any-change",
    "removal-by-identity",
    "none-means-all",
    "inert",
]


@dataclass(frozen=True)
class _Seal:
    """Which change to a setting makes a check ask less, and the finding that says so.

    `weaker` is that change: a number `raised`; a flag turned `false` or `true`; a list
    `narrowed` by losing an entry, `added` to (which for an exclude narrows what is read), or
    `emptied`; `any-change` at all; a list of tables losing the entry its `identity` fields
    name (`removal-by-identity`); or `none-means-all`, where unset means every value, so
    setting the list, or dropping an entry from it, narrows. An `inert` setting gates
    nothing, so no change to it is reported and it needs no code.

    `identity` also lets each entry kept on both sides have its own fields compared. A
    finding's subject is the setting's dotted name, or with `cites_entry` the entry it lost,
    which is what a trailer names to answer it. `normalize` reads a value the way the
    setting's users do, so a respelling is no change.
    """

    weaker: _Weaker
    code: str = ""
    identity: tuple[str, ...] = ()
    cites_entry: bool = False
    normalize: Callable[[Any], object] | None = None


#: Every setting whose weaker direction is known, by its dotted name in the schema. Any
#: other setting is `unreviewed-setting-change` whenever it changes.
_SEALS: Final[dict[str, _Seal]] = {
    "project_name": _Seal("inert"),
    "paths.docs_root": _Seal("any-change", CODE_CHECK_DISABLED, normalize=_repo_path),
    "paths.source_roots": _Seal("narrowed", CODE_SOURCE_EXCLUDED),
    "paths.source_includes": _Seal("added", CODE_SOURCE_EXCLUDED),
    "paths.source_excludes": _Seal("added", CODE_SOURCE_EXCLUDED),
    "paths.honor_gitignore": _Seal("true", CODE_SOURCE_EXCLUDED),
    "paths.test_patterns": _Seal("emptied", CODE_SOURCE_EXCLUDED),
    "paths.test_roots": _Seal("narrowed", CODE_SOURCE_EXCLUDED),
    "paths.extra_docs": _Seal("narrowed", CODE_EXTRA_DOC_REMOVED),
    "paths.sources": _Seal("removal-by-identity", CODE_SETTING_WEAKENED, identity=("name",)),
    "paths.sources.path": _Seal("any-change", CODE_SETTING_WEAKENED),
    "paths.sources.ref": _Seal("any-change", CODE_SETTING_WEAKENED),
    # A trailer names the check it turns off.
    "checks.enabled": _Seal("narrowed", CODE_CHECK_DISABLED, cites_entry=True),
    "checks.external_links.enabled": _Seal("false", CODE_SETTING_WEAKENED),
    "checks.stale_reaper.deprecated_threshold_days": _Seal("raised", CODE_SETTING_WEAKENED),
    "checks.rfc_follow_through.accepted_threshold_days": _Seal("raised", CODE_SETTING_WEAKENED),
    "checks.glossary_discipline.glossary_path": _Seal("any-change", CODE_SETTING_WEAKENED),
    "checks.parent_child.length_warning_lines": _Seal("raised", CODE_SETTING_WEAKENED),
    "surface.rules": _Seal("removal-by-identity", CODE_RULES_NARROWED, identity=("kind", "globs")),
    "overrides.mtime_drift_days": _Seal("raised", CODE_SETTING_WEAKENED),
    "languages.enabled": _Seal("narrowed", CODE_SOURCE_EXCLUDED),
    "frameworks.enabled": _Seal("none-means-all", CODE_RULES_NARROWED),
    **{
        f"layers.{layer}.path": _Seal("any-change", CODE_LAYER_RULE_DISABLED)
        for layer in LAYER_NAMES
    },
    **{
        f"layers.{layer}.{rule}": _Seal("false", CODE_LAYER_RULE_DISABLED)
        for layer in LAYER_NAMES
        for rule in ("require_tests", "require_scope_section")
    },
}


@dataclass(frozen=True)
class _Change:
    """A setting that differs between two configs: `name` is its dotted name in the schema,
    and `shown` the same with the entry selected in each list of tables it sits in."""

    name: str
    shown: str
    was: Any
    now: Any


def _config_weakening(old: IrminsulConfig, new: IrminsulConfig, base_ref: str) -> list[Finding]:
    """Settings this change moved the way that makes a check ask less, and settings no seal
    judges that changed at all.

    The schema is walked rather than listed, so a field added to it is compared from the
    day it exists: unsealed, it is a hint until somebody gives it a direction. Each finding
    names the setting it is about as its subject, which a trailer names to answer it.
    """
    out: list[Finding] = []
    for change in _changes(old, new):
        seal = _SEALS.get(change.name)
        if seal is None:
            out.append(
                _finding(
                    CODE_UNREVIEWED_SETTING_CHANGE,
                    Severity.warning,
                    CONFIG_FILENAME,
                    f"{change.shown} changed since {base_ref}, and nothing here judges "
                    "whether that weakens the gate",
                    None,
                    subject=change.name,
                )
            )
            continue
        for what, entry in _weakenings(seal, change):
            cited = str(entry) if seal.cites_entry else change.name
            certain = DiffIntegrityPass.classes[seal.code] is FindingClass.certain
            out.append(
                _finding(
                    seal.code,
                    Severity.error if certain else Severity.warning,
                    CONFIG_FILENAME,
                    f"{what} since {base_ref}",
                    "restore it",
                    subject=cited,
                )
            )
    return out


def _changes(old: BaseModel, new: BaseModel, name: str = "", shown: str = "") -> Iterator[_Change]:
    """Every setting that differs between `old` and `new`, walked through the schema.

    A table is walked into, and so is each entry a list of tables keeps on both sides when
    its seal names the fields that identify one.
    """
    for field in type(old).model_fields:
        dotted, label = f"{name}{field}", f"{shown}{field}"
        was, now = getattr(old, field), getattr(new, field)
        if isinstance(was, BaseModel) and isinstance(now, BaseModel):
            yield from _changes(was, now, f"{dotted}.", f"{label}.")
            continue
        if was == now:
            continue
        yield _Change(dotted, label, was, now)
        seal = _SEALS.get(dotted)
        if seal is None or not seal.identity:
            continue
        before, after = _by_identity(was, seal.identity), _by_identity(now, seal.identity)
        for key in sorted(before.keys() & after.keys()):
            selected = f"{label}[{_selector(seal.identity, key)}]."
            yield from _changes(before[key], after[key], f"{dotted}.", selected)


def _weakenings(seal: _Seal, change: _Change) -> list[tuple[str, object]]:
    """What `change` did in the direction `seal` calls weaker, each with the entry it
    concerns, or nothing when it went the other way."""
    shown, was, now = change.shown, change.was, change.now
    match seal.weaker:
        case "raised":
            if now > was:
                return [(f"{shown} was widened from {was} to {now}", None)]
        case "false":
            if was and not now:
                return [(f"{shown} was turned off", None)]
        case "true":
            if now and not was:
                return [(f"{shown} was turned on", None)]
        case "emptied":
            if was and not now:
                return [(f"{shown} was emptied", None)]
        case "any-change":
            if seal.normalize is None or seal.normalize(was) != seal.normalize(now):
                return [(f"{shown} changed from {was!r} to {now!r}", None)]
        case "added":
            return [(f"{item!r} was added to {shown}", item) for item in _only_in(now, was)]
        case "narrowed":
            return [(f"{item!r} was removed from {shown}", item) for item in _only_in(was, now)]
        case "none-means-all":
            if was is None:
                return [(f"{shown} was narrowed from every entry to {now!r}", None)]
            if now is not None:
                return [(f"{item!r} was removed from {shown}", item) for item in _only_in(was, now)]
        case "removal-by-identity":
            kept = _by_identity(now, seal.identity)
            return [
                (f"{shown}[{_selector(seal.identity, key)}] was removed", key)
                for key in _by_identity(was, seal.identity)
                if key not in kept
            ]
    return []


def _only_in(entries: list[Any], other: list[Any]) -> list[Any]:
    return [item for item in dict.fromkeys(entries) if item not in other]


def _by_identity(
    entries: list[BaseModel], fields: tuple[str, ...]
) -> dict[tuple[Any, ...], BaseModel]:
    return {tuple(getattr(entry, field) for field in fields): entry for entry in entries}


def _selector(fields: tuple[str, ...], key: tuple[Any, ...]) -> str:
    return ", ".join(f"{field}={value!r}" for field, value in zip(fields, key, strict=True))


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


def _decision_wording(text: str | None) -> str | None:
    """The `## Decision` section with each inline link reduced to its text, without
    code-span backticks, and with each anchor's pin left out.

    Linking a phrase to the record that now governs it is how a later record qualifies
    an accepted one without rewriting it, and it changes no word of the decision; linking
    one flag inside a longer code span splits that span. Only the words are compared, so
    a word changed inside the new link still counts. A pin is written by `anchors --re-pin`
    to say which version of the code was re-read, so moving one rewrites nothing, while
    what the anchor names still counts.
    """
    decision = _decision(text) if text is not None else None
    if decision is None:
        return None
    unpinned = ANCHOR_RE.sub(
        lambda match: f"anchor {match['path']}#{match['symbol'] or ''}", decision
    )
    return _INLINE_LINK_RE.sub(r"\1", unpinned).replace("`", "")


def _finding(
    code: str,
    severity: Severity,
    path: str,
    message: str,
    suggestion: str | None,
    *,
    subject: str | None = None,
    about: tuple[str, ...] = (),
) -> Finding:
    return Finding(
        check=CHECK_NAME,
        code=code,
        severity=severity,
        message=message,
        path=Path(path),
        suggestion=suggestion,
        subject=subject,
        about=tuple(dict.fromkeys(about)),
    )
