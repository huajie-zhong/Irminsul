"""Tests for the diff-integrity pass that runs under `check --diff`."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from irminsul.cli import app

runner = CliRunner()

_RFC = (
    "---\nid: 0001-x\ntitle: X\nstatus: stable\n"
    "rfc_state: implemented\nresolved_by: docs/decisions/INDEX.md\n---\n\n# X\n\nProposal.\n"
)
_ADR = (
    "---\nid: 0001-choice\ntitle: Choice\nstatus: stable\n---\n\n# Choice\n\n"
    "## Status\n\nAccepted.\n\n## Decision\n\nUse A.\n\n## Consequences\n\nFine.\n"
)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _commit(root: Path, message: str) -> str:
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-qm", message)
    return _git(root, "rev-parse", "HEAD")


def _repo(root: Path) -> Path:
    _git(root, "init", "-q")
    _write(
        root,
        "irminsul.toml",
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = []\n'
        '[checks]\nenabled = ["frontmatter"]\n',
    )
    _write(
        root,
        "docs/decisions/INDEX.md",
        "---\nid: decisions\ntitle: D\nstatus: stable\n---\n\n# D\n",
    )
    return root


def _codes(root: Path, base: str) -> list[str]:
    result = runner.invoke(app, ["check", "--diff", base, "--format", "json", "--path", str(root)])
    return sorted(f["code"] for f in json.loads(result.output)["findings"])


def test_a_growing_baseline_is_an_error(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    entry = {"check": "links", "path": "docs/a.md", "message": "broken", "fingerprint": "x"}
    _write(root, ".irminsul-baseline.json", json.dumps({"version": 1, "findings": [entry]}))
    base = _commit(root, "baseline")
    grown = [entry, {**entry, "message": "also broken"}]
    _write(root, ".irminsul-baseline.json", json.dumps({"version": 1, "findings": grown}))
    _commit(root, "grow baseline")

    assert "diff-integrity/baseline-grew" in _codes(root, base)


_DEBT = {"check": "links", "path": "docs/a.md", "message": "broken", "fingerprint": "x"}
_MORE_DEBT = {**_DEBT, "message": "also broken"}
_GREW = "diff-integrity/baseline-grew"


def _baseline(root: Path, *entries: dict[str, str], path: str = ".irminsul-baseline.json") -> None:
    _write(root, path, json.dumps({"version": 1, "findings": list(entries)}))


def _before_irminsul(root: Path) -> str:
    _git(root, "init", "-q")
    _write(root, "README.md", "# r\n")
    return _commit(root, "before irminsul")


def test_adopting_irminsul_with_a_baseline_is_not_growth(tmp_path: Path) -> None:
    """A repository with no config and no baseline has no ratchet to hold, so the baseline
    its adopting change records is a first one rather than a bigger one."""
    base = _before_irminsul(tmp_path)
    _repo(tmp_path)
    _baseline(tmp_path, _DEBT, _MORE_DEBT)
    _commit(tmp_path, "adopt irminsul, recording the debt already there")

    assert _GREW not in _codes(tmp_path, base)


def test_the_change_after_adoption_may_shrink_the_baseline(tmp_path: Path) -> None:
    _before_irminsul(tmp_path)
    _repo(tmp_path)
    _baseline(tmp_path, _DEBT, _MORE_DEBT)
    adopted = _commit(tmp_path, "adopt")
    _baseline(tmp_path, _DEBT)
    _commit(tmp_path, "pay some debt down")

    assert _GREW not in _codes(tmp_path, adopted)


def test_the_change_after_adoption_may_not_grow_the_baseline(tmp_path: Path) -> None:
    _before_irminsul(tmp_path)
    _repo(tmp_path)
    _baseline(tmp_path, _DEBT)
    adopted = _commit(tmp_path, "adopt")
    _baseline(tmp_path, _DEBT, _MORE_DEBT)
    _commit(tmp_path, "record new debt")

    assert _GREW in _codes(tmp_path, adopted)


def test_recreating_the_config_in_one_change_does_not_reset_the_ratchet(tmp_path: Path) -> None:
    _repo(tmp_path)
    _baseline(tmp_path, _DEBT)
    base = _commit(tmp_path, "adopted")
    config = (tmp_path / "irminsul.toml").read_text(encoding="utf-8")
    _write(tmp_path, "irminsul.toml", config.replace('"r"', '"renamed"'))
    _baseline(tmp_path, _DEBT, _MORE_DEBT)
    _commit(tmp_path, "rewrite the config and the baseline together")

    assert _GREW in _codes(tmp_path, base)


def test_dropping_the_config_first_does_not_reset_the_ratchet(tmp_path: Path) -> None:
    """A run with no config still honours the baseline at its default path, so a base that
    holds one is an adopter however its config came to be missing."""
    _repo(tmp_path)
    _baseline(tmp_path, _DEBT)
    _commit(tmp_path, "adopted")
    config = (tmp_path / "irminsul.toml").read_text(encoding="utf-8")
    (tmp_path / "irminsul.toml").unlink()
    without_config = _commit(tmp_path, "drop the config, keep the baseline")
    _write(tmp_path, "irminsul.toml", config)
    _baseline(tmp_path, _DEBT, _MORE_DEBT)
    _commit(tmp_path, "bring the config back with a bigger baseline")

    assert _GREW in _codes(tmp_path, without_config)


def test_pointing_a_returning_config_at_a_new_baseline_file_is_still_growth(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    _baseline(tmp_path, _DEBT)
    _commit(tmp_path, "adopted")
    config = (tmp_path / "irminsul.toml").read_text(encoding="utf-8")
    (tmp_path / "irminsul.toml").unlink()
    without_config = _commit(tmp_path, "drop the config, keep the baseline")
    _write(
        tmp_path, "irminsul.toml", config.replace("[paths]\n", '[paths]\nbaseline = "debt.json"\n')
    )
    _baseline(tmp_path, _DEBT, _MORE_DEBT, path="debt.json")
    _commit(tmp_path, "bring the config back, pointed at a new baseline file")

    assert _GREW in _codes(tmp_path, without_config)


def test_recreating_a_deleted_baseline_is_growth(tmp_path: Path) -> None:
    """An adopter's first baseline is created once; one recorded later hides findings the
    gate was already reporting."""
    _repo(tmp_path)
    base = _commit(tmp_path, "adopted with no baseline")
    _baseline(tmp_path, _DEBT)
    _commit(tmp_path, "record debt after the fact")

    assert _GREW in _codes(tmp_path, base)


def test_editing_an_implemented_rfc_is_an_error(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "docs/rfcs/0001-x.md", _RFC)
    base = _commit(root, "implemented rfc")
    _write(root, "docs/rfcs/0001-x.md", _RFC.replace("Proposal.", "Better proposal."))
    _commit(root, "edit")

    assert "diff-integrity/implemented-rfc-changed" in _codes(root, base)


def test_flipping_an_implemented_rfc_back_to_draft_is_still_a_change(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "docs/rfcs/0001-x.md", _RFC)
    base = _commit(root, "implemented rfc")
    _write(root, "docs/rfcs/0001-x.md", _RFC.replace("implemented", "draft"))
    _commit(root, "flip")

    assert "diff-integrity/implemented-rfc-changed" in _codes(root, base)


def test_deleting_an_implemented_rfc_is_an_error(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "docs/rfcs/0001-x.md", _RFC)
    base = _commit(root, "implemented rfc")
    (root / "docs" / "rfcs" / "0001-x.md").unlink()
    _commit(root, "delete")

    assert "diff-integrity/implemented-rfc-removed" in _codes(root, base)


def test_renaming_and_editing_an_implemented_rfc_is_an_error(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "docs/rfcs/0001-x.md", _RFC)
    base = _commit(root, "implemented rfc")
    (root / "docs" / "rfcs" / "0001-x.md").unlink()
    _write(
        root,
        "docs/rfcs/0001-y.md",
        _RFC.replace("id: 0001-x", "id: 0001-y").replace("Proposal.", "Other."),
    )
    _commit(root, "rename and edit")

    assert "diff-integrity/implemented-rfc-changed" in _codes(root, base)


def test_a_pure_rename_of_an_implemented_rfc_passes(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "docs/rfcs/0001-x.md", _RFC)
    base = _commit(root, "implemented rfc")
    (root / "docs" / "rfcs" / "0001-x.md").unlink()
    _write(root, "docs/rfcs/0001-y.md", _RFC.replace("id: 0001-x", "id: 0001-y"))
    _commit(root, "rename")

    assert not [code for code in _codes(root, base) if code.startswith("diff-integrity/")]


def test_retitling_an_accepted_decision_renames_its_file_and_passes(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "docs/decisions/choice.md", _ADR)
    base = _commit(root, "adr")
    _git(root, "mv", "docs/decisions/choice.md", "docs/decisions/pick-a-lane.md")
    _write(
        root,
        "docs/decisions/pick-a-lane.md",
        _ADR.replace("id: 0001-choice", "id: pick-a-lane")
        .replace("title: Choice", "title: Pick a lane")
        .replace("# Choice", "# Pick a lane"),
    )
    _commit(root, "retitle")

    assert not [code for code in _codes(root, base) if code.startswith("diff-integrity/")]


def test_a_renamed_decision_is_still_held_to_its_decision_section(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "docs/decisions/choice.md", _ADR)
    base = _commit(root, "adr")
    _git(root, "mv", "docs/decisions/choice.md", "docs/decisions/pick-a-lane.md")
    _write(
        root,
        "docs/decisions/pick-a-lane.md",
        _ADR.replace("id: 0001-choice", "id: pick-a-lane").replace("Use A.", "Use B."),
    )
    _commit(root, "retitle and rewrite the decision")

    codes = _codes(root, base)
    assert "diff-integrity/decision-rewritten" in codes
    assert "diff-integrity/accepted-decision-removed" not in codes


def test_deleting_an_accepted_decision_is_an_error(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "docs/decisions/0001-choice.md", _ADR)
    base = _commit(root, "adr")
    (root / "docs" / "decisions" / "0001-choice.md").unlink()
    _commit(root, "delete adr")

    assert "diff-integrity/accepted-decision-removed" in _codes(root, base)


def test_rewriting_an_accepted_decision_warns_but_other_sections_do_not(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "docs/decisions/0001-choice.md", _ADR)
    base = _commit(root, "adr")
    _write(root, "docs/decisions/0001-choice.md", _ADR.replace("Fine.", "Fine enough."))
    middle = _commit(root, "edit consequences")
    assert "diff-integrity/decision-rewritten" not in _codes(root, base)

    _write(root, "docs/decisions/0001-choice.md", _ADR.replace("Use A.", "Use B."))
    _commit(root, "rewrite decision")
    assert "diff-integrity/decision-rewritten" in _codes(root, middle)


def _owned_repo(root: Path) -> str:
    _repo(root)
    _write(
        root,
        "irminsul.toml",
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = ["src"]\n'
        '[checks]\nenabled = ["frontmatter"]\n',
    )
    _write(root, "src/a.py", "A = 1\n")
    _write(root, "src/b.py", "B = 1\n")
    _write(
        root,
        "docs/components/big.md",
        "---\nid: big\ntitle: Big\nstatus: stable\ndescribes:\n  - src/*.py\n---\n\n"
        "# Big\n\nThe parser lives in `a.py` and reads input.\n\nThe writer is separate.\n",
    )
    return _commit(root, "base")


def test_a_file_moved_to_another_doc_is_a_hint_and_its_old_prose_is_listed(
    tmp_path: Path,
) -> None:
    base = _owned_repo(tmp_path)
    _write(
        tmp_path,
        "docs/components/small.md",
        "---\nid: small\ntitle: Small\nstatus: stable\ndescribes:\n  - src/a.py\n---\n\n# Small\n",
    )
    _commit(tmp_path, "split")
    assert "diff-integrity/owner-changed" in _codes(tmp_path, base)

    result = runner.invoke(
        app, ["list", "review", "--base", base, "--format", "json", "--path", str(tmp_path)]
    )
    moved = [i for i in json.loads(result.output)["items"] if "moved-file" in i["markers"]]
    assert [(i["path"], i["sentence"]) for i in moved] == [
        ("docs/components/big.md", "The parser lives in `a.py` and reads input.")
    ]


def test_an_unchanged_owner_is_not_reported(tmp_path: Path) -> None:
    base = _owned_repo(tmp_path)
    _write(
        tmp_path, "docs/components/big.md", _read(tmp_path, "docs/components/big.md") + "\nMore.\n"
    )
    _commit(tmp_path, "edit")
    assert "diff-integrity/owner-changed" not in _codes(tmp_path, base)


def _read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


_CONFIG = 'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = []\n'


def _config_repo(root: Path) -> str:
    _repo(root)
    _write(root, "irminsul.toml", _CONFIG + '[checks]\nenabled = ["frontmatter", "links"]\n')
    return _commit(root, "base")


def _config_codes(root: Path, base: str) -> list[str]:
    weakening = {
        "diff-integrity/check-disabled",
        "diff-integrity/layer-rule-disabled",
        "diff-integrity/source-excluded",
        "diff-integrity/extra-doc-removed",
        "diff-integrity/setting-weakened",
        "diff-integrity/unreviewed-setting-change",
    }
    return [code for code in _codes(root, base) if code in weakening]


def test_removing_a_check_or_a_layer_rule_is_an_error(tmp_path: Path) -> None:
    base = _config_repo(tmp_path)
    _write(
        tmp_path,
        "irminsul.toml",
        _CONFIG
        + '[checks]\nenabled = ["frontmatter"]\n[layers.components]\nrequire_tests = false\n',
    )
    _commit(tmp_path, "weaken")
    assert _config_codes(tmp_path, base) == [
        "diff-integrity/check-disabled",
        "diff-integrity/layer-rule-disabled",
    ]


def test_a_decision_record_naming_the_setting_allows_it(tmp_path: Path) -> None:
    base = _config_repo(tmp_path)
    _write(
        tmp_path,
        "irminsul.toml",
        _CONFIG
        + '[checks]\nenabled = ["frontmatter"]\n[layers.components]\nrequire_tests = false\n',
    )
    _write(
        tmp_path,
        "docs/decisions/drop-links.md",
        "---\nid: drop-links\ntitle: Drop links\nstatus: stable\n---\n\n# Drop links\n\n"
        "## Decision\n\nDisable `links` and `require_tests` for now.\n",
    )
    _commit(tmp_path, "weaken with a record")
    assert _config_codes(tmp_path, base) == []


def test_excluding_source_or_dropping_a_guidance_file_is_a_hint(tmp_path: Path) -> None:
    base = _config_repo(tmp_path)
    _write(
        tmp_path,
        "irminsul.toml",
        'project_name = "r"\n[paths]\ndocs_root = "docs"\nsource_roots = []\n'
        'source_excludes = ["gen/**"]\nextra_docs = ["README.md"]\n'
        '[checks]\nenabled = ["frontmatter", "links"]\n',
    )
    _commit(tmp_path, "narrow")
    assert sorted(_config_codes(tmp_path, base)) == [
        "diff-integrity/extra-doc-removed",
        "diff-integrity/extra-doc-removed",
        "diff-integrity/source-excluded",
    ]


def test_a_doc_moved_to_another_path_keeps_its_files(tmp_path: Path) -> None:
    base = _owned_repo(tmp_path)
    text = _read(tmp_path, "docs/components/big.md")
    (tmp_path / "docs/components/big.md").unlink()
    _write(tmp_path, "docs/architecture/big.md", text)
    _commit(tmp_path, "move")
    assert "diff-integrity/owner-changed" not in _codes(tmp_path, base)


def test_moving_the_rfcs_folder_in_config_does_not_unseal_a_record(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "docs/rfcs/0001-x.md", _RFC)
    base = _commit(root, "implemented rfc")
    config = _read(root, "irminsul.toml") + '[layers.rfcs]\npath = "proposals"\n'
    _write(root, "irminsul.toml", config)
    _write(root, "docs/rfcs/0001-x.md", _RFC.replace("Proposal.", "Better proposal."))
    _commit(root, "move folder and edit")

    assert "diff-integrity/implemented-rfc-changed" in _codes(root, base)


def test_a_baseline_path_spelled_with_dotdot_still_counts(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    entry = {"check": "links", "path": "docs/a.md", "message": "broken", "fingerprint": "x"}
    _write(root, ".irminsul-baseline.json", json.dumps({"version": 1, "findings": [entry]}))
    base = _commit(root, "baseline")
    config = _read(root, "irminsul.toml").replace(
        "source_roots = []\n", 'source_roots = []\nbaseline = "docs/../.irminsul-baseline.json"\n'
    )
    _write(root, "irminsul.toml", config)
    grown = [entry, {**entry, "message": "also broken"}]
    _write(root, ".irminsul-baseline.json", json.dumps({"version": 1, "findings": grown}))
    _commit(root, "grow baseline")

    assert "diff-integrity/baseline-grew" in _codes(root, base)


def test_a_baseline_cannot_hide_diff_integrity_findings(tmp_path: Path) -> None:
    root = _config_repo(tmp_path)
    _write(tmp_path, "irminsul.toml", _CONFIG + '[checks]\nenabled = ["frontmatter"]\n')
    entry = {
        "check": "diff-integrity",
        "path": "irminsul.toml",
        "message": f"check 'links' was removed from checks.enabled since {root}",
    }
    _write(tmp_path, ".irminsul-baseline.json", json.dumps({"version": 1, "findings": [entry]}))
    _commit(tmp_path, "weaken and baseline it")

    assert "diff-integrity/check-disabled" in _config_codes(tmp_path, root)


def test_editing_an_existing_record_does_not_excuse_a_weakening(tmp_path: Path) -> None:
    _repo(tmp_path)
    _write(tmp_path, "irminsul.toml", _CONFIG + '[checks]\nenabled = ["frontmatter", "links"]\n')
    _write(tmp_path, "docs/decisions/0001-choice.md", _ADR)
    base = _commit(tmp_path, "base")
    _write(tmp_path, "irminsul.toml", _CONFIG + '[checks]\nenabled = ["frontmatter"]\n')
    _write(tmp_path, "docs/decisions/0001-choice.md", _ADR.replace("Fine.", "Keep `links`."))
    _commit(tmp_path, "weaken through an old record")

    assert "diff-integrity/check-disabled" in _config_codes(tmp_path, base)


def test_adopting_irminsul_is_not_a_weakening(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _write(tmp_path, "README.md", "# r\n")
    base = _commit(tmp_path, "before irminsul")
    _repo(tmp_path)
    _commit(tmp_path, "adopt")

    assert _config_codes(tmp_path, base) == []


def test_an_ignore_comment_for_a_time_code_is_not_unused_under_diff(tmp_path: Path) -> None:
    from irminsul.checks.pipeline import finish
    from irminsul.config import load
    from irminsul.docgraph import build_graph

    _write(tmp_path, "irminsul.toml", _CONFIG)
    _write(
        tmp_path,
        "docs/guides/g.md",
        "---\nid: g\ntitle: G\nstatus: stable\n---\n\n# G\n\n"
        "See https://example.invalid. "
        '<!-- irminsul:ignore external-links/unreachable reason="flaky host" -->\n',
    )
    graph = build_graph(tmp_path, load(tmp_path / "irminsul.toml"))
    assert finish([], graph, ran=["external-links"], diff=True) == []


_ANCHORED = (
    "---\nid: widget\ntitle: Widget\nstatus: stable\n"
    "claims:\n  - id: widget-runs\n    state: implemented\n    kind: invariant\n"
    "    claim: The widget runs.\n    evidence:\n      - src/widget.py\n"
    "---\n\n# Widget\n\nIt runs.\n<!-- anchor: src/widget.py#run -->\n"
)


def _anchored_repo(root: Path) -> tuple[Path, str]:
    _repo(root)
    _write(root, "src/widget.py", "def run():\n    return 1\n")
    _write(root, "docs/components/widget.md", _ANCHORED)
    return root, _commit(root, "anchored doc")


def test_removing_an_anchor_whose_code_survives_is_an_error(tmp_path: Path) -> None:
    root, base = _anchored_repo(tmp_path)
    _write(
        root,
        "docs/components/widget.md",
        _ANCHORED.replace("\n<!-- anchor: src/widget.py#run -->", ""),
    )
    _commit(root, "drop the anchor")

    assert "diff-integrity/anchor-removed" in _codes(root, base)


def test_removing_an_anchor_with_its_code_is_allowed(tmp_path: Path) -> None:
    root, base = _anchored_repo(tmp_path)
    _write(
        root,
        "docs/components/widget.md",
        _ANCHORED.replace("\n<!-- anchor: src/widget.py#run -->", ""),
    )
    _write(root, "src/widget.py", "def other():\n    return 2\n")
    _commit(root, "drop the anchor and the code")

    assert "diff-integrity/anchor-removed" not in _codes(root, base)


def test_removing_a_claim_whose_evidence_survives_is_an_error(tmp_path: Path) -> None:
    root, base = _anchored_repo(tmp_path)
    stripped = (
        _ANCHORED[: _ANCHORED.index("claims:")] + _ANCHORED[_ANCHORED.index("---\n\n# Widget") :]
    )
    _write(root, "docs/components/widget.md", stripped)
    _commit(root, "drop the claim")

    assert "diff-integrity/claim-removed" in _codes(root, base)


def test_removing_a_claim_with_its_evidence_is_allowed(tmp_path: Path) -> None:
    root, base = _anchored_repo(tmp_path)
    stripped = (
        _ANCHORED[: _ANCHORED.index("claims:")] + _ANCHORED[_ANCHORED.index("---\n\n# Widget") :]
    )
    _write(
        root,
        "docs/components/widget.md",
        stripped.replace("\n<!-- anchor: src/widget.py#run -->", ""),
    )
    (root / "src" / "widget.py").unlink()
    _commit(root, "drop the claim and the code")

    assert "diff-integrity/claim-removed" not in _codes(root, base)


_INVENTORIED = (
    "---\nid: widget\ntitle: Widget\nstatus: stable\n"
    "inventory:\n  - kind: cli\n    source: src/widget.py\n    explained_in: any\n"
    "---\n\n# Widget\n\nIt runs.\n"
)


def test_hollowing_out_an_inventory_contract_is_a_weakening(tmp_path: Path) -> None:
    """The removal seal keys on `(kind, source)`, so every field that makes the entry a
    contract could be dropped while the entry stayed — silencing live identities without
    tripping anything. Deleting one `explained_in:` line was enough."""
    root = _repo(tmp_path)
    _write(root, "src/widget.py", "def run():\n    return 1\n")
    _write(root, "docs/components/widget.md", _INVENTORIED)
    base = _commit(root, "inventoried doc")

    _write(root, "docs/components/widget.md", _INVENTORIED.replace("    explained_in: any\n", ""))
    _commit(root, "drop the explained_in contract")

    assert "diff-integrity/inventory-weakened" in _codes(root, base)


def test_tightening_an_inventory_contract_is_silent(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _write(root, "src/widget.py", "def run():\n    return 1\n")
    _write(root, "docs/components/widget.md", _INVENTORIED)
    base = _commit(root, "inventoried doc")

    _write(
        root,
        "docs/components/widget.md",
        _INVENTORIED.replace("explained_in: any", "explained_in: self").replace(
            "    explained_in: self\n", "    explained_in: self\n    complete: true\n"
        ),
    )
    _commit(root, "ask for more")

    assert "diff-integrity/inventory-weakened" not in _codes(root, base)


def test_renaming_a_doc_does_not_hide_the_governance_it_dropped(tmp_path: Path) -> None:
    """`--find-renames` lists a renamed doc under its new path only, so reading the base
    side at that path found nothing and the doc was skipped — making a rename the
    cheapest way to drop every anchor and claim it held."""
    root, _ = _anchored_repo(tmp_path)
    # Enough shared prose that git scores the pair as a rename rather than add+delete.
    padded = _ANCHORED.replace("It runs.", "It runs. " + "Stable prose that survives. " * 40)
    _write(root, "docs/components/widget.md", padded)
    base = _commit(root, "pad the doc so the rename is detected")

    stripped = padded[: padded.index("claims:")] + padded[padded.index("---\n\n# Widget") :]
    _git(root, "mv", "docs/components/widget.md", "docs/components/gadget.md")
    _write(
        root,
        "docs/components/gadget.md",
        stripped.replace("id: widget", "id: gadget").replace(
            "\n<!-- anchor: src/widget.py#run -->", ""
        ),
    )
    _commit(root, "rename and drop the claim and anchor")

    codes = _codes(root, base)
    assert "diff-integrity/claim-removed" in codes
    assert "diff-integrity/anchor-removed" in codes


def test_rewording_a_claim_is_not_removing_it(tmp_path: Path) -> None:
    """Fixing the wording of a claim is maintenance, and had no green route.

    Identity was the `(id, text)` pair, so any edit to the sentence read as a deletion
    of the claim and an addition of a different one.
    """
    root, base = _anchored_repo(tmp_path)
    _write(
        root,
        "docs/components/widget.md",
        _ANCHORED.replace("The widget runs.", "The widget runs on demand."),
    )
    _commit(root, "reword the claim")

    assert "diff-integrity/claim-removed" not in _codes(root, base)


def test_neutering_a_claim_in_place_is_reported(tmp_path: Path) -> None:
    """Keeping the id and emptying the sentence is how a claim stops saying anything.

    Reading a rewording as a deletion had no green route, but treating it as silent let
    `The widget runs` become `The widget exists` unreported.
    """
    root, base = _anchored_repo(tmp_path)
    _write(
        root,
        "docs/components/widget.md",
        _ANCHORED.replace("The widget runs.", "The widget exists."),
    )
    _commit(root, "empty the claim")

    codes = _codes(root, base)
    assert "diff-integrity/claim-reworded" in codes
    assert "diff-integrity/claim-removed" not in codes


def test_repointing_a_governing_claims_evidence_is_a_change_of_intent(tmp_path: Path) -> None:
    """The words of a contract are not the whole contract: aiming it at a file that
    trivially satisfies it leaves the sentence intact and governs nothing."""
    root, _ = _anchored_repo(tmp_path)
    governing = _ANCHORED.replace(
        "    kind: invariant\n", "    kind: invariant\n    relation: governs-evidence\n"
    )
    _write(root, "docs/components/widget.md", governing)
    _write(root, "src/trivial.py", "X = 1\n")
    base = _commit(root, "make the claim govern")

    _write(
        root,
        "docs/components/widget.md",
        governing.replace("      - src/widget.py", "      - src/trivial.py"),
    )
    _commit(root, "aim it somewhere harmless")

    assert "diff-integrity/governing-claim-changed" in _codes(root, base)


def test_renaming_a_claim_id_is_still_a_removal(tmp_path: Path) -> None:
    root, base = _anchored_repo(tmp_path)
    _write(root, "docs/components/widget.md", _ANCHORED.replace("widget-runs", "widget-executes"))
    _commit(root, "rename the claim id")

    assert "diff-integrity/claim-removed" in _codes(root, base)


def test_a_record_naming_the_claim_excuses_removing_it(tmp_path: Path) -> None:
    root, base = _anchored_repo(tmp_path)
    stripped = (
        _ANCHORED[: _ANCHORED.index("claims:")] + _ANCHORED[_ANCHORED.index("---\n\n# Widget") :]
    )
    _write(root, "docs/components/widget.md", stripped)
    _write(
        root,
        "docs/decisions/widget-claim-retired.md",
        "---\nid: widget-claim-retired\ntitle: Widget claim retired\nstatus: stable\n---\n\n"
        "# Widget claim retired\n\n## Decision\n\nThe claim `widget-runs` is retired.\n",
    )
    _commit(root, "drop the claim with a record")

    assert "diff-integrity/claim-removed" not in _codes(root, base)


def test_a_draft_record_naming_the_setting_does_not_allow_it(tmp_path: Path) -> None:
    """A nine-line draft whose body was just the check name used to unlock it."""
    base = _config_repo(tmp_path)
    _write(tmp_path, "irminsul.toml", _CONFIG + '[checks]\nenabled = ["frontmatter"]\n')
    _write(
        tmp_path,
        "docs/decisions/scratch.md",
        "---\nid: scratch\ntitle: Scratch\nstatus: draft\n---\n\n# Scratch\n\n`links`\n",
    )
    _commit(tmp_path, "weaken with a scratch file")

    assert "diff-integrity/check-disabled" in _config_codes(tmp_path, base)


def test_a_record_naming_the_setting_outside_its_decision_does_not_allow_it(
    tmp_path: Path,
) -> None:
    base = _config_repo(tmp_path)
    _write(tmp_path, "irminsul.toml", _CONFIG + '[checks]\nenabled = ["frontmatter"]\n')
    _write(
        tmp_path,
        "docs/decisions/aside.md",
        "---\nid: aside\ntitle: Aside\nstatus: stable\n---\n\n# Aside\n\n"
        "## Context\n\nWe once used `links`.\n\n## Decision\n\nSomething unrelated.\n",
    )
    _commit(tmp_path, "mention the check in passing")

    assert "diff-integrity/check-disabled" in _config_codes(tmp_path, base)


def test_repointing_docs_root_is_an_error(tmp_path: Path) -> None:
    """A fresh folder with one stub INDEX used to give 0 findings and exit 0."""
    base = _config_repo(tmp_path)
    _write(tmp_path, "irminsul.toml", _CONFIG.replace('docs_root = "docs"', 'docs_root = "notes"'))
    _write(
        tmp_path,
        "notes/decisions/INDEX.md",
        "---\nid: decisions\ntitle: D\nstatus: stable\n---\n\n# D\n",
    )
    _commit(tmp_path, "repoint docs_root")

    assert "diff-integrity/check-disabled" in _config_codes(tmp_path, base)


def test_moving_a_layer_folder_is_an_error(tmp_path: Path) -> None:
    base = _config_repo(tmp_path)
    _write(
        tmp_path,
        "irminsul.toml",
        _CONFIG + '[layers.decisions]\npath = "adr"\n',
    )
    _commit(tmp_path, "move the decisions folder")

    assert "diff-integrity/layer-rule-disabled" in _config_codes(tmp_path, base)


def _workflow_repo(root: Path) -> str:
    _repo(root)
    _write(
        root,
        ".github/workflows/docs.yml",
        'jobs:\n  docs:\n    steps:\n      - run: irminsul check --diff "origin/main"\n',
    )
    return _commit(root, "gated workflow")


def test_dropping_the_diff_flag_from_a_workflow_is_an_error(tmp_path: Path) -> None:
    """The seal runs only under --diff, which lives in a file the change can edit."""
    base = _workflow_repo(tmp_path)
    _write(
        tmp_path,
        ".github/workflows/docs.yml",
        "jobs:\n  docs:\n    steps:\n      - run: irminsul check\n",
    )
    _commit(tmp_path, "loosen the gate")

    assert "diff-integrity/gate-weakened" in _codes(tmp_path, base)


def test_deleting_the_check_step_is_an_error(tmp_path: Path) -> None:
    base = _workflow_repo(tmp_path)
    _write(
        tmp_path, ".github/workflows/docs.yml", "jobs:\n  docs:\n    steps:\n      - run: echo hi\n"
    )
    _commit(tmp_path, "remove the check")

    assert "diff-integrity/gate-weakened" in _codes(tmp_path, base)


def test_an_unrelated_workflow_edit_is_not_a_weakening(tmp_path: Path) -> None:
    base = _workflow_repo(tmp_path)
    _write(
        tmp_path,
        ".github/workflows/docs.yml",
        'jobs:\n  docs:\n    steps:\n      - run: echo setup\n      - run: irminsul check --diff "origin/main"\n',
    )
    _commit(tmp_path, "add a step")

    assert "diff-integrity/gate-weakened" not in _codes(tmp_path, base)


def test_moving_the_check_to_another_workflow_is_not_a_weakening(tmp_path: Path) -> None:
    """Counted per file, an ordinary CI refactor read as deleting the gate."""
    base = _workflow_repo(tmp_path)
    (tmp_path / ".github" / "workflows" / "docs.yml").unlink()
    _write(
        tmp_path,
        ".github/workflows/gate.yml",
        'jobs:\n  docs:\n    steps:\n      - run: irminsul check --diff "origin/main"\n',
    )
    _commit(tmp_path, "move the step to another workflow")

    assert "diff-integrity/gate-weakened" not in _codes(tmp_path, base)


def _workflow(trigger: str, step: str) -> str:
    """A workflow long enough that git pairs a lightly edited copy with it as a rename."""
    return (
        f"name: docs\n\non: {trigger}\n\njobs:\n  docs:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - uses: actions/checkout@v4\n        with:\n"
        f"          fetch-depth: 0\n      - run: pip install irminsul\n{step}"
    )


_RUN_GATE = '      - run: irminsul check --strict --diff "origin/main"\n'
_ACTION_GATE = (
    "      - uses: acme/irminsul@v1\n        with:\n"
    "          strict: true\n          diff: origin/main\n"
)
_NIGHTLY = "\n  schedule:\n    - cron: '0 3 * * *'"


def _triggered_repo(root: Path, step: str = _RUN_GATE, trigger: str = "pull_request") -> str:
    _repo(root)
    _write(root, ".github/workflows/docs.yml", _workflow(trigger, step))
    return _commit(root, "gated workflow")


def _rename_workflow(root: Path, base: str, text: str) -> None:
    _git(root, "mv", ".github/workflows/docs.yml", ".github/workflows/gate.yml")
    _write(root, ".github/workflows/gate.yml", text)
    _commit(root, "rename the workflow")
    status = _git(root, "diff", "--find-renames", "--name-status", base, "HEAD", "--", ".github")
    assert status.startswith("R"), f"git no longer reads this as a rename: {status}"


def _weakenings(root: Path, base: str) -> list[str]:
    result = runner.invoke(app, ["check", "--diff", base, "--format", "json", "--path", str(root)])
    return [
        f["message"]
        for f in json.loads(result.output)["findings"]
        if f["code"] == "diff-integrity/gate-weakened"
    ]


def test_renaming_a_workflow_does_not_hide_a_weakened_run_step(tmp_path: Path) -> None:
    """Git lists a renamed file under its new name alone, so a comparison that reads only
    the changed paths scores the renamed workflow's base as empty and sees no loss."""
    base = _triggered_repo(tmp_path)
    weaker = _workflow("pull_request", "      - run: irminsul check --strict\n")
    _rename_workflow(tmp_path, base, weaker)

    assert _weakenings(tmp_path, base)


def test_renaming_a_workflow_does_not_hide_weakened_action_inputs(tmp_path: Path) -> None:
    base = _triggered_repo(tmp_path, _ACTION_GATE)
    weaker = _workflow(
        "pull_request", "      - uses: acme/irminsul@v1\n        with:\n          strict: true\n"
    )
    _rename_workflow(tmp_path, base, weaker)

    assert _weakenings(tmp_path, base)


def test_renaming_a_workflow_and_keeping_its_gate_is_not_a_weakening(tmp_path: Path) -> None:
    base = _triggered_repo(tmp_path)
    renamed = _workflow("pull_request", _RUN_GATE).replace("name: docs", "name: gate")
    _rename_workflow(tmp_path, base, renamed)

    assert _weakenings(tmp_path, base) == []


def test_deleting_a_workflow_is_an_error(tmp_path: Path) -> None:
    base = _triggered_repo(tmp_path)
    (tmp_path / ".github" / "workflows" / "docs.yml").unlink()
    _commit(tmp_path, "delete the workflow")

    assert _weakenings(tmp_path, base)


def test_moving_a_workflow_out_of_the_folder_github_runs_is_an_error(tmp_path: Path) -> None:
    base = _triggered_repo(tmp_path)
    _git(tmp_path, "mv", ".github/workflows/docs.yml", ".github/workflows/docs.yml.disabled")
    _commit(tmp_path, "park the workflow")

    assert _weakenings(tmp_path, base)


def test_a_nightly_gate_does_not_pay_for_one_taken_off_pull_requests(tmp_path: Path) -> None:
    """One total for the whole repository lets an unrelated workflow's gain cancel the loss,
    though no pull request is judged by a scheduled run."""
    _repo(tmp_path)
    _write(tmp_path, ".github/workflows/docs.yml", _workflow("pull_request", _RUN_GATE))
    _write(
        tmp_path,
        ".github/workflows/nightly.yml",
        _workflow(_NIGHTLY, "      - run: irminsul check\n"),
    )
    base = _commit(tmp_path, "a pull request gate and a nightly run")
    _write(
        tmp_path,
        ".github/workflows/docs.yml",
        _workflow("pull_request", "      - run: irminsul check\n"),
    )
    _write(tmp_path, ".github/workflows/nightly.yml", _workflow(_NIGHTLY, _RUN_GATE))
    _commit(tmp_path, "move the strength to the nightly run")

    messages = _weakenings(tmp_path, base)

    assert messages and all("`pull_request`" in m and "`schedule`" not in m for m in messages)


def test_moving_the_gate_between_pull_request_workflows_is_not_a_weakening(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    _write(tmp_path, ".github/workflows/docs.yml", _workflow("pull_request", _RUN_GATE))
    _write(
        tmp_path,
        ".github/workflows/lint.yml",
        _workflow("pull_request", "      - run: ruff check .\n"),
    )
    base = _commit(tmp_path, "two pull request workflows")
    _write(
        tmp_path,
        ".github/workflows/docs.yml",
        _workflow("pull_request", "      - run: echo docs\n"),
    )
    _write(
        tmp_path,
        ".github/workflows/lint.yml",
        _workflow("pull_request", "      - run: ruff check .\n" + _RUN_GATE),
    )
    _commit(tmp_path, "run the gate from the lint workflow")

    assert _weakenings(tmp_path, base) == []


def test_taking_pull_request_off_a_workflows_triggers_is_an_error(tmp_path: Path) -> None:
    base = _triggered_repo(tmp_path, trigger="[push, pull_request]")
    _write(tmp_path, ".github/workflows/docs.yml", _workflow("[push]", _RUN_GATE))
    _commit(tmp_path, "stop running on pull requests")

    messages = _weakenings(tmp_path, base)

    assert messages and all("`pull_request`" in m and "`push`" not in m for m in messages)


def test_a_workflow_that_stops_parsing_no_longer_counts_for_its_events(tmp_path: Path) -> None:
    base = _triggered_repo(tmp_path)
    broken = _workflow("pull_request", _RUN_GATE).replace("jobs:\n", "jobs: [\n")
    _write(tmp_path, ".github/workflows/docs.yml", broken)
    _commit(tmp_path, "break the yaml")

    assert _weakenings(tmp_path, base)


_RUN_EVERY_CHECK = (
    '      - run: irminsul check --profile all-available --strict --diff "origin/main"\n'
)
_ACTION_EVERY_CHECK = (
    "      - uses: acme/irminsul@v1\n        with:\n"
    "          profile: all-available\n          strict: true\n          diff: origin/main\n"
)


def test_narrowing_the_profile_flag_is_an_error(tmp_path: Path) -> None:
    """Taking a check out of `checks.enabled` is reported, so a narrower profile was the
    route to the same result that nothing watched."""
    base = _triggered_repo(tmp_path, _RUN_EVERY_CHECK)
    narrower = _RUN_EVERY_CHECK.replace("--profile all-available", "--profile enabled")
    _write(tmp_path, ".github/workflows/docs.yml", _workflow("pull_request", narrower))
    _commit(tmp_path, "gate only the enabled checks")

    messages = _weakenings(tmp_path, base)

    assert len(messages) == 1 and "`--profile`" in messages[0]


def test_dropping_the_profile_flag_is_an_error(tmp_path: Path) -> None:
    base = _triggered_repo(tmp_path, _RUN_EVERY_CHECK)
    dropped = _RUN_EVERY_CHECK.replace("--profile all-available ", "")
    _write(tmp_path, ".github/workflows/docs.yml", _workflow("pull_request", dropped))
    _commit(tmp_path, "fall back to the default profile")

    assert _weakenings(tmp_path, base)


def test_narrowing_the_profile_input_of_the_action_is_an_error(tmp_path: Path) -> None:
    base = _triggered_repo(tmp_path, _ACTION_EVERY_CHECK)
    narrower = _ACTION_EVERY_CHECK.replace("profile: all-available", "profile: enabled")
    _write(tmp_path, ".github/workflows/docs.yml", _workflow("pull_request", narrower))
    _commit(tmp_path, "gate only the enabled checks")

    assert _weakenings(tmp_path, base)


def test_writing_the_default_profile_out_is_not_a_weakening(tmp_path: Path) -> None:
    base = _triggered_repo(tmp_path)
    spelled = _RUN_GATE.replace("check ", "check --profile enabled ")
    _write(tmp_path, ".github/workflows/docs.yml", _workflow("pull_request", spelled))
    _commit(tmp_path, "spell the default out")

    assert _weakenings(tmp_path, base) == []


def test_widening_the_profile_is_not_a_weakening(tmp_path: Path) -> None:
    base = _triggered_repo(tmp_path)
    _write(tmp_path, ".github/workflows/docs.yml", _workflow("pull_request", _RUN_EVERY_CHECK))
    _commit(tmp_path, "gate every available check")

    assert _weakenings(tmp_path, base) == []


def test_a_decision_record_naming_the_profile_excuses_narrowing_it(tmp_path: Path) -> None:
    base = _triggered_repo(tmp_path, _RUN_EVERY_CHECK)
    narrower = _RUN_EVERY_CHECK.replace("--profile all-available", "--profile enabled")
    _write(tmp_path, ".github/workflows/docs.yml", _workflow("pull_request", narrower))
    _write(
        tmp_path,
        "docs/decisions/gate-the-enabled-checks.md",
        _ADR.replace("0001-choice", "gate-the-enabled-checks").replace(
            "Use A.", "Gate with `--profile` enabled; the experimental checks are too noisy."
        ),
    )
    _commit(tmp_path, "narrow the profile, and say why")

    assert _weakenings(tmp_path, base) == []


_LOCAL_ACTION = """\
name: irminsul
inputs:
  strict:
    default: 'false'
  diff:
    default: ''
runs:
  using: composite
  steps:
    - shell: bash
      env:
        STRICT: ${{ inputs.strict }}
        DIFF: ${{ inputs.diff }}
      run: |
        args=()
        if [ "$STRICT" = "true" ]; then args+=(--strict); fi
        if [ -n "$DIFF" ]; then args+=("--diff=$DIFF"); fi
        irminsul check "${args[@]}"
"""
_LOCAL_STEP = (
    "      - uses: ./\n        with:\n          strict: true\n          diff: origin/main\n"
)
_NO_GATE = _workflow("pull_request", "      - run: echo docs\n")


def _local_action_repo(root: Path, folder: str = "") -> str:
    """A pull request gate that calls an action kept in the repository, at `folder`."""
    _repo(root)
    _write(root, f"{folder}action.yml", _LOCAL_ACTION)
    step = _LOCAL_STEP.replace("uses: ./", "uses: ./" + folder.rstrip("/"))
    _write(root, ".github/workflows/docs.yml", _workflow("pull_request", step))
    return _commit(root, "gate through a local action")


def test_deleting_a_local_action_step_is_an_error(tmp_path: Path) -> None:
    """`uses: ./` names no owner and no ref, so a rule written for the published Action
    read the step as something else and scored the gate as absent."""
    base = _local_action_repo(tmp_path)
    _write(tmp_path, ".github/workflows/docs.yml", _NO_GATE)
    _commit(tmp_path, "drop the local action step")

    assert _weakenings(tmp_path, base)


def test_dropping_an_input_of_a_local_action_is_an_error(tmp_path: Path) -> None:
    base = _local_action_repo(tmp_path)
    weaker = _LOCAL_STEP.replace("          diff: origin/main\n", "")
    _write(tmp_path, ".github/workflows/docs.yml", _workflow("pull_request", weaker))
    _commit(tmp_path, "drop the diff input")

    messages = _weakenings(tmp_path, base)

    assert len(messages) == 1 and "`--diff`" in messages[0]


def test_a_local_action_in_a_subfolder_is_a_gate_too(tmp_path: Path) -> None:
    base = _local_action_repo(tmp_path, ".github/actions/docs-gate/")
    _write(tmp_path, ".github/workflows/docs.yml", _NO_GATE)
    _commit(tmp_path, "drop the vendored action step")

    assert _weakenings(tmp_path, base)


def test_a_local_action_that_stops_passing_a_flag_on_is_an_error(tmp_path: Path) -> None:
    """No workflow changes: the action it calls stops turning `diff` into `--diff`."""
    base = _local_action_repo(tmp_path)
    gutted = _LOCAL_ACTION.replace(
        '        if [ -n "$DIFF" ]; then args+=("--diff=$DIFF"); fi\n', ""
    )
    _write(tmp_path, "action.yml", gutted)
    _commit(tmp_path, "stop passing --diff through")

    messages = _weakenings(tmp_path, base)

    assert len(messages) == 1 and "`--diff`" in messages[0]


def test_a_local_action_that_stops_running_the_check_is_an_error(tmp_path: Path) -> None:
    base = _local_action_repo(tmp_path)
    _write(tmp_path, "action.yml", _LOCAL_ACTION.replace("irminsul check", "echo skipped"))
    _commit(tmp_path, "stop running the check")

    assert _weakenings(tmp_path, base)


def test_a_local_action_that_never_ran_the_check_is_not_a_gate(tmp_path: Path) -> None:
    _repo(tmp_path)
    _write(tmp_path, "action.yml", _LOCAL_ACTION.replace("irminsul check", "echo"))
    _write(tmp_path, ".github/workflows/docs.yml", _workflow("pull_request", _LOCAL_STEP))
    base = _commit(tmp_path, "a local action that is not a gate")
    _write(tmp_path, ".github/workflows/docs.yml", _NO_GATE)
    _commit(tmp_path, "drop it")

    assert _weakenings(tmp_path, base) == []


def test_editing_a_local_action_without_weakening_it_is_not_an_error(tmp_path: Path) -> None:
    base = _local_action_repo(tmp_path)
    _write(tmp_path, "action.yml", _LOCAL_ACTION.replace("name: irminsul", "name: docs gate"))
    _commit(tmp_path, "rename the action")

    assert _weakenings(tmp_path, base) == []


def test_this_repositorys_own_action_is_scored_as_a_gate() -> None:
    """The project's CI runs the Action as `uses: ./`, which is the spelling it could not see."""
    from irminsul.checks.diff_integrity import _gate_strength

    root = Path(__file__).resolve().parents[1]

    def read(path: str) -> str | None:
        target = root / path
        return target.read_text(encoding="utf-8") if target.is_file() else None

    workflow = (
        "on: pull_request\njobs:\n  docs:\n    steps:\n"
        "      - uses: ./\n        with:\n          strict: true\n          diff: origin/main\n"
    )

    assert _gate_strength(workflow, read) == (1, 3, 2, 1)
    assert _gate_strength(workflow) == (0, 0, 0, 0)


_SCAFFOLDED_PATHS = (
    '    paths:\n      - "docs/**"\n      - "irminsul.toml"\n      - "src/**"\n'
    '      - ".github/workflows/**"\n'
)


def _filtered(paths: str) -> str:
    return _workflow(f"\n  pull_request:\n{paths}", _RUN_GATE)


def _paths_repo(root: Path, workflow: str) -> str:
    """A repository whose gate reads `docs/`, `src/mod.py` and the config, and not `LICENSE`."""
    _repo(root)
    config = (root / "irminsul.toml").read_text(encoding="utf-8")
    _write(root, "irminsul.toml", config.replace("source_roots = []", 'source_roots = ["src"]'))
    _write(root, "src/mod.py", "def alpha():\n    return 1\n")
    _write(root, "LICENSE", "MIT\n")
    _write(root, ".github/workflows/docs.yml", workflow)
    return _commit(root, "a gate on pull requests")


def test_taking_a_source_root_out_of_the_paths_filter_is_an_error(tmp_path: Path) -> None:
    """The step and its flags are untouched, and the gate never runs for a source change."""
    base = _paths_repo(tmp_path, _filtered(_SCAFFOLDED_PATHS))
    narrowed = _SCAFFOLDED_PATHS.replace('      - "src/**"\n', "")
    _write(tmp_path, ".github/workflows/docs.yml", _filtered(narrowed))
    _commit(tmp_path, "stop running the gate for source changes")

    messages = _weakenings(tmp_path, base)

    assert len(messages) == 1 and "`src/mod.py`" in messages[0] and "`pull_request`" in messages[0]


def test_ignoring_the_docs_tree_is_an_error(tmp_path: Path) -> None:
    base = _paths_repo(tmp_path, _workflow("pull_request", _RUN_GATE))
    _write(
        tmp_path,
        ".github/workflows/docs.yml",
        _filtered('    paths-ignore:\n      - "docs/**"\n'),
    )
    _commit(tmp_path, "skip the gate for doc changes")

    assert _weakenings(tmp_path, base)


def test_negating_a_judged_path_is_an_error(tmp_path: Path) -> None:
    base = _paths_repo(tmp_path, _filtered(_SCAFFOLDED_PATHS))
    _write(
        tmp_path,
        ".github/workflows/docs.yml",
        _filtered(_SCAFFOLDED_PATHS + '      - "!src/**"\n'),
    )
    _commit(tmp_path, "take the source root back out")

    assert _weakenings(tmp_path, base)


def test_filtering_a_gate_down_to_what_it_reads_is_not_a_weakening(tmp_path: Path) -> None:
    """`LICENSE` stops running the gate, which never read it."""
    base = _paths_repo(tmp_path, _workflow("pull_request", _RUN_GATE))
    _write(tmp_path, ".github/workflows/docs.yml", _filtered(_SCAFFOLDED_PATHS))
    _commit(tmp_path, "run the gate only for what it reads")

    assert _weakenings(tmp_path, base) == []


def test_replacing_patterns_with_a_wider_one_is_not_a_weakening(tmp_path: Path) -> None:
    """Three patterns are gone, which a comparison of the lists would report."""
    base = _paths_repo(tmp_path, _filtered(_SCAFFOLDED_PATHS))
    _write(tmp_path, ".github/workflows/docs.yml", _filtered('    paths:\n      - "**"\n'))
    _commit(tmp_path, "one pattern for everything")

    assert _weakenings(tmp_path, base) == []


def test_dropping_the_pattern_of_a_deleted_source_root_is_not_a_weakening(tmp_path: Path) -> None:
    base = _paths_repo(tmp_path, _filtered(_SCAFFOLDED_PATHS))
    _git(tmp_path, "rm", "-rq", "src")
    config = (tmp_path / "irminsul.toml").read_text(encoding="utf-8")
    _write(tmp_path, "irminsul.toml", config.replace('source_roots = ["src"]', "source_roots = []"))
    narrowed = _SCAFFOLDED_PATHS.replace('      - "src/**"\n', "")
    _write(tmp_path, ".github/workflows/docs.yml", _filtered(narrowed))
    _commit(tmp_path, "the source root is gone, and so is its pattern")

    assert [m for m in _weakenings(tmp_path, base) if "alone no longer runs" in m] == []


def test_a_decision_record_naming_paths_excuses_a_narrower_filter(tmp_path: Path) -> None:
    base = _paths_repo(tmp_path, _filtered(_SCAFFOLDED_PATHS))
    narrowed = _SCAFFOLDED_PATHS.replace('      - "src/**"\n', "")
    _write(tmp_path, ".github/workflows/docs.yml", _filtered(narrowed))
    _write(
        tmp_path,
        "docs/decisions/gate-docs-changes-only.md",
        _ADR.replace("0001-choice", "gate-docs-changes-only").replace(
            "Use A.", "Narrow the gate's `paths` to the docs tree; source is gated elsewhere."
        ),
    )
    _commit(tmp_path, "narrow the filter, and say why")

    assert _weakenings(tmp_path, base) == []


def test_path_filters_are_read_the_way_github_reads_them() -> None:
    from irminsul.checks.diff_integrity import _triggers

    def runs(patterns: list[str], path: str, kind: str = "paths") -> bool:
        return _triggers((kind, patterns), path)

    assert _triggers(None, "anything")
    assert runs(["docs/**"], "docs/a/b.md") and not runs(["docs/**"], "src/a.py")
    # `*` stops at a slash, so a bare `*.md` reaches only the repository root.
    assert runs(["*.md"], "README.md") and not runs(["*.md"], "docs/a.md")
    assert runs(["**/*.md"], "README.md") and runs(["**/*.md"], "docs/a/b.md")
    assert runs(["**.md"], "docs/a.md")
    # The last pattern to match decides, so a negation can be overridden again.
    assert not runs(["src/**", "!src/gen/**"], "src/gen/x.py")
    assert runs(["src/**", "!src/gen/**", "src/gen/keep.py"], "src/gen/keep.py")
    assert not runs(["docs/**"], "docs/a.md", kind="paths-ignore")
    assert runs(["docs/**"], "src/a.py", kind="paths-ignore")


_UNREADABLE = "diff-integrity/filter-unreadable"
_NOT_COMPARED = "diff-integrity/filter-not-compared"
#: Four shapes a person can type that GitHub's filter syntax allows through as YAML and
#: `re.compile` rejects: a quantifier with nothing before it, twice; a backwards range;
#: and a character class that never closes.
_MALFORMED = ("+build/**", "?src/**", "src/[z-a].py", "src/[]")


def _findings(root: Path, base: str) -> list[dict[str, str]]:
    result = runner.invoke(app, ["check", "--diff", base, "--format", "json", "--path", str(root)])
    return list(json.loads(result.output)["findings"])


def _filter_findings(root: Path, base: str) -> list[dict[str, str]]:
    return [f for f in _findings(root, base) if f["code"] in {_UNREADABLE, _NOT_COMPARED}]


@pytest.mark.parametrize("pattern", _MALFORMED)
def test_a_filter_entry_that_is_not_a_pattern_is_reported_not_raised(
    tmp_path: Path, pattern: str
) -> None:
    """Each of these reached `re.compile` unguarded and ended the whole run in a traceback,
    which took every other diff-integrity finding down with it."""
    base = _paths_repo(tmp_path, _filtered(_SCAFFOLDED_PATHS))
    _write(
        tmp_path,
        ".github/workflows/docs.yml",
        _filtered(_SCAFFOLDED_PATHS + f'      - "{pattern}"\n'),
    )
    _commit(tmp_path, "add an entry that is not a pattern")

    reported = _filter_findings(tmp_path, base)

    assert [f["code"] for f in reported] == [_UNREADABLE]
    assert reported[0]["severity"] == "error"
    assert pattern in reported[0]["message"] and "pull_request" in reported[0]["message"]
    assert reported[0]["path"] == ".github/workflows/docs.yml"


def test_an_unreadable_filter_entry_does_not_become_a_weakening(tmp_path: Path) -> None:
    """The narrowing pass is skipped rather than answered from a pattern nothing read:
    reporting `src/mod.py` as no longer gated would be a certain finding resting on it."""
    base = _paths_repo(tmp_path, _filtered(_SCAFFOLDED_PATHS))
    _write(tmp_path, ".github/workflows/docs.yml", _filtered('    paths:\n      - "+build/**"\n'))
    _commit(tmp_path, "narrow the filter to one entry nothing can read")

    assert [m for m in _weakenings(tmp_path, base) if "alone no longer runs" in m] == []
    assert _filter_findings(tmp_path, base)


def test_an_unreadable_entry_inherited_from_the_base_is_a_hint(tmp_path: Path) -> None:
    """The change did not make it unreadable, and a run is not blocked by history. The two
    facts are two codes because a class belongs to a code, not to one occurrence of it."""
    broken = _SCAFFOLDED_PATHS + '      - "+build/**"\n'
    base = _paths_repo(tmp_path, _filtered(broken))
    _write(tmp_path, ".github/workflows/docs.yml", _filtered(broken + '      - "extra/**"\n'))
    _commit(tmp_path, "widen a filter that already held a broken entry")

    reported = _filter_findings(tmp_path, base)

    assert [f["code"] for f in reported] == [_NOT_COMPARED]
    assert reported[0]["severity"] == "warning"


def test_fixing_an_unreadable_entry_says_the_base_was_not_compared(tmp_path: Path) -> None:
    """The head reads, the base does not, so what the gate admitted there is unknown and
    no narrowing conclusion is available — the same posture as an unreadable base config."""
    base = _paths_repo(tmp_path, _filtered('    paths:\n      - "+build/**"\n'))
    _write(tmp_path, ".github/workflows/docs.yml", _filtered(_SCAFFOLDED_PATHS))
    _commit(tmp_path, "replace the broken entry with real ones")

    reported = _filter_findings(tmp_path, base)

    assert [f["code"] for f in reported] == [_NOT_COMPARED]
    assert "not compared" in reported[0]["message"]
    assert [m for m in _weakenings(tmp_path, base) if "alone no longer runs" in m] == []


def test_an_unreadable_entry_does_not_silence_the_rest_of_the_pass(tmp_path: Path) -> None:
    """The traceback took the whole check with it, so a broken filter hid every seal a
    change had broken. The flag axes are scored from the workflow, not from its filters."""
    base = _paths_repo(tmp_path, _filtered(_SCAFFOLDED_PATHS))
    weaker = _filtered(_SCAFFOLDED_PATHS + '      - "+build/**"\n').replace(
        "--strict --diff", "--diff"
    )
    _write(tmp_path, ".github/workflows/docs.yml", weaker)
    _commit(tmp_path, "drop --strict, and add an entry nothing can read")

    codes = {f["code"] for f in _findings(tmp_path, base)}

    assert _UNREADABLE in codes and "diff-integrity/gate-weakened" in codes


def test_a_valid_filter_beside_a_broken_one_still_matches() -> None:
    """An unreadable entry matches nothing rather than swallowing the list around it."""
    from irminsul.checks.diff_integrity import _filter_regex, _triggers, _unreadable

    assert all(_filter_regex(pattern) is None for pattern in _MALFORMED)
    assert _filter_regex("src/**") is not None
    assert _unreadable(("paths", ["src/**", "+build/**"])) == ["+build/**"]
    assert _unreadable(("paths", ["!+build/**"])) == ["!+build/**"]
    assert _unreadable(None) == [] and _unreadable(("paths", ["src/**"])) == []
    assert _triggers(("paths", ["src/**", "+build/**"]), "src/mod.py")
    assert not _triggers(("paths", ["+build/**"]), "build/mod.py")
    # `[` with no `]` anywhere is escaped rather than opened, so it stays readable.
    assert _filter_regex("src/[a.py") is not None


def test_swapping_a_gate_flag_for_a_stronger_one_is_not_a_weakening(tmp_path: Path) -> None:
    """`--strict` and `--fail-on` are mutually exclusive, so migrating between them
    has to drop one — which a per-flag count read as switching the gate off.

    Strength is what counts, not presence: `--fail-on hint,time` fails on the same three
    classes `--strict` does, so the swap gates exactly as hard.
    """
    _workflow_repo(tmp_path)
    _write(
        tmp_path,
        ".github/workflows/docs.yml",
        'jobs:\n  docs:\n    steps:\n      - run: irminsul check --diff "origin/main" --fail-on hint,time\n',
    )
    base = _commit(tmp_path, "gate on every class")
    _write(
        tmp_path,
        ".github/workflows/docs.yml",
        'jobs:\n  docs:\n    steps:\n      - run: irminsul check --diff "origin/main" --strict\n',
    )
    _commit(tmp_path, "say it with --strict instead")

    assert "diff-integrity/gate-weakened" not in _codes(tmp_path, base)


def test_trading_strict_for_a_narrower_fail_on_is_a_weakening(tmp_path: Path) -> None:
    """`--strict` fails on certain, hint and time; `--fail-on time` lets hints pass.
    Treating the two as interchangeable spellings accepted a real weakening."""
    _workflow_repo(tmp_path)
    _write(
        tmp_path,
        ".github/workflows/docs.yml",
        'jobs:\n  docs:\n    steps:\n      - run: irminsul check --diff "origin/main" --strict\n',
    )
    base = _commit(tmp_path, "strict gate")
    _write(
        tmp_path,
        ".github/workflows/docs.yml",
        'jobs:\n  docs:\n    steps:\n      - run: irminsul check --diff "origin/main" --fail-on time\n',
    )
    _commit(tmp_path, "let hints pass")

    assert "diff-integrity/gate-weakened" in _codes(tmp_path, base)


def test_wrapping_a_long_invocation_is_not_a_weakening(tmp_path: Path) -> None:
    """Strength is scored per line, so a `run: |` block that wraps its flags across
    continuation lines put `--strict` and `--diff` on lines without `irminsul check` —
    and reformatting for readability failed CI with two certain findings."""
    _workflow_repo(tmp_path)
    _write(
        tmp_path,
        ".github/workflows/docs.yml",
        'jobs:\n  docs:\n    steps:\n      - run: irminsul check --strict --diff "origin/main"\n',
    )
    base = _commit(tmp_path, "one long line")

    _write(
        tmp_path,
        ".github/workflows/docs.yml",
        "jobs:\n  docs:\n    steps:\n"
        "      - run: |\n"
        "          irminsul check \\\n"
        "            --strict \\\n"
        '            --diff "origin/main"\n',
    )
    _commit(tmp_path, "wrap it for readability")

    assert "diff-integrity/gate-weakened" not in _codes(tmp_path, base)


def test_commenting_out_the_check_step_is_a_weakening(tmp_path: Path) -> None:
    """The count read raw YAML, and a commented-out step still contains every token."""
    base = _workflow_repo(tmp_path)
    _write(
        tmp_path,
        ".github/workflows/docs.yml",
        "jobs:\n  docs:\n    steps:\n"
        '      # - run: irminsul check --diff "origin/main"\n'
        "      - run: echo skipped\n",
    )
    _commit(tmp_path, "comment the gate out")

    assert "diff-integrity/gate-weakened" in _codes(tmp_path, base)


def test_renaming_a_step_to_mention_the_tool_is_not_a_weakening(tmp_path: Path) -> None:
    """The count was a plain substring over the whole file, so a step `name:` that
    mentions `irminsul check` counted as an invocation."""
    _workflow_repo(tmp_path)
    _write(
        tmp_path,
        ".github/workflows/docs.yml",
        "jobs:\n  docs:\n    steps:\n      - name: run irminsul check in CI\n"
        '        run: irminsul check --diff "origin/main"\n',
    )
    base = _commit(tmp_path, "name the step after the command")

    _write(
        tmp_path,
        ".github/workflows/docs.yml",
        "jobs:\n  docs:\n    steps:\n      - name: docs gate\n"
        '        run: irminsul check --diff "origin/main"\n',
    )
    _commit(tmp_path, "rename the step")

    assert "diff-integrity/gate-weakened" not in _codes(tmp_path, base)


_GOVERNING = (
    "---\nid: widget\ntitle: Widget\nstatus: stable\n"
    "claims:\n  - id: widget-stateless\n    state: implemented\n    kind: invariant\n"
    "    relation: governs-evidence\n"
    "    claim: The widget never persists state between calls.\n"
    "    evidence:\n      - src/widget.py\n"
    "---\n\n# Widget\n\nIt runs.\n"
)


def _governing_repo(root: Path) -> str:
    _repo(root)
    _write(root, "src/widget.py", "def run():\n    return 1\n")
    _write(root, "docs/components/widget.md", _GOVERNING)
    return _commit(root, "governing claim")


def test_rewording_a_governing_claim_is_an_error(tmp_path: Path) -> None:
    """Editing the contract to match the code it forbids must not pass quietly."""
    base = _governing_repo(tmp_path)
    _write(
        tmp_path,
        "docs/components/widget.md",
        _GOVERNING.replace("never persists state", "may persist state"),
    )
    _commit(tmp_path, "reword the contract")

    assert "diff-integrity/governing-claim-changed" in _codes(tmp_path, base)


def test_downgrading_the_relation_is_an_error(tmp_path: Path) -> None:
    """Protection is read from the base, so a change cannot lower its own."""
    base = _governing_repo(tmp_path)
    _write(
        tmp_path,
        "docs/components/widget.md",
        _GOVERNING.replace("relation: governs-evidence", "relation: follows-evidence").replace(
            "never persists state", "may persist state"
        ),
    )
    _commit(tmp_path, "downgrade then reword")

    assert "diff-integrity/governing-claim-changed" in _codes(tmp_path, base)


def test_a_decision_record_authorizes_the_change(tmp_path: Path) -> None:
    base = _governing_repo(tmp_path)
    _write(
        tmp_path,
        "docs/components/widget.md",
        _GOVERNING.replace("never persists state", "may persist state"),
    )
    _write(
        tmp_path,
        "docs/decisions/allow-widget-state.md",
        "---\nid: allow-widget-state\ntitle: Allow widget state\nstatus: stable\n---\n\n"
        "# Allow widget state\n\n## Decision\n\nThe claim `widget-stateless` is retired.\n",
    )
    _commit(tmp_path, "authorize the intent change")

    assert "diff-integrity/governing-claim-changed" not in _codes(tmp_path, base)


def test_an_untouched_governing_claim_is_silent(tmp_path: Path) -> None:
    base = _governing_repo(tmp_path)
    _write(tmp_path, "src/widget.py", "def run():\n    return 2\n")
    _commit(tmp_path, "change the code only")

    assert "diff-integrity/governing-claim-changed" not in _codes(tmp_path, base)


def _without_claims(text: str) -> str:
    return text[: text.index("claims:")] + text[text.index("---\n\n# Widget") :]


def test_removing_a_governing_claim_with_its_evidence_is_an_error(tmp_path: Path) -> None:
    """Deleting the code releases a claim that only described it, but a contract does not
    end because the code it governed was deleted alongside it."""
    base = _governing_repo(tmp_path)
    _write(tmp_path, "docs/components/widget.md", _without_claims(_GOVERNING))
    (tmp_path / "src" / "widget.py").unlink()
    _commit(tmp_path, "drop the contract and the code together")

    assert "diff-integrity/governing-claim-removed" in _codes(tmp_path, base)


def test_removing_a_governing_claim_whose_evidence_survives_is_an_error(tmp_path: Path) -> None:
    base = _governing_repo(tmp_path)
    _write(tmp_path, "docs/components/widget.md", _without_claims(_GOVERNING))
    _commit(tmp_path, "drop the contract")

    assert "diff-integrity/governing-claim-removed" in _codes(tmp_path, base)


def test_renaming_a_governing_claim_while_deleting_its_evidence_is_an_error(
    tmp_path: Path,
) -> None:
    base = _governing_repo(tmp_path)
    _write(
        tmp_path,
        "docs/components/widget.md",
        _GOVERNING.replace("widget-stateless", "widget-stateful").replace(
            "      - src/widget.py\n", "      - src/other.py\n"
        ),
    )
    _write(tmp_path, "src/other.py", "Y = 1\n")
    (tmp_path / "src" / "widget.py").unlink()
    _commit(tmp_path, "rename the contract away")

    assert "diff-integrity/governing-claim-removed" in _codes(tmp_path, base)


def test_deleting_the_doc_and_code_of_a_governing_claim_is_an_error(tmp_path: Path) -> None:
    base = _governing_repo(tmp_path)
    (tmp_path / "docs" / "components" / "widget.md").unlink()
    (tmp_path / "src" / "widget.py").unlink()
    _commit(tmp_path, "delete the doc and the code")

    assert "diff-integrity/governing-claim-removed" in _codes(tmp_path, base)


def test_downgrading_before_deleting_a_governing_claim_is_still_an_error(tmp_path: Path) -> None:
    """Protection is read from the base, so lowering it in an earlier commit of the same
    change does not release the claim in a later one."""
    base = _governing_repo(tmp_path)
    _write(
        tmp_path,
        "docs/components/widget.md",
        _GOVERNING.replace("relation: governs-evidence", "relation: follows-evidence"),
    )
    _commit(tmp_path, "downgrade first")
    _write(tmp_path, "docs/components/widget.md", _without_claims(_GOVERNING))
    (tmp_path / "src" / "widget.py").unlink()
    _commit(tmp_path, "then delete it with its code")

    assert "diff-integrity/governing-claim-removed" in _codes(tmp_path, base)


def test_a_decision_record_ends_a_governing_claim_with_its_code(tmp_path: Path) -> None:
    base = _governing_repo(tmp_path)
    _write(tmp_path, "docs/components/widget.md", _without_claims(_GOVERNING))
    (tmp_path / "src" / "widget.py").unlink()
    _write(
        tmp_path,
        "docs/decisions/retire-the-widget.md",
        "---\nid: retire-the-widget\ntitle: Retire the widget\nstatus: stable\n---\n\n"
        "# Retire the widget\n\n## Decision\n\nThe widget is removed, and `widget-stateless` "
        "ends with it.\n",
    )
    _commit(tmp_path, "retire the widget by decision")

    codes = _codes(tmp_path, base)
    assert "diff-integrity/governing-claim-removed" not in codes
    assert "diff-integrity/claim-removed" not in codes


def test_moving_a_governing_claim_to_another_doc_is_not_a_removal(tmp_path: Path) -> None:
    base = _governing_repo(tmp_path)
    _write(tmp_path, "docs/components/widget.md", _without_claims(_GOVERNING))
    _write(
        tmp_path,
        "docs/components/gadget.md",
        _GOVERNING.replace("id: widget\ntitle: Widget", "id: gadget\ntitle: Gadget").replace(
            "# Widget", "# Gadget"
        ),
    )
    _commit(tmp_path, "move the contract to the doc that now owns it")

    assert "diff-integrity/governing-claim-removed" not in _codes(tmp_path, base)


_ACTION_WORKFLOW = (
    "on:\n  pull_request:\njobs:\n  check:\n    runs-on: ubuntu-latest\n    steps:\n"
    "      - uses: actions/checkout@v4\n"
    "      - name: Gate\n        uses: acme/irminsul@v1\n        with:\n"
    "          diff: origin/${{ github.base_ref }}\n          fail-on: hint\n"
)


def _action_repo(root: Path) -> str:
    _repo(root)
    _write(root, ".github/workflows/docs.yml", _ACTION_WORKFLOW)
    return _commit(root, "gate through the composite Action")


def test_gate_strength_scores_the_composite_action() -> None:
    """Scaffolded workflows gate through `uses:` and `with:` inputs, which never contain
    the words `irminsul check`, so the seal read every adopter's gate as absent."""
    from irminsul.checks.diff_integrity import _gate_strength

    assert _gate_strength(_ACTION_WORKFLOW) == (1, 2, 2, 1)
    strict = _ACTION_WORKFLOW.replace("fail-on: hint", "strict: true")
    assert _gate_strength(strict) == (1, 3, 2, 1)
    lookalike = _ACTION_WORKFLOW.replace("acme/irminsul@v1", "acme/irminsul-lint@v1")
    assert _gate_strength(lookalike) == (0, 0, 0, 0)


def test_the_scaffolded_pr_workflow_is_scored_as_a_gate(tmp_path: Path) -> None:
    from irminsul.checks.diff_integrity import _gate_strength
    from irminsul.init.command import InitAnswers, write_scaffold

    answers = InitAnswers(
        project_name="demo",
        languages=["python"],
        source_roots=["src"],
        github_user="acme",
        today="2026-09-17",
    )
    write_scaffold(tmp_path, answers)

    workflows = tmp_path / ".github" / "workflows"
    assert _gate_strength((workflows / "docs-pr.yml").read_text(encoding="utf-8")) == (1, 1, 2, 1)
    nightly = (workflows / "docs-nightly.yml").read_text(encoding="utf-8")
    assert _gate_strength(nightly) == (1, 2, 0, 1)


def test_dropping_the_diff_input_from_the_action_is_an_error(tmp_path: Path) -> None:
    base = _action_repo(tmp_path)
    _write(
        tmp_path,
        ".github/workflows/docs.yml",
        _ACTION_WORKFLOW.replace("          diff: origin/${{ github.base_ref }}\n", ""),
    )
    _commit(tmp_path, "drop the diff input")

    assert "diff-integrity/gate-weakened" in _codes(tmp_path, base)


def test_commenting_out_the_action_step_is_an_error(tmp_path: Path) -> None:
    base = _action_repo(tmp_path)
    commented = _ACTION_WORKFLOW.replace(
        "      - name: Gate\n        uses: acme/irminsul@v1\n        with:\n"
        "          diff: origin/${{ github.base_ref }}\n          fail-on: hint\n",
        "      # - name: Gate\n      #   uses: acme/irminsul@v1\n",
    )
    _write(tmp_path, ".github/workflows/docs.yml", commented)
    _commit(tmp_path, "comment the gate out")

    assert "diff-integrity/gate-weakened" in _codes(tmp_path, base)


def test_swapping_the_action_for_an_equal_run_step_is_not_a_weakening(tmp_path: Path) -> None:
    base = _action_repo(tmp_path)
    _write(
        tmp_path,
        ".github/workflows/docs.yml",
        _ACTION_WORKFLOW.replace(
            "      - name: Gate\n        uses: acme/irminsul@v1\n        with:\n"
            "          diff: origin/${{ github.base_ref }}\n          fail-on: hint\n",
            '      - run: irminsul check --fail-on hint --diff "origin/main"\n',
        ),
    )
    _commit(tmp_path, "call the CLI directly")

    assert "diff-integrity/gate-weakened" not in _codes(tmp_path, base)


def test_a_freshly_initialized_repo_seals_its_scaffolded_gate(tmp_path: Path) -> None:
    """End to end in an adopter repository: `irminsul init`, then a change that deletes the
    `diff:` input the scaffolded PR workflow gates with."""
    root = tmp_path / "adopter"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("X = 1\n", encoding="utf-8")
    _git(root, "init", "-q")
    result = runner.invoke(
        app, ["init", "--no-interactive", "--language", "python", "--path", str(root)]
    )
    assert result.exit_code == 0, result.output
    base = _commit(root, "adopt irminsul")

    workflow = root / ".github" / "workflows" / "docs-pr.yml"
    text = workflow.read_text(encoding="utf-8")
    weakened = "\n".join(
        line for line in text.splitlines() if "diff:" not in line and line.strip() != "with:"
    )
    workflow.write_text(weakened + "\n", encoding="utf-8")
    _commit(root, "stop gating the diff")

    assert "diff-integrity/gate-weakened" in _codes(root, base)
