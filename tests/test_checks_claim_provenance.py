"""Tests for ClaimProvenanceCheck."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from irminsul.anchors import file_pin
from irminsul.checks.claim_provenance import CODE_UNKNOWN_CLAIM_REF, ClaimProvenanceCheck

from .conftest import (
    commit_all,
    commit_file,
    git_init,
    load_graph,
    write_config,
    write_doc,
)

_BASE = _dt.datetime(2025, 1, 1, 12, tzinfo=_dt.UTC)


def _at(minutes: int) -> _dt.datetime:
    """A fixed instant `minutes` after the base: commit order must not depend on the clock."""
    return _BASE + _dt.timedelta(minutes=minutes)


def test_claim_provenance_accepts_valid_claim_states(tmp_path: Path) -> None:
    write_config(tmp_path, source_roots=["src"])
    (tmp_path / "src" / "checks").mkdir(parents=True)
    (tmp_path / "src" / "checks" / "claim.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "action.yml").write_text("name: docs\n", encoding="utf-8")
    write_doc(
        tmp_path,
        "docs/components/claim-check.md",
        doc_id="claim-check",
        body="Implementation docs.",
    )
    write_doc(
        tmp_path,
        "docs/components/checks.md",
        doc_id="checks",
        body="Enablement docs.",
    )
    write_doc(
        tmp_path,
        "docs/rfcs/0001-thing.md",
        doc_id="0001-thing",
        status="draft",
        body="Future work.",
        frontmatter_extra=["rfc_state: open"],
    )
    write_doc(
        tmp_path,
        "docs/foundation/enforcement.md",
        doc_id="enforcement",
        body=(
            "CI blocks invalid docs. <!-- claim:enabled-claim -->\n\n"
            "A planned feature exists. <!-- claim:planned-claim -->"
        ),
        frontmatter_extra=[
            "claims:",
            "  - id: planned-claim",
            "    state: planned",
            "    kind: feature",
            "    claim: Planned feature.",
            "    evidence:",
            "      - docs/rfcs/0001-thing.md",
            "  - id: implemented-claim",
            "    state: implemented",
            "    kind: check",
            "    claim: Source exists.",
            "    evidence:",
            "      - src/checks/claim.py",
            "  - id: available-claim",
            "    state: available",
            "    kind: check",
            "    claim: Source and docs exist.",
            "    evidence:",
            "      - src/checks/claim.py",
            "      - docs/components/checks.md",
            "  - id: enabled-claim",
            "    state: enabled",
            "    kind: ci_gate",
            "    claim: Workflow evidence exists.",
            "    evidence:",
            "      - action.yml",
            "  - id: external-claim",
            "    state: external",
            "    kind: local_tool",
            "    claim: External config exists.",
            "    evidence:",
            "      - action.yml",
        ],
    )

    assert ClaimProvenanceCheck().run(load_graph(tmp_path)) == []


def test_claim_provenance_accepts_a_repo_root_source_root(tmp_path: Path) -> None:
    """`irminsul init` writes `source_roots = ["."]` for a flat Go repo, whose
    repo-relative prefix is the empty string — a prefix every path starts with.
    Classifying by that prefix alone made every path source evidence, and
    `state: external` is "process evidence that is *not* source", so no
    external claim could be satisfied. The docs tree, `irminsul.toml`, the
    Action and the workflows are not source even when the source root is the
    repo root."""
    write_config(tmp_path, source_roots=["."])
    (tmp_path / "main.go").write_text("package main\n", encoding="utf-8")
    (tmp_path / "action.yml").write_text("name: docs\n", encoding="utf-8")
    write_doc(
        tmp_path,
        "docs/guides/release.md",
        doc_id="release",
        body="The release runbook.",
    )
    write_doc(
        tmp_path,
        "docs/foundation/enforcement.md",
        doc_id="enforcement",
        body=(
            "The runbook exists. <!-- claim:process-claim -->\n\n"
            "The tool is configured. <!-- claim:config-claim -->\n\n"
            "The binary exists. <!-- claim:code-claim -->\n\n"
            "CI enforces it. <!-- claim:gate-claim -->"
        ),
        frontmatter_extra=[
            "claims:",
            "  - id: process-claim",
            "    state: external",
            "    kind: local_tool",
            "    claim: The runbook is documented.",
            "    evidence:",
            "      - docs/guides/release.md",
            "  - id: config-claim",
            "    state: external",
            "    kind: local_tool",
            "    claim: The tool is configured.",
            "    evidence:",
            "      - irminsul.toml",
            "  - id: code-claim",
            "    state: implemented",
            "    kind: check",
            "    claim: Source exists.",
            "    evidence:",
            "      - main.go",
            "  - id: gate-claim",
            "    state: enabled",
            "    kind: ci_gate",
            "    claim: Action evidence exists.",
            "    evidence:",
            "      - action.yml",
        ],
    )

    assert ClaimProvenanceCheck().run(load_graph(tmp_path)) == []


def test_repo_root_source_root_does_not_make_every_doc_implementation(tmp_path: Path) -> None:
    """The mirror: widening "everything is source" would also stop
    `implemented` and `available` from being checked at all."""
    write_config(tmp_path, source_roots=["."])
    (tmp_path / "main.go").write_text("package main\n", encoding="utf-8")
    write_doc(
        tmp_path,
        "docs/guides/notes.md",
        doc_id="notes",
        body="Background reading.",
    )
    write_doc(
        tmp_path,
        "docs/foundation/enforcement.md",
        doc_id="enforcement",
        body="The feature is built. <!-- claim:code-claim -->",
        frontmatter_extra=[
            "claims:",
            "  - id: code-claim",
            "    state: implemented",
            "    kind: check",
            "    claim: Source exists.",
            "    evidence:",
            "      - docs/guides/notes.md",
        ],
    )

    findings = ClaimProvenanceCheck().run(load_graph(tmp_path))

    assert [f.message for f in findings] == [
        "claim 'code-claim' has no evidence appropriate for state 'implemented'"
    ]


def test_claim_provenance_flags_state_inappropriate_evidence(tmp_path: Path) -> None:
    write_config(tmp_path, source_roots=["src"])
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "claim.py").write_text("x = 1\n", encoding="utf-8")
    write_doc(
        tmp_path,
        "docs/foundation/enforcement.md",
        doc_id="enforcement",
        body="CI blocks invalid docs. <!-- claim:enabled-claim -->",
        frontmatter_extra=[
            "claims:",
            "  - id: enabled-claim",
            "    state: enabled",
            "    kind: ci_gate",
            "    claim: Workflow evidence exists.",
            "    evidence:",
            "      - src/claim.py",
        ],
    )

    findings = ClaimProvenanceCheck().run(load_graph(tmp_path))

    assert len(findings) == 1
    assert findings[0].severity.value == "error"
    assert "state 'enabled'" in findings[0].message


def test_claim_provenance_rejects_evidence_that_escapes_the_repo(tmp_path: Path) -> None:
    """In `same-repo` every source file is addressable repo-relative, so a `..`
    segment names nothing the tool is willing to reason about, and the guard
    must reject it as well as an absolute path."""
    write_config(tmp_path, source_roots=["src"])
    (tmp_path / "src").mkdir()
    outside = tmp_path.parent / "outside"
    outside.mkdir(exist_ok=True)
    (outside / "claim.py").write_text("x = 1\n", encoding="utf-8")
    write_doc(
        tmp_path,
        "docs/foundation/enforcement.md",
        doc_id="enforcement",
        body="The module exists. <!-- claim:escaping-claim -->",
        frontmatter_extra=[
            "claims:",
            "  - id: escaping-claim",
            "    state: implemented",
            "    kind: check",
            "    claim: Source exists.",
            "    evidence:",
            "      - ../outside/claim.py",
        ],
    )

    findings = ClaimProvenanceCheck().run(load_graph(tmp_path))

    assert any("must not be absolute or escape the tree with '..'" in f.message for f in findings)
    assert all(f.severity.value == "error" for f in findings)


def test_claim_provenance_rejects_absolute_evidence(tmp_path: Path) -> None:
    write_config(tmp_path, source_roots=["src"])
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "claim.py").write_text("x = 1\n", encoding="utf-8")
    write_doc(
        tmp_path,
        "docs/foundation/enforcement.md",
        doc_id="enforcement",
        body="The module exists. <!-- claim:absolute-claim -->",
        frontmatter_extra=[
            "claims:",
            "  - id: absolute-claim",
            "    state: implemented",
            "    kind: check",
            "    claim: Source exists.",
            "    evidence:",
            f"      - {(tmp_path / 'src' / 'claim.py').as_posix()}",
        ],
    )

    findings = ClaimProvenanceCheck().run(load_graph(tmp_path))

    assert any("must not be absolute or escape the tree with '..'" in f.message for f in findings)


def test_claim_provenance_warns_on_unknown_claim_reference(tmp_path: Path) -> None:
    write_config(tmp_path, source_roots=["src"])
    write_doc(
        tmp_path,
        "docs/foundation/enforcement.md",
        doc_id="enforcement",
        body="CI blocks invalid docs. <!-- claim:missing -->",
    )

    findings = ClaimProvenanceCheck().run(load_graph(tmp_path))

    assert any("unknown structured claim reference" in finding.message for finding in findings)


def test_claim_provenance_reports_unknown_claim_ref_in_any_layer(tmp_path: Path) -> None:
    write_config(tmp_path, source_roots=["src"])
    write_doc(
        tmp_path,
        "docs/components/widget.md",
        doc_id="widget",
        body="CI blocks invalid docs. <!-- claim:missing -->",
    )

    findings = ClaimProvenanceCheck().run(load_graph(tmp_path))

    assert [finding.code for finding in findings] == [CODE_UNKNOWN_CLAIM_REF]


_DOC = "docs/foundation/enforcement.md"


def _claim_repo(tmp_path: Path, later_evidence: str | None = None, *, pinned: bool = False) -> Path:
    """A claim citing `action.yml`, pinned to it when `pinned`, with the doc committed after the
    evidence, and the evidence committed again after the doc when `later_evidence` is given."""
    write_config(tmp_path, source_roots=["src"])
    git_init(tmp_path)
    commit_all(tmp_path, "config", when=_at(0), paths=["irminsul.toml"])
    commit_file(tmp_path, "action.yml", "name: docs\n", "workflow", when=_at(0))
    write_doc(
        tmp_path,
        _DOC,
        doc_id="enforcement",
        body="CI blocks invalid docs. <!-- claim:enabled-claim -->",
        frontmatter_extra=[
            "claims:",
            "  - id: enabled-claim",
            "    state: enabled",
            "    kind: ci_gate",
            "    claim: Workflow evidence exists.",
            "    evidence:",
            "      - action.yml",
            *(
                ["    pinned:", f"      action.yml: {file_pin(tmp_path / 'action.yml')}"]
                if pinned
                else []
            ),
        ],
    )
    commit_all(tmp_path, "doc claim", when=_at(1), paths=[_DOC])
    if later_evidence is not None:
        commit_file(tmp_path, "action.yml", later_evidence, "workflow update", when=_at(2))
    return tmp_path


def _drift(root: Path, **graph_kwargs: object) -> list[str]:
    graph = load_graph(root, now=_dt.date(2025, 2, 1), **graph_kwargs)
    return [finding.message for finding in ClaimProvenanceCheck().run(graph)]


def test_claim_provenance_warns_when_evidence_changed_after_doc(tmp_path: Path) -> None:
    root = _claim_repo(tmp_path, "name: docs\non: [push]\n")

    findings = ClaimProvenanceCheck().run(load_graph(root))

    assert len(findings) == 1
    assert "changed after the doc" in findings[0].message


def test_evidence_edited_but_not_committed_drifts_from_a_committed_doc(tmp_path: Path) -> None:
    root = _claim_repo(tmp_path)
    assert _drift(root) == []

    (root / "action.yml").write_text("name: docs\non: [push]\n", encoding="utf-8")

    assert _drift(root) == [
        "claim 'enabled-claim' cites evidence changed after the doc: 'action.yml'"
    ]
    assert _drift(root, committed_only=True) == []


def test_a_doc_edited_beside_its_evidence_does_not_drift(tmp_path: Path) -> None:
    """The evidence files sort on both sides of the doc, so no tie-break by path passes."""
    root = _claim_repo(tmp_path)
    (root / "action.yml").write_text("name: docs\non: [push]\n", encoding="utf-8")
    config = root / "irminsul.toml"
    config.write_text(config.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    doc = root / _DOC
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(
            "      - action.yml\n", "      - action.yml\n      - irminsul.toml\n"
        )
        + "\nPush runs it.\n",
        encoding="utf-8",
    )

    assert _drift(root) == []


def test_editing_the_doc_answers_committed_drift_before_the_commit(tmp_path: Path) -> None:
    root = _claim_repo(tmp_path, "name: docs\non: [push]\n")
    assert len(_drift(root)) == 1

    doc = root / _DOC
    doc.write_text(doc.read_text(encoding="utf-8") + "\nPush runs it.\n", encoding="utf-8")

    assert _drift(root) == []
    assert len(_drift(root, committed_only=True)) == 1


def test_evidence_edited_after_a_pin_drifts_until_the_pin_is_renewed(tmp_path: Path) -> None:
    root = _claim_repo(tmp_path, pinned=True)
    evidence = root / "action.yml"
    old_pin = file_pin(evidence)
    evidence.write_text("name: docs\non: [push]\n", encoding="utf-8")

    assert _drift(root) == [
        "claim 'enabled-claim' cites evidence changed after the doc and since it was pinned: "
        "'action.yml'"
    ]
    assert _drift(root, committed_only=True) == []

    doc = root / _DOC
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(old_pin, file_pin(evidence)), encoding="utf-8"
    )

    assert _drift(root) == []


def test_a_pinned_claim_answered_by_an_uncommitted_re_pin_does_not_drift(tmp_path: Path) -> None:
    root = _claim_repo(tmp_path, "name: docs\non: [push]\n", pinned=True)
    assert len(_drift(root)) == 1

    doc = root / _DOC
    text = doc.read_text(encoding="utf-8")
    stale = text.split("action.yml: ", 1)[1].split("\n", 1)[0].strip()
    doc.write_text(text.replace(stale, str(file_pin(root / "action.yml"))), encoding="utf-8")

    assert _drift(root) == []
    assert _drift(root, committed_only=True) == []


def test_a_pin_keeps_a_reread_claim_answered_through_a_formatting_commit(
    tmp_path: Path,
) -> None:
    root = _claim_repo(tmp_path, "name:   docs\n\n", pinned=True)

    assert ClaimProvenanceCheck().run(load_graph(root)) == []


def test_a_pinned_claim_drifts_when_its_evidence_changes(tmp_path: Path) -> None:
    root = _claim_repo(tmp_path, "name: docs\non: [push]\n", pinned=True)

    findings = ClaimProvenanceCheck().run(load_graph(root))

    assert [f.message for f in findings] == [
        "claim 'enabled-claim' cites evidence changed after the doc and since it was pinned: "
        "'action.yml'"
    ]
    assert "--re-pin --doc docs/foundation/enforcement.md --claim enabled-claim`" in (
        findings[0].suggestion or ""
    )


def test_updating_the_doc_clears_a_stale_pin_as_it_would_without_one(tmp_path: Path) -> None:
    """A pin only ever removes drift, so the protocol's usual fix still works."""
    root = _claim_repo(tmp_path, "name: docs\non: [push]\n", pinned=True)
    doc = root / "docs" / "foundation" / "enforcement.md"
    commit_file(
        root,
        "docs/foundation/enforcement.md",
        doc.read_text(encoding="utf-8").replace("Workflow evidence", "Push workflow evidence"),
        "doc follows the workflow",
        when=_at(3),
    )

    assert ClaimProvenanceCheck().run(load_graph(root)) == []


def test_claim_provenance_validates_evidence_in_a_component_doc(tmp_path: Path) -> None:
    """A governing claim in a component doc is enforced against change, so its evidence has
    to exist; checking that says nothing about whether the claim is true."""
    write_config(tmp_path, source_roots=["src"])
    write_doc(
        tmp_path,
        "docs/components/widget.md",
        doc_id="widget",
        body="The widget keeps no state.",
        frontmatter_extra=[
            "claims:",
            "  - id: widget-stateless",
            "    state: implemented",
            "    kind: invariant",
            "    relation: governs-evidence",
            "    claim: The widget keeps no state.",
            "    evidence:",
            "      - src/gone.py",
        ],
    )

    findings = ClaimProvenanceCheck().run(load_graph(tmp_path))

    assert [finding.code for finding in findings] == ["claim-provenance/evidence-path-missing"]


def test_claim_provenance_reports_certain_codes_on_a_draft(tmp_path: Path) -> None:
    """A marker naming no claim and evidence that does not exist are wrong about something
    outside the doc, so `status: draft` does not excuse them."""
    write_config(tmp_path, source_roots=["src"])
    write_doc(
        tmp_path,
        "docs/foundation/enforcement.md",
        doc_id="enforcement",
        status="draft",
        body="The gate holds. <!-- claim:missing -->",
        frontmatter_extra=[
            "claims:",
            "  - id: gate-holds",
            "    state: implemented",
            "    kind: invariant",
            "    claim: The gate holds.",
            "    evidence:",
            "      - src/gone.py",
        ],
    )

    findings = ClaimProvenanceCheck().run(load_graph(tmp_path))

    assert sorted(f.code for f in findings) == [
        "claim-provenance/evidence-path-missing",
        "claim-provenance/unknown-claim-ref",
    ]
