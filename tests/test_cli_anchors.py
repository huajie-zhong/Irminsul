"""Tests for the `irminsul anchors` report output formats."""

from __future__ import annotations

import json
import os
import re
import shlex
from pathlib import Path

import pytest
from typer.testing import CliRunner

from irminsul.anchors import parse_anchors
from irminsul.cli import app

from .conftest import (
    anchor_repo,
    check_findings,
    cli_output,
    commit_all,
    git_init,
    invoke,
    load_graph,
    write,
    write_config,
)

runner = CliRunner()


def test_anchors_report_plain(tmp_path: Path) -> None:
    repo = anchor_repo(tmp_path)
    result = runner.invoke(app, ["anchors", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    assert "1 anchor finding(s)" in result.output


def test_anchors_report_json(tmp_path: Path) -> None:
    repo = anchor_repo(tmp_path)
    result = runner.invoke(app, ["anchors", "--format", "json", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["version"] == 1
    assert len(data["findings"]) == 1
    finding = data["findings"][0]
    assert finding["check"] == "claim-anchor"
    assert finding["severity"] == "info"
    assert data["summary"] == {"errors": 0, "warnings": 0, "info": 1}


def _two_doc_repo(tmp_path: Path) -> Path:
    repo = anchor_repo(tmp_path)
    (repo / "src" / "other.py").write_text("def beta():\n    return 1\n", encoding="utf-8")
    (repo / "docs" / "components" / "d.md").write_text(
        "---\nid: d\ntitle: D\nstatus: stable\n"
        "describes: [src/other.py]\n---\n\n# D\n\nBeta does a thing.\n"
        "<!-- anchor: src/other.py#beta @sha256:0000deadbeef -->\n",
        encoding="utf-8",
    )
    doc = repo / "docs" / "components" / "c.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(
            "<!-- anchor: src/mod.py#alpha -->",
            "<!-- anchor: src/mod.py#alpha @sha256:0000deadbeef -->",
        ),
        encoding="utf-8",
    )
    return repo


def _pins(repo: Path) -> dict[str, str]:
    import re

    return {
        name: re.search(
            r"sha256:([0-9a-f]+)", (repo / "docs" / "components" / name).read_text("utf-8")
        ).group(1)
        for name in ("c.md", "d.md")
    }


def test_re_pin_without_a_doc_is_refused(tmp_path: Path) -> None:
    """One command used to stamp every drift signal in the repository."""
    repo = _two_doc_repo(tmp_path)
    before = _pins(repo)

    result = runner.invoke(app, ["anchors", "--re-pin", "--path", str(repo)])

    assert result.exit_code == 2
    assert "--doc" in result.output
    assert _pins(repo) == before


def test_re_pin_writes_only_the_named_doc(tmp_path: Path) -> None:
    repo = _two_doc_repo(tmp_path)
    before = _pins(repo)

    result = runner.invoke(
        app, ["anchors", "--re-pin", "--doc", "docs/components/c.md", "--path", str(repo)]
    )
    assert result.exit_code == 0, result.output

    after = _pins(repo)
    assert after["c.md"] != before["c.md"]
    assert after["d.md"] == before["d.md"], "re-pinned a doc the caller did not name"


def test_re_pin_takes_a_doc_id(tmp_path: Path) -> None:
    repo = _two_doc_repo(tmp_path)
    before = _pins(repo)

    result = runner.invoke(app, ["anchors", "--re-pin", "--doc", "c", "--path", str(repo)])
    assert result.exit_code == 0, result.output

    after = _pins(repo)
    assert after["c.md"] != before["c.md"]
    assert after["d.md"] == before["d.md"]


@pytest.mark.parametrize("mode", ["--re-pin", "--suggest"])
def test_a_doc_that_matches_nothing_is_refused(tmp_path: Path, mode: str) -> None:
    """An empty answer to a mistyped --doc read as "nothing to do"."""
    repo = _two_doc_repo(tmp_path)
    before = _pins(repo)

    result = runner.invoke(app, ["anchors", mode, "--doc", "no-such-doc", "--path", str(repo)])

    assert result.exit_code == 2
    assert "no doc with id or path no-such-doc" in result.output
    assert _pins(repo) == before


def test_re_pin_all_writes_every_doc(tmp_path: Path) -> None:
    repo = _two_doc_repo(tmp_path)
    before = _pins(repo)

    result = runner.invoke(app, ["anchors", "--re-pin", "--all", "--path", str(repo)])
    assert result.exit_code == 0, result.output

    after = _pins(repo)
    assert after["c.md"] != before["c.md"] and after["d.md"] != before["d.md"]


def test_repin_never_leaves_a_doc_truncated(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A write that fails mid-sweep leaves the doc exactly as it was, and is reported
    rather than escaping as a traceback."""
    repo = anchor_repo(tmp_path)
    doc = repo / "docs" / "components" / "c.md"
    (repo / "src" / "mod.py").write_text("def alpha():\n    return 2\n", encoding="utf-8")
    before = doc.read_text(encoding="utf-8")

    real_replace = os.replace

    def _boom(src, dst):  # type: ignore[no-untyped-def]
        if str(dst).endswith("c.md"):
            raise OSError("disk full")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", _boom)

    result = runner.invoke(app, ["anchors", "--re-pin", "--all", "--path", str(repo)])

    assert result.exit_code == 2
    assert doc.read_text(encoding="utf-8") == before, "the doc was left damaged"
    assert "could not re-pin" in cli_output(result)


def _drifted_claim_repo(tmp_path: Path) -> Path:
    """A foundation claim whose evidence was committed after the doc."""
    repo = tmp_path / "claims"
    (repo / "src").mkdir(parents=True)
    write_config(repo, project_name="claims", source_roots=["src"], enabled=["claim-provenance"])
    (repo / "src" / "mod.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    (repo / "src" / "util.py").write_text("LIMIT = 1\n", encoding="utf-8")
    doc = repo / "docs" / "foundation" / "rules.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "---\nid: rules\ntitle: Rules\nstatus: stable\ndescribes: []\nclaims:\n"
        "  - id: alpha-works\n    state: implemented\n    kind: invariant\n"
        "    claim: Alpha returns a number.\n    evidence:\n"
        "      - src/mod.py\n      - src/util.py\n---\n\n# Rules\n\n"
        "Alpha returns a number. <!-- claim:alpha-works -->\n",
        encoding="utf-8",
    )

    git_init(repo)
    commit_all(repo, "seed", when="2024-01-01T00:00:00Z")
    (repo / "src" / "mod.py").write_text("def alpha():\n    return 2\n", encoding="utf-8")
    commit_all(repo, "alpha returns two", when="2024-02-01T00:00:00Z")
    return repo


def _drift(repo: Path) -> list[str]:
    result = runner.invoke(app, ["check", "--format", "json", "--path", str(repo)])
    findings = json.loads(result.stdout)["findings"]
    return [f["message"] for f in findings if f["code"] == "claim-provenance/evidence-drift"]


def test_re_pin_pins_a_claims_evidence_as_reread(tmp_path: Path) -> None:
    from irminsul.anchors import file_pin

    repo = _drifted_claim_repo(tmp_path)
    doc = repo / "docs" / "foundation" / "rules.md"
    before = doc.read_text(encoding="utf-8")
    assert _drift(repo) == [
        "claim 'alpha-works' cites evidence changed after the doc: 'src/mod.py'"
    ]

    result = runner.invoke(app, ["anchors", "--re-pin", "--doc", "rules", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    assert "2 claim evidence pin(s)" in result.output

    pins = (
        "    pinned:\n"
        f"      src/mod.py: {file_pin(repo / 'src' / 'mod.py')}\n"
        f"      src/util.py: {file_pin(repo / 'src' / 'util.py')}\n"
    )
    expected = before.replace("      - src/util.py\n", "      - src/util.py\n" + pins)
    assert doc.read_text(encoding="utf-8") == expected
    assert _drift(repo) == []

    again = runner.invoke(app, ["anchors", "--re-pin", "--doc", "rules", "--path", str(repo)])
    assert "0 claim evidence pin(s)" in again.output
    assert doc.read_text(encoding="utf-8") == expected
    commit_all(repo, "re-pin", when="2024-02-15T00:00:00Z", paths=["docs/foundation/rules.md"])

    (repo / "src" / "mod.py").write_text(
        "def alpha():  # a comment\n    return 2\n", encoding="utf-8"
    )
    commit_all(repo, "comment alpha", when="2024-03-01T00:00:00Z", paths=["src/mod.py"])
    assert _drift(repo) == [], "a comment-only commit re-asked a re-read claim"

    (repo / "src" / "util.py").write_text("LIMIT = 2\n", encoding="utf-8")
    commit_all(repo, "raise the limit", when="2024-03-02T00:00:00Z", paths=["src/util.py"])
    assert _drift(repo) == [
        "claim 'alpha-works' cites evidence changed after the doc and since it was pinned: "
        "'src/util.py'"
    ]


def test_a_stale_pin_is_dropped_by_re_pin(tmp_path: Path) -> None:
    repo = _drifted_claim_repo(tmp_path)
    doc = repo / "docs" / "foundation" / "rules.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(
            "      - src/util.py\n",
            "      - src/util.py\n    pinned:\n      src/gone.py: sha256:0\n",
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["anchors", "--re-pin", "--doc", "rules", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    assert "claim alpha-works: src/gone.py (dropped)" in result.output
    assert "src/gone.py" not in doc.read_text(encoding="utf-8")
    assert "src/util.py: sha256:" in doc.read_text(encoding="utf-8")


def test_anchors_report_leaves_out_what_an_ignore_comment_answers(tmp_path: Path) -> None:
    """The report is `claim-anchor`'s findings as `irminsul check` reports them. It ran the
    check raw, so a finding a reasoned ignore comment had answered came back here."""
    repo = anchor_repo(tmp_path)
    doc = repo / "docs" / "components" / "c.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(
            "<!-- anchor:",
            '<!-- irminsul:ignore claim-anchor/unpinned reason="pinned at release" -->\n'
            "<!-- anchor:",
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["anchors", "--format", "json", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["findings"] == []


_RULES_DOC = (
    "---\nid: rules\ntitle: Rules\nstatus: stable\ndescribes: []\nclaims:\n"
    "  - id: alpha-works\n    state: implemented\n    kind: invariant\n"
    "    claim: Alpha returns a number.\n    evidence:\n"
    "      - src/mod.py\n      - src/util.py\n    pinned:\n"
    "      src/mod.py: sha256:0000\n      src/util.py: sha256:0000\n"
    "  - id: beta-works\n    state: implemented\n    kind: invariant\n"
    "    claim: Beta returns a number.\n    evidence:\n"
    "      - src/other.py\n    pinned:\n      src/other.py: sha256:0000\n"
    "---\n\n# Rules\n\n"
    "Alpha returns a number. <!-- claim:alpha-works -->\n"
    "<!-- anchor: src/mod.py#alpha @sha256:0000deadbeef -->\n\n"
    "Beta returns a number. <!-- claim:beta-works -->\n"
    "<!-- anchor: src/other.py#beta @sha256:0000deadbeef -->\n"
)


def _selector_repo(tmp_path: Path, *, newline: str = "\n") -> Path:
    """One doc with two claims and two anchors, every pin stale."""
    repo = tmp_path / "selectors"
    write_config(repo, project_name="selectors", source_roots=["src"])
    write(repo, "src/mod.py", "def alpha():\n    return 1\n")
    write(repo, "src/util.py", "LIMIT = 1\n")
    write(repo, "src/other.py", "def beta():\n    return 1\n")
    doc = repo / "docs" / "foundation" / "rules.md"
    doc.parent.mkdir(parents=True)
    doc.write_bytes(_RULES_DOC.replace("\n", newline).encode("utf-8"))
    return repo


def _selector_pins(repo: Path) -> dict[str, str]:
    """Every pin in the doc, named as a re-pin names the pin it moves."""
    node = load_graph(repo).nodes["rules"]
    pins = {
        f"claim {claim.id}: {path}": pin
        for claim in node.frontmatter.claims
        for path, pin in claim.pinned.items()
    }
    pins.update({f"anchor {a.target}": a.pinned or "" for a in parse_anchors(node.body)})
    return pins


def _moved(before: dict[str, str], after: dict[str, str]) -> set[str]:
    assert before.keys() == after.keys()
    return {name for name in before if before[name] != after[name]}


def _re_pin(repo: Path, *selectors: str) -> tuple[int, str]:
    return invoke(repo, "anchors", "--re-pin", "--doc", "rules", *selectors)


def test_re_pin_claim_moves_only_that_claims_pins(tmp_path: Path) -> None:
    repo = _selector_repo(tmp_path)
    before = _selector_pins(repo)

    code, output = _re_pin(repo, "--claim", "alpha-works")

    assert code == 0, output
    assert _moved(before, _selector_pins(repo)) == {
        "claim alpha-works: src/mod.py",
        "claim alpha-works: src/util.py",
    }


def test_re_pin_evidence_narrows_a_claim_to_one_file(tmp_path: Path) -> None:
    repo = _selector_repo(tmp_path)
    before = _selector_pins(repo)

    code, output = _re_pin(repo, "--claim", "alpha-works", "--evidence", "src/util.py")

    assert code == 0, output
    assert _moved(before, _selector_pins(repo)) == {"claim alpha-works: src/util.py"}


def test_re_pin_anchor_moves_only_that_anchor(tmp_path: Path) -> None:
    repo = _selector_repo(tmp_path)
    before = _selector_pins(repo)

    code, output = _re_pin(repo, "--anchor", "src/mod.py#alpha")

    assert code == 0, output
    assert _moved(before, _selector_pins(repo)) == {"anchor src/mod.py#alpha"}


def test_re_pin_takes_a_claim_and_an_anchor_together(tmp_path: Path) -> None:
    repo = _selector_repo(tmp_path)
    before = _selector_pins(repo)

    code, output = _re_pin(repo, "--claim", "beta-works", "--anchor", "src/mod.py#alpha")

    assert code == 0, output
    assert _moved(before, _selector_pins(repo)) == {
        "claim beta-works: src/other.py",
        "anchor src/mod.py#alpha",
    }


def test_re_pin_with_no_selector_names_every_pin_it_moved(tmp_path: Path) -> None:
    repo = _selector_repo(tmp_path)
    before = _selector_pins(repo)

    code, output = _re_pin(repo)

    assert code == 0, output
    assert _moved(before, _selector_pins(repo)) == set(before)
    lines = [line.strip() for line in output.splitlines()]
    assert "docs/foundation/rules.md" in lines
    for name in before:
        assert name in lines
    assert "re-pinned 2 anchor(s), 3 claim evidence pin(s)" in lines


@pytest.mark.parametrize(
    ("selectors", "message"),
    [
        (["--claim", "gamma"], "no claim with id gamma"),
        (["--claim", "alpha-works", "--claim", "gamma"], "no claim with id gamma"),
        (["--anchor", "src/mod.py#gamma"], "no anchor src/mod.py#gamma"),
        (["--anchor", "src/mod.py#alpha", "--anchor", "src/mod.py"], "no anchor src/mod.py "),
        (
            ["--claim", "alpha-works", "--evidence", "src/other.py"],
            "no selected claim cites src/other.py",
        ),
    ],
)
def test_a_selector_that_names_nothing_in_the_doc_writes_nothing(
    tmp_path: Path, selectors: list[str], message: str
) -> None:
    repo = _selector_repo(tmp_path)
    doc = repo / "docs" / "foundation" / "rules.md"
    before = doc.read_bytes()

    code, output = _re_pin(repo, *selectors)

    assert code == 2
    assert message in output
    assert doc.read_bytes() == before


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--re-pin", "--all", "--claim", "alpha-works"], "inside one doc"),
        (["--re-pin", "--all", "--anchor", "src/mod.py#alpha"], "inside one doc"),
        (["--re-pin", "--doc", "rules", "--evidence", "src/mod.py"], "name it with --claim"),
        (["--suggest", "--doc", "rules", "--claim", "alpha-works"], "narrow --re-pin"),
        (["--doc", "rules", "--anchor", "src/mod.py#alpha"], "narrow --re-pin"),
    ],
)
def test_a_selector_needs_re_pin_its_doc_and_for_evidence_its_claim(
    tmp_path: Path, args: list[str], message: str
) -> None:
    repo = _selector_repo(tmp_path)
    doc = repo / "docs" / "foundation" / "rules.md"
    before = doc.read_bytes()

    code, output = invoke(repo, "anchors", *args)

    assert code == 2
    assert message in output
    assert doc.read_bytes() == before


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_re_pin_keeps_the_docs_line_endings(tmp_path: Path, newline: str) -> None:
    repo = _selector_repo(tmp_path, newline=newline)
    doc = repo / "docs" / "foundation" / "rules.md"
    before = doc.read_bytes()

    code, output = _re_pin(repo)

    assert code == 0, output
    after = doc.read_bytes()
    assert after != before
    assert after.count(b"\r\n") == (after.count(b"\n") if newline == "\r\n" else 0)


def _run_suggested(repo: Path, suggestion: str) -> int:
    """Run the `irminsul ...` command a suggestion prints in a code span."""
    match = re.search(r"`irminsul ([^`]+)`", suggestion)
    assert match is not None, suggestion
    code, _ = invoke(repo, *shlex.split(match.group(1)))
    return code


def _anchor_findings(repo: Path) -> list[dict[str, str]]:
    _, output = invoke(repo, "anchors", "--format", "json")
    findings: list[dict[str, str]] = json.loads(output)["findings"]
    return findings


def test_the_evidence_drift_suggestion_re_pins_only_the_claim_it_reports(tmp_path: Path) -> None:
    repo = _drifted_claim_repo(tmp_path)
    (finding,) = [f for f in check_findings(repo) if f["code"] == "claim-provenance/evidence-drift"]

    assert (
        "`irminsul anchors --re-pin --doc docs/foundation/rules.md --claim alpha-works`"
        in (finding["suggestion"])
    )
    assert _run_suggested(repo, finding["suggestion"]) == 0
    assert _drift(repo) == []


@pytest.mark.parametrize("drifted", [False, True])
def test_the_claim_anchor_suggestion_re_pins_only_the_anchor_it_reports(
    tmp_path: Path, drifted: bool
) -> None:
    repo = anchor_repo(tmp_path)
    doc = repo / "docs" / "components" / "c.md"
    if drifted:
        doc.write_text(
            doc.read_text(encoding="utf-8").replace(
                "#alpha -->", "#alpha @sha256:0000deadbeef -->"
            ),
            encoding="utf-8",
        )
    (finding,) = _anchor_findings(repo)

    assert (
        "`irminsul anchors --re-pin --doc docs/components/c.md --anchor src/mod.py#alpha`"
        in (finding["suggestion"])
    )
    assert _run_suggested(repo, finding["suggestion"]) == 0
    assert _anchor_findings(repo) == []
