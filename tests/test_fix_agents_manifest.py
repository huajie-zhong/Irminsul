"""`irminsul fix` writes the agent manifest's generated section, which `agents-manifest`
checks; it is the only generated artifact."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from irminsul.cli import app
from irminsul.regen.agents_md import GENERATED_END, GENERATED_START, replace_generated_section

from .conftest import check_findings, write_config

runner = CliRunner()

_MANIFEST = Path("docs") / "AGENTS.md"


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    write_config(repo, source_roots=["src"], enabled=["agents-manifest"])
    src = repo / "src" / "mylib"
    src.mkdir(parents=True)
    (src / "core.py").write_text("def run(): pass\n", encoding="utf-8")
    (repo / "docs").mkdir()
    return repo


def _check_codes(repo: Path) -> list[str]:
    return [finding["code"] for finding in check_findings(repo)]


def _fix(repo: Path) -> str:
    result = runner.invoke(app, ["fix", "--path", str(repo)])
    assert result.exit_code == 0, result.output
    return result.output


def test_fix_scaffolds_a_missing_manifest(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    assert _check_codes(repo) == ["agents-manifest/manifest-missing"]

    _fix(repo)

    text = (repo / _MANIFEST).read_text(encoding="utf-8")
    assert "<!-- agents-manifest:generated-start -->" in text
    assert "<!-- agents-manifest:generated-end -->" in text
    assert "## Foundations" in text
    assert "## Protocol" in text
    assert _check_codes(repo) == []


def _law_3_line(text: str) -> str:
    [line] = [line for line in text.splitlines() if "**Law 3.**" in line]
    return line.strip()


def test_a_scaffolded_manifest_holds_the_laws_and_points_at_the_loop(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)

    _fix(repo)

    text = (repo / _MANIFEST).read_text(encoding="utf-8")
    assert "## Foundations" in text
    assert "## Protocol" in text
    assert "### The Layers" not in text

    protocol = text.split("## Protocol", 1)[1]
    [paragraph] = [line for line in protocol.splitlines() if line.strip()]
    assert "AGENTS.md" in paragraph

    principles = Path(__file__).resolve().parents[1] / "docs" / "foundation" / "principles.md"
    assert _law_3_line(text) == _law_3_line(principles.read_text(encoding="utf-8"))


def test_fix_rewrites_a_drifted_section_and_keeps_curated_ones(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    _fix(repo)
    manifest = repo / _MANIFEST
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "## Foundations", "## Foundations\n\nCURATED EDIT SURVIVES"
        ),
        encoding="utf-8",
    )
    (repo / "docs" / "components").mkdir()
    (repo / "docs" / "components" / "core.md").write_text(
        "---\nid: core\ntitle: Core\nstatus: stable\ndescribes:\n  - src/mylib/core.py\n---\n\n"
        "# Core\n",
        encoding="utf-8",
    )
    assert _check_codes(repo) == ["agents-manifest/generated-section-drift"]

    _fix(repo)

    text = manifest.read_text(encoding="utf-8")
    assert "CURATED EDIT SURVIVES" in text
    assert "components/core.md" in text
    assert _check_codes(repo) == []


def test_the_drift_finding_names_the_fix_that_clears_it(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    _fix(repo)
    start = "<!-- agents-manifest:generated-start -->"
    (repo / _MANIFEST).write_text(
        (repo / _MANIFEST).read_text(encoding="utf-8").replace(start, f"{start}\n\nstale row"),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["check", "--format", "json", "--path", str(repo)])
    [finding] = json.loads(result.output)["findings"]

    assert finding["code"] == "agents-manifest/generated-section-drift"
    assert finding["fix_command"] == "irminsul fix --only agents-manifest"


def test_no_fix_rebuilds_a_manifest_whose_markers_do_not_parse(tmp_path: Path) -> None:
    """Rebuilding it from the template would delete every curated section."""
    repo = _make_repo(tmp_path)
    _fix(repo)
    manifest = repo / _MANIFEST
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("<!-- agents-manifest:generated-end -->", "")
        + "\n## Curated\n\nAuthored guidance that must survive.\n",
        encoding="utf-8",
    )
    before = manifest.read_text(encoding="utf-8")
    assert "agents-manifest/missing-generated-markers" in _check_codes(repo)

    assert "no automatic fixes available" in _fix(repo)
    assert manifest.read_text(encoding="utf-8") == before


def test_no_fix_chooses_between_two_generated_pairs(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    _fix(repo)
    manifest = repo / _MANIFEST
    text = manifest.read_text(encoding="utf-8")
    block = text[text.index(GENERATED_START) : text.index(GENERATED_END) + len(GENERATED_END)]
    manifest.write_text(f"{text}\n{block}\n", encoding="utf-8")
    (repo / "docs" / "components").mkdir()
    (repo / "docs" / "components" / "core.md").write_text(
        "---\nid: core\ntitle: Core\nstatus: stable\ndescribes:\n  - src/mylib/core.py\n---\n\n"
        "# Core\n",
        encoding="utf-8",
    )
    before = manifest.read_text(encoding="utf-8")
    assert _check_codes(repo) == ["agents-manifest/missing-generated-markers"]

    assert "no automatic fixes available" in _fix(repo)
    assert manifest.read_text(encoding="utf-8") == before


def test_the_generated_section_is_replaced_beside_a_fenced_example_of_the_markers() -> None:
    example = f"```\n{GENERATED_START}\nan example\n{GENERATED_END}\n```\n"
    text = f"{example}{GENERATED_START}\nold row\n{GENERATED_END}\ntail\n"

    assert replace_generated_section(text, "new row\n") == (
        f"{example}{GENERATED_START}\n\nnew row\n\n{GENERATED_END}\ntail\n"
    )


def test_the_generated_section_is_replaced_only_for_one_start_before_one_end() -> None:
    pair = f"{GENERATED_START}\nrow\n{GENERATED_END}\n"

    assert replace_generated_section(pair + pair, "new row") is None
    assert replace_generated_section(f"{GENERATED_END}\n{GENERATED_START}\n", "new row") is None
    assert replace_generated_section("no markers\n", "new row") is None


def test_no_fix_rewrites_a_manifest_that_is_not_utf8(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    _fix(repo)
    manifest = repo / _MANIFEST
    manifest.write_text(manifest.read_text(encoding="utf-8"), encoding="utf-16")
    as_written = manifest.read_bytes()
    assert _check_codes(repo) == ["agents-manifest/manifest-unreadable"]

    assert "no automatic fixes available" in _fix(repo)
    assert manifest.read_bytes() == as_written
