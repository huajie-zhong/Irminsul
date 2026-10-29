"""Tests for the diff-integrity pass that runs under `check --diff`."""

from __future__ import annotations

import datetime as _dt
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from irminsul.cli import app

from .conftest import (
    check_codes,
    check_findings,
    commit_all,
    config_toml,
    git,
    git_init,
    load_graph,
    write,
    write_config,
)

runner = CliRunner()

_AT = _dt.datetime(2024, 1, 1, tzinfo=_dt.UTC)

_RFC = (
    "---\nid: 0001-x\ntitle: X\nstatus: stable\nsummary: A test doc.\n"
    "rfc_state: implemented\nresolved_by: docs/decisions/INDEX.md\n---\n\n# X\n\nProposal.\n"
)
_ADR = (
    "---\nid: 0001-choice\ntitle: Choice\nstatus: stable\nsummary: A test doc.\n---\n\n# Choice\n\n"
    "## Status\n\nAccepted.\n\n## Decision\n\nUse A.\n\n## Consequences\n\nFine.\n"
)


def _repo(root: Path) -> Path:
    git_init(root)
    write_config(root, enabled=["frontmatter"])
    write(
        root,
        "docs/decisions/INDEX.md",
        "---\nid: decisions\ntitle: D\nstatus: stable\nsummary: A test doc.\n---\n\n# D\n",
    )
    return root


def test_a_growing_baseline_is_an_error(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    entry = {"check": "links", "path": "docs/a.md", "message": "broken", "fingerprint": "x"}
    write(root, ".irminsul-baseline.json", json.dumps({"version": 1, "findings": [entry]}))
    base = commit_all(root, "baseline")
    grown = [entry, {**entry, "message": "also broken"}]
    write(root, ".irminsul-baseline.json", json.dumps({"version": 1, "findings": grown}))
    commit_all(root, "grow baseline")

    assert "diff-integrity/baseline-grew" in check_codes(root, "--diff", base)


_DEBT = {"check": "links", "path": "docs/a.md", "message": "broken", "fingerprint": "x"}
_MORE_DEBT = {**_DEBT, "message": "also broken"}
_GREW = "diff-integrity/baseline-grew"


def _baseline(root: Path, *entries: dict[str, str], path: str = ".irminsul-baseline.json") -> None:
    write(root, path, json.dumps({"version": 1, "findings": list(entries)}))


def _before_irminsul(root: Path) -> str:
    git_init(root)
    write(root, "README.md", "# r\n")
    return commit_all(root, "before irminsul")


def test_adopting_irminsul_with_a_baseline_is_not_growth(tmp_path: Path) -> None:
    """A repository with no config and no baseline has no ratchet to hold, so the baseline
    its adopting change records is a first one rather than a bigger one."""
    base = _before_irminsul(tmp_path)
    _repo(tmp_path)
    _baseline(tmp_path, _DEBT, _MORE_DEBT)
    commit_all(tmp_path, "adopt irminsul, recording the debt already there")

    assert _GREW not in check_codes(tmp_path, "--diff", base)


def test_the_change_after_adoption_may_shrink_the_baseline(tmp_path: Path) -> None:
    _before_irminsul(tmp_path)
    _repo(tmp_path)
    _baseline(tmp_path, _DEBT, _MORE_DEBT)
    adopted = commit_all(tmp_path, "adopt")
    _baseline(tmp_path, _DEBT)
    commit_all(tmp_path, "pay some debt down")

    assert _GREW not in check_codes(tmp_path, "--diff", adopted)


def test_the_change_after_adoption_may_not_grow_the_baseline(tmp_path: Path) -> None:
    _before_irminsul(tmp_path)
    _repo(tmp_path)
    _baseline(tmp_path, _DEBT)
    adopted = commit_all(tmp_path, "adopt")
    _baseline(tmp_path, _DEBT, _MORE_DEBT)
    commit_all(tmp_path, "record new debt")

    assert _GREW in check_codes(tmp_path, "--diff", adopted)


def test_recreating_the_config_in_one_change_does_not_reset_the_ratchet(tmp_path: Path) -> None:
    _repo(tmp_path)
    _baseline(tmp_path, _DEBT)
    base = commit_all(tmp_path, "adopted")
    config = (tmp_path / "irminsul.toml").read_text(encoding="utf-8")
    write(tmp_path, "irminsul.toml", config.replace('"r"', '"renamed"'))
    _baseline(tmp_path, _DEBT, _MORE_DEBT)
    commit_all(tmp_path, "rewrite the config and the baseline together")

    assert _GREW in check_codes(tmp_path, "--diff", base)


def test_dropping_the_config_first_does_not_reset_the_ratchet(tmp_path: Path) -> None:
    """A run with no config still honours the baseline at its default path, so a base that
    holds one is an adopter however its config came to be missing."""
    _repo(tmp_path)
    _baseline(tmp_path, _DEBT)
    commit_all(tmp_path, "adopted")
    config = (tmp_path / "irminsul.toml").read_text(encoding="utf-8")
    (tmp_path / "irminsul.toml").unlink()
    without_config = commit_all(tmp_path, "drop the config, keep the baseline")
    write(tmp_path, "irminsul.toml", config)
    _baseline(tmp_path, _DEBT, _MORE_DEBT)
    commit_all(tmp_path, "bring the config back with a bigger baseline")

    assert _GREW in check_codes(tmp_path, "--diff", without_config)


def test_pointing_a_returning_config_at_a_new_baseline_file_is_still_growth(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    _baseline(tmp_path, _DEBT)
    commit_all(tmp_path, "adopted")
    config = (tmp_path / "irminsul.toml").read_text(encoding="utf-8")
    (tmp_path / "irminsul.toml").unlink()
    without_config = commit_all(tmp_path, "drop the config, keep the baseline")
    write(
        tmp_path, "irminsul.toml", config.replace("[paths]\n", '[paths]\nbaseline = "debt.json"\n')
    )
    _baseline(tmp_path, _DEBT, _MORE_DEBT, path="debt.json")
    commit_all(tmp_path, "bring the config back, pointed at a new baseline file")

    assert _GREW in check_codes(tmp_path, "--diff", without_config)


def test_recreating_a_deleted_baseline_is_growth(tmp_path: Path) -> None:
    """An adopter's first baseline is created once; one recorded later hides findings the
    gate was already reporting."""
    _repo(tmp_path)
    base = commit_all(tmp_path, "adopted with no baseline")
    _baseline(tmp_path, _DEBT)
    commit_all(tmp_path, "record debt after the fact")

    assert _GREW in check_codes(tmp_path, "--diff", base)


def _grown_baseline_repo(root: Path) -> str:
    _repo(root)
    _baseline(root, _DEBT)
    base = commit_all(root, "adopted")
    _baseline(root, _DEBT, _MORE_DEBT)
    return base


def test_a_decision_record_naming_the_baseline_clears_its_growth(tmp_path: Path) -> None:
    base = _grown_baseline_repo(tmp_path)
    _record(tmp_path, "upgrade-adds-findings", ".irminsul-baseline.json")
    commit_all(tmp_path, "re-create the baseline, and say why the findings wait")

    assert _GREW not in check_codes(tmp_path, "--diff", base)


def test_a_grown_baseline_without_a_record_is_still_growth(tmp_path: Path) -> None:
    base = _grown_baseline_repo(tmp_path)
    commit_all(tmp_path, "re-create the baseline")

    assert _GREW in check_codes(tmp_path, "--diff", base)


def test_a_record_naming_another_file_does_not_clear_baseline_growth(tmp_path: Path) -> None:
    base = _grown_baseline_repo(tmp_path)
    _record(tmp_path, "something-else", "irminsul.toml")
    commit_all(tmp_path, "re-create the baseline, explain another file")

    assert _GREW in check_codes(tmp_path, "--diff", base)


def test_a_draft_record_naming_the_baseline_does_not_clear_its_growth(tmp_path: Path) -> None:
    base = _grown_baseline_repo(tmp_path)
    _record(tmp_path, "upgrade-adds-findings", ".irminsul-baseline.json", status="draft")
    commit_all(tmp_path, "re-create the baseline, with an unaccepted record")

    assert _GREW in check_codes(tmp_path, "--diff", base)


def test_a_record_naming_the_configured_baseline_path_clears_its_growth(tmp_path: Path) -> None:
    _repo(tmp_path)
    config = (tmp_path / "irminsul.toml").read_text(encoding="utf-8")
    write(
        tmp_path, "irminsul.toml", config.replace("[paths]\n", '[paths]\nbaseline = "debt.json"\n')
    )
    _baseline(tmp_path, _DEBT, path="debt.json")
    base = commit_all(tmp_path, "adopted, baseline at debt.json")
    _baseline(tmp_path, _DEBT, _MORE_DEBT, path="debt.json")
    _record(tmp_path, "wrong-file", ".irminsul-baseline.json")
    commit_all(tmp_path, "grow it, naming the default path instead")
    assert _GREW in check_codes(tmp_path, "--diff", base)

    _record(tmp_path, "right-file", "debt.json")
    commit_all(tmp_path, "name the file the baseline really is")
    assert _GREW not in check_codes(tmp_path, "--diff", base)


def test_editing_an_implemented_rfc_is_an_error(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    write(root, "docs/rfcs/0001-x.md", _RFC)
    base = commit_all(root, "implemented rfc")
    write(root, "docs/rfcs/0001-x.md", _RFC.replace("Proposal.", "Better proposal."))
    commit_all(root, "edit")

    assert "diff-integrity/implemented-rfc-changed" in check_codes(root, "--diff", base)


def test_flipping_an_implemented_rfc_back_to_draft_is_still_a_change(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    write(root, "docs/rfcs/0001-x.md", _RFC)
    base = commit_all(root, "implemented rfc")
    write(root, "docs/rfcs/0001-x.md", _RFC.replace("implemented", "draft"))
    commit_all(root, "flip")

    assert "diff-integrity/implemented-rfc-changed" in check_codes(root, "--diff", base)


def test_deleting_an_implemented_rfc_is_an_error(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    write(root, "docs/rfcs/0001-x.md", _RFC)
    base = commit_all(root, "implemented rfc")
    (root / "docs" / "rfcs" / "0001-x.md").unlink()
    commit_all(root, "delete")

    assert "diff-integrity/implemented-rfc-removed" in check_codes(root, "--diff", base)


def test_renaming_and_editing_an_implemented_rfc_is_an_error(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    write(root, "docs/rfcs/0001-x.md", _RFC)
    base = commit_all(root, "implemented rfc")
    (root / "docs" / "rfcs" / "0001-x.md").unlink()
    write(
        root,
        "docs/rfcs/0001-y.md",
        _RFC.replace("id: 0001-x", "id: 0001-y").replace("Proposal.", "Other."),
    )
    commit_all(root, "rename and edit")

    assert "diff-integrity/implemented-rfc-changed" in check_codes(root, "--diff", base)


def test_a_pure_rename_of_an_implemented_rfc_passes(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    write(root, "docs/rfcs/0001-x.md", _RFC)
    base = commit_all(root, "implemented rfc")
    (root / "docs" / "rfcs" / "0001-x.md").unlink()
    write(root, "docs/rfcs/0001-y.md", _RFC.replace("id: 0001-x", "id: 0001-y"))
    commit_all(root, "rename")

    assert not [
        code for code in check_codes(root, "--diff", base) if code.startswith("diff-integrity/")
    ]


_RFC_CHANGED = "diff-integrity/implemented-rfc-changed"
_GOOD_ADR = "docs/decisions/0001-good-adr.md"
_BETTER_ADR = "docs/decisions/0001-better.md"
_LINKING_RFC = (
    "---\nid: 0001-x\ntitle: X\nstatus: stable\nsummary: A test doc.\n"
    f"rfc_state: implemented\nresolved_by: {_GOOD_ADR}\n---\n\n# X\n\n"
    "Settled by [the ADR](../decisions/0001-good-adr.md#decision) and `docs/decisions/"
    "0001-good-adr.md`,\nrecorded as `0001-good-adr`.\n\n"
    "## Proposal\n\nThe proposal is long enough that git still sees one file after a few of its\n"
    "references change: every sentence here stays exactly as it was written, so a rename\n"
    "of the file is detected as a rename and not as a deletion beside an addition.\n"
)


def _linked_repo(root: Path, rfc: str = _LINKING_RFC) -> str:
    """An implemented RFC that links an ADR by its relative path, its repo path and its id."""
    _repo(root)
    config = (root / "irminsul.toml").read_text(encoding="utf-8")
    write(root, "irminsul.toml", config.replace('["frontmatter"]', '["frontmatter", "links"]'))
    write(root, _GOOD_ADR, _ADR.replace("id: 0001-choice", "id: 0001-good-adr"))
    write(root, "docs/rfcs/0001-x.md", rfc)
    return commit_all(root, "an ADR and the implemented RFC that links it")


def _rename_the_adr(root: Path) -> None:
    git(root, "mv", _GOOD_ADR, _BETTER_ADR)
    write(root, _BETTER_ADR, _ADR.replace("id: 0001-choice", "id: 0001-better"))


def _retarget(text: str) -> str:
    return text.replace("0001-good-adr", "0001-better")


def test_retargeting_an_implemented_rfcs_links_to_a_renamed_doc_is_not_a_change(
    tmp_path: Path,
) -> None:
    """Renaming the ADR breaks the link in the RFC, and fixing the link must not trip the
    seal on the RFC, or the change has no way to pass."""
    base = _linked_repo(tmp_path)
    _rename_the_adr(tmp_path)
    write(tmp_path, "docs/rfcs/0001-x.md", _retarget(_LINKING_RFC))
    commit_all(tmp_path, "rename the ADR and retarget the RFC that links it")

    codes = check_codes(tmp_path, "--diff", base)

    assert _RFC_CHANGED not in codes
    assert "links/broken-link" not in codes


def test_the_rename_alone_leaves_the_link_broken_and_the_rfc_untouched(tmp_path: Path) -> None:
    base = _linked_repo(tmp_path)
    _rename_the_adr(tmp_path)
    commit_all(tmp_path, "rename the ADR")

    codes = check_codes(tmp_path, "--diff", base)

    assert "links/broken-link" in codes
    assert _RFC_CHANGED not in codes


def test_a_retarget_with_one_other_word_changed_is_still_a_change(tmp_path: Path) -> None:
    base = _linked_repo(tmp_path)
    _rename_the_adr(tmp_path)
    write(tmp_path, "docs/rfcs/0001-x.md", _retarget(_LINKING_RFC).replace("Settled", "Closed"))
    commit_all(tmp_path, "rename the ADR, retarget the RFC, and reword it")

    assert _RFC_CHANGED in check_codes(tmp_path, "--diff", base)


def test_retargeting_a_link_to_a_doc_nobody_renamed_is_a_change(tmp_path: Path) -> None:
    base = _linked_repo(tmp_path)
    write(tmp_path, "docs/decisions/0002-other.md", _ADR.replace("0001-choice", "0002-other"))
    write(
        tmp_path,
        "docs/rfcs/0001-x.md",
        _LINKING_RFC.replace("0001-good-adr", "0002-other"),
    )
    commit_all(tmp_path, "point the RFC at another ADR")

    assert _RFC_CHANGED in check_codes(tmp_path, "--diff", base)


def test_retargeting_to_a_doc_that_is_not_the_one_renamed_is_a_change(tmp_path: Path) -> None:
    base = _linked_repo(tmp_path)
    write(tmp_path, "docs/decisions/0002-other.md", _ADR.replace("0001-choice", "0002-other"))
    commit_all(tmp_path, "another ADR")
    _rename_the_adr(tmp_path)
    write(
        tmp_path,
        "docs/rfcs/0001-x.md",
        _LINKING_RFC.replace("0001-good-adr", "0002-other"),
    )
    commit_all(tmp_path, "rename the ADR, point the RFC at a different one")

    assert _RFC_CHANGED in check_codes(tmp_path, "--diff", base)


def test_a_renamed_implemented_rfc_may_retarget_its_links_too(tmp_path: Path) -> None:
    base = _linked_repo(tmp_path)
    _rename_the_adr(tmp_path)
    git(tmp_path, "mv", "docs/rfcs/0001-x.md", "docs/rfcs/0001-y.md")
    write(
        tmp_path,
        "docs/rfcs/0001-y.md",
        _retarget(_LINKING_RFC).replace("id: 0001-x", "id: 0001-y"),
    )
    commit_all(tmp_path, "rename both, retarget the RFC")

    codes = check_codes(tmp_path, "--diff", base)

    assert not [code for code in codes if code.startswith("diff-integrity/")]
    assert "links/broken-link" not in codes


def test_an_id_is_retargeted_only_as_a_whole_token(tmp_path: Path) -> None:
    rfc = _LINKING_RFC + "A longer id, `0001-good-adr-extended`, is another doc.\n"
    base = _linked_repo(tmp_path, rfc)
    _rename_the_adr(tmp_path)
    retargeted = _retarget(rfc).replace("0001-better-extended", "0001-good-adr-extended")
    write(tmp_path, "docs/rfcs/0001-x.md", retargeted)
    commit_all(tmp_path, "retarget the whole tokens")
    assert _RFC_CHANGED not in check_codes(tmp_path, "--diff", base)

    write(tmp_path, "docs/rfcs/0001-x.md", _retarget(rfc))
    commit_all(tmp_path, "retarget the longer id too")
    assert _RFC_CHANGED in check_codes(tmp_path, "--diff", base)


def test_a_link_retarget_passes_when_the_renamed_docs_id_is_also_a_prose_word(
    tmp_path: Path,
) -> None:
    """The id `choice` is an ordinary word in the RFC, so only the path is retargeted."""
    rfc = (
        "---\nid: 0001-x\ntitle: X\nstatus: stable\nsummary: A test doc.\n"
        "rfc_state: implemented\nresolved_by: docs/decisions/INDEX.md\n---\n\n# X\n\n"
        "The choice is recorded in [the ADR](../decisions/choice.md).\n"
    )
    _linked_repo(tmp_path, rfc)
    git(tmp_path, "mv", _GOOD_ADR, "docs/decisions/choice.md")
    write(tmp_path, "docs/decisions/choice.md", _ADR.replace("id: 0001-choice", "id: choice"))
    base = commit_all(tmp_path, "the ADR is called choice")
    git(tmp_path, "mv", "docs/decisions/choice.md", "docs/decisions/pick-one.md")
    write(tmp_path, "docs/decisions/pick-one.md", _ADR.replace("id: 0001-choice", "id: pick-one"))
    write(tmp_path, "docs/rfcs/0001-x.md", rfc.replace("choice.md", "pick-one.md"))
    commit_all(tmp_path, "rename the ADR and retarget the link")

    codes = check_codes(tmp_path, "--diff", base)

    assert _RFC_CHANGED not in codes
    assert "links/broken-link" not in codes


def test_retitling_an_accepted_decision_renames_its_file_and_passes(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    write(root, "docs/decisions/choice.md", _ADR)
    base = commit_all(root, "adr")
    git(root, "mv", "docs/decisions/choice.md", "docs/decisions/pick-a-lane.md")
    write(
        root,
        "docs/decisions/pick-a-lane.md",
        _ADR.replace("id: 0001-choice", "id: pick-a-lane")
        .replace("title: Choice", "title: Pick a lane")
        .replace("# Choice", "# Pick a lane"),
    )
    commit_all(root, "retitle")

    assert not [
        code for code in check_codes(root, "--diff", base) if code.startswith("diff-integrity/")
    ]


def test_a_renamed_decision_is_still_held_to_its_decision_section(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    write(root, "docs/decisions/choice.md", _ADR)
    base = commit_all(root, "adr")
    git(root, "mv", "docs/decisions/choice.md", "docs/decisions/pick-a-lane.md")
    write(
        root,
        "docs/decisions/pick-a-lane.md",
        _ADR.replace("id: 0001-choice", "id: pick-a-lane").replace("Use A.", "Use B."),
    )
    commit_all(root, "retitle and rewrite the decision")

    codes = check_codes(root, "--diff", base)
    assert "diff-integrity/decision-rewritten" in codes
    assert "diff-integrity/accepted-decision-removed" not in codes


def test_deleting_an_accepted_decision_is_an_error(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    write(root, "docs/decisions/0001-choice.md", _ADR)
    base = commit_all(root, "adr")
    (root / "docs" / "decisions" / "0001-choice.md").unlink()
    commit_all(root, "delete adr")

    assert "diff-integrity/accepted-decision-removed" in check_codes(root, "--diff", base)


def test_rewriting_an_accepted_decision_warns_but_other_sections_do_not(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    write(root, "docs/decisions/0001-choice.md", _ADR)
    base = commit_all(root, "adr")
    write(root, "docs/decisions/0001-choice.md", _ADR.replace("Fine.", "Fine enough."))
    middle = commit_all(root, "edit consequences")
    assert "diff-integrity/decision-rewritten" not in check_codes(root, "--diff", base)

    write(root, "docs/decisions/0001-choice.md", _ADR.replace("Use A.", "Use B."))
    commit_all(root, "rewrite decision")
    assert "diff-integrity/decision-rewritten" in check_codes(root, "--diff", middle)


def _owned_repo(root: Path) -> str:
    _repo(root)
    write_config(root, source_roots=["src"], enabled=["frontmatter"])
    write(root, "src/a.py", "A = 1\n")
    write(root, "src/b.py", "B = 1\n")
    write(
        root,
        "docs/components/big.md",
        "---\nid: big\ntitle: Big\nstatus: stable\nsummary: A test doc.\ndescribes:\n  - src/*.py\n---\n\n"
        "# Big\n\nThe parser lives in `a.py` and reads input.\n\nThe writer is separate.\n",
    )
    return commit_all(root, "base")


def test_a_file_moved_to_another_doc_is_a_hint_and_its_old_prose_is_listed(
    tmp_path: Path,
) -> None:
    base = _owned_repo(tmp_path)
    write(
        tmp_path,
        "docs/components/small.md",
        "---\nid: small\ntitle: Small\nstatus: stable\nsummary: A test doc.\ndescribes:\n  - src/a.py\n---\n\n# Small\n",
    )
    commit_all(tmp_path, "split")
    assert "diff-integrity/owner-changed" in check_codes(tmp_path, "--diff", base)

    result = runner.invoke(
        app, ["list", "review", "--base-ref", base, "--format", "json", "--path", str(tmp_path)]
    )
    moved = [i for i in json.loads(result.output)["items"] if "moved-file" in i["markers"]]
    assert [(i["path"], i["sentence"]) for i in moved] == [
        ("docs/components/big.md", "The parser lives in `a.py` and reads input.")
    ]


def test_an_unchanged_owner_is_not_reported(tmp_path: Path) -> None:
    base = _owned_repo(tmp_path)
    write(
        tmp_path, "docs/components/big.md", _read(tmp_path, "docs/components/big.md") + "\nMore.\n"
    )
    commit_all(tmp_path, "edit")
    assert "diff-integrity/owner-changed" not in check_codes(tmp_path, "--diff", base)


def _read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


_CONFIG = config_toml()


def _config_repo(root: Path) -> str:
    _repo(root)
    write(root, "irminsul.toml", _CONFIG + '[checks]\nenabled = ["frontmatter", "links"]\n')
    return commit_all(root, "base")


def _config_codes(root: Path, base: str) -> list[str]:
    weakening = {
        "diff-integrity/check-disabled",
        "diff-integrity/layer-rule-disabled",
        "diff-integrity/source-excluded",
        "diff-integrity/extra-doc-removed",
        "diff-integrity/setting-weakened",
        "diff-integrity/unreviewed-setting-change",
    }
    return [code for code in check_codes(root, "--diff", base) if code in weakening]


def test_removing_a_check_or_a_layer_rule_is_an_error(tmp_path: Path) -> None:
    base = _config_repo(tmp_path)
    write(
        tmp_path,
        "irminsul.toml",
        _CONFIG
        + '[checks]\nenabled = ["frontmatter"]\n[layers.components]\nrequire_tests = false\n',
    )
    commit_all(tmp_path, "weaken")
    assert _config_codes(tmp_path, base) == [
        "diff-integrity/check-disabled",
        "diff-integrity/layer-rule-disabled",
    ]


def test_removing_a_check_this_version_no_longer_has_is_still_reported(tmp_path: Path) -> None:
    """Deleting a check takes its name and settings out of the schema, so the base config
    names a check and a table this version does not know. The base is still its own record."""
    _repo(tmp_path)
    write(
        tmp_path,
        "irminsul.toml",
        _CONFIG
        + '[checks]\nenabled = ["frontmatter", "retired-check"]\n'
        + "[checks.retired_check]\nthreshold = 3\n",
    )
    base = commit_all(tmp_path, "base")
    write(tmp_path, "irminsul.toml", _CONFIG + '[checks]\nenabled = ["frontmatter"]\n')
    commit_all(tmp_path, "delete the check")

    codes = check_codes(tmp_path, "--diff", base)

    assert "diff-integrity/check-disabled" in codes
    assert "diff-integrity/base-config-unreadable" not in codes


def test_a_decision_record_naming_the_setting_allows_it(tmp_path: Path) -> None:
    base = _config_repo(tmp_path)
    write(
        tmp_path,
        "irminsul.toml",
        _CONFIG
        + '[checks]\nenabled = ["frontmatter"]\n[layers.components]\nrequire_tests = false\n',
    )
    write(
        tmp_path,
        "docs/decisions/drop-links.md",
        "---\nid: drop-links\ntitle: Drop links\nstatus: stable\nsummary: A test doc.\n---\n\n# Drop links\n\n"
        "## Decision\n\nDisable `links` and `layers.components.require_tests` for now.\n",
    )
    commit_all(tmp_path, "weaken with a record")
    assert _config_codes(tmp_path, base) == []


def test_excluding_source_or_dropping_a_guidance_file_is_a_hint(tmp_path: Path) -> None:
    base = _config_repo(tmp_path)
    write(
        tmp_path,
        "irminsul.toml",
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = []\n'
        'source_excludes = ["gen/**"]\nextra_docs = ["README.md"]\n'
        '[checks]\nenabled = ["frontmatter", "links"]\n',
    )
    commit_all(tmp_path, "narrow")
    assert sorted(_config_codes(tmp_path, base)) == [
        "diff-integrity/extra-doc-removed",
        "diff-integrity/extra-doc-removed",
        "diff-integrity/source-excluded",
    ]


def test_a_doc_moved_to_another_path_keeps_its_files(tmp_path: Path) -> None:
    base = _owned_repo(tmp_path)
    text = _read(tmp_path, "docs/components/big.md")
    (tmp_path / "docs/components/big.md").unlink()
    write(tmp_path, "docs/architecture/big.md", text)
    commit_all(tmp_path, "move")
    assert "diff-integrity/owner-changed" not in check_codes(tmp_path, "--diff", base)


def test_moving_the_rfcs_folder_in_config_does_not_unseal_a_record(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    write(root, "docs/rfcs/0001-x.md", _RFC)
    base = commit_all(root, "implemented rfc")
    config = _read(root, "irminsul.toml") + '[layers.rfcs]\npath = "proposals"\n'
    write(root, "irminsul.toml", config)
    write(root, "docs/rfcs/0001-x.md", _RFC.replace("Proposal.", "Better proposal."))
    commit_all(root, "move folder and edit")

    assert "diff-integrity/implemented-rfc-changed" in check_codes(root, "--diff", base)


def test_a_baseline_path_spelled_with_dotdot_still_counts(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    entry = {"check": "links", "path": "docs/a.md", "message": "broken", "fingerprint": "x"}
    write(root, ".irminsul-baseline.json", json.dumps({"version": 1, "findings": [entry]}))
    base = commit_all(root, "baseline")
    config = _read(root, "irminsul.toml").replace(
        "source_roots = []\n", 'source_roots = []\nbaseline = "docs/../.irminsul-baseline.json"\n'
    )
    write(root, "irminsul.toml", config)
    grown = [entry, {**entry, "message": "also broken"}]
    write(root, ".irminsul-baseline.json", json.dumps({"version": 1, "findings": grown}))
    commit_all(root, "grow baseline")

    assert "diff-integrity/baseline-grew" in check_codes(root, "--diff", base)


def test_a_baseline_cannot_hide_diff_integrity_findings(tmp_path: Path) -> None:
    root = _config_repo(tmp_path)
    write(tmp_path, "irminsul.toml", _CONFIG + '[checks]\nenabled = ["frontmatter"]\n')
    entry = {
        "check": "diff-integrity",
        "path": "irminsul.toml",
        "message": f"check 'links' was removed from checks.enabled since {root}",
    }
    write(tmp_path, ".irminsul-baseline.json", json.dumps({"version": 1, "findings": [entry]}))
    commit_all(tmp_path, "weaken and baseline it")

    assert "diff-integrity/check-disabled" in _config_codes(tmp_path, root)


def test_editing_an_existing_record_does_not_excuse_a_weakening(tmp_path: Path) -> None:
    _repo(tmp_path)
    write(tmp_path, "irminsul.toml", _CONFIG + '[checks]\nenabled = ["frontmatter", "links"]\n')
    write(tmp_path, "docs/decisions/0001-choice.md", _ADR)
    base = commit_all(tmp_path, "base")
    write(tmp_path, "irminsul.toml", _CONFIG + '[checks]\nenabled = ["frontmatter"]\n')
    write(tmp_path, "docs/decisions/0001-choice.md", _ADR.replace("Fine.", "Keep `links`."))
    commit_all(tmp_path, "weaken through an old record")

    assert "diff-integrity/check-disabled" in _config_codes(tmp_path, base)


def test_adopting_irminsul_is_not_a_weakening(tmp_path: Path) -> None:
    git_init(tmp_path)
    write(tmp_path, "README.md", "# r\n")
    base = commit_all(tmp_path, "before irminsul")
    _repo(tmp_path)
    commit_all(tmp_path, "adopt")

    assert _config_codes(tmp_path, base) == []


def test_an_ignore_comment_for_a_time_code_is_not_unused_under_diff(tmp_path: Path) -> None:
    from irminsul.checks.pipeline import finish

    write(tmp_path, "irminsul.toml", _CONFIG)
    write(
        tmp_path,
        "docs/guides/g.md",
        "---\nid: g\ntitle: G\nstatus: stable\nsummary: A test doc.\n---\n\n# G\n\n"
        "See https://example.invalid. "
        '<!-- irminsul:ignore external-links/unreachable reason="flaky host" -->\n',
    )
    graph = load_graph(tmp_path)
    assert finish([], graph, ran=["external-links"], diff=True) == []


_ANCHORED = (
    "---\nid: widget\ntitle: Widget\nstatus: stable\nsummary: A test doc.\n"
    "claims:\n  - id: widget-runs\n    state: implemented\n    kind: invariant\n"
    "    claim: The widget runs.\n    evidence:\n      - src/widget.py\n"
    "---\n\n# Widget\n\nIt runs.\n<!-- anchor: src/widget.py#run -->\n"
)


def _anchored_repo(root: Path) -> tuple[Path, str]:
    _repo(root)
    write(root, "src/widget.py", "def run():\n    return 1\n")
    write(root, "docs/components/widget.md", _ANCHORED)
    return root, commit_all(root, "anchored doc")


def test_removing_an_anchor_whose_code_survives_is_an_error(tmp_path: Path) -> None:
    root, base = _anchored_repo(tmp_path)
    write(
        root,
        "docs/components/widget.md",
        _ANCHORED.replace("\n<!-- anchor: src/widget.py#run -->", ""),
    )
    commit_all(root, "drop the anchor")

    assert "diff-integrity/anchor-removed" in check_codes(root, "--diff", base)


def test_removing_an_anchor_with_its_code_is_allowed(tmp_path: Path) -> None:
    root, base = _anchored_repo(tmp_path)
    write(
        root,
        "docs/components/widget.md",
        _ANCHORED.replace("\n<!-- anchor: src/widget.py#run -->", ""),
    )
    write(root, "src/widget.py", "def other():\n    return 2\n")
    commit_all(root, "drop the anchor and the code")

    assert "diff-integrity/anchor-removed" not in check_codes(root, "--diff", base)


def test_removing_a_claim_whose_evidence_survives_is_an_error(tmp_path: Path) -> None:
    root, base = _anchored_repo(tmp_path)
    stripped = (
        _ANCHORED[: _ANCHORED.index("claims:")] + _ANCHORED[_ANCHORED.index("---\n\n# Widget") :]
    )
    write(root, "docs/components/widget.md", stripped)
    commit_all(root, "drop the claim")

    assert "diff-integrity/claim-removed" in check_codes(root, "--diff", base)


def test_removing_a_claim_with_its_evidence_is_allowed(tmp_path: Path) -> None:
    root, base = _anchored_repo(tmp_path)
    stripped = (
        _ANCHORED[: _ANCHORED.index("claims:")] + _ANCHORED[_ANCHORED.index("---\n\n# Widget") :]
    )
    write(
        root,
        "docs/components/widget.md",
        stripped.replace("\n<!-- anchor: src/widget.py#run -->", ""),
    )
    (root / "src" / "widget.py").unlink()
    commit_all(root, "drop the claim and the code")

    assert "diff-integrity/claim-removed" not in check_codes(root, "--diff", base)


_INVENTORIED = (
    "---\nid: widget\ntitle: Widget\nstatus: stable\nsummary: A test doc.\n"
    "inventory:\n  - kind: cli\n    source: src/widget.py\n    explained_in: any\n"
    "---\n\n# Widget\n\nIt runs.\n"
)


def test_hollowing_out_an_inventory_contract_is_a_weakening(tmp_path: Path) -> None:
    """The removal seal keys on `(kind, source)`, so every field that makes the entry a
    contract could be dropped while the entry stayed — silencing live identities without
    tripping anything. Deleting one `explained_in:` line was enough."""
    root = _repo(tmp_path)
    write(root, "src/widget.py", "def run():\n    return 1\n")
    write(root, "docs/components/widget.md", _INVENTORIED)
    base = commit_all(root, "inventoried doc")

    write(root, "docs/components/widget.md", _INVENTORIED.replace("    explained_in: any\n", ""))
    commit_all(root, "drop the explained_in contract")

    assert "diff-integrity/inventory-weakened" in check_codes(root, "--diff", base)


def test_tightening_an_inventory_contract_is_silent(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    write(root, "src/widget.py", "def run():\n    return 1\n")
    write(root, "docs/components/widget.md", _INVENTORIED)
    base = commit_all(root, "inventoried doc")

    write(
        root,
        "docs/components/widget.md",
        _INVENTORIED.replace("explained_in: any", "explained_in: self").replace(
            "    explained_in: self\n", "    explained_in: self\n    complete: true\n"
        ),
    )
    commit_all(root, "ask for more")

    assert "diff-integrity/inventory-weakened" not in check_codes(root, "--diff", base)


def test_renaming_a_doc_does_not_hide_the_governance_it_dropped(tmp_path: Path) -> None:
    """`--find-renames` lists a renamed doc under its new path only, so reading the base
    side at that path found nothing and the doc was skipped — making a rename the
    cheapest way to drop every anchor and claim it held."""
    root, _ = _anchored_repo(tmp_path)
    # Enough shared prose that git scores the pair as a rename rather than add+delete.
    padded = _ANCHORED.replace("It runs.", "It runs. " + "Stable prose that survives. " * 40)
    write(root, "docs/components/widget.md", padded)
    base = commit_all(root, "pad the doc so the rename is detected")

    stripped = padded[: padded.index("claims:")] + padded[padded.index("---\n\n# Widget") :]
    git(root, "mv", "docs/components/widget.md", "docs/components/gadget.md")
    write(
        root,
        "docs/components/gadget.md",
        stripped.replace("id: widget", "id: gadget").replace(
            "\n<!-- anchor: src/widget.py#run -->", ""
        ),
    )
    commit_all(root, "rename and drop the claim and anchor")

    codes = check_codes(root, "--diff", base)
    assert "diff-integrity/claim-removed" in codes
    assert "diff-integrity/anchor-removed" in codes


def test_rewording_a_claim_is_not_removing_it(tmp_path: Path) -> None:
    """Fixing the wording of a claim is maintenance, and had no green route.

    Identity was the `(id, text)` pair, so any edit to the sentence read as a deletion
    of the claim and an addition of a different one.
    """
    root, base = _anchored_repo(tmp_path)
    write(
        root,
        "docs/components/widget.md",
        _ANCHORED.replace("The widget runs.", "The widget runs on demand."),
    )
    commit_all(root, "reword the claim")

    assert "diff-integrity/claim-removed" not in check_codes(root, "--diff", base)


def test_neutering_a_claim_in_place_is_reported(tmp_path: Path) -> None:
    """Keeping the id and emptying the sentence is how a claim stops saying anything.

    Reading a rewording as a deletion had no green route, but treating it as silent let
    `The widget runs` become `The widget exists` unreported.
    """
    root, base = _anchored_repo(tmp_path)
    write(
        root,
        "docs/components/widget.md",
        _ANCHORED.replace("The widget runs.", "The widget exists."),
    )
    commit_all(root, "empty the claim")

    codes = check_codes(root, "--diff", base)
    assert "diff-integrity/claim-reworded" in codes
    assert "diff-integrity/claim-removed" not in codes


def test_repointing_a_governing_claims_evidence_is_a_change_of_intent(tmp_path: Path) -> None:
    """The words of a contract are not the whole contract: aiming it at a file that
    trivially satisfies it leaves the sentence intact and governs nothing."""
    root, _ = _anchored_repo(tmp_path)
    governing = _ANCHORED.replace(
        "    kind: invariant\n", "    kind: invariant\n    relation: governs-evidence\n"
    )
    write(root, "docs/components/widget.md", governing)
    write(root, "src/trivial.py", "X = 1\n")
    base = commit_all(root, "make the claim govern")

    write(
        root,
        "docs/components/widget.md",
        governing.replace("      - src/widget.py", "      - src/trivial.py"),
    )
    commit_all(root, "aim it somewhere harmless")

    assert "diff-integrity/governing-claim-changed" in check_codes(root, "--diff", base)


def test_renaming_a_claim_id_is_still_a_removal(tmp_path: Path) -> None:
    root, base = _anchored_repo(tmp_path)
    write(root, "docs/components/widget.md", _ANCHORED.replace("widget-runs", "widget-executes"))
    commit_all(root, "rename the claim id")

    assert "diff-integrity/claim-removed" in check_codes(root, "--diff", base)


def test_a_record_naming_the_claim_excuses_removing_it(tmp_path: Path) -> None:
    root, base = _anchored_repo(tmp_path)
    stripped = (
        _ANCHORED[: _ANCHORED.index("claims:")] + _ANCHORED[_ANCHORED.index("---\n\n# Widget") :]
    )
    write(root, "docs/components/widget.md", stripped)
    write(
        root,
        "docs/decisions/widget-claim-retired.md",
        "---\nid: widget-claim-retired\ntitle: Widget claim retired\nstatus: stable\nsummary: A test doc.\n---\n\n"
        "# Widget claim retired\n\n## Decision\n\nThe claim `widget-runs` is retired.\n",
    )
    commit_all(root, "drop the claim with a record")

    assert "diff-integrity/claim-removed" not in check_codes(root, "--diff", base)


def test_a_draft_record_naming_the_setting_does_not_allow_it(tmp_path: Path) -> None:
    """A nine-line draft whose body was just the check name used to unlock it."""
    base = _config_repo(tmp_path)
    write(tmp_path, "irminsul.toml", _CONFIG + '[checks]\nenabled = ["frontmatter"]\n')
    write(
        tmp_path,
        "docs/decisions/scratch.md",
        "---\nid: scratch\ntitle: Scratch\nstatus: draft\nsummary: A test doc.\n---\n\n# Scratch\n\n`links`\n",
    )
    commit_all(tmp_path, "weaken with a scratch file")

    assert "diff-integrity/check-disabled" in _config_codes(tmp_path, base)


def test_a_record_naming_the_setting_outside_its_decision_does_not_allow_it(
    tmp_path: Path,
) -> None:
    base = _config_repo(tmp_path)
    write(tmp_path, "irminsul.toml", _CONFIG + '[checks]\nenabled = ["frontmatter"]\n')
    write(
        tmp_path,
        "docs/decisions/aside.md",
        "---\nid: aside\ntitle: Aside\nstatus: stable\nsummary: A test doc.\n---\n\n# Aside\n\n"
        "## Context\n\nWe once used `links`.\n\n## Decision\n\nSomething unrelated.\n",
    )
    commit_all(tmp_path, "mention the check in passing")

    assert "diff-integrity/check-disabled" in _config_codes(tmp_path, base)


def test_repointing_docs_root_is_an_error(tmp_path: Path) -> None:
    """A fresh folder with one stub INDEX used to give 0 findings and exit 0."""
    base = _config_repo(tmp_path)
    write(tmp_path, "irminsul.toml", _CONFIG.replace('docs_root = "docs"', 'docs_root = "notes"'))
    write(
        tmp_path,
        "notes/decisions/INDEX.md",
        "---\nid: decisions\ntitle: D\nstatus: stable\nsummary: A test doc.\n---\n\n# D\n",
    )
    commit_all(tmp_path, "repoint docs_root")

    assert "diff-integrity/check-disabled" in _config_codes(tmp_path, base)


def test_moving_a_layer_folder_is_an_error(tmp_path: Path) -> None:
    base = _config_repo(tmp_path)
    write(
        tmp_path,
        "irminsul.toml",
        _CONFIG + '[layers.decisions]\npath = "adr"\n',
    )
    commit_all(tmp_path, "move the decisions folder")

    assert "diff-integrity/layer-rule-disabled" in _config_codes(tmp_path, base)


_GOVERNING = (
    "---\nid: widget\ntitle: Widget\nstatus: stable\nsummary: A test doc.\n"
    "claims:\n  - id: widget-stateless\n    state: implemented\n    kind: invariant\n"
    "    relation: governs-evidence\n"
    "    claim: The widget never persists state between calls.\n"
    "    evidence:\n      - src/widget.py\n"
    "---\n\n# Widget\n\nIt runs.\n"
)


def _governing_repo(root: Path) -> str:
    _repo(root)
    write(root, "src/widget.py", "def run():\n    return 1\n")
    write(root, "docs/components/widget.md", _GOVERNING)
    return commit_all(root, "governing claim")


def test_rewording_a_governing_claim_is_an_error(tmp_path: Path) -> None:
    """Editing the contract to match the code it forbids must not pass quietly."""
    base = _governing_repo(tmp_path)
    write(
        tmp_path,
        "docs/components/widget.md",
        _GOVERNING.replace("never persists state", "may persist state"),
    )
    commit_all(tmp_path, "reword the contract")

    assert "diff-integrity/governing-claim-changed" in check_codes(tmp_path, "--diff", base)


def test_downgrading_the_relation_is_an_error(tmp_path: Path) -> None:
    """Protection is read from the base, so a change cannot lower its own."""
    base = _governing_repo(tmp_path)
    write(
        tmp_path,
        "docs/components/widget.md",
        _GOVERNING.replace("relation: governs-evidence", "relation: follows-evidence").replace(
            "never persists state", "may persist state"
        ),
    )
    commit_all(tmp_path, "downgrade then reword")

    assert "diff-integrity/governing-claim-changed" in check_codes(tmp_path, "--diff", base)


def test_a_decision_record_authorizes_the_change(tmp_path: Path) -> None:
    base = _governing_repo(tmp_path)
    write(
        tmp_path,
        "docs/components/widget.md",
        _GOVERNING.replace("never persists state", "may persist state"),
    )
    write(
        tmp_path,
        "docs/decisions/allow-widget-state.md",
        "---\nid: allow-widget-state\ntitle: Allow widget state\nstatus: stable\nsummary: A test doc.\n---\n\n"
        "# Allow widget state\n\n## Decision\n\nThe claim `widget-stateless` is retired.\n",
    )
    commit_all(tmp_path, "authorize the intent change")

    assert "diff-integrity/governing-claim-changed" not in check_codes(tmp_path, "--diff", base)


def test_an_untouched_governing_claim_is_silent(tmp_path: Path) -> None:
    base = _governing_repo(tmp_path)
    write(tmp_path, "src/widget.py", "def run():\n    return 2\n")
    commit_all(tmp_path, "change the code only")

    assert "diff-integrity/governing-claim-changed" not in check_codes(tmp_path, "--diff", base)


def _without_claims(text: str) -> str:
    return text[: text.index("claims:")] + text[text.index("---\n\n# Widget") :]


def test_removing_a_governing_claim_with_its_evidence_is_an_error(tmp_path: Path) -> None:
    """Deleting the code releases a claim that only described it, but a contract does not
    end because the code it governed was deleted alongside it."""
    base = _governing_repo(tmp_path)
    write(tmp_path, "docs/components/widget.md", _without_claims(_GOVERNING))
    (tmp_path / "src" / "widget.py").unlink()
    commit_all(tmp_path, "drop the contract and the code together")

    assert "diff-integrity/governing-claim-removed" in check_codes(tmp_path, "--diff", base)


def test_removing_a_governing_claim_whose_evidence_survives_is_an_error(tmp_path: Path) -> None:
    base = _governing_repo(tmp_path)
    write(tmp_path, "docs/components/widget.md", _without_claims(_GOVERNING))
    commit_all(tmp_path, "drop the contract")

    assert "diff-integrity/governing-claim-removed" in check_codes(tmp_path, "--diff", base)


def test_renaming_a_governing_claim_while_deleting_its_evidence_is_an_error(
    tmp_path: Path,
) -> None:
    base = _governing_repo(tmp_path)
    write(
        tmp_path,
        "docs/components/widget.md",
        _GOVERNING.replace("widget-stateless", "widget-stateful").replace(
            "      - src/widget.py\n", "      - src/other.py\n"
        ),
    )
    write(tmp_path, "src/other.py", "Y = 1\n")
    (tmp_path / "src" / "widget.py").unlink()
    commit_all(tmp_path, "rename the contract away")

    assert "diff-integrity/governing-claim-removed" in check_codes(tmp_path, "--diff", base)


def test_deleting_the_doc_and_code_of_a_governing_claim_is_an_error(tmp_path: Path) -> None:
    base = _governing_repo(tmp_path)
    (tmp_path / "docs" / "components" / "widget.md").unlink()
    (tmp_path / "src" / "widget.py").unlink()
    commit_all(tmp_path, "delete the doc and the code")

    assert "diff-integrity/governing-claim-removed" in check_codes(tmp_path, "--diff", base)


def test_downgrading_before_deleting_a_governing_claim_is_still_an_error(tmp_path: Path) -> None:
    """Protection is read from the base, so lowering it in an earlier commit of the same
    change does not release the claim in a later one."""
    base = _governing_repo(tmp_path)
    write(
        tmp_path,
        "docs/components/widget.md",
        _GOVERNING.replace("relation: governs-evidence", "relation: follows-evidence"),
    )
    commit_all(tmp_path, "downgrade first")
    write(tmp_path, "docs/components/widget.md", _without_claims(_GOVERNING))
    (tmp_path / "src" / "widget.py").unlink()
    commit_all(tmp_path, "then delete it with its code")

    assert "diff-integrity/governing-claim-removed" in check_codes(tmp_path, "--diff", base)


def test_a_decision_record_ends_a_governing_claim_with_its_code(tmp_path: Path) -> None:
    base = _governing_repo(tmp_path)
    write(tmp_path, "docs/components/widget.md", _without_claims(_GOVERNING))
    (tmp_path / "src" / "widget.py").unlink()
    write(
        tmp_path,
        "docs/decisions/retire-the-widget.md",
        "---\nid: retire-the-widget\ntitle: Retire the widget\nstatus: stable\nsummary: A test doc.\n---\n\n"
        "# Retire the widget\n\n## Decision\n\nThe widget is removed, and `widget-stateless` "
        "ends with it.\n",
    )
    commit_all(tmp_path, "retire the widget by decision")

    codes = check_codes(tmp_path, "--diff", base)
    assert "diff-integrity/governing-claim-removed" not in codes
    assert "diff-integrity/claim-removed" not in codes


def test_moving_a_governing_claim_to_another_doc_is_not_a_removal(tmp_path: Path) -> None:
    base = _governing_repo(tmp_path)
    write(tmp_path, "docs/components/widget.md", _without_claims(_GOVERNING))
    write(
        tmp_path,
        "docs/components/gadget.md",
        _GOVERNING.replace("id: widget\ntitle: Widget", "id: gadget\ntitle: Gadget").replace(
            "# Widget", "# Gadget"
        ),
    )
    commit_all(tmp_path, "move the contract to the doc that now owns it")

    assert "diff-integrity/governing-claim-removed" not in check_codes(tmp_path, "--diff", base)


_GATE_FILE = "diff-integrity/gate-file-changed"
_DOCS_PR = ".github/workflows/docs-pr.yml"
_NIGHTLY = ".github/workflows/docs-nightly.yml"
_GATE_STEP = 'irminsul check --diff "origin/main"'


def _gate(*steps: str) -> str:
    return (
        "name: docs\n\non: pull_request\n\njobs:\n  check:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - uses: actions/checkout@v4\n        with:\n"
        "          fetch-depth: 0\n" + "".join(f"      - run: {step}\n" for step in steps)
    )


def _gated_repo(root: Path, *paths: str) -> str:
    _repo(root)
    for path in paths or (_DOCS_PR,):
        write(root, path, _gate(_GATE_STEP))
    return commit_all(root, "gated workflow")


def _record(root: Path, slug: str, *named: str, status: str = "stable") -> None:
    spans = " and ".join(f"`{path}`" for path in named)
    write(
        root,
        f"docs/decisions/{slug}.md",
        f"---\nid: {slug}\ntitle: {slug}\nstatus: {status}\nsummary: A test record.\n---\n\n"
        f"# {slug}\n\n"
        f"## Decision\n\nEdit {spans}: the gate asks more of a change, not less.\n",
    )


def _sealed(root: Path, base: str) -> tuple[int, list[dict[str, str]]]:
    result = runner.invoke(app, ["check", "--diff", base, "--format", "json", "--path", str(root)])
    findings = json.loads(result.output)["findings"]
    return result.exit_code, [f for f in findings if f["code"] == _GATE_FILE]


def _sealed_paths(root: Path, base: str) -> list[str]:
    return [f["path"] for f in _sealed(root, base)[1]]


def test_discarding_the_gates_exit_status_is_reported(tmp_path: Path) -> None:
    """`|| echo` discards the exit status as surely as `|| true` does, and the seal reports
    the file without reading what the edit means."""
    base = _gated_repo(tmp_path)
    write(tmp_path, _DOCS_PR, _gate(_GATE_STEP + " || echo docs drift"))
    commit_all(tmp_path, "let the gate fail quietly")

    code, sealed = _sealed(tmp_path, base)

    assert code == 1
    assert [(f["path"], f["severity"], f["class"]) for f in sealed] == [
        (_DOCS_PR, "error", "certain")
    ]


@pytest.mark.parametrize(
    "edit",
    [
        lambda text: "# The docs gate.\n" + text,
        lambda text: text.replace("jobs:\n", "jobs: [\n"),
    ],
    ids=["comment-only", "stops-parsing"],
)
def test_any_edit_to_a_gate_workflow_is_reported(
    tmp_path: Path, edit: Callable[[str], str]
) -> None:
    """The seal reads text, not YAML, so neither a harmless comment nor a file GitHub can
    no longer run is told apart from any other edit."""
    base = _gated_repo(tmp_path)
    write(tmp_path, _DOCS_PR, edit(_gate(_GATE_STEP)))
    commit_all(tmp_path, "edit the gate")

    assert _sealed_paths(tmp_path, base) == [_DOCS_PR]


def test_a_workflow_that_never_mentions_irminsul_is_not_sealed(tmp_path: Path) -> None:
    _repo(tmp_path)
    write(tmp_path, _DOCS_PR, _gate(_GATE_STEP))
    write(tmp_path, ".github/workflows/lint.yml", _gate("ruff check ."))
    base = commit_all(tmp_path, "a gate and a lint workflow")
    write(tmp_path, ".github/workflows/lint.yml", _gate("ruff check .", "ruff format --check ."))
    commit_all(tmp_path, "lint the formatting too")

    assert _sealed_paths(tmp_path, base) == []


def test_a_workflow_that_stops_mentioning_irminsul_is_still_sealed(tmp_path: Path) -> None:
    """Mentioned at the base is enough: deleting the gate step is the edit the seal exists
    to stop, and it leaves no trace of the tool in the file."""
    base = _gated_repo(tmp_path)
    write(tmp_path, _DOCS_PR, _gate("echo docs"))
    commit_all(tmp_path, "drop the gate step")

    assert _sealed_paths(tmp_path, base) == [_DOCS_PR]


@pytest.mark.parametrize(("status", "cleared"), [("stable", True), ("draft", False)])
def test_a_decision_record_naming_the_file_clears_it(
    tmp_path: Path, status: str, cleared: bool
) -> None:
    base = _gated_repo(tmp_path)
    write(tmp_path, _DOCS_PR, _gate(_GATE_STEP + " --fail-on hint"))
    _record(tmp_path, "gate-on-hints", _DOCS_PR, status=status)
    commit_all(tmp_path, "fail on hints, and say why")

    code, sealed = _sealed(tmp_path, base)

    assert (code, sealed == []) == ((0, True) if cleared else (1, False))


def test_a_record_clears_only_the_file_it_names(tmp_path: Path) -> None:
    base = _gated_repo(tmp_path, _DOCS_PR, _NIGHTLY)
    for path in (_DOCS_PR, _NIGHTLY):
        write(tmp_path, path, _gate(_GATE_STEP, "echo done"))
    _record(tmp_path, "announce-the-gate", _DOCS_PR)
    commit_all(tmp_path, "edit both gates, explain one")

    assert _sealed_paths(tmp_path, base) == [_NIGHTLY]


def test_an_adopting_change_is_not_sealed(tmp_path: Path) -> None:
    """A base with no config has no gate to weaken, as with the first baseline."""
    git_init(tmp_path)
    write(tmp_path, "README.md", "# r\n")
    base = commit_all(tmp_path, "before irminsul")
    _repo(tmp_path)
    write(tmp_path, _DOCS_PR, _gate(_GATE_STEP))
    commit_all(tmp_path, "adopt irminsul with its gate")

    assert _sealed_paths(tmp_path, base) == []


def test_a_base_that_dropped_its_config_but_kept_its_baseline_is_sealed(tmp_path: Path) -> None:
    """Deleting the config in one change must not unseal the gate for the next."""
    git_init(tmp_path)
    _baseline(tmp_path)
    base = commit_all(tmp_path, "config deleted, baseline left")
    _repo(tmp_path)
    write(tmp_path, _DOCS_PR, _gate(_GATE_STEP))
    commit_all(tmp_path, "config back, gate edited")

    assert _sealed_paths(tmp_path, base) == [_DOCS_PR]


def test_adding_a_gate_workflow_after_adoption_is_reported(tmp_path: Path) -> None:
    _repo(tmp_path)
    base = commit_all(tmp_path, "adopted, no gate yet")
    write(tmp_path, _DOCS_PR, _gate(_GATE_STEP))
    commit_all(tmp_path, "add the gate")

    assert _sealed_paths(tmp_path, base) == [_DOCS_PR]


def test_a_deleted_gate_file_is_named_by_the_path_it_had(tmp_path: Path) -> None:
    base = _gated_repo(tmp_path)
    (tmp_path / _DOCS_PR).unlink()
    commit_all(tmp_path, "delete the gate")

    _, sealed = _sealed(tmp_path, base)

    assert [f["path"] for f in sealed] == [_DOCS_PR] and "deleted" in sealed[0]["message"]


@pytest.mark.parametrize("moved_to", [".github/workflows/gate.yml", "ci/docs-pr.yml.disabled"])
def test_a_renamed_gate_file_is_reported_once_by_its_new_path(
    tmp_path: Path, moved_to: str
) -> None:
    """Moving a workflow out of the folder GitHub reads switches it off, so the new path
    being outside that folder does not unseal it."""
    base = _gated_repo(tmp_path)
    (tmp_path / moved_to).parent.mkdir(parents=True, exist_ok=True)
    git(tmp_path, "mv", _DOCS_PR, moved_to)
    commit_all(tmp_path, "move the gate")

    _, sealed = _sealed(tmp_path, base)

    assert [f["path"] for f in sealed] == [moved_to] and _DOCS_PR in sealed[0]["message"]


@pytest.mark.parametrize("action", ["action.yml", ".github/actions/docs-gate/action.yaml"])
def test_an_action_definition_that_runs_irminsul_is_sealed(tmp_path: Path, action: str) -> None:
    definition = (
        "name: docs gate\nruns:\n  using: composite\n  steps:\n"
        f"    - shell: bash\n      run: {_GATE_STEP}\n"
    )
    _repo(tmp_path)
    write(tmp_path, action, definition)
    base = commit_all(tmp_path, "a local action that gates")
    write(tmp_path, action, definition.replace(_GATE_STEP, "echo skipped"))
    commit_all(tmp_path, "stop gating inside the action")

    assert _sealed_paths(tmp_path, base) == [action]


@pytest.mark.parametrize(
    "code",
    [
        "diff-integrity/gate-weakened",
        "diff-integrity/filter-unreadable",
        "diff-integrity/filter-not-compared",
    ],
)
def test_the_scoring_codes_are_unknown(code: str) -> None:
    result = runner.invoke(app, ["explain", code])

    assert result.exit_code == 2 and f"unknown code '{code}'" in result.output


def test_a_freshly_initialized_repo_seals_its_scaffolded_gate(tmp_path: Path) -> None:
    """The scaffold gates through the published Action, so the file names the tool in a
    `uses:` line rather than in a command."""
    root = tmp_path / "adopter"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("X = 1\n", encoding="utf-8")
    git_init(root)
    result = runner.invoke(
        app, ["init", "--no-interactive", "--language", "python", "--path", str(root)]
    )
    assert result.exit_code == 0, result.output
    base = commit_all(root, "adopt irminsul")
    workflow = root / _DOCS_PR
    workflow.write_text(workflow.read_text(encoding="utf-8") + "# edited\n", encoding="utf-8")
    commit_all(root, "edit the scaffolded gate")

    assert _sealed_paths(root, base) == [_DOCS_PR]


def test_linking_unchanged_words_of_an_accepted_decision_is_not_a_rewrite(tmp_path: Path) -> None:
    """Pointing a phrase at the record that now governs it changes no word of the decision,
    so it is not the in-place rewrite the seal exists to catch."""
    root = _repo(tmp_path)
    decided = _ADR.replace("Use A.", "Use A with `--strict` on.")
    write(root, "docs/decisions/0001-choice.md", decided)
    base = commit_all(root, "adr")
    write(
        root,
        "docs/decisions/0001-choice.md",
        decided.replace("`--strict`", "[`--strict`](trim-the-surface.md)"),
    )
    commit_all(root, "link the flag to the record that retired it")

    assert "diff-integrity/decision-rewritten" not in check_codes(root, "--diff", base)


def test_a_word_changed_inside_a_new_link_is_still_a_rewrite(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    decided = _ADR.replace("Use A.", "Use A with `--strict` on.")
    write(root, "docs/decisions/0001-choice.md", decided)
    base = commit_all(root, "adr")
    write(
        root,
        "docs/decisions/0001-choice.md",
        decided.replace("`--strict` on", "[`--fail-on`](trim-the-surface.md) on"),
    )
    commit_all(root, "change the flag while linking it")

    assert "diff-integrity/decision-rewritten" in check_codes(root, "--diff", base)


def test_linking_one_flag_of_a_longer_code_span_is_not_a_rewrite(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    decided = _ADR.replace("Use A.", "Run `context --before-edit <path...>` first.")
    write(root, "docs/decisions/0001-choice.md", decided)
    base = commit_all(root, "adr")
    write(
        root,
        "docs/decisions/0001-choice.md",
        decided.replace(
            "`context --before-edit <path...>`",
            "`context` [`--before-edit`](trim-the-surface.md) `<path...>`",
        ),
    )
    commit_all(root, "link the flag")

    assert "diff-integrity/decision-rewritten" not in check_codes(root, "--diff", base)


_PINNED_ADR = _ADR.replace("Use A.", "Use A.\n<!-- anchor: src/a.py#run @sha256:000000000000 -->")


def test_re_pinning_an_anchor_of_an_accepted_decision_is_not_a_rewrite(tmp_path: Path) -> None:
    """A pin says which version of the code was re-read and changes no word of the decision;
    reading it as a rewrite would leave the anchor drifted for good."""
    root = _repo(tmp_path)
    write(root, "docs/decisions/0001-choice.md", _PINNED_ADR)
    base = commit_all(root, "adr")
    write(root, "docs/decisions/0001-choice.md", _PINNED_ADR.replace("0" * 12, "1" * 12))
    commit_all(root, "re-pin")

    assert "diff-integrity/decision-rewritten" not in check_codes(root, "--diff", base)


def test_retargeting_an_anchor_of_an_accepted_decision_is_a_rewrite(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    write(root, "docs/decisions/0001-choice.md", _PINNED_ADR)
    base = commit_all(root, "adr")
    write(root, "docs/decisions/0001-choice.md", _PINNED_ADR.replace("#run", "#walk"))
    commit_all(root, "point the anchor elsewhere")

    assert "diff-integrity/decision-rewritten" in check_codes(root, "--diff", base)


def _suggestion(root: Path, base: str, code: str) -> str:
    findings = [f for f in check_findings(root, "--diff", base) if f["code"] == code]
    assert len(findings) == 1
    return findings[0]["suggestion"]


def _offers_keeping_the_code_or_superseding(suggestion: str) -> bool:
    return (
        "keep the code it names" in suggestion
        and "still agree as accepted" in suggestion
        and "new ADR that supersedes it" in suggestion
        and "wording does not change either way" in suggestion
    )


def test_a_rewritten_decision_is_offered_keeping_the_code_as_well_as_superseding(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    write(root, "docs/decisions/0001-choice.md", _ADR)
    base = commit_all(root, "adr", when=_AT)
    write(root, "docs/decisions/0001-choice.md", _ADR.replace("Use A.", "Use B."))
    commit_all(root, "rewrite decision", when=_AT)

    suggestion = _suggestion(root, base, "diff-integrity/decision-rewritten")

    assert _offers_keeping_the_code_or_superseding(suggestion), suggestion


def test_a_rewritten_and_renamed_decision_is_offered_the_same_two_ways(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    write(root, "docs/decisions/choice.md", _ADR)
    base = commit_all(root, "adr", when=_AT)
    git(root, "mv", "docs/decisions/choice.md", "docs/decisions/pick-a-lane.md")
    write(
        root,
        "docs/decisions/pick-a-lane.md",
        _ADR.replace("id: 0001-choice", "id: pick-a-lane").replace("Use A.", "Use B."),
    )
    commit_all(root, "retitle and rewrite the decision", when=_AT)

    suggestion = _suggestion(root, base, "diff-integrity/decision-rewritten")

    assert _offers_keeping_the_code_or_superseding(suggestion), suggestion


def test_explain_decision_rewritten_offers_the_same_two_ways() -> None:
    result = runner.invoke(app, ["explain", "diff-integrity/decision-rewritten"])

    assert result.exit_code == 0, result.output
    assert "Restore its wording and keep the code it names" in result.output
    assert "supersedes this one" in result.output
