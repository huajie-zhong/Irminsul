"""End-to-end tests for `irminsul seed` and its `init` integration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from irminsul.checks.foundation_readiness import FoundationReadinessCheck
from irminsul.cli import app
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph
from irminsul.seed.command import SeedError, gather_answers_from_flags

from .conftest import cli_output, load_graph, seed_repo

runner = CliRunner()

_FLAGS = [
    "--principle",
    "Docs and code evolve together",
    "--idea",
    "A CLI that enforces doc structure in CI",
    "--belief",
    "Drift is cheaper to prevent than to repair",
    "--first-user",
    "A solo maintainer adopting the system",
    "--non-goals",
    "Hosting a server; Running an LLM in the hard path",
    "--direction-risks",
    "Becoming a generic linter",
]


def _fresh_repo(tmp_path: Path) -> Path:
    target = tmp_path / "proj"
    result = runner.invoke(
        app,
        [
            "init",
            "--fresh",
            "--language",
            "python",
            "--no-interactive",
            "--path",
            str(target),
        ],
    )
    assert result.exit_code == 0, result.stdout
    return target


def _seed_no_interactive(repo: Path, *extra: str) -> object:
    return runner.invoke(app, ["seed", "--no-interactive", *_FLAGS, *extra, "--path", str(repo)])


def test_seed_with_flags_writes_the_two_foundation_docs(tmp_path: Path) -> None:
    repo = _fresh_repo(tmp_path)
    result = _seed_no_interactive(repo)
    assert result.exit_code == 0, result.stdout

    principles = (repo / "docs/foundation/principles.md").read_text(encoding="utf-8")
    assert "Docs and code evolve together" in principles
    assert "A solo maintainer adopting the system" in principles

    overview = (repo / "docs/architecture/overview.md").read_text(encoding="utf-8")
    assert "A CLI that enforces doc structure in CI" in overview

    # The principles and overview docs only: no decision record and no RFC.
    assert result.stdout.count(".md") == 2, result.stdout
    assert not (repo / "docs/rfcs/initial-direction.md").exists()


def test_seed_clears_foundation_readiness_warning(tmp_path: Path) -> None:
    repo = _fresh_repo(tmp_path)
    config = load(find_config(repo))

    before = FoundationReadinessCheck().run(build_graph(repo, config))
    assert {f.doc_id for f in before} >= {"principles", "overview"}

    assert _seed_no_interactive(repo).exit_code == 0

    after = FoundationReadinessCheck().run(build_graph(repo, config))
    assert after == []


def test_seeded_docs_parse_cleanly(tmp_path: Path) -> None:
    repo = _fresh_repo(tmp_path)
    assert _seed_no_interactive(repo).exit_code == 0
    graph = load_graph(repo)
    assert graph.parse_failures == []
    assert graph.missing_frontmatter == []


def test_day_one_fresh_seeded_repo_reports_zero_findings(tmp_path: Path) -> None:
    """The acceptance contract for the scaffold: a freshly initialized and
    seeded repo must start life with 0 errors and 0 warnings under the
    configured profile. Day-one warnings teach adopters to ignore warnings."""
    repo = _fresh_repo(tmp_path)
    assert _seed_no_interactive(repo).exit_code == 0

    seed_repo(repo, "Adopt Irminsul")

    result = runner.invoke(
        app,
        ["check", "--format", "json", "--path", str(repo)],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["summary"]["errors"] == 0
    assert report["summary"]["warnings"] == 0, report["findings"]


def test_seed_interactive_prompts(tmp_path: Path) -> None:
    repo = _fresh_repo(tmp_path)
    answers = "\n".join(
        [
            "Keep it simple",
            "A focused CLI",
            "Simplicity scales",
            "An early adopter",
            "",  # non-goals
            "",  # direction risks
        ]
    )
    result = runner.invoke(app, ["seed", "--path", str(repo)], input=answers + "\n")
    assert result.exit_code == 0, result.stdout
    assert "PIB statement" in result.stdout
    principles = (repo / "docs/foundation/principles.md").read_text(encoding="utf-8")
    assert "Keep it simple" in principles


def test_seed_missing_required_flags_errors(tmp_path: Path) -> None:
    repo = _fresh_repo(tmp_path)
    result = runner.invoke(
        app,
        ["seed", "--no-interactive", "--principle", "only this", "--path", str(repo)],
    )
    # The validation exits 2; the message lands on stdout or stderr depending
    # on the click version, so check both.
    assert result.exit_code == 2
    message = result.output
    try:
        message += result.stderr
    except ValueError:
        pass
    assert "--idea" in message


def test_gather_answers_from_flags_names_every_missing_flag() -> None:
    # Direct unit coverage of the flag-mode validation: it must raise a plain error
    # (not an AssertionError) and name each missing flag, including empty-string values.
    with pytest.raises(SeedError) as excinfo:
        gather_answers_from_flags(
            project_name="proj",
            principle="Keep it simple",
            idea=None,
            belief=None,
            first_user="",
            non_goals=None,
            direction_risks=None,
        )
    assert excinfo.value.code == 2
    out = str(excinfo.value)
    assert "--idea" in out
    assert "--belief" in out
    assert "--first-user" in out
    assert "--principle" not in out


def test_seed_refuses_edited_foundation(tmp_path: Path) -> None:
    repo = _fresh_repo(tmp_path)
    assert _seed_no_interactive(repo).exit_code == 0
    # Second run: foundation docs are now real content, not scaffold.
    result = _seed_no_interactive(repo)
    assert result.exit_code == 1
    assert "edited away" in cli_output(result)


def test_seed_reseed_overwrites(tmp_path: Path) -> None:
    repo = _fresh_repo(tmp_path)
    assert _seed_no_interactive(repo).exit_code == 0
    result = runner.invoke(
        app,
        [
            "seed",
            "--no-interactive",
            "--reseed",
            "--principle",
            "A revised principle",
            "--idea",
            "A revised idea",
            "--belief",
            "A revised belief",
            "--first-user",
            "A revised user",
            "--path",
            str(repo),
        ],
    )
    assert result.exit_code == 0, result.stdout
    principles = (repo / "docs/foundation/principles.md").read_text(encoding="utf-8")
    assert "A revised principle" in principles
    assert "Docs and code evolve together" not in principles


def test_seed_merge_appends_dated_block(tmp_path: Path) -> None:
    repo = _fresh_repo(tmp_path)
    assert _seed_no_interactive(repo).exit_code == 0
    result = _seed_no_interactive(repo, "--merge")
    assert result.exit_code == 0, result.stdout
    principles = (repo / "docs/foundation/principles.md").read_text(encoding="utf-8")
    assert "## Seed pass — " in principles
    # Original seeded content is retained.
    assert "Docs and code evolve together" in principles


def test_init_no_interactive_does_not_seed(tmp_path: Path) -> None:
    repo = _fresh_repo(tmp_path)
    principles = (repo / "docs/foundation/principles.md").read_text(encoding="utf-8")
    assert "Replace this paragraph with your own principle" in principles


def test_init_fresh_interactive_offers_seed(tmp_path: Path) -> None:
    target = tmp_path / "proj"
    # language, project name, confirm seed, then the six PIB prompts.
    feed = "\n".join(
        ["python", "", "y", "Evolve together", "A CLI", "Prevent drift", "A maintainer", "", ""]
    )
    result = runner.invoke(app, ["init", "--fresh", "--path", str(target)], input=feed + "\n")
    assert result.exit_code == 0, result.stdout
    principles = (target / "docs/foundation/principles.md").read_text(encoding="utf-8")
    assert "Evolve together" in principles
    assert "A CLI" in (target / "docs/architecture/overview.md").read_text(encoding="utf-8")


def test_init_fresh_interactive_can_decline_seed(tmp_path: Path) -> None:
    target = tmp_path / "proj"
    feed = "\n".join(["python", "", "n"])
    result = runner.invoke(app, ["init", "--fresh", "--path", str(target)], input=feed + "\n")
    assert result.exit_code == 0, result.stdout
    principles = (target / "docs/foundation/principles.md").read_text(encoding="utf-8")
    assert "Replace this paragraph with your own principle" in principles


def test_seed_refuses_an_authored_doc_that_kept_a_scaffold_heading(tmp_path: Path) -> None:
    """A fully authored doc that kept a prompt's wording as a heading was overwritten, and
    its `status: stable` downgraded to draft, while seeding recognised prompts by their
    words. Nothing marks that heading, so the doc is authored and seeding refuses it.
    """
    repo = _fresh_repo(tmp_path)
    assert _seed_no_interactive(repo).exit_code == 0

    principles = repo / "docs" / "foundation" / "principles.md"
    overview = repo / "docs" / "architecture" / "overview.md"
    principles.write_text(
        "---\nid: principles\ntitle: Principles\nstatus: stable\n---\n\n"
        "# Principles\n\nHours of authored intent.\n\n"
        "## Who should it serve first?\n\nResearchers.\n",
        encoding="utf-8",
    )
    overview.write_text(
        "---\nid: overview\ntitle: Overview\nstatus: stable\n---\n\n"
        "# Overview\n\nAuthored architecture prose.\n\n"
        "## Purpose\n\nWhat this system does, in one sentence.\n",
        encoding="utf-8",
    )

    result = _seed_no_interactive(repo)

    assert result.exit_code == 1
    assert "Hours of authored intent." in principles.read_text(encoding="utf-8")
    assert "status: stable" in principles.read_text(encoding="utf-8")


def test_seed_replaces_only_marked_text(tmp_path: Path) -> None:
    """A doc that answered one prompt and left the rest keeps its answer: seeding removes
    only the text a marker covers, and fills each section from the seed by its heading."""
    repo = _fresh_repo(tmp_path)
    principles = repo / "docs" / "foundation" / "principles.md"
    text = principles.read_text(encoding="utf-8")
    goal = "- _What is this system for?_ <!-- irminsul:placeholder -->"
    assert goal in text
    principles.write_text(text.replace(goal, "- Keep every doc honest."), encoding="utf-8")

    assert _seed_no_interactive(repo).exit_code == 0

    seeded = principles.read_text(encoding="utf-8")
    assert "irminsul:placeholder" not in seeded
    assert "## Goals\n\n- Keep every doc honest." in seeded
    assert "- **Principle** — Docs and code evolve together" in seeded
    assert "- Hosting a server" in seeded
    assert "Who should it serve first?" not in seeded
    assert seeded.count("## Non-goals") == 1


def test_seed_keeps_the_line_endings_of_the_docs_it_rewrites(tmp_path: Path) -> None:
    repo = _fresh_repo(tmp_path)
    docs = [
        repo / "docs" / "foundation" / "principles.md",
        repo / "docs" / "architecture" / "overview.md",
    ]
    for doc in docs:
        doc.write_bytes(doc.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))

    assert _seed_no_interactive(repo).exit_code == 0

    for doc in docs:
        raw = doc.read_bytes()
        assert raw.count(b"\n") == raw.count(b"\r\n") > 0, doc


def test_seed_renders_the_scaffold_init_writes(tmp_path: Path) -> None:
    """One template per doc: a seeded principles doc is init's scaffold with the answers in
    place of the marked prompts, so a scaffold edit reaches both."""
    from irminsul.init.command import render_scaffold
    from irminsul.seed.command import SeedAnswers

    answers = SeedAnswers(
        principle="P", idea="I", belief="B", first_user="U", project_name="demo", today="x"
    )
    seeded = render_scaffold(
        "docs/foundation/principles.md.j2", {"project_name": "demo", "seed": answers}
    )
    scaffolded = render_scaffold(
        "docs/foundation/principles.md.j2", {"project_name": "demo", "seed": None}
    )

    assert seeded.split("\n## ")[0].splitlines()[:9] == scaffolded.splitlines()[:9]
    assert "- **Principle** — P" in seeded
    assert "irminsul:placeholder" not in seeded
    assert "irminsul:placeholder" in scaffolded
