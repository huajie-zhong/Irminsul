"""End-to-end tests for `irminsul seed` and its `init` integration."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from irminsul.checks.foundation_readiness import FoundationReadinessCheck
from irminsul.cli import app
from irminsul.config import find_config, load
from irminsul.docgraph import build_graph

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
    result = runner.invoke(app, ["init", "--fresh", "--no-interactive", "--path", str(target)])
    assert result.exit_code == 0, result.stdout
    return target


def _seed_no_interactive(repo: Path, *extra: str) -> object:
    return runner.invoke(app, ["seed", "--no-interactive", *_FLAGS, *extra, "--path", str(repo)])


def test_seed_with_flags_writes_foundation_and_anchors(tmp_path: Path) -> None:
    repo = _fresh_repo(tmp_path)
    result = _seed_no_interactive(repo)
    assert result.exit_code == 0, result.stdout

    principles = (repo / "docs/00-foundation/principles.md").read_text(encoding="utf-8")
    assert "Docs and code evolve together" in principles
    assert "A solo maintainer adopting the system" in principles

    overview = (repo / "docs/10-architecture/overview.md").read_text(encoding="utf-8")
    assert "A CLI that enforces doc structure in CI" in overview

    # The anchoring ADR is titled from the idea; the anchoring RFC is created.
    assert (repo / "docs/50-decisions/0002-a-cli-that-enforces-doc-structure-in-ci.md").is_file()
    assert (repo / "docs/80-evolution/rfcs/0001-initial-direction.md").is_file()


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
    graph = build_graph(repo, load(find_config(repo)))
    assert graph.parse_failures == []
    assert graph.missing_frontmatter == []
    assert "0001-initial-direction" in graph.nodes


def test_seed_from_json(tmp_path: Path) -> None:
    repo = _fresh_repo(tmp_path)
    seed_file = tmp_path / "seed.json"
    seed_file.write_text(
        json.dumps(
            {
                "principle": "Stay deterministic",
                "idea": "Ship a check engine",
                "belief": "Determinism builds trust",
                "first_user": "A CI pipeline",
                "non_goals": ["Being a wiki"],
                "direction_risks": ["Scope creep"],
            }
        ),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["seed", "--json", str(seed_file), "--path", str(repo)])
    assert result.exit_code == 0, result.stdout
    principles = (repo / "docs/00-foundation/principles.md").read_text(encoding="utf-8")
    assert "Stay deterministic" in principles


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
    principles = (repo / "docs/00-foundation/principles.md").read_text(encoding="utf-8")
    assert "Keep it simple" in principles


def test_seed_missing_required_flags_errors(tmp_path: Path) -> None:
    repo = _fresh_repo(tmp_path)
    result = runner.invoke(
        app,
        ["seed", "--no-interactive", "--principle", "only this", "--path", str(repo)],
    )
    assert result.exit_code != 0
    assert "--idea" in result.stdout


def test_seed_refuses_edited_foundation(tmp_path: Path) -> None:
    repo = _fresh_repo(tmp_path)
    assert _seed_no_interactive(repo).exit_code == 0
    # Second run: foundation docs are now real content, not scaffold.
    result = _seed_no_interactive(repo)
    assert result.exit_code == 1
    assert "edited away" in result.stdout


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
    principles = (repo / "docs/00-foundation/principles.md").read_text(encoding="utf-8")
    assert "A revised principle" in principles
    assert "Docs and code evolve together" not in principles
    # --reseed refreshes foundation docs but does not re-anchor.
    adrs = list((repo / "docs/50-decisions").glob("000*-*.md"))
    assert not any("revised" in p.name for p in adrs)


def test_seed_merge_appends_dated_block(tmp_path: Path) -> None:
    repo = _fresh_repo(tmp_path)
    assert _seed_no_interactive(repo).exit_code == 0
    result = _seed_no_interactive(repo, "--merge")
    assert result.exit_code == 0, result.stdout
    principles = (repo / "docs/00-foundation/principles.md").read_text(encoding="utf-8")
    assert "## Seed pass — " in principles
    # Original seeded content is retained.
    assert "Docs and code evolve together" in principles


def test_init_no_interactive_does_not_seed(tmp_path: Path) -> None:
    repo = _fresh_repo(tmp_path)
    principles = (repo / "docs/00-foundation/principles.md").read_text(encoding="utf-8")
    assert "Replace this paragraph with your own principle" in principles
    assert not (repo / "docs/80-evolution/rfcs").exists()


def test_init_fresh_interactive_offers_seed(tmp_path: Path) -> None:
    target = tmp_path / "proj"
    # project name, render target, confirm seed, then the six PIB prompts.
    feed = "\n".join(
        ["", "", "y", "Evolve together", "A CLI", "Prevent drift", "A maintainer", "", ""]
    )
    result = runner.invoke(app, ["init", "--fresh", "--path", str(target)], input=feed + "\n")
    assert result.exit_code == 0, result.stdout
    principles = (target / "docs/00-foundation/principles.md").read_text(encoding="utf-8")
    assert "Evolve together" in principles
    assert (target / "docs/80-evolution/rfcs/0001-initial-direction.md").is_file()


def test_init_fresh_interactive_can_decline_seed(tmp_path: Path) -> None:
    target = tmp_path / "proj"
    feed = "\n".join(["", "", "n"])
    result = runner.invoke(app, ["init", "--fresh", "--path", str(target)], input=feed + "\n")
    assert result.exit_code == 0, result.stdout
    principles = (target / "docs/00-foundation/principles.md").read_text(encoding="utf-8")
    assert "Replace this paragraph with your own principle" in principles
